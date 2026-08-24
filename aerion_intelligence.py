# =========================================================
#  aerion_intelligence.py  —  AERION Intelligence Suite
#  /decide  /scenario  /playerintel  /powerrank  /battle  /rising
#
#  Integration in bot1.py:
#    from aerion_intelligence import register_intelligence
#    # in on_ready():
#    register_intelligence(bot, groq, supabase_get, check_membership)
# =========================================================

import asyncio, json, re
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
import pytz

_IST = pytz.timezone("Asia/Kolkata")

# ── Injected refs ──────────────────────────────────────────
_bot            = None
_groq           = None
_supabase_get   = None
_check_member   = None   # check_membership from aerion_membership

# ── Branding ───────────────────────────────────────────────
BOT_NAME    = "AERION"
BOT_VER     = "V3 ALPHA"
FOOTER      = f"{BOT_NAME} Intelligence Engine • {BOT_VER}"
MODEL       = "openai/gpt-oss-120b"

def _now_ist(): return datetime.now(_IST)
def _ts():      return _now_ist().strftime("%d %b %Y  %I:%M %p IST")

# ── AI call ────────────────────────────────────────────────
async def _ai(system: str, user: str, max_tokens=800) -> str:
    try:
        resp = await asyncio.to_thread(
            _groq.chat.completions.create,
            model=MODEL,
            max_tokens=max_tokens,
            temperature=0.6,
            messages=[
                {"role":"system","content":system},
                {"role":"user",  "content":user},
            ]
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ AI unavailable: {e}"

# ── Fetch player data from Supabase ───────────────────────
async def _player_data(discord_id: str = None, sts_id: str = None) -> dict | None:
    try:
        if discord_id:
            rows = await _supabase_get("share_users",{
                "discord_id":f"eq.{discord_id}",
                "select":"sts_id,name,airline,alliance,aero_points,contribution_points"
            })
        elif sts_id:
            rows = await _supabase_get("share_users",{
                "sts_id":f"eq.{sts_id}",
                "select":"sts_id,name,airline,alliance,aero_points,contribution_points"
            })
        else:
            return None
        return rows[0] if rows else None
    except: return None

async def _player_entries(sts_id: str, limit=30) -> list:
    try:
        rows = await _supabase_get("share_entries",{
            "sts_id": f"eq.{sts_id}",
            "select": "value,created_at,alliance",
            "order":  "created_at.desc",
            "limit":  str(limit)
        })
        return rows or []
    except: return []

async def _all_entries(limit=500) -> list:
    try:
        rows = await _supabase_get("share_entries",{
            "select":"sts_id,value,created_at,alliance",
            "order": "created_at.desc",
            "limit": str(limit)
        })
        return rows or []
    except: return []

async def _all_players() -> list:
    try:
        rows = await _supabase_get("share_users",{
            "select":"sts_id,name,airline,alliance,aero_points,contribution_points"
        })
        return rows or []
    except: return []

def _parse_val(v):
    try: return float(v)
    except: return 0.0

def _fmt(v):
    v = float(v)
    if v >= 1e9: return f"${v/1e9:.3f}B"
    if v >= 1e6: return f"${v/1e6:.2f}M"
    if v >= 1e3: return f"${v/1e3:.1f}K"
    return f"${v:,.0f}"

def _ist_day(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z","+00:00"))\
               .astimezone(_IST).strftime("%Y-%m-%d")
    except: return "?"

# ──────────────────────────────────────────────────────────
#  PLAYER STATS CALCULATOR
# ──────────────────────────────────────────────────────────
def _calc_stats(entries: list) -> dict:
    """Calculate comprehensive stats from share_entries."""
    if not entries:
        return {}
    vals      = [_parse_val(e["value"]) for e in entries]
    days      = list({_ist_day(e["created_at"]) for e in entries})
    avg       = sum(vals)/len(vals)
    mx        = max(vals)
    mn        = min(vals)
    latest    = vals[0] if vals else 0
    # 7-day growth
    now_ist   = _now_ist()
    week_vals = [_parse_val(e["value"]) for e in entries
                 if (now_ist - datetime.fromisoformat(
                     e["created_at"].replace("Z","+00:00")
                 ).astimezone(_IST)).days <= 7]
    growth_7d = 0.0
    if len(week_vals) >= 2:
        growth_7d = ((week_vals[0]-week_vals[-1])/week_vals[-1]*100
                     if week_vals[-1] else 0)
    # Streak
    streak = 0
    check  = now_ist.date()
    for d in sorted(days, reverse=True):
        try:
            dd = datetime.strptime(d,"%Y-%m-%d").date()
            if dd == check: streak+=1; check -= timedelta(days=1)
            else: break
        except: pass
    # Consistency
    if entries:
        first = datetime.fromisoformat(
            entries[-1]["created_at"].replace("Z","+00:00")).astimezone(_IST).date()
        total_days = max((_now_ist().date()-first).days+1, 1)
        consistency = len(days)/total_days*100
    else:
        consistency = 0

    return {
        "entries":     len(entries),
        "days_active": len(days),
        "avg":         avg,
        "max":         mx,
        "min":         mn,
        "latest":      latest,
        "growth_7d":   growth_7d,
        "streak":      streak,
        "consistency": consistency,
    }

# ─────────────────────────────────────────────────────────
#  GATE CHECK
# ─────────────────────────────────────────────────────────
async def _gate(ctx) -> bool:
    """Check membership + send error if not active. Returns True if OK."""
    if not _check_member:
        return True   # membership module not loaded
    status = await _check_member(str(ctx.author.id))
    if not status["linked"]:
        await ctx.send(
            "❌ Link your Discord to the AERO portal first with `/link <code>`.",
            ephemeral=True)
        return False
    if not status["has_access"]:
        cost = 1000 if status["is_new"] else 100
        await ctx.send(
            f"🔒 **AERION Membership Required**\n"
            f"Use `/subscribe` to activate ({cost:,} AERO Points).",
            ephemeral=True)
        return False
    return True

# =========================================================
#  /decide  —  AI analyses your data, recommends next move
# =========================================================
async def _cmd_decide(ctx, question: str):
    await ctx.defer()
    if not await _gate(ctx): return

    player = await _player_data(discord_id=str(ctx.author.id))
    if not player:
        return await ctx.send(
            "❌ No portal profile found. Link your account with `/link <code>`.")

    entries = await _player_entries(player["sts_id"], limit=20)
    stats   = _calc_stats(entries)

    context = (
        f"Player: {player.get('name')} | Airline: {player.get('airline')} | "
        f"Alliance: {player.get('alliance')}\n"
        f"AERO Points: {player.get('aero_points',0):,} | "
        f"Contribution: {player.get('contribution_points',0):,}\n"
        f"Share Stats: latest={_fmt(stats.get('latest',0))}, "
        f"avg={_fmt(stats.get('avg',0))}, "
        f"7d growth={stats.get('growth_7d',0):.1f}%, "
        f"streak={stats.get('streak',0)}d, "
        f"consistency={stats.get('consistency',0):.1f}%"
    )

    system = (
        f"You are {BOT_NAME}, an advanced AM4 aviation intelligence AI. "
        "Analyse the player's data and give a clear, actionable recommendation. "
        "Be specific, data-driven and concise. Max 3 key points."
    )
    user = f"Player data:\n{context}\n\nQuestion: {question}"

    thinking_msg = await ctx.send("🧠 **AERION** is analysing your data...")
    answer = await _ai(system, user, max_tokens=600)

    embed = discord.Embed(
        title="🧠 AERION DECIDE",
        color=0x00d4ff
    )
    embed.add_field(name="❓ Question", value=question, inline=False)
    embed.add_field(name="📊 Your Profile",
        value=(
            f"Airline: **{player.get('airline','?')}** | "
            f"Alliance: **{player.get('alliance','?')}**\n"
            f"Latest: {_fmt(stats.get('latest',0))} | "
            f"7d Growth: {stats.get('growth_7d',0):+.1f}% | "
            f"Streak: {stats.get('streak',0)}d"
        ), inline=False)
    embed.add_field(name="🤖 AERION Recommendation", value=answer[:1020], inline=False)
    embed.set_footer(text=f"{FOOTER} • {_ts()}")
    await thinking_msg.edit(content=None, embed=embed)

# =========================================================
#  /scenario  —  Simulate strategy before executing
# =========================================================
async def _cmd_scenario(ctx, scenario: str):
    await ctx.defer()
    if not await _gate(ctx): return

    player  = await _player_data(discord_id=str(ctx.author.id))
    entries = await _player_entries(player["sts_id"] if player else "", 20) if player else []
    stats   = _calc_stats(entries)

    context = ""
    if player:
        context = (
            f"Player: {player.get('name')} | "
            f"Airline: {player.get('airline')} | "
            f"Alliance: {player.get('alliance')}\n"
            f"Current avg share: {_fmt(stats.get('avg',0))} | "
            f"Growth: {stats.get('growth_7d',0):+.1f}% (7d) | "
            f"Points: {player.get('aero_points',0):,}"
        )

    system = (
        f"You are {BOT_NAME}, an AM4 strategy simulation engine. "
        "Analyse the scenario, list pros/cons, estimate outcome, "
        "and give a clear recommendation. Be data-driven and concise. "
        "Structure: Scenario Analysis → Pros → Cons → Estimated Outcome → Verdict."
    )
    user = (
        f"{'Player context:\n' + context + chr(10) if context else ''}"
        f"Scenario to simulate: {scenario}"
    )

    msg = await ctx.send("⚙️ **AERION** simulating scenario...")
    result = await _ai(system, user, max_tokens=700)

    embed = discord.Embed(
        title="🔮 AERION SCENARIO SIMULATOR",
        color=0xa855f7
    )
    embed.add_field(name="📋 Scenario", value=scenario[:512], inline=False)
    if context:
        embed.add_field(name="👤 Your Profile",
            value=f"Airline: **{player.get('airline','?')}** | "
                  f"Alliance: **{player.get('alliance','?')}**",
            inline=False)
    embed.add_field(name="🔮 Simulation Result", value=result[:1020], inline=False)
    embed.set_footer(text=f"{FOOTER} • {_ts()}")
    await msg.edit(content=None, embed=embed)

# =========================================================
#  /playerintel  —  Complete player profile & intelligence
# =========================================================
async def _cmd_playerintel(ctx, sts_id: str = None):
    await ctx.defer()
    if not await _gate(ctx): return

    if sts_id:
        player = await _player_data(sts_id=sts_id.strip().upper())
    else:
        player = await _player_data(discord_id=str(ctx.author.id))

    if not player:
        return await ctx.send(
            "❌ Player not found. Link your account or provide a valid STS ID.")

    sid     = player["sts_id"]
    entries = await _player_entries(sid, limit=30)
    stats   = _calc_stats(entries)

    if not stats:
        return await ctx.send(f"❌ No share history found for `{sid}`.")

    # Rank among all players by latest value
    all_entries = await _all_entries(limit=500)
    latest_per  = {}
    for e in all_entries:
        s = e["sts_id"]
        if s not in latest_per:
            latest_per[s] = _parse_val(e["value"])
    sorted_players = sorted(latest_per.values(), reverse=True)
    try:
        rank = sorted_players.index(stats["latest"]) + 1
    except ValueError:
        rank = "?"
    total = len(sorted_players)

    # AI intel
    context = (
        f"Player: {player.get('name')} | Airline: {player.get('airline')} | "
        f"Alliance: {player.get('alliance')}\n"
        f"Latest: {_fmt(stats['latest'])} | Avg: {_fmt(stats['avg'])} | "
        f"Max: {_fmt(stats['max'])} | 7d Growth: {stats['growth_7d']:+.1f}%\n"
        f"Streak: {stats['streak']}d | Consistency: {stats['consistency']:.1f}% | "
        f"Alliance Rank: #{rank}/{total}\n"
        f"AERO Points: {player.get('aero_points',0):,} | "
        f"Contribution: {player.get('contribution_points',0):,}"
    )
    system = (
        f"You are {BOT_NAME}. Write a sharp player intelligence report. "
        "Include: Performance tier, Strengths, Risk areas, Growth trend, "
        "1 key recommendation. Be concise (3-4 lines)."
    )
    ai_intel = await _ai(system, context, max_tokens=400)

    # Consistency rank
    def _cons_label(c):
        if c >= 90: return "🏆 Legend"
        if c >= 75: return "💎 Diamond"
        if c >= 60: return "🥇 Gold"
        if c >= 40: return "🥈 Silver"
        return "🥉 Bronze"

    color = 0x00ff88 if stats["growth_7d"] >= 0 else 0xff4757
    embed = discord.Embed(
        title=f"🔍 PLAYER INTEL — {player.get('name','?')}",
        color=color
    )
    embed.add_field(name="✈️ Profile",
        value=(
            f"**Airline  :** {player.get('airline','?')}\n"
            f"**Alliance :** {player.get('alliance','?')}\n"
            f"**STS ID   :** `{sid}`"
        ), inline=True)
    embed.add_field(name="📊 Share Stats",
        value=(
            f"**Latest  :** {_fmt(stats['latest'])}\n"
            f"**Average :** {_fmt(stats['avg'])}\n"
            f"**All-Time:** {_fmt(stats['max'])}"
        ), inline=True)
    embed.add_field(name="📈 Performance",
        value=(
            f"**7d Growth   :** {stats['growth_7d']:+.1f}%\n"
            f"**Streak      :** 🔥 {stats['streak']} day(s)\n"
            f"**Consistency :** {stats['consistency']:.1f}% {_cons_label(stats['consistency'])}"
        ), inline=True)
    embed.add_field(name="🏅 Alliance Rank",
        value=f"**#{rank}** out of **{total}** players",
        inline=True)
    embed.add_field(name="💰 AERO",
        value=(
            f"**Points      :** {player.get('aero_points',0):,}\n"
            f"**Contribution:** {player.get('contribution_points',0):,}"
        ), inline=True)
    embed.add_field(name="🧠 AERION Intel", value=ai_intel[:1020], inline=False)
    embed.set_footer(text=f"{FOOTER} • {_ts()}")
    await ctx.send(embed=embed)

# =========================================================
#  /powerrank  —  Dynamic leaderboard with scoring formula
# =========================================================
async def _cmd_powerrank(ctx, top: int = 10):
    await ctx.defer()
    if not await _gate(ctx): return

    all_entries = await _all_entries(limit=500)
    all_players = await _all_players()
    player_map  = {p["sts_id"]: p for p in all_players}

    if not all_entries:
        return await ctx.send("❌ No share data available yet.")

    # Build per-player stats
    player_entries = {}
    for e in all_entries:
        sid = e["sts_id"]
        player_entries.setdefault(sid, []).append(e)

    scores = []
    for sid, entries in player_entries.items():
        s = _calc_stats(entries)
        p = player_map.get(sid, {})

        # Power Score formula:
        # 40% latest value (normalised later)
        # 25% 7d growth
        # 20% consistency
        # 15% streak
        raw_score = (
            _parse_val(s.get("latest",0)) * 0.40 +
            max(0, s.get("growth_7d",0)) * 1e6 * 0.25 +
            s.get("consistency",0) * 1e7 * 0.20 +
            s.get("streak",0) * 5e7 * 0.15
        )
        scores.append({
            "sts_id":      sid,
            "name":        p.get("name") or sid,
            "airline":     p.get("airline","?"),
            "alliance":    p.get("alliance","?"),
            "raw_score":   raw_score,
            "latest":      s.get("latest",0),
            "growth_7d":   s.get("growth_7d",0),
            "consistency": s.get("consistency",0),
            "streak":      s.get("streak",0),
        })

    # Normalise scores to 0-1000
    if scores:
        max_raw = max(s["raw_score"] for s in scores) or 1
        for s in scores:
            s["power_score"] = int(s["raw_score"] / max_raw * 1000)

    scores.sort(key=lambda x: x["power_score"], reverse=True)
    top_n = scores[:min(top, 15)]

    medals = ["🥇","🥈","🥉"]
    lines  = []
    for i, s in enumerate(top_n, 1):
        medal = medals[i-1] if i<=3 else f"`#{i}`"
        trend = "📈" if s["growth_7d"] >= 0 else "📉"
        lines.append(
            f"{medal} **{s['name']}** — `{s['power_score']}/1000`\n"
            f"　{_fmt(s['latest'])} {trend}{s['growth_7d']:+.1f}% "
            f"| {s['consistency']:.0f}% consistent | 🔥{s['streak']}d"
        )

    embed = discord.Embed(
        title=f"⚡ AERION POWER RANK — Top {len(top_n)}",
        description="\n\n".join(lines),
        color=0xf39c12
    )
    embed.set_footer(text=f"Score = 40% Value + 25% Growth + 20% Consistency + 15% Streak • {FOOTER}")
    await ctx.send(embed=embed)

# =========================================================
#  /battle  —  Head-to-head comparison
# =========================================================
async def _cmd_battle(ctx, sts1: str, sts2: str):
    await ctx.defer()
    if not await _gate(ctx): return

    sts1 = sts1.strip().upper()
    sts2 = sts2.strip().upper()

    p1 = await _player_data(sts_id=sts1)
    p2 = await _player_data(sts_id=sts2)
    if not p1: return await ctx.send(f"❌ Player `{sts1}` not found.")
    if not p2: return await ctx.send(f"❌ Player `{sts2}` not found.")

    e1 = await _player_entries(sts1, 30)
    e2 = await _player_entries(sts2, 30)
    s1 = _calc_stats(e1)
    s2 = _calc_stats(e2)

    if not s1: return await ctx.send(f"❌ No data for `{sts1}`.")
    if not s2: return await ctx.send(f"❌ No data for `{sts2}`.")

    n1 = p1.get("name") or sts1
    n2 = p2.get("name") or sts2

    # Compare categories
    def _cmp(v1, v2, higher=True):
        if higher:
            return ("🟢","🔴") if v1 > v2 else ("🔴","🟢") if v2 > v1 else ("🟡","🟡")
        else:
            return ("🟢","🔴") if v1 < v2 else ("🔴","🟢") if v2 < v1 else ("🟡","🟡")

    cats = [
        ("Latest Value",   s1["latest"],      s2["latest"],      _fmt,              True),
        ("Average",        s1["avg"],          s2["avg"],         _fmt,              True),
        ("All-Time High",  s1["max"],          s2["max"],         _fmt,              True),
        ("7d Growth",      s1["growth_7d"],    s2["growth_7d"],   lambda x:f"{x:+.1f}%", True),
        ("Consistency",    s1["consistency"],  s2["consistency"], lambda x:f"{x:.1f}%",   True),
        ("Streak",         s1["streak"],       s2["streak"],      lambda x:f"{x}d",       True),
        ("AERO Points",    p1.get("aero_points",0), p2.get("aero_points",0), lambda x:f"{x:,}", True),
    ]

    p1_wins = p2_wins = 0
    rows = []
    for cat, v1, v2, fmt_fn, higher in cats:
        c1, c2 = _cmp(v1, v2, higher)
        if c1 == "🟢": p1_wins += 1
        elif c2 == "🟢": p2_wins += 1
        rows.append(f"`{cat:<16}` {c1} {fmt_fn(v1):<14} vs {fmt_fn(v2):<14} {c2}")

    winner = n1 if p1_wins > p2_wins else (n2 if p2_wins > p1_wins else "DRAW")
    w_color = 0x00ff88 if winner != "DRAW" else 0xffa502

    # AI verdict
    context = (
        f"{n1}: latest={_fmt(s1['latest'])}, avg={_fmt(s1['avg'])}, "
        f"growth={s1['growth_7d']:+.1f}%, streak={s1['streak']}d\n"
        f"{n2}: latest={_fmt(s2['latest'])}, avg={_fmt(s2['avg'])}, "
        f"growth={s2['growth_7d']:+.1f}%, streak={s2['streak']}d"
    )
    verdict = await _ai(
        f"You are {BOT_NAME}. Give a 2-line battle verdict comparing these two AM4 players.",
        context, max_tokens=150
    )

    embed = discord.Embed(
        title=f"⚔️ BATTLE: {n1} vs {n2}",
        color=w_color
    )
    embed.add_field(name="📊 Head-to-Head",
        value="```\n" + "\n".join(rows) + "\n```",
        inline=False)
    embed.add_field(name="🏆 Winner",
        value=f"**{winner}** ({p1_wins}-{p2_wins})",
        inline=True)
    embed.add_field(name="🤖 AERION Verdict", value=verdict[:512], inline=False)
    embed.set_footer(text=f"{FOOTER} • {_ts()}")
    await ctx.send(embed=embed)

# =========================================================
#  /rising  —  Fastest growing players
# =========================================================
async def _cmd_rising(ctx, top: int = 5):
    await ctx.defer()
    if not await _gate(ctx): return

    all_entries = await _all_entries(limit=500)
    all_players = await _all_players()
    player_map  = {p["sts_id"]: p for p in all_players}

    if not all_entries:
        return await ctx.send("❌ No share data available.")

    player_entries = {}
    for e in all_entries:
        player_entries.setdefault(e["sts_id"], []).append(e)

    rising = []
    for sid, entries in player_entries.items():
        s = _calc_stats(entries)
        if s.get("growth_7d",0) <= 0: continue
        if s.get("entries",0) < 3: continue
        p = player_map.get(sid, {})
        rising.append({
            "sts_id":    sid,
            "name":      p.get("name") or sid,
            "airline":   p.get("airline","?"),
            "alliance":  p.get("alliance","?"),
            "growth_7d": s["growth_7d"],
            "latest":    s["latest"],
            "streak":    s["streak"],
        })

    rising.sort(key=lambda x: x["growth_7d"], reverse=True)
    top_n = rising[:min(top, 10)]

    if not top_n:
        return await ctx.send("📊 No rising players found in the last 7 days.")

    lines = []
    for i, r in enumerate(top_n, 1):
        lines.append(
            f"**{i}. {r['name']}** ({r['airline']})\n"
            f"　📈 +{r['growth_7d']:.1f}% (7d) | "
            f"Latest: {_fmt(r['latest'])} | 🔥 {r['streak']}d streak"
        )

    embed = discord.Embed(
        title=f"🚀 RISING PLAYERS — Top {len(top_n)} Fastest Growing",
        description="\n\n".join(lines),
        color=0x00ff88
    )
    embed.set_footer(text=f"Based on 7-day growth rate • {FOOTER} • {_ts()}")
    await ctx.send(embed=embed)

# =========================================================
#  REGISTER ALL COMMANDS
# =========================================================
def register_intelligence(bot_instance, groq_client, supa_get, check_member_fn=None):
    global _bot, _groq, _supabase_get, _check_member
    _bot          = bot_instance
    _groq         = groq_client
    _supabase_get = supa_get
    _check_member = check_member_fn
    print("[AERION INTEL] Registering intelligence commands...")

    @bot_instance.hybrid_command(
        name="decide",
        description="AERION analyses your airline data and recommends the best decision"
    )
    @app_commands.describe(question="What decision do you need help with?")
    async def decide(ctx, *, question: str):
        await _cmd_decide(ctx, question)

    @bot_instance.hybrid_command(
        name="scenario",
        description="Simulate a strategy before making a move"
    )
    @app_commands.describe(scenario="Describe the scenario or strategy to simulate")
    async def scenario(ctx, *, scenario: str):
        await _cmd_scenario(ctx, scenario)

    @bot_instance.hybrid_command(
        name="playerintel",
        description="Complete performance profile for any player"
    )
    @app_commands.describe(sts_id="STS ID of the player (leave blank for yourself)")
    async def playerintel(ctx, sts_id: str = None):
        await _cmd_playerintel(ctx, sts_id)

    @bot_instance.hybrid_command(
        name="powerrank",
        description="Dynamic player ranking based on performance, growth & consistency"
    )
    @app_commands.describe(top="How many players to show (default 10, max 15)")
    async def powerrank(ctx, top: int = 10):
        top = max(3, min(top, 15))
        await _cmd_powerrank(ctx, top)

    @bot_instance.hybrid_command(
        name="battle",
        description="Compare two players across all key metrics"
    )
    @app_commands.describe(
        sts1="First player STS ID",
        sts2="Second player STS ID"
    )
    async def battle(ctx, sts1: str, sts2: str):
        await _cmd_battle(ctx, sts1, sts2)

    @bot_instance.hybrid_command(
        name="rising",
        description="Discover the fastest-growing players in the last 7 days"
    )
    @app_commands.describe(top="How many players to show (default 5)")
    async def rising(ctx, top: int = 5):
        await _cmd_rising(ctx, top)

    print("[AERION INTEL] Commands ready: /decide /scenario /playerintel /powerrank /battle /rising")
