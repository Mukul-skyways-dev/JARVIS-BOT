import discord
import random 
from discord.ext import commands
from discord.ui import View, Button

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import io

import sqlite3
import os
import requests

from flask import Flask
from threading import Thread

# =========================
# KEEP ALIVE SERVER
# =========================
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# =========================
# BOT CONFIG
# =========================
TOKEN = os.getenv("TOKEN")
WELCOME_ROLE_NAME = "Member"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE AUTO DOWNLOAD
# =========================

DB_URL = "https://github.com/Mukul-skyways-dev/JARVIS-BOT/releases/download/Dv1/am4_data.db.updated"
DB_FILE = "am4_data.db"

def download_db():
    print("🔄 Checking database...")

    # always ensure fresh/correct DB (important for Render issues)
    print("⬇ Downloading database from GitHub Release...")

    try:
        response = requests.get(DB_URL, timeout=30)
        response.raise_for_status()

        with open(DB_FILE, "wb") as f:
            f.write(response.content)

        print("✅ Database downloaded successfully")

    except Exception as e:
        print("❌ DB download failed:", e)

# MUST run BEFORE sqlite connect
download_db()

# =========================
# SQLITE CONNECTION
# =========================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# =========================
# DIFFICULTY SYSTEM
# =========================
def get_user_mode(user_id):
    cursor.execute(
        "SELECT difficulty FROM player_settings WHERE user_id=?",
        (str(user_id),)
    )
    row = cursor.fetchone()

    if row and row[0]:
        return row[0].lower()

    return "realism"


def set_user_mode(user_id, mode):
    cursor.execute(
        "INSERT OR REPLACE INTO player_settings (user_id, difficulty) VALUES (?, ?)",
        (str(user_id), mode)
    )
    conn.commit()

