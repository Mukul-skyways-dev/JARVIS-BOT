# =========================================================
#  aerion_membership.py  —  AERION Membership System
#
#  Paste at top of bot1.py imports:
#    from aerion_membership import (
#        check_membership, membership_required,
#        register_membership_commands
#    )
#
#  Call in bot setup:
#    register_membership_commands(bot, supabase_get, supabase_post, supabase_patch)
#
#  Gate any command with:
#    @membership_required
#    async def your_command(ctx, ...):
#
#  Supabase columns needed in share_users:
#    aerion_access    BOOLEAN DEFAULT FALSE
#    aerion_expires   TIMESTAMPTZ DEFAULT NULL
#    aerion_joined_at TIMESTAMPTZ DEFAULT NULL   (first-ever join)
# =========================================================

import os, uuid, random, string, asyncio, functools, math
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
try:
    import pytz
    _IST = pytz.timezone("Asia/Kolkata")
except Exception:
    try:
        from zoneinfo import ZoneInfo
        _IST = ZoneInfo("Asia/Kolkata")
    except Exception:
        _IST = timezone(timedelta(hours=5, minutes=30))

# ── Pricing ───────────────────────────────────────────────
MEMBERSHIP_NEW_COST     = 1000   # first-time join (never been a member)
MEMBERSHIP_RENEWAL_COST = 100    # renewal (was member before)
MEMBERSHIP_DAYS         = 30     # validity in days

# ── Bot name ──────────────────────────────────────────────
BOT_NAME    = "AERION"
BOT_VERSION = "V3 ALPHA"
BOT_TAGLINE = "Think Smarter. Operate Better. Fly Further."

# ── Injected refs ─────────────────────────────────────────
_bot           = None
_supabase_get  = None
_supabase_post = None
_supabase_patch= None
_commands_registered = False

def _now_utc():  return datetime.now(timezone.utc)
def _now_ist():  return datetime.now(_IST)

# ─────────────────────────────────────────────────────────
#  TRANSACTION ID GENERATOR
# ─────────────────────────────────────────────────────────
def _gen_txn_id() -> str:
    """Generate unique alphanumeric transaction ID: AER-XXXXXXXX"""
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f"AER-{suffix}"

# ─────────────────────────────────────────────────────────
#  MEMBERSHIP CHECK
# ─────────────────────────────────────────────────────────
async def check_membership(discord_id: str) -> dict:
    """
    Check if a Discord user has active AERION membership.

    Returns dict:
        linked       bool           — is Discord linked to a portal account?
        has_access   bool           — is membership currently active?
        is_new       bool           — never been a member before (pay 1000)
        sts_id       str | None
        name         str | None
        aero_points  int
        expires      datetime | None (UTC-aware)
        days_left    int
        row          dict | None    — full share_users row
        error        str | None     — non-None only if database query failed
        db_error     bool           — True if lookup threw exception
    """
    uid = str(discord_id).strip()
    result = {
        "linked": False, "has_access": False, "is_new": True,
        "sts_id": None, "name": None, "aero_points": 0,
        "expires": None, "days_left": 0, "row": None,
        "error": None, "db_error": False,
    }

    if _supabase_get is None:
        err_msg = "Supabase REST client not initialized in aerion_membership module"
        print(f"[MEMBERSHIP] check_membership config error: {err_msg}")
        result["error"] = err_msg
        result["db_error"] = True
        return result

    try:
        # Prioritize rows with aerion_access=True and latest expiry if duplicates exist
        rows = await _supabase_get("share_users", {
            "discord_id": f"eq.{uid}",
            "select": "sts_id,name,aero_points,aerion_access,"
                      "aerion_expires,aerion_joined_at,airline,alliance",
            "order": "aerion_access.desc,aerion_expires.desc.nullslast",
        })
        if not rows:
            return result

        row = rows[0]
        result["linked"]      = True
        result["row"]         = row
        result["sts_id"]      = row.get("sts_id")
        result["name"]        = row.get("name") or row.get("sts_id")
        result["aero_points"] = int(row.get("aero_points") or 0)
        result["is_new"]      = not bool(row.get("aerion_joined_at"))

        # Determine access flag safely across boolean, string, and integer types
        raw_access = row.get("aerion_access")
        is_access_true = (
            raw_access is True or
            str(raw_access).strip().lower() in ("true", "t", "1", "yes")
        )

        expires_raw = row.get("aerion_expires")
        now_utc = _now_utc()

        if expires_raw:
            try:
                # Handle ISO 8601 strings with 'Z' or offsets
                clean_exp = str(expires_raw).strip().replace("Z", "+00:00")
                expires_dt = datetime.fromisoformat(clean_exp)
                # Ensure timezone-aware (assume UTC if naive)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                else:
                    expires_dt = expires_dt.astimezone(timezone.utc)

                result["expires"] = expires_dt
                seconds_left = (expires_dt - now_utc).total_seconds()

                if seconds_left > 0:
                    # Active: at least 1 day or ceiling of fractional days
                    days_left = max(1, math.ceil(seconds_left / 86400.0))
                    result["days_left"] = days_left
                    if is_access_true:
                        result["has_access"] = True
                else:
                    # Expired
                    result["days_left"] = 0
                    result["has_access"] = False
            except Exception as e:
                print(f"[MEMBERSHIP] expires parse error for '{expires_raw}': {e}")
                # If timestamp parsing fails but access flag is active, allow access
                if is_access_true:
                    result["has_access"] = True
        elif is_access_true:
            # aerion_access is True without an expiration date (e.g. lifetime / admin access)
            result["has_access"] = True
            result["days_left"] = 9999

    except Exception as e:
        print(f"[MEMBERSHIP] check_membership error for Discord {uid}: {e}")
        result["error"] = str(e)
        result["db_error"] = True

    return result

