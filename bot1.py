import discord
import random 
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

# =========================
# MATPLOTLIB OPTIMIZE (Memory Fix)
# =========================
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['figure.dpi'] = 80
plt.rcParams['savefig.dpi'] = 80
plt.rcParams['figure.figsize'] = (6, 3)
import numpy as np
import io

import sqlite3
import os
import requests
from openai import OpenAI
import pytz

from export_view import ExportView

# =========================
# FLASK + PORT BINDING (Render Web Service Fix)
# =========================
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "JARVIS Bot is Alive! 🚀"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

from datetime import datetime, timedelta
import asyncio
import time
from PIL import Image, ImageDraw
import tempfile
from contextlib import contextmanager

# =========================
# BOT CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

groq = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

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
    print("⬇ Downloading database from GitHub Release...")
    try:
        response = requests.get(DB_URL, timeout=30)
        response.raise_for_status()
        with open(DB_FILE, "wb") as f:
            f.write(response.content)
        print("✅ Database downloaded successfully")
    except Exception as e:
        print("❌ DB download failed:", e)

download_db()

# =========================================================
# FUELS DATABASE DOWNLOAD
# =========================================================

FUELS_DB_URL = "https://github.com/Mukul-skyways-dev/JARVIS-BOT/releases/download/Dv1/fuels.db"
FUELS_DB_FILE = "fuels.db"

def download_fuels_db():
    print("🔄 Checking fuels database...")
    try:
        print("⬇ Downloading fuels database from GitHub Release...")
        response = requests.get(FUELS_DB_URL, timeout=30)
        response.raise_for_status()
        with open(FUELS_DB_FILE, "wb") as f:
            f.write(response.content)
        print("✅ Fuels database downloaded successfully")
    except Exception as e:
        print("❌ Fuels DB download failed:", e)

download_fuels_db()

# =========================================================
# DATABASE CONNECTIONS WITH CONTEXT MANAGER (Memory Fix)
# =========================================================

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_fuels_db():
    conn = sqlite3.connect(FUELS_DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

@contextmanager
def get_dyn_db():
    conn = sqlite3.connect("new_am4.db", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# =========================================================
# DIFFICULTY SYSTEM
# =========================================================
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

# =========================================================
# MENU VIEW
# =========================================================
class EliteMenu(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Flight Ops", style=discord.ButtonStyle.primary, row=0)
    async def route_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="FLIGHT OPERATIONS",
            description="""
━━━━━━━━━━━━━━━━━━

`!route DEL BOM A320`

MODULES
• Flight Time Analysis
• Demand System (Y/J/F)
• Smart Seat Configuration
• Dynamic Ticket Pricing
• Profit Estimation
• Stopover Support
• Maintenance Calculation

━━━━━━━━━━━━━━━━━━
STATUS : OPERATIONAL
""",
            color=0x00c3ff
        )
        embed.set_footer(text="JARVIS • Flight Operations Engine")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Route Intel", style=discord.ButtonStyle.danger, row=0)
    async def best_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="ROUTE INTELLIGENCE",
            description="""
━━━━━━━━━━━━━━━━━━

`!best_r DEL A320`
`!best_short DEL A320`
`!best_long DEL A320`

FEATURES
• Best Profit Routes
• Short Haul Optimization
• Long Haul Optimization
• Demand Scanning
• Route Ranking Engine

━━━━━━━━━━━━━━━━━━
STATUS : ACTIVE
""",
            color=0xff4747
        )
        embed.set_footer(text="JARVIS • Route Intelligence Core")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Fleet Analysis", style=discord.ButtonStyle.secondary, row=0)
    async def compare_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="FLEET ANALYSIS",
            description="""
━━━━━━━━━━━━━━━━━━

`!compare A320 vs B737`

ANALYSIS
• Profit Comparison
• Capacity Breakdown
• Fuel Efficiency
• Speed & Range
• Income Statistics
• Cost Evaluation

━━━━━━━━━━━━━━━━━━
STATUS : STABLE
""",
            color=0xbfc3c7
        )
        embed.set_footer(text="JARVIS • Fleet Analysis System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Airport Systems", style=discord.ButtonStyle.success, row=1)
    async def airport_help(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="AIRPORT SYSTEMS",
            description="""
━━━━━━━━━━━━━━━━━━

`!airport DEL`

DATABASE
• Runway Information
• Market Analysis
• Hub Cost
• Traffic Statistics
• Airport Coordinates
• Operational Data

━━━━━━━━━━━━━━━━━━
DATABASE : CONNECTED
""",
            color=0x2ecc71
        )
        embed.set_footer(text="JARVIS • Airport Database System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Utilities", style=discord.ButtonStyle.secondary, row=1)
    async def general(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="SYSTEM UTILITIES",
            description="""
━━━━━━━━━━━━━━━━━━

`!menu`
`!ping`

SYSTEM
• Control Panel
• Status Monitoring
• Bot Response
• Utility Commands

━━━━━━━━━━━━━━━━━━
SYSTEM : ONLINE
""",
            color=0x9b59b6
        )
        embed.set_footer(text="JARVIS • Utility Interface")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =========================
