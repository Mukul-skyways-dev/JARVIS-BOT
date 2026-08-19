# =========================================================
# JARVIS SHARE MODULE  — Portal-synced via Supabase
# Paste this entire block into bot1__9_.py just before
# the "ON READY" section.
#
# Tables used (already exist in your portal's Supabase):
#   share_users   — sts_id, discord_id, name, airline,
#                   alliance, aero_points
#   share_entries — id, sts_id, alliance, value, created_at
#
# Requires: SUPABASE_URL + SUPABASE_KEY env vars (already set)
# Requires: supabase_get / supabase_patch / supabase_post
#           helpers (already in your bot)
# =========================================================

import pytz, io, asyncio, time
from datetime import datetime, timezone, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

IST = pytz.timezone("Asia/Kolkata")

# ── helpers ───────────────────────────────────────────────
def _now_ist():
    return datetime.now(IST)

def _ist_str(iso_str):
    """Convert ISO UTC string → readable IST string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        ist = dt.astimezone(IST)
        return ist.strftime("%d %b %Y  %I:%M %p IST")
    except:
        return iso_str

def _today_ist():
    return _now_ist().strftime("%Y-%m-%d")

def _money(v):
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    return f"${v:,.0f}"

def _parse_money(s):
    """'5.2B' / '500M' / '12345' → float"""
    try:
        s = str(s).strip().upper().replace(",","")
        if s.endswith("B"): return float(s[:-1]) * 1e9
        if s.endswith("M"): return float(s[:-1]) * 1e6
        return float(s)
    except:
        return None

# ── fetch linked STS for a Discord user ───────────────────
async def _get_sts(discord_id: str):
    """Returns the STS ID linked to this Discord user, or None."""
    try:
        rows = await supabase_get(
            "share_users",
            {"discord_id": f"eq.{discord_id}", "select": "sts_id,name,airline,alliance,aero_points"}
        )
        return rows[0] if rows else None
    except Exception as e:
        print(f"[SHARE] _get_sts error: {e}")
        return None

# ── graph helper (dark background) ───────────────────────
_SHARE_BG  = "#0a0e1a"
_SHARE_FG  = "#1e2540"
_SHARE_ACC = "#00d4ff"
_SHARE_GRN = "#00ff88"
_SHARE_RED = "#ff4757"

def _dark_fig(w=10, h=5):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(_SHARE_BG)
    ax.set_facecolor(_SHARE_FG)
    ax.tick_params(colors="#8e9ac0")
    ax.xaxis.label.set_color("#8e9ac0")
    ax.yaxis.label.set_color("#8e9ac0")
    ax.title.set_color(_SHARE_ACC)
    for sp in ax.spines.values():
        sp.set_color("#2a3450")
    ax.grid(alpha=0.12, linestyle=":", color="#3a4460")
    return fig, ax

def _save_buf(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120,
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf

# ── rank label ────────────────────────────────────────────
def _rank_label(consistency_pct):
    if consistency_pct >= 90: return "🏆 Legend"
    if consistency_pct >= 75: return "💎 Diamond"
    if consistency_pct >= 60: return "🥇 Gold"
    if consistency_pct >= 40: return "🥈 Silver"
    return "🥉 Bronze"

# =========================================================
# !submitshare  — submit from Discord → portal Supabase
# =========================================================
@bot.hybrid_command(
    name="submitshare",
    description="Submit your share value to the AERO portal (same as portal entry)"
)
@app_commands.describe(
    value="Share value — e.g. 5.2B or 500M or 1234567",
    alliance="Your alliance name (leave blank to use your default)"
)
async def submitshare(ctx, value: str, alliance: str = None):
    await ctx.defer(ephemeral=True)

    user = await _get_sts(str(ctx.author.id))
    if not user:
        return await ctx.send(
            "❌ Your Discord isn't linked to the portal yet.\n"
            "→ Go to the AERO portal → generate a link code → use `/link <code>` here.",
            ephemeral=True
        )

    sts_id    = user["sts_id"]
    val_float = _parse_money(value)
    if val_float is None or val_float <= 0:
        return await ctx.send(
            "❌ Invalid value. Use formats like `5.2B`, `500M`, or `1234567`",
            ephemeral=True
        )

    # Use provided alliance or fall back to profile default
    alliance_name = (alliance or user.get("alliance") or "").strip()
    if not alliance_name:
        return await ctx.send(
            "❌ No alliance set. Either provide one: `!submitshare 5B MyAlliance`\n"
            "or set your alliance on the portal first.",
            ephemeral=True
        )

    # Check duplicate (same sts + alliance + today IST)
    today = _today_ist()
    try:
        existing = await supabase_get("share_entries", {
            "sts_id":   f"eq.{sts_id}",
            "alliance": f"eq.{alliance_name}",
            "select":   "id,created_at",
        })
        # Filter to today IST
        today_entries = [
            e for e in existing
            if datetime.fromisoformat(
                e["created_at"].replace("Z", "+00:00")
            ).astimezone(IST).strftime("%Y-%m-%d") == today
        ]
    except Exception as e:
        print(f"[SHARE] duplicate check error: {e}")
        today_entries = []

    if today_entries:
        return await ctx.send(
            f"⚠️ You already submitted a share value today for **{alliance_name}**.\n"
            "You can edit it on the portal within 3 hours of submitting.",
            ephemeral=True
        )

    # Insert entry
    try:
        await supabase_post("share_entries", {
            "sts_id":     sts_id,
            "alliance":   alliance_name,
            "value":      val_float,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        print(f"[SHARE] insert error: {e}")
        return await ctx.send(f"❌ Submission failed: {e}", ephemeral=True)

    embed = discord.Embed(
        title="✅ Share Entry Submitted",
        description=f"Your value has been posted to the AERO portal.",
        color=0x00ff88
    )
    embed.add_field(name="STS ID",    value=f"`{sts_id}`",        inline=True)
    embed.add_field(name="Value",     value=_money(val_float),    inline=True)
    embed.add_field(name="Alliance",  value=alliance_name,        inline=True)
    embed.add_field(name="Date",      value=today,                inline=True)
    embed.set_footer(text="JARVIS • AERO Portal Sync")
    await ctx.send(embed=embed, ephemeral=True)

    # Public confirmation in channel
    pub = discord.Embed(
        description=f"📤 **{user.get('name') or ctx.author.display_name}** submitted share value → {_money(val_float)}",
        color=0x00d4ff
    )
    pub.set_footer(text=f"STS: {sts_id} • {alliance_name}")
    await ctx.channel.send(embed=pub)

# =========================================================
# !myshares  — my own share history from portal
# =========================================================
@bot.hybrid_command(
    name="myshares",
    description="View your share entry history from the AERO portal"
)
async def myshares(ctx):
    await ctx.defer()

    user = await _get_sts(str(ctx.author.id))
    if not user:
        return await ctx.send(
            "❌ Not linked. Use `/link <code>` after generating a code on the portal."
        )

    sts_id = user["sts_id"]

    try:
        entries = await supabase_get("share_entries", {
            "sts_id":  f"eq.{sts_id}",
            "select":  "*",
            "order":   "created_at.desc",
            "limit":   "30",
        })
    except Exception as e:
        return await ctx.send(f"❌ Could not fetch entries: {e}")

    if not entries:
        return await ctx.send("📭 No share entries found on the portal yet.")

    # Stats
    values = [e["value"] for e in entries]
    avg_v  = sum(values) / len(values)
    max_v  = max(values)
    min_v  = min(values)

    # Unique days submitted
    days = set(
        datetime.fromisoformat(e["created_at"].replace("Z","+00:00"))
        .astimezone(IST).strftime("%Y-%m-%d")
        for e in entries
    )
    # Streak: consecutive days up to today
    streak = 0
    check  = _now_ist().date()
    dates  = sorted(days, reverse=True)
    for d in dates:
        dd = datetime.strptime(d, "%Y-%m-%d").date()
        if dd == check:
            streak += 1
            check = check - timedelta(days=1)
        else:
            break

    embed = discord.Embed(
        title=f"📊 My Share History — {user.get('name') or sts_id}",
        color=0x00d4ff
    )
    embed.add_field(name="STS ID",     value=f"`{sts_id}`",          inline=True)
    embed.add_field(name="Alliance",   value=user.get("alliance","—"),inline=True)
    embed.add_field(name="AERO Pts",   value=f"{user.get('aero_points',0):,}", inline=True)
    embed.add_field(name="Entries",    value=str(len(entries)),       inline=True)
    embed.add_field(name="Days Active",value=str(len(days)),          inline=True)
    embed.add_field(name="Streak",     value=f"🔥 {streak} day(s)",   inline=True)
    embed.add_field(name="Average",    value=_money(avg_v),           inline=True)
    embed.add_field(name="Highest",    value=_money(max_v),           inline=True)
    embed.add_field(name="Lowest",     value=_money(min_v),           inline=True)

    # Last 5 entries
    recent = entries[:5]
    hist_text = "\n".join(
        f"`{_ist_str(e['created_at'])}` → **{_money(e['value'])}** ({e.get('alliance','')})"
        for e in recent
    )
    embed.add_field(name="Recent Entries", value=hist_text or "—", inline=False)
    embed.set_footer(text="JARVIS • AERO Portal Sync")
    embed.set_thumbnail(url=ctx.author.display_avatar.url)

    await ctx.send(embed=embed, view=_MySharesView(entries, user))

class _MySharesView(discord.ui.View):
    def __init__(self, entries, user):
        super().__init__(timeout=180)
        self.entries = entries
        self.user    = user

    @discord.ui.button(label="📈 Graph", style=discord.ButtonStyle.primary)
    async def graph_btn(self, interaction, button):
        entries = list(reversed(self.entries))  # oldest first
        dates  = [
            datetime.fromisoformat(e["created_at"].replace("Z","+00:00"))
            .astimezone(IST).strftime("%d %b")
            for e in entries
        ]
        values = [e["value"] for e in entries]
        avg_v  = sum(values) / len(values)

        fig, ax = _dark_fig(11, 5)
        ax.plot(dates, values, color=_SHARE_ACC, linewidth=2.5,
                marker="o", markersize=5, zorder=3)
        ax.axhline(avg_v, color="#8e9ac0", linestyle="--",
                   linewidth=1, alpha=0.6, label=f"Avg {_money(avg_v)}")
        ax.fill_between(range(len(values)), values, alpha=0.08, color=_SHARE_ACC)
        ax.set_title(f"Share History — {self.user.get('name') or self.user['sts_id']}")
        ax.set_xlabel("Date")
        ax.set_ylabel("Value ($)")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: _money(x)))
        plt.xticks(rotation=35, color="#8e9ac0", fontsize=8)
        ax.legend(facecolor=_SHARE_FG, labelcolor="#8e9ac0")
        buf = _save_buf(fig)

        e = discord.Embed(title="📈 Share Value Graph", color=0x00d4ff)
        e.set_image(url="attachment://share_graph.png")
        e.set_footer(text="JARVIS • AERO Portal Sync")
        await interaction.response.send_message(
            embed=e, file=discord.File(buf, "share_graph.png"), ephemeral=True)

# =========================================================
# !shareboard  — alliance leaderboard from portal data
# =========================================================
@bot.hybrid_command(
    name="shareboard",
    description="AERO portal share leaderboard (all players, latest entry)"
)
@app_commands.describe(alliance="Filter by alliance name (optional)")
async def shareboard(ctx, alliance: str = None):
    await ctx.defer()
    try:
        entries = await supabase_get("share_entries", {
            "select": "*",
            "order":  "created_at.desc",
        })
        users = await supabase_get("share_users", {
            "select": "sts_id,name,airline,alliance,aero_points",
        })
    except Exception as e:
        return await ctx.send(f"❌ Could not fetch data: {e}")

    if not entries:
        return await ctx.send("📭 No entries on the portal yet.")

    # Build user lookup
    user_map = {u["sts_id"]: u for u in users}

    # Latest entry per player
    seen = {}
    for e in entries:
        sid = e["sts_id"]
        if sid not in seen:
            seen[sid] = e

    # Filter by alliance if provided
    if alliance:
        seen = {
            sid: e for sid, e in seen.items()
            if (e.get("alliance") or "").lower() == alliance.lower()
        }
        if not seen:
            return await ctx.send(f"❌ No entries found for alliance **{alliance}**")

    # Sort by value desc
    board = sorted(seen.values(), key=lambda e: e["value"], reverse=True)

    medals = ["🥇","🥈","🥉"]
    text   = ""
    for i, e in enumerate(board[:15], 1):
        sid  = e["sts_id"]
        u    = user_map.get(sid, {})
        name = u.get("name") or sid
        pts  = u.get("aero_points", 0)
        med  = medals[i-1] if i <= 3 else f"`#{i}`"
        text += (f"{med} **{name}** (`{sid}`)\n"
                 f"　{_money(e['value'])} • {e.get('alliance','?')} • {pts:,} pts\n\n")

    title = f"🏆 Share Leaderboard"
    if alliance: title += f" — {alliance}"

    embed = discord.Embed(title=title, description=text, color=0x00d4ff)
    embed.set_footer(
        text=f"Data from AERO Portal • {len(board)} players • JARVIS")
    await ctx.send(embed=embed,
                   view=_ShareBoardView(entries, users, board, alliance))

class _ShareBoardView(discord.ui.View):
    def __init__(self, entries, users, board, alliance):
        super().__init__(timeout=180)
        self.entries  = entries
        self.user_map = {u["sts_id"]: u for u in users}
        self.board    = board
        self.alliance = alliance

    @discord.ui.button(label="📊 Bar Chart", style=discord.ButtonStyle.primary)
    async def bar_btn(self, interaction, button):
        top   = self.board[:10]
        names = [(self.user_map.get(e["sts_id"],{}).get("name") or e["sts_id"])[:10]
                 for e in top]
        vals  = [e["value"] for e in top]

        fig, ax = _dark_fig(10, 5)
        bars = ax.bar(names, vals, color=_SHARE_ACC, alpha=0.85)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height(), _money(v),
                    ha="center", va="bottom",
                    color="#e0e8ff", fontsize=8)
        ax.set_title("Top 10 Share Values")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x,_: _money(x)))
        plt.xticks(rotation=35, color="#8e9ac0", fontsize=8)
        buf = _save_buf(fig)

        e = discord.Embed(title="📊 Share Bar Chart", color=0x00d4ff)
        e.set_image(url="attachment://share_bar.png")
        await interaction.response.send_message(
            embed=e, file=discord.File(buf,"share_bar.png"), ephemeral=True)

    @discord.ui.button(label="📈 Growth Lines", style=discord.ButtonStyle.secondary)
    async def growth_btn(self, interaction, button):
        top5 = self.board[:5]
        fig, ax = _dark_fig(11, 5)
        colors = [_SHARE_ACC,"#a855f7","#ff6b6b","#ffa502","#00ff88"]
        for idx, e in enumerate(top5):
            sid   = e["sts_id"]
            name  = (self.user_map.get(sid,{}).get("name") or sid)[:12]
            hist  = sorted(
                [x for x in self.entries if x["sts_id"]==sid],
                key=lambda x: x["created_at"]
            )
            if len(hist) < 2: continue
            dates = [datetime.fromisoformat(x["created_at"].replace("Z","+00:00"))
                     .astimezone(IST).strftime("%d %b") for x in hist]
            vals  = [x["value"] for x in hist]
            ax.plot(dates, vals, label=name, color=colors[idx],
                    linewidth=2, marker="o", markersize=4)
        ax.set_title("Top 5 Share Growth")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x,_: _money(x)))
        plt.xticks(rotation=35, color="#8e9ac0", fontsize=8)
        ax.legend(facecolor=_SHARE_FG, labelcolor="#8e9ac0", fontsize=8)
        buf = _save_buf(fig)

        e = discord.Embed(title="📈 Top 5 Growth", color=0x00d4ff)
        e.set_image(url="attachment://share_growth.png")
        await interaction.response.send_message(
            embed=e, file=discord.File(buf,"share_growth.png"), ephemeral=True)

# =========================================================
# !shareprofile  — detailed profile of any player
# =========================================================
@bot.hybrid_command(
    name="shareprofile",
    description="Detailed share profile of a portal player"
)
@app_commands.describe(sts_id="STS ID of the player (or leave blank for yourself)")
async def shareprofile(ctx, sts_id: str = None):
    await ctx.defer()

    if not sts_id:
        me = await _get_sts(str(ctx.author.id))
        if not me:
            return await ctx.send(
                "❌ Not linked. Use `/link <code>` after generating a code on the portal, "
                "or provide an STS ID: `/shareprofile <sts_id>`"
            )
        sts_id = me["sts_id"]

    sts_id = sts_id.strip().upper()

    # Fetch user + entries in parallel
    try:
        users   = await supabase_get("share_users",
            {"sts_id": f"eq.{sts_id}", "select": "*"})
        entries = await supabase_get("share_entries",
            {"sts_id": f"eq.{sts_id}", "select": "*",
             "order": "created_at.desc"})
    except Exception as e:
        return await ctx.send(f"❌ Could not fetch data: {e}")

    if not users:
        return await ctx.send(f"❌ No player found with STS ID `{sts_id}`")

    u      = users[0]
    values = [e["value"] for e in entries]
    if not values:
        return await ctx.send(f"📭 `{sts_id}` hasn't submitted any share entries yet.")

    avg_v  = sum(values) / len(values)
    max_v  = max(values)
    min_v  = min(values)
    total  = len(values)
    latest = values[0] if values else 0

    # Days active
    days = set(
        datetime.fromisoformat(e["created_at"].replace("Z","+00:00"))
        .astimezone(IST).strftime("%Y-%m-%d")
        for e in entries
    )
    # Streak
    streak = 0
    check  = _now_ist().date()
    for d in sorted(days, reverse=True):
        dd = datetime.strptime(d, "%Y-%m-%d").date()
        if dd == check:
            streak += 1
            check  = check - timedelta(days=1)
        else:
            break

    # Simple consistency: days submitted / (total days since first entry)
    if entries:
        first_dt = datetime.fromisoformat(
            entries[-1]["created_at"].replace("Z","+00:00")).astimezone(IST).date()
        total_days = max((_now_ist().date() - first_dt).days + 1, 1)
        consistency = len(days) / total_days * 100
    else:
        consistency = 0

    rank = _rank_label(consistency)

    # Growth: compare latest vs 7 days ago
    week_ago = _now_ist() - timedelta(days=7)
    week_entries = [
        e["value"] for e in entries
        if datetime.fromisoformat(e["created_at"].replace("Z","+00:00"))
        .astimezone(IST) >= week_ago
    ]
    if len(week_entries) >= 2:
        growth = ((week_entries[0] - week_entries[-1]) / week_entries[-1]) * 100
        growth_str = f"{'▲' if growth >= 0 else '▼'} {abs(growth):.1f}% (7d)"
        growth_col = 0x00ff88 if growth >= 0 else 0xff4757
    else:
        growth_str = "—"
        growth_col = 0x00d4ff

    embed = discord.Embed(
        title=f"👤 {u.get('name') or sts_id} — Portal Profile",
        color=growth_col
    )
    embed.add_field(name="STS ID",        value=f"`{sts_id}`",             inline=True)
    embed.add_field(name="Airline",        value=u.get("airline","—"),      inline=True)
    embed.add_field(name="Alliance",       value=u.get("alliance","—"),     inline=True)
    embed.add_field(name="AERO Points",    value=f"{u.get('aero_points',0):,}", inline=True)
    embed.add_field(name="Rank",           value=rank,                      inline=True)
    embed.add_field(name="7d Growth",      value=growth_str,                inline=True)
    embed.add_field(name="Latest Value",   value=_money(latest),            inline=True)
    embed.add_field(name="Average",        value=_money(avg_v),             inline=True)
    embed.add_field(name="All-Time High",  value=_money(max_v),             inline=True)
    embed.add_field(name="Entries",        value=str(total),                inline=True)
    embed.add_field(name="Days Active",    value=str(len(days)),            inline=True)
    embed.add_field(name="Streak",         value=f"🔥 {streak}d",          inline=True)
    embed.add_field(name="Consistency",    value=f"{consistency:.1f}%",     inline=True)

    # Last 3 entries
    recent = entries[:3]
    rec_txt = "\n".join(
        f"• {_ist_str(e['created_at'])} → **{_money(e['value'])}** `{e.get('alliance','')}`"
        for e in recent
    )
    embed.add_field(name="Recent Entries", value=rec_txt or "—", inline=False)

    discord_linked = u.get("discord_id")
    if discord_linked:
        embed.set_footer(text=f"Discord: {discord_linked} • JARVIS • AERO Portal")
    else:
        embed.set_footer(text="JARVIS • AERO Portal Sync")

    await ctx.send(embed=embed, view=_ProfileView(entries, u))

class _ProfileView(discord.ui.View):
    def __init__(self, entries, user):
        super().__init__(timeout=180)
        self.entries = entries
        self.user    = user

    @discord.ui.button(label="📈 Graph", style=discord.ButtonStyle.primary)
    async def graph(self, interaction, button):
        hist   = list(reversed(self.entries))
        dates  = [datetime.fromisoformat(e["created_at"].replace("Z","+00:00"))
                  .astimezone(IST).strftime("%d %b") for e in hist]
        values = [e["value"] for e in hist]
        avg_v  = sum(values) / len(values)

        fig, ax = _dark_fig(11, 5)
        ax.plot(dates, values, color=_SHARE_ACC, linewidth=2.5,
                marker="o", markersize=5)
        ax.axhline(avg_v, color="#8e9ac0", linestyle="--",
                   linewidth=1, alpha=0.6, label=f"Avg {_money(avg_v)}")
        ax.fill_between(range(len(values)), values, alpha=0.08, color=_SHARE_ACC)
        ax.set_title(f"{self.user.get('name') or self.user['sts_id']} — Share History")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: _money(x)))
        plt.xticks(rotation=35, color="#8e9ac0", fontsize=8)
        ax.legend(facecolor=_SHARE_FG, labelcolor="#8e9ac0")
        buf = _save_buf(fig)

        e = discord.Embed(title="📈 Share History Graph", color=0x00d4ff)
        e.set_image(url="attachment://profile_graph.png")
        await interaction.response.send_message(
            embed=e, file=discord.File(buf,"profile_graph.png"), ephemeral=True)

# =========================================================
# !compareprofile  — head-to-head two players
# =========================================================
@bot.hybrid_command(
    name="compareprofile",
    description="Compare two portal players head-to-head"
)
@app_commands.describe(sts1="First player STS ID", sts2="Second player STS ID")
async def compareprofile(ctx, sts1: str, sts2: str):
    await ctx.defer()

    async def _fetch_player(sts):
        sts = sts.strip().upper()
        u   = await supabase_get("share_users",
            {"sts_id":f"eq.{sts}","select":"*"})
        e   = await supabase_get("share_entries",
            {"sts_id":f"eq.{sts}","select":"*","order":"created_at.desc"})
        return (u[0] if u else None), e

    u1, e1 = await _fetch_player(sts1)
    u2, e2 = await _fetch_player(sts2)

    if not u1: return await ctx.send(f"❌ Player `{sts1}` not found")
    if not u2: return await ctx.send(f"❌ Player `{sts2}` not found")
    if not e1: return await ctx.send(f"📭 `{sts1}` has no entries")
    if not e2: return await ctx.send(f"📭 `{sts2}` has no entries")

    v1 = [x["value"] for x in e1]
    v2 = [x["value"] for x in e2]
    avg1, avg2 = sum(v1)/len(v1), sum(v2)/len(v2)
    max1, max2 = max(v1),         max(v2)
    name1 = u1.get("name") or sts1
    name2 = u2.get("name") or sts2
    winner = name1 if avg1 > avg2 else name2

    # Bar comparison
    fig, ax = _dark_fig(8, 5)
    cats   = ["Latest","Average","All-Time High"]
    x      = np.arange(len(cats))
    w      = 0.35
    d1     = [v1[0], avg1, max1]
    d2     = [v2[0], avg2, max2]
    ax.bar(x - w/2, d1, w, label=name1, color=_SHARE_ACC,  alpha=0.85)
    ax.bar(x + w/2, d2, w, label=name2, color="#a855f7", alpha=0.85)
    ax.set_xticks(x); ax.set_xticklabels(cats, color="#8e9ac0")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: _money(x)))
    ax.legend(facecolor=_SHARE_FG, labelcolor="#8e9ac0")
    ax.set_title(f"{name1} vs {name2}")
    buf = _save_buf(fig)

    embed = discord.Embed(
        title=f"⚔️ {name1} vs {name2}",
        description=f"🏆 **Winner (by avg):** {winner}",
        color=0x00d4ff
    )
    def _row(label, val1, val2, higher_better=True):
        b1 = "**" if (val1>val2 if higher_better else val1<val2) else ""
        b2 = "**" if (val2>val1 if higher_better else val2<val1) else ""
        e1s = b1+_money(val1)+b1 if isinstance(val1, float) else b1+str(val1)+b1
        e2s = b2+_money(val2)+b2 if isinstance(val2, float) else b2+str(val2)+b2
        return f"`{label:15}` {e1s:>18}   {e2s}"

    lines = [
        f"`{'':15}` {'`'+name1+'`':>18}   `{name2}`",
        _row("Latest",       float(v1[0]), float(v2[0])),
        _row("Average",      avg1,         avg2),
        _row("All-Time High",max1,         max2),
        _row("Entries",      float(len(v1)),float(len(v2))),
        _row("AERO Points",  float(u1.get("aero_points",0)),
                             float(u2.get("aero_points",0))),
    ]
    embed.add_field(name="Stats", value="\n".join(lines), inline=False)
    embed.set_image(url="attachment://compare.png")
    embed.set_footer(text="JARVIS • AERO Portal Sync")
    await ctx.send(embed=embed, file=discord.File(buf,"compare.png"))

# =========================================================
# !alliancestats  — alliance aggregate from portal
# =========================================================
@bot.hybrid_command(
    name="alliancestats",
    description="Alliance share stats from the AERO portal"
)
@app_commands.describe(alliance="Alliance name")
async def alliancestats(ctx, *, alliance: str):
    await ctx.defer()
    try:
        entries = await supabase_get("share_entries", {
            "alliance": f"eq.{alliance}",
            "select":   "*",
            "order":    "created_at.desc",
        })
        users = await supabase_get("share_users", {
            "alliance": f"eq.{alliance}",
            "select":   "sts_id,name,aero_points",
        })
    except Exception as e:
        return await ctx.send(f"❌ Fetch failed: {e}")

    if not entries:
        return await ctx.send(f"❌ No entries found for alliance **{alliance}**")

    user_map = {u["sts_id"]: u for u in users}
    total_val = sum(e["value"] for e in entries)
    avg_val   = total_val / len(entries)
    max_val   = max(e["value"] for e in entries)
    players   = set(e["sts_id"] for e in entries)
    total_pts = sum(u.get("aero_points",0) for u in users)

    # Top 3 by latest entry
    latest_per = {}
    for e in entries:
        if e["sts_id"] not in latest_per:
            latest_per[e["sts_id"]] = e["value"]
    top3 = sorted(latest_per.items(), key=lambda x: x[1], reverse=True)[:3]

    embed = discord.Embed(
        title=f"🏦 Alliance — {alliance}",
        color=0x00d4ff
    )
    embed.add_field(name="Members",       value=str(len(players)),      inline=True)
    embed.add_field(name="Total Entries", value=str(len(entries)),      inline=True)
    embed.add_field(name="Total AERO Pts",value=f"{total_pts:,}",       inline=True)
    embed.add_field(name="Total Value",   value=_money(total_val),      inline=True)
    embed.add_field(name="Avg Value",     value=_money(avg_val),        inline=True)
    embed.add_field(name="Highest Value", value=_money(max_val),        inline=True)

    top_txt = "\n".join(
        f"{'🥇🥈🥉'[i]} **{(user_map.get(sid,{}).get('name') or sid)}** → {_money(v)}"
        for i,(sid,v) in enumerate(top3)
    )
    embed.add_field(name="Top 3 (latest)", value=top_txt or "—", inline=False)

    # Daily trend chart
    by_day = {}
    for e in entries:
        day = datetime.fromisoformat(e["created_at"].replace("Z","+00:00"))\
              .astimezone(IST).strftime("%d %b")
        by_day.setdefault(day, []).append(e["value"])

    if len(by_day) >= 2:
        sorted_days = sorted(by_day.keys(),
            key=lambda d: datetime.strptime(d, "%d %b"))
        avgs = [sum(by_day[d])/len(by_day[d]) for d in sorted_days]
        fig, ax = _dark_fig(10, 4)
        ax.plot(sorted_days, avgs, color=_SHARE_ACC, linewidth=2,
                marker="o", markersize=4)
        ax.fill_between(range(len(avgs)), avgs, alpha=0.08, color=_SHARE_ACC)
        ax.set_title(f"{alliance} — Daily Avg Share Value")
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: _money(x)))
        plt.xticks(rotation=35, color="#8e9ac0", fontsize=8)
        buf = _save_buf(fig)
        embed.set_image(url="attachment://alliance_trend.png")
        embed.set_footer(text="JARVIS • AERO Portal Sync")
        await ctx.send(embed=embed, file=discord.File(buf,"alliance_trend.png"))
    else:
        embed.set_footer(text="JARVIS • AERO Portal Sync")
        await ctx.send(embed=embed)

# =========================================================
# !portalalert  — DM me when any player submits a new entry
# =========================================================
_alert_subscribers: set = set()   # discord user IDs subscribed

@bot.hybrid_command(
    name="portalalert",
    description="Toggle DM notifications when new share entries are posted on the portal"
)
async def portalalert(ctx):
    uid = ctx.author.id
    if uid in _alert_subscribers:
        _alert_subscribers.discard(uid)
        await ctx.send("🔕 Portal share alerts **OFF**. You won't be DM'd.", ephemeral=True)
    else:
        _alert_subscribers.add(uid)
        await ctx.send("🔔 Portal share alerts **ON**. I'll DM you when new entries appear!", ephemeral=True)

# =========================================================
# BACKGROUND TASK — poll Supabase for new entries, DM subs
# =========================================================
_last_seen_entry_id = None

async def _portal_alert_loop():
    global _last_seen_entry_id
    await bot.wait_until_ready()
    print("[SHARE ALERT] Background loop started")

    # Seed the last-seen ID on startup (don't alert for historical data)
    try:
        rows = await supabase_get("share_entries", {
            "select": "id", "order": "id.desc", "limit": "1"
        })
        if rows:
            _last_seen_entry_id = rows[0]["id"]
    except Exception as e:
        print(f"[SHARE ALERT] Seed error: {e}")

    while not bot.is_closed():
        await asyncio.sleep(120)   # poll every 2 minutes
        if not _alert_subscribers:
            continue
        try:
            params = {"select": "*", "order": "id.desc", "limit": "10"}
            if _last_seen_entry_id:
                params["id"] = f"gt.{_last_seen_entry_id}"
            new_entries = await supabase_get("share_entries", params)
            if not new_entries:
                continue

            # Update cursor
            _last_seen_entry_id = max(e["id"] for e in new_entries)

            # Fetch names
            sids = list(set(e["sts_id"] for e in new_entries))
            users = await supabase_get("share_users", {
                "sts_id": f"in.({','.join(sids)})",
                "select": "sts_id,name,alliance"
            })
            umap = {u["sts_id"]: u for u in users}

            for e in new_entries:
                u    = umap.get(e["sts_id"], {})
                name = u.get("name") or e["sts_id"]
                msg  = (f"📤 **New Share Entry** on AERO Portal\n"
                        f"Player: **{name}** (`{e['sts_id']}`)\n"
                        f"Alliance: {e.get('alliance','—')}\n"
                        f"Value: **{_money(e['value'])}**\n"
                        f"Time: {_ist_str(e['created_at'])}")
                for uid in list(_alert_subscribers):
                    try:
                        user = await bot.fetch_user(uid)
                        await user.send(msg)
                    except Exception as ex:
                        print(f"[SHARE ALERT] DM failed to {uid}: {ex}")
        except Exception as e:
            print(f"[SHARE ALERT] Poll error: {e}")

# =========================================================
# Register the background task in on_ready
# =========================================================
# ADD this line inside your existing on_ready() event:
#
#   bot.loop.create_task(_portal_alert_loop())
#
# =========================================================
