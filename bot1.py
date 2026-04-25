import discord
import random 
from discord.ext import commands
from discord.ui import View, Button

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

DB_URL = "https://github.com/Mukul-skyways-dev/JARVIS-BOT/releases/download/V1/am4_data.db"
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
cursor = conn.cursor()

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
# CALC ENGINE
# =========================
def calc(route, plane, mods=None):

    dist = route["distance"]
    speed = plane["speed"]

    if mods and "speed" in mods:
        speed *= 1.1

    time = dist / speed if speed else 1
    trips = max(1, int(24 / time))

    y, j, f = route["y"], route["j"], route["f"]

    total = y + j + f
    cap = plane["capacity"]

    y_c = int(cap * (y/total)) if total else 0
    j_c = int(cap * (j/total)) if total else 0
    f_c = cap - y_c - j_c

    y_price = dist * 0.9
    j_price = dist * 2.2
    f_price = dist * 4.5

    income_trip = (y_c*y_price)+(j_c*j_price)+(f_c*f_price)
    income_trip += route["cargo"] * 0.4

    fuel = dist * plane["fuel"] * 4
    co2 = dist * 1.8

    if mods:
        if "fuel" in mods: fuel *= 0.9
        if "co2" in mods: co2 *= 0.9

    fuel_lb = fuel * 2.2
    co2_q = co2 * 1.1

    acheck = 40000
    repair = 25000

    profit_trip = income_trip - fuel - co2 - acheck - repair
    ci = int((profit_trip / income_trip)*100) if income_trip else 0

    return {
        "time": time,
        "trips": trips,
        "income_trip": int(income_trip),
        "fuel": int(fuel),
        "fuel_lb": int(fuel_lb),
        "co2": int(co2),
        "co2_q": int(co2_q),
        "acheck": acheck,
        "repair": repair,
        "profit_trip": int(profit_trip),
        "ci": ci,
        "income_day": int(income_trip * trips),
        "fuel_day": int(fuel * trips),
        "co2_day": int(co2 * trips),
        "profit_day": int(profit_trip * trips)
    }

# =========================
# LEADERBOARD
# =========================
@bot.command()
async def leaderboard(ctx):

    cursor.execute("""
    SELECT username, points FROM users
    ORDER BY points DESC LIMIT 10
    """)

    data = cursor.fetchall()

    if not data:
        await ctx.send("❌ No leaderboard data yet")
        return

    medals = ["🥇", "🥈", "🥉"]
    text = ""

    for i, (name, pts) in enumerate(data, 1):
        medal = medals[i-1] if i <= 3 else "🔹"
        text += f"{medal} **{name}** — {pts} pts\n"

    embed = discord.Embed(
        title="🏆 Command Leaderboard",
        description=text,
        color=0xFFD700
    )

    embed.set_footer(text="JARVIS - AERO CROWN DYNASTY ™")

    await ctx.send(embed=embed)

