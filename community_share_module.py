"""Community share tracking for players who are not portal members.

This module is designed to be imported into your main bot file (e.g. bot1.py).
It uses its own Supabase tables:
  - community_share_profiles
  - community_share_entries

HOW TO USE IN YOUR MAIN BOT FILE:
---------------------------------
Option 1 (Recommended - identical to aerion_membership pattern):
    from community_share_module import register_community_share_commands

    # In your on_ready() or after bot initialization:
    register_community_share_commands(bot, supabase_get, supabase_post, supabase_patch)

Option 2 (Extension loader):
    await bot.load_extension("community_share_module")
"""

from __future__ import annotations

import asyncio
import io
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pytz
import requests

# ── Tables & Timezone ─────────────────────────────────────
COMMUNITY_PROFILE_TABLE = "community_share_profiles"
COMMUNITY_ENTRY_TABLE = "community_share_entries"
IST = pytz.timezone("Asia/Kolkata")

# ── Visual Theme ──────────────────────────────────────────
_BG = "#080d18"
_PANEL = "#151e32"
_GRID = "#33415f"
_TEXT = "#dce7ff"
_MUTED = "#8e9ac0"
_ACCENT = 0x00D4FF      # Cyan
_GREEN = 0x00FF88       # Mint Green
_RED = 0xFF5964         # Coral Red
_PURPLE = 0xA855F7      # Lavender
_GOLD = 0xFFD700        # Gold for ATH / 1st

# ── Injected or Internal References ───────────────────────
_bot: Optional[commands.Bot] = None
_supabase_get = None
_supabase_post = None
_supabase_patch = None
_commands_registered = False


# ──────────────────────────────────────────────────────────
#  INTERNAL SUPABASE REST FALLBACK
# ──────────────────────────────────────────────────────────
def _get_supa_headers() -> dict:
    key = os.getenv("SUPABASE_KEY", "")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def _default_supabase_get(table: str, params: dict):
    url = f"{os.getenv('SUPABASE_URL', '')}/rest/v1/{table}"
    resp = await asyncio.to_thread(
        requests.get,
        url,
        headers=_get_supa_headers(),
        params=params,
        timeout=12,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else []


async def _default_supabase_post(table: str, data: dict | list):
    url = f"{os.getenv('SUPABASE_URL', '')}/rest/v1/{table}"
    headers = _get_supa_headers()
    headers["Prefer"] = "return=representation"
    resp = await asyncio.to_thread(
        requests.post,
        url,
        headers=headers,
        json=data,
        timeout=12,
    )
    resp.raise_for_status()
    if resp.status_code in (200, 201) and resp.content:
        try:
            return resp.json()
        except Exception:
            return None
    return None


async def _default_supabase_patch(table: str, params: dict, data: dict):
    url = f"{os.getenv('SUPABASE_URL', '')}/rest/v1/{table}"
    headers = _get_supa_headers()
    headers["Prefer"] = "return=representation"
    resp = await asyncio.to_thread(
        requests.patch,
        url,
        headers=headers,
        params=params,
        json=data,
        timeout=12,
    )
    resp.raise_for_status()
    if resp.status_code in (200, 204) and resp.content:
        try:
            return resp.json()
        except Exception:
            return None
    return None


# Wrap Supabase calls with automatic fallback and safety
async def _db_get(table: str, params: dict) -> list[dict]:
    if _supabase_get is not None:
        try:
            res = await _supabase_get(table, params)
            return res if isinstance(res, list) else ([res] if res else [])
        except Exception as exc:
            print(f"[COMMUNITY DB] Injected get failed, trying fallback: {exc}")
    return await _default_supabase_get(table, params)


async def _db_post(table: str, data: dict) -> list[dict] | dict | None:
    if _supabase_post is not None:
        try:
            return await _supabase_post(table, data)
        except Exception as exc:
            # Check if it was just a 201 Created empty body JSONDecodeError
            if "JSONDecodeError" in type(exc).__name__:
                return [data]
            print(f"[COMMUNITY DB] Injected post failed, trying fallback: {exc}")
    return await _default_supabase_post(table, data)


async def _db_patch(table: str, params: dict, data: dict) -> list[dict] | dict | None:
    if _supabase_patch is not None:
        try:
            return await _supabase_patch(table, params, data)
        except Exception as exc:
            print(f"[COMMUNITY DB] Injected patch failed, trying fallback: {exc}")
    return await _default_supabase_patch(table, params, data)


# ──────────────────────────────────────────────────────────
#  HELPER FUNCTIONS (Time, Currency, Parsing)
# ──────────────────────────────────────────────────────────
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
    """Parse 5.2B, 500M, 12.5K, or plain number."""
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
    return f"{'▲ +' if value > 0 else ('▼ ' if value < 0 else '')}{value:.2f}%"


def _signed_diff(current: float, previous: float) -> str:
    diff = current - previous
    if diff == 0:
        return "$0.00 (0.00%)"
    pct = (diff / previous * 100) if previous > 0 else 0
    symbol = "▲ +" if diff > 0 else "▼ -"
    return f"{symbol}{_money(abs(diff))} ({pct:+.2f}%)"


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
            "latest": 0.0,
            "previous": 0.0,
            "average": 0.0,
            "minimum": 0.0,
            "maximum": 0.0,
            "growth": None,
            "volatility": None,
            "avg_change": None,
            "consistency": 0.0,
            "streak": 0,
            "trend_per_day": None,
            "first_date": None,
            "latest_date": None,
        }

    values = np.array([_value(entry) for entry in ordered], dtype=float)
    dates = [_entry_date(entry) for entry in ordered]
    active_dates = set(dates)
    latest = float(values[-1])
    previous = float(values[-2]) if len(values) >= 2 else latest
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
        "previous": previous,
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


