import discord
import random 
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

# =========================
# REPLACE MATPLOTLIB WITH PILLOW (LIGHTWEIGHT)
# =========================
import io
import sqlite3
import os
import requests
import pytz
import time
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta

# No matplotlib - using PIL only
from PIL import Image, ImageDraw, ImageFont

# =========================
# FLASK - PORT BINDING (Render)
# =========================
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "JARVIS Bot is Alive!"

def run():
    app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

# =========================
# BOT CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE DOWNLOAD
# =========================
DB_FILE = "am4_data.db"
FUELS_DB_FILE = "fuels.db"

def download_db():
    try:
        response = requests.get(
            "https://github.com/Mukul-skyways-dev/JARVIS-BOT/releases/download/Dv1/am4_data.db.updated",
            timeout=30
        )
        response.raise_for_status()
        with open(DB_FILE, "wb") as f:
            f.write(response.content)
        print("✅ Database downloaded")
    except Exception as e:
        print("❌ DB download failed:", e)

def download_fuels_db():
    try:
        response = requests.get(
            "https://github.com/Mukul-skyways-dev/JARVIS-BOT/releases/download/Dv1/fuels.db",
            timeout=30
        )
        response.raise_for_status()
        with open(FUELS_DB_FILE, "wb") as f:
            f.write(response.content)
        print("✅ Fuels DB downloaded")
    except Exception as e:
        print("❌ Fuels DB download failed:", e)

download_db()
download_fuels_db()

# =========================
# DATABASE CONNECTIONS
# =========================
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_fuels_db():
    conn = sqlite3.connect(FUELS_DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# =========================
# UTILITY FUNCTIONS
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
    return f"{h}h {m}m"

# =========================
# DIFFICULTY SYSTEM
# =========================
def get_user_mode(user_id):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT difficulty FROM player_settings WHERE user_id=?", (str(user_id),))
        row = cursor.fetchone()
        if row and row[0]:
            return row[0].lower()
    return "realism"

def set_user_mode(user_id, mode):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO player_settings (user_id, difficulty) VALUES (?, ?)", (str(user_id), mode))
        conn.commit()

# =========================
# FETCH DATA
# =========================
def get_route(frm, to):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT distance, dem_y, dem_j, dem_f, cargo FROM routes
        WHERE (f_iata=? AND t_iata=?) OR (f_iata=? AND t_iata=?)
        LIMIT 1
        """, (frm.upper(), to.upper(), to.upper(), frm.upper()))
        row = cursor.fetchone()
        if not row: return None
        return {
            "distance": to_float(row[0]),
            "y": to_int(row[1]),
            "j": to_int(row[2]),
            "f": to_int(row[3]),
            "cargo": to_int(row[4]) if row[4] else 0
        }

def get_all_planes():
    with get_db() as conn:
        cursor = conn.cursor()
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

def airport_name(iata):
    try:
        iata = iata.upper()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT f_city, f_country, f_name FROM routes WHERE f_iata = ? LIMIT 1", (iata,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT t_city, t_country, t_name FROM routes WHERE t_iata = ? LIMIT 1", (iata,))
                row = cursor.fetchone()
            if row:
                return f"{iata} • {row[2]}\n{row[0]}, {row[1]}"
    except:
        pass
    return iata

# =========================
# CALC ENGINE
# =========================
def calc(route, plane, user_id, mods=None):
    mode = get_user_mode(user_id)
    dist = float(route["distance"])
    speed = float(plane["speed"])
    if mods and "speed" in mods:
        speed *= 1.1
    time = dist / speed if speed else 1
    trips = max(1, int(24 / time))
    y = int(route["y"])
    j = int(route["j"])
    f = int(route["f"])
    total = y + j + f
    cap = int(plane["capacity"])
    
    if mode == "easy":
        lf = 1.0
        y_price = (0.4 * dist) + 170
        j_price = (0.8 * dist) + 560
        f_price = (1.2 * dist) + 1200
        fuel_mult = 4
        co2_mult = 1.8
        acheck = 20000
        repair = 15000
        cargo_mul = 0.5
    else:
        lf = 0.85
        y_price = (0.3 * dist) + 150
        j_price = (0.6 * dist) + 500
        f_price = (0.9 * dist) + 1000
        fuel_mult = 5.5
        co2_mult = 2.5
        acheck = 40000
        repair = 25000
        cargo_mul = 0.35
    
    if total > 0:
        y_ratio = y / total
        j_ratio = j / total
        f_ratio = f / total
        y_c = int(cap * y_ratio * lf)
        j_c = int(cap * j_ratio * lf)
        used = y_c + j_c
        f_c = max(0, cap - used)
    else:
        y_c = j_c = f_c = 0
    
    income_trip = (y_c * y_price) + (j_c * j_price) + (f_c * f_price)
    cargo = float(route.get("cargo", 0))
    cargo_income = cargo * cargo_mul
    income_trip += cargo_income
    
    fuel = dist * float(plane["fuel"]) * fuel_mult
    co2 = dist * co2_mult
    if mods:
        if "fuel" in mods:
            fuel *= 0.9
        if "co2" in mods:
            co2 *= 0.9
    fuel_lb = fuel * 2.2
    co2_q = co2 * 1.1
    
    total_cost = fuel + co2 + acheck + repair
    profit_trip = income_trip - total_cost
    ci = int((profit_trip / income_trip) * 100) if income_trip else 0
    
    income_day = income_trip * trips
    fuel_day = fuel * trips
    co2_day = co2 * trips
    profit_day = profit_trip * trips
    
    return {
        "mode": mode,
        "distance": int(dist),
        "time": round(time, 2),
        "trips": trips,
        "y": y_c,
        "j": j_c,
        "f": f_c,
        "y_price": int(y_price),
        "j_price": int(j_price),
        "f_price": int(f_price),
        "income_trip": int(income_trip),
        "cargo_income": int(cargo_income),
        "fuel": int(fuel),
        "fuel_lb": int(fuel_lb),
        "co2": int(co2),
        "co2_q": int(co2_q),
        "acheck": int(acheck),
        "repair": int(repair),
        "total_cost": int(total_cost),
        "profit_trip": int(profit_trip),
        "ci": ci,
        "income_day": int(income_day),
        "fuel_day": int(fuel_day),
        "co2_day": int(co2_day),
        "profit_day": int(profit_day)
    }

# =========================
# LEADERBOARD SYSTEM
# =========================
with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        points INTEGER DEFAULT 0,
        last_used REAL DEFAULT 0
    )
    """)
    conn.commit()

