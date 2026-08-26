# =========================================================
#  aerion_governance_suite.py  —  AERION Governance Batch
#  Voting • Governance/Proposals • Treasury • Tournament • Case
#
#  ONE module, ONE register call. Everything below shares the
#  same injected refs (_bot/_supa_get/_supa_post/_supa_patch/
#  _check_member) and the same permanent-Voting-ID + voting
#  engine, exactly like your other aerion_*.py files.
#
#  Run aerion_governance_schema.sql in Supabase FIRST.
#
#  Integration in bot1.py:
#    from aerion_governance_suite import register_governance_suite
#    # in on_ready():
#    register_governance_suite(bot, supabase_get, supabase_post, supabase_patch, check_membership)
# =========================================================

import asyncio, random, string, math
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
import pytz

_IST = pytz.timezone("Asia/Kolkata")
BOT_NAME = "AERION"
FOOTER   = f"{BOT_NAME} Governance Suite"
TREASURY_VOTE_THRESHOLD = 500  # spends >= this need a passed vote

# ── Injected refs (shared across every section below) ─────
_bot          = None
_supa_get     = None
_supa_post    = None
_supa_patch   = None
_check_member = None

# ── Hooks: internal — governance/treasury/case register here
#    so voting.close_vote() can call back into the right
#    section without any cross-file imports ─────────────────
_close_hooks: dict = {}

# ─────────────────────────────────────────────────────────
#  SHARED HELPERS
# ─────────────────────────────────────────────────────────
def _now_ist(): return datetime.now(_IST)
def _now_utc(): return datetime.now(timezone.utc)
def _ts():      return _now_ist().strftime("%d %b %Y  %I:%M %p IST")

def _gen_uid(prefix: str) -> str:
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}-" + ''.join(random.choices(chars, k=8))

def _parse_dt(iso: str):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None

def _fmt_pts(v):
    return f"{float(v):,.0f} pts"

async def _gate(ctx) -> bool:
    """Standard AERION membership gate — same shape as your other modules."""
    if not _check_member:
        return True
    try:
        status = await _check_member(str(ctx.author.id))
    except Exception:
        return True
    if not status["linked"]:
        await ctx.send("🔗 Link your Discord to the AERO portal first with `/link <code>`.", ephemeral=True)
        return False
    if not status["has_access"]:
        cost = 1000 if status["is_new"] else 100
        await ctx.send(f"🔒 **AERION Membership Required** — use `/subscribe` ({cost:,} AERO Points).", ephemeral=True)
        return False
    return True

def _is_admin(ctx) -> bool:
    return bool(ctx.author.guild_permissions.manage_guild)


# ═══════════════════════════════════════════════════════════
#  SECTION 1 — VOTING CORE
#  Permanent Voting ID + poll create/vote/close/results.
#  Everything else in this file builds on top of it.
# ═══════════════════════════════════════════════════════════

async def get_voter_row(discord_id: str) -> dict | None:
    try:
        rows = await _supa_get("voting_ids", {"discord_id": f"eq.{discord_id}", "select": "*"})
        return rows[0] if rows else None
    except Exception as e:
        print(f"[VOTING] get_voter_row error: {e}")
        return None

async def _cmd_voterid(ctx):
    await ctx.defer(ephemeral=True)
    if not await _gate(ctx): return

    existing = await get_voter_row(str(ctx.author.id))
    if existing:
        embed = discord.Embed(
            title="🗳️ Your AERION Voting ID",
            description=(
                f"You're already registered.\n\n"
                f"**Voter ID:** `{existing['voter_id']}`\n"
                f"**STS ID:** `{existing['sts_id']}`\n"
                f"**Registered:** {existing['created_at'][:10]}"
            ),
            color=0x00d4ff
        )
        embed.set_footer(text=FOOTER)
        return await ctx.send(embed=embed, ephemeral=True)

    status = await _check_member(str(ctx.author.id)) if _check_member else None
    if not status or not status.get("linked"):
        return await ctx.send("❌ Link your portal account first with `/link <code>`.", ephemeral=True)

    voter_id = _gen_uid("AVID")
    try:
        await _supa_post("voting_ids", {
            "voter_id":   voter_id,
            "discord_id": str(ctx.author.id),
            "sts_id":     status["sts_id"],
            "name":       status["name"],
            "guild_id":   str(ctx.guild.id) if ctx.guild else None,
            "created_at": _now_utc().isoformat(),
        })
    except Exception as e:
        return await ctx.send(f"❌ Registration failed: {e}", ephemeral=True)

    embed = discord.Embed(
        title="✅ Voting ID Issued",
        description=(
            f"**Voter ID:** `{voter_id}`\n"
            f"**Linked to STS:** `{status['sts_id']}`\n\n"
            "This ID is permanent — it's what checks you in whenever you vote. "
            "You never need to register again."
        ),
        color=0x00ff88
    )
    embed.set_footer(text=FOOTER)
    await ctx.send(embed=embed, ephemeral=True)

async def _get_vote(vote_uid: str) -> dict | None:
    try:
        rows = await _supa_get("votes", {"vote_uid": f"eq.{vote_uid}", "select": "*"})
        return rows[0] if rows else None
    except Exception:
        return None

async def _get_vote_records(vote_uid: str) -> list:
    try:
        rows = await _supa_get("vote_records", {"vote_uid": f"eq.{vote_uid}", "select": "*"})
        return rows or []
    except Exception:
        return []

def _tally(records: list, options: list) -> dict:
    counts = {o: 0 for o in options}
    for r in records:
        if r["option_choice"] in counts:
            counts[r["option_choice"]] += 1
    return counts

async def _eligible_count(vote: dict) -> int:
    try:
        rows = await _supa_get("voting_ids", {"guild_id": f"eq.{vote.get('guild_id')}", "select": "voter_id"})
        return len(rows) if rows else 0
    except Exception:
        return 0

def _progress_bar(pct: float, length=14) -> str:
    filled = round(length * min(max(pct, 0), 100) / 100)
    return "█" * filled + "░" * (length - filled)

async def _build_vote_embed(vote: dict, final=False) -> discord.Embed:
    records = await _get_vote_records(vote["vote_uid"])
    options = vote["options"] if isinstance(vote["options"], list) else []
    counts  = _tally(records, options)
    total   = sum(counts.values())
    elig    = await _eligible_count(vote)
    part_pct = (total / elig * 100) if elig else 0

    end_dt = _parse_dt(vote["end_at"])
    time_txt = "Closed" if final else (f"<t:{int(end_dt.timestamp())}:R>" if end_dt else "—")

    color = 0x95a5a6 if final else 0x00d4ff
    embed = discord.Embed(title=f"🗳️ {vote['title']}", description=vote.get("description") or "\u200b", color=color)
    lines = []
    for opt in options:
        c = counts.get(opt, 0)
        pct = (c / total * 100) if total else 0
        lines.append(f"**{opt}** — {c} vote(s)  ({pct:.0f}%)\n`{_progress_bar(pct)}`")
    embed.add_field(name="📊 Current Standing" if not final else "📊 Final Result",
                     value="\n\n".join(lines) or "No votes yet", inline=False)
    embed.add_field(name="👥 Participation", value=f"{total} voted ({part_pct:.0f}% of {elig} eligible)", inline=True)
    embed.add_field(name="⏱️ Status" if not final else "🏁 Ended", value=time_txt, inline=True)
    embed.add_field(name="🙈 Anonymity", value="Anonymous" if vote.get("anonymous", True) else "Public", inline=True)

    if final:
        if vote.get("is_tie"):
            embed.add_field(name="⚖️ Result", value="**TIE** — no single winning option", inline=False)
        else:
            embed.add_field(name="🏆 Winning Option", value=f"**{vote.get('winner_option','—')}**", inline=False)

    embed.set_footer(text=f"{FOOTER} • ID: {vote['vote_uid']} • {_ts()}")
    return embed

class _VoteSelect(discord.ui.Select):
    def __init__(self, vote_uid: str, options: list):
        select_opts = [discord.SelectOption(label=o[:100], value=o) for o in options][:25]
        super().__init__(placeholder="Cast your vote...", min_values=1, max_values=1,
                          options=select_opts, custom_id=f"aerion_vote_select:{vote_uid}")
        self.vote_uid = vote_uid

    async def callback(self, interaction: discord.Interaction):
        await _handle_vote_cast(interaction, self.vote_uid, self.values[0])

