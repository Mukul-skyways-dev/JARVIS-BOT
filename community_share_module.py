"""Community share tracking for players who are not portal members.

This module deliberately uses its own Supabase tables and never reads or writes
the portal member tables used by share_module.py.
"""

from __future__ import annotations

import io
import math
from datetime import date, datetime, timedelta, timezone

import discord
from discord import app_commands
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pytz


COMMUNITY_PROFILE_TABLE = "community_share_profiles"
COMMUNITY_ENTRY_TABLE = "community_share_entries"
IST = pytz.timezone("Asia/Kolkata")

_BG = "#080d18"
_PANEL = "#151e32"
_GRID = "#33415f"
_TEXT = "#dce7ff"
_MUTED = "#8e9ac0"
_ACCENT = "#00d4ff"
_GREEN = "#00ff88"
_RED = "#ff5964"
_PURPLE = "#a855f7"


def _now_ist() -> datetime:
    return datetime.now(IST)


def _today() -> date:
    return _now_ist().date()


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            ).astimezone(IST).date()
        except (TypeError, ValueError):
            return None


def _entry_date(entry: dict) -> date | None:
    return _parse_date(entry.get("entry_date") or entry.get("created_at"))


def _value(entry: dict) -> float:
    try:
        return float(entry.get("share_value", entry.get("value", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_money(raw: str) -> float | None:
    """Parse 5.2B, 500M, 12.5K, or a plain number."""
    try:
        text = str(raw).strip().upper().replace(",", "").replace("$", "")
        multiplier = 1
        if text.endswith("B"):
            multiplier, text = 1_000_000_000, text[:-1]
        elif text.endswith("M"):
            multiplier, text = 1_000_000, text[:-1]
        elif text.endswith("K"):
            multiplier, text = 1_000, text[:-1]
        value = float(text) * multiplier
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def _money(value: float) -> str:
    value = float(value or 0)
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def _signed_pct(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{'▲' if value >= 0 else '▼'} {abs(value):.1f}%"


def _profile_name(profile: dict) -> str:
    return profile.get("discord_name") or profile.get("airline_name") or "Player"


def _sorted_entries(entries: list[dict]) -> list[dict]:
    return sorted(
        [entry for entry in entries if _entry_date(entry) and _value(entry) > 0],
        key=lambda entry: _entry_date(entry),
    )


def _stats(entries: list[dict]) -> dict:
    ordered = _sorted_entries(entries)
    if not ordered:
        return {
            "count": 0,
            "days": 0,
            "latest": 0,
            "average": 0,
            "minimum": 0,
            "maximum": 0,
            "growth": None,
            "volatility": None,
            "avg_change": None,
            "consistency": 0,
            "streak": 0,
            "trend_per_day": None,
            "first_date": None,
            "latest_date": None,
        }

    values = np.array([_value(entry) for entry in ordered], dtype=float)
    dates = [_entry_date(entry) for entry in ordered]
    active_dates = set(dates)
    latest = float(values[-1])
    first = float(values[0])

    returns = [
        (values[index] - values[index - 1]) / values[index - 1] * 100
        for index in range(1, len(values))
        if values[index - 1] > 0
    ]
    avg_change = float(np.mean(np.abs(returns))) if returns else None
    volatility = float(np.std(returns)) if len(returns) >= 2 else None

    baseline = None
    target_day = dates[-1] - timedelta(days=7)
    for index in range(len(dates) - 1, -1, -1):
        if dates[index] <= target_day:
            baseline = float(values[index])
            break
    if baseline is None and len(values) >= 2:
        baseline = first
    growth = ((latest - baseline) / baseline * 100) if baseline else None

    span_days = max((dates[-1] - dates[0]).days + 1, 1)
    consistency = len(active_dates) / span_days * 100
    streak = 0
    cursor = _today()
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)

    trend_per_day = None
    if len(values) >= 2:
        x = np.array([(current - dates[0]).days for current in dates], dtype=float)
        slope = float(np.polyfit(x, values, 1)[0])
        trend_per_day = slope / first * 100 if first else None

    return {
        "count": len(ordered),
        "days": len(active_dates),
        "latest": latest,
        "average": float(np.mean(values)),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "growth": growth,
        "volatility": volatility,
        "avg_change": avg_change,
        "consistency": consistency,
        "streak": streak,
        "trend_per_day": trend_per_day,
        "first_date": dates[0],
        "latest_date": dates[-1],
    }


def _figure(w: float = 11, h: float = 5):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PANEL)
    ax.tick_params(colors=_MUTED)
    ax.xaxis.label.set_color(_MUTED)
    ax.yaxis.label.set_color(_MUTED)
    ax.title.set_color(_TEXT)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
    ax.grid(alpha=0.22, linestyle=":", color=_GRID)
    return fig, ax


def _png(fig) -> io.BytesIO:
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=130,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
    )
    buffer.seek(0)
    plt.close(fig)
    return buffer


def _chart(entries: list[dict], profile: dict, days: int | None = None):
    ordered = _sorted_entries(entries)
    if days:
        cutoff = _today() - timedelta(days=max(days - 1, 0))
        ordered = [entry for entry in ordered if _entry_date(entry) >= cutoff]

    fig, ax = _figure()
    if not ordered:
        ax.set_title("No share entries yet")
        return _png(fig)

    dates = [_entry_date(entry) for entry in ordered]
    values = [_value(entry) for entry in ordered]
    labels = [item.strftime("%d %b") for item in dates]
    ax.plot(
        labels,
        values,
        color=_ACCENT,
        linewidth=2.6,
        marker="o",
        markersize=5,
        label="Daily share value",
        zorder=3,
    )
    if len(values) >= 3:
        window = min(7, len(values))
        rolling = np.convolve(
            np.array(values, dtype=float),
            np.ones(window) / window,
            mode="valid",
        )
        ax.plot(
            labels[window - 1:],
            rolling,
            color=_GREEN,
            linewidth=1.8,
            linestyle="--",
            label=f"{window}-entry average",
        )
    ax.fill_between(range(len(values)), values, alpha=0.09, color=_ACCENT)
    ax.set_title(f"{_profile_name(profile)} — Share Value Trend")
    ax.set_xlabel("Entry date")
    ax.set_ylabel("Share value")
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda value, _: _money(value))
    )
    ax.legend(facecolor=_PANEL, labelcolor=_TEXT)
    plt.xticks(rotation=35, color=_MUTED, fontsize=8)
    return _png(fig)


