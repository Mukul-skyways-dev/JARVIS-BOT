# =========================================================
#  am4_agent.py  —  JARVIS AM4 Automation Module
#
#  USAGE in bot1__9_.py:
#    from am4_agent import setup_agent
#    # inside on_ready():
#    setup_agent(bot, supabase_get, supabase_post)
#
#  ENV VARS needed:
#    AM4_EMAIL       — AM4 login email
#    AM4_PASSWORD    — AM4 login password
#    AGENT_CHANNEL   — Discord channel ID for results
# =========================================================

import os
import re
import json
import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
import pytz

# ── Constants ─────────────────────────────────────────────
_IST = pytz.timezone("Asia/Kolkata")
_AM4_URL = "https://www.airlinemanager.com"

# ── State (module-level) ──────────────────────────────────
_state = {
    "running":       False,
    "last_run":      None,   # datetime IST
    "log":           [],     # list of result dicts
    "schedule_h":    0,      # 0 = disabled
}

# ── Injected references (set by setup_agent) ──────────────
_bot          = None
_supabase_get = None
_supabase_post= None

def setup_agent(bot_instance, supa_get_fn, supa_post_fn):
    """
    Call this inside on_ready() to wire the agent into JARVIS.

    Example:
        from am4_agent import setup_agent
        @bot.event
        async def on_ready():
            ...
            setup_agent(bot, supabase_get, supabase_post)
    """
    global _bot, _supabase_get, _supabase_post
    _bot           = bot_instance
    _supabase_get  = supa_get_fn
    _supabase_post = supa_post_fn

    # Register slash commands onto the bot
    _register_commands(bot_instance)

    # Start background auto-loop
    bot_instance.loop.create_task(_auto_loop())
    print("[AM4 AGENT] Module loaded — commands registered, auto-loop started")


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────
def _now_ist():
    return datetime.now(_IST)

def _today_ist():
    return _now_ist().strftime("%Y-%m-%d")

def _fmt(v):
    """Float → readable money string."""
    try:
        v = float(v)
        if v >= 1e9: return f"${v/1e9:.3f}B"
        if v >= 1e6: return f"${v/1e6:.2f}M"
        if v >= 1e3: return f"${v/1e3:.1f}K"
        return f"${v:,.0f}"
    except:
        return str(v)

def _parse(s):
    """'5.2B' / '$500M' / '1,234' → float."""
    try:
        s = str(s).replace("$", "").replace(",", "").strip().upper()
        if s.endswith("B"): return float(s[:-1]) * 1e9
        if s.endswith("M"): return float(s[:-1]) * 1e6
        if s.endswith("K"): return float(s[:-1]) * 1e3
        return float(s)
    except:
        return 0.0

def _env(key):
    return os.getenv(key, "")

def _agent_ch_id():
    try: return int(_env("AGENT_CHANNEL"))
    except: return 0


# ─────────────────────────────────────────────────────────
#  SUPABASE WRAPPERS
# ─────────────────────────────────────────────────────────
async def _find_by_airline(airline: str):
    """
    Match airline name from AM4 → share_users row.
    Tries ilike (contains, case-insensitive) first, then exact.
    """
    if not _supabase_get:
        return None
    name = airline.strip()
    # ilike search
    try:
        rows = await _supabase_get("share_users", {
            "airline": f"ilike.*{name}*",
            "select":  "sts_id,name,airline,alliance,discord_id",
        })
        if rows:
            return rows[0]
    except Exception as e:
        print(f"[AGENT] ilike search error for '{name}': {e}")

    # fallback: exact match
    try:
        rows = await _supabase_get("share_users", {
            "airline": f"eq.{name}",
            "select":  "sts_id,name,airline,alliance,discord_id",
        })
        if rows:
            return rows[0]
    except Exception as e:
        print(f"[AGENT] exact search error for '{name}': {e}")

    return None