class VoteView(discord.ui.View):
    """Persistent — reattached to open votes on startup by _reattach_open_views()."""
    def __init__(self, vote_uid: str, options: list):
        super().__init__(timeout=None)
        self.add_item(_VoteSelect(vote_uid, options))

async def _handle_vote_cast(interaction: discord.Interaction, vote_uid: str, option: str):
    await interaction.response.defer(ephemeral=True)
    discord_id = str(interaction.user.id)

    if _check_member:
        status = await _check_member(discord_id)
        if not status["linked"]:
            return await interaction.followup.send("🔗 Link your portal account first with `/link <code>`.", ephemeral=True)
        if not status["has_access"]:
            return await interaction.followup.send("🔒 Active AERION membership required to vote. Use `/subscribe`.", ephemeral=True)

    voter = await get_voter_row(discord_id)
    if not voter:
        return await interaction.followup.send("❌ You need a permanent Voting ID first. Run `/voterid`.", ephemeral=True)

    vote = await _get_vote(vote_uid)
    if not vote or vote["status"] != "open":
        return await interaction.followup.send("❌ This vote is no longer open.", ephemeral=True)

    end_dt = _parse_dt(vote["end_at"])
    if end_dt and _now_utc() >= end_dt:
        return await interaction.followup.send("⏱️ Voting time is over — results are being finalised.", ephemeral=True)

    role_id = vote.get("eligible_role_id")
    if role_id and interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if not member or not any(str(r.id) == str(role_id) for r in member.roles):
            return await interaction.followup.send("❌ You're not eligible to vote on this one.", ephemeral=True)

    try:
        await _supa_post("vote_records", {
            "vote_uid": vote_uid, "voter_id": voter["voter_id"], "discord_id": discord_id,
            "option_choice": option, "voted_at": _now_utc().isoformat(),
        })
    except Exception as e:
        if "duplicate" in str(e).lower() or "23505" in str(e):
            return await interaction.followup.send("⚠️ You've already voted on this. One member = one vote.", ephemeral=True)
        return await interaction.followup.send(f"❌ Vote failed: {e}", ephemeral=True)

    await interaction.followup.send("✅ Your vote has been recorded. Nobody can see what you chose.", ephemeral=True)

    try:
        if vote.get("channel_id") and vote.get("message_id"):
            channel = _bot.get_channel(int(vote["channel_id"]))
            if channel:
                msg = await channel.fetch_message(int(vote["message_id"]))
                fresh = await _get_vote(vote_uid)
                await msg.edit(embed=await _build_vote_embed(fresh))
    except Exception as e:
        print(f"[VOTING] live refresh failed: {e}")

async def close_vote(vote_uid: str, cancelled=False) -> dict | None:
    vote = await _get_vote(vote_uid)
    if not vote or vote["status"] != "open":
        return vote

    if cancelled:
        await _supa_patch("votes", {"vote_uid": f"eq.{vote_uid}"}, {"status": "cancelled", "closed_at": _now_utc().isoformat()})
        return await _get_vote(vote_uid)

    records = await _get_vote_records(vote_uid)
    options = vote["options"] if isinstance(vote["options"], list) else []
    counts  = _tally(records, options)
    total   = sum(counts.values())

    winner, is_tie = None, False
    if total:
        mx  = max(counts.values())
        top = [o for o, c in counts.items() if c == mx]
        if len(top) > 1: is_tie = True
        else: winner = top[0]

    await _supa_patch("votes", {"vote_uid": f"eq.{vote_uid}"}, {
        "status": "closed", "result": counts, "winner_option": winner,
        "is_tie": is_tie, "closed_at": _now_utc().isoformat(),
    })
    fresh = await _get_vote(vote_uid)

    try:
        if vote.get("channel_id") and vote.get("message_id"):
            channel = _bot.get_channel(int(vote["channel_id"]))
            if channel:
                msg = await channel.fetch_message(int(vote["message_id"]))
                await msg.edit(embed=await _build_vote_embed(fresh, final=True), view=None)
                await channel.send(embed=await _build_vote_embed(fresh, final=True))
    except Exception as e:
        print(f"[VOTING] close announce failed: {e}")

    linked_type = fresh.get("linked_type")
    if linked_type and linked_type in _close_hooks:
        try:
            await _close_hooks[linked_type](fresh)
        except Exception as e:
            print(f"[VOTING] close hook '{linked_type}' failed: {e}")

    return fresh

async def create_vote(title: str, description: str, options: list, duration_hours: float,
                       created_by: str, channel: discord.abc.Messageable, guild_id, anonymous=True,
                       eligible_role_id=None, linked_type=None, linked_uid=None) -> dict:
    vote_uid = _gen_uid("VOTE")
    end_at = _now_utc() + timedelta(hours=duration_hours)
    row = {
        "vote_uid": vote_uid, "title": title, "description": description,
        "vote_type": "yesno" if set(options) <= {"Yes", "No", "Abstain"} else "multi",
        "options": options, "anonymous": anonymous,
        "eligible_role_id": str(eligible_role_id) if eligible_role_id else None,
        "guild_id": str(guild_id) if guild_id else None, "created_by": created_by,
        "start_at": _now_utc().isoformat(), "end_at": end_at.isoformat(), "status": "open",
        "linked_type": linked_type, "linked_uid": linked_uid, "created_at": _now_utc().isoformat(),
    }
    await _supa_post("votes", row)
    vote = await _get_vote(vote_uid)

    embed = await _build_vote_embed(vote)
    view  = VoteView(vote_uid, options)
    msg   = await channel.send(embed=embed, view=view)

    await _supa_patch("votes", {"vote_uid": f"eq.{vote_uid}"}, {"channel_id": str(channel.id), "message_id": str(msg.id)})
    return await _get_vote(vote_uid)

async def _cmd_vote_create(ctx, title: str, duration_hours: float, options: str = "Yes,No,Abstain",
                            description: str = "", anonymous: bool = True, eligible_role: discord.Role = None):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    if duration_hours <= 0 or duration_hours > 24 * 30:
        return await ctx.send("❌ Duration must be between 0 and 720 hours.", ephemeral=True)

    opt_list = [o.strip() for o in options.split(",") if o.strip()][:25]
    if len(opt_list) < 2:
        return await ctx.send("❌ Provide at least 2 options, comma-separated.", ephemeral=True)

    vote = await create_vote(title=title, description=description, options=opt_list, duration_hours=duration_hours,
                              created_by=str(ctx.author.id), channel=ctx.channel, guild_id=ctx.guild.id if ctx.guild else None,
                              anonymous=anonymous, eligible_role_id=eligible_role.id if eligible_role else None)
    await ctx.send(f"✅ Vote `{vote['vote_uid']}` created and posted above.", ephemeral=True)

async def _cmd_vote_results(ctx, vote_uid: str):
    await ctx.defer()
    vote = await _get_vote(vote_uid.strip().upper())
    if not vote:
        return await ctx.send("❌ Vote not found.")
    await ctx.send(embed=await _build_vote_embed(vote, final=(vote["status"] != "open")))

async def _cmd_vote_close(ctx, vote_uid: str):
    await ctx.defer(ephemeral=True)
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    vote = await close_vote(vote_uid.strip().upper())
    if not vote:
        return await ctx.send("❌ Vote not found.", ephemeral=True)
    await ctx.send(f"✅ Vote `{vote_uid}` closed. Winner: **{vote.get('winner_option') or ('TIE' if vote.get('is_tie') else '—')}**", ephemeral=True)

async def _cmd_vote_cancel(ctx, vote_uid: str):
    await ctx.defer(ephemeral=True)
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    vote = await close_vote(vote_uid.strip().upper(), cancelled=True)
    if not vote:
        return await ctx.send("❌ Vote not found.", ephemeral=True)
    await ctx.send(f"🚫 Vote `{vote_uid}` cancelled.", ephemeral=True)

async def _cmd_vote_list(ctx, status: str = "open"):
    await ctx.defer()
    try:
        rows = await _supa_get("votes", {
            "guild_id": f"eq.{ctx.guild.id}" if ctx.guild else "is.null",
            "status": f"eq.{status}", "select": "vote_uid,title,end_at,status",
            "order": "created_at.desc", "limit": "15"
        })
    except Exception:
        rows = []
    if not rows:
        return await ctx.send(f"📭 No `{status}` votes found.")
    lines = [f"`{r['vote_uid']}` — **{r['title']}** ({r['status']})" for r in rows]
    embed = discord.Embed(title=f"🗳️ Votes — {status.upper()}", description="\n".join(lines), color=0x00d4ff)
    embed.set_footer(text=FOOTER)
    await ctx.send(embed=embed)

