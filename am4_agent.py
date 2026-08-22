# =========================================================
#  am4_agent.py  —  JARVIS AM4 Automation Module  v4
#
#  USAGE:
#    from am4_agent import setup_agent
#    setup_agent(bot, supabase_get, supabase_post)
#
#  ENV VARS:
#    AM4_COOKIES    — JSON array of browser cookies (see below)
#    AM4_EMAIL      — AM4 login email (fallback)
#    AM4_PASSWORD   — AM4 login password (fallback)
#    AM4_MAGIC_LINK — Activation link from email (fallback)
#    AM4_ALLIANCE   — Alliance name e.g. "Eternal Dynasty"
#    AGENT_CHANNEL  — Discord channel ID for results
#
# ─────────────────────────────────────────────────────────
#  HOW TO GET AM4_COOKIES:
#
#  1. Open Chrome on desktop
#  2. Go to https://www.airlinemanager.com and LOGIN
#  3. Press F12 → Console tab
#  4. Paste this JS and press Enter:
#
#     copy(JSON.stringify(document.cookie.split(';').map(c=>{
#       const [name,...rest]=c.trim().split('=');
#       return {name:name.trim(),value:rest.join('=').trim(),
#               domain:'.airlinemanager.com',path:'/'};
#     })))
#
#  5. Ctrl+V in Notepad — you'll see JSON like:
#     [{"name":"session","value":"abc123","domain":...}]
#  6. Copy that entire JSON → paste as AM4_COOKIES in Render env
#
#  Cookies stay valid for weeks/months. Refresh when agent stops working.
# =========================================================

import os, re, json, asyncio, subprocess, sys
from datetime import datetime, timezone
import discord
from discord import app_commands
import pytz

_IST = pytz.timezone("Asia/Kolkata")

# ── Junk text filter ──────────────────────────────────────
_JUNK = {
    "build your airline empire","play free now","watch trailer",
    "real planes","maintain","modify","play with","400+",
    "download on the","get it on","app store","google play",
    "airline manager","build","empire","trailer","free now",
    "download","install","copyright","privacy","terms",
    "contact","about","home","menu","navigation","cookie",
    "accept","decline","subscribe","newsletter",
}

def _is_junk(name):
    n = name.strip().lower()
    if len(n) < 2 or len(n) > 60: return True
    for w in _JUNK:
        if w in n: return True
    if name.isupper() and len(name.split()) <= 3: return True
    if name[0] in "•●■▶►◄◀▼▲→←@#": return True
    return False

# ── Auto-install Playwright ───────────────────────────────
def _ensure_playwright():
    try:
        from playwright.async_api import async_playwright
        return
    except ImportError:
        subprocess.run([sys.executable,"-m","pip","install","playwright"],
                       check=True, capture_output=True)
    subprocess.run(
        [sys.executable,"-m","playwright","install","chromium","--with-deps"],
        capture_output=True, text=True
    )

_ensure_playwright()
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# ── State ─────────────────────────────────────────────────
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
    _bot, _supabase_get, _supabase_post = bot_instance, supa_get_fn, supa_post_fn
    _register_commands(bot_instance)
    bot_instance.loop.create_task(_auto_loop())
    print("[AGENT] Ready ✅")

# ── Utils ─────────────────────────────────────────────────
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
    try: await page.screenshot(path=f"/tmp/am4_{name}.png", full_page=False)
    except: pass

async def _click(page, sels, timeout=4000):
    for s in sels:
        try: await page.click(s, timeout=timeout); return True
        except: pass
    return False

async def _fill(page, sels, val, timeout=5000):
    for s in sels:
        try: await page.fill(s, val, timeout=timeout); return True
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
            {"select":"sts_id,name,airline,alliance,discord_id"})
        result = {}
        for r in rows:
            airline = (r.get("airline") or "").strip()
            if airline:
                result[airline.lower()] = r
        print(f"[AGENT] Portal players loaded: {len(result)}")
        return result
    except Exception as e:
        print(f"[AGENT] fetch error: {e}")
        return {}