# ──────────────────────────────────────────────────────────
#  CHART GENERATION (Matplotlib Dark Theme)
# ──────────────────────────────────────────────────────────
def _figure(w: float = 10, h: float = 4.6):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PANEL)
    ax.tick_params(colors=_MUTED)
    ax.xaxis.label.set_color(_MUTED)
    ax.yaxis.label.set_color(_MUTED)
    ax.title.set_color(_TEXT)
    for spine in ax.spines.values():
        spine.set_color(_GRID)
    ax.grid(alpha=0.25, linestyle=":", color=_GRID)
    return fig, ax


def _png(fig) -> io.BytesIO:
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=120,
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
        ax.set_title("No share entries recorded yet", color=_MUTED)
        return _png(fig)

    dates = [_entry_date(entry) for entry in ordered]
    values = [_value(entry) for entry in ordered]
    labels = [item.strftime("%d %b") for item in dates]

    ax.plot(
        labels,
        values,
        color="#00d4ff",
        linewidth=2.5,
        marker="o",
        markersize=5,
        label="Share value",
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
            color="#00ff88",
            linewidth=1.8,
            linestyle="--",
            label=f"{window}-day moving avg",
        )
    ax.fill_between(range(len(values)), values, alpha=0.12, color="#00d4ff")
    ax.set_title(f"{_profile_name(profile)} — Share Value Trend ({len(ordered)} entries)")
    ax.set_xlabel("Date (IST)")
    ax.set_ylabel("Share Value")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: _money(val)))
    ax.legend(facecolor=_PANEL, labelcolor=_TEXT, loc="upper left")
    plt.xticks(rotation=30, color=_MUTED, fontsize=8)
    return _png(fig)


# ──────────────────────────────────────────────────────────
#  DATABASE REPOSITORIES
# ──────────────────────────────────────────────────────────
async def _get_profile(discord_id: str) -> dict | None:
    rows = await _db_get(
        COMMUNITY_PROFILE_TABLE,
        {"discord_id": f"eq.{discord_id}", "select": "*", "limit": "1"},
    )
    return rows[0] if rows else None


async def _get_entries(profile_id: int, limit: int = 400) -> list[dict]:
    return await _db_get(
        COMMUNITY_ENTRY_TABLE,
        {
            "profile_id": f"eq.{profile_id}",
            "select": "id,profile_id,entry_date,share_value,created_at",
            "order": "entry_date.asc",
            "limit": str(limit),
        },
    )


async def _get_all_profiles() -> list[dict]:
    return await _db_get(
        COMMUNITY_PROFILE_TABLE,
        {
            "active": "eq.true",
            "select": "id,discord_id,discord_name,airline_name,alliance",
            "order": "discord_name.asc",
            "limit": "1000",
        },
    )


