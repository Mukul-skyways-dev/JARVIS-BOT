# =========================================================
#  aerion_alliance.py  —  AERION Alliance Intelligence
#  /allianceintel  /activityaudit  /activityalert  /mission
#
#  Integration in bot1_aerion.py:
#    from aerion_alliance import register_alliance
#    # in on_ready():
#    register_alliance(bot, groq, supabase_get, supabase_post,
#                      supabase_patch, check_membership)
# =========================================================

import asyncio, json
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
import pytz
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

_IST     = pytz.timezone("Asia/Kolkata")
BOT_NAME = "AERION"
BOT_VER  = "V3 ALPHA"
FOOTER   = f"{BOT_NAME} Alliance Intelligence • {BOT_VER}"
MODEL    = "openai/gpt-oss-120b"

# ── Injected refs ──────────────────────────────────────────
_bot           = None
_groq          = None
_supa_get      = None
_supa_post     = None
_supa_patch    = None
_check_member  = None

# ── Alert config store (in-memory, reset on restart) ──────
# Structure: { guild_id: { days_threshold, channel_id, enabled } }
_alert_configs: dict = {}

# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────
def _now_ist():  return datetime.now(_IST)
def _now_utc():  return datetime.now(timezone.utc)
def _ts():       return _now_ist().strftime("%d %b %Y  %I:%M %p IST")

def _fmt(v):
    try:
        v = float(v)
        if v >= 1e9: return f"${v/1e9:.3f}B"
        if v >= 1e6: return f"${v/1e6:.2f}M"
        if v >= 1e3: return f"${v/1e3:.1f}K"
        return f"${v:,.0f}"
    except: return str(v)

def _parse(v):
    try: return float(v)
    except: return 0.0

def _ist_day(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))\
               .astimezone(_IST).strftime("%Y-%m-%d")
    except: return "1970-01-01"

def _days_since(iso: str) -> int:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_IST)
        return (_now_ist() - dt).days
    except: return 999

