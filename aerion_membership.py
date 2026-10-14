# =========================================================
#  aerion_membership.py  —  AERION Membership System
# =========================================================

import os, uuid, random, string, asyncio, functools, math
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
import pytz

_IST = pytz.timezone("Asia/Kolkata")

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

def set_supabase_refs(supa_get, supa_post=None, supa_patch=None):
    """Set Supabase database helpers so check_membership is immediately usable."""
    global _supabase_get, _supabase_post, _supabase_patch
    _supabase_get = supa_get
    if supa_post is not None:
        _supabase_post = supa_post
    if supa_patch is not None:
        _supabase_patch = supa_patch

def _now_utc():  return datetime.now(timezone.utc)
def _now_ist():  return datetime.now(_IST)

# ─────────────────────────────────────────────────────────
#  TRANSACTION ID GENERATOR
# ─────────────────────────────────────────────────────────
def _gen_txn_id() -> str:
    chars = string.ascii_uppercase + string.digits
    suffix = ''.join(random.choices(chars, k=8))
    return f"AER-{suffix}"

# ─────────────────────────────────────────────────────────
#  MEMBERSHIP CHECK
# ─────────────────────────────────────────────────────────
async def check_membership(discord_id: str) -> dict:
    result = {
        "linked": False, "has_access": False, "is_new": True,
        "sts_id": None, "name": None, "aero_points": 0,
        "expires": None, "days_left": 0, "row": None,
        "db_error": False, "error": None,
    }
    disc_id_str = str(discord_id or "").strip()
    if not disc_id_str:
        return result

    if _supabase_get is None:
        print(f"[MEMBERSHIP] Warning: _supabase_get not initialized for check_membership({disc_id_str})")
        result["db_error"] = True
        result["error"] = "Database connection not initialized"
        return result

    try:
        rows = await _supabase_get("share_users", {
            "discord_id": f"eq.{disc_id_str}",
            "select": "sts_id,name,aero_points,aerion_access,"
                      "aerion_expires,aerion_joined_at,airline,alliance",
        })
        if not rows:
            return result

        active_candidates = [
            r for r in rows
            if (bool(r.get("aerion_access")) or str(r.get("aerion_access")).lower() in ("true", "1", "t"))
        ]
        row = active_candidates[0] if active_candidates else rows[0]

        result["linked"]      = True
        result["row"]         = row
        result["sts_id"]      = row.get("sts_id")
        result["name"]        = row.get("name") or row.get("sts_id")
        result["aero_points"] = int(row.get("aero_points") or 0)
        result["is_new"]      = not bool(row.get("aerion_joined_at"))

        raw_access = row.get("aerion_access")
        access_flag = bool(raw_access) or str(raw_access).lower() in ("true", "1", "t")

        expires_raw = row.get("aerion_expires")
        if expires_raw:
            try:
                expires_dt = datetime.fromisoformat(
                    str(expires_raw).replace("Z", "+00:00"))
                result["expires"] = expires_dt
                time_left_sec = (expires_dt - _now_utc()).total_seconds()
                result["days_left"] = max(0, math.ceil(time_left_sec / 86400))
                if access_flag and time_left_sec > 0:
                    result["has_access"] = True
            except Exception as e:
                print(f"[MEMBERSHIP] expires parse error for {disc_id_str}: {e}")
                if access_flag:
                    result["has_access"] = True
        else:
            if access_flag:
                result["has_access"] = True
                result["days_left"] = 9999

    except Exception as e:
        print(f"[MEMBERSHIP] check_membership error for {disc_id_str}: {e}")
        result["db_error"] = True
        result["error"] = str(e)

    return result