async def _get_all_entries(limit: int = 5000) -> list[dict]:
    return await _db_get(
        COMMUNITY_ENTRY_TABLE,
        {
            "select": "id,profile_id,entry_date,share_value,created_at",
            "order": "entry_date.desc",
            "limit": str(limit),
        },
    )


# ──────────────────────────────────────────────────────────
#  EMBED BUILDERS
# ──────────────────────────────────────────────────────────
def _stats_embed(profile: dict, entries: list[dict], title: str | None = None):
    stats = _stats(entries)
    growth = stats["growth"]
    color = _GREEN if growth is not None and growth >= 0 else _RED
    embed = discord.Embed(
        title=title or f"📊 Community Share Analysis — {_profile_name(profile)}",
        color=color,
    )
    embed.add_field(name="🆔 Profile ID", value=f"`#CSP-{profile.get('id', 'N/A')}`", inline=True)
    embed.add_field(name="✈️ Airline", value=profile.get("airline_name", "—"), inline=True)
    embed.add_field(name="🌐 Alliance", value=profile.get("alliance", "—"), inline=True)
    embed.add_field(name="💰 Latest Share", value=f"**{_money(stats['latest'])}**", inline=True)
    embed.add_field(name="📈 7-Day Growth", value=_signed_pct(growth), inline=True)
    embed.add_field(name="🏆 All-Time High", value=_money(stats["maximum"]), inline=True)
    embed.add_field(name="📊 Average", value=_money(stats["average"]), inline=True)
    embed.add_field(name="🔥 Streak", value=f"`{stats['streak']} day(s)`", inline=True)
    embed.add_field(name="📝 Total Entries", value=f"`{stats['count']}`", inline=True)
    embed.add_field(
        name="⚡ Volatility",
        value="—" if stats["volatility"] is None else f"{stats['volatility']:.2f}%",
        inline=True,
    )
    embed.add_field(
        name="🔄 Daily Movement",
        value="—" if stats["avg_change"] is None else f"{stats['avg_change']:.2f}%",
        inline=True,
    )
    embed.add_field(
        name="🎯 Consistency",
        value=f"{stats['consistency']:.1f}%",
        inline=True,
    )
    if stats["first_date"] and stats["latest_date"]:
        embed.add_field(
            name="🗓️ Tracking Range",
            value=f"`{stats['first_date'].strftime('%d %b %Y')}` → `{stats['latest_date'].strftime('%d %b %Y')}`",
            inline=False,
        )
    return embed