# =========================
# MENU VIEW
# =========================
class EliteMenu(View):
    def __init__(self):
        super().__init__(timeout=None)

    # ✈ ROUTE
    @discord.ui.button(label="✈ Route System", style=discord.ButtonStyle.blurple)
    async def route_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="✈ Route Command",
            description="""
`!route DEL BOM A320`

📊 Includes:
• Flight time, distance
• Demand (Y/J/F)
• Config & Ticket price
• A-check, Repair
• Profit (Trip + Day)
• Mods & Stopover
""",
            color=0x3498db
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 🔥 BEST
    @discord.ui.button(label="🔥 Best Routes", style=discord.ButtonStyle.red)
    async def best_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="🔥 Best Route Finder",
            description="""
`!best_r DEL A320`
`!best_short DEL A320`
`!best_long DEL A320`

📈 Finds:
• Most profitable routes
• Short / Long optimization
""",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ⚖ COMPARE
    @discord.ui.button(label="⚖ Compare Planes", style=discord.ButtonStyle.gray)
    async def compare_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="⚖ Plane Comparison",
            description="""
`!compare A320 vs B737`

📊 Shows:
• Cost, Capacity, Range
• Speed, Fuel, CO2
• Income (Flight/Day)
• Winner Highlight
""",
            color=0x95a5a6
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ℹ GENERAL
    @discord.ui.button(label="ℹ General", style=discord.ButtonStyle.secondary)
    async def general(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="ℹ General Commands",
            description="""
`!menu`
`!ping`

🤖 Chat:
Hi / Hello / Jarvis
""",
            color=0x2ecc71
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# MENU COMMAND
# =========================
@bot.command()
async def menu(ctx):

    embed = discord.Embed(
        title="🤖 JARVIS CONTROL PANEL",
        description="""
━━━━━━━━━━━━━━━━━━━━━━━

✈ **ROUTE SYSTEM**
`!route DEL BOM A320`

🔥 **BEST ROUTES**
`!best_r DEL A320`
`!best_short DEL A320`
`!best_long DEL A320`

⚖ **PLANE COMPARISON**
`!compare A320 vs B737`

━━━━━━━━━━━━━━━━━━━━━━━
👇 Use buttons below for help
━━━━━━━━━━━━━━━━━━━━━━━
""",
        color=0x00BFFF
    )

    # server icon (optional)
    guild = ctx.guild

    if guild is not None and guild.icon is not None:
        embed.set_thumbnail(url=guild.icon.url)

    embed.set_footer(text="JARVIS - A AERO CROWN DYNASTY OFFICIAL BOT")

    await ctx.send(embed=embed, view=EliteMenu())

# =========================
# UTILS
# =========================
def clean(x):
    return str(x).replace(",", "").replace('"', "").replace("'", "").strip()

def to_int(x):
    try: return int(float(clean(x)))
    except: return 0

def to_float(x):
    try: return float(clean(x))
    except: return 0.0

def norm(x):
    return x.upper().replace("-", "").replace(" ", "")

def money(x):
    return f"${x:,.0f}"

def format_time(hours):
    h = int(hours)
    m = int((hours - h) * 60)
    s = int((((hours - h) * 60) - m) * 60)
    return f"{h:02}:{m:02}:{s:02} ({round(hours,3)} hr)"

# =========================
# FETCH DATA
# =========================
def get_route(frm, to):
    cursor.execute("""
    SELECT * FROM routes
    WHERE (f_iata=? AND t_iata=?)
       OR (f_iata=? AND t_iata=?)
    LIMIT 1
    """, (frm.upper(), to.upper(), to.upper(), frm.upper()))

    row = cursor.fetchone()
    if not row: return None

    return {
        "distance": to_float(row[5]),
        "y": to_int(row[9]),
        "j": to_int(row[10]),
        "f": to_int(row[11]),
        "cargo": to_int(row[8])
    }

def get_all_planes():
    cursor.execute("SELECT model, variant, capacity, range, speed, fuel_efficiency, cost FROM aircraft")
    planes = []
    for r in cursor.fetchall():
        planes.append({
            "name": f"{r[0]} {r[1]}",
            "capacity": to_int(r[2]),
            "range": to_float(r[3]),
            "speed": to_float(r[4]),
            "fuel": to_float(r[5]),
            "cost": to_int(r[6])
        })
    return planes

def get_plane(name):
    key = norm(name)
    for p in get_all_planes():
        if key in norm(p["name"]):
            return p
    return None

# =========================
# CALC ENGINE (UNIFIED FINAL)
# =========================
def calc(route, plane, user_id, mods=None):

    # =========================
    # USER MODE
    # =========================
    mode = get_user_mode(user_id)

    # =========================
    # BASE VALUES
    # =========================
    dist = float(route["distance"])
    speed = float(plane["speed"])

    if mods and "speed" in mods:
        speed *= 1.1

    time = dist / speed if speed else 1
    trips = max(1, int(24 / time))

    # =========================
    # DEMAND
    # =========================
    y = int(route["y"])
    j = int(route["j"])
    f = int(route["f"])

    total = y + j + f
    cap = int(plane["capacity"])

    # =========================
    # DIFFICULTY SETTINGS
    # =========================
    if mode == "easy":
        lf = 1.0

        y_mul, j_mul, f_mul = 0.35, 0.9, 1.8
        fuel_mult, co2_mult = 4, 1.8

        acheck, repair = 20000, 15000
        cargo_mul = 0.5

    else:  # REALISM
        lf = 0.85

        y_mul, j_mul, f_mul = 0.28, 0.7, 1.4
        fuel_mult, co2_mult = 5.5, 2.5

        acheck, repair = 40000, 25000
        cargo_mul = 0.35

    # =========================
    # CONFIGURATION
    # =========================
    if total > 0:
        y_c = int(cap * (y / total) * lf)
        j_c = int(cap * (j / total) * lf)
        f_c = cap - y_c - j_c
    else:
        y_c = j_c = f_c = 0

    # =========================
    # TICKET PRICES
    # =========================
    y_price = dist * y_mul
    j_price = dist * j_mul
    f_price = dist * f_mul

    # =========================
    # INCOME
    # =========================
    income_trip = (
        (y_c * y_price) +
        (j_c * j_price) +
        (f_c * f_price)
    )

    # cargo income
    cargo = float(route.get("cargo", 0))
    income_trip += cargo * cargo_mul

    # =========================
    # COSTS
    # =========================
    fuel = dist * float(plane["fuel"]) * fuel_mult
    co2 = dist * co2_mult

    if mods:
        if "fuel" in mods:
            fuel *= 0.9
        if "co2" in mods:
            co2 *= 0.9

    fuel_lb = fuel * 2.2
    co2_q = co2 * 1.1

    # =========================
    # PROFIT
    # =========================
    profit_trip = income_trip - fuel - co2 - acheck - repair
    ci = int((profit_trip / income_trip) * 100) if income_trip else 0

    # =========================
    # RETURN DATA
    # =========================
    return {
        "mode": mode,

        # flight
        "time": round(time, 2),
        "trips": trips,

        # config
        "y": y_c,
        "j": j_c,
        "f": f_c,

        # ticket prices
        "y_price": int(y_price),
        "j_price": int(j_price),
        "f_price": int(f_price),

        # income
        "income_trip": int(income_trip),

        # cost
        "fuel": int(fuel),
        "fuel_lb": int(fuel_lb),

        "co2": int(co2),
        "co2_q": int(co2_q),

        "acheck": acheck,
        "repair": repair,

        # profit
        "profit_trip": int(profit_trip),
        "ci": ci,

        # per day
        "income_day": int(income_trip * trips),
        "fuel_day": int(fuel * trips),
        "co2_day": int(co2 * trips),
        "profit_day": int(profit_trip * trips)
    }

# ========================
# Leaderboard 
# ========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0,
    last_used REAL DEFAULT 0
)
""")
conn.commit()


# =========================
# LIVE USAGE TRACKER (ANTI-SPAM + LIVE POINTS)
# =========================
COOLDOWN = 3  # seconds

def add_usage(user):
    now = time.time()

    cursor.execute("SELECT last_used FROM users WHERE user_id=?", (str(user.id),))
    row = cursor.fetchone()

    # anti spam protection
    if row and now - row[0] < COOLDOWN:
        return

    cursor.execute("""
    INSERT INTO users (user_id, username, points, last_used)
    VALUES (?, ?, 1, ?)
    ON CONFLICT(user_id)
    DO UPDATE SET
        points = points + 1,
        username = excluded.username,
        last_used = excluded.last_used
    """, (str(user.id), user.name, now))

    conn.commit()


# =========================
# LEADERBOARD VIEW (LIVE DASHBOARD)
# =========================
class LeaderboardView(View):

    def __init__(self):
        super().__init__(timeout=180)
        self.page = 0
        self.data = self.fetch()

    # =========================
    # FETCH DATA
    # =========================
    def fetch(self):
        cursor.execute("""
        SELECT username, points
        FROM users
        ORDER BY points DESC
        """)
        return cursor.fetchall()

    # =========================
    # PAGINATION
    # =========================
    def page_data(self):
        start = self.page * 10
        return self.data[start:start + 10]

    # =========================
    # EMBED UI
    # =========================
    def build_embed(self):

        medals = ["🥇", "🥈", "🥉"]

        text = ""

        for i, (name, pts) in enumerate(self.page_data(), start=1):
            rank = self.page * 10 + i
            medal = medals[rank - 1] if rank <= 3 else "🔹"

            text += f"{medal} **#{rank} {name}** — `{pts:,}` uses\n"

        embed = discord.Embed(
            title="📊 LIVE JARVIS USAGE LEADERBOARD",
            description=text or "No data yet",
            color=0x1e2b4a
        )

        embed.set_footer(
            text=f"Page {self.page + 1} • Live Tracking • AERO CROWN DYNASTY"
        )

        return embed

    # =========================
    # GRAPH (ANIMATED STYLE BAR)
    # =========================
    def build_graph(self):

        top = self.data[:10]

        names = [x[0][:8] for x in top]
        values = [x[1] for x in top]

        plt.figure(figsize=(8, 4))
        plt.style.use("dark_background")

        plt.gca().set_facecolor("#0b1a40")
        plt.gcf().patch.set_facecolor("#0b1a40")

        bars = plt.bar(names, values, color="#00e5ff")

        # glow effect illusion
        for bar in bars:
            bar.set_alpha(0.9)

        plt.xticks(rotation=40)
        plt.title("LIVE BOT USAGE RANKING", color="white")

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=300)
        buf.seek(0)
        plt.close()

        return buf

    # =========================
    # BUTTONS
    # =========================

    @discord.ui.button(label="⬅ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, button):

        if self.page > 0:
            self.page -= 1

        await self.update(interaction)

    @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):

        if (self.page + 1) * 10 < len(self.data):
            self.page += 1

        await self.update(interaction)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.success)
    async def refresh(self, interaction, button):

        self.data = self.fetch()
        self.page = 0

        await self.update(interaction)

    @discord.ui.button(label="📊 Graph", style=discord.ButtonStyle.grey)
    async def graph(self, interaction, button):

        buf = self.build_graph()
        file = discord.File(buf, "leaderboard.png")

        embed = discord.Embed(
            title="📊 Live Usage Graph",
            color=0x1e2b4a
        )

        embed.set_image(url="attachment://leaderboard.png")

        await interaction.response.edit_message(
            embed=embed,
            attachments=[file],
            view=self
        )

    # =========================
    # UPDATE ENGINE
    # =========================
    async def update(self, interaction):

        self.data = self.fetch()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            attachments=[],
            view=self
        )


# =========================
# AUTO TRACK EVERY COMMAND USE (GLOBAL HOOK)
# =========================
@bot.event
async def on_command(ctx):
    add_usage(ctx.author)


# =========================
# LEADERBOARD COMMAND
# =========================
@bot.command()
async def leaderboard(ctx):

    view = LeaderboardView()

    if not view.data:
        return await ctx.send("❌ No usage data yet")

    await ctx.send(
        embed=view.build_embed(),
        view=view
    )

# =========================
# DIFFICULTY COMMAND
# =========================
@bot.command()
async def difficulty(ctx, mode=None):

    if not mode:
        current = get_user_mode(ctx.author.id)
        return await ctx.send(f"⚙ Your difficulty: **{current.upper()}**")

    mode = mode.lower()

    if mode not in ["easy", "realism"]:
        return await ctx.send("❌ Use: easy / realism")

    set_user_mode(ctx.author.id, mode)

    await ctx.send(f"✅ Difficulty set to **{mode.upper()}**")

# =========================
# AIRPORT HELPER (FINAL STABLE)
# =========================
def airport_name(iata):
    try:
        iata = iata.upper()

        # BEST METHOD → directly airport table style lookup
        cursor.execute("""
        SELECT city, country 
        FROM routes
        WHERE iata = ?
        LIMIT 1
        """, (iata,))

        row = cursor.fetchone()

        # fallback (very important)
        if not row:
            cursor.execute("""
            SELECT city, country 
            FROM routes
            WHERE f_iata = ? OR t_iata = ?
            LIMIT 1
            """, (iata, iata))

            row = cursor.fetchone()

        if row:
            city = row[0]
            country = row[1]

            # safe return
            if city and country:
                return f"{iata} — {city}, {country}"

    except:
        pass

    return iata  # fallback (no blank ever)

# =========================
# ROUTE COMMAND (FINAL)
# =========================
@bot.command()
async def route(ctx, frm, to, *, plane_name):

    route = get_route(frm, to)
    plane = get_plane(plane_name)

    if not route:
        return await ctx.send("❌ Route not found")
    if not plane:
        return await ctx.send("❌ Plane not found")

    distance_total = float(route["distance"])
    plane_range = float(plane["range"])

    # =========================
    # STOPOVER (FAST + REAL)
    # =========================
    stop_airport = None

    if distance_total > plane_range:
        cursor.execute("""
        SELECT t_iata 
        FROM routes
        WHERE f_iata = ?
        AND CAST(distance AS REAL) < ?
        ORDER BY CAST(distance AS REAL) DESC
        LIMIT 1
        """, (frm.upper(), plane_range))

        row = cursor.fetchone()
        if row:
            stop_airport = row[0]

    # =========================
    # CALC ENGINE
    # =========================
    result = calc(route, plane, ctx.author.id)
    mode = result["mode"]

    # =========================
    # ROUTE DISPLAY
    # =========================
    from_txt = airport_name(frm)
    to_txt = airport_name(to)

    if stop_airport:
        stop_txt = airport_name(stop_airport)
        route_display = f"{from_txt}\n→ {stop_txt}\n→ {to_txt}"
    else:
        route_display = f"{from_txt}\n→ {to_txt}"

    # =========================
    # EMBED
    # =========================
    embed = discord.Embed(
        title=f"{plane['name']} • Route Analysis V2.0.1",
        description=f"```{route_display}```",
        color=0x2b2d31
    )

    # FLIGHT INFO
    embed.add_field(
        name="Flight Info",
        value=(
            f"Distance: {int(distance_total):,} km\n"
            f"Trips: {result['trips']}/day\n"
            f"Mode: {mode.upper()}"
        ),
        inline=False
    )

    # DEMAND
    embed.add_field(
        name="Demand",
        value=(
            f"Y {route['y']}\n"
            f"J {route['j']}\n"
            f"F {route['f']}"
        ),
        inline=True
    )

    # CONFIG
    embed.add_field(
        name="Configuration",
        value=(
            f"Y {result['y']}\n"
            f"J {result['j']}\n"
            f"F {result['f']}"
        ),
        inline=True
    )

    # TICKET PRICING (FROM CALC)
    embed.add_field(
        name="Ticket Pricing",
        value=(
            f"Y ${result['y_price']:,}\n"
            f"J ${result['j_price']:,}\n"
            f"F ${result['f_price']:,}"
        ),
        inline=True
    )

    # PER FLIGHT
    embed.add_field(
        name="Per Flight",
        value=(
            f"Income: ${result['income_trip']:,}\n"
            f"Fuel: ${result['fuel']:,}\n"
            f"CO2: ${result['co2']:,}\n"
            f"Maint: ${result['acheck'] + result['repair']:,}\n\n"
            f"Profit: ${result['profit_trip']:,}\n"
            f"CI: {result['ci']}%"
        ),
        inline=False
    )

    # PER DAY
    embed.add_field(
        name="Per Day",
        value=(
            f"Income: ${result['income_day']:,}\n"
            f"Fuel: ${result['fuel_day']:,}\n"
            f"CO2: ${result['co2_day']:,}\n"
            f"Maint: ${(result['acheck'] + result['repair']) * result['trips']:,}\n\n"
            f"Profit: ${result['profit_day']:,}\n"
            f"Flights: {result['trips']}"
        ),
        inline=False
    )

    embed.set_footer(text="JARVIS • AERO CROWN DYNASTY OFFICIAL BOT")

    await ctx.send(embed=embed)

# =========================
# IMPORTS (SAFE MERGE)
# =========================
import discord
from discord.ui import View
import matplotlib.pyplot as plt
import numpy as np
import io

# =========================
# COMPARE VIEW 
# =========================
class CompareView(View):
    def __init__(self, p1, p2, r1, r2):
        super().__init__(timeout=120)

        self.p1 = p1
        self.p2 = p2
        self.r1 = r1
        self.r2 = r2

        self.page = 0

    # =========================
    # SAFE FORMATTER
    # =========================
    def fmt(self, a, b, reverse=False):
        try:
            a = float(a)
            b = float(b)
        except:
            return f"{a}"

        if reverse:
            return f"**{a:,.0f}**" if a < b else f"{a:,.0f}"
        return f"**{a:,.0f}**" if a > b else f"{a:,.0f}"

    # =========================
    # PAGE 1 - TEXT EMBED
    # =========================
    def build_embed(self):

        embed = discord.Embed(
            title=f"{self.p1['name']}  VS  {self.p2['name']}",
            description="```Advanced Aircraft Analytics Engine```",
            color=0x1e2b4a  # DARK BLUE THEME
        )

        # ================= SPEC =================
        embed.add_field(
            name="✦ Specifications",
            value=(
                f"Capacity → {self.fmt(self.p1['capacity'], self.p2['capacity'])} │ {self.fmt(self.p2['capacity'], self.p1['capacity'])}\n"
                f"Range → {self.fmt(self.p1['range'], self.p2['range'])} │ {self.fmt(self.p2['range'], self.p1['range'])}\n"
                f"Speed → {self.fmt(self.p1['speed'], self.p2['speed'])} │ {self.fmt(self.p2['speed'], self.p1['speed'])}\n"
                f"Fuel → {self.fmt(self.p1['fuel'], self.p2['fuel'], True)} │ {self.fmt(self.p2['fuel'], self.p1['fuel'], True)}"
            ),
            inline=False
        )

        # ================= OPS =================
        embed.add_field(
            name="✦ Operations",
            value=(
                f"Trips/Day → {self.fmt(self.r1['trips'], self.r2['trips'])} │ {self.fmt(self.r2['trips'], self.r1['trips'])}\n"
                f"Flight Time → {self.fmt(self.r1['time'], self.r2['time'], True)} │ {self.fmt(self.r2['time'], self.r1['time'], True)}\n"
                f"CI Score → {self.fmt(self.r1['ci'], self.r2['ci'])}% │ {self.fmt(self.r2['ci'], self.r1['ci'])}%"
            ),
            inline=False
        )

        # ================= REVENUE =================
        embed.add_field(
            name="✦ Revenue",
            value=(
                f"Income/Flight → {self.fmt(self.r1['income_trip'], self.r2['income_trip'])} │ {self.fmt(self.r2['income_trip'], self.r1['income_trip'])}\n"
                f"Profit/Flight → {self.fmt(self.r1['profit_trip'], self.r2['profit_trip'])} │ {self.fmt(self.r2['profit_trip'], self.r1['profit_trip'])}\n"
                f"Income/Day → {self.fmt(self.r1['income_day'], self.r2['income_day'])} │ {self.fmt(self.r2['income_day'], self.r1['income_day'])}\n"
                f"Profit/Day → {self.fmt(self.r1['profit_day'], self.r2['profit_day'])} │ {self.fmt(self.r2['profit_day'], self.r1['profit_day'])}"
            ),
            inline=False
        )

        # ================= COST =================
        embed.add_field(
            name="✦ Cost Analysis",
            value=(
                f"Fuel/Flight → {self.fmt(self.r1['fuel'], self.r2['fuel'], True)} │ {self.fmt(self.r2['fuel'], self.r1['fuel'], True)}\n"
                f"CO2/Flight → {self.fmt(self.r1['co2'], self.r2['co2'], True)} │ {self.fmt(self.r2['co2'], self.r1['co2'], True)}\n"
                f"Maint → {self.fmt(self.r1['acheck'] + self.r1['repair'], self.r2['acheck'] + self.r2['repair'], True)} │ {self.fmt(self.r2['acheck'] + self.r2['repair'], self.r1['acheck'] + self.r1['repair'], True)}"
            ),
            inline=False
        )

        # ================= EFF =================
        embed.add_field(
            name="✦ Efficiency",
            value=(
                f"Fuel(lb) → {self.fmt(self.r1['fuel_lb'], self.r2['fuel_lb'], True)} │ {self.fmt(self.r2['fuel_lb'], self.r1['fuel_lb'], True)}\n"
                f"CO2(q) → {self.fmt(self.r1['co2_q'], self.r2['co2_q'], True)} │ {self.fmt(self.r2['co2_q'], self.r1['co2_q'], True)}"
            ),
            inline=False
        )

        winner = self.p1["name"] if self.r1["profit_day"] > self.r2["profit_day"] else self.p2["name"]
        embed.set_footer(text=f"Page 1/3 • Winner: {winner}")

        return embed

    # =========================
    # GRAPH (FIXED NORMALIZATION + STABLE)
    # =========================
    def make_graph(self):

        labels = ["Income", "Profit", "Fuel", "CO2", "Trips"]

        p1_vals = [
            self.r1["income_day"],
            self.r1["profit_day"],
            self.r1["fuel_day"],
            self.r1["co2_day"],
            self.r1["trips"]
        ]

        p2_vals = [
            self.r2["income_day"],
            self.r2["profit_day"],
            self.r2["fuel_day"],
            self.r2["co2_day"],
            self.r2["trips"]
        ]

        # SAFE NORMALIZATION (NO FLAT LINE BUG)
        max_vals = [max(a, b) if max(a, b) != 0 else 1 for a, b in zip(p1_vals, p2_vals)]
        p1n = [a / m for a, m in zip(p1_vals, max_vals)]
        p2n = [b / m for b, m in zip(p2_vals, max_vals)]

        x = range(len(labels))

        plt.figure(figsize=(9, 5))
        plt.style.use("dark_background")

        # DARK BLUE BACKGROUND
        plt.gca().set_facecolor("#0b1a40")
        plt.gcf().patch.set_facecolor("#0b1a40")

        # PLOTS
        plt.plot(x, p1n, marker='o', linewidth=2.5, label=self.p1["name"])
        plt.plot(x, p2n, marker='s', linewidth=2.5, linestyle='--', label=self.p2["name"])

        plt.xticks(x, labels)
        plt.grid(alpha=0.4, linestyle=":")
        plt.legend()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=300)
        buf.seek(0)
        plt.close()

        return buf

    # =========================
    # RADAR (FIXED SCALING)
    # =========================
    def make_radar(self):

        labels = ["Income", "Profit", "Efficiency", "Speed", "Trips"]

        def safe(a, b):
            m = max(a, b)
            return (a / m if m else 0), (b / m if m else 0)

        i1, i2 = safe(self.r1["income_day"], self.r2["income_day"])
        p1v, p2v = safe(self.r1["profit_day"], self.r2["profit_day"])
        s1, s2 = safe(self.p1["speed"], self.p2["speed"])
        t1, t2 = safe(self.r1["trips"], self.r2["trips"])

        e1 = (i1 + p1v) / 2
        e2 = (i2 + p2v) / 2

        v1 = [i1, p1v, e1, s1, t1]
        v2 = [i2, p2v, e2, s2, t2]

        angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()

        v1 += v1[:1]
        v2 += v2[:1]
        angles += angles[:1]

        plt.figure(figsize=(6, 6))
        ax = plt.subplot(111, polar=True)

        ax.set_facecolor("#0b1a40")
        plt.gcf().patch.set_facecolor("#0b1a40")

        ax.plot(angles, v1, linewidth=2.5, label=self.p1["name"])
        ax.plot(angles, v2, linewidth=2.5, linestyle="--", label=self.p2["name"])

        ax.fill(angles, v1, alpha=0.15)
        ax.fill(angles, v2, alpha=0.15)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, color="white")

        plt.legend()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=300)
        buf.seek(0)
        plt.close()

        return buf

    # =========================
    # BUTTONS
    # =========================
    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction, button):
        self.page = (self.page - 1) % 3
        await self.update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction, button):
        self.page = (self.page + 1) % 3
        await self.update(interaction)

    # =========================
    # UPDATE ENGINE
    # =========================
    async def update(self, interaction):

        if self.page == 0:
            await interaction.response.edit_message(
                embed=self.build_embed(),
                attachments=[],
                view=self
            )

        elif self.page == 1:
            buf = self.make_graph()
            file = discord.File(buf, "graph.png")

            embed = discord.Embed(
                title="📊 Performance Graph",
                color=0x1e2b4a
            )
            embed.set_image(url="attachment://graph.png")

            await interaction.response.edit_message(
                embed=embed,
                attachments=[file],
                view=self
            )

        elif self.page == 2:
            buf = self.make_radar()
            file = discord.File(buf, "radar.png")

            embed = discord.Embed(
                title="🧭 Radar Analysis",
                color=0x1e2b4a
            )
            embed.set_image(url="attachment://radar.png")

            await interaction.response.edit_message(
                embed=embed,
                attachments=[file],
                view=self
            )

# =========================
# COMMAND
# =========================
@bot.command()
async def compare(ctx, *, planes_input):

    try:
        p1_name, p2_name = planes_input.lower().split(" vs ")
    except:
        return await ctx.send("❌ Use: !compare A320 vs B737")

    p1 = get_plane(p1_name)
    p2 = get_plane(p2_name)

    if not p1 or not p2:
        return await ctx.send("❌ Plane not found")

    route = {
        "distance": 5000,
        "y": 300,
        "j": 50,
        "f": 10,
        "cargo": 10000
    }

    r1 = calc(route, p1, ctx.author.id)
    r2 = calc(route, p2, ctx.author.id)

    view = CompareView(p1, p2, r1, r2)

    await ctx.send(embed=view.build_embed(), view=view)

# =========================
# BEST PLANE
# =========================
@bot.command()
async def best(ctx, frm, to):

    r = get_route(frm,to)
    if not r:
        await ctx.send("❌ Route not found"); return

    best_plane = None
    best_score = -999999999

    for p in get_all_planes():
        if r["distance"] > p["range"]: continue

        c = calc(r,p)
        score = c["profit_day"] + p["speed"]*10 - p["fuel"]*100

        if score > best_score:
            best_score = score
            best_plane = p
            best_calc = c

    embed = discord.Embed(title="🏆 BEST PLANE", color=0x00ff00)
    embed.add_field(name="Plane", value=best_plane["name"], inline=False)
    embed.add_field(name="Profit/day", value=money(best_calc["profit_day"]), inline=False)

    await ctx.send(embed=embed)
# =========================
# BEST ROUTE COMMAND
# =========================
@bot.command(name="best_r", aliases=["bestr", "top"])
async def best(ctx, airport, *, plane_name):

    airport = airport.upper()
    plane = get_plane(plane_name)

    if not plane:
        await ctx.send("❌ Plane not found")
        return

    # =========================
    # GET ROUTES (LIMITED FAST QUERY)
    # =========================
    cursor.execute("""
    SELECT t_iata, distance, dem_y, dem_j, dem_f
    FROM routes
    WHERE f_iata = ?
    LIMIT 300
    """, (airport,))

    routes = cursor.fetchall()

    if not routes:
        await ctx.send("❌ No routes found")
        return

    results = []

    for r in routes:
        try:
            dest, dist, y, j, f = r

            distance = to_float(dist)

            # skip if too long (no stopover logic here for speed)
            if distance > plane["range"]:
                continue

            y = int(y)
            j = int(j)
            f = int(f)

            total_demand = y + j + f
            if total_demand == 0:
                continue

            # =========================
            # CONFIG
            # =========================
            cap = plane["capacity"]

            y_ratio = y / total_demand
            j_ratio = j / total_demand
            f_ratio = f / total_demand

            y_seats = int(cap * y_ratio)
            j_seats = int(cap * j_ratio)
            f_seats = cap - y_seats - j_seats

            # load factor
            lf = 0.85
            y_seats = int(y_seats * lf)
            j_seats = int(j_seats * lf)
            f_seats = int(f_seats * lf)

            # =========================
            # PRICING
            # =========================
            y_price = distance * 0.35
            j_price = distance * 0.9
            f_price = distance * 1.8

            income = (y_seats * y_price) + (j_seats * j_price) + (f_seats * f_price)

            # =========================
            # COST
            # =========================
            fuel = distance * plane["fuel"] * 6.5
            co2 = distance * 3.2
            profit = income - fuel - co2 - 40000 - 25000

            # =========================
            # TIME
            # =========================
            flight_time = distance / plane["speed"]
            flights_day = max(1, int(24 / flight_time))

            daily_profit = profit * flights_day

            results.append((dest, distance, int(daily_profit)))

        except:
            continue

    if not results:
        await ctx.send("❌ No profitable routes found")
        return

    # =========================
    # SORT TOP 5
    # =========================
    results.sort(key=lambda x: x[2], reverse=True)
    top = results[:5]

    # =========================
    # UI
    # =========================
    text = ""

    for i, r in enumerate(top, start=1):
        dest, dist, profit = r

        text += f"""