async def _ai(system: str, user: str, max_tokens=600) -> str:
    try:
        resp = await asyncio.to_thread(
            _groq.chat.completions.create,
            model=MODEL,
            max_tokens=max_tokens,
            temperature=0.6,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ AI unavailable: {e}"

# ─────────────────────────────────────────────────────────
#  DATA FETCHERS
# ─────────────────────────────────────────────────────────
async def _get_alliance_players(alliance: str) -> list:
    try:
        rows = await _supa_get("share_users", {
            "alliance": f"ilike.*{alliance}*",
            "select":   "sts_id,name,airline,alliance,aero_points,contribution_points,discord_id",
        })
        return rows or []
    except Exception as e:
        print(f"[ALLIANCE] _get_alliance_players error: {e}")
        return []

async def _get_player_entries(sts_id: str, limit=30) -> list:
    try:
        rows = await _supa_get("share_entries", {
            "sts_id": f"eq.{sts_id}",
            "select": "value,created_at",
            "order":  "created_at.desc",
            "limit":  str(limit),
        })
        return rows or []
    except: return []

async def _get_all_alliance_entries(alliance: str, limit=500) -> list:
    try:
        rows = await _supa_get("share_entries", {
            "alliance": f"ilike.*{alliance}*",
            "select":   "sts_id,value,created_at",
            "order":    "created_at.desc",
            "limit":    str(limit),
        })
        return rows or []
    except: return []

# ─────────────────────────────────────────────────────────
#  MEMBERSHIP GATE
# ─────────────────────────────────────────────────────────
async def _gate(ctx) -> bool:
    if not _check_member: return True
    try:
        status = await _check_member(str(ctx.author.id))
    except: return True

    if not status["linked"]:
        embed = discord.Embed(
            title="🔗 Link Required",
            description="Use `/link <code>` to connect your portal account first.",
            color=0xff4757
        )
        embed.set_footer(text=f"{BOT_NAME} • AERO CROWN DYNASTY")
        await ctx.send(embed=embed, ephemeral=True)
        return False

    if not status["has_access"]:
        cost = 1000 if status["is_new"] else 100
        pts  = status["aero_points"]
        embed = discord.Embed(
            title="🔒 AERION MEMBERSHIP REQUIRED",
            description=(
                f"{'🆕' if status['is_new'] else '🔄'} "
                f"**{cost:,} AERO Points** to activate.\n"
                f"Your balance: **{pts:,}**\n\n"
                + ("✅ Use `/subscribe` now!" if pts >= cost
                   else f"❌ Need **{cost-pts:,}** more points.")
            ),
            color=0xff4757
        )
        embed.set_footer(text=f"{BOT_NAME} • AERO CROWN DYNASTY")
        await ctx.send(embed=embed, ephemeral=True)
        return False

    return True

# ─────────────────────────────────────────────────────────
#  PLAYER STATS
# ─────────────────────────────────────────────────────────
def _player_stats(entries: list) -> dict:
    if not entries:
        return {"entries": 0, "days": 0, "latest": 0, "avg": 0,
                "max": 0, "growth_7d": 0, "streak": 0,
                "consistency": 0, "last_active": None}

    vals   = [_parse(e["value"]) for e in entries]
    days   = sorted({_ist_day(e["created_at"]) for e in entries}, reverse=True)
    latest = vals[0]
    avg    = sum(vals) / len(vals)
    mx     = max(vals)

    # 7-day growth
    now_ist = _now_ist()
    recent  = [_parse(e["value"]) for e in entries
               if (_now_ist() - datetime.fromisoformat(
                   e["created_at"].replace("Z", "+00:00")
               ).astimezone(_IST)).days <= 7]
    growth_7d = 0.0
    if len(recent) >= 2:
        growth_7d = (recent[0] - recent[-1]) / recent[-1] * 100 if recent[-1] else 0

    # Streak
    streak = 0
    check  = now_ist.date()
    for d in days:
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
            if dd == check: streak += 1; check -= timedelta(days=1)
            else: break
        except: pass

    # Consistency
    if entries:
        first_day = min(days)
        try:
            first_dt  = datetime.strptime(first_day, "%Y-%m-%d")
            total_days= max((now_ist.date() - first_dt.date()).days + 1, 1)
            consistency = len(days) / total_days * 100
        except: consistency = 0
    else:
        consistency = 0

    last_active = days[0] if days else None
    days_inactive = (_now_ist().date() - datetime.strptime(last_active, "%Y-%m-%d").date()).days \
                    if last_active else 999

    return {
        "entries":       len(entries),
        "days":          len(days),
        "latest":        latest,
        "avg":           avg,
        "max":           mx,
        "growth_7d":     growth_7d,
        "streak":        streak,
        "consistency":   consistency,
        "last_active":   last_active,
        "days_inactive": days_inactive,
    }

def _activity_label(days_inactive: int, consistency: float) -> tuple:
    """Returns (label, emoji, color_hex)"""
    if days_inactive <= 2 and consistency >= 60:
        return "Active",   "🟢", 0x00ff88
    if days_inactive <= 5:
        return "At Risk",  "🟡", 0xffa502
    return "Inactive",     "🔴", 0xff4757

# ─────────────────────────────────────────────────────────
#  DARK GRAPH HELPER
# ─────────────────────────────────────────────────────────
_BG  = "#0a0e1a"
_FG  = "#1e2540"
_ACC = "#00d4ff"
_GRN = "#00ff88"
_RED = "#ff4757"
_AMB = "#ffa502"

def _dark_fig(w=10, h=5):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_FG)
    ax.tick_params(colors="#8e9ac0")
    for sp in ax.spines.values(): sp.set_color("#2a3450")
    ax.grid(alpha=0.12, linestyle=":", color="#3a4460")
    return fig, ax