def _match(name, portal_map):
    key = name.strip().lower()
    if key in portal_map: return portal_map[key]
    for pk, pv in portal_map.items():
        if key in pk or pk in key: return pv
    kw = set(key.split())
    for pk, pv in portal_map.items():
        if kw & set(pk.split()): return pv
    return None

async def _already_submitted(sts_id, alliance):
    try:
        rows = await _supabase_get("share_entries",{
            "sts_id":f"eq.{sts_id}","alliance":f"eq.{alliance}",
            "select":"id,created_at"})
        today = _today_ist()
        for r in rows:
            day = datetime.fromisoformat(
                r["created_at"].replace("Z","+00:00")
            ).astimezone(_IST).strftime("%Y-%m-%d")
            if day == today: return True
    except: pass
    return False

async def _submit_entry(sts_id, alliance, value):
    await _supabase_post("share_entries",{
        "sts_id":sts_id, "alliance":alliance, "value":value,
        "created_at":datetime.now(timezone.utc).isoformat()})

async def _dm_player(discord_id, alliance, value):
    if not discord_id or not _bot: return
    try:
        u = await _bot.fetch_user(int(discord_id))
        await u.send(
            f"📤 **JARVIS Auto-Submitted** your share entry!\n"
            f"Alliance : **{alliance}**\n"
            f"Value    : **{_fmt(value)}**\n"
            f"`{_now_ist().strftime('%d %b %Y  %I:%M %p IST')}`")
    except: pass

# ─────────────────────────────────────────────────────────
#  GAME LOADED CHECK
# ─────────────────────────────────────────────────────────
async def _game_loaded(page) -> bool:
    """Returns True if we are inside the game UI."""
    # Look for any game-specific element
    game_selectors = [
        "#sidebar",".sidebar","[id*='sidebar']","[class*='sidebar']",
        "#main-nav",".main-nav","#navBar",
        ".game-ui","[class*='game-ui']",".game-container",
        "#game-container","[id*='game']",
        ".bottom-nav","[class*='bottom-nav']","[class*='tab-bar']",
        "#dashboard","[id*='dashboard']","[class*='dashboard']",
        "canvas#gameCanvas","canvas",
        "iframe[src*='game']",
    ]
    for sel in game_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                print(f"[AGENT] Game element found: {sel}")
                return True
        except: pass

    url   = page.url.lower()
    title = await page.title()
    print(f"[AGENT] _game_loaded → url={url} title={title}")

    if any(x in url for x in ["login","signin","register","activate","landing"]):
        return False

    try:
        body = await page.evaluate(
            "() => document.body?.innerText?.slice(0,2000) || ''"
        )
        # Marketing page detected
        if "build your airline empire" in body.lower(): return False
        # Game content detected
        if any(x in body.lower() for x in
               ["alliance","dashboard","my airline","flights","routes",
                "airport","revenue","fuel","fleet"]):
            return True
    except: pass

    return False

