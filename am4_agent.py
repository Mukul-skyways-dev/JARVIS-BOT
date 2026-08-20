# =========================================================
#  am4_agent.py  —  JARVIS AM4 Automation Module  v2
#
#  USAGE in bot:
#    from am4_agent import setup_agent
#    # inside on_ready():
#    setup_agent(bot, supabase_get, supabase_post)
#
#  ENV VARS:
#    AM4_EMAIL        — AM4 login email
#    AM4_PASSWORD     — AM4 login password
#    AM4_ALLIANCE     — Exact alliance name to search (e.g. "Eternal Shadow")
#    AGENT_CHANNEL    — Discord channel ID for results
# =========================================================

import os, re, json, asyncio, subprocess, sys
from datetime import datetime, timezone
import discord
from discord import app_commands
import pytz

_IST = pytz.timezone("Asia/Kolkata")

# ── Auto-install Playwright browsers if missing ───────────
def _ensure_playwright():
    try:
        from playwright.async_api import async_playwright
        # Quick check: try importing without launching
        return True
    except ImportError:
        print("[AGENT] Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"],
                       check=True, capture_output=True)
    # Install browsers
    print("[AGENT] Installing Chromium browser...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium",
         "--with-deps"],
        capture_output=True, text=True
    )
    print("[AGENT] Browser install:", result.stdout[-300:] if result.stdout else result.stderr[-300:])
    return True

_ensure_playwright()
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── State ─────────────────────────────────────────────────
_state = {
    "running":    False,
    "last_run":   None,
    "log":        [],
    "schedule_h": 0,
}

# ── Injected refs ─────────────────────────────────────────
_bot           = None
_supabase_get  = None
_supabase_post = None

def setup_agent(bot_instance, supa_get_fn, supa_post_fn):
    global _bot, _supabase_get, _supabase_post
    _bot           = bot_instance
    _supabase_get  = supa_get_fn
    _supabase_post = supa_post_fn
    _register_commands(bot_instance)
    bot_instance.loop.create_task(_auto_loop())
    print("[AM4 AGENT] Ready — commands registered, loop started")

# ── Tiny helpers ──────────────────────────────────────────
def _now_ist():    return datetime.now(_IST)
def _today_ist():  return _now_ist().strftime("%Y-%m-%d")
def _env(k):       return os.getenv(k, "")

def _fmt(v):
    try:
        v = float(v)
        if v >= 1e9: return f"${v/1e9:.3f}B"
        if v >= 1e6: return f"${v/1e6:.2f}M"
        if v >= 1e3: return f"${v/1e3:.1f}K"
        return f"${v:,.0f}"
    except: return str(v)

def _parse(s):
    try:
        s = str(s).replace("$","").replace(",","").strip().upper()
        if s.endswith("B"): return float(s[:-1])*1e9
        if s.endswith("M"): return float(s[:-1])*1e6
        if s.endswith("K"): return float(s[:-1])*1e3
        return float(s)
    except: return 0.0

# ─────────────────────────────────────────────────────────
#  SUPABASE  
# ─────────────────────────────────────────────────────────
async def _fetch_portal_airlines() -> dict:
    """
    Fetch ALL players from share_users.
    Returns dict: { airline_name_lower: {sts_id, name, alliance, discord_id} }
    """
    try:
        rows = await _supabase_get("share_users", {
            "select": "sts_id,name,airline,alliance,discord_id",
        })
        result = {}
        for r in rows:
            airline = (r.get("airline") or "").strip()
            if airline:
                result[airline.lower()] = r
        print(f"[AGENT] Portal players loaded: {len(result)}")
        return result
    except Exception as e:
        print(f"[AGENT] fetch_portal_airlines error: {e}")
        return {}