def _save_buf(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110,
                facecolor=fig.get_facecolor())
    buf.seek(0); plt.close(fig)
    return buf

# =========================================================
#  /allianceintel  —  Full alliance health & performance
# =========================================================
async def _cmd_allianceintel(ctx, alliance: str):
    await ctx.defer()
    if not await _gate(ctx): return

    msg = await ctx.send(f"🏛️ **AERION** analysing alliance `{alliance}`...")

    players = await _get_alliance_players(alliance)
    if not players:
        return await msg.edit(content=f"❌ No players found for alliance `{alliance}`.")

    entries_all = await _get_all_alliance_entries(alliance, limit=1000)
    entry_map   = {}
    for e in entries_all:
        entry_map.setdefault(e["sts_id"], []).append(e)

    # Per-player stats
    all_stats = []
    for p in players:
        sid   = p["sts_id"]
        st    = _player_stats(entry_map.get(sid, []))
        label, emoji, _ = _activity_label(st["days_inactive"], st["consistency"])
        all_stats.append({**p, **st, "label": label, "emoji": emoji})

    total    = len(all_stats)
    active   = sum(1 for s in all_stats if s["label"] == "Active")
    at_risk  = sum(1 for s in all_stats if s["label"] == "At Risk")
    inactive = sum(1 for s in all_stats if s["label"] == "Inactive")

    # Alliance-level metrics
    vals_latest = [s["latest"] for s in all_stats if s["latest"] > 0]
    alliance_avg= sum(vals_latest)/len(vals_latest) if vals_latest else 0
    alliance_top= max(vals_latest) if vals_latest else 0
    total_contrib = sum(_parse(p.get("contribution_points",0)) for p in players)
    total_pts     = sum(_parse(p.get("aero_points",0)) for p in players)

    # Health score (0-100)
    activity_score  = (active / total * 100) if total else 0
    consistency_avg = sum(s["consistency"] for s in all_stats) / total if total else 0
    health_score    = int(activity_score * 0.5 + consistency_avg * 0.5)

    def _health_label(score):
        if score >= 80: return "🟢 Excellent"
        if score >= 60: return "🟡 Good"
        if score >= 40: return "🟠 Fair"
        return "🔴 Critical"

    # AI analysis
    context = (
        f"Alliance: {alliance} | Members: {total}\n"
        f"Active: {active} | At-Risk: {at_risk} | Inactive: {inactive}\n"
        f"Avg Share: {_fmt(alliance_avg)} | Top Share: {_fmt(alliance_top)}\n"
        f"Health Score: {health_score}/100 | Avg Consistency: {consistency_avg:.1f}%\n"
        f"Total Contribution Points: {total_contrib:,.0f}\n"
        f"Top 3 players by latest: "
        + ", ".join(f"{s['name']}({_fmt(s['latest'])})"
                    for s in sorted(all_stats, key=lambda x: x["latest"], reverse=True)[:3])
    )
    ai_report = await _ai(
        f"You are {BOT_NAME}. Write a concise alliance health report (3-4 lines). "
        "Include: Overall health assessment, key strengths, biggest risks, "
        "and 1 actionable recommendation for the alliance leader.",
        context, max_tokens=350
    )

    # Top 5 members
    top5 = sorted(all_stats, key=lambda x: x["latest"], reverse=True)[:5]
    top5_txt = "\n".join(
        f"{s['emoji']} **{s['name']}** — {_fmt(s['latest'])} | "
        f"{s['consistency']:.0f}% consistent | {s['streak']}d streak"
        for s in top5
    )

    # Graph: activity distribution pie
    fig, ax = plt.subplots(figsize=(5, 4))
    fig.patch.set_facecolor(_BG); ax.set_facecolor(_BG)
    sizes  = [active, at_risk, inactive]
    colors = [_GRN, _AMB, _RED]
    labels = [f"Active\n{active}", f"At Risk\n{at_risk}", f"Inactive\n{inactive}"]
    wedges, _ = ax.pie(
        [max(s, 0.001) for s in sizes],
        colors=colors, startangle=90,
        wedgeprops=dict(edgecolor=_BG, linewidth=2)
    )
    ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(1, 0.5),
              facecolor=_FG, labelcolor="#e0e8ff", fontsize=9)
    ax.set_title(f"{alliance} — Activity Status", color=_ACC, fontsize=11)
    pie_buf = _save_buf(fig)

    color = 0x00ff88 if health_score >= 70 else (0xffa502 if health_score >= 40 else 0xff4757)
    embed = discord.Embed(
        title=f"🏛️ ALLIANCE INTEL — {alliance.upper()}",
        color=color
    )
    embed.add_field(name="📊 Overview",
        value=(
            f"**Members     :** {total}\n"
            f"**Health Score:** {health_score}/100 {_health_label(health_score)}\n"
            f"**Activity    :** 🟢{active} 🟡{at_risk} 🔴{inactive}"
        ), inline=True)
    embed.add_field(name="💹 Share Performance",
        value=(
            f"**Alliance Avg:** {_fmt(alliance_avg)}\n"
            f"**Top Value   :** {_fmt(alliance_top)}\n"
            f"**Avg Consist.:** {consistency_avg:.1f}%"
        ), inline=True)
    embed.add_field(name="💰 AERO Economy",
        value=(
            f"**Total AERO Pts  :** {total_pts:,.0f}\n"
            f"**Total Contrib.  :** {total_contrib:,.0f}"
        ), inline=True)
    embed.add_field(name="🏆 Top 5 Members", value=top5_txt or "—", inline=False)
    embed.add_field(name="🧠 AERION Intelligence Report",
        value=ai_report[:1020], inline=False)
    embed.set_image(url="attachment://alliance_pie.png")
    embed.set_footer(text=f"{FOOTER} • {_ts()}")

    await msg.delete()
    await ctx.send(embed=embed, file=discord.File(pie_buf, "alliance_pie.png"))