# ─────────────────────────────────────────────────────────
#  STRATEGY 0  —  Cookie-based (MOST RELIABLE)
# ─────────────────────────────────────────────────────────
async def _login_cookies(ctx_browser, page) -> bool:
    """
    Load saved cookies → navigate to game.
    No UI interaction needed. Works as long as session is valid.
    """
    cookies_raw = _env("AM4_COOKIES").strip()
    if not cookies_raw:
        print("[AGENT] AM4_COOKIES not set")
        return False

    try:
        cookies = json.loads(cookies_raw)
        if not isinstance(cookies, list) or len(cookies) == 0:
            print("[AGENT] AM4_COOKIES empty or invalid JSON")
            return False

        print(f"[AGENT] Loading {len(cookies)} cookies...")

        # Ensure required fields on each cookie
        fixed = []
        for c in cookies:
            if not c.get("name") or not c.get("value"):
                continue
            fixed.append({
                "name":   c["name"],
                "value":  c["value"],
                "domain": c.get("domain", ".airlinemanager.com"),
                "path":   c.get("path",   "/"),
                "httpOnly": c.get("httpOnly", False),
                "secure":   c.get("secure",   True),
                "sameSite": c.get("sameSite", "None"),
            })

        await ctx_browser.add_cookies(fixed)
        print(f"[AGENT] Cookies set: {len(fixed)}")

        # Navigate directly to game
        game_urls = [
            "https://www.airlinemanager.com/game",
            "https://www.airlinemanager.com/",
            "https://www.airlinemanager.com/#game",
            "https://www.airlinemanager.com/dashboard",
        ]

        for gurl in game_urls:
            try:
                print(f"[AGENT] Navigating: {gurl}")
                await page.goto(gurl, wait_until="commit", timeout=60_000)
                await asyncio.sleep(6)
                await _ss(page, "00_cookie_login")

                if await _game_loaded(page):
                    print(f"[AGENT] ✅ Cookie login success at {gurl}")
                    return True
                print(f"[AGENT] Not in game at {gurl}")
            except Exception as e:
                print(f"[AGENT] Cookie goto error ({gurl}): {e}")

        print("[AGENT] Cookie login failed — cookies may be expired")
        return False

    except json.JSONDecodeError as e:
        print(f"[AGENT] AM4_COOKIES JSON parse error: {e}")
        return False
    except Exception as e:
        print(f"[AGENT] Cookie login error: {e}")
        return False

# ─────────────────────────────────────────────────────────
#  STRATEGY 1  —  Magic / Activation link
# ─────────────────────────────────────────────────────────
async def _login_magic(page) -> bool:
    link = _env("AM4_MAGIC_LINK").strip()
    if not link:
        print("[AGENT] AM4_MAGIC_LINK not set")
        return False

    print(f"[AGENT] Trying magic link...")
    for attempt in range(2):
        try:
            await page.goto(link, wait_until="commit", timeout=60_000)
            await asyncio.sleep(6)
            await _ss(page, "01_magic_link")

            if await _game_loaded(page):
                print("[AGENT] ✅ Magic link success!")
                return True
            print(f"[AGENT] Magic link attempt {attempt+1}: game not loaded")
        except Exception as e:
            print(f"[AGENT] Magic link attempt {attempt+1} error: {e}")
        await asyncio.sleep(3)

    return False

