# =========================================================
#  am4_agent.py  —  JARVIS AM4 Automation Module  v3
#
#  USAGE:
#    from am4_agent import setup_agent
#    setup_agent(bot, supabase_get, supabase_post)
#
#  ENV VARS:
#    AM4_EMAIL      — AM4 login email
#    AM4_PASSWORD   — AM4 login password
#    AM4_ALLIANCE   — Alliance name to search (e.g. "Eternal Shadow")
#    AGENT_CHANNEL  — Discord channel ID for results
# =========================================================

import os, re, json, asyncio, subprocess, sys
from datetime import datetime, timezone
import discord
from discord import app_commands
import pytz

_IST = pytz.timezone("Asia/Kolkata")

# ── Marketing page words to IGNORE in scraper ─────────────
# These appear on AM4 landing page — never actual airline names
_IGNORE_WORDS = {
    "build your airline empire", "play free now", "watch trailer",
    "real planes", "maintain", "modify", "play with", "400+",
    "download on the", "get it on", "app store", "google play",
    "airline manager", "build", "empire", "trailer", "free now",
    "download", "install", "copyright", "privacy", "terms",
    "contact", "about", "home", "menu", "navigation",
}

def _is_junk_name(name: str) -> bool:
    """Return True if this looks like marketing/UI text, not an airline name."""
    n = name.strip().lower()
    if len(n) < 2 or len(n) > 60:
        return True
    # Contains common marketing words
    for word in _IGNORE_WORDS:
        if word in n:
            return True
    # All caps short words = UI buttons
    if name.isupper() and len(name.split()) <= 3:
        return True
    # Starts with symbols
    if name[0] in "•●■▶►◄◀▼▲→←":
        return True
    return False

# ── Auto-install Playwright if missing ────────────────────
def _ensure_playwright():
    try:
        import playwright
    except ImportError:
        print("[AGENT] Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"],
                       check=True, capture_output=True)
    try:
        from playwright.async_api import async_playwright
    except:
        pass
    print("[AGENT] Installing Chromium browser binaries...")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
        capture_output=True, text=True
    )

_ensure_playwright()
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── Module state ──────────────────────────────────────────
_state = {
    "running":    False,
    "last_run":   None,
    "log":        [],
    "schedule_h": 0,
}

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
    print("[AM4 AGENT] Ready")

# ── Helpers ───────────────────────────────────────────────
def _now_ist():   return datetime.now(_IST)
def _today_ist(): return _now_ist().strftime("%Y-%m-%d")
def _env(k):      return os.getenv(k, "")

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

async def _ss(page, name):
    try: await page.screenshot(path=f"/tmp/am4_{name}.png")
    except: pass

async def _click(page, sels, timeout=3000):
    for s in sels:
        try:
            await page.click(s, timeout=timeout)
            return True
        except: pass
    return False

async def _fill(page, sels, val, timeout=4000):
    for s in sels:
        try:
            await page.fill(s, val, timeout=timeout)
            return True
        except: pass
    return False

async def _wait(page, sels, timeout=10000):
    for s in sels:
        try:
            el = await page.wait_for_selector(s, timeout=timeout)
            if el: return el
        except: pass
    return None

# ── Supabase ──────────────────────────────────────────────
async def _fetch_portal_airlines():
    try:
        rows = await _supabase_get("share_users",
            {"select": "sts_id,name,airline,alliance,discord_id"})
        result = {}
        for r in rows:
            airline = (r.get("airline") or "").strip()
            if airline:
                result[airline.lower()] = r
        print(f"[AGENT] Portal players: {len(result)}")
        return result
    except Exception as e:
        print(f"[AGENT] fetch error: {e}")
        return {}

def _match(am4_name, portal_map):
    key = am4_name.strip().lower()
    if key in portal_map: return portal_map[key]
    for pk, pv in portal_map.items():
        if key in pk or pk in key: return pv
    kw = set(key.split())
    for pk, pv in portal_map.items():
        if kw & set(pk.split()): return pv
    return None

async def _already_submitted(sts_id, alliance):
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