# =========================================================
#  /activityaudit  —  Scan & classify all members
# =========================================================
async def _cmd_activityaudit(ctx, alliance: str, days_threshold: int = 3):
    await ctx.defer()
    if not await _gate(ctx): return

    msg = await ctx.send(f"🔍 **AERION** auditing `{alliance}` members...")

    players = await _get_alliance_players(alliance)
    if not players:
        return await msg.edit(content=f"❌ No players found for `{alliance}`.")

    entries_all = await _get_all_alliance_entries(alliance, limit=1000)
    entry_map   = {}
    for e in entries_all:
        entry_map.setdefault(e["sts_id"], []).append(e)

    active_list   = []
    at_risk_list  = []
    inactive_list = []

    for p in players:
        sid   = p["sts_id"]
        st    = _player_stats(entry_map.get(sid, []))
        label, emoji, _ = _activity_label(st["days_inactive"], st["consistency"])

        row = {
            "name":         p.get("name") or sid,
            "sts_id":       sid,
            "discord_id":   p.get("discord_id"),
            "latest":       st["latest"],
            "days_inactive":st["days_inactive"],
            "consistency":  st["consistency"],
            "streak":       st["streak"],
            "last_active":  st["last_active"] or "Never",
        }
        if label == "Active":   active_list.append(row)
        elif label == "At Risk": at_risk_list.append(row)
        else:                   inactive_list.append(row)

    # Sort each group
    for lst in [active_list, at_risk_list, inactive_list]:
        lst.sort(key=lambda x: x["days_inactive"])

    def _rows_text(lst, limit=8):
        if not lst: return "None"
        lines = []
        for r in lst[:limit]:
            linked = "🔗" if r["discord_id"] else "⚠️"
            lines.append(
                f"{linked} **{r['name']}** — "
                f"Last: `{r['last_active']}` | "
                f"{r['consistency']:.0f}% consistent | "
                f"{r['days_inactive']}d ago"
            )
        if len(lst) > limit:
            lines.append(f"*...and {len(lst)-limit} more*")
        return "\n".join(lines)

    # Bar chart: days inactive per member
    all_members = active_list + at_risk_list + inactive_list
    all_members.sort(key=lambda x: x["days_inactive"], reverse=True)
    names  = [m["name"][:10] for m in all_members[:15]]
    d_vals = [m["days_inactive"] for m in all_members[:15]]
    colors = []
    for m in all_members[:15]:
        lbl, _, _ = _activity_label(m["days_inactive"], m["consistency"])
        colors.append(_GRN if lbl=="Active" else (_AMB if lbl=="At Risk" else _RED))

    fig, ax = _dark_fig(10, 5)
    bars = ax.barh(names, d_vals, color=colors, alpha=0.85)
    ax.set_xlabel("Days Inactive", color="#8e9ac0")
    ax.set_title(f"{alliance} — Member Activity Audit", color=_ACC)
    ax.axvline(days_threshold, color="#ffffff", linestyle="--",
               alpha=0.4, linewidth=1, label=f"Threshold ({days_threshold}d)")
    ax.legend(facecolor=_FG, labelcolor="#8e9ac0")
    ax.invert_yaxis()
    for bar, val in zip(bars, d_vals):
        ax.text(bar.get_width()+0.1, bar.get_y()+bar.get_height()/2,
                f"{val}d", va="center", color="#e0e8ff", fontsize=8)
    buf = _save_buf(fig)

    embed = discord.Embed(
        title=f"🔍 ACTIVITY AUDIT — {alliance.upper()}",
        color=0x00d4ff
    )
    embed.add_field(name="📊 Summary",
        value=(
            f"🟢 **Active   :** {len(active_list)}\n"
            f"🟡 **At Risk  :** {len(at_risk_list)}\n"
            f"🔴 **Inactive :** {len(inactive_list)}\n"
            f"**Threshold:** {days_threshold}d"
        ), inline=True)
    embed.add_field(name="🟢 Active Members",
        value=_rows_text(active_list, 5), inline=False)
    embed.add_field(name="🟡 At Risk (4-5 days inactive)",
        value=_rows_text(at_risk_list, 6), inline=False)
    embed.add_field(name="🔴 Inactive (6+ days)",
        value=_rows_text(inactive_list, 6), inline=False)

    if inactive_list:
        embed.add_field(name="💡 Tip",
            value="Use `/activityalert` to automatically DM inactive members.",
            inline=False)

    embed.set_image(url="attachment://audit.png")
    embed.set_footer(text=f"{FOOTER} • {_ts()}")

    await msg.delete()
    await ctx.send(embed=embed, file=discord.File(buf, "audit.png"))