# ─────────────────────────────────────────────────────────
#  STRATEGY 2  —  Email / Password login
# ─────────────────────────────────────────────────────────
async def _login_credentials(page) -> bool:
    email    = _env("AM4_EMAIL")
    password = _env("AM4_PASSWORD")
    if not email or not password:
        print("[AGENT] AM4_EMAIL/AM4_PASSWORD not set")
        return False

    print("[AGENT] Trying credential login...")

    # Try direct login URLs first
    form_found = False
    for url in [
        "https://www.airlinemanager.com/login",
        "https://www.airlinemanager.com/auth/login",
        "https://www.airlinemanager.com/signin",
    ]:
        try:
            await page.goto(url, wait_until="commit", timeout=60_000)
            await asyncio.sleep(3)
            el = await _wait(page, [
                "input[type='email']","input[type='password']",
                "input[name='email']","#email",
                "[placeholder*='email' i]",
            ], timeout=5000)
            if el:
                print(f"[AGENT] Form found at {url}")
                form_found = True
                break
        except Exception as e:
            print(f"[AGENT] {url} error: {e}")

    # Fallback: homepage → click Login
    if not form_found:
        for attempt in range(3):
            try:
                await page.goto("https://www.airlinemanager.com",
                                wait_until="commit", timeout=60_000)
                await asyncio.sleep(5)
                break
            except Exception as e:
                print(f"[AGENT] Homepage attempt {attempt+1}: {e}")
                await asyncio.sleep(3)

        await _ss(page, "02_homepage")

        # Dismiss consent
        for txt in ["Accept","I agree","OK","Allow","Accept all"]:
            try: await page.click(f"text={txt}", timeout=1500); break
            except: pass

        # Log all interactive elements
        try:
            els = await page.evaluate("""
                () => [...document.querySelectorAll('a,button,input')]
                      .slice(0,60)
                      .map(e=>({
                          tag:e.tagName, text:e.textContent.trim().slice(0,40),
                          href:e.href||'', id:e.id||'',
                          cls:e.className.toString().slice(0,60),
                          type:e.type||'', ph:e.placeholder||''
                      }))
            """)
            print("[AGENT] === Page elements ===")
            for e in els:
                if e['text'] or e['id'] or e['ph']:
                    print(f"  {e['tag']:6} text='{e['text']:30}' "
                          f"id='{e['id']:15}' ph='{e['ph']:20}' "
                          f"href='{e['href'][:40]}'")
        except Exception as e:
            print(f"[AGENT] Element dump error: {e}")

        await _ss(page, "03_homepage_rendered")

        # JS click login
        result = await page.evaluate("""
            () => {
                const exact = ['log in','login','sign in','signin'];
                const all = [...document.querySelectorAll('a,button,span,li')];
                for (const el of all) {
                    const t = el.textContent.trim().toLowerCase();
                    if (exact.includes(t) && el.offsetParent !== null) {
                        el.click();
                        return 'exact:' + el.tagName + ':' + el.textContent.trim();
                    }
                }
                for (const el of all) {
                    const t = el.textContent.trim().toLowerCase();
                    if (t.length < 15 && (t.includes('login') || t.includes('log in'))
                        && el.offsetParent !== null) {
                        el.click();
                        return 'partial:' + el.tagName + ':' + el.textContent.trim();
                    }
                }
                return null;
            }
        """)
        print(f"[AGENT] Login btn click: {result}")
        await asyncio.sleep(3)
        await _ss(page, "04_after_login_click")

        el = await _wait(page, [
            "input[type='email']","input[type='password']",
            "input[name='email']","#email",
            "[placeholder*='email' i]","[placeholder*='password' i]",
        ], timeout=8000)
        form_found = el is not None

    if not form_found:
        await _ss(page, "05_no_form")
        print("[AGENT] ❌ No login form found")
        return False

    # Fill credentials
    await _fill(page, [
        "input[name='email']","input[type='email']",
        "#email","#login-email","[placeholder*='email' i]",
    ], email)

    await _fill(page, [
        "input[name='password']","input[type='password']",
        "#password","#login-password","[placeholder*='password' i]",
    ], password)

    await _ss(page, "06_form_filled")

    # Submit
    submitted = await _click(page, [
        "button[type='submit']","input[type='submit']",
        "#loginBtn","#btnLogin",
        "button:has-text('Login')",
        "button:has-text('Log In')",
        "button:has-text('Sign In')",
        ".login-btn",".btn-login",
        "[class*='login'][class*='btn']",
    ])
    if not submitted:
        try: await page.keyboard.press("Enter")
        except: pass

    print("[AGENT] Waiting for game...")
    await asyncio.sleep(8)
    try: await page.wait_for_load_state("networkidle", timeout=40_000)
    except: pass
    await asyncio.sleep(4)
    await _ss(page, "07_post_submit")
    print(f"[AGENT] URL: {page.url}")

    if await _game_loaded(page):
        print("[AGENT] ✅ Credential login success!")
        return True

    print("[AGENT] ❌ Credential login failed")
    return False

# ─────────────────────────────────────────────────────────
#  LOGIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────
async def _login(ctx_browser, page) -> bool:
    """
    Try all login strategies in priority order:
      0. Cookie-based  (most reliable — no UI)
      1. Magic link    (direct game access)
      2. Credentials   (email + password form)
    """
    # Strategy 0: Cookies
    if await _login_cookies(ctx_browser, page):
        return True

    # Strategy 1: Magic link
    if await _login_magic(page):
        return True

    # Strategy 2: Credentials
    if await _login_credentials(page):
        return True

    return False