# MENU COMMAND
# =========================
@bot.command()
async def menu(ctx):
    embed = discord.Embed(
        title="JARVIS AVIATION COMMAND",
        description="""
━━━━━━━━━━━━━━━━━━

FLIGHT OPERATIONS
• route
• pricing engine
• profit calculation
• flight analysis

━━━━━━━━━━━━━━━━━━

ROUTE INTELLIGENCE
• best_r
• best_short
• best_long
• market optimization

━━━━━━━━━━━━━━━━━━

FLEET ANALYSIS
• compare
• aircraft statistics
• performance evaluation

━━━━━━━━━━━━━━━━━━

AIRPORT SYSTEMS
• airport search
• market data
• runway analysis
• traffic information

━━━━━━━━━━━━━━━━━━

SYSTEM STATUS

Route Engine        ONLINE
Airport Database    ACTIVE
Flight Calculator   STABLE

━━━━━━━━━━━━━━━━━━

Aircraft Supported : 490+
Routes Indexed     : 300K+
Database Version   : V3 CORE

Use the control buttons below.
""",
        color=0x0f172a
    )
    embed.set_footer(text="JARVIS • A AERO CROWN DYNASTY OFFICIAL BOT")
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
    with get_db() as conn:
        cursor = conn.cursor()
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

# =========================
# CALC ENGINE V3
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

# ========================
# Leaderboard 
# ========================
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

# =========================
# FIX: add_usage function (TypeError fix)
# =========================
def add_usage(user):
    now = time.time()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_used FROM users WHERE user_id=?", (str(user.id),))
        row = cursor.fetchone()
        
        # FIX: Check and convert properly
        if row:
            try:
                last_used = float(row[0])  # Convert to float
                if now - last_used < COOLDOWN:
                    return
            except (ValueError, TypeError):
                pass  # If conversion fails, proceed with update
        
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
# LEADERBOARD VIEW
# =========================
class LeaderboardView(View):
    def __init__(self):
        super().__init__(timeout=180)
        self.page = 0
        self.data = self.fetch()

    def fetch(self):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, points FROM users ORDER BY points DESC")
            return cursor.fetchall()

    def page_data(self):
        start = self.page * 10
        return self.data[start:start + 10]

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
        embed.set_footer(text=f"Page {self.page + 1} • Live Tracking • AERO CROWN DYNASTY")
        return embed

    def build_graph(self):
        top = self.data[:10]
        names = [x[0][:8] for x in top]
        values = [x[1] for x in top]
        plt.figure(figsize=(6, 3))
        plt.style.use("dark_background")
        plt.gca().set_facecolor("#0b1a40")
        plt.gcf().patch.set_facecolor("#0b1a40")
        bars = plt.bar(names, values, color="#00e5ff")
        for bar in bars:
            bar.set_alpha(0.9)
        plt.xticks(rotation=40)
        plt.title("LIVE BOT USAGE RANKING", color="white")
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=80)
        buf.seek(0)
        plt.close()
        return buf

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
        embed = discord.Embed(title="📊 Live Usage Graph", color=0x1e2b4a)
        embed.set_image(url="attachment://leaderboard.png")
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    async def update(self, interaction):
        self.data = self.fetch()
        await interaction.response.edit_message(embed=self.build_embed(), attachments=[], view=self)

# =========================
# AUTO TRACK
# =========================
@bot.event
async def on_command(ctx):
    add_usage(ctx.author)

@bot.command()
async def leaderboard(ctx):
    view = LeaderboardView()
    if not view.data:
        return await ctx.send("❌ No usage data yet")
    await ctx.send(embed=view.build_embed(), view=view)

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

# =========================================================
# AIRPORT HELPER
# =========================================================
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
                city = row[0]
                country = row[1]
                airport = row[2]
                return f"{iata} • {airport}\n{city}, {country}"
    except Exception as e:
        print("airport_name error:", e)
    return iata