async def _submit(sts_id, alliance, value):
    await _supabase_post("share_entries", {
        "sts_id":     sts_id,
        "alliance":   alliance,
        "value":      value,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

async def _dm(discord_id, alliance, value):
    if not discord_id or not _bot: return
    try:
        u = await _bot.fetch_user(int(discord_id))
        await u.send(
            f"📤 **JARVIS Auto-Submit** — share entry posted!\n"
            f"Alliance : **{alliance}**\n"
            f"Value    : **{_fmt(value)}**\n"
            f"`{_now_ist().strftime('%d %b %Y  %I:%M %p IST')}`"
        )
    except: pass

# ─────────────────────────────────────────────────────────
#  LOGIN  —  Direct /login URL approach
# ─────────────────────────────────────────────────────────
async def _login(page) -> bool:
    """
    Login strategy (priority order):
      1. Magic/Activation link  (fastest — direct game access)
      2. Direct /login URL      (no button hunting needed)
      3. Homepage → find Login button → fill form
    """
    email      = _env("AM4_EMAIL")
    password   = _env("AM4_PASSWORD")
    magic_link = _env("AM4_MAGIC_LINK").strip()

    # ─────────────────────────────────────────────────────
    # STRATEGY 1 — Magic / Activation link
    # ─────────────────────────────────────────────────────
    if magic_link:
        print(f"[AGENT] Trying magic link: {magic_link[:60]}...")
        try:
            await page.goto(magic_link, wait_until="commit",
                            timeout=60_000)
            await asyncio.sleep(4)
            try:
                await page.wait_for_load_state("networkidle", timeout=45_000)
            except: pass
            await asyncio.sleep(3)
            await _ss(page, "01_magic_link")
            print(f"[AGENT] Magic link URL: {page.url}")

            # Check if game loaded
            if await _game_loaded(page):
                print("[AGENT] ✅ Magic link worked — game open!")
                return True

            print("[AGENT] Magic link didn't open game — trying login flow")
        except Exception as e:
            print(f"[AGENT] Magic link error: {e}")
    else:
        print("[AGENT] No AM4_MAGIC_LINK set — skipping to login flow")

    # ─────────────────────────────────────────────────────
    # STRATEGY 2 — Direct /login URL
    # ─────────────────────────────────────────────────────
    direct_login_urls = [
        "https://www.airlinemanager.com/login",
        "https://www.airlinemanager.com/auth/login",
        "https://www.airlinemanager.com/signin",
        "https://www.airlinemanager.com/auth",
        "https://www.airlinemanager.com/user/login",
    ]

    form_found = False
    for url in direct_login_urls:
        print(f"[AGENT] Trying: {url}")
        try:
            await page.goto(url, wait_until="commit", timeout=60_000)
            await asyncio.sleep(3)
            el = await _wait(page, [
                "input[type='email']", "input[type='password']",
                "input[name='email']", "input[name='password']",
                "#email", "#password",
                "[placeholder*='email' i]", "[placeholder*='password' i]",
            ], timeout=8000)
            if el:
                print(f"[AGENT] ✅ Login form at: {url}")
                form_found = True
                break
        except: pass

    await _ss(page, "02_direct_url_attempt")

    # ─────────────────────────────────────────────────────
    # STRATEGY 3 — Homepage → click Login button
    # ─────────────────────────────────────────────────────
    if not form_found:
        print("[AGENT] Direct URL failed — opening homepage")
        # Retry up to 3 times if timeout
        for _attempt in range(3):
            try:
                await page.goto(
                    "https://www.airlinemanager.com",
                    wait_until="commit",   # fastest — fire as soon as navigation commits
                    timeout=60_000
                )
                # Wait for page to actually render
                await asyncio.sleep(5)
                break
            except Exception as _ge:
                print(f"[AGENT] Homepage goto attempt {_attempt+1} failed: {_ge}")
                if _attempt == 2: raise
                await asyncio.sleep(3)
        await _ss(page, "03_homepage")

        # Dismiss consent banner
        for txt in ["Accept","I agree","OK","Allow","Accept all","Got it"]:
            try:
                await page.click(f"text={txt}", timeout=1500)
                await asyncio.sleep(0.5)
                break
            except: pass

        # Dump all interactive elements so Render logs show exact selectors
        try:
            els_info = await page.evaluate("""
                () => [...document.querySelectorAll('a, button, input')]
                      .slice(0, 50)
                      .map(el => ({
                          tag:  el.tagName,
                          text: el.textContent.trim().slice(0,40),
                          href: el.href  || '',
                          id:   el.id    || '',
                          cls:  el.className.toString().slice(0,60),
                          type: el.type  || '',
                          ph:   el.placeholder || '',
                      }))
            """)
            print("[AGENT] === Homepage interactive elements ===")
            for el in els_info:
                print(f"  {el['tag']:6} | text='{el['text']:25}' | "
                      f"id='{el['id']:15}' | href='{el['href'][:40]}' | "
                      f"cls='{el['cls'][:40]}'")
        except Exception as e:
            print(f"[AGENT] Element dump error: {e}")

        await _ss(page, "04_homepage_rendered")

        # JS click: find element with login text
        clicked = await page.evaluate("""
            () => {
                const loginTexts = ['log in', 'login', 'sign in', 'signin'];
                const all = [...document.querySelectorAll('a, button, span, li, div')];
                // Exact match first
                for (const el of all) {
                    const txt = el.textContent.trim().toLowerCase();
                    if (loginTexts.includes(txt) && el.offsetParent !== null) {
                        el.click();
                        return `exact: <${el.tagName}> "${el.textContent.trim()}" id="${el.id}"`;
                    }
                }
                // Partial match (text length < 20 to avoid matching paragraphs)
                for (const el of all) {
                    const txt = el.textContent.trim().toLowerCase();
                    if (txt.length < 20
                        && (txt.includes('log in') || txt.includes('login'))
                        && el.offsetParent !== null) {
                        el.click();
                        return `partial: <${el.tagName}> "${el.textContent.trim()}" id="${el.id}"`;
                    }
                }
                return null;
            }
        """)
        print(f"[AGENT] Login btn JS result: {clicked}")
        await asyncio.sleep(3)
        await _ss(page, "05_after_login_btn")

        # Check form appeared
        el = await _wait(page, [
            "input[type='email']", "input[type='password']",
            "input[name='email']", "input[name='password']",
            "#email", "#password",
            "[placeholder*='email' i]", "[placeholder*='password' i]",
        ], timeout=10000)
        form_found = el is not None

    # ─────────────────────────────────────────────────────
    # FILL FORM (Strategies 2 & 3)
    # ─────────────────────────────────────────────────────
    if not form_found:
        await _ss(page, "06_form_not_found")
        print("[AGENT] ❌ No login form found via any strategy")
        return False

    print("[AGENT] Filling credentials...")
    await asyncio.sleep(1)

    # Email
    await _fill(page, [
        "input[name='email']", "input[type='email']",
        "#email", "#login-email", "#inputEmail",
        "[placeholder*='email' i]", "[placeholder*='mail' i]",
        "form input:first-of-type",
    ], email)

    # Password
    await _fill(page, [
        "input[name='password']", "input[type='password']",
        "#password", "#login-password", "#inputPassword",
        "[placeholder*='password' i]",
        "form input[type='password']",
    ], password)

    await _ss(page, "07_form_filled")

    # Submit
    submitted = await _click(page, [
        "button[type='submit']",
        "input[type='submit']",
        "#loginBtn", "#btnLogin", "#submitBtn",
        "button:has-text('Login')",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        ".login-btn", ".btn-login", ".btn-submit",
        "[class*='login'][class*='btn']",
        "[class*='submit']",
    ])

    if not submitted:
        try:
            await page.keyboard.press("Enter")
        except: pass

    # Wait for game
    print("[AGENT] Waiting for game to load...")
    await asyncio.sleep(8)
    try:
        await page.wait_for_load_state("networkidle", timeout=45_000)
    except: pass
    await asyncio.sleep(3)
    await _ss(page, "08_post_submit")
    print(f"[AGENT] URL after submit: {page.url}")

    if await _game_loaded(page):
        print("[AGENT] ✅ Logged in via email/password!")
        return True

    print("[AGENT] ❌ Login failed via all strategies")
    return False


async def _game_loaded(page) -> bool:
    """
    Check if AM4 game UI is visible.
    Returns True if we are inside the game (not on marketing/login page).
    """
    # Check for known game UI elements
    for sel in [
        "#sidebar", ".sidebar",
        "#main-nav", ".main-nav",
        "#navBar", ".navbar",
        ".game-ui", ".game-container",
        "#game", "[id*='game']",
        ".bottom-nav", ".nav-tabs",
        "[class*='tab-bar']",
        "canvas",
        "iframe#gameFrame",
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                print(f"[AGENT] Game UI element found: {sel}")
                return True
        except: pass

    # URL / title check
    url   = page.url.lower()
    title = await page.title()
    print(f"[AGENT] _game_loaded check — url:{url} title:{title}")

    # Not on marketing/auth pages = likely in game
    is_auth = any(x in url for x in ["login","signin","register","activate"])
    if is_auth:
        return False

    # Marketing page detection: body has "Build Your Airline Empire"
    try:
        body = await page.evaluate(
            "() => document.body?.innerText?.toLowerCase() || ''"
        )
        if "build your airline empire" in body and len(body) < 5000:
            return False
    except: pass

    # If URL changed from original and not on auth page → assume game
    if "airlinemanager.com" in url and not is_auth:
        return True

    return False


async def _open_alliance_tab(page) -> bool:
    alliance_name = _env("AM4_ALLIANCE") or "Eternal Shadow"
    print(f"[AGENT] Opening alliance: '{alliance_name}'")

    # Dump sidebar elements first
    try:
        sidebar_info = await page.evaluate("""
            () => {
                const sels = ['#sidebar','nav','[class*="sidebar"]',
                              '[class*="nav"]','[class*="menu"]',
                              '[class*="bottom"]','[class*="tab"]'];
                for (const sel of sels) {
                    const el = document.querySelector(sel);
                    if (el) return {
                        sel: sel,
                        html: el.innerHTML.slice(0, 800),
                        children: [...el.querySelectorAll('*')].slice(0,20)
                                  .map(c=>({tag:c.tagName,id:c.id,
                                            cls:c.className.toString().slice(0,60),
                                            txt:c.textContent.trim().slice(0,30)}))
                    };
                }
                return null;
            }
        """)
        if sidebar_info:
            print(f"[AGENT] Sidebar ({sidebar_info['sel']}) children:")
            for c in sidebar_info.get('children', []):
                print(f"  {c['tag']} id='{c['id']}' cls='{c['cls']}' txt='{c['txt']}'")
    except Exception as e:
        print(f"[AGENT] Sidebar dump error: {e}")

    await _ss(page, "09_before_alliance_click")

    # Click alliance/star tab
    clicked = await page.evaluate(f"""
        () => {{
            // Search for star icon or alliance tab
            const keywords = ['alliance','star','guild','club'];
            const all = [...document.querySelectorAll('a,button,li,div,span,img')];
            for (const el of all) {{
                const txt  = (el.textContent || '').trim().toLowerCase();
                const id   = (el.id || '').toLowerCase();
                const cls  = (el.className || '').toString().toLowerCase();
                const src  = (el.src || el.href || '').toLowerCase();
                const title= (el.title || el.alt || '').toLowerCase();

                for (const kw of keywords) {{
                    if ((txt === kw || id.includes(kw) || cls.includes(kw)
                         || src.includes(kw) || title.includes(kw))
                        && el.offsetParent !== null) {{
                        el.click();
                        return 'clicked: ' + el.tagName + ' id=' + el.id
                               + ' cls=' + el.className.toString().slice(0,40)
                               + ' txt=' + el.textContent.trim().slice(0,20);
                    }}
                }}
            }}
            return null;
        }}
    """)
    print(f"[AGENT] Alliance tab click: {clicked}")

    await asyncio.sleep(3)
    await _ss(page, "10_after_alliance_click")

    # Search for the specific alliance
    filled = await _fill(page, [
        "input[placeholder*='search' i]",
        "input[placeholder*='alliance' i]",
        "input[placeholder*='name' i]",
        "input[placeholder*='find' i]",
        "#allianceSearch", "#searchInput", "#search",
        "[class*='search'] input",
        "[id*='search'] input",
        "input[type='text']",
        "input[type='search']",
    ], alliance_name, timeout=4000)

    if filled:
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
        await _ss(page, "11_after_search")

        # Click the alliance from results
        await _click(page, [
            f"text={alliance_name}",
            ".result-item", ".search-result", ".alliance-result",
            "[class*='result']", "[class*='item']",
        ], timeout=3000)
        await asyncio.sleep(2)

    # Click Members tab
    await _click(page, [
        "text=Members", "text=MEMBERS", "text=Roster",
        "#membersTab", "[href*='member']",
        "[class*='member'][class*='tab']",
    ], timeout=3000)

    await asyncio.sleep(2)
    await _ss(page, "12_members_page")

    html = await page.content()
    print(f"[AGENT] Members page content length: {len(html)}")
    return len(html) > 500


# ─────────────────────────────────────────────────────────
#  SCRAPE MEMBERS  (with marketing text filter)
# ─────────────────────────────────────────────────────────
async def _scrape_members(page, portal_map: dict) -> list:
    members = []

    # ── DOM rows ──────────────────────────────────────────
    for row_sel in [
        "table tbody tr", ".member-row", ".alliance-member",
        ".player-row", ".roster-row", "[class*='member']",
        "ul li", "ol li",
    ]:
        try:
            rows = await page.query_selector_all(row_sel)
            if len(rows) < 2: continue
            print(f"[AGENT] Trying selector '{row_sel}': {len(rows)} rows")

            for row in rows:
                try:
                    text = (await row.inner_text()).strip()
                    if not text or len(text) < 2: continue

                    # Get airline name from first meaningful cell
                    airline = ""
                    for ns in [
                        ".airline-name",".name",".player-name",".airline",
                        "td:nth-child(1)","td:nth-child(2)",
                        "[class*='name']","[class*='airline']",
                        "strong","b","span:first-child",
                    ]:
                        try:
                            el = await row.query_selector(ns)
                            if el:
                                t = (await el.inner_text()).strip()
                                if t and len(t) > 1:
                                    airline = t
                                    break
                        except: pass

                    if not airline:
                        airline = text.split("\n")[0].strip()

                    # Skip marketing/junk text
                    if _is_junk_name(airline):
                        continue

                    # Get share value
                    sv = 0.0
                    for vs in [
                        ".share-value",".shares",".stock",".value",
                        "td:nth-child(3)","td:nth-child(4)","td:nth-child(5)",
                        "[class*='share']","[class*='stock']",
                    ]:
                        try:
                            el = await row.query_selector(vs)
                            if el:
                                v = _parse((await el.inner_text()).strip())
                                if v > 0: sv = v; break
                        except: pass

                    # Scan cells for money pattern
                    if sv == 0:
                        for cs in ["td","span","[class*='col']"]:
                            cells = await row.query_selector_all(cs)
                            for c in cells:
                                ct = (await c.inner_text()).strip()
                                if re.search(r"\d[\d,\.]*\s*[BMK$]|\$[\d,\.]+", ct, re.I):
                                    v = _parse(ct)
                                    if v > 0: sv = v; break
                            if sv > 0: break

                    members.append({"airline": airline, "share_value": sv})
                except: continue

            if members:
                print(f"[AGENT] DOM: {len(members)} members via '{row_sel}'")
                break
        except: continue

    # ── JSON in page source ───────────────────────────────
    if not members:
        try:
            html = await page.content()
            for pat in [
                r'members\s*[=:]\s*(\[[\s\S]*?\])',
                r'players\s*[=:]\s*(\[[\s\S]*?\])',
                r'allianceMembers\s*=\s*(\[[\s\S]*?\]);',
                r'roster\s*[=:]\s*(\[[\s\S]*?\])',
            ]:
                m = re.search(pat, html, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        for item in data:
                            airline = (
                                item.get("name") or item.get("airline") or
                                item.get("airlineName") or ""
                            ).strip()
                            sv = float(
                                item.get("shareValue") or item.get("shares") or 0
                            )
                            if airline and not _is_junk_name(airline):
                                members.append({"airline":airline,"share_value":sv})
                        if members:
                            print(f"[AGENT] JSON: {len(members)} members")
                            return members
                    except: pass
        except: pass

    # ── Smart text fallback — only include names that match portal ──
    # This avoids picking up marketing text
    if not members:
        print("[AGENT] Using portal-matched text fallback")
        try:
            body = await page.evaluate("() => document.body.innerText")
            lines = [l.strip() for l in body.split("\n")
                     if l.strip() and not _is_junk_name(l.strip())]
            for line in lines:
                # Only include if it matches a portal player
                if _match(line, portal_map):
                    members.append({"airline": line, "share_value": 0.0})
            if members:
                print(f"[AGENT] Portal-matched text: {len(members)} members")
        except: pass

    return members


# ─────────────────────────────────────────────────────────
#  CORE RUN
# ─────────────────────────────────────────────────────────
async def run_agent() -> list:
    if _state["running"]: return []
    _state["running"] = True
    results = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox","--disable-setuid-sandbox",
                      "--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage","--disable-gpu"],
            )
            ctx = await browser.new_context(
                viewport={"width":1280,"height":800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = await ctx.new_page()

            # Pre-fetch portal players
            portal_map = await _fetch_portal_airlines()
            if not portal_map:
                results.append({"airline":"—","sts_id":"—","value":0,
                    "status":"FATAL: No players in portal share_users table"})
                await browser.close(); return results

            alliance_name = _env("AM4_ALLIANCE") or "Eternal Shadow"

            # Login
            login_ok = await _login(page)
            if not login_ok:
                results.append({"airline":"—","sts_id":"—","value":0,
                    "status":"FATAL: Login failed — use /agentdebug for screenshots"})
                await browser.close(); return results

            # Open alliance tab
            await _open_alliance_tab(page)

            # Scrape (pass portal_map for smart fallback)
            members = await _scrape_members(page, portal_map)
            print(f"[AGENT] Total members found: {len(members)}")

            if not members:
                results.append({"airline":"—","sts_id":"—","value":0,
                    "status":"FATAL: No members found — use /agentdebug"})
                await browser.close(); return results

            # Match + submit
            for m in members:
                airline = (m.get("airline") or "").strip()
                share_val = m.get("share_value", 0.0)
                if not airline: continue

                portal_user = _match(airline, portal_map)
                if not portal_user:
                    results.append({"airline":airline,"sts_id":"—",
                        "value":share_val,"status":"no_match"})
                    continue

                sts_id       = portal_user["sts_id"]
                player_allia = portal_user.get("alliance") or alliance_name

                if await _already_submitted(sts_id, player_allia):
                    results.append({"airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":"already_done"})
                    continue

                try:
                    await _submit(sts_id, player_allia, share_val)
                    results.append({"airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":"submitted"})
                    print(f"[AGENT] ✅ {airline} → {sts_id} → {_fmt(share_val)}")
                    await _dm(portal_user.get("discord_id"), player_allia, share_val)
                except Exception as e:
                    results.append({"airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":f"error:{e}"})

            await browser.close()

    except Exception as e:
        print(f"[AGENT] FATAL: {e}")
        results.append({"airline":"—","sts_id":"—","value":0,
            "status":f"FATAL:{e}"})
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
    while not _bot.is_closed():
        await asyncio.sleep(3600)
        h = _state.get("schedule_h", 0)
        if h <= 0: continue
        last = _state.get("last_run")
        if last and (_now_ist()-last).total_seconds()/3600 < h: continue
        print(f"[AGENT] Auto-run ({h}h)")
        ch = _bot.get_channel(int(_env("AGENT_CHANNEL") or 0))
        if ch: await ch.send(f"🤖 Agent auto-run... (every {h}h)")
        results = await run_agent()
        if ch and results: await _post_results(ch, results)


# ─────────────────────────────────────────────────────────
#  RESULTS EMBED
# ─────────────────────────────────────────────────────────
async def _post_results(channel, results):
    sub = [r for r in results if r["status"]=="submitted"]
    don = [r for r in results if r["status"]=="already_done"]
    nm  = [r for r in results if r["status"]=="no_match"]
    err = [r for r in results
           if r["status"] not in ("submitted","already_done","no_match")]

    color = 0x00ff88 if sub else (0xffa502 if don else 0xff4757)
    e = discord.Embed(title="🤖 JARVIS AM4 Agent — Complete",
        color=color, timestamp=datetime.now(timezone.utc))
    e.add_field(name="✅ Submitted",    value=str(len(sub)), inline=True)
    e.add_field(name="⏭ Already Done", value=str(len(don)), inline=True)
    e.add_field(name="❓ No Match",    value=str(len(nm)),  inline=True)

    if sub:
        lines = [f"• **{r['airline']}** (`{r['sts_id']}`) → {_fmt(r['value'])}"
                 for r in sub[:10]]
        if len(sub)>10: lines.append(f"*...+{len(sub)-10}*")
        e.add_field(name="Submitted", value="\n".join(lines), inline=False)

    if nm:
        e.add_field(
            name="⚠️ No STS match — players must set airline name on portal",
            value="\n".join(f"• {r['airline']}" for r in nm[:8]), inline=False)

    if err:
        e.add_field(name="❌ Errors",
            value="\n".join(r['status'] for r in err[:3]), inline=False)

    e.set_footer(text="JARVIS • AM4 Portal Agent")
    await channel.send(embed=e)


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
            return await ctx.send("⚠️ Already running.", ephemeral=True)
        if not _env("AM4_EMAIL") or not _env("AM4_PASSWORD"):
            return await ctx.send(
                "❌ Set `AM4_EMAIL` and `AM4_PASSWORD` in Render env.", ephemeral=True)

        alliance = _env("AM4_ALLIANCE") or "Eternal Shadow"
        await ctx.send(
            f"🤖 **JARVIS Agent Starting...**\n"
            f"→ Logging into AM4\n"
            f"→ Searching alliance: `{alliance}`\n"
            f"→ Matching → Submitting\n"
            f"*~90 sec. Results will post here.*"
        )
        asyncio.create_task(_run_post(ctx.channel))

    async def _run_post(ch):
        r = await run_agent()
        await _post_results(ch, r)

    @bot.hybrid_command(name="agentstatus",
        description="Check AM4 agent status")
    async def agentstatus(ctx):
        e = discord.Embed(title="🤖 JARVIS AM4 Agent", color=0x00d4ff)
        if _state["running"]:
            e.description = "⚙️ **Running...** scan in progress"
            e.color = 0xffa502
        elif _state["last_run"]:
            e.description = f"✅ Last: `{_state['last_run'].strftime('%d %b %Y %I:%M %p IST')}`"
            log = _state["log"]
            s=sum(1 for r in log if r["status"]=="submitted")
            d=sum(1 for r in log if r["status"]=="already_done")
            n=sum(1 for r in log if r["status"]=="no_match")
            er=sum(1 for r in log if r["status"] not in("submitted","already_done","no_match"))
            e.add_field(name="✅",value=str(s),inline=True)
            e.add_field(name="⏭",value=str(d),inline=True)
            e.add_field(name="❓",value=str(n),inline=True)
            e.add_field(name="❌",value=str(er),inline=True)
            nm_r=[r for r in log if r["status"]=="no_match"]
            if nm_r:
                e.add_field(name="No portal match",
                    value="\n".join(f"• {r['airline']}" for r in nm_r[:8])
                          +"\n*(Set airline name on portal)*",inline=False)
        else:
            e.description = "💤 Not run yet. Use `/agentrun`."
        e.set_footer(text="JARVIS • AM4 Agent")
        await ctx.send(embed=e)

    @bot.hybrid_command(name="agentschedule",
        description="[Admin] Auto-run every N hours (0=off)")
    @app_commands.describe(hours="Hours between runs. 0 to disable.")
    async def agentschedule(ctx, hours: int = 12):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        _state["schedule_h"] = hours
        ch = _env("AGENT_CHANNEL")
        await ctx.send(
            "🔕 Auto-agent disabled." if hours <= 0
            else f"⏰ Agent runs every **{hours}h**."
                 + (f" Results → <#{ch}>" if ch else "")
        )

    @bot.hybrid_command(name="agentdebug",
        description="[Admin] View step-by-step debug screenshots")
    async def agentdebug(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        import os as _os
        labels = [
            ("01_login_url_attempt", "Login URL Attempt"),
            ("02_homepage",          "Homepage"),
            ("03_homepage_rendered", "Homepage Rendered"),
            ("04_after_login_click", "After Login Button Click"),
            ("05_form_not_found",    "Form Not Found"),
            ("06_form_filled",       "Form Filled"),
            ("07_post_login",        "Post Login"),
            ("08_game_check",        "Game Check"),
            ("09_before_alliance",   "Before Alliance Click"),
            ("10_after_alliance",    "After Alliance Click"),
            ("11_after_search",      "After Alliance Search"),
            ("12_members_page",      "Members Page"),
        ]
        files = []
        for name, label in labels:
            p = f"/tmp/am4_{name}.png"
            if _os.path.exists(p):
                files.append(discord.File(p, f"{label.replace(' ','_')}.png"))
        if not files:
            return await ctx.send("❌ No screenshots yet. Run `/agentrun` first.",
                                  ephemeral=True)
        for i in range(0, len(files), 10):
            await ctx.send(
                f"📸 Debug ({i+1}-{i+len(files[i:i+10])} of {len(files)}):",
                files=files[i:i+10]
            )