# ─────────────────────────────────────────────────────────
#  OPEN ALLIANCE TAB  (⭐ star in sidebar)
# ─────────────────────────────────────────────────────────
async def _open_alliance_tab(page) -> bool:
    alliance = _env("AM4_ALLIANCE") or "Eternal Dynasty"
    print(f"[AGENT] Opening alliance: '{alliance}'")

    # Dump sidebar for debugging
    try:
        info = await page.evaluate("""
            () => {
                const all = [...document.querySelectorAll('nav *,#sidebar *,[class*="sidebar"] *,[class*="nav"] *,[class*="menu"] *,[class*="tab"] *')].slice(0,60);
                return all.map(e=>({
                    tag:e.tagName, id:e.id||'',
                    cls:e.className.toString().slice(0,50),
                    txt:e.textContent.trim().slice(0,25),
                    src:(e.src||e.href||'').slice(0,50),
                    title:(e.title||e.alt||'').slice(0,25),
                }));
            }
        """)
        print("[AGENT] === Sidebar/Nav elements ===")
        for e in info:
            if e['txt'] or e['id'] or e['cls']:
                print(f"  {e['tag']:6} id='{e['id']:12}' "
                      f"cls='{e['cls'][:35]}' txt='{e['txt']}' "
                      f"title='{e['title']}'")
    except Exception as e:
        print(f"[AGENT] Sidebar dump error: {e}")

    await _ss(page, "08_before_alliance")

    # JS click: find alliance/star tab
    clicked = await page.evaluate("""
        () => {
            const kws = ['alliance','star','guild','clan'];
            const all = [...document.querySelectorAll('a,button,li,div,span,img,svg')];
            for (const kw of kws) {
                for (const el of all) {
                    const txt   = (el.textContent||'').trim().toLowerCase();
                    const id    = (el.id||'').toLowerCase();
                    const cls   = (el.className||'').toString().toLowerCase();
                    const src   = (el.src||el.href||'').toLowerCase();
                    const title = (el.title||el.alt||'').toLowerCase();
                    if ((txt===kw || id.includes(kw) || cls.includes(kw)
                         || src.includes(kw) || title.includes(kw))
                        && el.offsetParent !== null) {
                        el.click();
                        return kw + ':' + el.tagName + ':' + (el.id||el.className.toString().slice(0,30));
                    }
                }
            }
            return null;
        }
    """)
    print(f"[AGENT] Alliance tab click: {clicked}")
    await asyncio.sleep(3)
    await _ss(page, "09_after_alliance_click")

    # Try search
    filled = await _fill(page, [
        "input[placeholder*='search' i]","input[placeholder*='alliance' i]",
        "input[placeholder*='name' i]","input[placeholder*='find' i]",
        "#allianceSearch","#searchInput","#search",
        "[class*='search'] input","input[type='text']","input[type='search']",
    ], alliance, timeout=4000)

    if filled:
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(2)
        await _ss(page, "10_after_search")

        await _click(page, [
            f"text={alliance}",".result-item",".search-result",
            ".alliance-result","[class*='result']",
        ], timeout=3000)
        await asyncio.sleep(2)

    # Click Members tab
    await _click(page, [
        "text=Members","text=MEMBERS","text=Roster","text=Players",
        "#membersTab","[href*='member']","[class*='member'][class*='tab']",
    ], timeout=3000)

    await asyncio.sleep(2)
    await _ss(page, "11_members_page")

    html = await page.content()
    return len(html) > 500