# =========================================================
# AIRCRAFT VISUAL SYSTEM (Memory Optimized)
# =========================================================
def draw_aircraft_card(plane, result, route, frm, to):
    W = 1200
    H = 700
    
    img = Image.new("RGB", (W, H), (10, 15, 25))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle((0, 0, W, H), fill=(10, 15, 25))
    draw.rounded_rectangle((50, 50, W - 50, H - 50), radius=20, outline=(100, 150, 255, 100), width=1)
    
    try:
        title_font = ImageFont.truetype("arial.ttf", 28)
        header_font = ImageFont.truetype("arial.ttf", 22)
        text_font = ImageFont.truetype("arial.ttf", 18)
        small_font = ImageFont.truetype("arial.ttf", 14)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    from_airport = airport_name(frm)
    to_airport = airport_name(to)
    draw.text((80, 70), "JARVIS AVIATION VISUAL SYSTEM", fill=(150, 200, 255), font=title_font)
    draw.text((80, 120), from_airport, fill=(100, 180, 255), font=header_font)
    draw.text((80, 155), "▼", fill=(255, 255, 255), font=text_font)
    draw.text((80, 185), to_airport, fill=(100, 180, 255), font=header_font)
    
    capacity = max(int(float(plane["capacity"])), 100)
    fuselage_length = min(max(450, 450 + int(capacity * 0.1)), 650)
    fuselage_height = min(max(60, 60 + int(capacity * 0.005)), 85)
    fuselage_x = 200
    fuselage_y = 270
    
    draw.rounded_rectangle(
        (fuselage_x, fuselage_y, fuselage_x + fuselage_length, fuselage_y + fuselage_height),
        radius=fuselage_height // 2,
        fill=(220, 225, 240)
    )
    
    cockpit_x = fuselage_x + fuselage_length - 55
    cockpit_y = fuselage_y + (fuselage_height // 2) - 12
    draw.rounded_rectangle(
        (cockpit_x, cockpit_y, cockpit_x + 40, cockpit_y + 24),
        radius=8,
        fill=(80, 150, 230)
    )
    
    window_count = min(max(int(capacity / 15), 12), 30)
    window_spacing = (fuselage_length - 160) // window_count
    for i in range(window_count):
        window_x = fuselage_x + 60 + (i * window_spacing)
        draw.rounded_rectangle(
            (window_x, fuselage_y + 18, window_x + 12, fuselage_y + 32),
            radius=3,
            fill=(70, 150, 220)
        )
    
    draw.text(
        (fuselage_x + 100, fuselage_y + fuselage_height - 25),
        plane["name"],
        fill=(30, 35, 45),
        font=header_font
    )
    
    y_seats = max(result["y"], 0)
    j_seats = max(result["j"], 0)
    f_seats = max(result["f"], 0)
    total_seats = max(y_seats + j_seats + f_seats, 1)
    
    bar_x = fuselage_x + 60
    bar_y = fuselage_y - 30
    bar_w = fuselage_length - 120
    bar_h = 15
    
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=6, fill=(40, 45, 60))
    
    f_w = int((f_seats / total_seats) * bar_w)
    j_w = int((j_seats / total_seats) * bar_w)
    y_w = bar_w - f_w - j_w
    
    current_x = bar_x
    if f_w > 0:
        draw.rounded_rectangle((current_x, bar_y, current_x + f_w, bar_y + bar_h), radius=4, fill=(220, 60, 100))
        current_x += f_w
    if j_w > 0:
        draw.rounded_rectangle((current_x, bar_y, current_x + j_w, bar_y + bar_h), radius=4, fill=(255, 180, 40))
        current_x += j_w
    if y_w > 0:
        draw.rounded_rectangle((current_x, bar_y, current_x + y_w, bar_y + bar_h), radius=4, fill=(50, 180, 255))
    
    sx = 80
    sy = 400
    draw.text((sx, sy), "FLIGHT DATA", fill=(150, 200, 255), font=text_font)
    stats = [
        f"✈️ Distance      : {int(route['distance']):,} km",
        f"🔄 Trips/Day     : {result['trips']}",
        f"⏱️ Flight Time   : {format_time(result['time'])}",
        f"💰 Daily Profit  : ${result['profit_day']:,}",
        f"⛽ Fuel Cost     : ${result['fuel_day']:,}",
        f"🌱 CO2 Cost      : ${result['co2_day']:,}"
    ]
    for i, stat in enumerate(stats):
        draw.text((sx + 10, sy + 30 + i * 28), stat, fill=(200, 210, 220), font=small_font)
    
    rx = 700
    ry = 400
    draw.text((rx, ry), "CABIN CONFIGURATION", fill=(150, 200, 255), font=text_font)
    legend = [
        ("First Class", (220, 60, 100), f"{f_seats} seats"),
        ("Business", (255, 180, 40), f"{j_seats} seats"),
        ("Economy", (50, 180, 255), f"{y_seats} seats")
    ]
    for i, (name, color, count) in enumerate(legend):
        yy = ry + 35 + i * 40
        draw.rounded_rectangle((rx + 10, yy, rx + 40, yy + 25), radius=4, fill=color)
        draw.text((rx + 55, yy + 3), name, fill=(200, 210, 220), font=small_font)
        draw.text((rx + 55, yy + 20), count, fill=(150, 160, 170), font=small_font)
    
    ci = result['ci']
    meter_y = ry + 170
    draw.text((rx, meter_y), "PERFORMANCE METER", fill=(150, 200, 255), font=text_font)
    draw.rounded_rectangle((rx + 10, meter_y + 30, rx + 220, meter_y + 48), radius=6, fill=(40, 45, 60))
    meter_w = int(210 * (ci / 100))
    if ci > 85:
        meter_color = (50, 200, 80)
    elif ci > 70:
        meter_color = (255, 180, 40)
    else:
        meter_color = (220, 60, 60)
    draw.rounded_rectangle((rx + 10, meter_y + 30, rx + 10 + meter_w, meter_y + 48), radius=4, fill=meter_color)
    draw.text((rx + 80, meter_y + 55), f"{ci}%", fill=(255, 255, 255), font=text_font)
    
    footer_y = H - 40
    draw.text((W // 2 - 120, footer_y), "AERO CROWN DYNASTY • JARVIS INTELLIGENCE", fill=(80, 85, 110), font=small_font)
    
    temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(temp.name, format='PNG', optimize=True, compress_level=6)
    img.close()
    return temp.name

def format_time(minutes):
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"

# =========================================================
# ROUTE COMMAND
# =========================================================
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
    stop_airport = None
    
    if distance_total > plane_range:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT t_iata FROM routes
            WHERE f_iata = ? AND CAST(distance AS REAL) < ?
            ORDER BY CAST(distance AS REAL) DESC LIMIT 1
            """, (frm.upper(), plane_range))
            row = cursor.fetchone()
            if row:
                stop_airport = row[0]
    
    result = calc(route, plane, ctx.author.id)
    mode = result["mode"]
    
    from_txt = airport_name(frm)
    to_txt = airport_name(to)
    if stop_airport:
        stop_txt = airport_name(stop_airport)
        route_display = f"{from_txt}\n→ {stop_txt}\n→ {to_txt}"
    else:
        route_display = f"{from_txt}\n→ {to_txt}"
    
    embed = discord.Embed(title=f"{plane['name']} • Route Analysis V3.0.1", description=f"```{route_display}```", color=0x2b2d31)
    embed.add_field(name="✈ Flight Info", value=f"**Distance:** {int(distance_total):,} km\n**Trips:** {result['trips']}/day\n**Mode:** {mode.upper()}", inline=False)
    embed.add_field(name="📊 Demand", value=f"**Y:** {route['y']}\n**J:** {route['j']}\n**F:** {route['f']}", inline=True)
    embed.add_field(name="⚙ Configuration", value=f"**Y:** {result['y']}\n**J:** {result['j']}\n**F:** {result['f']}", inline=True)
    embed.add_field(name="🎟 Ticket Pricing", value=f"**Y:** ${result['y_price']:,}\n**J:** ${result['j_price']:,}\n**F:** ${result['f_price']:,}", inline=True)
    embed.add_field(name="💰 Per Flight", value=f"**Income:** ${result['income_trip']:,}\n**Fuel:** ${result['fuel']:,}\n**CO2:** ${result['co2']:,}\n**Maint:** ${result['acheck'] + result['repair']:,}\n\n**Profit:** ${result['profit_trip']:,}\n**CI:** {result['ci']}%", inline=False)
    embed.add_field(name="📅 Per Day", value=f"**Income:** ${result['income_day']:,}\n**Fuel:** ${result['fuel_day']:,}\n**CO2:** ${result['co2_day']:,}\n**Maint:** ${(result['acheck'] + result['repair']) * result['trips']:,}\n\n**Profit:** ${result['profit_day']:,}\n**Flights:** {result['trips']}", inline=False)
    embed.set_footer(text="JARVIS • AERO CROWN DYNASTY OFFICIAL BOT")
    
    report_data = {
        "Route": f"{frm.upper()} -> {to.upper()}",
        "Aircraft": plane["name"],
        "Distance": f"{int(distance_total):,} km",
        "Mode": mode.upper(),
        "Trips/Day": result["trips"],
        "Economy Demand": route["y"],
        "Business Demand": route["j"],
        "First Demand": route["f"],
        "Economy Config": result["y"],
        "Business Config": result["j"],
        "First Config": result["f"],
        "Economy Ticket": result["y_price"],
        "Business Ticket": result["j_price"],
        "First Ticket": result["f_price"],
        "Income/Flight": result["income_trip"],
        "Fuel/Flight": result["fuel"],
        "CO2/Flight": result["co2"],
        "Profit/Flight": result["profit_trip"],
        "Profit/Day": result["profit_day"],
        "CI": f"{result['ci']}%"
    }
    
    img_path = draw_aircraft_card(plane, result, route, frm, to)
    file = discord.File(img_path, filename="route.png")
    embed.set_image(url="attachment://route.png")
    await ctx.send(embed=embed, file=file, view=ExportView(report_data))

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

    def fmt(self, a, b, reverse=False):
        try:
            a = float(a)
            b = float(b)
        except:
            return f"{a}"
        if reverse:
            return f"**{a:,.0f}**" if a < b else f"{a:,.0f}"
        return f"**{a:,.0f}**" if a > b else f"{a:,.0f}"

    def build_embed(self):
        embed = discord.Embed(title=f"{self.p1['name']}  VS  {self.p2['name']}", description="```Advanced Aircraft Analytics Engine```", color=0x2b2d31)
        embed.add_field(name="✦ Specifications", value=f"**Capacity** → {self.fmt(self.p1['capacity'], self.p2['capacity'])} │ {self.fmt(self.p2['capacity'], self.p1['capacity'])}\n**Range** → {self.fmt(self.p1['range'], self.p2['range'])} │ {self.fmt(self.p2['range'], self.p1['range'])}\n**Speed** → {self.fmt(self.p1['speed'], self.p2['speed'])} │ {self.fmt(self.p2['speed'], self.p1['speed'])}\n**Fuel** → {self.fmt(self.p1['fuel'], self.p2['fuel'], True)} │ {self.fmt(self.p2['fuel'], self.p1['fuel'], True)}", inline=False)
        embed.add_field(name="✦ Operations", value=f"**Trips/Day** → {self.fmt(self.r1['trips'], self.r2['trips'])} │ {self.fmt(self.r2['trips'], self.r1['trips'])}\n**Flight Time** → {self.fmt(self.r1['time'], self.r2['time'], True)} │ {self.fmt(self.r2['time'], self.r1['time'], True)}\n**CI Score** → {self.fmt(self.r1['ci'], self.r2['ci'])}% │ {self.fmt(self.r2['ci'], self.r1['ci'])}%", inline=False)
        embed.add_field(name="✦ Revenue", value=f"**Income/Flight** → {self.fmt(self.r1['income_trip'], self.r2['income_trip'])} │ {self.fmt(self.r2['income_trip'], self.r1['income_trip'])}\n**Profit/Flight** → {self.fmt(self.r1['profit_trip'], self.r2['profit_trip'])} │ {self.fmt(self.r2['profit_trip'], self.r1['profit_trip'])}\n**Income/Day** → {self.fmt(self.r1['income_day'], self.r2['income_day'])} │ {self.fmt(self.r2['income_day'], self.r1['income_day'])}\n**Profit/Day** → {self.fmt(self.r1['profit_day'], self.r2['profit_day'])} │ {self.fmt(self.r2['profit_day'], self.r1['profit_day'])}", inline=False)
        embed.add_field(name="✦ Cost Analysis", value=f"**Fuel/Flight** → {self.fmt(self.r1['fuel'], self.r2['fuel'], True)} │ {self.fmt(self.r2['fuel'], self.r1['fuel'], True)}\n**CO2/Flight** → {self.fmt(self.r1['co2'], self.r2['co2'], True)} │ {self.fmt(self.r2['co2'], self.r1['co2'], True)}\n**Maint** → {self.fmt(self.r1['acheck'] + self.r1['repair'], self.r2['acheck'] + self.r2['repair'], True)} │ {self.fmt(self.r2['acheck'] + self.r2['repair'], self.r1['acheck'] + self.r1['repair'], True)}", inline=False)
        embed.add_field(name="✦ Efficiency", value=f"**Fuel(lb)** → {self.fmt(self.r1['fuel_lb'], self.r2['fuel_lb'], True)} │ {self.fmt(self.r2['fuel_lb'], self.r1['fuel_lb'], True)}\n**CO2(q)** → {self.fmt(self.r1['co2_q'], self.r2['co2_q'], True)} │ {self.fmt(self.r2['co2_q'], self.r1['co2_q'], True)}", inline=False)
        winner = self.p1["name"] if self.r1["profit_day"] > self.r2["profit_day"] else self.p2["name"]
        embed.set_footer(text=f"Page 1/3 • Winner: {winner}")
        return embed

    def make_graph(self):
        labels = ["Income", "Profit", "Fuel", "CO2", "Trips"]
        p1_vals = [self.r1["income_day"], self.r1["profit_day"], self.r1["fuel_day"], self.r1["co2_day"], self.r1["trips"] * 100000]
        p2_vals = [self.r2["income_day"], self.r2["profit_day"], self.r2["fuel_day"], self.r2["co2_day"], self.r2["trips"] * 100000]
        max_val = max(max(p1_vals), max(p2_vals))
        if max_val == 0: max_val = 1
        p1n = [v / max_val for v in p1_vals]
        p2n = [v / max_val for v in p2_vals]
        x = np.arange(len(labels))
        
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor("#1f1f1f")
        ax.set_facecolor("#2b2d31")
        
        ax.plot(x, p1n, marker='o', linewidth=2.5, label=self.p1["name"])
        ax.plot(x, p2n, marker='s', linewidth=2.5, linestyle='--', label=self.p2["name"])
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.grid(alpha=0.18, linestyle=':')
        ax.legend()
        for spine in ax.spines.values():
            spine.set_color("#555555")
        ax.tick_params(colors="white")
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=80)
        buf.seek(0)
        plt.close()
        return buf

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
        
        fig = plt.figure(figsize=(5, 5))
        ax = plt.subplot(111, polar=True)
        fig.patch.set_facecolor("#1f1f1f")
        ax.set_facecolor("#2b2d31")
        ax.plot(angles, v1, linewidth=2.5, label=self.p1["name"])
        ax.plot(angles, v2, linewidth=2.5, linestyle='--', label=self.p2["name"])
        ax.fill(angles, v1, alpha=0.12)
        ax.fill(angles, v2, alpha=0.12)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, color="white")
        ax.grid(alpha=0.2)
        plt.legend()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=80)
        buf.seek(0)
        plt.close()
        return buf

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction, button):
        self.page = (self.page - 1) % 3
        await self.update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction, button):
        self.page = (self.page + 1) % 3
        await self.update(interaction)

    async def update(self, interaction):
        if self.page == 0:
            await interaction.response.edit_message(embed=self.build_embed(), attachments=[], view=self)
        elif self.page == 1:
            buf = self.make_graph()
            file = discord.File(buf, "graph.png")
            embed = discord.Embed(title="📊 Performance Graph", color=0x2b2d31)
            embed.set_image(url="attachment://graph.png")
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        elif self.page == 2:
            buf = self.make_radar()
            file = discord.File(buf, "radar.png")
            embed = discord.Embed(title="🧭 Radar Analysis", color=0x2b2d31)
            embed.set_image(url="attachment://radar.png")
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

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
    view = CompareView(p1, p2, r1, r2)
    report_data = {
        "Plane 1": p1["name"],
        "Plane 2": p2["name"],
        "P1 Profit/Day": r1["profit_day"],
        "P2 Profit/Day": r2["profit_day"],
        "P1 Income/Day": r1["income_day"],
        "P2 Income/Day": r2["income_day"],
        "P1 Fuel/Day": r1["fuel_day"],
        "P2 Fuel/Day": r2["fuel_day"],
        "P1 Trips": r1["trips"],
        "P2 Trips": r2["trips"],
        "P1 CI": r1["ci"],
        "P2 CI": r2["ci"]
    }
    export_view = ExportView(report_data)
    await ctx.send(embed=view.build_embed(), view=view)
    await ctx.send("📁 Download Compare Report", view=export_view)

# =========================
# BEST PLANE
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
    embed = discord.Embed(title="Best Aircraft", description=f"```{airport_name(frm)}\n→ {airport_name(to)}```", color=0x2b2d31)
    embed.add_field(name="Aircraft", value=best_plane["name"], inline=False)
    embed.add_field(name="Profit/Day", value=money(best_calc["profit_day"]), inline=True)
    embed.add_field(name="Trips/Day", value=best_calc["trips"], inline=True)
    embed.add_field(name="Mode", value=best_calc["mode"].upper(), inline=False)
    embed.set_footer(text="JARVIS • Aircraft Optimization")
    report_data = {
        "Route": f"{frm.upper()} -> {to.upper()}",
        "Aircraft": best_plane["name"],
        "Mode": best_calc["mode"],
        "Profit/Day": best_calc["profit_day"],
        "Trips/Day": best_calc["trips"],
        "Income/Day": best_calc["income_day"],
        "Fuel/Day": best_calc["fuel_day"],
        "CI": best_calc["ci"]
    }
    export_view = ExportView(report_data)
    await ctx.send(embed=embed)
    await ctx.send("Download Report", view=export_view)

# =========================
# BEST ROUTE COMMANDS
# =========================
@bot.command(name="best_r", aliases=["bestr", "top"])
async def best_r(ctx, airport, *, plane_name):
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        return await ctx.send("Plane not found")
    mode = get_user_mode(ctx.author.id)
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (airport,))
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
        text += f"**{i}. {airport} → {dest}**\n`Profit` ${profit:,}/day\n`Trips` {trips}/day\n`CI` {ci}%\n`Range` {dist:,} km\n\n"
    
    embed = discord.Embed(title=f"Best Routes • {plane['name']}", description=text, color=0x2b2d31)
    embed.add_field(name="Analysis", value=f"`Airport:` {airport}\n`Aircraft:` {plane['name']}\n`Mode:` {mode.upper()}", inline=False)
    embed.set_footer(text="JARVIS • Smart Route Optimization")
    
    export_data = {"Airport": airport, "Aircraft": plane["name"], "Mode": mode}
    for i, r in enumerate(top, start=1):
        dest, dist, profit, trips, ci = r
        export_data[f"#{i} Route"] = f"{airport}->{dest}"
        export_data[f"#{i} Profit"] = profit
        export_data[f"#{i} Trips"] = trips
        export_data[f"#{i} CI"] = ci
        export_data[f"#{i} Range"] = dist
    export_view = ExportView(export_data)
    await ctx.send(embed=embed)
    await ctx.send("Download Route Report", view=export_view)

@bot.command(name="best_short")
async def best_short(ctx, airport, *, plane_name):
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        await ctx.send("❌ Plane not found")
        return
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (airport,))
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
    embed.set_footer(text="JARVIS - AERO CROWN DYNASTY ™")
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
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (airport,))
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
    embed.set_footer(text="JARVIS - AERO CROWN DYNASTY ™")
    await ctx.send(embed=embed)

# =========================
# WELCOME + CHAT
# =========================
@bot.event
async def on_member_join(member):
    channel = member.guild.system_channel
    if channel:
        embed = discord.Embed(title="👋 Welcome to Aero Crown Dynasty", description=f"{member.mention} welcome onboard!\n\nUse `!menu` to explore JARVIS.", color=0x00ffcc)
        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
        embed.set_footer(text="JARVIS - A AERO CROWN DYNASTY OFFICIAL BOT")
        await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    msg = message.content.lower().strip()
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_mentioned or is_dm):
        await bot.process_commands(message)
        return
    msg = msg.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    greetings = ["hi", "hello", "hey", "jarvis", "yo"]
    thanks = ["thanks", "thank you", "thx"]
    help_words = ["help", "support", "what can you do"]
    if any(word == msg for word in greetings):
        replies = [f"Hey {message.author.mention} 👋 I'm online and ready.", f"Hello {message.author.mention} ⚡ What do you need?", f"Hi {message.author.mention} 👋 Jarvis is active."]
        await message.channel.send(random.choice(replies))
    elif any(word in msg for word in thanks):
        replies = [f"You're welcome {message.author.mention} 👍", f"Anytime {message.author.mention} ⚡", f"Glad to help {message.author.mention} 😊"]
        await message.channel.send(random.choice(replies))
    elif any(word in msg for word in help_words):
        await message.channel.send(f"🧠 {message.author.mention} I can help with AM4 routes, aircraft data, comparisons, leaderboard, and system commands.")
    else:
        replies = [f"{message.author.mention} I'm not fully sure, but I can try helping. Can you rephrase?", f"{message.author.mention} 🤔 I need a bit more context.", f"{message.author.mention} I don't have a direct match for that, but I'm listening."]
        await message.channel.send(random.choice(replies))
    await bot.process_commands(message)

# =========================================================
# FUEL COMMANDS - FIXED WITH FALLBACK
# =========================================================

# FIX: Alternative function using pytz
def get_am4_market_time_v2():
    real_ts = int(time.time())
    ist_ts = real_ts + (5.5 * 3600)
    market_slot_ts = (int(ist_ts) // 1800) * 1800
    utc = pytz.UTC
    dt = datetime.fromtimestamp(market_slot_ts, utc)
    return dt.day, dt.strftime("%H:%M"), real_ts

# FIX: Main function with fallback
def get_am4_market_time():
    real_ts = int(time.time())
    ist_ts = real_ts + (5.5 * 3600)
    market_slot_ts = (int(ist_ts) // 1800) * 1800
    try:
        dt = datetime.fromtimestamp(market_slot_ts, datetime.timezone.utc)
        return dt.day, dt.strftime("%H:%M"), real_ts
    except AttributeError:
        return get_am4_market_time_v2()

def analyze_market(fuel, co2):
    f_stat = "🟢 BUY" if fuel < 900 else ("🟡 NEED" if fuel <= 1100 else "🔴 NO")
    c_stat = "🟢 BUY" if co2 < 100 else ("🟡 URG" if co2 <= 120 else "🔴 NO")
    return f_stat, c_stat

def get_market_session(fuel_price, co2_price):
    if fuel_price < 800 and co2_price < 90:
        return "🚀 SUPER SALE", 0xff0000
    elif fuel_price < 900 and co2_price < 100:
        return "🟢 BUYING WINDOW", 0x00ff00
    elif fuel_price < 950 and co2_price < 110:
        return "📊 GOOD OPPORTUNITY", 0x88ff88
    elif fuel_price <= 1100 and co2_price <= 120:
        return "⚠️ AVERAGE MARKET", 0xffaa00
    else:
        return "⏸️ NEUTRAL MARKET", 0x88aaff

def calculate_price_trend(price_type, day_num, time_str):
    try:
        h, m = map(int, time_str.split(':'))
        current_minutes = h * 60 + m
        trends = []
        with get_fuels_db() as conn:
            cursor = conn.cursor()
            for i in range(1, 4):
                prev_minutes = current_minutes - (i * 30)
                if prev_minutes < 0:
                    prev_day = day_num - 1
                    if prev_day < 1:
                        prev_day = 7
                    prev_minutes += 24 * 60
                else:
                    prev_day = day_num
                prev_h = prev_minutes // 60
                prev_m = prev_minutes % 60
                prev_time = f"{prev_h:02d}:{prev_m:02d}"
                cursor.execute(f"SELECT {price_type} FROM Day{prev_day} WHERE TimeUTC = ?", (prev_time,))
                row = cursor.fetchone()
                if row:
                    trends.append(row[0])
        if len(trends) >= 2:
            if trends[0] < trends[1]:
                return "falling"
            elif trends[0] > trends[1]:
                return "rising"
        return "stable"
    except:
        return "stable"

def get_trading_suggestion(fuel_price, co2_price, fuel_trend, co2_trend):
    suggestions = []
    if fuel_price < 850:
        suggestions.append("⛽ 🔥 BUY NOW - historically low")
    elif fuel_price < 950:
        suggestions.append("⛽ ✅ GOOD PRICE - consider buying")
    elif fuel_price <= 1100:
        suggestions.append("⛽ ⚠️ MODERATE - buy only if urgent")
    else:
        suggestions.append("⛽ ❌ TOO EXPENSIVE - avoid buying")
    if co2_price < 95:
        suggestions.append("🌱 🔥 EXCELLENT - stock up now!")
    elif co2_price < 110:
        suggestions.append("🌱 ✅ DECENT PRICE - good to buy")
    else:
        suggestions.append("🌱 ⚠️ HIGH PRICE - wait for drop")
    if fuel_price < 900 and co2_price < 100:
        suggestions.append("\n🎯 STRATEGY: Aggressive buying")
    elif fuel_price > 1200 or co2_price > 130:
        suggestions.append("\n🛡️ STRATEGY: Hold resources")
    else:
        suggestions.append("\n⚖️ STRATEGY: Balanced approach")
    return "\n".join(suggestions)

@bot.command(name="fuel")
async def fuel_check(ctx):
    try:
        day_num, time_str, unix_ts = get_am4_market_time()
    except:
        day_num, time_str, unix_ts = get_am4_market_time_v2()
    
    with get_fuels_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT FuelPrice, CO2Price FROM Day{day_num} WHERE TimeUTC = ?", (time_str,))
        row = cursor.fetchone()
    
    if row:
        fuel_price = row["FuelPrice"]
        co2_price = row["CO2Price"]
        fuel_trend = calculate_price_trend("FuelPrice", day_num, time_str)
        co2_trend = calculate_price_trend("CO2Price", day_num, time_str)
        session_msg, session_color = get_market_session(fuel_price, co2_price)
        f_s, c_s = analyze_market(fuel_price, co2_price)
        
        embed = discord.Embed(title="⚡ AM4 FUEL Market Dashboard", description=f"### {session_msg}", color=session_color)
        utc_real = datetime.now(datetime.timezone.utc).strftime("%H:%M UTC")
        embed.add_field(name="🕐 Time Synchronization", value=f"🌍 **UTC Time:** `{utc_real}`\n\n🖥️ **Your Local Time:** <t:{unix_ts}:F>", inline=False)
        fuel_emoji = "📉" if fuel_trend == "falling" else "📈" if fuel_trend == "rising" else "➡️"
        co2_emoji = "📉" if co2_trend == "falling" else "📈" if co2_trend == "rising" else "➡️"
        embed.add_field(name="⛽ FUEL ANALYSIS", value=f"```yaml\n💰 Price: ${fuel_price}\n{fuel_emoji} Trend: {fuel_trend.upper()}\n🎯 Status: {f_s}\n💡 Best Buy: < $900```", inline=True)
        embed.add_field(name="🌱 CO2 ANALYSIS", value=f"```yaml\n💰 Price: ${co2_price}\n{co2_emoji} Trend: {co2_trend.upper()}\n🎯 Status: {c_s}\n💡 Best Buy: < $100```", inline=True)
        fuel_score = max(0, 100 - ((fuel_price - 700) / 10)) if fuel_price > 700 else 100
        co2_score = max(0, 100 - ((co2_price - 80) / 5)) if co2_price > 80 else 100
        total_score = (fuel_score + co2_score) / 2
        score_bar = "█" * int(total_score / 10) + "░" * (10 - int(total_score / 10))
        embed.add_field(name="📊 MARKET HEALTH", value=f"```yaml\n{score_bar} {total_score:.1f}%\nRating: {'EXCELLENT' if total_score > 80 else 'GOOD' if total_score > 60 else 'AVERAGE'}```", inline=False)
        suggestions = get_trading_suggestion(fuel_price, co2_price, fuel_trend, co2_trend)
        embed.add_field(name="💡 SMART SUGGESTIONS", value=f"```yaml\n{suggestions}```", inline=False)
        embed.set_footer(text="AM4 Market • Updates every 30 mins")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ No market data available for current time slot!")

@bot.command(name="predict")
async def predict_market(ctx):
    try:
        now_utc = datetime.now(datetime.timezone.utc)
    except AttributeError:
        now_utc = datetime.now(pytz.UTC)
    
    ist_now = now_utc + timedelta(hours=5, minutes=30)
    minute_slot = 30 if ist_now.minute >= 30 else 0
    current_slot = ist_now.replace(minute=minute_slot, second=0, microsecond=0)
    rows = []
    best_fuel_price = float("inf")
    best_fuel_slot = None
    best_co2_price = float("inf")
    best_co2_slot = None

    for i in range(24):
        future_slot = current_slot + timedelta(minutes=(i * 30))
        target_day = future_slot.day
        db_time = future_slot.strftime("%H:%M")
        try:
            with get_fuels_db() as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT FuelPrice, CO2Price FROM Day{target_day} WHERE TimeUTC = ?", (db_time,))
                row = cursor.fetchone()
        except:
            row = None
        if row:
            fuel_price = row["FuelPrice"]
            co2_price = row["CO2Price"]
            if fuel_price < 900 and co2_price < 100:
                action = "🟢 BUY"
            elif fuel_price <= 1100:
                action = "🟡 WAIT"
            else:
                action = "🔴 AVOID"
            utc_slot = future_slot - timedelta(hours=5, minutes=30)
            ist_timezone = datetime.timezone(timedelta(hours=5, minutes=30))
            future_slot_ist = future_slot.replace(tzinfo=ist_timezone)
            rows.append({"utc": utc_slot.strftime("%H:%M"), "local": int(future_slot_ist.timestamp()), "fuel": fuel_price, "co2": co2_price, "action": action})
            if fuel_price < best_fuel_price:
                best_fuel_price = fuel_price
                best_fuel_slot = int(future_slot_ist.timestamp())
            if co2_price < best_co2_price:
                best_co2_price = co2_price
                best_co2_slot = int(future_slot_ist.timestamp())

    if not rows:
        return await ctx.send("❌ No market data available!")

    embeds = []
    items_per_page = 8
    total_pages = ((len(rows) - 1) // items_per_page) + 1
    utc_display = now_utc.strftime("%A, %B %d, %Y %I:%M %p UTC")

    for page_start in range(0, len(rows), items_per_page):
        page_rows = rows[page_start:page_start + items_per_page]
        embed = discord.Embed(title=f"🔮 Market Outlook • Page {(page_start // items_per_page) + 1}/{total_pages}", description=f"🕐 **UTC Current:** {utc_display}\n📊 **12-Hour Fuel & CO2 Forecast**\n\n━━━━━━━━━━━━━━━━━━", color=0x9b59b6)
        prediction_text = ""
        for r in page_rows:
            prediction_text += f"⏰ <t:{r['local']}:t>\n⛽ Fuel: **${r['fuel']}**\n🌱 CO2: **${r['co2']}**\n{r['action']}\n━━━━━━━━━━━━━━━━━━\n"
        embed.add_field(name="📈 Prediction Matrix", value=prediction_text, inline=False)
        if page_start == 0:
            best_text = f"⛽ **Best Fuel:** `${best_fuel_price}`\n🕒 <t:{best_fuel_slot}:F>\n\n🌱 **Best CO2:** `${best_co2_price}`\n🕒 <t:{best_co2_slot}:F>"
            embed.add_field(name="🎯 Best Trading Windows", value=best_text, inline=False)
        embed.set_footer(text="🟢 Buy • 🟡 Wait • 🔴 Avoid • Updates every 30 mins")
        embeds.append(embed)

    class PredictView(View):
        def __init__(self, embeds):
            super().__init__(timeout=43200)
            self.embeds = embeds
            self.page = 0
        async def update_message(self, interaction):
            await interaction.response.edit_message(embed=self.embeds[self.page], view=self)
        @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
        async def prev_btn(self, interaction, button):
            if self.page > 0:
                self.page -= 1
            await self.update_message(interaction)
        @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
        async def next_btn(self, interaction, button):
            if self.page < len(self.embeds) - 1:
                self.page += 1
            await self.update_message(interaction)

    view = PredictView(embeds)
    await ctx.send(embed=embeds[0], view=view)

# =========================
# RUN BOT WITH PORT BINDING (Render Web Service Fix)
# =========================
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: TOKEN environment variable missing.")
    else:
        keep_alive()  # Flask server for port binding
        bot.run(TOKEN)