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
    Shows a helpful embed with how to subscribe.
    """
    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        # Acknowledge Discord interaction immediately if within a slash command interaction
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            try:
                await ctx.defer(ephemeral=True)
            except Exception:
                pass

        status = await check_membership(str(ctx.author.id))

        if status.get("error") or status.get("db_error"):
            embed = discord.Embed(
                title="⚠️ Portal Connection Error",
                description=(
                    "Could not verify your membership right now due to a temporary database connection error.\n\n"
                    "Please try again in a few moments."
                ),
                color=0xffaa00
            )
            embed.set_footer(text=f"{BOT_NAME} • {BOT_TAGLINE}")
            try:
                await ctx.send(embed=embed, ephemeral=True)
            except Exception:
                await ctx.send(embed=embed)
            return

        if not status["linked"]:
            embed = discord.Embed(
                title="🔗 Not Linked to AERION Portal",
                description=(
                    "You need to link your portal account first.\n\n"
                    "**Steps:**\n"
                    "1. Go to the AERO portal\n"
                    "2. Generate a link code from your profile\n"
                    "3. Use `/link <code>` here\n"
                    "4. Then subscribe with `/subscribe`"
                ),
                color=0xff4757
            )
            embed.set_footer(text=f"{BOT_NAME} • {BOT_TAGLINE}")
            try:
                await ctx.send(embed=embed, ephemeral=True)
            except Exception:
                await ctx.send(embed=embed)
            return

        if not status["has_access"]:
            cost = MEMBERSHIP_NEW_COST if status["is_new"] else MEMBERSHIP_RENEWAL_COST
            pts  = status["aero_points"]
            can_afford = pts >= cost

            embed = discord.Embed(
                title="🔒 AERION MEMBERSHIP REQUIRED",
                description=(
                    f"**Please purchase a membership to use the AERION ecosystem.**\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{'🆕 First-time join' if status['is_new'] else '🔄 Renewal'}\n"
                    f"Cost    : **{cost:,} AERO Points**\n"
                    f"Your Bal: **{pts:,} AERO Points**"
                    + (f"\n\n✅ You can afford this! Use `/subscribe` to activate."
                       if can_afford
                       else f"\n\n❌ Insufficient points. Need {cost-pts:,} more.\n"
                            f"Earn points by using the portal or completing quests.")
                    + "\n━━━━━━━━━━━━━━━━━━━━━━━"
                ),
                color=0xff4757
            )
            embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION} • {BOT_TAGLINE}")
            try:
                await ctx.send(embed=embed, ephemeral=True)
            except Exception:
                await ctx.send(embed=embed)
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
    """DM the user a beautifully formatted membership certificate."""
    issued = _now_ist().strftime("%d %b %Y  %I:%M %p IST")
    exp_str= expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
    kind   = "FOUNDING MEMBER CERTIFICATE" if is_new else "RENEWAL CERTIFICATE"

    embed = discord.Embed(
        title=f"🎫 {BOT_NAME} MEMBERSHIP — {kind}",
        color=0x00e5ff
    )
    embed.description = (
        f"```\n"
        f"╔══════════════════════════════════════╗\n"
        f"║     AERION ECOSYSTEM MEMBERSHIP      ║\n"
        f"║     {BOT_VERSION:<36}║\n"
        f"╚══════════════════════════════════════╝\n"
        f"```"
    )
    embed.add_field(
        name="👤 Member Details",
        value=(
            f"**Name :** {name}\n"
            f"**STS ID:** `{sts_id}`\n"
            f"**Discord:** {discord_user.mention}"
        ),
        inline=False
    )
    embed.add_field(
        name="🎫 Membership Info",
        value=(
            f"**Type    :** {'New Member' if is_new else 'Renewal'}\n"
            f"**Duration:** {MEMBERSHIP_DAYS} days\n"
            f"**Issued  :** {issued}\n"
            f"**Expires :** {exp_str}"
        ),
        inline=False
    )
    embed.add_field(
        name="🧾 Transaction",
        value=(
            f"**TXN ID :** `{txn_id}`\n"
            f"**Amount :** {cost:,} AERO Points\n"
            f"**Status :** ✅ CONFIRMED"
        ),
        inline=False
    )
    embed.add_field(
        name="✨ Access Granted",
        value=(
            "• All AERION Intelligence commands\n"
            "• Alliance Intelligence suite\n"
            "• Smart Monitoring & Alerts\n"
            "• Player Progression system\n"
            "• Advanced AM4 analytics"
        ),
        inline=False
    )
    embed.set_footer(text=f"{BOT_NAME} • {BOT_TAGLINE} • TXN: {txn_id}")

    try:
        await discord_user.send(
            content=(
                f"🎉 **Welcome to {BOT_NAME}{'!' if is_new else ' — Membership Renewed!'}** "
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

        color = 0x00ff88 if has_acc else 0xff4757
        status_text = (
            f"✅ **ACTIVE** — {days} day(s) remaining"
            if has_acc else
            "❌ **INACTIVE** — Purchase membership to access AERION"
        )

        exp_str = (
            expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
            if expires else "—"
        )

        embed = discord.Embed(
            title=f"🤖 {BOT_NAME} — Membership Status",
            color=color
        )
        embed.add_field(name="👤 Profile",
            value=(
                f"**Name  :** {status['name']}\n"
                f"**STS ID:** `{status['sts_id']}`\n"
                f"**Points:** {pts:,} AERO"
            ), inline=False)
        embed.add_field(name="🎫 Membership",
            value=(
                f"**Status  :** {status_text}\n"
                f"**Expires :** {exp_str}\n"
                f"**Type    :** {'New Member' if is_new else 'Renewal'}"
            ), inline=False)

        if not has_acc:
            can_afford = pts >= cost
            embed.add_field(
                name=f"{'🆕 Join' if is_new else '🔄 Renew'} AERION",
                value=(
                    f"Cost: **{cost:,} AERO Points**\n"
                    + ("✅ You can afford this! Use `/subscribe`"
                       if can_afford
                       else f"❌ Need {cost-pts:,} more points. Earn via portal quests.")
                ), inline=False)

        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION} • {BOT_TAGLINE}")
        await ctx.send(embed=embed, ephemeral=True)

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
            return await ctx.send(
                "⚠️ Could not connect to portal database. Please try again shortly.",
                ephemeral=True
            )

        if not status["linked"]:
            return await ctx.send(
                "❌ Link your Discord first with `/link <code>`.",
                ephemeral=True
            )

        is_new  = status["is_new"]
        cost    = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
        pts     = status["aero_points"]
        days    = status["days_left"]

        # Build confirmation view
        view = _SubscribeConfirmView(ctx.author, is_new, cost, pts, days)
        embed = discord.Embed(
            title=f"{'🆕 JOIN' if is_new else '🔄 RENEW'} — AERION MEMBERSHIP",
            color=0x00d4ff
        )
        embed.add_field(name="📋 Summary",
            value=(
                f"**Type     :** {'First-time join' if is_new else 'Renewal'}\n"
                f"**Cost     :** {cost:,} AERO Points\n"
                f"**Duration :** {MEMBERSHIP_DAYS} days\n"
                f"**Your Bal :** {pts:,} AERO Points\n"
                f"**After    :** {pts-cost:,} AERO Points"
                + (f"\n**Extends  :** +{MEMBERSHIP_DAYS} days (currently {days}d left)"
                   if not is_new and days > 0 else "")
            ), inline=False)

        if pts < cost:
            embed.add_field(
                name="❌ Insufficient Points",
                value=(
                    f"You need {cost-pts:,} more AERO Points.\n"
                    "Earn points by using the portal or completing quests."
                ), inline=False)
            return await ctx.send(embed=embed, ephemeral=True)

        embed.add_field(name="⚠️ Confirm",
            value="Press **Confirm** to deduct points and activate membership.\n"
                  "A certificate will be DM'd to you.", inline=False)
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
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
        color  = 0x00ff88 if status["has_access"] else 0xff4757

        embed = discord.Embed(
            title=f"🔍 Membership Check — {member.display_name}",
            color=color
        )
        embed.add_field(name="Linked",    value="✅" if status["linked"]     else "❌", inline=True)
        embed.add_field(name="Access",    value="✅" if status["has_access"] else "❌", inline=True)
        embed.add_field(name="Days Left", value=str(status["days_left"]),               inline=True)
        if status["sts_id"]:
            embed.add_field(name="STS ID",     value=f"`{status['sts_id']}`",           inline=True)
            embed.add_field(name="Name",       value=status["name"] or "—",             inline=True)
            embed.add_field(name="AERO Points",value=f"{status['aero_points']:,}",      inline=True)
        if status["expires"]:
            embed.add_field(name="Expires",
                value=status["expires"].astimezone(_IST).strftime("%d %b %Y %I:%M %p IST"),
                inline=False)
        if status.get("error"):
            embed.add_field(name="Error Notice", value=f"⚠️ {status['error']}", inline=False)
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION}")
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
            await ctx.send(
                f"✅ Granted **{days}d** AERION membership to {member.mention}.\n"
                f"TXN: `{txn_id}` | DM sent: {'✅' if dm_sent else '❌ (DMs off)'}",
                ephemeral=True
            )
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

    @discord.ui.button(label="✅ Confirm Purchase", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message(
                "❌ Only the original user can confirm.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        result = await _do_subscribe(self.user)

        if not result["success"]:
            return await interaction.followup.send(result["message"], ephemeral=True)

        expires_str = result["expires"].astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
        embed = discord.Embed(
            title=f"🎉 AERION MEMBERSHIP ACTIVATED!",
            color=0x00ff88
        )
        embed.add_field(name="✅ Status",
            value=(
                f"**TXN ID  :** `{result['txn_id']}`\n"
                f"**Deducted:** {result['cost']:,} AERO Points\n"
                f"**Balance :** {result['new_pts']:,} AERO Points\n"
                f"**Expires :** {expires_str}"
            ), inline=False)
        embed.add_field(name="📨 Certificate",
            value=("✅ Sent to your DMs!"
                   if result["dm_sent"]
                   else "⚠️ Couldn't DM you — enable DMs to receive certificate."),
            inline=False)
        embed.set_footer(text=f"{BOT_NAME} {BOT_VERSION} • TXN: {result['txn_id']}")
        self.stop()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.stop()
        await interaction.response.send_message(
            "❌ Subscription cancelled. No points deducted.", ephemeral=True)