**{i}. {airport} → {dest}**
📏 {int(dist):,} km
💰 ${profit:,}/day
"""

    embed = discord.Embed(
        title=f"🔥 Best Routes from {airport} ({plane['name']})",
        description=text,
        color=0x00ffcc
    )

    embed.set_footer(text="JARVIS - A AERO CROWN DYNASTY OFFICIAL BOT")

    await ctx.send(embed=embed)
# =========================
# BEST SHORT ROUTE
#==========================
@bot.command(name="best_short")
async def best_short(ctx, airport, *, plane_name):

    airport = airport.upper()
    plane = get_plane(plane_name)

    if not plane:
        await ctx.send("❌ Plane not found")
        return

    cursor.execute("""
    SELECT t_iata, distance, dem_y, dem_j, dem_f
    FROM routes
    WHERE f_iata = ?
    LIMIT 300
    """, (airport,))

    routes = cursor.fetchall()
    results = []

    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = to_float(dist)

            # SHORT FILTER
            if distance > 3000:
                continue

            if distance > plane["range"]:
                continue

            y, j, f = int(y), int(j), int(f)
            total = y + j + f
            if total == 0:
                continue

            cap = plane["capacity"]

            y_seats = int(cap * (y / total) * 0.85)
            j_seats = int(cap * (j / total) * 0.85)
            f_seats = cap - y_seats - j_seats

            y_price = distance * 0.35
            j_price = distance * 0.9
            f_price = distance * 1.8

            income = (y_seats*y_price)+(j_seats*j_price)+(f_seats*f_price)

            fuel = distance * plane["fuel"] * 6.5
            co2 = distance * 3.2

            profit = income - fuel - co2 - 40000 - 25000

            flights = max(1, int(24 / (distance / plane["speed"])))
            daily_profit = int(profit * flights)

            results.append((dest, distance, daily_profit))

        except:
            continue

    if not results:
        await ctx.send("❌ No short routes found")
        return

    results.sort(key=lambda x: x[2], reverse=True)
    top = results[:5]

    text = ""
    for i, r in enumerate(top, 1):
        text += f"**{i}. {airport} → {r[0]}**\n📏 {int(r[1]):,} km\n💰 ${r[2]:,}/day\n\n"

    embed = discord.Embed(
        title=f"⚡ Best SHORT Routes ({plane['name']})",
        description=text,
        color=0x00ffcc
    )

    embed.set_footer(text="JARVIS - AERO CROWN DYNASTY ™")
    await ctx.send(embed=embed)
#==========================
# BEST LONG ROUTE 
#==========================
@bot.command(name="best_long")
async def best_long(ctx, airport, *, plane_name):

    airport = airport.upper()
    plane = get_plane(plane_name)

    if not plane:
        await ctx.send("❌ Plane not found")
        return

    cursor.execute("""
    SELECT t_iata, distance, dem_y, dem_j, dem_f
    FROM routes
    WHERE f_iata = ?
    LIMIT 300
    """, (airport,))

    routes = cursor.fetchall()
    results = []

    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = to_float(dist)

            # LONG FILTER
            if distance <= 3000:
                continue

            if distance > plane["range"]:
                continue

            y, j, f = int(y), int(j), int(f)
            total = y + j + f
            if total == 0:
                continue

            cap = plane["capacity"]

            y_seats = int(cap * (y / total) * 0.85)
            j_seats = int(cap * (j / total) * 0.85)
            f_seats = cap - y_seats - j_seats

            y_price = distance * 0.35
            j_price = distance * 0.9
            f_price = distance * 1.8

            income = (y_seats*y_price)+(j_seats*j_price)+(f_seats*f_price)

            fuel = distance * plane["fuel"] * 6.5
            co2 = distance * 3.2

            profit = income - fuel - co2 - 40000 - 25000

            flights = max(1, int(24 / (distance / plane["speed"])))
            daily_profit = int(profit * flights)

            results.append((dest, distance, daily_profit))

        except:
            continue

    if not results:
        await ctx.send("❌ No long routes found")
        return

    results.sort(key=lambda x: x[2], reverse=True)
    top = results[:5]

    text = ""
    for i, r in enumerate(top, 1):
        text += f"**{i}. {airport} → {r[0]}**\n📏 {int(r[1]):,} km\n💰 ${r[2]:,}/day\n\n"

    embed = discord.Embed(
        title=f"🌍 Best LONG Routes ({plane['name']})",
        description=text,
        color=0xff9900
    )

    embed.set_footer(text="JARVIS - AERO CROWN DYNASTY ™")
    await ctx.send(embed=embed)
# =========================
# WELCOME + CHAT
# =========================
@bot.event
async def on_member_join(member):

    channel = member.guild.system_channel

    if channel:
        embed = discord.Embed(
            title="👋 Welcome to Aero Crown Dynasty",
            description=f"{member.mention} welcome onboard!\n\nUse `!menu` to explore JARVIS.",
            color=0x00ffcc
        )

        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)

        embed.set_footer(text="JARVIS - A AERO CROWN DYNASTY OFFICIAL BOT")

        await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    msg = message.content.lower().strip()

    # -------- CHECK IF BOT IS MENTIONED --------
    is_mentioned = bot.user in message.mentions

    # -------- CHECK IF DM --------
    is_dm = isinstance(message.channel, discord.DMChannel)

    # -------- ALLOW SMART REPLY ONLY IN THESE CASES --------
    if not (is_mentioned or is_dm):
        await bot.process_commands(message)
        return

    # Remove mention text from message for clean processing
    msg = msg.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

    # -------- INTENTS --------
    greetings = ["hi", "hello", "hey", "jarvis", "yo"]
    thanks = ["thanks", "thank you", "thx"]
    help_words = ["help", "support", "what can you do"]

    # -------- GREETING --------
    if any(word == msg for word in greetings):
        replies = [
            f"Hey {message.author.mention} 👋 I'm online and ready.",
            f"Hello {message.author.mention} ⚡ What do you need?",
            f"Hi {message.author.mention} 👋 Jarvis is active."
        ]
        await message.channel.send(random.choice(replies))

    # -------- THANK YOU --------
    elif any(word in msg for word in thanks):
        replies = [
            f"You're welcome {message.author.mention} 👍",
            f"Anytime {message.author.mention} ⚡",
            f"Glad to help {message.author.mention} 😊"
        ]
        await message.channel.send(random.choice(replies))

    # -------- HELP --------
    elif any(word in msg for word in help_words):
        await message.channel.send(
            f"🧠 {message.author.mention} I can help with AM4 routes, aircraft data, comparisons, leaderboard, and system commands."
        )

    # -------- SMART FALLBACK --------
    else:
        replies = [
            f"{message.author.mention} I’m not fully sure, but I can try helping. Can you rephrase?",
            f"{message.author.mention} 🤔 I need a bit more context.",
            f"{message.author.mention} I don’t have a direct match for that, but I’m listening."
        ]
        await message.channel.send(random.choice(replies))

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    print("🚀 JARVIS is now active and ready")


# =========================
# KEEP ALIVE (ONLY ONCE)
# =========================
keep_alive()


# =========================
# SAFE START (IMPORTANT FIX)
# =========================
if __name__ == "__main__":
    bot.run(TOKEN)