async def _already_submitted(sts_id: str, alliance: str) -> bool:
    """Return True if this STS has an entry for today in share_entries."""
    if not _supabase_get:
        return False
    try:
        rows = await _supabase_get("share_entries", {
            "sts_id":   f"eq.{sts_id}",
            "alliance": f"eq.{alliance}",
            "select":   "id,created_at",
        })
        today = _today_ist()
        for r in rows:
            day = datetime.fromisoformat(
                r["created_at"].replace("Z", "+00:00")
            ).astimezone(_IST).strftime("%Y-%m-%d")
            if day == today:
                return True
    except Exception as e:
        print(f"[AGENT] already_submitted check error: {e}")
    return False


async def _do_submit(sts_id: str, alliance: str, value: float):
    """Insert one row into share_entries."""
    await _supabase_post("share_entries", {
        "sts_id":     sts_id,
        "alliance":   alliance,
        "value":      value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ─────────────────────────────────────────────────────────
#  PLAYWRIGHT: LOGIN
# ─────────────────────────────────────────────────────────
async def _do_login(page) -> bool:
    """
    Navigate to AM4, log in with env credentials.
    Returns True if login succeeded.
    """
    email    = _env("AM4_EMAIL")
    password = _env("AM4_PASSWORD")

    print("[AGENT] Opening AM4...")
    await page.goto(_AM4_URL, wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(3)

    # Dismiss cookie / GDPR banners
    for txt in ["Accept", "I agree", "OK", "Allow", "Accept all"]:
        try:
            await page.click(f"text={txt}", timeout=2_000)
            await asyncio.sleep(1)
            break
        except:
            pass

    # Email
    for sel in ["input[name='email']", "input[type='email']",
                "#email", "#login-email", "[placeholder*='email' i]"]:
        try:
            await page.fill(sel, email, timeout=4_000)
            break
        except:
            pass

    # Password
    for sel in ["input[name='password']", "input[type='password']",
                "#password", "#login-password", "[placeholder*='password' i]"]:
        try:
            await page.fill(sel, password, timeout=4_000)
            break
        except:
            pass

    # Submit
    for sel in ["button[type='submit']", "#loginBtn", ".login-btn",
                "input[type='submit']", "text=Login", "text=Sign In",
                "text=Log In", "[class*='login'][class*='btn']"]:
        try:
            await page.click(sel, timeout=4_000)
            break
        except:
            pass

    await page.wait_for_load_state("networkidle", timeout=25_000)
    await asyncio.sleep(3)
    await page.screenshot(path="/tmp/am4_login.png")
    print(f"[AGENT] Post-login URL: {page.url}")

    url = page.url.lower()
    return "login" not in url and "signin" not in url and "airlinemanager" in url


# ─────────────────────────────────────────────────────────
#  PLAYWRIGHT: NAVIGATE TO ALLIANCE
# ─────────────────────────────────────────────────────────
async def _open_alliance(page) -> bool:
    """
    Try several methods to reach the alliance/members page.
    Returns True when something that looks like member data is visible.
    """
    # Method A: click nav links
    for sel in [
        "text=Alliance", "text=Members", "[href*='alliance']",
        "#allianceBtn", ".alliance-nav", "[class*='alliance'][class*='btn']",
        ".nav-alliance", "text=My Alliance",
    ]:
        try:
            await page.click(sel, timeout=3_000)
            await asyncio.sleep(2)
            print(f"[AGENT] Alliance nav clicked: {sel}")
            break
        except:
            pass

    await asyncio.sleep(2)

    # Method B: direct URL guesses
    if not await _members_visible(page):
        for url in [
            f"{_AM4_URL}/alliance",
            f"{_AM4_URL}/game/alliance",
            f"{_AM4_URL}/#alliance",
            f"{_AM4_URL}/alliance/members",
        ]:
            try:
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=15_000)
                await asyncio.sleep(2)
                if await _members_visible(page):
                    print(f"[AGENT] Alliance page via URL: {url}")
                    break
            except:
                pass

    await page.screenshot(path="/tmp/am4_alliance.png")
    print(f"[AGENT] Alliance page URL: {page.url}")
    return await _members_visible(page)


async def _members_visible(page) -> bool:
    """Quick check if any member-like elements are on the page."""
    for sel in [
        "table tr", ".member-row", ".alliance-member",
        "#memberTable tbody tr", "[class*='member']",
        ".player-row", ".leaderboard-row",
    ]:
        try:
            els = await page.query_selector_all(sel)
            if len(els) > 1:
                return True
        except:
            pass
    return False


# ─────────────────────────────────────────────────────────
#  PLAYWRIGHT: SCRAPE MEMBERS
# ─────────────────────────────────────────────────────────
async def _scrape_members(page) -> list:
    """
    Extract { airline, share_value } for each alliance member.

    Three strategies in priority order:
      1. DOM rows (table / list)
      2. JSON blob embedded in page JS
      3. XHR response intercept (set up before navigation)
    """
    members = []

    # ── Strategy 1: DOM rows ──────────────────────────────
    row_sels = [
        "table tr",
        ".member-row", ".alliance-member",
        "#memberTable tbody tr",
        "[class*='member'][class*='row']",
        ".player-row", ".leaderboard-row",
    ]
    rows = []
    for sel in row_sels:
        try:
            found = await page.query_selector_all(sel)
            if len(found) > 1:
                rows = found
                break
        except:
            pass

    for row in rows:
        try:
            text = (await row.inner_text()).strip()
            if not text or len(text) < 3:
                continue

            # Airline name
            airline = ""
            for name_sel in [
                ".airline-name", ".name", ".player-name",
                "td:nth-child(1)", "td:nth-child(2)",
                "[class*='name']", "[class*='airline']",
            ]:
                try:
                    el = await row.query_selector(name_sel)
                    if el:
                        t = (await el.inner_text()).strip()
                        if t and len(t) > 1:
                            airline = t
                            break
                except:
                    pass

            if not airline:
                airline = text.split("\n")[0].strip()

            if not airline or len(airline) < 2:
                continue

            # Share value
            share_val = 0.0
            for sv_sel in [
                ".share-value", ".shares", ".share",
                "td:nth-child(5)", "td:nth-child(4)", "td:nth-child(6)",
                "[class*='share']", "[class*='value']",
            ]:
                try:
                    el = await row.query_selector(sv_sel)
                    if el:
                        sv = _parse((await el.inner_text()).strip())
                        if sv > 0:
                            share_val = sv
                            break
                except:
                    pass

            # Scan ALL cells for money pattern if still 0
            if share_val == 0:
                cells = await row.query_selector_all("td, .cell, span")
                for cell in cells:
                    ct = (await cell.inner_text()).strip()
                    if re.search(r"[\d\.]+\s*[BMK$]", ct, re.I):
                        sv = _parse(ct)
                        if sv > 0:
                            share_val = sv
                            break

            members.append({"airline": airline, "share_value": share_val})
        except:
            continue

    if members:
        return members

    # ── Strategy 2: JSON in page source ──────────────────
    try:
        html = await page.content()
        patterns = [
            r'allianceMembers\s*=\s*(\[.*?\]);',
            r'"members"\s*:\s*(\[.*?\])',
            r'players\s*=\s*(\[.*?\]);',
            r'memberList\s*=\s*(\[.*?\]);',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                for item in data:
                    airline = (
                        item.get("name") or item.get("airline") or
                        item.get("airline_name") or item.get("companyName") or ""
                    ).strip()
                    sv = float(
                        item.get("shareValue") or item.get("share_value") or
                        item.get("shares") or item.get("stockValue") or 0
                    )
                    if airline:
                        members.append({"airline": airline, "share_value": sv})
                if members:
                    print(f"[AGENT] Extracted {len(members)} members via JSON pattern")
                    return members
    except Exception as e:
        print(f"[AGENT] JSON strategy error: {e}")

    return members


async def _get_alliance_name(page) -> str:
    for sel in [
        ".alliance-name", "#allianceName", ".alliance-title",
        ".alliance-header h1", ".alliance-header h2",
        "h1", "h2", ".title",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                t = (await el.inner_text()).strip()
                if t and len(t) > 1:
                    return t
        except:
            pass
    return "AERO ETERNAL CORP"


# ─────────────────────────────────────────────────────────
#  CORE RUN FUNCTION
# ─────────────────────────────────────────────────────────
async def run_agent() -> list:
    """
    Full cycle:
      login → alliance page → scrape → match STS → submit entries

    Returns list of result dicts:
      { airline, sts_id, value, status }
    status values:
      'submitted'   — new entry posted to portal
      'already_done'— entry already exists for today
      'no_match'    — airline name not found in share_users
      'error:<msg>' — submission failed
      'FATAL:<msg>' — crash at login/navigation level
    """
    if _state["running"]:
        return []

    _state["running"] = True
    results = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = await ctx.new_page()

            # ── Login ──────────────────────────────────────
            login_ok = await _do_login(page)
            if not login_ok:
                results.append({
                    "airline": "—", "sts_id": "—", "value": 0,
                    "status": (
                        "FATAL: Login failed — check AM4_EMAIL / AM4_PASSWORD.\n"
                        "Debug screenshot: /tmp/am4_login.png\n"
                        "Use /agentdebug to view it in Discord."
                    ),
                })
                await browser.close()
                return results

            # ── Alliance page ──────────────────────────────
            alliance_ok = await _open_alliance(page)
            if not alliance_ok:
                results.append({
                    "airline": "—", "sts_id": "—", "value": 0,
                    "status": (
                        "FATAL: Alliance page not found / members not visible.\n"
                        "Debug screenshot: /tmp/am4_alliance.png\n"
                        "Use /agentdebug — send the screenshot to update selectors."
                    ),
                })
                await browser.close()
                return results

            # ── Scrape ─────────────────────────────────────
            members = await _scrape_members(page)
            alliance_name = await _get_alliance_name(page)
            print(f"[AGENT] Alliance: {alliance_name} | Members: {len(members)}")

            if not members:
                results.append({
                    "airline": "—", "sts_id": "—", "value": 0,
                    "status": (
                        "FATAL: No members scraped from alliance page.\n"
                        "Use /agentdebug and share screenshot for selector fix."
                    ),
                })
                await browser.close()
                return results

            # ── Match + Submit ─────────────────────────────
            for m in members:
                airline   = (m.get("airline") or "").strip()
                share_val = m.get("share_value", 0.0)

                if not airline:
                    continue

                portal_user = await _find_by_airline(airline)

                if not portal_user:
                    results.append({
                        "airline": airline, "sts_id": "—",
                        "value": share_val, "status": "no_match",
                    })
                    continue

                sts_id       = portal_user["sts_id"]
                player_allia = portal_user.get("alliance") or alliance_name

                if await _already_submitted(sts_id, player_allia):
                    results.append({
                        "airline": airline, "sts_id": sts_id,
                        "value": share_val, "status": "already_done",
                    })
                    continue

                try:
                    await _do_submit(sts_id, player_allia, share_val)
                    results.append({
                        "airline": airline, "sts_id": sts_id,
                        "value": share_val, "status": "submitted",
                    })
                    print(f"[AGENT] ✅ {airline} → {sts_id} → {_fmt(share_val)}")

                    # DM the player if Discord linked
                    disc_id = portal_user.get("discord_id")
                    if disc_id and _bot:
                        try:
                            du = await _bot.fetch_user(int(disc_id))
                            await du.send(
                                f"📤 **JARVIS Auto-Submitted** your share entry!\n"
                                f"Alliance : **{player_allia}**\n"
                                f"Value    : **{_fmt(share_val)}**\n"
                                f"`{_now_ist().strftime('%d %b %Y  %I:%M %p IST')}`"
                            )
                        except Exception as dm_err:
                            print(f"[AGENT] DM failed {disc_id}: {dm_err}")

                except Exception as sub_err:
                    results.append({
                        "airline": airline, "sts_id": sts_id,
                        "value": share_val, "status": f"error:{sub_err}",
                    })

            await browser.close()

    except Exception as fatal:
        print(f"[AGENT] FATAL: {fatal}")
        results.append({
            "airline": "—", "sts_id": "—", "value": 0,
            "status": f"FATAL:{fatal}",
        })
    finally:
        _state["running"]  = False
        _state["last_run"] = _now_ist()
        _state["log"]      = results

    return results


# ─────────────────────────────────────────────────────────
#  BACKGROUND AUTO-LOOP
# ─────────────────────────────────────────────────────────
async def _auto_loop():
    await _bot.wait_until_ready()
    print("[AGENT] Auto-loop running")
    while not _bot.is_closed():
        await asyncio.sleep(3600)   # check every hour
        h = _state.get("schedule_h", 0)
        if h <= 0:
            continue
        last = _state.get("last_run")
        if last:
            elapsed_h = (_now_ist() - last).total_seconds() / 3600
            if elapsed_h < h:
                continue
        print(f"[AGENT] Auto-run triggered (every {h}h)")
        ch_id = _agent_ch_id()
        ch = _bot.get_channel(ch_id) if ch_id else None
        if ch:
            await ch.send(
                f"🤖 **JARVIS Agent auto-run...** (scheduled every {h}h)"
            )
        results = await run_agent()
        if ch and results:
            await _post_results(ch, results)


# ─────────────────────────────────────────────────────────
#  RESULT EMBED
# ─────────────────────────────────────────────────────────
async def _post_results(channel, results: list):
    submitted = [r for r in results if r["status"] == "submitted"]
    already   = [r for r in results if r["status"] == "already_done"]
    no_match  = [r for r in results if r["status"] == "no_match"]
    errors    = [r for r in results
                 if r["status"] not in ("submitted", "already_done", "no_match")]

    color = 0x00ff88 if submitted else (0xffa502 if already else 0xff4757)

    embed = discord.Embed(
        title="🤖 JARVIS AM4 Agent — Run Complete",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="✅ Submitted",    value=str(len(submitted)), inline=True)
    embed.add_field(name="⏭ Already Done", value=str(len(already)),   inline=True)
    embed.add_field(name="❓ No Match",    value=str(len(no_match)),   inline=True)

    if submitted:
        lines = [
            f"• **{r['airline']}** (`{r['sts_id']}`) → {_fmt(r['value'])}"
            for r in submitted[:10]
        ]
        if len(submitted) > 10:
            lines.append(f"*...and {len(submitted) - 10} more*")
        embed.add_field(name="Submitted Entries",
                        value="\n".join(lines), inline=False)

    if no_match:
        lines = [f"• {r['airline']}" for r in no_match[:8]]
        embed.add_field(
            name="⚠️ No STS Match — tell these players to set their exact airline name on the portal",
            value="\n".join(lines), inline=False,
        )

    if errors:
        lines = [f"• {r['status']}" for r in errors[:3]]
        embed.add_field(name="❌ Errors", value="\n".join(lines), inline=False)

    embed.set_footer(text="JARVIS • AM4 Portal Agent")
    await channel.send(embed=embed)


# ─────────────────────────────────────────────────────────
#  DISCORD COMMANDS  (registered via setup_agent)
# ─────────────────────────────────────────────────────────
def _register_commands(bot):

    @bot.hybrid_command(
        name="agentrun",
        description="[Admin] Login to AM4, scrape alliance, auto-submit share entries to portal",
    )
    async def agentrun(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)

        if _state["running"]:
            return await ctx.send(
                "⚠️ Agent already running. Use `/agentstatus`.", ephemeral=True
            )

        if not _env("AM4_EMAIL") or not _env("AM4_PASSWORD"):
            return await ctx.send(
                "❌ `AM4_EMAIL` and `AM4_PASSWORD` env vars not set in Render.",
                ephemeral=True,
            )

        await ctx.send(
            "🤖 **JARVIS Agent Starting...**\n"
            "→ Logging into AM4\n"
            "→ Scraping alliance member list\n"
            "→ Matching airline names → STS IDs on portal\n"
            "→ Auto-submitting share entries\n\n"
            "*Takes ~60-90 sec. Results will post here.*"
        )

        async def _run():
            results = await run_agent()
            await _post_results(ctx.channel, results)

        asyncio.create_task(_run())

    # ── /agentstatus ──────────────────────────────────────
    @bot.hybrid_command(
        name="agentstatus",
        description="Check AM4 agent status and last run summary",
    )
    async def agentstatus(ctx):
        embed = discord.Embed(title="🤖 JARVIS AM4 Agent", color=0x00d4ff)

        if _state["running"]:
            embed.description = "⚙️ **Currently running...** scan in progress"
            embed.color = 0xffa502

        elif _state["last_run"]:
            embed.description = (
                f"✅ Last run: "
                f"`{_state['last_run'].strftime('%d %b %Y  %I:%M %p IST')}`"
            )
            log = _state["log"]
            if log:
                sub = sum(1 for r in log if r["status"] == "submitted")
                don = sum(1 for r in log if r["status"] == "already_done")
                nm  = sum(1 for r in log if r["status"] == "no_match")
                err = sum(1 for r in log
                          if r["status"] not in
                          ("submitted", "already_done", "no_match"))
                embed.add_field(name="✅ Submitted",    value=str(sub), inline=True)
                embed.add_field(name="⏭ Already Done", value=str(don), inline=True)
                embed.add_field(name="❓ No Match",    value=str(nm),  inline=True)
                embed.add_field(name="❌ Errors",      value=str(err), inline=True)

                nm_rows = [r for r in log if r["status"] == "no_match"]
                if nm_rows:
                    embed.add_field(
                        name="Airlines with no portal match",
                        value="\n".join(f"• {r['airline']}" for r in nm_rows[:8])
                              + "\n*(Ask them to add their exact airline name on portal)*",
                        inline=False,
                    )
        else:
            embed.description = "💤 Not run yet. Use `/agentrun` to start."

        embed.set_footer(text="JARVIS • AM4 Portal Agent")
        await ctx.send(embed=embed)

    # ── /agentschedule ────────────────────────────────────
    @bot.hybrid_command(
        name="agentschedule",
        description="[Admin] Auto-run agent every N hours (0 = disable)",
    )
    @app_commands.describe(hours="Run every N hours. 0 to disable.")
    async def agentschedule(ctx, hours: int = 12):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)

        _state["schedule_h"] = hours
        ch_id = _agent_ch_id()

        if hours <= 0:
            return await ctx.send("🔕 Auto-agent **disabled**.")

        await ctx.send(
            f"⏰ Agent will auto-run every **{hours}h**.\n"
            + (f"Results → <#{ch_id}>" if ch_id else
               "Set `AGENT_CHANNEL` env var to get results in a channel.")
        )

    # ── /agentdebug ───────────────────────────────────────
    @bot.hybrid_command(
        name="agentdebug",
        description="[Admin] Get debug screenshots from the last agent run",
    )
    async def agentdebug(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)

        import os as _os
        files = []
        for path, label in [
            ("/tmp/am4_login.png",    "Login_Page"),
            ("/tmp/am4_alliance.png", "Alliance_Page"),
        ]:
            if _os.path.exists(path):
                files.append(discord.File(path, filename=f"{label}.png"))

        if not files:
            return await ctx.send(
                "❌ No screenshots yet. Run `/agentrun` first.",
                ephemeral=True,
            )

        await ctx.send(
            "📸 **Debug screenshots from last agent run.**\n"
            "Share these to get correct selectors if members aren't detected:",
            files=files,
        )