# =========================================================
#  /activityalert  —  Auto-DM inactive members
# =========================================================
async def _cmd_activityalert(ctx, alliance: str,
                              days: int = 5, action: str = "notify"):
    await ctx.defer()
    if not await _gate(ctx): return

    if not ctx.author.guild_permissions.manage_guild:
        return await ctx.send("❌ Only alliance admins can use this command.", ephemeral=True)

    action = action.lower()
    if action not in ("notify", "status", "off"):
        return await ctx.send("❌ `action` must be: `notify`, `status`, or `off`")

    guild_id = str(ctx.guild.id)

    if action == "status":
        cfg = _alert_configs.get(guild_id)
        if not cfg or not cfg.get("enabled"):
            return await ctx.send("ℹ️ Activity alerts are **disabled** for this server.")
        return await ctx.send(
            f"✅ Activity alerts **active**\n"
            f"Alliance: `{cfg['alliance']}` | Threshold: **{cfg['days']}d** | "
            f"Channel: <#{cfg['channel_id']}>")

    if action == "off":
        _alert_configs[guild_id] = {"enabled": False}
        return await ctx.send("🔕 Activity alerts **disabled**.")

    # action == notify: scan + DM inactive members NOW
    msg = await ctx.send(
        f"📢 Scanning `{alliance}` for members inactive **{days}+ days**...")

    players = await _get_alliance_players(alliance)
    if not players:
        return await msg.edit(content=f"❌ No players found for `{alliance}`.")

    entries_all = await _get_all_alliance_entries(alliance, limit=1000)
    entry_map   = {}
    for e in entries_all:
        entry_map.setdefault(e["sts_id"], []).append(e)

    notified = skipped_no_discord = already_active = 0
    notified_names = []

    for p in players:
        sid  = p["sts_id"]
        st   = _player_stats(entry_map.get(sid, []))

        if st["days_inactive"] < days:
            already_active += 1
            continue

        disc_id = p.get("discord_id")
        if not disc_id:
            skipped_no_discord += 1
            continue

        # DM the player
        try:
            user = await _bot.fetch_user(int(disc_id))
            embed = discord.Embed(
                title="⚠️ AERION Activity Alert",
                description=(
                    f"Hey **{p.get('name', 'Player')}**! 👋\n\n"
                    f"You haven't submitted a share entry in **{st['days_inactive']} day(s)**.\n\n"
                    f"Your alliance **{alliance}** depends on your activity.\n"
                    f"Last active: `{st['last_active'] or 'Unknown'}`\n\n"
                    f"**Log in to the AERO portal and submit your share entry today!**"
                ),
                color=0xffa502
            )
            embed.add_field(name="📊 Your Stats",
                value=(
                    f"Consistency: {st['consistency']:.1f}%\n"
                    f"Streak: {st['streak']}d\n"
                    f"Last Value: {_fmt(st['latest'])}"
                ), inline=False)
            embed.set_footer(text=f"{FOOTER} | Sent by {ctx.author.display_name}")
            await user.send(embed=embed)
            notified += 1
            notified_names.append(p.get("name", sid))
        except Exception as e:
            print(f"[ALLIANCE] DM failed for {disc_id}: {e}")
            skipped_no_discord += 1

    # Save config for auto-loop
    _alert_configs[guild_id] = {
        "enabled":    True,
        "alliance":   alliance,
        "days":       days,
        "channel_id": ctx.channel.id,
    }

    result_embed = discord.Embed(
        title="📢 Activity Alert — Sent",
        color=0x00ff88 if notified else 0xffa502
    )
    result_embed.add_field(name="✅ DMs Sent",       value=str(notified),            inline=True)
    result_embed.add_field(name="⏭ Already Active", value=str(already_active),       inline=True)
    result_embed.add_field(name="⚠️ No Discord",    value=str(skipped_no_discord),   inline=True)
    if notified_names:
        result_embed.add_field(name="Notified Members",
            value="\n".join(f"• {n}" for n in notified_names[:10])
                  + (f"\n*...+{len(notified_names)-10} more*"
                     if len(notified_names) > 10 else ""),
            inline=False)
    result_embed.add_field(name="💡 Auto-Alerts",
        value="Use `/activityalert status` to check alert config.\nAlerts also run daily via `/mission`.",
        inline=False)
    result_embed.set_footer(text=f"{FOOTER} • {_ts()}")

    await msg.delete()
    await ctx.send(embed=result_embed)