# ─────────────────────────────────────────────────────────
#  SCRAPE MEMBERS
# ─────────────────────────────────────────────────────────
async def _scrape_members(page, portal_map) -> list:
    members = []

    # DOM rows
    for row_sel in [
        "table tbody tr",".member-row",".alliance-member",
        ".player-row",".roster-row","[class*='member']",
        "[class*='player']","ul li","ol li",
    ]:
        try:
            rows = await page.query_selector_all(row_sel)
            if len(rows) < 2: continue
            print(f"[AGENT] Selector '{row_sel}': {len(rows)} rows")

            for row in rows:
                try:
                    text = (await row.inner_text()).strip()
                    if not text or len(text) < 2: continue

                    airline = ""
                    for ns in [
                        ".airline-name",".name",".player-name",".airline",
                        "td:nth-child(1)","td:nth-child(2)",
                        "[class*='name']","[class*='airline']","strong","b",
                    ]:
                        try:
                            el = await row.query_selector(ns)
                            if el:
                                t=(await el.inner_text()).strip()
                                if t and len(t)>1: airline=t; break
                        except: pass

                    if not airline:
                        airline = text.split("\n")[0].strip()

                    if _is_junk(airline): continue

                    sv = 0.0
                    for vs in [
                        ".share-value",".shares",".stock",".value",
                        "td:nth-child(3)","td:nth-child(4)","td:nth-child(5)",
                        "[class*='share']","[class*='stock']",
                    ]:
                        try:
                            el = await row.query_selector(vs)
                            if el:
                                v=_parse((await el.inner_text()).strip())
                                if v>0: sv=v; break
                        except: pass

                    if sv==0:
                        for cs in ["td","span","[class*='col']"]:
                            cells = await row.query_selector_all(cs)
                            for c in cells:
                                ct=(await c.inner_text()).strip()
                                if re.search(r"\d[\d,\.]*\s*[BMK$]",ct,re.I):
                                    v=_parse(ct)
                                    if v>0: sv=v; break
                            if sv>0: break

                    members.append({"airline":airline,"share_value":sv})
                except: continue

            if members:
                print(f"[AGENT] DOM: {len(members)} members")
                break
        except: continue

    # JSON in source
    if not members:
        try:
            html = await page.content()
            for pat in [
                r'members\s*[=:]\s*(\[[\s\S]*?\])',
                r'players\s*[=:]\s*(\[[\s\S]*?\])',
                r'allianceMembers\s*=\s*(\[[\s\S]*?\]);',
            ]:
                m = re.search(pat, html, re.DOTALL)
                if m:
                    data = json.loads(m.group(1))
                    for item in data:
                        a=(item.get("name") or item.get("airline") or "").strip()
                        sv=float(item.get("shareValue") or item.get("shares") or 0)
                        if a and not _is_junk(a):
                            members.append({"airline":a,"share_value":sv})
                    if members:
                        print(f"[AGENT] JSON: {len(members)} members"); break
        except: pass

    # Portal-matched text fallback
    if not members:
        try:
            body = await page.evaluate("() => document.body.innerText")
            for line in body.split("\n"):
                line = line.strip()
                if not _is_junk(line) and _match(line, portal_map):
                    members.append({"airline":line,"share_value":0.0})
            if members:
                print(f"[AGENT] Portal-matched text: {len(members)}")
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
                    "status":"FATAL: No players in share_users table"})
                await browser.close(); return results

            alliance_name = _env("AM4_ALLIANCE") or "Eternal Dynasty"

            # Login (try all strategies)
            if not await _login(ctx, page):
                results.append({"airline":"—","sts_id":"—","value":0,
                    "status":(
                        "FATAL: All login strategies failed.\n"
                        "→ Set AM4_COOKIES env var (most reliable)\n"
                        "→ See /agentdebug for screenshots\n"
                        "→ See /agentcookies for cookie setup guide"
                    )})
                await browser.close(); return results

            # Open alliance
            await _open_alliance_tab(page)

            # Scrape
            members = await _scrape_members(page, portal_map)
            print(f"[AGENT] Members: {len(members)}")

            if not members:
                results.append({"airline":"—","sts_id":"—","value":0,
                    "status":"FATAL: No members found. Use /agentdebug"})
                await browser.close(); return results

            # Match + Submit
            for m in members:
                airline   = (m.get("airline") or "").strip()
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
                    await _submit_entry(sts_id, player_allia, share_val)
                    results.append({"airline":airline,"sts_id":sts_id,
                        "value":share_val,"status":"submitted"})
                    print(f"[AGENT] ✅ {airline} → {sts_id} → {_fmt(share_val)}")
                    await _dm_player(portal_user.get("discord_id"),
                                     player_allia, share_val)
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
        ch = _bot.get_channel(int(_env("AGENT_CHANNEL") or 0))
        if ch: await ch.send(f"🤖 Agent auto-run (every {h}h)...")
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
           if r["status"] not in("submitted","already_done","no_match")]

    color = 0x00ff88 if sub else (0xffa502 if don else 0xff4757)
    e = discord.Embed(title="🤖 JARVIS AM4 Agent — Complete",
        color=color, timestamp=datetime.now(timezone.utc))
    e.add_field(name="✅ Submitted",    value=str(len(sub)), inline=True)
    e.add_field(name="⏭ Already Done", value=str(len(don)), inline=True)
    e.add_field(name="❓ No Match",    value=str(len(nm)),  inline=True)

    if sub:
        lines=[f"• **{r['airline']}** (`{r['sts_id']}`) → {_fmt(r['value'])}"
               for r in sub[:10]]
        if len(sub)>10: lines.append(f"*...+{len(sub)-10}*")
        e.add_field(name="Submitted",value="\n".join(lines),inline=False)
    if nm:
        e.add_field(
            name="⚠️ No STS match — set airline name on portal",
            value="\n".join(f"• {r['airline']}" for r in nm[:8]),inline=False)
    if err:
        e.add_field(name="❌ Errors",
            value="\n".join(r['status'] for r in err[:3]),inline=False)

    e.set_footer(text="JARVIS • AM4 Portal Agent")
    await channel.send(embed=e)