COOLDOWN = 3

def add_usage(user):
    now = time.time()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_used FROM users WHERE user_id=?", (str(user.id),))
        row = cursor.fetchone()
        if row:
            try:
                last_used = float(row[0])
                if now - last_used < COOLDOWN:
                    return
            except:
                pass
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

@bot.event
async def on_command(ctx):
    add_usage(ctx.author)

# =========================
# GRAPH GENERATION (PIL ONLY - No Matplotlib)
# =========================
def generate_simple_graph(alliance_name, data):
    # Simple text-based graph using PIL
    W, H = 600, 300
    img = Image.new('RGB', (W, H), color=(15, 20, 35))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 10)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Title
    draw.text((20, 10), f"📈 {alliance_name} - Growth", fill=(150, 200, 255), font=font)
    
    if len(data) < 2:
        draw.text((20, 100), "Insufficient data for graph", fill=(200, 200, 200), font=font)
        temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        img.save(temp.name, format='PNG', optimize=True)
        return temp.name
    
    # Plot points
    values = [d[0] for d in data]
    dates = [d[1][-5:] for d in data]
    
    max_val = max(values) if values else 1
    min_val = min(values) if values else 0
    range_val = max_val - min_val if max_val != min_val else 1
    
    x_start, y_start = 50, 250
    x_step = (W - 100) // max(1, len(values) - 1)
    
    points = []
    for i, val in enumerate(values):
        x = x_start + i * x_step
        y = y_start - int(((val - min_val) / range_val) * 180)
        points.append((x, y))
        
        # Draw point
        draw.ellipse((x-4, y-4, x+4, y+4), fill=(0, 255, 136))
        draw.text((x-10, y+10), dates[i], fill=(200, 200, 200), font=font_small)
    
    # Draw line
    if len(points) > 1:
        for i in range(len(points) - 1):
            draw.line([points[i], points[i+1]], fill=(0, 255, 136), width=2)
    
    # Grid lines
    for i in range(0, 5):
        y = y_start - i * 45
        draw.line([(x_start-10, y), (W-50, y)], fill=(50, 50, 70), width=1)
    
    # Value labels
    for i in range(0, 5):
        val = min_val + (range_val / 4) * i
        y = y_start - i * 45
        draw.text((10, y-8), f"${int(val):,}", fill=(150, 150, 170), font=font_small)
    
    temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(temp.name, format='PNG', optimize=True)
    img.close()
    return temp.name