# =========================================================
#  /mission  —  Mission Control for AERION automation
# =========================================================

# Mission state
_mission_state = {
    "daily_brief":   {"enabled": False, "channel_id": None, "time": "09:00"},
    "activity_scan": {"enabled": False, "interval_h": 24},
    "share_alerts":  {"enabled": False, "threshold": 0},
    "last_brief_day": None,
}

class _MissionControlView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=180)
        self.ctx = ctx

    def _build_embed(self):
        s = _mission_state
        db  = s["daily_brief"]
        act = s["activity_scan"]
        sha = s["share_alerts"]

        embed = discord.Embed(
            title="🎯 AERION MISSION CONTROL",
            description=(
                "Centralised control for AERION's automated operations.\n"
                "Toggle modules, set channels and configure schedules."
            ),
            color=0x00d4ff
        )
        embed.add_field(name="📰 Daily Brief",
            value=(
                f"Status : {'✅ ON' if db['enabled'] else '❌ OFF'}\n"
                f"Time   : {db['time']} IST\n"
                f"Channel: "
                + (f"<#{db['channel_id']}>" if db['channel_id'] else "Not set")
            ), inline=True)
        embed.add_field(name="🔍 Activity Scan",
            value=(
                f"Status  : {'✅ ON' if act['enabled'] else '❌ OFF'}\n"
                f"Interval: Every {act['interval_h']}h\n"
                f"Auto-DM : Inactive members"
            ), inline=True)
        embed.add_field(name="⛽ Share Alerts",
            value=(
                f"Status   : {'✅ ON' if sha['enabled'] else '❌ OFF'}\n"
                f"Threshold: {sha['threshold']}"
            ), inline=True)
        embed.set_footer(text=f"{FOOTER} • {_ts()}")
        return embed

    @discord.ui.button(label="📰 Toggle Daily Brief", style=discord.ButtonStyle.primary)
    async def toggle_brief(self, interaction, button):
        _mission_state["daily_brief"]["enabled"] = \
            not _mission_state["daily_brief"]["enabled"]
        _mission_state["daily_brief"]["channel_id"] = interaction.channel_id
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="🔍 Toggle Activity Scan", style=discord.ButtonStyle.secondary)
    async def toggle_activity(self, interaction, button):
        _mission_state["activity_scan"]["enabled"] = \
            not _mission_state["activity_scan"]["enabled"]
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="⛽ Toggle Share Alerts", style=discord.ButtonStyle.secondary)
    async def toggle_share(self, interaction, button):
        _mission_state["share_alerts"]["enabled"] = \
            not _mission_state["share_alerts"]["enabled"]
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶ Run All Now", style=discord.ButtonStyle.green)
    async def run_all(self, interaction, button):
        await interaction.response.send_message(
            "⚙️ Running all active AERION automation tasks...", ephemeral=True)
        await _run_mission_tasks(interaction.channel)

    @discord.ui.button(label="⏹ Disable All", style=discord.ButtonStyle.red)
    async def disable_all(self, interaction, button):
        for key in _mission_state:
            if isinstance(_mission_state[key], dict) and "enabled" in _mission_state[key]:
                _mission_state[key]["enabled"] = False
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