# ─────────────────────────────────────────────────────────
#  MEMBERSHIP REQUIRED DECORATOR
# ─────────────────────────────────────────────────────────
def membership_required(func):
    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        if hasattr(ctx, "defer"):
            try:
                interaction = getattr(ctx, "interaction", None)
                if interaction and not interaction.response.is_done():
                    await ctx.defer(ephemeral=True)
            except Exception:
                pass

        status = await check_membership(str(ctx.author.id))

        if status.get("db_error"):
            embed = discord.Embed(
                title="⚠️ Portal Connection Error",
                description="Unable to verify membership status right now. Please try again shortly.",
                color=0xffa502
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
                    "2. Generate a link code\n"
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
    issued = _now_ist().strftime("%d %b %Y  %I:%M %p IST")
    exp_str= expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST")
    kind   = "FOUNDING MEMBER CERTIFICATE" if is_new else "RENEWAL CERTIFICATE"

    embed = discord.Embed(
        title=f"🎫 {BOT_NAME} MEMBERSHIP — {kind}",
        color=0x00e5ff
    )
    embed.add_field(
        name="👤 Member Details",
        value=f"**Name :** {name}\n**STS ID:** `{sts_id}`\n**Discord:** {discord_user.mention}",
        inline=False
    )
    embed.add_field(
        name="🎫 Membership Info",
        value=f"**Type    :** {'New Member' if is_new else 'Renewal'}\n**Duration:** {MEMBERSHIP_DAYS} days\n**Issued  :** {issued}\n**Expires :** {exp_str}",
        inline=False
    )
    embed.add_field(
        name="🧾 Transaction",
        value=f"**TXN ID :** `{txn_id}`\n**Amount :** {cost:,} AERO Points\n**Status :** ✅ CONFIRMED",
        inline=False
    )
    embed.set_footer(text=f"{BOT_NAME} • {BOT_TAGLINE} • TXN: {txn_id}")
    try:
        await discord_user.send(content=f"🎉 **Welcome to {BOT_NAME}!**", embed=embed)
        return True
    except Exception:
        return False

# ─────────────────────────────────────────────────────────
#  SUBSCRIBE LOGIC
# ─────────────────────────────────────────────────────────
async def _do_subscribe(discord_user) -> dict:
    uid = str(discord_user.id)
    status = await check_membership(uid)

    if not status["linked"]:
        return {"success": False, "message": "❌ Link your Discord to the portal first with `/link <code>`"}

    is_new  = status["is_new"]
    cost    = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
    pts     = status["aero_points"]
    sts_id  = status["sts_id"]
    name    = status["name"]

    if pts < cost:
        return {"success": False, "message": f"❌ Insufficient Points. Need {cost:,}, you have {pts:,}."}

    now_utc = _now_utc()
    if not is_new and status["expires"] and status["expires"] > now_utc:
        expires = status["expires"] + timedelta(days=MEMBERSHIP_DAYS)
    else:
        expires = now_utc + timedelta(days=MEMBERSHIP_DAYS)

    new_pts = pts - cost
    txn_id  = _gen_txn_id()

    try:
        patch_data = {
            "aero_points":   new_pts,
            "aerion_access": True,
            "aerion_expires": expires.isoformat(),
        }
        if is_new:
            patch_data["aerion_joined_at"] = now_utc.isoformat()

        await _supabase_patch("share_users", {"sts_id": f"eq.{sts_id}"}, patch_data)
        await _supabase_post("point_transactions", {
            "sts_id":     sts_id,
            "amount":     -cost,
            "reason":     f"AERION Membership {'Join' if is_new else 'Renewal'} | {txn_id}",
            "created_at": now_utc.isoformat(),
        })

        dm_sent = await _send_membership_certificate(discord_user, sts_id, name, txn_id, cost, expires, is_new)
        return {
            "success": True, "message": "✅ Membership activated!", "txn_id": txn_id,
            "expires": expires, "cost": cost, "dm_sent": dm_sent, "new_pts": new_pts,
            "is_new": is_new, "name": name, "sts_id": sts_id,
        }
    except Exception as e:
        print(f"[MEMBERSHIP] subscribe error for {uid}: {e}")
        return {"success": False, "message": f"❌ Error: {e}"}

# ─────────────────────────────────────────────────────────
#  REGISTER COMMANDS
# ─────────────────────────────────────────────────────────
def register_membership_commands(bot_instance, supa_get, supa_post, supa_patch):
    global _bot, _supabase_get, _supabase_post, _supabase_patch
    _bot           = bot_instance
    _supabase_get  = supa_get
    _supabase_post = supa_post
    _supabase_patch= supa_patch
    print("[MEMBERSHIP] Module loaded and database references wired")

    if bot_instance.get_command("aerion") is None:
        @bot_instance.hybrid_command(name="aerion", description="Check your AERION membership status")
        async def aerion_status(ctx):
            await ctx.defer(ephemeral=True)
            status = await check_membership(str(ctx.author.id))

            if status.get("db_error"):
                embed = discord.Embed(
                    title=f"⚠️ {BOT_NAME} — Portal Connection Error",
                    description="Unable to verify membership status right now. Please try again shortly.",
                    color=0xffa502
                )
                return await ctx.send(embed=embed, ephemeral=True)

            if not status["linked"]:
                embed = discord.Embed(
                    title=f"🔗 {BOT_NAME} — Not Linked",
                    description="Your Discord account isn't linked to the AERO portal yet.\n\nUse `/link <code>` to link.",
                    color=0xff4757
                )
                return await ctx.send(embed=embed, ephemeral=True)

            pts      = status["aero_points"]
            has_acc  = status["has_access"]
            days     = status["days_left"]
            is_new   = status["is_new"]
            cost     = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
            expires  = status["expires"]

            color = 0x00ff88 if has_acc else 0xff4757
            status_text = f"✅ **ACTIVE** — {days} day(s) remaining" if has_acc else "❌ **INACTIVE**"
            exp_str = expires.astimezone(_IST).strftime("%d %b %Y  %I:%M %p IST") if expires else ("Permanent" if has_acc else "—")

            embed = discord.Embed(title=f"🤖 {BOT_NAME} — Membership Status", color=color)
            embed.add_field(name="👤 Profile", value=f"**Name  :** {status['name']}\n**STS ID:** `{status['sts_id']}`\n**Points:** {pts:,} AERO", inline=False)
            embed.add_field(name="🎫 Membership", value=f"**Status  :** {status_text}\n**Expires :** {exp_str}\n**Type    :** {'New Member' if is_new else 'Renewal'}", inline=False)

            if not has_acc:
                can_afford = pts >= cost
                embed.add_field(name=f"{'🆕 Join' if is_new else '🔄 Renew'} AERION", value=f"Cost: **{cost:,} AERO Points**\n" + ("✅ Use `/subscribe`" if can_afford else f"❌ Need {cost-pts:,} more points."), inline=False)

            await ctx.send(embed=embed, ephemeral=True)

    if bot_instance.get_command("subscribe") is None:
        @bot_instance.hybrid_command(name="subscribe", description="Activate or renew AERION membership")
        async def subscribe(ctx):
            await ctx.defer(ephemeral=True)
            status = await check_membership(str(ctx.author.id))
            if not status["linked"]:
                return await ctx.send("❌ Link your Discord first with `/link <code>`.", ephemeral=True)
            is_new  = status["is_new"]
            cost    = MEMBERSHIP_NEW_COST if is_new else MEMBERSHIP_RENEWAL_COST
            pts     = status["aero_points"]
            days    = status["days_left"]
            view = _SubscribeConfirmView(ctx.author, is_new, cost, pts, days)
            embed = discord.Embed(title="AERION MEMBERSHIP", color=0x00d4ff)
            embed.add_field(name="Cost", value=f"{cost:,} AERO Points", inline=True)
            embed.add_field(name="Balance", value=f"{pts:,} AERO Points", inline=True)
            await ctx.send(embed=embed, view=view, ephemeral=True)

    print("[MEMBERSHIP] Commands registered: /aerion /subscribe")

class _SubscribeConfirmView(discord.ui.View):
    def __init__(self, user, is_new, cost, pts, days_left):
        super().__init__(timeout=60)
        self.user = user; self.cost = cost; self.pts = pts
    @discord.ui.button(label="✅ Confirm Purchase", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user.id: return
        await interaction.response.defer(ephemeral=True)
        res = await _do_subscribe(self.user)
        await interaction.followup.send(res["message"], ephemeral=True)
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button):
        await interaction.response.send_message("❌ Cancelled.", ephemeral=True)