# ──────────────────────────────────────────────────────────
#  REGISTER COMMANDS (Injected into Bot instance)
# ──────────────────────────────────────────────────────────
def register_community_share_commands(
    bot_instance: commands.Bot,
    supa_get=None,
    supa_post=None,
    supa_patch=None,
):
    """Binds community share commands to the provided Discord bot instance."""
    global _bot, _supabase_get, _supabase_post, _supabase_patch, _commands_registered

    _bot = bot_instance
    if supa_get:
        _supabase_get = supa_get
    if supa_post:
        _supabase_post = supa_post
    if supa_patch:
        _supabase_patch = supa_patch

    if _commands_registered:
        print("[COMMUNITY SHARE] Commands already registered, updated database references.")
        return

    # ───────────────────────────────────────────────────────
    # 1. /communityregister
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityregister",
        description="Register or update your public AM4 share-tracking profile",
    )
    @app_commands.describe(
        discord_name="Your display name for tracking results",
        airline_name="Your AM4 Airline Name",
        alliance="Your AM4 Alliance Name",
    )
    async def communityregister(
        ctx: commands.Context,
        discord_name: str,
        airline_name: str,
        alliance: str,
    ):
        await ctx.defer(ephemeral=True)
        discord_name = discord_name.strip()[:80]
        airline_name = airline_name.strip()[:120]
        alliance = alliance.strip()[:120]

        if not discord_name or not airline_name or not alliance:
            return await ctx.send(
                "❌ **Missing Fields:** Please provide all 3 fields: Display Name, Airline Name, and Alliance.",
                ephemeral=True,
            )

        now_utc = datetime.now(timezone.utc).isoformat()
        now_ist_str = _now_ist().strftime("%d %b %Y, %I:%M %p IST")

        payload = {
            "discord_id": str(ctx.author.id),
            "discord_name": discord_name,
            "airline_name": airline_name,
            "alliance": alliance,
            "active": True,
            "updated_at": now_utc,
        }

        try:
            existing = await _get_profile(str(ctx.author.id))
            if existing:
                await _db_patch(
                    COMMUNITY_PROFILE_TABLE,
                    {"id": f"eq.{existing['id']}"},
                    payload,
                )
                action = "updated"
                profile_id = existing["id"]
            else:
                created = await _db_post(COMMUNITY_PROFILE_TABLE, payload)
                action = "created"
                if isinstance(created, list) and created and "id" in created[0]:
                    profile_id = created[0]["id"]
                elif isinstance(created, dict) and "id" in created:
                    profile_id = created["id"]
                else:
                    # Fetch profile back to get generated ID
                    refetched = await _get_profile(str(ctx.author.id))
                    profile_id = refetched["id"] if refetched else "CONFIRMED"

        except Exception as exc:
            print(f"[COMMUNITY SHARE] Registration error for {ctx.author.id}: {exc}")
            return await ctx.send(
                f"❌ **Registration Failed:** Could not save profile to database.\n`{exc}`",
                ephemeral=True,
            )

        # Build High-Tech Registration Confirmation Embed
        color = _GREEN if action == "created" else _ACCENT
        title_prefix = "🎉 Profile Registered!" if action == "created" else "🔄 Profile Updated!"

        embed = discord.Embed(
            title=f"📋 Community Share Tracking — {title_prefix}",
            description=(
                f"Your AM4 public share-tracking profile has been **successfully {action}**.\n"
                f"You can now submit daily share values and track your growth!"
            ),
            color=color,
        )
        embed.add_field(name="🆔 Profile ID", value=f"`#CSP-{profile_id}`", inline=True)
        embed.add_field(name="👤 Discord Member", value=f"{ctx.author.mention}\n`{discord_name}`", inline=True)
        embed.add_field(name="⚡ Status", value="`🟢 Active & Tracking`", inline=True)
        embed.add_field(name="✈️ Airline Name", value=f"**{airline_name}**", inline=True)
        embed.add_field(name="🌐 Alliance", value=f"**{alliance}**", inline=True)
        embed.add_field(name="📅 Timestamp", value=f"`{now_ist_str}`", inline=True)

        embed.add_field(
            name="🚀 Quick Start Guide",
            value=(
                "• **`/communityshare <value>`** — Submit your daily share (e.g. `5.2B`, `450M`, `1250000`)\n"
                "• **`/communityprofile`** — View your complete tracking profile & stats\n"
                "• **`/communityanalysis`** — View your share trend chart & analytics\n"
                "• **`/communityhistory`** — View your recent share logs\n"
                "• **`/communityleaderboard`** — See where you rank among community players"
            ),
            inline=False,
        )
        embed.set_footer(text=f"JARVIS • Community Share Tracking • ID: #CSP-{profile_id}")

        await ctx.send(embed=embed, ephemeral=True)

    # ───────────────────────────────────────────────────────
    # 2. /communityshare
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityshare",
        description="Submit or update your daily AM4 share value",
    )
    @app_commands.describe(
        value="Your share value, e.g. 5.2B, 500M, or 1250000",
        update="Set to True if you want to update today's already submitted value",
    )
    async def communityshare(
        ctx: commands.Context,
        value: str,
        update: bool = False,
    ):
        await ctx.defer(ephemeral=True)

        profile = await _get_profile(str(ctx.author.id))
        if not profile:
            return await ctx.send(
                "❌ **Profile Not Found:** Please register first using `/communityregister`.",
                ephemeral=True,
            )

        parsed_val = _parse_money(value)
        if parsed_val is None:
            return await ctx.send(
                "❌ **Invalid Value Format:** Use standard AM4 values like `5.2B`, `450M`, `85K`, or `1250000`.",
                ephemeral=True,
            )

        today_str = _today().isoformat()
        now_utc = datetime.now(timezone.utc).isoformat()
        now_ist_str = _now_ist().strftime("%d %b %Y, %I:%M %p IST")

        # Check existing entries for today
        try:
            today_entry = await _db_get(
                COMMUNITY_ENTRY_TABLE,
                {
                    "profile_id": f"eq.{profile['id']}",
                    "entry_date": f"eq.{today_str}",
                    "select": "id,share_value",
                    "limit": "1",
                },
            )
        except Exception as exc:
            print(f"[COMMUNITY SHARE] Lookup error: {exc}")
            today_entry = []

        is_update = False
        prev_today_val = None

        if today_entry:
            if not update:
                current_val = _value(today_entry[0])
                return await ctx.send(
                    f"⚠️ **Already Submitted Today:** You already logged **{_money(current_val)}** for today (`{today_str}`).\n\n"
                    f"💡 *Need to fix a typo?* Use: `/communityshare value:{value} update:True` to overwrite today's entry.",
                    ephemeral=True,
                )
            else:
                is_update = True
                prev_today_val = _value(today_entry[0])
                await _db_patch(
                    COMMUNITY_ENTRY_TABLE,
                    {"id": f"eq.{today_entry[0]['id']}"},
                    {"share_value": parsed_val, "created_at": now_utc},
                )
        else:
            await _db_post(
                COMMUNITY_ENTRY_TABLE,
                {
                    "profile_id": profile["id"],
                    "discord_id": str(ctx.author.id),
                    "entry_date": today_str,
                    "share_value": parsed_val,
                    "created_at": now_utc,
                },
            )

        # Retrieve fresh entries to compute accurate stats & streak
        entries = await _get_entries(profile["id"])
        stats = _stats(entries)

        # Check if All-Time High
        is_ath = (parsed_val >= stats["maximum"]) and (stats["count"] >= 2)

        color = _GOLD if is_ath else _GREEN
        title = "🎉 NEW ALL-TIME HIGH!" if is_ath else ("🔄 Share Value Updated" if is_update else "✅ Daily Share Recorded")

        embed = discord.Embed(
            title=f"{title} — {_profile_name(profile)}",
            color=color,
        )
        embed.add_field(
            name="💰 Recorded Share Value",
            value=f"**{_money(parsed_val)}**",
            inline=True,
        )

        if is_update and prev_today_val:
            embed.add_field(
                name="🔄 Previous Today",
                value=f"{_money(prev_today_val)} → {_signed_diff(parsed_val, prev_today_val)}",
                inline=True,
            )
        elif len(entries) >= 2:
            prev_entry = entries[-2]
            prev_val = _value(prev_entry)
            embed.add_field(
                name="📈 Daily Change",
                value=_signed_diff(parsed_val, prev_val),
                inline=True,
            )
        else:
            embed.add_field(
                name="📈 Daily Change",
                value="*First entry logged!*",
                inline=True,
            )

        embed.add_field(
            name="🔥 Streak",
            value=f"`{stats['streak']} day(s)`",
            inline=True,
        )
        embed.add_field(
            name="🏆 All-Time High",
            value=f"**{_money(stats['maximum'])}**",
            inline=True,
        )
        embed.add_field(
            name="📊 7-Day Growth",
            value=_signed_pct(stats["growth"]),
            inline=True,
        )
        embed.add_field(
            name="📅 Entry Date",
            value=f"`{now_ist_str}`",
            inline=True,
        )

        embed.set_footer(text=f"JARVIS • Community Share Tracking • Profile #{profile['id']}")
        await ctx.send(embed=embed, ephemeral=True)

    # ───────────────────────────────────────────────────────
    # 3. /communityprofile
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityprofile",
        description="View your or another member's community share profile card",
    )
    @app_commands.describe(member="Optional: Check another player's profile")
    async def communityprofile(
        ctx: commands.Context,
        member: Optional[discord.Member] = None,
    ):
        await ctx.defer()
        target = member or ctx.author
        profile = await _get_profile(str(target.id))

        if not profile:
            msg = "❌ You have not registered yet. Run `/communityregister` to get started!" if target == ctx.author else f"❌ {target.mention} has not registered for community tracking."
            return await ctx.send(msg)

        entries = await _get_entries(profile["id"])
        stats = _stats(entries)

        embed = discord.Embed(
            title=f"👤 Community Share Profile — {_profile_name(profile)}",
            color=_ACCENT,
        )
        embed.set_thumbnail(url=target.display_avatar.url if target.display_avatar else None)
        embed.add_field(name="🆔 Profile ID", value=f"`#CSP-{profile['id']}`", inline=True)
        embed.add_field(name="✈️ Airline Name", value=f"**{profile.get('airline_name', '—')}**", inline=True)
        embed.add_field(name="🌐 Alliance", value=f"**{profile.get('alliance', '—')}**", inline=True)
        embed.add_field(name="💰 Latest Share", value=f"**{_money(stats['latest'])}**", inline=True)
        embed.add_field(name="🏆 All-Time High", value=f"**{_money(stats['maximum'])}**", inline=True)
        embed.add_field(name="📊 Average Share", value=_money(stats["average"]), inline=True)
        embed.add_field(name="🔥 Current Streak", value=f"`{stats['streak']} day(s)`", inline=True)
        embed.add_field(name="📝 Total Entries", value=f"`{stats['count']}`", inline=True)
        embed.add_field(name="📈 7-Day Trend", value=_signed_pct(stats["growth"]), inline=True)

        if stats["first_date"] and stats["latest_date"]:
            embed.add_field(
                name="🗓️ Active Since",
                value=f"`{stats['first_date'].strftime('%d %b %Y')}` (Last entry: `{stats['latest_date'].strftime('%d %b %Y')}`)",
                inline=False,
            )

        embed.set_footer(text=f"JARVIS • Community Share Tracking • ID: #CSP-{profile['id']}")
        await ctx.send(embed=embed)

    # ───────────────────────────────────────────────────────
    # 4. /communityhistory
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityhistory",
        description="View your recent share value submission history",
    )
    @app_commands.describe(limit="Number of recent entries to show (max 20)")
    async def communityhistory(
        ctx: commands.Context,
        limit: int = 10,
    ):
        await ctx.defer(ephemeral=True)
        limit = max(3, min(int(limit or 10), 20))

        profile = await _get_profile(str(ctx.author.id))
        if not profile:
            return await ctx.send("❌ Register first with `/communityregister`.", ephemeral=True)

        entries = await _get_entries(profile["id"], limit=limit)
        if not entries:
            return await ctx.send("📭 No share entries found yet. Use `/communityshare <value>` to log your first value!", ephemeral=True)

        ordered = _sorted_entries(entries)
        recent = list(reversed(ordered))[:limit]

        lines = []
        for i, entry in enumerate(recent):
            val = _value(entry)
            edate = _entry_date(entry)
            date_str = edate.strftime("%d %b %Y") if edate else "—"

            # Compute change against subsequent older entry
            original_idx = ordered.index(entry)
            diff_str = ""
            if original_idx > 0:
                prev_val = _value(ordered[original_idx - 1])
                diff_str = f" ({_signed_pct((val - prev_val) / prev_val * 100)})"

            lines.append(f"`{date_str}`: **{_money(val)}**{diff_str}")

        embed = discord.Embed(
            title=f"📜 Share Submission History — {_profile_name(profile)}",
            description="\n".join(lines),
            color=_ACCENT,
        )
        embed.set_footer(text=f"Showing last {len(lines)} entries • Profile #CSP-{profile['id']}")
        await ctx.send(embed=embed, ephemeral=True)

    # ───────────────────────────────────────────────────────
    # 5. /communityanalysis
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityanalysis",
        description="View your community share analysis and trend chart",
    )
    @app_commands.describe(days="Chart window in days (between 7 and 365)")
    async def communityanalysis(ctx: commands.Context, days: int = 30):
        await ctx.defer()
        days = max(7, min(int(days or 30), 365))

        profile = await _get_profile(str(ctx.author.id))
        if not profile:
            return await ctx.send("❌ You are not registered yet. Use `/communityregister` to get started!")

        entries = await _get_entries(profile["id"])
        if not entries:
            return await ctx.send("📭 No entries found yet. Submit today's value with `/communityshare <value>`.")

        embed = _stats_embed(profile, entries)
        try:
            chart_buf = _chart(entries, profile, days=days)
            embed.set_image(url="attachment://community_trend.png")
            embed.set_footer(text=f"JARVIS • Community Share Tracking • ID: #CSP-{profile['id']}")
            await ctx.send(
                embed=embed,
                file=discord.File(chart_buf, "community_trend.png"),
            )
        except Exception as exc:
            print(f"[COMMUNITY SHARE] Chart error: {exc}")
            embed.set_footer(text=f"JARVIS • Community Share Tracking • ID: #CSP-{profile['id']} (Chart unavailable)")
            await ctx.send(embed=embed)

    # ───────────────────────────────────────────────────────
    # 6. /communityleaderboard
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityleaderboard",
        description="Show the AM4 community share leaderboard",
    )
    @app_commands.describe(alliance="Optional: Filter players by AM4 alliance")
    async def communityleaderboard(ctx: commands.Context, alliance: Optional[str] = None):
        await ctx.defer()
        try:
            profiles = await _get_all_profiles()
            entries = await _get_all_entries()
        except Exception as exc:
            print(f"[COMMUNITY SHARE] Leaderboard error: {exc}")
            return await ctx.send("❌ Could not fetch community tracking data.")

        profile_map = {str(p["id"]): p for p in profiles}
        latest = {}
        for entry in entries:
            key = str(entry.get("profile_id"))
            if key not in latest or _entry_date(entry) > _entry_date(latest[key]):
                latest[key] = entry

        rows = []
        for key, entry in latest.items():
            prof = profile_map.get(key)
            if not prof:
                continue
            if alliance and prof.get("alliance", "").lower() != alliance.lower().strip():
                continue
            rows.append((prof, entry))

        rows.sort(key=lambda r: _value(r[1]), reverse=True)
        if not rows:
            return await ctx.send(f"📭 No community tracking entries found{' for alliance `' + alliance + '`' if alliance else ''}.")

        lines = []
        for index, (prof, entry) in enumerate(rows[:15], 1):
            medal = ["🥇", "🥈", "🥉"][index - 1] if index <= 3 else f"`#{index:02d}`"
            edate = _entry_date(entry)
            date_str = edate.strftime("%d %b") if edate else "—"
            lines.append(
                f"{medal} **{_profile_name(prof)}** — **{_money(_value(entry))}**\n"
                f"　✈️ {prof.get('airline_name', '—')} • 🌐 {prof.get('alliance', '—')} • 🗓️ {date_str}"
            )

        title = "🏆 Community Share Leaderboard"
        if alliance:
            title += f" — {alliance.upper()}"

        embed = discord.Embed(
            title=title,
            description="\n\n".join(lines),
            color=_ACCENT,
        )
        embed.set_footer(text=f"Community Tracking • Showing top {min(len(rows), 15)} of {len(rows)} player(s)")
        await ctx.send(embed=embed)

    # ───────────────────────────────────────────────────────
    # 7. /communitycompare
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communitycompare",
        description="Compare share trends of two community players",
    )
    @app_commands.describe(
        player1="Display name or airline of the first player",
        player2="Display name or airline of the second player",
    )
    async def communitycompare(ctx: commands.Context, player1: str, player2: str):
        await ctx.defer()
        try:
            profiles = await _get_all_profiles()
            entries = await _get_all_entries()
        except Exception as exc:
            print(f"[COMMUNITY SHARE] Compare error: {exc}")
            return await ctx.send("❌ Could not fetch community tracking data.")

        def find_player(q: str):
            q = q.strip().lower()
            exact = [p for p in profiles if p.get("discord_name", "").lower() == q or p.get("airline_name", "").lower() == q]
            if exact:
                return exact[0]
            matches = [p for p in profiles if q in p.get("discord_name", "").lower() or q in p.get("airline_name", "").lower()]
            return matches[0] if len(matches) == 1 else None

        first = find_player(player1)
        second = find_player(player2)

        if not first or not second:
            missing = []
            if not first: missing.append(f"`{player1}`")
            if not second: missing.append(f"`{player2}`")
            return await ctx.send(f"❌ Could not uniquely match player(s): {', '.join(missing)}. Please check their registered names.")

        entry_map: dict[str, list[dict]] = {}
        for entry in entries:
            entry_map.setdefault(str(entry.get("profile_id")), []).append(entry)

        first_entries = entry_map.get(str(first["id"]), [])
        second_entries = entry_map.get(str(second["id"]), [])
        first_stats = _stats(first_entries)
        second_stats = _stats(second_entries)

        if not first_stats["count"] or not second_stats["count"]:
            return await ctx.send("❌ Both players need at least one recorded share entry to compare.")

        embed = discord.Embed(
            title=f"⚔️ Share Comparison: {_profile_name(first)} vs {_profile_name(second)}",
            color=_ACCENT,
        )
        embed.add_field(
            name=f"🔵 {_profile_name(first)}",
            value=(
                f"✈️ {first.get('airline_name', '—')}\n"
                f"💰 Latest: **{_money(first_stats['latest'])}**\n"
                f"🏆 ATH: **{_money(first_stats['maximum'])}**\n"
                f"📊 7d Growth: {_signed_pct(first_stats['growth'])}\n"
                f"🔥 Streak: `{first_stats['streak']}d` • Entries: `{first_stats['count']}`"
            ),
            inline=True,
        )
        embed.add_field(
            name=f"🟣 {_profile_name(second)}",
            value=(
                f"✈️ {second.get('airline_name', '—')}\n"
                f"💰 Latest: **{_money(second_stats['latest'])}**\n"
                f"🏆 ATH: **{_money(second_stats['maximum'])}**\n"
                f"📊 7d Growth: {_signed_pct(second_stats['growth'])}\n"
                f"🔥 Streak: `{second_stats['streak']}d` • Entries: `{second_stats['count']}`"
            ),
            inline=True,
        )

        try:
            fig, ax = _figure(10, 4.6)
            for prof, p_entries, p_color in (
                (first, first_entries, "#00d4ff"),
                (second, second_entries, "#a855f7"),
            ):
                ord_e = _sorted_entries(p_entries)
                lbls = [_entry_date(e).strftime("%d %b") for e in ord_e]
                ax.plot(
                    lbls,
                    [_value(e) for e in ord_e],
                    label=_profile_name(prof),
                    color=p_color,
                    linewidth=2.4,
                    marker="o",
                    markersize=4,
                )
            ax.set_title("Community Share Comparison")
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: _money(v)))
            ax.legend(facecolor=_PANEL, labelcolor=_TEXT)
            plt.xticks(rotation=30, color=_MUTED, fontsize=8)
            embed.set_image(url="attachment://compare.png")
            embed.set_footer(text="JARVIS • Community Share Tracking")
            await ctx.send(embed=embed, file=discord.File(_png(fig), "compare.png"))
        except Exception as exc:
            print(f"[COMMUNITY SHARE] Comparison chart error: {exc}")
            await ctx.send(embed=embed)

    # ───────────────────────────────────────────────────────
    # 8. /communityhelp
    # ───────────────────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="communityhelp",
        description="Guide and command list for AM4 Community Share Tracking",
    )
    async def communityhelp(ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        embed = discord.Embed(
            title="📖 JARVIS Community Share Tracking — Help Guide",
            description=(
                "Community Share Tracking allows **non-portal members** to track their daily "
                "AM4 airline share growth, view trend graphs, maintain streaks, and compete on the leaderboard."
            ),
            color=_ACCENT,
        )
        embed.add_field(
            name="📋 Registration & Profile",
            value=(
                "• `/communityregister` — Register your display name, airline, and alliance.\n"
                "• `/communityprofile` — View your registration card, ID, streak, and stats."
            ),
            inline=False,
        )
        embed.add_field(
            name="📈 Daily Tracking",
            value=(
                "• `/communityshare <value>` — Log today's share value (e.g. `5.2B`, `350M`).\n"
                "• `/communityshare value:<val> update:True` — Update today's entry if you made a typo.\n"
                "• `/communityhistory` — View your last 10 logged share entries."
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Analysis & Leaderboard",
            value=(
                "• `/communityanalysis [days]` — Generate your share growth chart & volatility analysis.\n"
                "• `/communityleaderboard [alliance]` — View the global or alliance ranking.\n"
                "• `/communitycompare <player1> <player2>` — Compare two players head-to-head."
            ),
            inline=False,
        )
        embed.set_footer(text="JARVIS • Community Share Tracking System")
        await ctx.send(embed=embed, ephemeral=True)

    _commands_registered = True
    print("[COMMUNITY SHARE] Registered 8 hybrid commands: /communityregister, /communityshare, /communityprofile, /communityhistory, /communityanalysis, /communityleaderboard, /communitycompare, /communityhelp")


# Alias setup functions
setup_community_share = register_community_share_commands


# Standard discord.py Extension Loader
async def setup(bot: commands.Bot):
    register_community_share_commands(bot)