async def _run_mission_tasks(channel=None):
    """Execute all enabled mission tasks."""
    results = []

    # Daily brief task
    if _mission_state["daily_brief"]["enabled"]:
        ch_id = _mission_state["daily_brief"]["channel_id"]
        ch    = _bot.get_channel(ch_id) if ch_id else channel
        if ch:
            embed = discord.Embed(
                title="📰 AERION DAILY INTELLIGENCE BRIEF",
                color=0x00d4ff,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="🕐 Generated",
                value=_now_ist().strftime("%d %b %Y  %I:%M %p IST"),
                inline=False)
            embed.add_field(name="System Status",
                value="✅ AERION Online | ✅ Portal Connected | ✅ AI Active",
                inline=False)
            embed.set_footer(text=f"{FOOTER}")
            await ch.send(embed=embed)
            results.append("✅ Daily brief posted")

    return results

async def _cmd_mission(ctx):
    await ctx.defer()
    if not await _gate(ctx): return
    if not ctx.author.guild_permissions.manage_guild:
        return await ctx.send("❌ Admin only.", ephemeral=True)
    view  = _MissionControlView(ctx)
    embed = view._build_embed()
    await ctx.send(embed=embed, view=view)

# ─────────────────────────────────────────────────────────
#  BACKGROUND AUTO-LOOP
# ─────────────────────────────────────────────────────────
async def _alliance_auto_loop():
    await _bot.wait_until_ready()
    print("[ALLIANCE] Auto-loop started")
    last_activity_run = None

    while not _bot.is_closed():
        await asyncio.sleep(60)
        now = _now_ist()

        # Daily brief at configured time
        if _mission_state["daily_brief"]["enabled"]:
            brief_day = _mission_state.get("last_brief_day")
            today_str = now.date().isoformat()
            brief_time = _mission_state["daily_brief"].get("time","09:00")
            try:
                target_h, target_m = map(int, brief_time.split(":"))
            except: target_h, target_m = 9, 0

            if (now.hour == target_h and now.minute < 5
                    and brief_day != today_str):
                _mission_state["last_brief_day"] = today_str
                ch_id = _mission_state["daily_brief"]["channel_id"]
                ch    = _bot.get_channel(ch_id) if ch_id else None
                if ch:
                    await _run_mission_tasks(ch)
                    print("[ALLIANCE] Daily brief posted")

        # Activity scan loop
        if _mission_state["activity_scan"]["enabled"]:
            interval_h = _mission_state["activity_scan"].get("interval_h", 24)
            if (last_activity_run is None or
                    (_now_ist()-last_activity_run).total_seconds()/3600 >= interval_h):
                last_activity_run = _now_ist()
                # Run alerts for all configured guilds
                for guild_id, cfg in _alert_configs.items():
                    if not cfg.get("enabled"): continue
                    ch = _bot.get_channel(cfg.get("channel_id",0))
                    if not ch: continue
                    print(f"[ALLIANCE] Auto activity scan for {cfg.get('alliance')}")