# =========================
# ROUTE COMMAND
# =========================
@bot.command()
async def route(ctx, frm, to, *, plane_name):

    route = get_route(frm, to)
    plane = get_plane(plane_name)

    if not route:
        await ctx.send("❌ Route not found")
        return

    if not plane:
        await ctx.send("❌ Plane not found")
        return

    distance_total = route["distance"]

    # =========================
    # FAST STOPOVER FIX
    # =========================
    stop_airport = None
    leg1 = leg2 = 0

    if distance_total > plane["range"]:

        cursor.execute("""
        SELECT f_iata, t_iata, distance 
        FROM routes 
        WHERE distance < ?
        """, (plane["range"],))

        candidates = cursor.fetchall()

        for row in candidates:
            try:
                f_iata, t_iata, d1 = row
                d1 = to_float(d1)

                d2 = distance_total - d1

                if d1 <= plane["range"] and d2 <= plane["range"]:
                    stop_airport = t_iata
                    leg1 = d1
                    leg2 = d2
                    break

            except:
                continue

        # fallback (always works)
        if not stop_airport:
            stop_airport = "MID"
            leg1 = distance_total / 2
            leg2 = distance_total / 2

    else:
        leg1 = distance_total

    # =========================
    # TIME
    # =========================
    speed = plane["speed"]

    if stop_airport:
        flight_time = (leg1 / speed) + (leg2 / speed)
    else:
        flight_time = leg1 / speed

    flights_per_day = max(1, int(24 / flight_time))

    # =========================
    # DEMAND SPLIT
    # =========================
    total_demand = route["y"] + route["j"] + route["f"]

    if total_demand == 0:
        await ctx.send("❌ No demand")
        return

    y_ratio = route["y"] / total_demand
    j_ratio = route["j"] / total_demand
    f_ratio = route["f"] / total_demand

    cap = plane["capacity"]

    y_seats = int(cap * y_ratio)
    j_seats = int(cap * j_ratio)
    f_seats = cap - y_seats - j_seats

    # =========================
    # LOAD FACTOR (REALISM)
    # =========================
    load_factor = 0.85

    y_seats = int(y_seats * load_factor)
    j_seats = int(j_seats * load_factor)
    f_seats = int(f_seats * load_factor)

    # =========================
    # REALISTIC PRICING
    # =========================
    distance = distance_total

    y_price = distance * 0.35
    j_price = distance * 0.9
    f_price = distance * 1.8

    income = (y_seats * y_price) + (j_seats * j_price) + (f_seats * f_price)
    income += route.get("cargo", 0) * 0.4

    # =========================
    # COST (REALISTIC)
    # =========================
    total_distance = leg1 + leg2 if stop_airport else leg1

    fuel = total_distance * plane["fuel"] * 6.5
    co2 = total_distance * 3.2

    acheck = 40000
    repair = 25000

    profit = income - fuel - co2 - acheck - repair
    ci = int((profit / income) * 100) if income else 0

    # =========================
    # TIME FORMAT
    # =========================
    def format_time(h):
        H = int(h)
        M = int((h - H) * 60)
        S = int((((h - H) * 60) - M) * 60)
        return f"{H:02}:{M:02}:{S:02} ({round(h,3)} hr)"

    # =========================
    # UI
    # =========================
    route_text = f"{frm.upper()} → {to.upper()}"
    if stop_airport:
        route_text = f"{frm.upper()} → {stop_airport} → {to.upper()}"

    embed = discord.Embed(
        title=f"✈ {route_text} | {plane['name']}",
        color=0x00ffcc
    )

    embed.add_field(
        name="🕒 Flight Info",
        value=f"""
Distance: {int(distance_total):,} km
Time: {format_time(flight_time)}
Trips/Day: {flights_per_day}
""",
        inline=False
    )

    embed.add_field(
        name="📊 Demand",
        value=f"Y: {route['y']} | J: {route['j']} | F: {route['f']}",
        inline=False
    )

    embed.add_field(
        name="⚙ Configuration",
        value=f"Y: {y_seats} | J: {j_seats} | F: {f_seats}",
        inline=False
    )

    embed.add_field(
        name="💺 Ticket Prices",
        value=f"""
Y: ${int(y_price):,}
J: ${int(j_price):,}
F: ${int(f_price):,}
""",
        inline=False
    )

    embed.add_field(
        name="💰 Per Flight",
        value=f"""
Income: ${int(income):,}
Fuel: ${int(fuel):,}
CO2: ${int(co2):,}
Acheck: ${acheck:,}
Repair: ${repair:,}

Profit: ${int(profit):,}
CI: {ci}
""",
        inline=False
    )

    embed.add_field(
        name="📅 Per Day",
        value=f"""
Income: ${int(income * flights_per_day):,}
Profit: ${int(profit * flights_per_day):,}
Flights: {flights_per_day}
""",
        inline=False
    )

    embed.set_footer(text="JARVIS - A AERO CROWN DYNASTY OFFICIAL BOT")

    await ctx.send(embed=embed)