async def _auto_close_loop():
    await _bot.wait_until_ready()
    print("[VOTING] Auto-close loop started")
    while not _bot.is_closed():
        await asyncio.sleep(60)
        try:
            open_votes = await _supa_get("votes", {"status": "eq.open", "select": "vote_uid,end_at"})
            now = _now_utc()
            for v in open_votes or []:
                end_dt = _parse_dt(v["end_at"])
                if end_dt and now >= end_dt:
                    print(f"[VOTING] Auto-closing {v['vote_uid']}")
                    await close_vote(v["vote_uid"])
        except Exception as e:
            print(f"[VOTING] auto-close loop error: {e}")

async def _reattach_open_views():
    await _bot.wait_until_ready()
    try:
        open_votes = await _supa_get("votes", {"status": "eq.open", "select": "vote_uid,options"})
        for v in open_votes or []:
            options = v["options"] if isinstance(v["options"], list) else []
            if options:
                _bot.add_view(VoteView(v["vote_uid"], options))
        print(f"[VOTING] Reattached {len(open_votes or [])} open vote view(s)")
    except Exception as e:
        print(f"[VOTING] reattach error: {e}")


# ═══════════════════════════════════════════════════════════
#  SECTION 2 — GOVERNANCE / PROPOSALS
#  Flow: Proposal → Discussion → Voting → Result → Archive
# ═══════════════════════════════════════════════════════════

STATUS_COLORS = {
    "draft": 0x95a5a6, "discussion": 0x00d4ff, "voting": 0xf39c12,
    "passed": 0x00ff88, "rejected": 0xff4757, "cancelled": 0x747d8c, "archived": 0x2f3542,
}

async def _get_proposal(proposal_uid: str) -> dict | None:
    rows = await _supa_get("proposals", {"proposal_uid": f"eq.{proposal_uid}", "select": "*"})
    return rows[0] if rows else None

def _build_proposal_embed(p: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"📜 Proposal {p['proposal_uid']}",
        description=f"**{p['title']}**\n\n{p.get('description') or '—'}",
        color=STATUS_COLORS.get(p["status"], 0x2b2d31)
    )
    embed.add_field(name="Author", value=f"<@{p['creator_discord_id']}>", inline=True)
    embed.add_field(name="Status", value=p["status"].upper(), inline=True)
    embed.add_field(name="Created", value=p["created_at"][:10], inline=True)
    if p.get("vote_uid"):
        embed.add_field(name="Linked Vote", value=f"`{p['vote_uid']}`", inline=True)
    if p.get("final_result"):
        embed.add_field(name="Final Result", value=p["final_result"], inline=False)
    embed.set_footer(text=f"{FOOTER} • {_ts()}")
    return embed