# ─────────────────────────────────────────────────────────
#  REGISTER ALL COMMANDS
# ─────────────────────────────────────────────────────────
def register_alliance(bot_instance, groq_client, supa_get, supa_post,
                      supa_patch, check_member_fn=None):
    global _bot, _groq, _supa_get, _supa_post, _supa_patch, _check_member
    _bot          = bot_instance
    _groq         = groq_client
    _supa_get     = supa_get
    _supa_post    = supa_post
    _supa_patch   = supa_patch
    _check_member = check_member_fn

    bot_instance.loop.create_task(_alliance_auto_loop())
    print("[ALLIANCE] Background loop started")

    @bot_instance.hybrid_command(
        name="allianceintel",
        description="Complete alliance health, activity and performance analysis"
    )
    @app_commands.describe(alliance="Alliance name to analyse")
    async def allianceintel(ctx, *, alliance: str):
        await _cmd_allianceintel(ctx, alliance)

    @bot_instance.hybrid_command(
        name="activityaudit",
        description="Scan alliance members — identify Active, At-Risk and Inactive players"
    )
    @app_commands.describe(
        alliance="Alliance name",
        days_threshold="Days without activity to flag (default 3)"
    )
    async def activityaudit(ctx, alliance: str, days_threshold: int = 3):
        await _cmd_activityaudit(ctx, alliance, days_threshold)

    @bot_instance.hybrid_command(
        name="activityalert",
        description="Automatically DM inactive alliance members via Discord"
    )
    @app_commands.describe(
        alliance="Alliance name",
        days="Inactivity threshold in days (default 5)",
        action="notify = send DMs now | status = check config | off = disable"
    )
    async def activityalert(ctx, alliance: str,
                            days: int = 5, action: str = "notify"):
        await _cmd_activityalert(ctx, alliance, days, action)

    @bot_instance.hybrid_command(
        name="mission",
        description="Central Mission Control — configure AERION's automated operations"
    )
    async def mission(ctx):
        await _cmd_mission(ctx)

    print("[ALLIANCE] Commands ready: /allianceintel /activityaudit /activityalert /mission")