# =========================
# DRAW AIRCRAFT CARD (PIL ONLY)
# =========================
def draw_aircraft_card(plane, result, route, frm, to):
    W, H = 800, 500
    img = Image.new('RGB', (W, H), color=(10, 15, 25))
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("arial.ttf", 20)
        header_font = ImageFont.truetype("arial.ttf", 16)
        text_font = ImageFont.truetype("arial.ttf", 12)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
    
    # Border
    draw.rounded_rectangle((10, 10, W-10, H-10), radius=15, outline=(100, 150, 255, 100), width=2)
    
    # Header
    draw.text((30, 25), f"JARVIS - {plane['name']}", fill=(150, 200, 255), font=title_font)
    draw.text((30, 55), f"{airport_name(frm)} → {airport_name(to)}", fill=(100, 180, 255), font=header_font)
    
    # Stats
    y_pos = 100
    stats = [
        f"✈️ Distance: {int(route['distance']):,} km",
        f"🔄 Trips/Day: {result['trips']}",
        f"⏱️ Flight Time: {format_time(result['time'])}",
        f"💰 Daily Profit: ${result['profit_day']:,}",
        f"⛽ Fuel/Day: ${result['fuel_day']:,}",
        f"🌱 CO2/Day: ${result['co2_day']:,}",
        f"📊 CI: {result['ci']}%"
    ]
    
    for i, stat in enumerate(stats):
        draw.text((30, y_pos + i*30), stat, fill=(200, 210, 220), font=text_font)
    
    # Seat config
    y_seats = max(result["y"], 0)
    j_seats = max(result["j"], 0)
    f_seats = max(result["f"], 0)
    total_seats = max(y_seats + j_seats + f_seats, 1)
    
    bar_x, bar_y = 400, 120
    bar_w, bar_h = 300, 25
    
    draw.rounded_rectangle((bar_x, bar_y, bar_x+bar_w, bar_y+bar_h), radius=8, fill=(40, 45, 60))
    
    f_w = int((f_seats / total_seats) * bar_w)
    j_w = int((j_seats / total_seats) * bar_w)
    y_w = bar_w - f_w - j_w
    
    cx = bar_x
    if f_w > 0:
        draw.rounded_rectangle((cx, bar_y, cx+f_w, bar_y+bar_h), radius=6, fill=(220, 60, 100))
        cx += f_w
    if j_w > 0:
        draw.rounded_rectangle((cx, bar_y, cx+j_w, bar_y+bar_h), radius=6, fill=(255, 180, 40))
        cx += j_w
    if y_w > 0:
        draw.rounded_rectangle((cx, bar_y, cx+y_w, bar_y+bar_h), radius=6, fill=(50, 180, 255))
    
    # Legend
    legend_y = bar_y + 40
    legend_items = [
        (f"F: {f_seats}", (220, 60, 100)),
        (f"J: {j_seats}", (255, 180, 40)),
        (f"Y: {y_seats}", (50, 180, 255))
    ]
    for i, (label, color) in enumerate(legend_items):
        x = 400 + i * 110
        draw.rounded_rectangle((x, legend_y, x+15, legend_y+15), radius=4, fill=color)
        draw.text((x+20, legend_y), label, fill=(200, 210, 220), font=text_font)
    
    # CI Meter
    ci = result['ci']
    meter_y = 220
    draw.text((400, meter_y), f"CI: {ci}%", fill=(150, 200, 255), font=text_font)
    draw.rounded_rectangle((400, meter_y+20, 700, meter_y+35), radius=6, fill=(40, 45, 60))
    meter_w = int(300 * (ci / 100))
    if ci > 85:
        color = (50, 200, 80)
    elif ci > 70:
        color = (255, 180, 40)
    else:
        color = (220, 60, 60)
    draw.rounded_rectangle((400, meter_y+20, 400+meter_w, meter_y+35), radius=4, fill=color)
    
    # Footer
    draw.text((30, H-30), "AERO CROWN DYNASTY • JARVIS", fill=(80, 85, 110), font=text_font)
    
    temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(temp.name, format='PNG', optimize=True, compress_level=6)
    img.close()
    return temp.name