# ─────────────────────────────────────────────────────────
#  DISCORD COMMANDS
# ─────────────────────────────────────────────────────────
def _register_commands(bot):

    @bot.hybrid_command(name="agentrun",
        description="[Admin] Login AM4 → scrape alliance → auto-submit shares")
    async def agentrun(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        if _state["running"]:
            return await ctx.send("⚠️ Already running.", ephemeral=True)

        alliance = _env("AM4_ALLIANCE") or "Eternal Dynasty"
        has_cookies = bool(_env("AM4_COOKIES"))
        has_magic   = bool(_env("AM4_MAGIC_LINK"))
        has_creds   = bool(_env("AM4_EMAIL") and _env("AM4_PASSWORD"))

        status_line = (
            f"🍪 Cookies: {'✅' if has_cookies else '❌'}  "
            f"🔗 Magic link: {'✅' if has_magic else '❌'}  "
            f"🔑 Credentials: {'✅' if has_creds else '❌'}"
        )

        await ctx.send(
            f"🤖 **JARVIS Agent Starting...**\n"
            f"{status_line}\n"
            f"Alliance: `{alliance}`\n"
            f"*~90 sec — results will post here.*"
        )
        asyncio.create_task(_run_and_post(ctx.channel))

    async def _run_and_post(ch):
        r = await run_agent()
        await _post_results(ch, r)

    @bot.hybrid_command(name="agentstatus",
        description="Check AM4 agent last run status")
    async def agentstatus(ctx):
        e = discord.Embed(title="🤖 JARVIS AM4 Agent", color=0x00d4ff)
        if _state["running"]:
            e.description="⚙️ **Running...** scan in progress"
            e.color=0xffa502
        elif _state["last_run"]:
            e.description=f"✅ Last: `{_state['last_run'].strftime('%d %b %Y %I:%M %p IST')}`"
            log=_state["log"]
            s=sum(1 for r in log if r["status"]=="submitted")
            d=sum(1 for r in log if r["status"]=="already_done")
            n=sum(1 for r in log if r["status"]=="no_match")
            er=sum(1 for r in log if r["status"] not in
                   ("submitted","already_done","no_match"))
            e.add_field(name="✅",value=str(s),inline=True)
            e.add_field(name="⏭",value=str(d),inline=True)
            e.add_field(name="❓",value=str(n),inline=True)
            e.add_field(name="❌",value=str(er),inline=True)
            nm_r=[r for r in log if r["status"]=="no_match"]
            if nm_r:
                e.add_field(name="No portal match (set airline name on portal):",
                    value="\n".join(f"• {r['airline']}" for r in nm_r[:8]),
                    inline=False)
        else:
            e.description="💤 Not run yet."
        e.set_footer(text="JARVIS • AM4 Agent")
        await ctx.send(embed=e)

    @bot.hybrid_command(name="agentschedule",
        description="[Admin] Auto-run every N hours (0=off)")
    @app_commands.describe(hours="Hours between runs. 0 to disable.")
    async def agentschedule(ctx, hours: int = 12):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        _state["schedule_h"] = hours
        await ctx.send("🔕 Disabled." if hours<=0
                       else f"⏰ Agent runs every **{hours}h**.")

    @bot.hybrid_command(name="agentdebug",
        description="[Admin] Get debug screenshots from last run")
    async def agentdebug(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        import os as _os
        labels=[
            ("00_cookie_login","Cookie Login"),
            ("01_magic_link","Magic Link"),
            ("02_homepage","Homepage"),
            ("03_homepage_rendered","Homepage Rendered"),
            ("04_after_login_click","After Login Click"),
            ("05_no_form","No Form Found"),
            ("06_form_filled","Form Filled"),
            ("07_post_submit","Post Submit"),
            ("08_before_alliance","Before Alliance"),
            ("09_after_alliance_click","After Alliance Click"),
            ("10_after_search","After Search"),
            ("11_members_page","Members Page"),
        ]
        files=[discord.File(f"/tmp/am4_{n}.png",f"{l.replace(' ','_')}.png")
               for n,l in labels if _os.path.exists(f"/tmp/am4_{n}.png")]
        if not files:
            return await ctx.send("❌ No screenshots. Run `/agentrun` first.",
                                  ephemeral=True)
        for i in range(0,len(files),10):
            await ctx.send(
                f"📸 Debug {i+1}-{i+len(files[i:i+10])} of {len(files)}:",
                files=files[i:i+10])

    @bot.hybrid_command(name="agentcookies",
        description="How to extract and set AM4 cookies for reliable login")
    async def agentcookies(ctx):
        e = discord.Embed(
            title="🍪 AM4 Cookie Login Setup",
            description=(
                "Cookie-based login is the **most reliable** method.\n"
                "No UI selectors — works even if AM4 changes their website.\n\n"
                "**Steps:**\n\n"
                "**1.** Open Chrome on desktop\n"
                "**2.** Go to `https://www.airlinemanager.com` and **login**\n"
                "**3.** Press `F12` → click **Console** tab\n"
                "**4.** Paste this JS and press Enter:\n"
                "```js\n"
                "copy(JSON.stringify(document.cookie.split(';').map(c=>{\n"
                "  const [name,...rest]=c.trim().split('=');\n"
                "  return {name:name.trim(),value:rest.join('=').trim(),\n"
                "  domain:'.airlinemanager.com',path:'/'};\n"
                "})))\n"
                "```\n"
                "**5.** Open Notepad → Ctrl+V (you'll see JSON)\n"
                "**6.** Copy that JSON\n"
                "**7.** In Render → **Environment** → add:\n"
                "`AM4_COOKIES` = *(paste JSON here)*\n\n"
                "**Cookies last weeks/months.**\n"
                "Refresh them if agent starts failing again."
            ),
            color=0x00d4ff
        )
        e.set_footer(text="JARVIS • AM4 Agent")
        await ctx.send(embed=e)