class _ProposalView(discord.ui.View):
    def __init__(self, proposal_uid: str):
        super().__init__(timeout=None)
        self.proposal_uid = proposal_uid

    async def _refresh(self, interaction):
        p = await _get_proposal(self.proposal_uid)
        view = self if p["status"] in ("discussion", "voting") else None
        await interaction.message.edit(embed=_build_proposal_embed(p), view=view)

    @discord.ui.button(label="🗳️ Start Voting", style=discord.ButtonStyle.primary, custom_id="aerion_prop_startvote")
    async def start_vote(self, interaction: discord.Interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        p = await _get_proposal(self.proposal_uid)
        if not p or p["status"] != "discussion":
            return await interaction.response.send_message("❌ Proposal isn't in Discussion status.", ephemeral=True)
        await interaction.response.defer()
        vote = await create_vote(title=f"Proposal: {p['title']}", description=p.get("description") or "",
                                  options=["Yes", "No", "Abstain"], duration_hours=24,
                                  created_by=str(interaction.user.id), channel=interaction.channel,
                                  guild_id=interaction.guild_id, anonymous=True,
                                  linked_type="proposal", linked_uid=self.proposal_uid)
        await _supa_patch("proposals", {"proposal_uid": f"eq.{self.proposal_uid}"},
                           {"status": "voting", "vote_uid": vote["vote_uid"]})
        await self._refresh(interaction)

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.danger, custom_id="aerion_prop_cancel")
    async def cancel(self, interaction: discord.Interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        await _supa_patch("proposals", {"proposal_uid": f"eq.{self.proposal_uid}"}, {"status": "cancelled"})
        await self._refresh(interaction)

    @discord.ui.button(label="🗄️ Archive", style=discord.ButtonStyle.secondary, custom_id="aerion_prop_archive")
    async def archive(self, interaction: discord.Interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        await _supa_patch("proposals", {"proposal_uid": f"eq.{self.proposal_uid}"}, {"status": "archived"})
        await self._refresh(interaction)

async def _on_proposal_vote_closed(vote: dict):
    proposal_uid = vote["linked_uid"]
    p = await _get_proposal(proposal_uid)
    if not p:
        return

    if vote["status"] == "cancelled":
        final_status, result_txt = "cancelled", "Vote was cancelled."
    elif vote.get("is_tie"):
        final_status, result_txt = "rejected", "Tie vote — proposal did not pass."
    elif vote.get("winner_option") == "Yes":
        final_status, result_txt = "passed", f"✅ Passed — {vote['result']}"
    else:
        final_status, result_txt = "rejected", f"❌ Rejected — {vote['result']}"

    await _supa_patch("proposals", {"proposal_uid": f"eq.{proposal_uid}"},
                       {"status": final_status, "final_result": result_txt, "decided_at": _now_utc().isoformat()})

    try:
        if p.get("channel_id"):
            channel = _bot.get_channel(int(p["channel_id"]))
            if channel:
                fresh = await _get_proposal(proposal_uid)
                await channel.send(embed=_build_proposal_embed(fresh))
    except Exception as e:
        print(f"[GOVERNANCE] announce failed: {e}")

async def _cmd_proposal_create(ctx, title: str, description: str = ""):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Only authorised roles can create official proposals.", ephemeral=True)

    proposal_uid = _gen_uid("PROP")
    await _supa_post("proposals", {
        "proposal_uid": proposal_uid, "title": title, "description": description,
        "creator_discord_id": str(ctx.author.id), "guild_id": str(ctx.guild.id) if ctx.guild else None,
        "status": "discussion", "created_at": _now_utc().isoformat(),
    })
    p = await _get_proposal(proposal_uid)
    view = _ProposalView(proposal_uid)
    msg = await ctx.send(embed=_build_proposal_embed(p), view=view)
    await _supa_patch("proposals", {"proposal_uid": f"eq.{proposal_uid}"},
                       {"channel_id": str(msg.channel.id), "message_id": str(msg.id)})

async def _cmd_proposal_view(ctx, proposal_uid: str):
    await ctx.defer()
    p = await _get_proposal(proposal_uid.strip().upper())
    if not p:
        return await ctx.send("❌ Proposal not found.")
    view = _ProposalView(p["proposal_uid"]) if p["status"] in ("discussion", "voting") else None
    await ctx.send(embed=_build_proposal_embed(p), view=view)

async def _cmd_proposal_list(ctx, status: str = "discussion"):
    await ctx.defer()
    rows = await _supa_get("proposals", {
        "guild_id": f"eq.{ctx.guild.id}" if ctx.guild else "is.null",
        "status": f"eq.{status}", "select": "proposal_uid,title,status",
        "order": "created_at.desc", "limit": "15"
    })
    if not rows:
        return await ctx.send(f"📭 No `{status}` proposals.")
    lines = [f"`{r['proposal_uid']}` — **{r['title']}**" for r in rows]
    embed = discord.Embed(title=f"📜 Proposals — {status.upper()}", description="\n".join(lines), color=0x00d4ff)
    embed.set_footer(text=FOOTER)
    await ctx.send(embed=embed)


# ═══════════════════════════════════════════════════════════
#  SECTION 3 — TREASURY
#  AERO Points are a virtual in-alliance currency only.
#  Small spends go through admin directly; big spends require
#  a passed vote before any points move.
# ═══════════════════════════════════════════════════════════

async def _balance(guild_id) -> float:
    rows = await _supa_get("treasury_ledger", {"guild_id": f"eq.{guild_id}", "select": "amount,type"})
    bal = 0.0
    for r in rows or []:
        bal += float(r["amount"]) if r["type"] == "income" else -float(r["amount"])
    return bal

async def _record_txn(guild_id, txn_type, amount, reason, actor, proposal_uid=None) -> dict:
    bal = await _balance(guild_id)
    new_bal = bal + amount if txn_type == "income" else bal - amount
    row = {
        "txn_uid": _gen_uid("TREAS"), "guild_id": str(guild_id), "type": txn_type,
        "amount": amount, "reason": reason, "actor_discord_id": str(actor),
        "proposal_uid": proposal_uid, "balance_after": new_bal, "created_at": _now_utc().isoformat(),
    }
    await _supa_post("treasury_ledger", row)
    return row

async def _cmd_treasury_dashboard(ctx):
    await ctx.defer()
    gid = ctx.guild.id if ctx.guild else 0
    bal = await _balance(gid)
    rows = await _supa_get("treasury_ledger", {"guild_id": f"eq.{gid}", "select": "*", "order": "created_at.desc", "limit": "10"})
    embed = discord.Embed(title="🏦 AERO Treasury Dashboard", color=0x00d4ff)
    embed.add_field(name="💰 Current Balance", value=f"**{_fmt_pts(bal)}**", inline=False)
    if rows:
        lines = [f"`{r['txn_uid']}` {'🟢+' if r['type']=='income' else '🔴-'}{_fmt_pts(r['amount'])} — {r['reason']} ({r['created_at'][:10]})" for r in rows]
        embed.add_field(name="📜 Recent Transactions", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="📜 Recent Transactions", value="No transactions yet.", inline=False)
    embed.set_footer(text=f"{FOOTER} • {_ts()} • AERO Points are virtual, no real-money value")
    await ctx.send(embed=embed)

async def _cmd_treasury_income(ctx, amount: float, reason: str):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.", ephemeral=True)
    txn = await _record_txn(ctx.guild.id, "income", amount, reason, ctx.author.id)
    await ctx.send(f"✅ Recorded income `{txn['txn_uid']}`: +{_fmt_pts(amount)} — {reason}\nNew balance: **{_fmt_pts(txn['balance_after'])}**")

async def _cmd_treasury_spend(ctx, amount: float, reason: str):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.", ephemeral=True)
    if amount >= TREASURY_VOTE_THRESHOLD:
        return await ctx.send(f"⚠️ Spends of {_fmt_pts(TREASURY_VOTE_THRESHOLD)} or more need member approval. Use `/treasury request` instead.", ephemeral=True)
    bal = await _balance(ctx.guild.id)
    if amount > bal:
        return await ctx.send(f"❌ Insufficient treasury balance ({_fmt_pts(bal)}).", ephemeral=True)
    txn = await _record_txn(ctx.guild.id, "expense", amount, reason, ctx.author.id)
    await ctx.send(f"✅ Recorded expense `{txn['txn_uid']}`: -{_fmt_pts(amount)} — {reason}\nNew balance: **{_fmt_pts(txn['balance_after'])}**")

async def _cmd_treasury_request(ctx, amount: float, reason: str, duration_hours: float = 24):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.", ephemeral=True)

    proposal_uid = _gen_uid("PROP")
    await _supa_post("proposals", {
        "proposal_uid": proposal_uid, "title": f"Treasury Spend: {_fmt_pts(amount)}", "description": reason,
        "creator_discord_id": str(ctx.author.id), "guild_id": str(ctx.guild.id) if ctx.guild else None,
        "status": "voting", "proposal_type": "treasury_spend", "treasury_amount": amount,
        "created_at": _now_utc().isoformat(),
    })
    vote = await create_vote(title=f"Approve treasury spend: {_fmt_pts(amount)}",
                              description=f"**Reason:** {reason}\n**Proposal:** `{proposal_uid}`",
                              options=["Yes", "No", "Abstain"], duration_hours=duration_hours,
                              created_by=str(ctx.author.id), channel=ctx.channel, guild_id=ctx.guild.id if ctx.guild else None,
                              anonymous=True, linked_type="treasury_spend", linked_uid=proposal_uid)
    await _supa_patch("proposals", {"proposal_uid": f"eq.{proposal_uid}"}, {"vote_uid": vote["vote_uid"]})
    await ctx.send(f"🗳️ Spend request `{proposal_uid}` is now up for vote — see the panel above.")

async def _on_treasury_vote_closed(vote: dict):
    proposal_uid = vote["linked_uid"]
    rows = await _supa_get("proposals", {"proposal_uid": f"eq.{proposal_uid}", "select": "*"})
    p = rows[0] if rows else None
    if not p:
        return

    if vote["status"] == "cancelled" or vote.get("is_tie") or vote.get("winner_option") != "Yes":
        await _supa_patch("proposals", {"proposal_uid": f"eq.{proposal_uid}"},
                           {"status": "rejected", "final_result": "❌ Not approved — no points spent.", "decided_at": _now_utc().isoformat()})
        outcome_txt = "❌ **Rejected** — no AERO Points were spent."
    else:
        amount = float(p["treasury_amount"])
        bal = await _balance(p["guild_id"])
        if amount > bal:
            await _supa_patch("proposals", {"proposal_uid": f"eq.{proposal_uid}"},
                               {"status": "rejected", "final_result": "❌ Approved but treasury balance was insufficient at execution time.", "decided_at": _now_utc().isoformat()})
            outcome_txt = "⚠️ Approved by vote, but the treasury balance was insufficient — no funds moved."
        else:
            txn = await _record_txn(p["guild_id"], "expense", amount, p["description"], p["creator_discord_id"], proposal_uid)
            await _supa_patch("proposals", {"proposal_uid": f"eq.{proposal_uid}"},
                               {"status": "passed", "final_result": f"✅ Approved — {txn['txn_uid']} executed.", "decided_at": _now_utc().isoformat()})
            outcome_txt = f"✅ **Approved** — `{txn['txn_uid']}` executed: -{_fmt_pts(amount)}. New balance: **{_fmt_pts(txn['balance_after'])}**"

    try:
        if vote.get("channel_id"):
            channel = _bot.get_channel(int(vote["channel_id"]))
            if channel:
                embed = discord.Embed(title=f"🏦 Treasury Proposal Result — {proposal_uid}", description=outcome_txt, color=0x00d4ff)
                embed.set_footer(text=FOOTER)
                await channel.send(embed=embed)
    except Exception as e:
        print(f"[TREASURY] announce failed: {e}")


# ═══════════════════════════════════════════════════════════
#  SECTION 4 — TOURNAMENT
#  Single-elimination bracket, auto-progression, optional
#  AERO Points reward credited to the winner on completion.
# ═══════════════════════════════════════════════════════════

async def _get_tourney(tourney_uid: str) -> dict | None:
    rows = await _supa_get("tournaments", {"tourney_uid": f"eq.{tourney_uid}", "select": "*"})
    return rows[0] if rows else None

async def _get_participants(tourney_uid: str) -> list:
    rows = await _supa_get("tournament_participants", {"tourney_uid": f"eq.{tourney_uid}", "select": "*", "order": "seed.asc"})
    return rows or []

async def _get_matches(tourney_uid: str, round_no: int = None) -> list:
    params = {"tourney_uid": f"eq.{tourney_uid}", "select": "*", "order": "round.asc,match_no.asc"}
    if round_no is not None:
        params["round"] = f"eq.{round_no}"
    rows = await _supa_get("tournament_matches", params)
    return rows or []

async def _build_tourney_embed(t: dict) -> discord.Embed:
    parts = await _get_participants(t["tourney_uid"])
    embed = discord.Embed(
        title=f"🏆 {t['title']}", description=t.get("description") or "\u200b",
        color={"registration": 0x00d4ff, "ongoing": 0xf39c12, "completed": 0x00ff88, "cancelled": 0x747d8c}.get(t["status"], 0x2b2d31)
    )
    embed.add_field(name="Status", value=t["status"].upper(), inline=True)
    embed.add_field(name="Participants", value=f"{len(parts)}/{t['max_participants']}", inline=True)
    embed.add_field(name="Reward", value=f"{t['reward_points']:,} AERO Points" if t["reward_points"] else "None", inline=True)
    if t["status"] == "registration" and t.get("reg_end_at"):
        embed.add_field(name="Registration Closes", value=f"<t:{int(datetime.fromisoformat(t['reg_end_at'].replace('Z','+00:00')).timestamp())}:R>", inline=False)
    if parts:
        names = ", ".join(p["name"] or p["sts_id"] for p in parts[:20])
        embed.add_field(name="👥 Registered", value=names + (f" +{len(parts)-20} more" if len(parts) > 20 else ""), inline=False)
    if t["status"] == "completed" and t.get("winner_name"):
        embed.add_field(name="🥇 Winner", value=f"**{t['winner_name']}**", inline=False)
    embed.set_footer(text=f"{FOOTER} • {t['tourney_uid']} • {_ts()}")
    return embed

class _TourneyView(discord.ui.View):
    def __init__(self, tourney_uid: str):
        super().__init__(timeout=None)
        self.tourney_uid = tourney_uid

    async def _refresh(self, interaction):
        t = await _get_tourney(self.tourney_uid)
        view = self if t["status"] == "registration" else None
        await interaction.message.edit(embed=await _build_tourney_embed(t), view=view)

    @discord.ui.button(label="📝 Register", style=discord.ButtonStyle.success, custom_id="aerion_tourney_register")
    async def register(self, interaction: discord.Interaction, button):
        await interaction.response.defer(ephemeral=True)
        discord_id = str(interaction.user.id)
        status = None
        if _check_member:
            status = await _check_member(discord_id)
            if not status["linked"]:
                return await interaction.followup.send("🔗 Link your portal account first with `/link <code>`.", ephemeral=True)
            if not status["has_access"]:
                return await interaction.followup.send("🔒 Active membership required. Use `/subscribe`.", ephemeral=True)

        t = await _get_tourney(self.tourney_uid)
        if t["status"] != "registration":
            return await interaction.followup.send("❌ Registration is closed.", ephemeral=True)
        parts = await _get_participants(self.tourney_uid)
        if len(parts) >= t["max_participants"]:
            return await interaction.followup.send("❌ Tournament is full.", ephemeral=True)
        if any(p["discord_id"] == discord_id for p in parts):
            return await interaction.followup.send("⚠️ You're already registered.", ephemeral=True)

        sts_id = status["sts_id"] if status else discord_id
        name   = status["name"] if status else interaction.user.display_name
        try:
            await _supa_post("tournament_participants", {
                "tourney_uid": self.tourney_uid, "sts_id": sts_id, "discord_id": discord_id,
                "name": name, "seed": len(parts) + 1, "joined_at": _now_utc().isoformat(),
            })
        except Exception as e:
            return await interaction.followup.send(f"❌ Registration failed: {e}", ephemeral=True)
        await interaction.followup.send("✅ You're registered!", ephemeral=True)
        await self._refresh(interaction)

    @discord.ui.button(label="▶ Start Tournament", style=discord.ButtonStyle.primary, custom_id="aerion_tourney_start")
    async def start(self, interaction: discord.Interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        result = await _start_tournament(self.tourney_uid)
        if not result["ok"]:
            return await interaction.followup.send(result["message"], ephemeral=True)
        t = await _get_tourney(self.tourney_uid)
        await interaction.message.edit(embed=await _build_tourney_embed(t), view=None)
        await _post_bracket(interaction.channel, self.tourney_uid, round_no=1)

    @discord.ui.button(label="🚫 Cancel", style=discord.ButtonStyle.danger, custom_id="aerion_tourney_cancel")
    async def cancel(self, interaction: discord.Interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        await _supa_patch("tournaments", {"tourney_uid": f"eq.{self.tourney_uid}"}, {"status": "cancelled"})
        await self._refresh(interaction)

async def _start_tournament(tourney_uid: str) -> dict:
    t = await _get_tourney(tourney_uid)
    if not t or t["status"] != "registration":
        return {"ok": False, "message": "❌ Tournament isn't in registration."}
    parts = await _get_participants(tourney_uid)
    if len(parts) < 2:
        return {"ok": False, "message": "❌ Need at least 2 participants."}

    random.shuffle(parts)
    size = 2 ** math.ceil(math.log2(len(parts)))
    slots = parts + [None] * (size - len(parts))

    match_no = 1
    for i in range(0, size, 2):
        p1, p2 = slots[i], slots[i + 1]
        winner, status = None, "pending"
        if p1 and not p2: winner, status = p1["sts_id"], "bye"
        elif p2 and not p1: winner, status = p2["sts_id"], "bye"
        await _supa_post("tournament_matches", {
            "tourney_uid": tourney_uid, "round": 1, "match_no": match_no,
            "p1_sts_id": p1["sts_id"] if p1 else None, "p2_sts_id": p2["sts_id"] if p2 else None,
            "p1_name": p1["name"] if p1 else None, "p2_name": p2["name"] if p2 else None,
            "winner_sts_id": winner, "status": status, "created_at": _now_utc().isoformat(),
        })
        match_no += 1

    await _supa_patch("tournaments", {"tourney_uid": f"eq.{tourney_uid}"}, {"status": "ongoing", "started_at": _now_utc().isoformat()})
    return {"ok": True, "message": "started"}

def _bracket_lines(matches: list) -> str:
    lines = []
    for m in matches:
        p1 = m.get("p1_name") or m.get("p1_sts_id") or "BYE"
        p2 = m.get("p2_name") or m.get("p2_sts_id") or "BYE"
        if m["status"] in ("verified", "bye"):
            win = m.get("winner_sts_id")
            p1_txt = f"**{p1}** ✅" if win == m.get("p1_sts_id") else p1
            p2_txt = f"**{p2}** ✅" if win == m.get("p2_sts_id") else p2
            lines.append(f"`M{m['match_no']}` {p1_txt} vs {p2_txt}")
        elif m["status"] == "reported":
            lines.append(f"`M{m['match_no']}` {p1} vs {p2} — ⏳ awaiting admin verification")
        else:
            lines.append(f"`M{m['match_no']}` {p1} vs {p2}")
    return "\n".join(lines) or "—"

async def _post_bracket(channel, tourney_uid: str, round_no: int):
    matches = await _get_matches(tourney_uid, round_no)
    embed = discord.Embed(title=f"🏆 Round {round_no} Bracket", description=_bracket_lines(matches), color=0xf39c12)
    embed.set_footer(text=f"{FOOTER} • {tourney_uid} • Report with /tournament report")
    await channel.send(embed=embed)

async def _maybe_advance_round(tourney_uid: str, round_no: int, channel):
    matches = await _get_matches(tourney_uid, round_no)
    if not matches or any(m["status"] not in ("verified", "bye") for m in matches):
        return

    winners = [m["winner_sts_id"] for m in matches]
    winner_names = {m["winner_sts_id"]: (m["p1_name"] if m["winner_sts_id"] == m["p1_sts_id"] else m["p2_name"]) for m in matches}

    if len(winners) == 1:
        t = await _get_tourney(tourney_uid)
        winner_sts = winners[0]
        winner_name = winner_names.get(winner_sts, winner_sts)
        await _supa_patch("tournaments", {"tourney_uid": f"eq.{tourney_uid}"}, {
            "status": "completed", "completed_at": _now_utc().isoformat(),
            "winner_sts_id": winner_sts, "winner_name": winner_name,
        })
        if t.get("reward_points"):
            await _award_points(winner_sts, t["reward_points"], f"Tournament win: {t['title']} ({tourney_uid})")
        if channel:
            embed = discord.Embed(title="🏆 TOURNAMENT COMPLETE", description=f"**Champion: {winner_name}**", color=0x00ff88)
            if t.get("reward_points"):
                embed.add_field(name="Reward", value=f"{t['reward_points']:,} AERO Points credited")
            embed.set_footer(text=f"{FOOTER} • {tourney_uid}")
            await channel.send(embed=embed)
        return

    next_round = round_no + 1
    match_no = 1
    for i in range(0, len(winners), 2):
        w1, w2 = winners[i], winners[i + 1] if i + 1 < len(winners) else None
        winner, status = (w1, "bye") if not w2 else (None, "pending")
        await _supa_post("tournament_matches", {
            "tourney_uid": tourney_uid, "round": next_round, "match_no": match_no,
            "p1_sts_id": w1, "p2_sts_id": w2,
            "p1_name": winner_names.get(w1), "p2_name": winner_names.get(w2) if w2 else None,
            "winner_sts_id": winner, "status": status, "created_at": _now_utc().isoformat(),
        })
        match_no += 1

    if channel:
        await _post_bracket(channel, tourney_uid, next_round)
    await _maybe_advance_round(tourney_uid, next_round, channel)

async def _award_points(sts_id: str, amount: int, reason: str):
    try:
        rows = await _supa_get("share_users", {"sts_id": f"eq.{sts_id}", "select": "aero_points"})
        if not rows:
            return
        new_bal = int(rows[0].get("aero_points") or 0) + amount
        await _supa_patch("share_users", {"sts_id": f"eq.{sts_id}"}, {"aero_points": new_bal})
        await _supa_post("point_transactions", {"sts_id": sts_id, "amount": amount, "reason": reason, "created_at": _now_utc().isoformat()})
    except Exception as e:
        print(f"[TOURNAMENT] award_points failed: {e}")

async def _cmd_tournament_create(ctx, title: str, max_participants: int = 16, reward_points: int = 0,
                                  reg_hours: float = 24, description: str = ""):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)

    tourney_uid = _gen_uid("TOUR")
    reg_end = _now_utc() + timedelta(hours=reg_hours)
    await _supa_post("tournaments", {
        "tourney_uid": tourney_uid, "title": title, "description": description,
        "guild_id": str(ctx.guild.id) if ctx.guild else None, "status": "registration",
        "max_participants": max_participants, "reward_points": reward_points,
        "created_by": str(ctx.author.id), "reg_end_at": reg_end.isoformat(), "created_at": _now_utc().isoformat(),
    })
    t = await _get_tourney(tourney_uid)
    view = _TourneyView(tourney_uid)
    msg = await ctx.send(embed=await _build_tourney_embed(t), view=view)
    await _supa_patch("tournaments", {"tourney_uid": f"eq.{tourney_uid}"}, {"channel_id": str(msg.channel.id), "message_id": str(msg.id)})

async def _cmd_tournament_report(ctx, tourney_uid: str, round_no: int, match_no: int, winner_sts_id: str):
    await ctx.defer(ephemeral=True)
    if not await _gate(ctx): return
    rows = await _supa_get("tournament_matches", {
        "tourney_uid": f"eq.{tourney_uid.strip().upper()}", "round": f"eq.{round_no}",
        "match_no": f"eq.{match_no}", "select": "*"
    })
    if not rows:
        return await ctx.send("❌ Match not found.", ephemeral=True)
    m = rows[0]
    winner_sts_id = winner_sts_id.strip().upper()
    if winner_sts_id not in (m.get("p1_sts_id"), m.get("p2_sts_id")):
        return await ctx.send("❌ That STS ID isn't in this match.", ephemeral=True)
    await _supa_patch("tournament_matches", {"id": f"eq.{m['id']}"}, {"winner_sts_id": winner_sts_id, "status": "reported", "reported_by": str(ctx.author.id)})
    await ctx.send("✅ Result reported — awaiting admin verification with `/tournament verify`.", ephemeral=True)

async def _cmd_tournament_verify(ctx, tourney_uid: str, round_no: int, match_no: int):
    await ctx.defer()
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    tourney_uid = tourney_uid.strip().upper()
    rows = await _supa_get("tournament_matches", {"tourney_uid": f"eq.{tourney_uid}", "round": f"eq.{round_no}", "match_no": f"eq.{match_no}", "select": "*"})
    if not rows or rows[0]["status"] != "reported":
        return await ctx.send("❌ No reported result to verify for that match.", ephemeral=True)
    m = rows[0]
    await _supa_patch("tournament_matches", {"id": f"eq.{m['id']}"}, {"status": "verified", "verified_at": _now_utc().isoformat()})
    await ctx.send(f"✅ Match `M{match_no}` verified.")
    await _maybe_advance_round(tourney_uid, round_no, ctx.channel)

async def _cmd_tournament_bracket(ctx, tourney_uid: str, round_no: int = None):
    await ctx.defer()
    tourney_uid = tourney_uid.strip().upper()
    if round_no is None:
        all_matches = await _get_matches(tourney_uid)
        round_no = max((m["round"] for m in all_matches), default=1)
    await _post_bracket(ctx.channel, tourney_uid, round_no)

async def _cmd_tournament_view(ctx, tourney_uid: str):
    await ctx.defer()
    t = await _get_tourney(tourney_uid.strip().upper())
    if not t:
        return await ctx.send("❌ Tournament not found.")
    view = _TourneyView(t["tourney_uid"]) if t["status"] == "registration" else None
    await ctx.send(embed=await _build_tourney_embed(t), view=view)

async def _cmd_tournament_list(ctx, status: str = "registration"):
    await ctx.defer()
    rows = await _supa_get("tournaments", {
        "guild_id": f"eq.{ctx.guild.id}" if ctx.guild else "is.null",
        "status": f"eq.{status}", "select": "tourney_uid,title,status", "order": "created_at.desc", "limit": "15"
    })
    if not rows:
        return await ctx.send(f"📭 No `{status}` tournaments.")
    lines = [f"`{r['tourney_uid']}` — **{r['title']}**" for r in rows]
    embed = discord.Embed(title=f"🏆 Tournaments — {status.upper()}", description="\n".join(lines), color=0xf39c12)
    embed.set_footer(text=FOOTER)
    await ctx.send(embed=embed)

async def _reattach_tourney_views():
    await _bot.wait_until_ready()
    try:
        open_t = await _supa_get("tournaments", {"status": "eq.registration", "select": "tourney_uid"})
        for t in open_t or []:
            _bot.add_view(_TourneyView(t["tourney_uid"]))
        print(f"[TOURNAMENT] Reattached {len(open_t or [])} registration view(s)")
    except Exception as e:
        print(f"[TOURNAMENT] reattach error: {e}")


# ═══════════════════════════════════════════════════════════
#  SECTION 5 — CASE / DISCIPLINARY
#  Never auto-punishes. A decision vote only records what
#  members decided — enforcement stays a manual admin action.
# ═══════════════════════════════════════════════════════════

CASE_STATUS_COLORS = {
    "open": 0xf39c12, "under_review": 0x00d4ff, "awaiting_decision": 0xe67e22,
    "resolved": 0x00ff88, "dismissed": 0x747d8c, "archived": 0x2f3542,
}

async def _get_case(case_uid: str) -> dict | None:
    rows = await _supa_get("cases", {"case_uid": f"eq.{case_uid}", "select": "*"})
    return rows[0] if rows else None

async def _case_log(case_uid, actor, action, note=None):
    await _supa_post("case_history", {"case_uid": case_uid, "actor_discord_id": str(actor), "action": action, "note": note, "created_at": _now_utc().isoformat()})

async def _build_case_embed(c: dict) -> discord.Embed:
    hist = await _supa_get("case_history", {"case_uid": f"eq.{c['case_uid']}", "select": "*", "order": "created_at.desc", "limit": "6"})
    embed = discord.Embed(title=f"⚖️ Case {c['case_uid']}", description=c["reason"], color=CASE_STATUS_COLORS.get(c["status"], 0x2b2d31))
    embed.add_field(name="Subject", value=f"<@{c['subject_discord_id']}>", inline=True)
    embed.add_field(name="Reporter", value=f"<@{c['reporter_discord_id']}>", inline=True)
    embed.add_field(name="Status", value=c["status"].replace("_", " ").upper(), inline=True)
    if c.get("assigned_admin"):
        embed.add_field(name="Assigned Admin", value=f"<@{c['assigned_admin']}>", inline=True)
    if c.get("evidence"):
        embed.add_field(name="📎 Evidence", value=c["evidence"][:1000], inline=False)
    if c.get("decision"):
        embed.add_field(name="⚖️ Decision", value=f"**{c['decision']}**" + (f"\n{c.get('decision_note') or ''}" if c.get("decision_note") else ""), inline=False)
    if c.get("vote_uid"):
        embed.add_field(name="Decision Vote", value=f"`{c['vote_uid']}`", inline=True)
    if hist:
        lines = [f"`{h['created_at'][11:16]}` {h['action']}" + (f" — {h['note']}" if h.get("note") else "") for h in hist]
        embed.add_field(name="🕓 History", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"{FOOTER} • Created {c['created_at'][:10]} • {_ts()}")
    return embed

class _CaseView(discord.ui.View):
    def __init__(self, case_uid: str):
        super().__init__(timeout=None)
        self.case_uid = case_uid

    async def _refresh(self, interaction):
        c = await _get_case(self.case_uid)
        view = self if c["status"] not in ("resolved", "dismissed", "archived") else None
        await interaction.message.edit(embed=await _build_case_embed(c), view=view)

    @discord.ui.button(label="🔍 Under Review", style=discord.ButtonStyle.primary, custom_id="aerion_case_review")
    async def review(self, interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        await _supa_patch("cases", {"case_uid": f"eq.{self.case_uid}"}, {"status": "under_review", "assigned_admin": str(interaction.user.id)})
        await _case_log(self.case_uid, interaction.user.id, "status_change", "Moved to Under Review")
        await self._refresh(interaction)

    @discord.ui.button(label="🗳️ Decision Vote", style=discord.ButtonStyle.secondary, custom_id="aerion_case_vote")
    async def decision_vote(self, interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        c = await _get_case(self.case_uid)
        if c["status"] not in ("open", "under_review"):
            return await interaction.response.send_message("❌ Case must be Open or Under Review to start a decision vote.", ephemeral=True)
        await interaction.response.defer()
        vote = await create_vote(title=f"Case Decision: {self.case_uid}",
                                  description=f"Subject: <@{c['subject_discord_id']}>\nReason: {c['reason']}",
                                  options=["Warning", "Probation", "Removal", "Dismiss Case"], duration_hours=48,
                                  created_by=str(interaction.user.id), channel=interaction.channel,
                                  guild_id=interaction.guild_id, anonymous=True,
                                  linked_type="case_decision", linked_uid=self.case_uid)
        await _supa_patch("cases", {"case_uid": f"eq.{self.case_uid}"}, {"status": "awaiting_decision", "vote_uid": vote["vote_uid"]})
        await _case_log(self.case_uid, interaction.user.id, "decision_vote_started", vote["vote_uid"])
        await self._refresh(interaction)

    @discord.ui.button(label="❌ Dismiss", style=discord.ButtonStyle.danger, custom_id="aerion_case_dismiss")
    async def dismiss(self, interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        await _supa_patch("cases", {"case_uid": f"eq.{self.case_uid}"}, {"status": "dismissed", "decision": "Dismissed by admin", "resolved_at": _now_utc().isoformat()})
        await _case_log(self.case_uid, interaction.user.id, "dismissed")
        await self._refresh(interaction)

    @discord.ui.button(label="🗄️ Archive", style=discord.ButtonStyle.secondary, custom_id="aerion_case_archive")
    async def archive(self, interaction, button):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        await interaction.response.defer()
        await _supa_patch("cases", {"case_uid": f"eq.{self.case_uid}"}, {"status": "archived"})
        await _case_log(self.case_uid, interaction.user.id, "archived")
        await self._refresh(interaction)

async def _on_case_vote_closed(vote: dict):
    case_uid = vote["linked_uid"]
    c = await _get_case(case_uid)
    if not c:
        return

    if vote["status"] == "cancelled":
        note = "Decision vote cancelled."
        await _supa_patch("cases", {"case_uid": f"eq.{case_uid}"}, {"status": "under_review"})
    elif vote.get("is_tie"):
        note = "Decision vote tied — needs admin follow-up."
        await _supa_patch("cases", {"case_uid": f"eq.{case_uid}"}, {"status": "under_review"})
    else:
        decision = vote["winner_option"]
        final_status = "dismissed" if decision == "Dismiss Case" else "resolved"
        await _supa_patch("cases", {"case_uid": f"eq.{case_uid}"}, {
            "status": final_status, "decision": decision,
            "decision_note": "Decided by member vote — enforcement (if any) still requires manual admin action.",
            "resolved_at": _now_utc().isoformat(),
        })
        note = f"Vote result: **{decision}** ({vote['result']})"

    await _case_log(case_uid, "system", "decision_vote_closed", note)

    try:
        if vote.get("channel_id"):
            channel = _bot.get_channel(int(vote["channel_id"]))
            if channel:
                fresh = await _get_case(case_uid)
                await channel.send(content="⚖️ Case decision vote has ended.", embed=await _build_case_embed(fresh))
    except Exception as e:
        print(f"[CASE] announce failed: {e}")

async def _cmd_case_open(ctx, member: discord.Member, reason: str, evidence: str = ""):
    await ctx.defer()
    if not await _gate(ctx): return
    if not _is_admin(ctx):
        return await ctx.send("❌ Only authorised roles can open cases.", ephemeral=True)

    case_uid = _gen_uid("CASE")
    await _supa_post("cases", {
        "case_uid": case_uid, "subject_discord_id": str(member.id), "reporter_discord_id": str(ctx.author.id),
        "guild_id": str(ctx.guild.id) if ctx.guild else None, "reason": reason, "evidence": evidence,
        "status": "open", "created_at": _now_utc().isoformat(),
    })
    await _case_log(case_uid, ctx.author.id, "opened", reason)
    c = await _get_case(case_uid)
    view = _CaseView(case_uid)
    msg = await ctx.send(embed=await _build_case_embed(c), view=view)
    await _supa_patch("cases", {"case_uid": f"eq.{case_uid}"}, {"channel_id": str(msg.channel.id), "message_id": str(msg.id)})

async def _cmd_case_note(ctx, case_uid: str, note: str):
    await ctx.defer(ephemeral=True)
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    c = await _get_case(case_uid.strip().upper())
    if not c:
        return await ctx.send("❌ Case not found.", ephemeral=True)
    await _case_log(c["case_uid"], ctx.author.id, "note", note)
    await ctx.send("✅ Note added.", ephemeral=True)

async def _cmd_case_evidence(ctx, case_uid: str, evidence: str):
    await ctx.defer(ephemeral=True)
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    c = await _get_case(case_uid.strip().upper())
    if not c:
        return await ctx.send("❌ Case not found.", ephemeral=True)
    merged = (c.get("evidence") or "") + f"\n— {evidence}"
    await _supa_patch("cases", {"case_uid": f"eq.{c['case_uid']}"}, {"evidence": merged.strip()})
    await _case_log(c["case_uid"], ctx.author.id, "evidence_added", evidence)
    await ctx.send("✅ Evidence added.", ephemeral=True)

async def _cmd_case_view(ctx, case_uid: str):
    await ctx.defer()
    c = await _get_case(case_uid.strip().upper())
    if not c:
        return await ctx.send("❌ Case not found.")
    view = _CaseView(c["case_uid"]) if c["status"] not in ("resolved", "dismissed", "archived") else None
    await ctx.send(embed=await _build_case_embed(c), view=view)

async def _cmd_case_list(ctx, status: str = "open"):
    await ctx.defer()
    if not _is_admin(ctx):
        return await ctx.send("❌ Admin only.", ephemeral=True)
    rows = await _supa_get("cases", {
        "guild_id": f"eq.{ctx.guild.id}" if ctx.guild else "is.null",
        "status": f"eq.{status}", "select": "case_uid,reason,subject_discord_id", "order": "created_at.desc", "limit": "15"
    })
    if not rows:
        return await ctx.send(f"📭 No `{status}` cases.")
    lines = [f"`{r['case_uid']}` — <@{r['subject_discord_id']}> — {r['reason'][:60]}" for r in rows]
    embed = discord.Embed(title=f"⚖️ Cases — {status.upper()}", description="\n".join(lines), color=0x00d4ff)
    embed.set_footer(text=FOOTER)
    await ctx.send(embed=embed, ephemeral=True)

async def _reattach_case_views():
    await _bot.wait_until_ready()
    try:
        open_c = await _supa_get("cases", {"status": f"in.(open,under_review,awaiting_decision)", "select": "case_uid"})
        for c in open_c or []:
            _bot.add_view(_CaseView(c["case_uid"]))
        print(f"[CASE] Reattached {len(open_c or [])} case view(s)")
    except Exception as e:
        print(f"[CASE] reattach error: {e}")


# ═══════════════════════════════════════════════════════════
#  REGISTER — one call wires up all 5 sections
# ═══════════════════════════════════════════════════════════
def register_governance_suite(bot_instance, supa_get, supa_post, supa_patch, check_member_fn=None):
    global _bot, _supa_get, _supa_post, _supa_patch, _check_member
    _bot, _supa_get, _supa_post, _supa_patch, _check_member = \
        bot_instance, supa_get, supa_post, supa_patch, check_member_fn

    # wire cross-section hooks (proposal / treasury_spend / case_decision)
    _close_hooks["proposal"] = _on_proposal_vote_closed
    _close_hooks["treasury_spend"] = _on_treasury_vote_closed
    _close_hooks["case_decision"] = _on_case_vote_closed

    # background loops
    bot_instance.loop.create_task(_auto_close_loop())
    bot_instance.loop.create_task(_reattach_open_views())
    bot_instance.loop.create_task(_reattach_tourney_views())
    bot_instance.loop.create_task(_reattach_case_views())

    # ── /voterid + /vote group ──
    @bot_instance.hybrid_command(name="voterid", description="Get your permanent AERION Voting ID (one-time)")
    async def voterid(ctx):
        await _cmd_voterid(ctx)

    @bot_instance.hybrid_group(name="vote", description="AERION voting system")
    async def vote(ctx): pass

    @vote.command(name="create", description="[Admin] Create a new vote")
    @app_commands.describe(title="Vote title", duration_hours="How long voting stays open (hours)",
                            options="Comma-separated options (default: Yes,No,Abstain)",
                            description="Optional longer description", anonymous="Hide who voted for what (default True)",
                            eligible_role="Restrict voting to this role (optional)")
    async def vote_create(ctx, title: str, duration_hours: float, options: str = "Yes,No,Abstain",
                           description: str = "", anonymous: bool = True, eligible_role: discord.Role = None):
        await _cmd_vote_create(ctx, title, duration_hours, options, description, anonymous, eligible_role)

    @vote.command(name="results", description="View live or final results for a vote")
    @app_commands.describe(vote_uid="Vote ID e.g. VOTE-AB12CD34")
    async def vote_results(ctx, vote_uid: str):
        await _cmd_vote_results(ctx, vote_uid)

    @vote.command(name="close", description="[Admin] Force-close a vote now and announce results")
    @app_commands.describe(vote_uid="Vote ID")
    async def vote_close(ctx, vote_uid: str):
        await _cmd_vote_close(ctx, vote_uid)

    @vote.command(name="cancel", description="[Admin] Cancel a vote — no results announced")
    @app_commands.describe(vote_uid="Vote ID")
    async def vote_cancel(ctx, vote_uid: str):
        await _cmd_vote_cancel(ctx, vote_uid)

    @vote.command(name="list", description="List votes by status")
    @app_commands.describe(status="open, closed, or cancelled")
    async def vote_list(ctx, status: str = "open"):
        await _cmd_vote_list(ctx, status)

    # ── /proposal group ──
    @bot_instance.hybrid_group(name="proposal", description="AERION governance proposals")
    async def proposal(ctx): pass

    @proposal.command(name="create", description="[Admin] Open a new proposal for discussion")
    @app_commands.describe(title="Proposal title", description="Full description")
    async def proposal_create(ctx, title: str, description: str = ""):
        await _cmd_proposal_create(ctx, title, description)

    @proposal.command(name="view", description="View a proposal's current panel")
    @app_commands.describe(proposal_uid="Proposal ID e.g. PROP-AB12CD34")
    async def proposal_view(ctx, proposal_uid: str):
        await _cmd_proposal_view(ctx, proposal_uid)

    @proposal.command(name="list", description="List proposals by status")
    @app_commands.describe(status="draft, discussion, voting, passed, rejected, cancelled, archived")
    async def proposal_list(ctx, status: str = "discussion"):
        await _cmd_proposal_list(ctx, status)

    # ── /treasury group ──
    @bot_instance.hybrid_group(name="treasury", description="AERO Treasury (virtual points, no real-money value)")
    async def treasury(ctx): pass

    @treasury.command(name="dashboard", description="View treasury balance and recent transactions")
    async def treasury_dashboard(ctx):
        await _cmd_treasury_dashboard(ctx)

    @treasury.command(name="income", description="[Admin] Record treasury income")
    @app_commands.describe(amount="AERO Points amount", reason="Reason")
    async def treasury_income(ctx, amount: float, reason: str):
        await _cmd_treasury_income(ctx, amount, reason)

    @treasury.command(name="spend", description=f"[Admin] Direct spend (only under {TREASURY_VOTE_THRESHOLD} pts)")
    @app_commands.describe(amount="AERO Points amount", reason="Reason")
    async def treasury_spend(ctx, amount: float, reason: str):
        await _cmd_treasury_spend(ctx, amount, reason)

    @treasury.command(name="request", description=f"[Admin] Request a large spend ({TREASURY_VOTE_THRESHOLD}+ pts) — puts it to a vote")
    @app_commands.describe(amount="AERO Points amount", reason="Reason", duration_hours="Voting duration in hours")
    async def treasury_request(ctx, amount: float, reason: str, duration_hours: float = 24):
        await _cmd_treasury_request(ctx, amount, reason, duration_hours)

    # ── /tournament group ──
    @bot_instance.hybrid_group(name="tournament", description="AERION tournament system")
    async def tournament(ctx): pass

    @tournament.command(name="create", description="[Admin] Create a new tournament")
    @app_commands.describe(title="Title", max_participants="Cap (default 16)", reward_points="AERO Points reward for winner",
                            reg_hours="Registration window in hours", description="Description")
    async def tournament_create(ctx, title: str, max_participants: int = 16, reward_points: int = 0,
                                 reg_hours: float = 24, description: str = ""):
        await _cmd_tournament_create(ctx, title, max_participants, reward_points, reg_hours, description)

    @tournament.command(name="report", description="Report your match result (needs admin verification)")
    @app_commands.describe(tourney_uid="Tournament ID", round_no="Round number", match_no="Match number", winner_sts_id="Winner's STS ID")
    async def tournament_report(ctx, tourney_uid: str, round_no: int, match_no: int, winner_sts_id: str):
        await _cmd_tournament_report(ctx, tourney_uid, round_no, match_no, winner_sts_id)

    @tournament.command(name="verify", description="[Admin] Verify a reported match result and auto-advance the bracket")
    @app_commands.describe(tourney_uid="Tournament ID", round_no="Round number", match_no="Match number")
    async def tournament_verify(ctx, tourney_uid: str, round_no: int, match_no: int):
        await _cmd_tournament_verify(ctx, tourney_uid, round_no, match_no)

    @tournament.command(name="bracket", description="View the bracket for a round")
    @app_commands.describe(tourney_uid="Tournament ID", round_no="Round number (default: latest)")
    async def tournament_bracket(ctx, tourney_uid: str, round_no: int = None):
        await _cmd_tournament_bracket(ctx, tourney_uid, round_no)

    @tournament.command(name="view", description="View a tournament's panel")
    @app_commands.describe(tourney_uid="Tournament ID")
    async def tournament_view(ctx, tourney_uid: str):
        await _cmd_tournament_view(ctx, tourney_uid)

    @tournament.command(name="list", description="List tournaments by status")
    @app_commands.describe(status="registration, ongoing, completed, cancelled")
    async def tournament_list(ctx, status: str = "registration"):
        await _cmd_tournament_list(ctx, status)

    # ── /case group ──
    @bot_instance.hybrid_group(name="case", description="AERION case / disciplinary management")
    async def case(ctx): pass

    @case.command(name="open", description="[Admin] Open a new case")
    @app_commands.describe(member="Subject of the case", reason="Reason", evidence="Optional evidence/notes")
    async def case_open(ctx, member: discord.Member, reason: str, evidence: str = ""):
        await _cmd_case_open(ctx, member, reason, evidence)

    @case.command(name="note", description="[Admin] Add a note to a case")
    @app_commands.describe(case_uid="Case ID e.g. CASE-AB12CD34", note="Note text")
    async def case_note(ctx, case_uid: str, note: str):
        await _cmd_case_note(ctx, case_uid, note)

    @case.command(name="evidence", description="[Admin] Attach evidence to a case")
    @app_commands.describe(case_uid="Case ID", evidence="Evidence text/link")
    async def case_evidence(ctx, case_uid: str, evidence: str):
        await _cmd_case_evidence(ctx, case_uid, evidence)

    @case.command(name="view", description="View a case panel")
    @app_commands.describe(case_uid="Case ID")
    async def case_view(ctx, case_uid: str):
        await _cmd_case_view(ctx, case_uid)

    @case.command(name="list", description="[Admin] List cases by status")
    @app_commands.describe(status="open, under_review, awaiting_decision, resolved, dismissed, archived")
    async def case_list(ctx, status: str = "open"):
        await _cmd_case_list(ctx, status)

    print("[GOVERNANCE SUITE] Ready: /voterid /vote /proposal /treasury /tournament /case")