# =========================
# COMPARE COMMAND
# =========================
@bot.command()
async def compare(ctx, *, planes_input):

    try:
        p1_name, p2_name = planes_input.lower().split(" vs ")
    except:
        await ctx.send("❌ Use: !compare A320 vs B737")
        return

    p1 = get_plane(p1_name)
    p2 = get_plane(p2_name)

    if not p1 or not p2:
        await ctx.send("❌ Plane not found")
        return

    # ===== EXTRA DATA CLEAN =====
    def safe_cost(x):
        try:
            return int(str(x).replace("$","").replace(",","").strip())
        except:
            return 0

    p1["cost"] = safe_cost(p1.get("cost",0))
    p2["cost"] = safe_cost(p2.get("cost",0))

    # ===== VISUAL COMPARISON =====
    def better(a,b,reverse=False):
        if reverse:
            return "🟢 __"+str(a)+"__" if a < b else "🔴 __"+str(a)+"__"
        return "🟢 __"+str(a)+"__" if a > b else "🔴 __"+str(a)+"__"

    def vs(a,b): return f"{a}   ×   {b}"

    # ===== DERIVED VALUES =====
    runway1 = int(p1["range"] * 2.5)
    runway2 = int(p2["range"] * 2.5)

    maint1 = int(p1["speed"] / 100)
    maint2 = int(p2["speed"] / 100)

    # Income estimation
    inc1 = p1["capacity"] * 1200
    inc2 = p2["capacity"] * 1200

    inc1_r = int(inc1 * 1.4)
    inc2_r = int(inc2 * 1.4)

    # ===== EMBED =====
    embed = discord.Embed(
        title=f"⚔ {p1['name']}  VS  {p2['name']}",
        color=0xffcc00
    )

    # COST
    embed.add_field(name="💰 Cost",
        value=vs(
            better(money(p1["cost"]), money(p2["cost"]), True),
            better(money(p2["cost"]), money(p1["cost"]), True)
        ),
        inline=False)

    # CAPACITY
    embed.add_field(name="👥 Capacity",
        value=vs(
            better(p1["capacity"], p2["capacity"]),
            better(p2["capacity"], p1["capacity"])
        ),
        inline=False)

    # RANGE
    embed.add_field(name="📏 Range",
        value=vs(
            better(int(p1["range"]), int(p2["range"])),
            better(int(p2["range"]), int(p1["range"]))
        ),
        inline=False)

    # SPEED
    embed.add_field(name="✈ Cruise Speed",
        value=vs(
            better(int(p1["speed"]), int(p2["speed"])),
            better(int(p2["speed"]), int(p1["speed"]))
        ),
        inline=False)

    # FUEL
    embed.add_field(name="⛽ Fuel Consumption",
        value=vs(
            better(p1["fuel"], p2["fuel"], True),
            better(p2["fuel"], p1["fuel"], True)
        ),
        inline=False)

    # CO2
    embed.add_field(name="🌍 CO2 Emission",
        value=vs(
            better(1.8, 1.8, True),
            better(1.8, 1.8, True)
        ),
        inline=False)

    # RUNWAY
    embed.add_field(name="🛬 Runway Required",
        value=vs(
            better(runway1, runway2, True),
            better(runway2, runway1, True)
        ),
        inline=False)

    # MAINTENANCE
    embed.add_field(name="🛠 Maintenance",
        value=vs(
            better(maint1, maint2, True),
            better(maint2, maint1, True)
        ),
        inline=False)

    # A-CHECK
    embed.add_field(name="🔧 A-Check",
        value=f"""
Easy: {vs(better(40000,40000,True), better(40000,40000,True))}
Realism: {vs(better(60000,60000,True), better(60000,60000,True))}
""",
        inline=False)

    # INCOME FLIGHT
    embed.add_field(name="💵 Income / Flight",
        value=f"""
Easy: {vs(better(inc1,inc2), better(inc2,inc1))}
Realism: {vs(better(inc1_r,inc2_r), better(inc2_r,inc1_r))}
""",
        inline=False)

    # INCOME DAY
    embed.add_field(name="📅 Income / Day",
        value=f"""
Easy: {vs(better(inc1*5,inc2*5), better(inc2*5,inc1*5))}
Realism: {vs(better(inc1_r*5,inc2_r*5), better(inc2_r*5,inc1_r*5))}
""",
        inline=False)

    # WINNER LOGIC
    score1 = (
        p1["capacity"]*2 +
        p1["range"] +
        p1["speed"]*2 -
        p1["fuel"]*100
    )

    score2 = (
        p2["capacity"]*2 +
        p2["range"] +
        p2["speed"]*2 -
        p2["fuel"]*100
    )

    winner = p1["name"] if score1 > score2 else p2["name"]

    embed.set_footer(text=f"🏆 Overall Winner: {winner} | JARVIS - A AERO CROWN DYNASTY OFFICIAL BOT")

    await ctx.send(embed=embed)
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