# =========================
# MENU VIEW
# =========================
class EliteMenu(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Flight Ops", style=discord.ButtonStyle.primary, row=0)
    async def route_help(self, interaction, button):
        embed = discord.Embed(title="FLIGHT OPERATIONS", description="`!route DEL BOM A320`", color=0x00c3ff)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Route Intel", style=discord.ButtonStyle.danger, row=0)
    async def best_help(self, interaction, button):
        embed = discord.Embed(title="ROUTE INTELLIGENCE", description="`!best_r DEL A320`", color=0xff4747)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Fleet", style=discord.ButtonStyle.secondary, row=0)
    async def compare_help(self, interaction, button):
        embed = discord.Embed(title="FLEET ANALYSIS", description="`!compare A320 vs B737`", color=0xbfc3c7)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Airport", style=discord.ButtonStyle.success, row=1)
    async def airport_help(self, interaction, button):
        embed = discord.Embed(title="AIRPORT", description="`!airport DEL`", color=0x2ecc71)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Fuel", style=discord.ButtonStyle.primary, row=1)
    async def fuel_help(self, interaction, button):
        embed = discord.Embed(title="FUEL MARKET", description="`!fuel` `!predict`", color=0x00aaff)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="📊 LB", style=discord.ButtonStyle.secondary, row=1)
    async def lb_help(self, interaction, button):
        embed = discord.Embed(title="LEADERBOARD", description="`!leaderboard`", color=0x9b59b6)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================
# COMMANDS
# =========================
@bot.command()
async def menu(ctx):
    embed = discord.Embed(title="JARVIS AVIATION COMMAND", description="Use buttons below", color=0x0f172a)
    await ctx.send(embed=embed, view=EliteMenu())

@bot.command()
async def difficulty(ctx, mode=None):
    if not mode:
        current = get_user_mode(ctx.author.id)
        return await ctx.send(f"⚙ Difficulty: **{current.upper()}**")
    mode = mode.lower()
    if mode not in ["easy", "realism"]:
        return await ctx.send("❌ Use: easy / realism")
    set_user_mode(ctx.author.id, mode)
    await ctx.send(f"✅ Difficulty set to **{mode.upper()}**")

# =========================
# ROUTE COMMAND
# =========================
@bot.command()
async def route(ctx, frm, to, *, plane_name):
    route = get_route(frm, to)
    plane = get_plane(plane_name)
    if not route:
        return await ctx.send("❌ Route not found")
    if not plane:
        return await ctx.send("❌ Plane not found")
    
    result = calc(route, plane, ctx.author.id)
    
    embed = discord.Embed(title=f"{plane['name']} • Route", description=f"{frm.upper()} → {to.upper()}", color=0x2b2d31)
    embed.add_field(name="✈ Flight", value=f"Distance: {int(route['distance']):,} km\nTrips: {result['trips']}/day", inline=True)
    embed.add_field(name="📊 Config", value=f"Y: {result['y']} J: {result['j']} F: {result['f']}", inline=True)
    embed.add_field(name="💰 Profit", value=f"Per Flight: ${result['profit_trip']:,}\nPer Day: ${result['profit_day']:,}", inline=False)
    embed.add_field(name="📈 CI", value=f"{result['ci']}%", inline=True)
    embed.add_field(name="Mode", value=result['mode'].upper(), inline=True)
    
    # Generate image
    img_path = draw_aircraft_card(plane, result, route, frm, to)
    file = discord.File(img_path, filename="route.png")
    embed.set_image(url="attachment://route.png")
    await ctx.send(embed=embed, file=file)

# =========================
# COMPARE COMMAND
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
    
    route = {"distance": 5000, "y": 300, "j": 50, "f": 10, "cargo": 10000}
    r1 = calc(route, p1, ctx.author.id)
    r2 = calc(route, p2, ctx.author.id)
    
    embed = discord.Embed(title=f"{p1['name']} vs {p2['name']}", color=0x2b2d31)
    embed.add_field(name=p1['name'], value=f"Profit/Day: ${r1['profit_day']:,}\nCI: {r1['ci']}%\nTrips: {r1['trips']}", inline=True)
    embed.add_field(name=p2['name'], value=f"Profit/Day: ${r2['profit_day']:,}\nCI: {r2['ci']}%\nTrips: {r2['trips']}", inline=True)
    winner = p1['name'] if r1['profit_day'] > r2['profit_day'] else p2['name']
    embed.set_footer(text=f"🏆 Winner: {winner}")
    await ctx.send(embed=embed)