def _match_airline(am4_name: str, portal_map: dict):
    """
    Match AM4 airline name to portal player.
    Tries: exact → contains → partial word match.
    """
    key = am4_name.strip().lower()
    # Exact
    if key in portal_map:
        return portal_map[key]
    # Contains either way
    for pk, pv in portal_map.items():
        if key in pk or pk in key:
            return pv
    # Word-level partial
    key_words = set(key.split())
    for pk, pv in portal_map.items():
        pk_words = set(pk.split())
        if key_words & pk_words:  # any word in common
            return pv
    return None

async def _already_submitted(sts_id: str, alliance: str) -> bool:
    try:
        rows = await _supabase_get("share_entries", {
            "sts_id":   f"eq.{sts_id}",
            "alliance": f"eq.{alliance}",
            "select":   "id,created_at",
        })
        today = _today_ist()
        for r in rows:
            day = datetime.fromisoformat(
                r["created_at"].replace("Z","+00:00")
            ).astimezone(_IST).strftime("%Y-%m-%d")
            if day == today: return True
        return False
    except: return False

async def _do_submit(sts_id: str, alliance: str, value: float):
    await _supabase_post("share_entries", {
        "sts_id":     sts_id,
        "alliance":   alliance,
        "value":      value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

async def _dm_player(discord_id, alliance, value):
    if not discord_id or not _bot: return
    try:
        u = await _bot.fetch_user(int(discord_id))
        await u.send(
            f"📤 **JARVIS Auto-Submitted** your share entry!\n"
            f"Alliance : **{alliance}**\n"
            f"Value    : **{_fmt(value)}**\n"
            f"`{_now_ist().strftime('%d %b %Y  %I:%M %p IST')}`"
        )
    except Exception as e:
        print(f"[AGENT] DM failed {discord_id}: {e}")

# ─────────────────────────────────────────────────────────
#  PLAYWRIGHT HELPERS
# ─────────────────────────────────────────────────────────
async def _screenshot(page, name: str):
    try:
        await page.screenshot(path=f"/tmp/am4_{name}.png", full_page=False)
    except: pass

async def _try_click(page, selectors: list, timeout=3000) -> bool:
    for sel in selectors:
        try:
            await page.click(sel, timeout=timeout)
            return True
        except: pass
    return False

async def _try_fill(page, selectors: list, value: str, timeout=4000) -> bool:
    for sel in selectors:
        try:
            await page.fill(sel, value, timeout=timeout)
            return True
        except: pass
    return False

async def _wait_any(page, selectors: list, timeout=10000):
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout)
            if el: return el
        except: pass
    return None

# ─────────────────────────────────────────────────────────
#  STEP 1 — LOGIN
# ─────────────────────────────────────────────────────────
async def _login(page) -> bool:
    email    = _env("AM4_EMAIL")
    password = _env("AM4_PASSWORD")

    # ── Step 1: Open AM4 landing page ─────────────────────
    print("[AGENT] Opening AM4 landing page...")
    await page.goto(
        "https://www.airlinemanager.com",
        wait_until="domcontentloaded",
        timeout=30_000
    )
    await asyncio.sleep(3)
    await _screenshot(page, "01_landing")

    # ── Step 2: Dismiss cookie/consent banner if present ──
    for txt in ["Accept","I agree","OK","Allow","Accept all","Got it","Close"]:
        try:
            await page.click(f"text={txt}", timeout=1500)
            await asyncio.sleep(0.5)
            break
        except: pass

    # ── Step 3: Click LOGIN button (NOT register/play) ────
    # AM4 landing page has "Login" link in top nav or hero section
    # We must click this BEFORE filling any form
    print("[AGENT] Looking for Login button on landing page...")
    login_btn_clicked = False

    # Priority order: most specific → least specific
    login_btn_selectors = [
        # Exact text matches (most reliable)
        "a:has-text('Login')",
        "a:has-text('Log In')",
        "a:has-text('Log in')",
        "button:has-text('Login')",
        "button:has-text('Log In')",
        # Nav bar login links
        "nav a[href*='login']",
        "header a[href*='login']",
        ".navbar a[href*='login']",
        ".nav a[href*='login']",
        # ID / class based
        "#loginBtn","#login-btn","#btnLogin",
        ".login-btn",".btn-login",".login-link",
        "[class*='login'][class*='btn']",
        "[class*='btn'][class*='login']",
        # Data attributes
        "[data-action='login']",
        "[data-target='#loginModal']",
        "[data-toggle='modal'][href*='login']",
        # Generic fallbacks
        "a[href*='login']",
        "a[href*='signin']",
    ]

    for sel in login_btn_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.click(timeout=3000)
                login_btn_clicked = True
                print(f"[AGENT] Login button clicked: {sel}")
                await asyncio.sleep(2)
                break
        except: pass

    await _screenshot(page, "02_after_login_btn_click")

    if not login_btn_clicked:
        print("[AGENT] ⚠️ Login button not found via selectors — trying JS search")
        try:
            await page.evaluate("""
                () => {
                    // Find any link/button with 'login' or 'log in' text
                    const all = [...document.querySelectorAll('a, button, span')];
                    for (const el of all) {
                        const t = el.textContent.trim().toLowerCase();
                        if ((t === 'login' || t === 'log in' || t === 'sign in')
                             && el.offsetParent !== null) {
                            el.click();
                            return el.textContent;
                        }
                    }
                    return null;
                }
            """)
            await asyncio.sleep(2)
            login_btn_clicked = True
        except Exception as e:
            print(f"[AGENT] JS login click error: {e}")

    # ── Step 4: Wait for login FORM to appear ─────────────
    print("[AGENT] Waiting for login form...")
    form_appeared = await _wait_any(page, [
        "input[type='email']",
        "input[type='password']",
        "input[name='email']",
        "input[name='password']",
        "#email","#login-email",
        "[placeholder*='email' i]",
        "[placeholder*='mail' i]",
        "#loginModal","#login-modal",
        ".login-form","[class*='login'][class*='form']",
    ], timeout=8000)

    await _screenshot(page, "03_login_form")

    if not form_appeared:
        print("[AGENT] Login form not visible after button click — screenshot saved")

    # ── Step 5: Fill Email ─────────────────────────────────
    print("[AGENT] Filling email...")
    email_filled = await _try_fill(page, [
        "input[name='email']",
        "input[type='email']",
        "#email",
        "#login-email",
        "[placeholder*='email' i]",
        "[placeholder*='mail' i]",
        ".login-form input[type='text']",
        "form input:nth-child(1)",
    ], email)
    print(f"[AGENT] Email filled: {email_filled}")

    # ── Step 6: Fill Password ──────────────────────────────
    print("[AGENT] Filling password...")
    pass_filled = await _try_fill(page, [
        "input[name='password']",
        "input[type='password']",
        "#password",
        "#login-password",
        "[placeholder*='password' i]",
        ".login-form input[type='password']",
        "form input[type='password']",
    ], password)
    print(f"[AGENT] Password filled: {pass_filled}")

    await _screenshot(page, "04_credentials_filled")

    # ── Step 7: Click SUBMIT / Login button in form ────────
    print("[AGENT] Submitting login form...")
    await _try_click(page, [
        # Inside modal / form — most specific first
        "#loginModal button[type='submit']",
        ".login-form button[type='submit']",
        "form button[type='submit']",
        "button[type='submit']",
        "input[type='submit']",
        # Text-based
        "button:has-text('Login')",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        "button:has-text('Enter')",
        # ID / class
        "#loginSubmit","#submitLogin","#btnSubmit",
        ".btn-submit",".submit-btn",".login-submit",
        "[class*='submit']","[class*='login'][class*='btn']",
    ])

    # ── Step 8: Wait for game to load ─────────────────────
    print("[AGENT] Waiting for game UI to load...")
    await asyncio.sleep(5)
    try:
        await page.wait_for_load_state("networkidle", timeout=25_000)
    except: pass
    await asyncio.sleep(3)
    await _screenshot(page, "05_post_submit")
    print(f"[AGENT] URL after submit: {page.url}")

    # ── Step 9: Verify game loaded ─────────────────────────
    # Look for any game UI element that confirms we are inside the game
    game_el = await _wait_any(page, [
        "#sidebar", ".sidebar",
        "#main-nav", ".main-nav",
        "#navBar", ".navbar",
        ".game-ui", ".game-container",
        "#game", "[id*='game']",
        "[class*='sidebar']",
        "[class*='game-']",
        "#dashboard", ".dashboard",
        ".bottom-nav", ".nav-tabs",
        "[class*='tab-bar']",
        # AM4 might use canvas for game
        "canvas",
        # Or an iframe
        "iframe#gameFrame", "iframe[src*='game']",
    ], timeout=10000)

    await _screenshot(page, "06_game_verify")

    if game_el:
        print("[AGENT] ✅ Game UI confirmed")
        return True

    # Title/URL fallback check
    title = await page.title()
    url   = page.url.lower()
    print(f"[AGENT] Title: {title} | URL: {url}")

    # If we are no longer on landing/login, assume success
    still_on_landing = any(x in url for x in [
        "login","signin","register","signup",
    ]) or ("build" in title.lower() and "airline" in title.lower())

    if not still_on_landing:
        print("[AGENT] ✅ URL/title suggests logged in")
        return True

    print("[AGENT] ❌ Still on login/landing page")
    return False


# ─────────────────────────────────────────────────────────
#  STEP 2 — OPEN ALLIANCE TAB (⭐ star icon in sidebar)
# ─────────────────────────────────────────────────────────
async def _open_alliance_tab(page) -> bool:
    alliance_name = _env("AM4_ALLIANCE") or "Eternal Shadow"
    print(f"[AGENT] Opening alliance tab, searching: '{alliance_name}'")

    await asyncio.sleep(2)

    # Try clicking the star / alliance tab in sidebar
    # AM4 uses various selectors for alliance tab
    clicked = await _try_click(page, [
        # Star icon variations
        "[title*='Alliance' i]",
        "[alt*='Alliance' i]",
        "[class*='alliance' i]",
        "[id*='alliance' i]",
        "[href*='alliance' i]",
        # Star shape / icon
        "[class*='star' i]",
        "[id*='star' i]",
        "img[src*='star']",
        "img[src*='alliance']",
        # Text
        "text=Alliance",
        "text=My Alliance",
        ".alliance-tab",
        "#allianceTab",
        "#btnAlliance",
        # Nav items - AM4 sidebar tabs are often nth-child
        ".sidebar li:nth-child(4) a",
        ".sidebar li:nth-child(5) a",
        ".nav-item:nth-child(4)",
        ".tab:nth-child(4)",
        ".bottom-nav li:nth-child(4)",
        "#tab4","#tab5",
    ], timeout=3000)

    await asyncio.sleep(2)
    await _screenshot(page, "07_alliance_tab")

    if not clicked:
        # Try by evaluating JS — find element containing star SVG or alliance keyword
        try:
            await page.evaluate("""
                () => {
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const txt = (el.textContent || el.title || el.alt || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const id  = (el.id || '').toLowerCase();
                        if ((txt.includes('alliance') || cls.includes('alliance') || id.includes('alliance'))
                            && el.tagName !== 'BODY' && el.tagName !== 'HTML') {
                            el.click();
                            break;
                        }
                    }
                }
            """)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[AGENT] JS alliance click error: {e}")

    # Now search for the alliance
    await _screenshot(page, "08_alliance_search_before")

    # Find search box and type alliance name
    searched = await _try_fill(page, [
        "input[placeholder*='search' i]",
        "input[placeholder*='alliance' i]",
        "input[placeholder*='find' i]",
        "input[placeholder*='name' i]",
        "#allianceSearch","#searchAlliance",
        ".alliance-search input",
        "[class*='search'] input",
        "[id*='search'] input",
        "input[type='text']",
        "input[type='search']",
    ], alliance_name, timeout=4000)

    if searched:
        await asyncio.sleep(1)
        # Press Enter or click search button
        try:
            await page.keyboard.press("Enter")
        except: pass
        await _try_click(page, [
            "button[type='submit']", ".search-btn", "#searchBtn",
            "text=Search", "text=Find", ".btn-search",
        ], timeout=2000)
        await asyncio.sleep(2)
        await _screenshot(page, "09_alliance_searched")

    # Try clicking on the alliance result
    await _try_click(page, [
        f"text={alliance_name}",
        ".alliance-result",".search-result",
        ".result-item",".alliance-item",
        "[class*='result']",
    ], timeout=3000)

    await asyncio.sleep(2)
    await _screenshot(page, "10_alliance_opened")

    # Navigate to Members tab within alliance
    await _try_click(page, [
        "text=Members","text=MEMBERS",
        "#membersTab","[href*='member']",
        "[class*='member'][class*='tab']",
        ".tab:contains('Member')",
        "text=Players","text=Roster",
    ], timeout=3000)

    await asyncio.sleep(2)
    await _screenshot(page, "11_members_tab")

    # Check if any member-like content appeared
    content = await page.content()
    has_members = any(x in content.lower() for x in
                      ["airline","member","player","roster"])
    print(f"[AGENT] Alliance/members content found: {has_members}")
    return has_members


# ─────────────────────────────────────────────────────────
#  STEP 3 — SCRAPE MEMBERS
# ─────────────────────────────────────────────────────────
async def _scrape_members(page) -> list:
    """
    Returns list of { airline, share_value }.
    Tries DOM rows → JSON in source → page text parsing.
    """
    members = []

    # ── DOM rows ──────────────────────────────────────────
    row_sels = [
        "table tbody tr",
        ".member-row",".alliance-member",
        ".player-row",".roster-row",
        "[class*='member']","[class*='player']",
        "ul.members li","ol.members li",
        ".list-item","[class*='list'] [class*='item']",
    ]
    rows = []
    for sel in row_sels:
        try:
            found = await page.query_selector_all(sel)
            if len(found) > 0:
                rows = found
                print(f"[AGENT] Rows found with selector '{sel}': {len(found)}")
                break
        except: pass

    for row in rows:
        try:
            text = (await row.inner_text()).strip()
            if not text or len(text) < 2: continue

            # Airline name
            airline = ""
            for sel in [
                ".airline-name",".name",".player-name",".airline",
                "td:nth-child(1)","td:nth-child(2)",
                "[class*='name']","[class*='airline']",
                "span:first-child","strong","b",
            ]:
                try:
                    el = await row.query_selector(sel)
                    if el:
                        t = (await el.inner_text()).strip()
                        if t and len(t) > 1:
                            airline = t
                            break
                except: pass

            if not airline:
                # First non-empty line of row text
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if lines: airline = lines[0]

            if not airline or len(airline) < 2: continue

            # Share value — look for money pattern
            share_val = 0.0
            for sel in [
                ".share-value",".shares",".stock",".value",
                "td:nth-child(3)","td:nth-child(4)","td:nth-child(5)",
                "[class*='share']","[class*='stock']","[class*='value']",
            ]:
                try:
                    el = await row.query_selector(sel)
                    if el:
                        sv = _parse((await el.inner_text()).strip())
                        if sv > 0: share_val = sv; break
                except: pass

            # Scan all cells for money pattern
            if share_val == 0:
                for cell_sel in ["td","span","div","[class*='col']"]:
                    cells = await row.query_selector_all(cell_sel)
                    for cell in cells:
                        ct = (await cell.inner_text()).strip()
                        if re.search(r"\d[\d,\.]*\s*[BMK$]|\$[\d,\.]+", ct, re.I):
                            sv = _parse(ct)
                            if sv > 0: share_val = sv; break
                    if share_val > 0: break

            members.append({"airline": airline, "share_value": share_val})
        except: continue

    if members:
        print(f"[AGENT] DOM extracted {len(members)} members")
        return members

    # ── JSON in page source ───────────────────────────────
    try:
        html = await page.content()
        for pat in [
            r'members\s*[=:]\s*(\[[\s\S]*?\])',
            r'players\s*[=:]\s*(\[[\s\S]*?\])',
            r'roster\s*[=:]\s*(\[[\s\S]*?\])',
            r'allianceMembers\s*=\s*(\[[\s\S]*?\]);',
        ]:
            m = re.search(pat, html, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    for item in data:
                        airline = (
                            item.get("name") or item.get("airline") or
                            item.get("airlineName") or item.get("companyName","")
                        ).strip()
                        sv = float(
                            item.get("shareValue") or item.get("share_value") or
                            item.get("shares") or item.get("stockValue") or 0
                        )
                        if airline:
                            members.append({"airline":airline,"share_value":sv})
                    if members:
                        print(f"[AGENT] JSON extracted {len(members)} members")
                        return members
                except: pass
    except Exception as e:
        print(f"[AGENT] JSON parse error: {e}")

    # ── Plain text fallback — read visible page text ───────
    try:
        body_text = await page.evaluate("() => document.body.innerText")
        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
        # Look for lines that look like airline names near money values
        for i, line in enumerate(lines):
            if len(line) > 50 or len(line) < 2: continue
            # Check next few lines for money value
            sv = 0.0
            for j in range(i+1, min(i+5, len(lines))):
                sv = _parse(lines[j])
                if sv > 0: break
            if len(line) > 2:
                members.append({"airline": line, "share_value": sv})
        if members:
            print(f"[AGENT] Text fallback extracted {len(members)} lines")
    except Exception as e:
        print(f"[AGENT] Text fallback error: {e}")

    return members


# ─────────────────────────────────────────────────────────
#  CORE RUN
# ─────────────────────────────────────────────────────────
async def run_agent() -> list:
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
                    "--disable-gpu",
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

            # ── 0. Pre-fetch all portal players ───────────
            portal_map = await _fetch_portal_airlines()
            if not portal_map:
                results.append({
                    "airline":"—","sts_id":"—","value":0,
                    "status":"FATAL: No players in portal share_users table yet.",
                })
                await browser.close(); return results

            alliance_name = _env("AM4_ALLIANCE") or "Eternal Shadow"

            # ── 1. Login ───────────────────────────────────
            login_ok = await _login(page)
            if not login_ok:
                results.append({
                    "airline":"—","sts_id":"—","value":0,
                    "status":(
                        "FATAL: Login failed.\n"
                        "→ Check AM4_EMAIL / AM4_PASSWORD in Render env vars.\n"
                        "→ Use /agentdebug to view screenshots."
                    ),
                })
                await browser.close(); return results

            # ── 2. Open Alliance tab ───────────────────────
            alliance_ok = await _open_alliance_tab(page)
            await _screenshot(page, "12_final_state")

            members = await _scrape_members(page)
            print(f"[AGENT] Members scraped: {len(members)}")

            if not members:
                results.append({
                    "airline":"—","sts_id":"—","value":0,
                    "status":(
                        "FATAL: No members found on alliance page.\n"
                        "→ Use /agentdebug — send screenshots 07-12 to Skyways.\n"
                        "→ Selectors need update based on actual AM4 game HTML."
                    ),
                })
                await browser.close(); return results

            # ── 3. Match + Submit ──────────────────────────
            for m in members:
                airline   = (m.get("airline") or "").strip()
                share_val = m.get("share_value", 0.0)
                if not airline: continue

                # Match to portal player
                portal_user = _match_airline(airline, portal_map)

                if not portal_user:
                    results.append({
                        "airline":airline,"sts_id":"—",
                        "value":share_val,"status":"no_match",
                    })
                    continue

                sts_id       = portal_user["sts_id"]
                player_allia = portal_user.get("alliance") or alliance_name

                # Duplicate check
                if await _already_submitted(sts_id, player_allia):
                    results.append({
                        "airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":"already_done",
                    })
                    continue

                # Submit
                try:
                    await _do_submit(sts_id, player_allia, share_val)
                    results.append({
                        "airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":"submitted",
                    })
                    print(f"[AGENT] ✅ {airline} → {sts_id} → {_fmt(share_val)}")
                    await _dm_player(portal_user.get("discord_id"),
                                     player_allia, share_val)
                except Exception as sub_e:
                    results.append({
                        "airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":f"error:{sub_e}",
                    })

            await browser.close()

    except Exception as fatal:
        print(f"[AGENT] FATAL: {fatal}")
        results.append({
            "airline":"—","sts_id":"—","value":0,
            "status":f"FATAL:{fatal}",
        })
    finally:
        _state["running"]  = False
        _state["last_run"] = _now_ist()
        _state["log"]      = results

    return results


# ─────────────────────────────────────────────────────────
#  AUTO LOOP
# ─────────────────────────────────────────────────────────
async def _auto_loop():
    await _bot.wait_until_ready()
    print("[AGENT] Auto-loop running")
    while not _bot.is_closed():
        await asyncio.sleep(3600)
        h = _state.get("schedule_h", 0)
        if h <= 0: continue
        last = _state.get("last_run")
        if last:
            elapsed = (_now_ist() - last).total_seconds() / 3600
            if elapsed < h: continue
        print(f"[AGENT] Auto-run ({h}h schedule)")
        ch = _bot.get_channel(int(_env("AGENT_CHANNEL") or 0))
        if ch:
            await ch.send(f"🤖 **Agent auto-run...** (every {h}h)")
        results = await run_agent()
        if ch and results:
            await _post_results(ch, results)


# ─────────────────────────────────────────────────────────
#  RESULT EMBED
# ─────────────────────────────────────────────────────────
async def _post_results(channel, results):
    sub = [r for r in results if r["status"]=="submitted"]
    don = [r for r in results if r["status"]=="already_done"]
    nm  = [r for r in results if r["status"]=="no_match"]
    err = [r for r in results
           if r["status"] not in ("submitted","already_done","no_match")]

    color = 0x00ff88 if sub else (0xffa502 if don else 0xff4757)
    embed = discord.Embed(
        title="🤖 JARVIS AM4 Agent — Complete",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="✅ Submitted",    value=str(len(sub)), inline=True)
    embed.add_field(name="⏭ Already Done", value=str(len(don)), inline=True)
    embed.add_field(name="❓ No Match",    value=str(len(nm)),  inline=True)

    if sub:
        lines = [f"• **{r['airline']}** (`{r['sts_id']}`) → {_fmt(r['value'])}"
                 for r in sub[:10]]
        if len(sub)>10: lines.append(f"*...+{len(sub)-10} more*")
        embed.add_field(name="Submitted", value="\n".join(lines), inline=False)

    if nm:
        lines = [f"• {r['airline']}" for r in nm[:8]]
        embed.add_field(
            name="⚠️ No STS match — tell players to set airline name on portal",
            value="\n".join(lines), inline=False,
        )

    if err:
        lines = [f"• {r['status']}" for r in err[:3]]
        embed.add_field(name="❌ Errors", value="\n".join(lines), inline=False)

    embed.set_footer(text="JARVIS • AM4 Portal Agent")
    await channel.send(embed=embed)


# ─────────────────────────────────────────────────────────
#  DISCORD COMMANDS
# ─────────────────────────────────────────────────────────
def _register_commands(bot):

    @bot.hybrid_command(name="agentrun",
        description="[Admin] Login AM4, scrape alliance, auto-submit share entries")
    async def agentrun(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        if _state["running"]:
            return await ctx.send("⚠️ Already running. Use `/agentstatus`.", ephemeral=True)
        if not _env("AM4_EMAIL") or not _env("AM4_PASSWORD"):
            return await ctx.send(
                "❌ Set `AM4_EMAIL` and `AM4_PASSWORD` in Render env.", ephemeral=True)

        alliance = _env("AM4_ALLIANCE") or "Eternal Shadow"
        await ctx.send(
            f"🤖 **JARVIS Agent Starting...**\n"
            f"→ Logging into AM4\n"
            f"→ Opening Alliance ⭐ tab → searching `{alliance}`\n"
            f"→ Matching members to portal STS IDs\n"
            f"→ Auto-submitting share entries\n\n"
            f"*~60-90 sec. Results will post here.*"
        )
        asyncio.create_task(_run_and_post(ctx.channel))

    async def _run_and_post(channel):
        results = await run_agent()
        await _post_results(channel, results)

    @bot.hybrid_command(name="agentstatus",
        description="Check AM4 agent status and last run summary")
    async def agentstatus(ctx):
        embed = discord.Embed(title="🤖 JARVIS AM4 Agent", color=0x00d4ff)
        if _state["running"]:
            embed.description = "⚙️ **Running...** scan in progress"
            embed.color = 0xffa502
        elif _state["last_run"]:
            embed.description = f"✅ Last: `{_state['last_run'].strftime('%d %b %Y %I:%M %p IST')}`"
            log = _state["log"]
            s=sum(1 for r in log if r["status"]=="submitted")
            d=sum(1 for r in log if r["status"]=="already_done")
            n=sum(1 for r in log if r["status"]=="no_match")
            e=sum(1 for r in log if r["status"] not in
                  ("submitted","already_done","no_match"))
            embed.add_field(name="✅",value=str(s),inline=True)
            embed.add_field(name="⏭",value=str(d),inline=True)
            embed.add_field(name="❓",value=str(n),inline=True)
            embed.add_field(name="❌",value=str(e),inline=True)
            nm_rows=[r for r in log if r["status"]=="no_match"]
            if nm_rows:
                embed.add_field(
                    name="No portal match (set airline name on portal):",
                    value="\n".join(f"• {r['airline']}" for r in nm_rows[:8]),
                    inline=False)
        else:
            embed.description = "💤 Not run yet. Use `/agentrun`."
        embed.set_footer(text="JARVIS • AM4 Agent")
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="agentschedule",
        description="[Admin] Auto-run every N hours (0=off)")
    @app_commands.describe(hours="Interval in hours. 0 to disable.")
    async def agentschedule(ctx, hours: int = 12):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        _state["schedule_h"] = hours
        if hours <= 0:
            return await ctx.send("🔕 Auto-agent **disabled**.")
        await ctx.send(f"⏰ Agent runs every **{hours}h** automatically.")

    @bot.hybrid_command(name="agentdebug",
        description="[Admin] View debug screenshots from last run")
    async def agentdebug(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        files = []
        labels = [
            ("01_landing","Landing Page"),
            ("02_after_play_click","After Play Click"),
            ("03_credentials_filled","Credentials Filled"),
            ("04_post_login","Post Login"),
            ("05_game_direct","Game Direct URL"),
            ("06_game_check","Game Check"),
            ("07_alliance_tab","Alliance Tab Clicked"),
            ("08_alliance_search_before","Before Search"),
            ("09_alliance_searched","After Search"),
            ("10_alliance_opened","Alliance Opened"),
            ("11_members_tab","Members Tab"),
            ("12_final_state","Final State"),
        ]
        import os as _os
        for name, label in labels:
            p = f"/tmp/am4_{name}.png"
            if _os.path.exists(p):
                files.append(discord.File(p, filename=f"{label.replace(' ','_')}.png"))

        if not files:
            return await ctx.send("❌ No screenshots. Run `/agentrun` first.", ephemeral=True)

        # Discord max 10 files per message
        for i in range(0, len(files), 10):
            batch = files[i:i+10]
            await ctx.send(
                f"📸 **Debug screenshots** ({i+1}-{i+len(batch)} of {len(files)}):",
                files=batch
            )