# ─────────────────────────────────────────────────────────
#  MEMBERSHIP REQUIRED DECORATOR
# ─────────────────────────────────────────────────────────
def membership_required(func):
    """
    Decorator for bot commands.
    Blocks execution if user doesn't have active AERION membership.
    Shows a rich branded embed with action buttons.
    """
    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            try:
                await ctx.defer(ephemeral=True)
            except Exception:
                pass

        status = await check_membership(str(ctx.author.id))

        if status.get("error") or status.get("db_error"):
            embed = discord.Embed(
                title="⚠️  Portal Temporarily Unavailable",
                description=(
                    "```\n"
                    "  AERION DATABASE GATEWAY\n"
                    "  ── STATUS: RECONNECTING ──\n"
                    "```\n"
                    "Could not reach the membership database right now.\n"
                    "This is temporary — please try again in a few moments."
                ),
                color=0xffaa00
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  {BOT_TAGLINE}")
            try:
                await ctx.send(embed=embed, ephemeral=True)
            except Exception:
                await ctx.send(embed=embed)
            return

        if not status["linked"]:
            embed = discord.Embed(
                title="🔗  Account Not Linked",
                color=0xff4757
            )
            embed.description = (
                "```\n"
                "  AERION PORTAL LINK REQUIRED\n"
                "```\n"
                "Your Discord account is **not linked** to the AERO Portal.\n"
                "Link your account to access the AERION ecosystem."
            )
            embed.add_field(
                name="📋  How to Link",
                value=(
                    "> **1.** Register on the AERO Portal\n"
                    "> **2.** Go to your profile → **Generate Link Code**\n"
                    "> **3.** Use `/link <code>` in this server\n"
                    "> **4.** Then run `/subscribe` to activate membership"
                ),
                inline=False
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  {BOT_TAGLINE}")
            try:
                await ctx.send(embed=embed, ephemeral=True)
            except Exception:
                await ctx.send(embed=embed)
            return

        if not status["has_access"]:
            cost = MEMBERSHIP_NEW_COST if status["is_new"] else MEMBERSHIP_RENEWAL_COST
            pts  = status["aero_points"]
            can_afford = pts >= cost
            short_by   = max(0, cost - pts)
            kind_label = "🆕  First-Time Join" if status["is_new"] else "🔄  Renewal"

            embed = discord.Embed(
                title="🔒  AERION Membership Required",
                color=0xf0c040
            )
            embed.description = (
                "```\n"
                "  AERION PREMIUM ACCESS\n"
                "  ── SUBSCRIPTION INACTIVE ──\n"
                "```\n"
                "Activate your membership to unlock the full AERION suite."
            )
            embed.add_field(
                name="📦  Subscription Details",
                value=(
                    f"**Type     :** {kind_label}\n"
                    f"**Cost     :** `{cost:,}` AERO Points\n"
                    f"**Duration :** {MEMBERSHIP_DAYS} days\n"
                    f"**Your Bal :** `{pts:,}` AERO Points"
                ),
                inline=True
            )
            embed.add_field(
                name="💳  Affordability",
                value=(
                    f"{'✅  **You can subscribe now!**' if can_afford else f'❌  Short by `{short_by:,}` pts'}\n\n"
                    + ("Run `/subscribe` to activate." if can_afford
                       else "Earn points via portal quests\nand AERION command usage.")
                ),
                inline=True
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  {BOT_TAGLINE}")
            view = _GateActionView(can_afford=can_afford)
            try:
                await ctx.send(embed=embed, view=view, ephemeral=True)
            except Exception:
                await ctx.send(embed=embed, view=view)
            return

        return await func(ctx, *args, **kwargs)

    return wrapper

# ─────────────────────────────────────────────────────────
#  CERTIFICATE / INVOICE DM
# ─────────────────────────────────────────────────────────
async def _send_membership_certificate(
    discord_user, sts_id: str, name: str,
    txn_id: str, cost: int, expires: datetime,
    is_new: bool
):
    """DM the user a premium gold-themed membership certificate."""
    issued  = _now_ist().strftime("%d %b %Y  %I:%M %p IST")
    exp_str = expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
    kind    = "FOUNDING MEMBER" if is_new else "RENEWAL CONFIRMED"
    color   = 0xf0c040  # Gold

    embed = discord.Embed(
        title=f"🏅  {BOT_NAME}  —  {kind}",
        color=color
    )
    embed.description = (
        "```\n"
        "  ╔══════════════════════════════════╗\n"
        "  ║    AERION MEMBERSHIP CERTIFICATE  ║\n"
        f"  ║    {BOT_VERSION:<34}║\n"
        "  ╚══════════════════════════════════╝\n"
        "```"
    )
    embed.add_field(
        name="👤  Member Details",
        value=(
            f"**Name    :** {name}\n"
            f"**STS ID  :** `{sts_id}`\n"
            f"**Discord :** {discord_user.mention}"
        ),
        inline=True
    )
    embed.add_field(
        name="🎫  Membership Info",
        value=(
            f"**Type    :** {'New Member 🆕' if is_new else 'Renewal 🔄'}\n"
            f"**Valid   :** {MEMBERSHIP_DAYS} days\n"
            f"**Issued  :** {issued}\n"
            f"**Expires :** {exp_str}"
        ),
        inline=True
    )
    embed.add_field(
        name="🧾  Transaction",
        value=(
            f"**TXN ID :** `{txn_id}`\n"
            f"**Cost   :** {cost:,} AERO Points\n"
            f"**Status :** ✅  CONFIRMED"
        ),
        inline=False
    )
    embed.add_field(
        name="✨  Access Unlocked",
        value=(
            "┣ AERION Intelligence Suite\n"
            "┣ Alliance Intelligence\n"
            "┣ Smart Monitoring & Alerts\n"
            "┣ Player Progression System\n"
            "┗ Advanced AM4 Analytics"
        ),
        inline=False
    )
    embed.set_footer(text=f"{BOT_NAME}  •  {BOT_TAGLINE}  •  TXN: {txn_id}")

    try:
        await discord_user.send(
            content=(
                f"🎉 **{'Welcome to AERION!' if is_new else 'AERION Membership Renewed!'}** "
                f"{discord_user.mention}"
            ),
            embed=embed
        )
        return True
    except discord.Forbidden:
        print(f"[MEMBERSHIP] Could not DM {discord_user} — DMs disabled")
        return False
    except Exception as e:
        print(f"[MEMBERSHIP] DM delivery error to {discord_user}: {e}")
        return False


# ─────────────────────────────────────────────────────────
#  SUBSCRIBE LOGIC
# ─────────────────────────────────────────────────────────
async def _do_subscribe(discord_user) -> dict:
    """
    Deduct AERO points, activate membership, send certificate.
    Returns { success, message, txn_id, expires, cost, dm_sent }
    """
    uid = str(discord_user.id).strip()
    status = await check_membership(uid)

    if status.get("error") or status.get("db_error"):
        return {"success": False, "message": "❌ Database connection error. Please try again shortly."}

    if not status["linked"]:
        return {"success": False,
                "message": "❌ Link your Discord to the portal first with `/link <code>`"}

    is_new  = status["is_new"]
    cost    = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
    pts     = status["aero_points"]
    sts_id  = status["sts_id"]
    name    = status["name"]

    if pts < cost:
        return {
            "success": False,
            "message": (
                f"❌ Insufficient AERO Points.\n"
                f"**Need:** {cost:,}  |  **You have:** {pts:,}  |  "
                f"**Short:** {cost-pts:,}"
            )
        }

    # Calculate expiry
    # If renewing with time remaining, extend from current expiry
    now_utc = _now_utc()
    if not is_new and status["expires"] and status["expires"] > now_utc:
        expires = status["expires"] + timedelta(days=MEMBERSHIP_DAYS)
    else:
        expires = now_utc + timedelta(days=MEMBERSHIP_DAYS)

    new_pts = pts - cost
    txn_id  = _gen_txn_id()

    try:
        # 1. Deduct points + activate membership
        patch_data = {
            "aero_points":   new_pts,
            "aerion_access": True,
            "aerion_expires": expires.isoformat(),
        }
        if is_new:
            patch_data["aerion_joined_at"] = now_utc.isoformat()

        await _supabase_patch(
            "share_users",
            {"sts_id": f"eq.{sts_id}"},
            patch_data
        )

        # 2. Record transaction (safe empty response handling)
        try:
            await _supabase_post("point_transactions", {
                "sts_id":     sts_id,
                "amount":     -cost,
                "reason":     f"AERION Membership {'Join' if is_new else 'Renewal'} | {txn_id}",
                "created_at": now_utc.isoformat(),
            })
        except Exception as tx_err:
            print(f"[MEMBERSHIP] point_transactions log error (non-fatal): {tx_err}")

        # 3. Send certificate DM
        dm_sent = await _send_membership_certificate(
            discord_user, sts_id, name, txn_id, cost, expires, is_new
        )

        return {
            "success":  True,
            "message":  "✅ Membership activated!",
            "txn_id":   txn_id,
            "expires":  expires,
            "cost":     cost,
            "dm_sent":  dm_sent,
            "new_pts":  new_pts,
            "is_new":   is_new,
            "name":     name,
            "sts_id":   sts_id,
        }

    except Exception as e:
        print(f"[MEMBERSHIP] subscribe error for {uid}: {e}")
        return {"success": False, "message": f"❌ Error: {e}"}

# ─────────────────────────────────────────────────────────
#  REGISTER COMMANDS
# ─────────────────────────────────────────────────────────
def register_membership_commands(bot_instance, supa_get, supa_post, supa_patch):
    global _bot, _supabase_get, _supabase_post, _supabase_patch, _commands_registered
    _bot           = bot_instance
    _supabase_get  = supa_get
    _supabase_post = supa_post
    _supabase_patch= supa_patch

    if _commands_registered:
        print("[MEMBERSHIP] Module re-attached (commands already registered)")
        return
    _commands_registered = True
    print("[MEMBERSHIP] Registering membership commands...")

    # ── /aerion ───────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="aerion",
        description="Check your AERION membership status"
    )
    async def aerion_status(ctx):
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)
        else:
            await ctx.defer(ephemeral=True)

        status = await check_membership(str(ctx.author.id))

        if status.get("error") or status.get("db_error"):
            embed = discord.Embed(
                title=f"⚠️ {BOT_NAME} — Service Unavailable",
                description=(
                    "Could not connect to the membership database right now.\n\n"
                    "Please try again in a few moments."
                ),
                color=0xffaa00
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
            return await ctx.send(embed=embed, ephemeral=True)

        if not status["linked"]:
            embed = discord.Embed(
                title=f"🔗 {BOT_NAME} — Not Linked",
                description=(
                    "Your Discord account isn't linked to the AERO portal yet.\n\n"
                    "**To get started:**\n"
                    "1. Register on the AERO portal\n"
                    "2. Generate a link code from your profile\n"
                    "3. Use `/link <code>` here\n"
                    "4. Use `/subscribe` to activate membership"
                ),
                color=0xff4757
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
            return await ctx.send(embed=embed, ephemeral=True)

        pts      = status["aero_points"]
        has_acc  = status["has_access"]
        days     = status["days_left"]
        is_new   = status["is_new"]
        cost     = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
        expires  = status["expires"]
        airline  = status.get("row", {}).get("airline") or "—"
        alliance = status.get("row", {}).get("alliance") or "—"

        # Color + status bar
        if has_acc and days > 15:
            color = 0x00ff88          # green  — healthy
        elif has_acc and days > 0:
            color = 0xf0c040          # gold   — expiring soon
        else:
            color = 0xff4757          # red    — inactive

        if has_acc:
            bar_filled = min(30, int(days / 30 * 30))
            bar = "█" * bar_filled + "░" * (30 - bar_filled)
            status_text = f"✅  **ACTIVE**  —  `{days}` day(s) remaining"
            bar_line    = f"`[{bar}]`"
        else:
            bar = "░" * 30
            status_text = "❌  **INACTIVE**  —  Membership not active"
            bar_line    = f"`[{bar}]`"

        exp_str = (
            expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
            if expires else "—"
        )

        embed = discord.Embed(
            title=f"🤖  {BOT_NAME}  —  Membership Dashboard",
            color=color
        )
        embed.description = (
            "```\n"
            "  AERO CROWN DYNASTY  |  AERION ECOSYSTEM\n"
            "```"
        )
        # Row 1 — Profile
        embed.add_field(
            name="👤  Profile",
            value=(
                f"**Name    :** {status['name']}\n"
                f"**STS ID  :** `{status['sts_id']}`\n"
                f"**Airline :** {airline}\n"
                f"**Alliance:** {alliance}"
            ),
            inline=True
        )
        # Row 1 — Points
        embed.add_field(
            name="💎  AERO Points",
            value=(
                f"`{pts:,}` points\n\n"
                f"{'✅  Can subscribe' if pts >= cost else f'❌  Need `{cost-pts:,}` more'}\n"
                f"({'Join' if is_new else 'Renewal'} costs `{cost:,}`)"
            ),
            inline=True
        )
        # Row 2 — Membership status (full width)
        embed.add_field(
            name="🎫  Membership Status",
            value=(
                f"{status_text}\n"
                f"{bar_line}\n"
                f"**Expires :** {exp_str}\n"
                f"**Type    :** {'First-Time Member 🆕' if is_new else 'Renewal Member 🔄'}"
            ),
            inline=False
        )

        if not has_acc:
            can_afford = pts >= cost
            embed.add_field(
                name=f"{'🆕  Join' if is_new else '🔄  Renew'}  AERION",
                value=(
                    f"**Cost     :** `{cost:,}` AERO Points\n"
                    f"**Duration :** {MEMBERSHIP_DAYS} days\n"
                    + ("✅  Use `/subscribe` to activate right now!"
                       if can_afford
                       else f"❌  Need `{cost-pts:,}` more points.\n"
                            "Earn via portal quests & AERION commands.")
                ),
                inline=False
            )

        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  {BOT_TAGLINE}")
        view = _AerionStatusView(has_access=has_acc, can_afford=(pts >= cost))
        await ctx.send(embed=embed, view=view, ephemeral=True)


    # ── /subscribe ────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="subscribe",
        description="Activate or renew your AERION membership with AERO Points"
    )
    async def subscribe(ctx):
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)
        else:
            await ctx.defer(ephemeral=True)

        status = await check_membership(str(ctx.author.id))

        if status.get("error") or status.get("db_error"):
            embed = discord.Embed(
                title="⚠️  Portal Unavailable",
                description=(
                    "Could not reach the membership database.\n"
                    "Please try again in a few moments."
                ),
                color=0xffaa00
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
            return await ctx.send(embed=embed, ephemeral=True)

        if not status["linked"]:
            embed = discord.Embed(
                title="🔗  Account Not Linked",
                description=(
                    "Link your Discord to the AERO Portal first.\n\n"
                    "> Use `/link <code>` with your portal link code."
                ),
                color=0xff4757
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
            return await ctx.send(embed=embed, ephemeral=True)

        is_new  = status["is_new"]
        cost    = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
        pts     = status["aero_points"]
        days    = status["days_left"]
        can_afford = pts >= cost

        # Build confirmation view
        view = _SubscribeConfirmView(ctx.author, is_new, cost, pts, days)

        color = 0xf0c040 if can_afford else 0xff4757
        embed = discord.Embed(
            title=f"{'🆕  JOIN' if is_new else '🔄  RENEW'}  —  AERION MEMBERSHIP",
            color=color
        )
        embed.description = (
            "```\n"
            f"  {'FIRST-TIME MEMBERSHIP' if is_new else 'MEMBERSHIP RENEWAL'}\n"
            "```"
        )
        # Col 1 — cost breakdown
        embed.add_field(
            name="📋  Cost Breakdown",
            value=(
                f"**Type     :** {'First-Time Join 🆕' if is_new else 'Renewal 🔄'}\n"
                f"**Cost     :** `{cost:,}` AERO Points\n"
                f"**Duration :** {MEMBERSHIP_DAYS} days\n"
                + (f"**Extends  :** +{MEMBERSHIP_DAYS}d (now {days}d left)\n"
                   if not is_new and days > 0 else "")
            ),
            inline=True
        )
        # Col 2 — your balance
        embed.add_field(
            name="💎  Your Balance",
            value=(
                f"**Current  :** `{pts:,}` pts\n"
                f"**After    :** `{max(0, pts-cost):,}` pts\n\n"
                + ("✅  **Sufficient balance**" if can_afford
                   else f"❌  Short by `{cost-pts:,}` pts")
            ),
            inline=True
        )

        if not can_afford:
            embed.add_field(
                name="❌  Insufficient Points",
                value=(
                    f"You need `{cost-pts:,}` more AERO Points.\n"
                    "Earn points by using AERION commands\n"
                    "and completing portal quests."
                ),
                inline=False
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  {BOT_TAGLINE}")
            return await ctx.send(embed=embed, ephemeral=True)

        embed.add_field(
            name="✨  Access You'll Unlock",
            value=(
                "┣ AERION Intelligence Suite\n"
                "┣ Alliance Intelligence\n"
                "┣ Advanced Route Analytics\n"
                "┗ All Premium Commands"
            ),
            inline=False
        )
        embed.add_field(
            name="⚠️  Confirm Purchase",
            value=(
                "Press **✅ Confirm** to deduct points and activate.\n"
                "A certificate will be DM'd to you instantly."
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  {BOT_TAGLINE}")
        await ctx.send(embed=embed, view=view, ephemeral=True)



    # ── /membercheck (admin) ──────────────────────────────
    @bot_instance.hybrid_command(
        name="membercheck",
        description="[Admin] Check membership status of any Discord user"
    )
    @app_commands.describe(member="Discord member to check")
    async def membercheck(ctx, member: discord.Member):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)
        else:
            await ctx.defer(ephemeral=True)

        status = await check_membership(str(member.id))

        if status.get("db_error"):
            embed = discord.Embed(
                title="⚠️  DB Error",
                description=f"Could not fetch data for {member.mention}.",
                color=0xffaa00
            )
            return await ctx.send(embed=embed, ephemeral=True)

        has_acc = status["has_access"]
        color   = 0x00ff88 if has_acc else (0xf0c040 if status["linked"] else 0xff4757)

        embed = discord.Embed(
            title=f"🔍  Member Check  —  {member.display_name}",
            color=color
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="🔗  Link Status",
            value=(
                f"{'✅  Linked' if status['linked'] else '❌  Not Linked'}\n"
                f"**STS ID :** `{status['sts_id'] or '—'}`\n"
                f"**Name   :** {status['name'] or '—'}"
            ),
            inline=True
        )
        embed.add_field(
            name="🎫  Membership",
            value=(
                f"**Access  :** {'✅  Active' if has_acc else '❌  Inactive'}\n"
                f"**Days    :** {status['days_left']}\n"
                f"**Points  :** {status['aero_points']:,}"
            ),
            inline=True
        )
        if status["expires"]:
            embed.add_field(
                name="⏰  Expiry",
                value=status["expires"].astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST"),
                inline=False
            )
        if status.get("error"):
            embed.add_field(name="⚠️  Notice", value=status["error"], inline=False)
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  Admin Panel")
        await ctx.send(embed=embed, ephemeral=True)



    # ── /grantmembership (admin) ──────────────────────────
    @bot_instance.hybrid_command(
        name="grantmembership",
        description="[Admin] Grant free AERION membership to a member"
    )
    @app_commands.describe(member="Discord member", days="Days to grant (default 30)")
    async def grantmembership(ctx, member: discord.Member, days: int = 30):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)
        else:
            await ctx.defer(ephemeral=True)

        status = await check_membership(str(member.id))
        if status.get("error") or status.get("db_error"):
            return await ctx.send(f"❌ Database error: {status.get('error')}", ephemeral=True)

        if not status["linked"]:
            return await ctx.send(
                f"❌ {member.display_name} hasn't linked their portal account yet.",
                ephemeral=True)

        now_utc  = _now_utc()
        expires  = now_utc + timedelta(days=days)
        sts_id   = status["sts_id"]
        txn_id   = _gen_txn_id()

        try:
            patch = {"aerion_access": True, "aerion_expires": expires.isoformat()}
            if status["is_new"]:
                patch["aerion_joined_at"] = now_utc.isoformat()
            await _supabase_patch("share_users", {"sts_id": f"eq.{sts_id}"}, patch)
            try:
                await _supabase_post("point_transactions", {
                    "sts_id":     sts_id,
                    "amount":     0,
                    "reason":     f"Admin grant {days}d | {txn_id} by {ctx.author}",
                    "created_at": now_utc.isoformat(),
                })
            except Exception as tx_err:
                print(f"[MEMBERSHIP] point_transactions log error (non-fatal): {tx_err}")

            dm_sent = await _send_membership_certificate(
                member, sts_id, status["name"], txn_id, 0, expires, status["is_new"]
            )
            exp_str = expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
            embed = discord.Embed(
                title=f"✅  Membership Granted  —  {member.display_name}",
                color=0x00ff88
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(
                name="🎫  Grant Details",
                value=(
                    f"**Member  :** {member.mention}\n"
                    f"**STS ID  :** `{sts_id}`\n"
                    f"**Duration:** {days} days\n"
                    f"**Expires :** {exp_str}"
                ),
                inline=True
            )
            embed.add_field(
                name="🧾  Transaction",
                value=(
                    f"**TXN ID :** `{txn_id}`\n"
                    f"**Cost   :** 0 pts (Admin Grant)\n"
                    f"**DM Cert:** {'✅ Sent' if dm_sent else '❌ DMs off'}"
                ),
                inline=True
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  Admin Action  •  By {ctx.author}")
            await ctx.send(embed=embed, ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Grant failed: {e}", ephemeral=True)

    print("[MEMBERSHIP] Commands registered: /aerion /subscribe /membercheck /grantmembership")


# ─────────────────────────────────────────────────────────
#  SUBSCRIBE CONFIRMATION VIEW
# ─────────────────────────────────────────────────────────
class _SubscribeConfirmView(discord.ui.View):
    def __init__(self, user, is_new, cost, pts, days_left):
        super().__init__(timeout=60)
        self.user      = user
        self.is_new    = is_new
        self.cost      = cost
        self.pts       = pts
        self.days_left = days_left

    @discord.ui.button(label="✅  Confirm & Activate", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "❌ Only the original user can confirm.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        result = await _do_subscribe(self.user)

        if not result["success"]:
            err_embed = discord.Embed(
                title="❌  Activation Failed",
                description=result["message"],
                color=0xff4757
            )
            err_embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
            return await interaction.followup.send(embed=err_embed, ephemeral=True)

        expires_str = result["expires"].astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
        embed = discord.Embed(
            title="🎉  AERION MEMBERSHIP ACTIVATED!",
            description=(
                "```\n"
                "  WELCOME TO THE AERION ECOSYSTEM\n"
                "```\n"
                "You now have full access to all AERION premium features!"
            ),
            color=0x00ff88
        )
        embed.add_field(
            name="💳  Transaction",
            value=(
                f"**TXN ID  :** `{result['txn_id']}`\n"
                f"**Deducted:** `{result['cost']:,}` AERO Points\n"
                f"**Balance :** `{result['new_pts']:,}` AERO Points"
            ),
            inline=True
        )
        embed.add_field(
            name="⏰  Validity",
            value=(
                f"**Expires  :** {expires_str}\n"
                f"**Duration :** {MEMBERSHIP_DAYS} days\n"
                f"**Type     :** {'New Member 🆕' if result['is_new'] else 'Renewal 🔄'}"
            ),
            inline=True
        )
        embed.add_field(
            name="📨  Certificate",
            value=(
                "✅  Sent to your DMs!" if result["dm_sent"]
                else "⚠️  Enable DMs to receive your certificate."
            ),
            inline=False
        )
        embed.add_field(
            name="✨  Access Unlocked",
            value=(
                "┣ AERION Intelligence Suite\n"
                "┣ Alliance Intelligence\n"
                "┣ Advanced Route Analytics\n"
                "┗ All Premium Commands"
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  TXN: {result['txn_id']}")
        self.stop()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌  Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.stop()
        cancel_embed = discord.Embed(
            title="❌  Purchase Cancelled",
            description="No points were deducted. Your balance is unchanged.",
            color=0xff4757
        )
        cancel_embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
        await interaction.response.send_message(embed=cancel_embed, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ─────────────────────────────────────────────────────────
#  GATE ACTION VIEW  (shown when user has no membership)
# ─────────────────────────────────────────────────────────
class _GateActionView(discord.ui.View):
    """Buttons shown on the 'membership required' gate embed."""
    def __init__(self, can_afford: bool = False):
        super().__init__(timeout=60)
        self.can_afford = can_afford

    @discord.ui.button(label="💎  Subscribe Now", style=discord.ButtonStyle.green)
    async def subscribe_btn(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            "Run `/subscribe` to activate your AERION membership!",
            ephemeral=True
        )

    @discord.ui.button(label="📋  How to Earn Points", style=discord.ButtonStyle.blurple)
    async def earn_btn(self, interaction: discord.Interaction, button):
        embed = discord.Embed(
            title="💎  How to Earn AERO Points",
            color=0xf0c040
        )
        embed.add_field(
            name="📊  AERION Commands",
            value=(
                "┣ `/route` — **+3** pts\n"
                "┣ `/best` series — **+2** pts each\n"
                "┣ `/compare`, `/whatif` — **+2–3** pts\n"
                "┗ `/routemap` — **+2** pts"
            ),
            inline=False
        )
        embed.add_field(
            name="🌐  Portal Quests",
            value="Complete quests on the AERO Portal for bonus point rewards.",
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}  •  Points are awarded per command use")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────────────────
#  AERION STATUS VIEW  (buttons on /aerion dashboard)
# ─────────────────────────────────────────────────────────
class _AerionStatusView(discord.ui.View):
    """Action buttons shown on the /aerion membership dashboard."""
    def __init__(self, has_access: bool = False, can_afford: bool = False):
        super().__init__(timeout=120)
        self.has_access = has_access
        self.can_afford = can_afford

    @discord.ui.button(label="🔄  Refresh Status", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button):
        await interaction.response.defer(ephemeral=True)
        status = await check_membership(str(interaction.user.id))
        if status.get("db_error"):
            return await interaction.followup.send(
                "⚠️  Could not refresh — database temporarily unavailable.",
                ephemeral=True
            )
        pts    = status["aero_points"]
        has_ac = status["has_access"]
        days   = status["days_left"]
        exp    = status["expires"]
        exp_str = exp.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST") if exp else "—"
        color  = 0x00ff88 if has_ac else 0xff4757
        embed  = discord.Embed(title="🔄  Status Refreshed", color=color)
        embed.add_field(name="Membership", value=f"{'✅ Active' if has_ac else '❌ Inactive'} — {days}d left", inline=True)
        embed.add_field(name="AERO Points", value=f"`{pts:,}`", inline=True)
        embed.add_field(name="Expires", value=exp_str, inline=False)
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="💎  Subscribe / Renew", style=discord.ButtonStyle.green)
    async def subscribe_btn(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            "Run **`/subscribe`** to activate or renew your AERION membership!",
            ephemeral=True
        )

    @discord.ui.button(label="💡  Earn Points", style=discord.ButtonStyle.blurple)
    async def earn_btn(self, interaction: discord.Interaction, button):
        embed = discord.Embed(title="💎  How to Earn AERO Points", color=0xf0c040)
        embed.add_field(
            name="📊  Commands",
            value=(
                "┣ `/route` — **+3** pts\n"
                "┣ `/best` — **+2** pts\n"
                "┣ `/compare`, `/whatif` — **+2–3** pts\n"
                "┗ `/routemap` — **+2** pts"
            ),
            inline=False
        )
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