# =========================
# BEST ROUTE COMMANDS
# =========================
@bot.command()
async def best(ctx, frm, to):
    route = get_route(frm, to)
    if not route:
        return await ctx.send("Route not found")
    
    best_plane = None
    best_calc = None
    best_score = -999999999
    
    for p in get_all_planes():
        try:
            if float(route["distance"]) > float(p["range"]):
                continue
            c = calc(route, p, ctx.author.id)
            score = c["profit_day"] + (float(p["speed"]) * 10) - (float(p["fuel"]) * 100)
            if score > best_score:
                best_score = score
                best_plane = p
                best_calc = c
        except:
            continue
    
    if not best_plane:
        return await ctx.send("No suitable aircraft found")
    
    embed = discord.Embed(title="Best Aircraft", description=f"{frm.upper()} → {to.upper()}", color=0x2b2d31)
    embed.add_field(name="Aircraft", value=best_plane["name"], inline=False)
    embed.add_field(name="Profit/Day", value=money(best_calc["profit_day"]), inline=True)
    embed.add_field(name="Trips", value=best_calc["trips"], inline=True)
    embed.add_field(name="CI", value=f"{best_calc['ci']}%", inline=True)
    embed.set_footer(text="JARVIS • Aircraft Optimization")
    await ctx.send(embed=embed)

@bot.command(name="best_r")
async def best_r(ctx, airport, *, plane_name):
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        return await ctx.send("Plane not found")
    
    mode = get_user_mode(ctx.author.id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 100", (airport,))
        routes = cursor.fetchall()
    
    if not routes:
        return await ctx.send("No routes found")
    
    results = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = float(dist)
            if distance > float(plane["range"]):
                continue
            y, j, f = int(y), int(j), int(f)
            total_demand = y + j + f
            if total_demand == 0:
                continue
            cap = int(plane["capacity"])
            
            if mode == "easy":
                lf = 1.0
                y_price = (0.4 * distance) + 170
                j_price = (0.8 * distance) + 560
                f_price = (1.2 * distance) + 1200
                fuel_mult = 4
                co2_mult = 1.8
                acheck = 20000
                repair = 15000
            else:
                lf = 0.85
                y_price = (0.3 * distance) + 150
                j_price = (0.6 * distance) + 500
                f_price = (0.9 * distance) + 1000
                fuel_mult = 5.5
                co2_mult = 2.5
                acheck = 40000
                repair = 25000
            
            y_ratio = y / total_demand
            j_ratio = j / total_demand
            f_ratio = f / total_demand
            y_seats = int(cap * y_ratio * lf)
            j_seats = int(cap * j_ratio * lf)
            f_seats = cap - y_seats - j_seats
            income = (y_seats * y_price) + (j_seats * j_price) + (f_seats * f_price)
            fuel = distance * float(plane["fuel"]) * fuel_mult
            co2 = distance * co2_mult
            profit = income - fuel - co2 - acheck - repair
            flight_time = distance / float(plane["speed"])
            flights_day = max(1, int(24 / flight_time))
            if flights_day > 18:
                continue
            daily_profit = int(profit * flights_day)
            ci = int((profit / income) * 100) if income else 0
            results.append((dest, int(distance), daily_profit, flights_day, ci))
        except:
            continue
    
    if not results:
        return await ctx.send("No profitable routes found")
    
    results.sort(key=lambda x: x[2], reverse=True)
    top = results[:5]
    
    text = ""
    for i, r in enumerate(top, start=1):
        dest, dist, profit, trips, ci = r
        text += f"**{i}. {airport} → {dest}**\nProfit: ${profit:,}/day | Trips: {trips} | CI: {ci}%\n\n"
    
    embed = discord.Embed(title=f"Best Routes • {plane['name']}", description=text, color=0x2b2d31)
    embed.set_footer(text=f"Mode: {mode.upper()}")
    await ctx.send(embed=embed)

@bot.command(name="best_short")
async def best_short(ctx, airport, *, plane_name):
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        await ctx.send("❌ Plane not found")
        return
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 100", (airport,))
        routes = cursor.fetchall()
    
    results = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = to_float(dist)
            if distance > 3000 or distance > plane["range"]:
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
    embed = discord.Embed(title=f"⚡ Best SHORT Routes ({plane['name']})", description=text, color=0x00ffcc)
    await ctx.send(embed=embed)

@bot.command(name="best_long")
async def best_long(ctx, airport, *, plane_name):
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        await ctx.send("❌ Plane not found")
        return
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 100", (airport,))
        routes = cursor.fetchall()
    
    results = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = to_float(dist)
            if distance <= 3000 or distance > plane["range"]:
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
    embed = discord.Embed(title=f"🌍 Best LONG Routes ({plane['name']})", description=text, color=0xff9900)
    await ctx.send(embed=embed)

# =========================
# AIRPORT COMMAND
# =========================
@bot.command()
async def airport(ctx, code):
    name = airport_name(code)
    embed = discord.Embed(title=f"🛫 Airport", description=name, color=0x2ecc71)
    await ctx.send(embed=embed)

# =========================
# LEADERBOARD
# =========================
@bot.command()
async def leaderboard(ctx):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
        rows = cursor.fetchall()
    
    if not rows:
        return await ctx.send("❌ No data")
    
    text = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, pts) in enumerate(rows, 1):
        medal = medals[i-1] if i <= 3 else f"#{i}"
        text += f"{medal} **{name}** — {pts} uses\n"
    
    embed = discord.Embed(title="📊 Leaderboard", description=text, color=0x1e2b4a)
    await ctx.send(embed=embed)