async def _get_profile(discord_id: str) -> dict | None:
    rows = await supabase_get(
        COMMUNITY_PROFILE_TABLE,
        {"discord_id": f"eq.{discord_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


async def _get_entries(profile_id: int, limit: int = 400) -> list[dict]:
    return await supabase_get(
        COMMUNITY_ENTRY_TABLE,
        {
            "profile_id": f"eq.{profile_id}",
            "select": "id,profile_id,entry_date,share_value,created_at",
            "order": "entry_date.asc",
            "limit": str(limit),
        },
    )


async def _get_all_profiles() -> list[dict]:
    return await supabase_get(
        COMMUNITY_PROFILE_TABLE,
        {
            "active": "eq.true",
            "select": "id,discord_id,discord_name,airline_name,alliance",
            "order": "discord_name.asc",
            "limit": "1000",
        },
    )


async def _get_all_entries(limit: int = 5000) -> list[dict]:
    return await supabase_get(
        COMMUNITY_ENTRY_TABLE,
        {
            "select": "id,profile_id,entry_date,share_value,created_at",
            "order": "entry_date.desc",
            "limit": str(limit),
        },
    )


def _stats_embed(profile: dict, entries: list[dict], title: str | None = None):
    stats = _stats(entries)
    growth = stats["growth"]
    color = _GREEN if growth is not None and growth >= 0 else _RED
    embed = discord.Embed(
        title=title or f"📊 Community Share Analysis — {_profile_name(profile)}",
        color=color,
    )
    embed.add_field(name="Airline", value=profile.get("airline_name", "—"), inline=True)
    embed.add_field(name="Alliance", value=profile.get("alliance", "—"), inline=True)
    embed.add_field(name="Entries", value=str(stats["count"]), inline=True)
    embed.add_field(name="Latest", value=_money(stats["latest"]), inline=True)
    embed.add_field(name="Average", value=_money(stats["average"]), inline=True)
    embed.add_field(name="All-time high", value=_money(stats["maximum"]), inline=True)
    embed.add_field(name="7d / baseline growth", value=_signed_pct(growth), inline=True)
    embed.add_field(
        name="Volatility",
        value="—" if stats["volatility"] is None else f"{stats['volatility']:.1f}%",
        inline=True,
    )
    embed.add_field(
        name="Avg daily movement",
        value="—" if stats["avg_change"] is None else f"{stats['avg_change']:.1f}%",
        inline=True,
    )
    embed.add_field(name="Consistency", value=f"{stats['consistency']:.1f}%", inline=True)
    embed.add_field(name="Current streak", value=f"🔥 {stats['streak']} day(s)", inline=True)
    embed.add_field(
        name="Trend/day",
        value="—" if stats["trend_per_day"] is None else _signed_pct(stats["trend_per_day"]),
        inline=True,
    )
    if stats["first_date"] and stats["latest_date"]:
        embed.add_field(
            name="Tracking window",
            value=f"{stats['first_date'].isoformat()} → {stats['latest_date'].isoformat()}",
            inline=False,
        )
    return embed


async def _send_analysis(ctx, profile: dict, entries: list[dict], days: int | None = None):
    embed = _stats_embed(profile, entries)
    chart = _chart(entries, profile, days=days)
    embed.set_image(url="attachment://community_share_trend.png")
    embed.set_footer(text="JARVIS • Community Share Tracking")
    await ctx.send(
        embed=embed,
        file=discord.File(chart, "community_share_trend.png"),
    )


@bot.hybrid_command(
    name="communityregister",
    description="Register your public AM4 share-tracking profile",
)
@app_commands.describe(
    discord_name="Name you want displayed in tracking results",
    airline_name="Your AM4 airline name",
    alliance="Your current AM4 alliance",
)
async def communityregister(
    ctx,
    discord_name: str,
    airline_name: str,
    alliance: str,
):
    await ctx.defer(ephemeral=True)
    discord_name = discord_name.strip()[:80]
    airline_name = airline_name.strip()[:120]
    alliance = alliance.strip()[:120]
    if not discord_name or not airline_name or not alliance:
        return await ctx.send("❌ All three profile fields are required.", ephemeral=True)

    payload = {
        "discord_id": str(ctx.author.id),
        "discord_name": discord_name,
        "airline_name": airline_name,
        "alliance": alliance,
        "active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        existing = await _get_profile(str(ctx.author.id))
        if existing:
            await supabase_patch(
                COMMUNITY_PROFILE_TABLE,
                {"id": f"eq.{existing['id']}"},
                payload,
            )
            action = "updated"
        else:
            await supabase_post(COMMUNITY_PROFILE_TABLE, payload)
            action = "created"
    except Exception as exc:
        print(f"[COMMUNITY SHARE] registration error: {exc}")
        return await ctx.send(
            "❌ Registration failed. Please try again in a moment.",
            ephemeral=True,
        )

    await ctx.send(
        f"✅ Community tracking profile **{action}**.\n"
        f"**{discord_name}** • {airline_name} • {alliance}\n\n"
        "Use `/communityshare` once per day to add your share value.",
        ephemeral=True,
    )


@bot.hybrid_command(
    name="communityshare",
    description="Submit your daily share value to community tracking",
)
@app_commands.describe(value="Share value, e.g. 5.2B, 500M, 1250000")
async def communityshare(ctx, value: str):
    await ctx.defer(ephemeral=True)
    try:
        profile = await _get_profile(str(ctx.author.id))
    except Exception as exc:
        print(f"[COMMUNITY SHARE] profile lookup error: {exc}")
        return await ctx.send("❌ Could not reach the tracking database.", ephemeral=True)
    if not profile:
        return await ctx.send(
            "❌ Register first with `/communityregister`.",
            ephemeral=True,
        )

    parsed = _parse_money(value)
    if parsed is None:
        return await ctx.send(
            "❌ Invalid value. Use formats like `5.2B`, `500M`, or `1250000`.",
            ephemeral=True,
        )

    today = _today().isoformat()
    try:
        existing = await supabase_get(
            COMMUNITY_ENTRY_TABLE,
            {
                "profile_id": f"eq.{profile['id']}",
                "entry_date": f"eq.{today}",
                "select": "id",
                "limit": "1",
            },
        )
    except Exception as exc:
        print(f"[COMMUNITY SHARE] daily duplicate check error: {exc}")
        return await ctx.send("❌ Could not verify today's entry.", ephemeral=True)
    if existing:
        return await ctx.send(
            f"⚠️ You already submitted today's value ({today}). "
            "You can submit again tomorrow.",
            ephemeral=True,
        )

    try:
        await supabase_post(
            COMMUNITY_ENTRY_TABLE,
            {
                "profile_id": profile["id"],
                "discord_id": str(ctx.author.id),
                "entry_date": today,
                "share_value": parsed,
            },
        )
        entries = await _get_entries(profile["id"])
    except Exception as exc:
        # The database unique constraint is the final race-condition guard.
        print(f"[COMMUNITY SHARE] entry insert error: {exc}")
        return await ctx.send(
            "❌ Today's entry could not be saved. It may already exist.",
            ephemeral=True,
        )

    stats = _stats(entries)
    await ctx.send(
        f"✅ **{_money(parsed)}** recorded for **{today}**.\n"
        f"Growth: **{_signed_pct(stats['growth'])}** • "
        f"Streak: **{stats['streak']} day(s)** • "
        f"Volatility: **{'—' if stats['volatility'] is None else f'{stats['volatility']:.1f}%'}**",
        ephemeral=True,
    )


@bot.hybrid_command(
    name="communityanalysis",
    description="View your community share analysis and trend chart",
)
@app_commands.describe(days="Chart window in days, from 7 to 365")
async def communityanalysis(ctx, days: int = 30):
    await ctx.defer()
    days = max(7, min(int(days or 30), 365))
    try:
        profile = await _get_profile(str(ctx.author.id))
        if not profile:
            return await ctx.send("❌ Register first with `/communityregister`.")
        entries = await _get_entries(profile["id"])
        if not entries:
            return await ctx.send("📭 No entries yet. Use `/communityshare` today.")
        await _send_analysis(ctx, profile, entries, days=days)
    except Exception as exc:
        print(f"[COMMUNITY SHARE] analysis error: {exc}")
        await ctx.send("❌ Could not build your analysis right now.")


@bot.hybrid_command(
    name="communityleaderboard",
    description="Show the community share leaderboard",
)
@app_commands.describe(alliance="Optional alliance filter")
async def communityleaderboard(ctx, alliance: str = None):
    await ctx.defer()
    try:
        profiles = await _get_all_profiles()
        entries = await _get_all_entries()
    except Exception as exc:
        print(f"[COMMUNITY SHARE] leaderboard error: {exc}")
        return await ctx.send("❌ Could not fetch community tracking data.")

    profile_map = {str(profile["id"]): profile for profile in profiles}
    latest = {}
    for entry in entries:
        key = str(entry.get("profile_id"))
        if key not in latest or _entry_date(entry) > _entry_date(latest[key]):
            latest[key] = entry

    rows = []
    for key, entry in latest.items():
        profile = profile_map.get(key)
        if not profile:
            continue
        if alliance and profile.get("alliance", "").lower() != alliance.lower():
            continue
        rows.append((profile, entry))
    rows.sort(key=lambda row: _value(row[1]), reverse=True)
    if not rows:
        return await ctx.send("📭 No community entries match that filter.")

    lines = []
    for index, (profile, entry) in enumerate(rows[:15], 1):
        medal = ["🥇", "🥈", "🥉"][index - 1] if index <= 3 else f"`#{index}`"
        lines.append(
            f"{medal} **{_profile_name(profile)}** — {_money(_value(entry))}\n"
            f"　{profile.get('airline_name', '—')} • {profile.get('alliance', '—')} "
            f"• {_entry_date(entry).isoformat()}"
        )

    title = "🏆 Community Share Leaderboard"
    if alliance:
        title += f" — {alliance}"
    embed = discord.Embed(title=title, description="\n\n".join(lines), color=0x00D4FF)
    embed.set_footer(text=f"Community tracking • {len(rows)} player(s)")
    await ctx.send(embed=embed)


@bot.hybrid_command(
    name="communitycompare",
    description="Compare two community tracking profiles",
)
@app_commands.describe(
    first_player="Displayed Discord name of the first player",
    second_player="Displayed Discord name of the second player",
)
async def communitycompare(ctx, first_player: str, second_player: str):
    await ctx.defer()
    try:
        profiles = await _get_all_profiles()
        entries = await _get_all_entries()
    except Exception as exc:
        print(f"[COMMUNITY SHARE] compare error: {exc}")
        return await ctx.send("❌ Could not fetch community tracking data.")

    def find_player(query: str):
        query = query.strip().lower()
        exact = [p for p in profiles if p.get("discord_name", "").lower() == query]
        if exact:
            return exact[0]
        matches = [p for p in profiles if query in p.get("discord_name", "").lower()]
        return matches[0] if len(matches) == 1 else None

    first = find_player(first_player)
    second = find_player(second_player)
    if not first or not second:
        return await ctx.send(
            "❌ I need one exact or unambiguous displayed Discord name for each player."
        )

    entry_map: dict[str, list[dict]] = {}
    for entry in entries:
        entry_map.setdefault(str(entry.get("profile_id")), []).append(entry)
    first_entries = entry_map.get(str(first["id"]), [])
    second_entries = entry_map.get(str(second["id"]), [])
    first_stats = _stats(first_entries)
    second_stats = _stats(second_entries)
    if not first_stats["count"] or not second_stats["count"]:
        return await ctx.send("❌ Both players need at least one share entry.")

    embed = discord.Embed(
        title=f"⚔️ {_profile_name(first)} vs {_profile_name(second)}",
        color=0x00D4FF,
    )
    embed.add_field(
        name=_profile_name(first),
        value=(
            f"Latest: {_money(first_stats['latest'])}\n"
            f"Average: {_money(first_stats['average'])}\n"
            f"Growth: {_signed_pct(first_stats['growth'])}\n"
            f"Volatility: {'—' if first_stats['volatility'] is None else f'{first_stats['volatility']:.1f}%'}"
        ),
        inline=True,
    )
    embed.add_field(
        name=_profile_name(second),
        value=(
            f"Latest: {_money(second_stats['latest'])}\n"
            f"Average: {_money(second_stats['average'])}\n"
            f"Growth: {_signed_pct(second_stats['growth'])}\n"
            f"Volatility: {'—' if second_stats['volatility'] is None else f'{second_stats['volatility']:.1f}%'}"
        ),
        inline=True,
    )

    fig, ax = _figure(11, 5)
    for profile, player_entries, color in (
        (first, first_entries, _ACCENT),
        (second, second_entries, _PURPLE),
    ):
        ordered = _sorted_entries(player_entries)
        labels = [_entry_date(entry).strftime("%d %b") for entry in ordered]
        ax.plot(
            labels,
            [_value(entry) for entry in ordered],
            label=_profile_name(profile),
            color=color,
            linewidth=2.2,
            marker="o",
            markersize=4,
        )
    ax.set_title("Community Share Comparison")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda value, _: _money(value)))
    ax.legend(facecolor=_PANEL, labelcolor=_TEXT)
    plt.xticks(rotation=35, color=_MUTED, fontsize=8)
    embed.set_image(url="attachment://community_compare.png")
    embed.set_footer(text="JARVIS • Community Share Tracking")
    await ctx.send(embed=embed, file=discord.File(_png(fig), "community_compare.png"))