# =========================
# FUEL COMMANDS
# =========================
def get_am4_market_time():
    real_ts = int(time.time())
    ist_ts = real_ts + (5.5 * 3600)
    market_slot_ts = (int(ist_ts) // 1800) * 1800
    try:
        dt = datetime.fromtimestamp(market_slot_ts, datetime.timezone.utc)
    except:
        dt = datetime.fromtimestamp(market_slot_ts, pytz.UTC)
    return dt.day, dt.strftime("%H:%M"), real_ts

@bot.command(name="fuel")
async def fuel_check(ctx):
    day_num, time_str, unix_ts = get_am4_market_time()
    with get_fuels_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT FuelPrice, CO2Price FROM Day{day_num} WHERE TimeUTC = ?", (time_str,))
        row = cursor.fetchone()
    
    if row:
        fuel = row["FuelPrice"]
        co2 = row["CO2Price"]
        
        embed = discord.Embed(title="⛽ AM4 FUEL", color=0x00aaff)
        embed.add_field(name="Fuel", value=f"${fuel}", inline=True)
        embed.add_field(name="CO2", value=f"${co2}", inline=True)
        
        if fuel < 900:
            status = "🟢 BUY"
        elif fuel <= 1100:
            status = "🟡 WAIT"
        else:
            status = "🔴 AVOID"
        embed.add_field(name="Status", value=status, inline=True)
        embed.set_footer(text=f"<t:{unix_ts}:R>")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ No data")

@bot.command(name="predict")
async def predict_market(ctx):
    try:
        now_utc = datetime.now(datetime.timezone.utc)
    except:
        now_utc = datetime.now(pytz.UTC)
    
    ist_now = now_utc + timedelta(hours=5, minutes=30)
    minute_slot = 30 if ist_now.minute >= 30 else 0
    current_slot = ist_now.replace(minute=minute_slot, second=0, microsecond=0)
    
    rows = []
    for i in range(12):
        future_slot = current_slot + timedelta(minutes=(i * 30))
        target_day = future_slot.day
        db_time = future_slot.strftime("%H:%M")
        
        with get_fuels_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT FuelPrice, CO2Price FROM Day{target_day} WHERE TimeUTC = ?", (db_time,))
            row = cursor.fetchone()
        
        if row:
            fuel = row["FuelPrice"]
            co2 = row["CO2Price"]
            action = "🟢 BUY" if (fuel < 900 and co2 < 100) else "🟡 WAIT" if fuel <= 1100 else "🔴 AVOID"
            rows.append(f"{db_time}: Fuel ${fuel} | CO2 ${co2} {action}")
    
    if not rows:
        return await ctx.send("❌ No data")
    
    embed = discord.Embed(title="🔮 Market Outlook", description="\n".join(rows[:8]), color=0x9b59b6)
    embed.set_footer(text="12-hour forecast")
    await ctx.send(embed=embed)

# =========================
# WELCOME + CHAT
# =========================
@bot.event
async def on_member_join(member):
    channel = member.guild.system_channel
    if channel:
        embed = discord.Embed(title="👋 Welcome!", description=f"{member.mention} use `!menu`", color=0x00ffcc)
        await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# =========================
# ON READY
# =========================
@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")
    print(f"📊 Commands: {len(bot.commands)}")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: TOKEN missing")
    else:
        keep_alive()
        bot.run(TOKEN)