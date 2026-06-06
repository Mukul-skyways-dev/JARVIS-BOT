import discord
import random 
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import io

import sqlite3
import os
import requests
from openai import OpenAI
import pytz

from export_view import ExportView
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta
import asyncio
import time
from PIL import Image, ImageDraw

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
# DYNAMIC DB (NEW FEATURES)
# =========================
conn_dyn = sqlite3.connect("new_am4.db", check_same_thread=False)
conn_dyn.row_factory = sqlite3.Row
cursor_dyn = conn_dyn.cursor()

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

    # =========================
    # FLIGHT OPS
    # =========================
    @discord.ui.button(
        label="Flight Ops",
        style=discord.ButtonStyle.primary,
        row=0
    )
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

        embed.set_footer(
            text="JARVIS • Flight Operations Engine"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =========================
    # ROUTE INTEL
    # =========================
    @discord.ui.button(
        label="Route Intel",
        style=discord.ButtonStyle.danger,
        row=0
    )
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

        embed.set_footer(
            text="JARVIS • Route Intelligence Core"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =========================
    # FLEET
    # =========================
    @discord.ui.button(
        label="Fleet Analysis",
        style=discord.ButtonStyle.secondary,
        row=0
    )
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

        embed.set_footer(
            text="JARVIS • Fleet Analysis System"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =========================
    # AIRPORT
    # =========================
    @discord.ui.button(
        label="Airport Systems",
        style=discord.ButtonStyle.success,
        row=1
    )
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

        embed.set_footer(
            text="JARVIS • Airport Database System"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =========================
    # UTILITIES
    # =========================
    @discord.ui.button(
        label="Utilities",
        style=discord.ButtonStyle.secondary,
        row=1
    )
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

        embed.set_footer(
            text="JARVIS • Utility Interface"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


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

    embed.set_footer(
        text="JARVIS • A AERO CROWN DYNASTY OFFICIAL BOT"
    )

    await ctx.send(
        embed=embed,
        view=EliteMenu()
    )

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
# CALC ENGINE V3 (REALISM + EASY)
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

        # load factor
        lf = 1.0

        # NEW REALISTIC TICKET FORMULA
        y_price = (0.4 * dist) + 170
        j_price = (0.8 * dist) + 560
        f_price = (1.2 * dist) + 1200

        # costs
        fuel_mult = 4
        co2_mult = 1.8

        acheck = 20000
        repair = 15000

        cargo_mul = 0.5

    else:  # REALISM MODE

        # realistic load factor
        lf = 0.85

        # NEW REALISM FORMULA
        y_price = (0.3 * dist) + 150
        j_price = (0.6 * dist) + 500
        f_price = (0.9 * dist) + 1000

        # realistic costs
        fuel_mult = 5.5
        co2_mult = 2.5

        acheck = 40000
        repair = 25000

        cargo_mul = 0.35

    # =========================
    # CONFIGURATION
    # =========================
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

    # =========================
    # INCOME
    # =========================
    income_trip = (
        (y_c * y_price) +
        (j_c * j_price) +
        (f_c * f_price)
    )

    # =========================
    # CARGO
    # =========================
    cargo = float(route.get("cargo", 0))
    cargo_income = cargo * cargo_mul

    income_trip += cargo_income

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
    total_cost = fuel + co2 + acheck + repair

    profit_trip = income_trip - total_cost

    ci = int((profit_trip / income_trip) * 100) if income_trip else 0

    # =========================
    # DAILY VALUES
    # =========================
    income_day = income_trip * trips
    fuel_day = fuel * trips
    co2_day = co2 * trips
    profit_day = profit_trip * trips

    # =========================
    # RETURN DATA
    # =========================
    return {

        # mode
        "mode": mode,

        # flight
        "distance": int(dist),
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
        "cargo_income": int(cargo_income),

        # costs
        "fuel": int(fuel),
        "fuel_lb": int(fuel_lb),

        "co2": int(co2),
        "co2_q": int(co2_q),

        "acheck": int(acheck),
        "repair": int(repair),

        "total_cost": int(total_cost),

        # profit
        "profit_trip": int(profit_trip),
        "ci": ci,

        # daily
        "income_day": int(income_day),
        "fuel_day": int(fuel_day),
        "co2_day": int(co2_day),
        "profit_day": int(profit_day)
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

    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (str(user.id),))
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

# =========================================================
# REQUIRED IMPORTS
# =========================================================

import tempfile

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageFilter
)

# =========================================================
# AIRPORT HELPER
# =========================================================

def airport_name(iata):

    try:

        iata = iata.upper()

        cursor.execute("""
        SELECT
            f_city,
            f_country,
            f_name
        FROM routes
        WHERE f_iata = ?
        LIMIT 1
        """, (iata,))

        row = cursor.fetchone()

        if not row:

            cursor.execute("""
            SELECT
                t_city,
                t_country,
                t_name
            FROM routes
            WHERE t_iata = ?
            LIMIT 1
            """, (iata,))

            row = cursor.fetchone()

        if row:

            city = row[0]
            country = row[1]
            airport = row[2]

            return (
                f"{iata} • {airport}\n"
                f"{city}, {country}"
            )

    except Exception as e:

        print("airport_name error:", e)

    return iata


# =========================================================
# GET ROUTE
# =========================================================

def get_route(frm, to):

    cursor.execute("""
    SELECT *
    FROM routes
    WHERE
    (f_iata = ? AND t_iata = ?)
    OR
    (f_iata = ? AND t_iata = ?)
    LIMIT 1
    """, (
        frm.upper(),
        to.upper(),
        to.upper(),
        frm.upper()
    ))

    row = cursor.fetchone()

    if not row:
        return None

    return {

        "distance": to_float(
            row["distance"]
        ),

        "y": to_int(
            row["dem_y"]
        ),

        "j": to_int(
            row["dem_j"]
        ),

        "f": to_int(
            row["dem_f"]
        ),

        "cargo": to_int(
            row["cargo"]
        ) if "cargo" in row.keys() else 0
    }


# =========================================================
# GET PLANE
# =========================================================

def get_plane(name):

    key = norm(name)

    for p in get_all_planes():

        plane_key = norm(
            p["name"]
        )

        if (
            key == plane_key
            or key in plane_key
            or plane_key in key
        ):
            return p

    return None

# =========================================================
# AIRCRAFT VISUAL SYSTEM V8 - COMPLETE REDESIGN
# REALISTIC FUSELAGE • SMOOTH CURVES • PROFESSIONAL LOOK
# =========================================================

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import tempfile
import math

def draw_aircraft_card(plane, result, route, frm, to):
    
    # =====================================================
    # CANVAS
    # =====================================================
    W = 1400
    H = 850
    
    img = Image.new("RGB", (W, H), (10, 15, 25))
    draw = ImageDraw.Draw(img)
    
    # =====================================================
    # BACKGROUND - Premium Dark Theme
    # =====================================================
    # Gradient background effect
    for i in range(H):
        ratio = i / H
        color = (10 + int(5 * ratio), 15 + int(10 * ratio), 25 + int(20 * ratio))
        draw.line([(0, i), (W, i)], fill=color, width=1)
    
    # Glow effects
    glow1 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd1 = ImageDraw.Draw(glow1)
    gd1.ellipse((100, 100, 500, 500), fill=(0, 150, 255, 40))
    glow1 = glow1.filter(ImageFilter.GaussianBlur(100))
    img.paste(glow1, (0, 0), glow1)
    
    # =====================================================
    # GLASS CARD PANEL
    # =====================================================
    panel = Image.new("RGBA", (W - 100, H - 100), (30, 35, 50, 180))
    panel = panel.filter(ImageFilter.GaussianBlur(2))
    img.paste(panel, (50, 50), panel)
    draw.rounded_rectangle((50, 50, W - 50, H - 50), radius=25, outline=(100, 150, 255, 150), width=2)
    
    # =====================================================
    # FONTS
    # =====================================================
    try:
        title_font = ImageFont.truetype("arial.ttf", 36)
        header_font = ImageFont.truetype("arial.ttf", 28)
        text_font = ImageFont.truetype("arial.ttf", 22)
        small_font = ImageFont.truetype("arial.ttf", 18)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # =====================================================
    # HEADER SECTION
    # =====================================================
    from_airport = airport_name(frm)
    to_airport = airport_name(to)
    
    draw.text((80, 70), "JARVIS AVIATION VISUAL SYSTEM", fill=(150, 200, 255), font=title_font)
    draw.line((80, 115, 500, 115), fill=(150, 200, 255, 100), width=1)
    
    # Route display
    draw.text((80, 140), from_airport, fill=(100, 180, 255), font=header_font)
    draw.text((80, 180), "▼", fill=(255, 255, 255), font=text_font)
    draw.text((80, 215), to_airport, fill=(100, 180, 255), font=header_font)
    
    # =====================================================
    # AIRCRAFT FUSELAGE - COMPLETELY REDESIGNED
    # =====================================================
    capacity = max(int(float(plane["capacity"])), 100)
    
    # Smooth proportional sizing
    fuselage_length = min(max(550, 550 + int(capacity * 0.12)), 780)
    fuselage_height = min(max(75, 75 + int(capacity * 0.006)), 105)
    
    # Position (centered beautifully)
    fuselage_x = 250
    fuselage_y = 310
    
    # =====================================================
    # DROP SHADOW
    # =====================================================
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (fuselage_x + 10, fuselage_y + 20, fuselage_x + fuselage_length + 10, fuselage_y + fuselage_height + 20),
        radius=fuselage_height // 2 + 5,
        fill=(0, 0, 0, 100)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(25))
    img.paste(shadow, (0, 0), shadow)
    
    # =====================================================
    # MAIN FUSELAGE BODY (SMOOTH CURVED)
    # =====================================================
    draw.rounded_rectangle(
        (fuselage_x, fuselage_y, fuselage_x + fuselage_length, fuselage_y + fuselage_height),
        radius=fuselage_height // 2,
        fill=(220, 225, 240)
    )
    
    # Fuselage metallic highlight
    highlight_y1 = fuselage_y + 8
    highlight_y2 = fuselage_y + 18
    draw.rounded_rectangle(
        (fuselage_x + 30, highlight_y1, fuselage_x + fuselage_length - 30, highlight_y2),
        radius=5,
        fill=(255, 255, 255, 200)
    )
    
    # Lower highlight
    low_y1 = fuselage_y + fuselage_height - 18
    low_y2 = fuselage_y + fuselage_height - 8
    draw.rounded_rectangle(
        (fuselage_x + 30, low_y1, fuselage_x + fuselage_length - 30, low_y2),
        radius=5,
        fill=(255, 255, 255, 120)
    )
    
    # =====================================================
    # NOSE SECTION (ELEGANT CURVE)
    # =====================================================
    nose_radius = fuselage_height // 2
    nose_start = fuselage_x + fuselage_length - 40
    
    # Nose cone
    draw.pieslice(
        (nose_start - 80, fuselage_y - 10, nose_start + 30, fuselage_y + fuselage_height + 10),
        start=270, end=450,
        fill=(210, 215, 230)
    )
    
    # Nose tip (darker)
    draw.pieslice(
        (nose_start - 50, fuselage_y, nose_start + 20, fuselage_y + fuselage_height),
        start=280, end=440,
        fill=(190, 195, 210)
    )
    
    # Cockpit windows (modern design)
    cockpit_w = 50
    cockpit_h = 28
    cockpit_x = fuselage_x + fuselage_length - 65
    cockpit_y = fuselage_y + (fuselage_height // 2) - 14
    
    draw.rounded_rectangle(
        (cockpit_x, cockpit_y, cockpit_x + cockpit_w, cockpit_y + cockpit_h),
        radius=10,
        fill=(80, 150, 230)
    )
    
    # Cockpit reflection
    draw.rounded_rectangle(
        (cockpit_x + 5, cockpit_y + 3, cockpit_x + cockpit_w - 5, cockpit_y + 12),
        radius=3,
        fill=(150, 200, 255, 180)
    )
    
    # =====================================================
    # TAIL SECTION (SWEPT BACK)
    # =====================================================
    tail_x = fuselage_x - 35
    tail_y = fuselage_y - 15
    
    # Vertical stabilizer
    draw.polygon([
        (tail_x + 20, fuselage_y + 10),
        (tail_x, fuselage_y + fuselage_height // 2),
        (tail_x + 15, fuselage_y + fuselage_height // 2 + 5),
        (tail_x + 45, fuselage_y + 15)
    ], fill=(200, 205, 220))
    
    # Tail cone
    draw.polygon([
        (tail_x + 5, fuselage_y + fuselage_height // 2 - 5),
        (tail_x - 15, fuselage_y + fuselage_height // 2),
        (tail_x + 5, fuselage_y + fuselage_height // 2 + 5)
    ], fill=(180, 185, 200))
    
    # =====================================================
    # PASSENGER WINDOWS (PERFECT SPACING)
    # =====================================================
    window_count = min(max(int(capacity / 10), 18), 42)
    window_spacing = (fuselage_length - 180) // window_count
    window_y = fuselage_y + 22
    window_h = 16
    
    for i in range(window_count):
        window_x = fuselage_x + 70 + (i * window_spacing)
        
        # Window frame
        draw.rounded_rectangle(
            (window_x, window_y, window_x + 14, window_y + window_h),
            radius=4,
            fill=(50, 55, 65)
        )
        
        # Window glass
        draw.rounded_rectangle(
            (window_x + 2, window_y + 2, window_x + 12, window_y + window_h - 2),
            radius=3,
            fill=(70, 150, 220)
        )
        
        # Window glow
        if i % 2 == 0:
            draw.rectangle(
                (window_x + 3, window_y + 3, window_x + 11, window_y + 10),
                fill=(120, 200, 255, 100)
            )
    
    # =====================================================
    # CABIN DOOR
    # =====================================================
    door_x = fuselage_x + fuselage_length - 200
    door_w = 30
    door_h = fuselage_height - 20
    
    draw.rounded_rectangle(
        (door_x, fuselage_y + 10, door_x + door_w, fuselage_y + door_h + 10),
        radius=8,
        fill=(190, 195, 210)
    )
    
    # Door outline
    draw.rounded_rectangle(
        (door_x + 3, fuselage_y + 13, door_x + door_w - 3, fuselage_y + door_h + 7),
        radius=6,
        outline=(100, 105, 120),
        width=1
    )
    
    # Door windows
    draw.rounded_rectangle(
        (door_x + 5, fuselage_y + 15, door_x + 25, fuselage_y + 30),
        radius=4,
        fill=(70, 150, 220)
    )
    
    # =====================================================
    # AIRCRAFT TITLE
    # =====================================================
    draw.text(
        (fuselage_x + 120, fuselage_y + fuselage_height - 35),
        plane["name"],
        fill=(30, 35, 45),
        font=header_font
    )
    
    # Registration
    reg = plane.get("registration", "VT-JARVIS")
    draw.text(
        (tail_x + 10, fuselage_y + fuselage_height - 28),
        reg,
        fill=(80, 85, 100),
        font=small_font
    )
    
    # =====================================================
    # SEAT CONFIGURATION BAR
    # =====================================================
    y_seats = max(result["y"], 0)
    j_seats = max(result["j"], 0)
    f_seats = max(result["f"], 0)
    total_seats = max(y_seats + j_seats + f_seats, 1)
    
    bar_x = fuselage_x + 80
    bar_y = fuselage_y - 35
    bar_w = fuselage_length - 160
    bar_h = 20
    
    # Background bar
    draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=8, fill=(40, 45, 60))
    
    f_w = int((f_seats / total_seats) * bar_w)
    j_w = int((j_seats / total_seats) * bar_w)
    y_w = bar_w - f_w - j_w
    
    current_x = bar_x
    
    if f_w > 0:
        draw.rounded_rectangle((current_x, bar_y, current_x + f_w, bar_y + bar_h), radius=6, fill=(220, 60, 100))
        current_x += f_w
    if j_w > 0:
        draw.rounded_rectangle((current_x, bar_y, current_x + j_w, bar_y + bar_h), radius=6, fill=(255, 180, 40))
        current_x += j_w
    if y_w > 0:
        draw.rounded_rectangle((current_x, bar_y, current_x + y_w, bar_y + bar_h), radius=6, fill=(50, 180, 255))
    
    # =====================================================
    # STATS PANEL (LEFT)
    # =====================================================
    sx = 80
    sy = 460
    
    # Section header
    draw.text((sx, sy), "FLIGHT DATA", fill=(150, 200, 255), font=text_font)
    draw.line((sx, sy + 30, sx + 250, sy + 30), fill=(150, 200, 255, 80), width=1)
    
    stats = [
        f"✈️ Distance      : {int(route['distance']):,} km",
        f"🔄 Trips/Day     : {result['trips']}",
        f"⏱️ Flight Time   : {format_time(result['time'])}",
        f"💰 Daily Profit  : ${result['profit_day']:,}",
        f"⛽ Fuel Cost     : ${result['fuel_day']:,}",
        f"🌱 CO2 Cost      : ${result['co2_day']:,}"
    ]
    
    for i, stat in enumerate(stats):
        draw.text((sx + 10, sy + 45 + i * 32), stat, fill=(200, 210, 220), font=small_font)
    
    # =====================================================
    # RIGHT PANEL - SEAT LEGEND & CI
    # =====================================================
    rx = 980
    ry = 460
    
    draw.text((rx, ry), "CABIN CONFIGURATION", fill=(150, 200, 255), font=text_font)
    draw.line((rx, ry + 30, rx + 280, ry + 30), fill=(150, 200, 255, 80), width=1)
    
    legend = [
        ("First Class", (220, 60, 100), f"{f_seats} seats"),
        ("Business", (255, 180, 40), f"{j_seats} seats"),
        ("Economy", (50, 180, 255), f"{y_seats} seats")
    ]
    
    for i, (name, color, count) in enumerate(legend):
        yy = ry + 45 + i * 50
        draw.rounded_rectangle((rx + 10, yy, rx + 45, yy + 30), radius=6, fill=color)
        draw.text((rx + 60, yy + 5), name, fill=(200, 210, 220), font=small_font)
        draw.text((rx + 60, yy + 25), count, fill=(150, 160, 170), font=small_font)
    
    # =====================================================
    # CONFIDENCE INDEX METER
    # =====================================================
    ci = result['ci']
    meter_y = ry + 220
    
    draw.text((rx, meter_y), "PERFORMANCE METER", fill=(150, 200, 255), font=text_font)
    
    # Meter background
    draw.rounded_rectangle((rx + 10, meter_y + 35, rx + 280, meter_y + 55), radius=8, fill=(40, 45, 60))
    
    # Meter fill
    meter_w = int(270 * (ci / 100))
    if ci > 85:
        meter_color = (50, 200, 80)
    elif ci > 70:
        meter_color = (255, 180, 40)
    else:
        meter_color = (220, 60, 60)
    
    draw.rounded_rectangle((rx + 10, meter_y + 35, rx + 10 + meter_w, meter_y + 55), radius=6, fill=meter_color)
    
    # CI percentage
    draw.text((rx + 120, meter_y + 65), f"{ci}%", fill=(255, 255, 255), font=text_font)
    
    # =====================================================
    # FOOTER
    # =====================================================
    footer_y = H - 50
    draw.text((W // 2 - 150, footer_y), "AERO CROWN DYNASTY • JARVIS INTELLIGENCE", fill=(80, 85, 110), font=small_font)
    draw.text((W // 2 - 100, footer_y + 25), "Powered by Advanced Aviation Analytics", fill=(60, 65, 90), font=small_font)
    
    # =====================================================
    # SAVE & RETURN
    # =====================================================
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


def airport_name(code):
    airports = {
        "JFK": "New York (JFK)",
        "LHR": "London Heathrow (LHR)",
        "DXB": "Dubai International (DXB)",
        "CDG": "Paris Charles de Gaulle",
        "FRA": "Frankfurt am Main",
        "SIN": "Singapore Changi",
        "HND": "Tokyo Haneda",
        "LAX": "Los Angeles International",
        "ORD": "Chicago O'Hare",
        "DFW": "Dallas/Fort Worth",
        "DEN": "Denver International",
        "DEL": "Delhi Indira Gandhi",
        "BOM": "Mumbai Chhatrapati Shivaji",
        "BLR": "Bangalore Kempegowda",
        "HYD": "Hyderabad Rajiv Gandhi"
    }
    return airports.get(code.upper(), code.upper())

def calculate_range(capacity):
    # Simplified range calculation
    return int(5000 + (capacity * 5))
    
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

    # =====================================================
    # STOPOVER SYSTEM
    # =====================================================

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

    # =====================================================
    # CALC ENGINE
    # =====================================================

    result = calc(
        route,
        plane,
        ctx.author.id
    )

    mode = result["mode"]

    # =====================================================
    # ROUTE DISPLAY
    # =====================================================

    from_txt = airport_name(frm)
    to_txt = airport_name(to)

    if stop_airport:

        stop_txt = airport_name(stop_airport)

        route_display = (
            f"{from_txt}\n"
            f"→ {stop_txt}\n"
            f"→ {to_txt}"
        )

    else:

        route_display = (
            f"{from_txt}\n"
            f"→ {to_txt}"
        )

    # =====================================================
    # EMBED
    # =====================================================

    embed = discord.Embed(
        title=f"{plane['name']} • Route Analysis V3.0.1",
        description=f"```{route_display}```",
        color=0x2b2d31
    )

    # =====================================================
    # FLIGHT INFO
    # =====================================================

    embed.add_field(
        name="✈ Flight Info",
        value=(
            f"**Distance:** {int(distance_total):,} km\n"
            f"**Trips:** {result['trips']}/day\n"
            f"**Mode:** {mode.upper()}"
        ),
        inline=False
    )

    # =====================================================
    # DEMAND
    # =====================================================

    embed.add_field(
        name="📊 Demand",
        value=(
            f"**Y:** {route['y']}\n"
            f"**J:** {route['j']}\n"
            f"**F:** {route['f']}"
        ),
        inline=True
    )

    # =====================================================
    # CONFIGURATION
    # =====================================================

    embed.add_field(
        name="⚙ Configuration",
        value=(
            f"**Y:** {result['y']}\n"
            f"**J:** {result['j']}\n"
            f"**F:** {result['f']}"
        ),
        inline=True
    )

    # =====================================================
    # TICKET PRICING
    # =====================================================

    embed.add_field(
        name="🎟 Ticket Pricing",
        value=(
            f"**Y:** ${result['y_price']:,}\n"
            f"**J:** ${result['j_price']:,}\n"
            f"**F:** ${result['f_price']:,}"
        ),
        inline=True
    )

    # =====================================================
    # PER FLIGHT
    # =====================================================

    embed.add_field(
        name="💰 Per Flight",
        value=(
            f"**Income:** ${result['income_trip']:,}\n"
            f"**Fuel:** ${result['fuel']:,}\n"
            f"**CO2:** ${result['co2']:,}\n"
            f"**Maint:** ${result['acheck'] + result['repair']:,}\n\n"
            f"**Profit:** ${result['profit_trip']:,}\n"
            f"**CI:** {result['ci']}%"
        ),
        inline=False
    )

    # =====================================================
    # PER DAY
    # =====================================================

    embed.add_field(
        name="📅 Per Day",
        value=(
            f"**Income:** ${result['income_day']:,}\n"
            f"**Fuel:** ${result['fuel_day']:,}\n"
            f"**CO2:** ${result['co2_day']:,}\n"
            f"**Maint:** ${(result['acheck'] + result['repair']) * result['trips']:,}\n\n"
            f"**Profit:** ${result['profit_day']:,}\n"
            f"**Flights:** {result['trips']}"
        ),
        inline=False
    )

    embed.set_footer(
        text="JARVIS • AERO CROWN DYNASTY OFFICIAL BOT"
    )

    # =====================================================
    # EXPORT DATA
    # =====================================================

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

    # =====================================================
    # AIRCRAFT VISUAL
    # =====================================================

    img_path = draw_aircraft_card(
        plane,
        result,
        route,
        frm,
        to
    )

    file = discord.File(
        img_path,
        filename="route.png"
    )

    embed.set_image(
        url="attachment://route.png"
    )

    # =====================================================
    # SEND
    # =====================================================

    await ctx.send(
        embed=embed,
        file=file,
        view=ExportView(report_data)
    )

# =========================
# COMPARE VIEW V3
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
    # PAGE 1
    # =========================
    def build_embed(self):

        embed = discord.Embed(
            title=f"{self.p1['name']}  VS  {self.p2['name']}",
            description="```Advanced Aircraft Analytics Engine```",
            color=0x2b2d31
        )

        # ================= SPEC =================
        embed.add_field(
            name="✦ Specifications",
            value=(
                f"**Capacity** → {self.fmt(self.p1['capacity'], self.p2['capacity'])} │ {self.fmt(self.p2['capacity'], self.p1['capacity'])}\n"
                f"**Range** → {self.fmt(self.p1['range'], self.p2['range'])} │ {self.fmt(self.p2['range'], self.p1['range'])}\n"
                f"**Speed** → {self.fmt(self.p1['speed'], self.p2['speed'])} │ {self.fmt(self.p2['speed'], self.p1['speed'])}\n"
                f"**Fuel** → {self.fmt(self.p1['fuel'], self.p2['fuel'], True)} │ {self.fmt(self.p2['fuel'], self.p1['fuel'], True)}"
            ),
            inline=False
        )

        # ================= OPS =================
        embed.add_field(
            name="✦ Operations",
            value=(
                f"**Trips/Day** → {self.fmt(self.r1['trips'], self.r2['trips'])} │ {self.fmt(self.r2['trips'], self.r1['trips'])}\n"
                f"**Flight Time** → {self.fmt(self.r1['time'], self.r2['time'], True)} │ {self.fmt(self.r2['time'], self.r1['time'], True)}\n"
                f"**CI Score** → {self.fmt(self.r1['ci'], self.r2['ci'])}% │ {self.fmt(self.r2['ci'], self.r1['ci'])}%"
            ),
            inline=False
        )

        # ================= REVENUE =================
        embed.add_field(
            name="✦ Revenue",
            value=(
                f"**Income/Flight** → {self.fmt(self.r1['income_trip'], self.r2['income_trip'])} │ {self.fmt(self.r2['income_trip'], self.r1['income_trip'])}\n"
                f"**Profit/Flight** → {self.fmt(self.r1['profit_trip'], self.r2['profit_trip'])} │ {self.fmt(self.r2['profit_trip'], self.r1['profit_trip'])}\n"
                f"**Income/Day** → {self.fmt(self.r1['income_day'], self.r2['income_day'])} │ {self.fmt(self.r2['income_day'], self.r1['income_day'])}\n"
                f"**Profit/Day** → {self.fmt(self.r1['profit_day'], self.r2['profit_day'])} │ {self.fmt(self.r2['profit_day'], self.r1['profit_day'])}"
            ),
            inline=False
        )

        # ================= COST =================
        embed.add_field(
            name="✦ Cost Analysis",
            value=(
                f"**Fuel/Flight** → {self.fmt(self.r1['fuel'], self.r2['fuel'], True)} │ {self.fmt(self.r2['fuel'], self.r1['fuel'], True)}\n"
                f"**CO2/Flight** → {self.fmt(self.r1['co2'], self.r2['co2'], True)} │ {self.fmt(self.r2['co2'], self.r1['co2'], True)}\n"
                f"**Maint** → {self.fmt(self.r1['acheck'] + self.r1['repair'], self.r2['acheck'] + self.r2['repair'], True)} │ {self.fmt(self.r2['acheck'] + self.r2['repair'], self.r1['acheck'] + self.r1['repair'], True)}"
            ),
            inline=False
        )

        # ================= EFF =================
        embed.add_field(
            name="✦ Efficiency",
            value=(
                f"**Fuel(lb)** → {self.fmt(self.r1['fuel_lb'], self.r2['fuel_lb'], True)} │ {self.fmt(self.r2['fuel_lb'], self.r1['fuel_lb'], True)}\n"
                f"**CO2(q)** → {self.fmt(self.r1['co2_q'], self.r2['co2_q'], True)} │ {self.fmt(self.r2['co2_q'], self.r1['co2_q'], True)}"
            ),
            inline=False
        )

        winner = (
            self.p1["name"]
            if self.r1["profit_day"] > self.r2["profit_day"]
            else self.p2["name"]
        )

        embed.set_footer(
            text=f"Page 1/3 • Winner: {winner}"
        )

        return embed

    # =========================
    # PERFORMANCE GRAPH
    # =========================
    def make_graph(self):

        labels = [
            "Income",
            "Profit",
            "Fuel",
            "CO2",
            "Trips"
        ]

        p1_vals = [
            self.r1["income_day"],
            self.r1["profit_day"],
            self.r1["fuel_day"],
            self.r1["co2_day"],
            self.r1["trips"] * 100000
        ]

        p2_vals = [
            self.r2["income_day"],
            self.r2["profit_day"],
            self.r2["fuel_day"],
            self.r2["co2_day"],
            self.r2["trips"] * 100000
        ]

        # BETTER NORMALIZATION
        max_val = max(
            max(p1_vals),
            max(p2_vals)
        )

        if max_val == 0:
            max_val = 1

        p1n = [v / max_val for v in p1_vals]
        p2n = [v / max_val for v in p2_vals]

        x = np.arange(len(labels))

        # ================= FIGURE =================
        fig, ax = plt.subplots(figsize=(9, 5))

        # LIGHT PROFESSIONAL DARK GRAY
        fig.patch.set_facecolor("#1f1f1f")
        ax.set_facecolor("#2b2d31")

        # ================= GLOW EFFECT =================
        for lw, alpha in [(10, 0.05), (7, 0.08), (5, 0.12)]:
            ax.plot(
                x,
                p1n,
                linewidth=lw,
                alpha=alpha
            )

        ax.plot(
            x,
            p1n,
            marker='o',
            linewidth=2.8,
            label=self.p1["name"]
        )

        for lw, alpha in [(10, 0.05), (7, 0.08), (5, 0.12)]:
            ax.plot(
                x,
                p2n,
                linewidth=lw,
                linestyle='--',
                alpha=alpha
            )

        ax.plot(
            x,
            p2n,
            marker='s',
            linewidth=2.8,
            linestyle='--',
            label=self.p2["name"]
        )

        # ================= STYLE =================
        ax.set_xticks(x)
        ax.set_xticklabels(labels)

        ax.grid(
            alpha=0.18,
            linestyle=':'
        )

        ax.legend()

        for spine in ax.spines.values():
            spine.set_color("#555555")

        ax.tick_params(colors="white")

        # ================= SAVE =================
        buf = io.BytesIO()

        plt.savefig(
            buf,
            format='png',
            bbox_inches='tight',
            dpi=300
        )

        buf.seek(0)

        plt.close()

        return buf

    # =========================
    # RADAR
    # =========================
    def make_radar(self):

        labels = [
            "Income",
            "Profit",
            "Efficiency",
            "Speed",
            "Trips"
        ]

        def safe(a, b):

            m = max(a, b)

            return (
                (a / m if m else 0),
                (b / m if m else 0)
            )

        i1, i2 = safe(
            self.r1["income_day"],
            self.r2["income_day"]
        )

        p1v, p2v = safe(
            self.r1["profit_day"],
            self.r2["profit_day"]
        )

        s1, s2 = safe(
            self.p1["speed"],
            self.p2["speed"]
        )

        t1, t2 = safe(
            self.r1["trips"],
            self.r2["trips"]
        )

        e1 = (i1 + p1v) / 2
        e2 = (i2 + p2v) / 2

        v1 = [i1, p1v, e1, s1, t1]
        v2 = [i2, p2v, e2, s2, t2]

        angles = np.linspace(
            0,
            2 * np.pi,
            len(labels),
            endpoint=False
        ).tolist()

        v1 += v1[:1]
        v2 += v2[:1]

        angles += angles[:1]

        # ================= FIGURE =================
        fig = plt.figure(figsize=(6, 6))

        ax = plt.subplot(111, polar=True)

        fig.patch.set_facecolor("#1f1f1f")
        ax.set_facecolor("#2b2d31")

        # ================= PLOTS =================
        ax.plot(
            angles,
            v1,
            linewidth=2.5,
            label=self.p1["name"]
        )

        ax.plot(
            angles,
            v2,
            linewidth=2.5,
            linestyle='--',
            label=self.p2["name"]
        )

        ax.fill(
            angles,
            v1,
            alpha=0.12
        )

        ax.fill(
            angles,
            v2,
            alpha=0.12
        )

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, color="white")

        ax.grid(alpha=0.2)

        plt.legend()

        # ================= SAVE =================
        buf = io.BytesIO()

        plt.savefig(
            buf,
            format='png',
            bbox_inches='tight',
            dpi=300
        )

        buf.seek(0)

        plt.close()

        return buf

    # =========================
    # BUTTONS
    # =========================
    @discord.ui.button(
        label="◀",
        style=discord.ButtonStyle.secondary
    )
    async def prev_btn(self, interaction, button):

        self.page = (self.page - 1) % 3

        await self.update(interaction)

    @discord.ui.button(
        label="▶",
        style=discord.ButtonStyle.primary
    )
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

            file = discord.File(
                buf,
                "graph.png"
            )

            embed = discord.Embed(
                title="📊 Performance Graph",
                color=0x2b2d31
            )

            embed.set_image(
                url="attachment://graph.png"
            )

            await interaction.response.edit_message(
                embed=embed,
                attachments=[file],
                view=self
            )

        elif self.page == 2:

            buf = self.make_radar()

            file = discord.File(
                buf,
                "radar.png"
            )

            embed = discord.Embed(
                title="🧭 Radar Analysis",
                color=0x2b2d31
            )

            embed.set_image(
                url="attachment://radar.png"
            )

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
        return await ctx.send(
            "❌ Use: !compare A320 vs B737"
        )

    p1 = get_plane(p1_name)
    p2 = get_plane(p2_name)

    if not p1 or not p2:
        return await ctx.send(
            "❌ Plane not found"
        )

    route = {
        "distance": 5000,
        "y": 300,
        "j": 50,
        "f": 10,
        "cargo": 10000
    }

    r1 = calc(route, p1, ctx.author.id)
    r2 = calc(route, p2, ctx.author.id)

    view = CompareView(
        p1,
        p2,
        r1,
        r2
    )

    # =========================
    # EXPORT DATA
    # =========================
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

    await ctx.send(
        embed=view.build_embed(),
        view=view
    )

    await ctx.send(
        "📁 Download Compare Report",
        view=export_view
    )

# =========================
# BEST PLANE
# =========================
@bot.command()
async def best(ctx, frm, to):

    route = get_route(frm, to)

    if not route:
        return await ctx.send(
            "Route not found"
        )

    best_plane = None
    best_calc = None
    best_score = -999999999

    for p in get_all_planes():

        try:

            if float(route["distance"]) > float(p["range"]):
                continue

            c = calc(
                route,
                p,
                ctx.author.id
            )

            score = (
                c["profit_day"]
                + (float(p["speed"]) * 10)
                - (float(p["fuel"]) * 100)
            )

            if score > best_score:

                best_score = score
                best_plane = p
                best_calc = c

        except:
            continue

    if not best_plane:
        return await ctx.send(
            "No suitable aircraft found"
        )

    embed = discord.Embed(
        title="Best Aircraft",
        description=(
            f"```"
            f"{airport_name(frm)}"
            f"\n→ "
            f"{airport_name(to)}"
            f"```"
        ),
        color=0x2b2d31
    )

    embed.add_field(
        name="Aircraft",
        value=best_plane["name"],
        inline=False
    )

    embed.add_field(
        name="Profit/Day",
        value=money(best_calc["profit_day"]),
        inline=True
    )

    embed.add_field(
        name="Trips/Day",
        value=best_calc["trips"],
        inline=True
    )

    embed.add_field(
        name="Mode",
        value=best_calc["mode"].upper(),
        inline=False
    )

    embed.set_footer(
        text="JARVIS • Aircraft Optimization"
    )

    # =========================
    # EXPORT
    # =========================
    report_data = {

        "Route":
        f"{frm.upper()} -> {to.upper()}",

        "Aircraft":
        best_plane["name"],

        "Mode":
        best_calc["mode"],

        "Profit/Day":
        best_calc["profit_day"],

        "Trips/Day":
        best_calc["trips"],

        "Income/Day":
        best_calc["income_day"],

        "Fuel/Day":
        best_calc["fuel_day"],

        "CI":
        best_calc["ci"]
    }

    export_view = ExportView(report_data)

    await ctx.send(embed=embed)

    await ctx.send(
        "Download Report",
        view=export_view
    )


# =========================
# BEST ROUTE COMMAND
# =========================
@bot.command(name="best_r", aliases=["bestr", "top"])
async def best_r(ctx, airport, *, plane_name):

    airport = airport.upper()

    plane = get_plane(plane_name)

    if not plane:
        return await ctx.send(
            "Plane not found"
        )

    # =========================
    # USER MODE
    # =========================
    mode = get_user_mode(ctx.author.id)

    # =========================
    # ROUTES
    # =========================
    cursor.execute("""
    SELECT t_iata, distance, dem_y, dem_j, dem_f
    FROM routes
    WHERE f_iata = ?
    LIMIT 300
    """, (airport,))

    routes = cursor.fetchall()

    if not routes:
        return await ctx.send(
            "No routes found"
        )

    results = []

    # =========================
    # ANALYSIS
    # =========================
    for r in routes:

        try:

            dest, dist, y, j, f = r

            distance = float(dist)

            if distance > float(plane["range"]):
                continue

            y = int(y)
            j = int(j)
            f = int(f)

            total_demand = y + j + f

            if total_demand == 0:
                continue

            cap = int(plane["capacity"])

            # =========================
            # MODE SETTINGS
            # =========================
            if mode == "easy":

                lf = 1.0

                # NEW EASY PRICING
                y_price = (0.4 * distance) + 170
                j_price = (0.8 * distance) + 560
                f_price = (1.2 * distance) + 1200

                fuel_mult = 4
                co2_mult = 1.8

                acheck = 20000
                repair = 15000

            else:

                lf = 0.85

                # NEW REALISM PRICING
                y_price = (0.3 * distance) + 150
                j_price = (0.6 * distance) + 500
                f_price = (0.9 * distance) + 1000

                fuel_mult = 5.5
                co2_mult = 2.5

                acheck = 40000
                repair = 25000

            # =========================
            # CONFIG
            # =========================
            y_ratio = y / total_demand
            j_ratio = j / total_demand
            f_ratio = f / total_demand

            y_seats = int(cap * y_ratio * lf)
            j_seats = int(cap * j_ratio * lf)

            f_seats = (
                cap
                - y_seats
                - j_seats
            )

            # =========================
            # INCOME
            # =========================
            income = (
                (y_seats * y_price)
                + (j_seats * j_price)
                + (f_seats * f_price)
            )

            # =========================
            # COST
            # =========================
            fuel = (
                distance
                * float(plane["fuel"])
                * fuel_mult
            )

            co2 = (
                distance
                * co2_mult
            )

            profit = (
                income
                - fuel
                - co2
                - acheck
                - repair
            )

            # =========================
            # TIME
            # =========================
            flight_time = (
                distance
                / float(plane["speed"])
            )

            flights_day = max(
                1,
                int(24 / flight_time)
            )

            # FILTER SHORT ROUTE SPAM
            if flights_day > 18:
                continue

            daily_profit = int(
                profit * flights_day
            )

            ci = int(
                (profit / income) * 100
            ) if income else 0

            results.append((
                dest,
                int(distance),
                daily_profit,
                flights_day,
                ci
            ))

        except:
            continue

    if not results:
        return await ctx.send(
            "No profitable routes found"
        )

    # =========================
    # SORT
    # =========================
    results.sort(
        key=lambda x: x[2],
        reverse=True
    )

    top = results[:5]

    # =========================
    # UI
    # =========================
    text = ""

    for i, r in enumerate(top, start=1):

        dest, dist, profit, trips, ci = r

        text += (
            f"**{i}. {airport} → {dest}**\n"

            f"`Profit` "
            f"${profit:,}/day\n"

            f"`Trips` "
            f"{trips}/day\n"

            f"`CI` "
            f"{ci}%\n"

            f"`Range` "
            f"{dist:,} km\n\n"
        )

    embed = discord.Embed(
        title=f"Best Routes • {plane['name']}",
        description=text,
        color=0x2b2d31
    )

    embed.add_field(
        name="Analysis",
        value=(
            f"`Airport:` {airport}\n"
            f"`Aircraft:` {plane['name']}\n"
            f"`Mode:` {mode.upper()}"
        ),
        inline=False
    )

    embed.set_footer(
        text="JARVIS • Smart Route Optimization"
    )

    # =========================
    # EXPORT
    # =========================
    export_data = {

        "Airport":
        airport,

        "Aircraft":
        plane["name"],

        "Mode":
        mode
    }

    for i, r in enumerate(top, start=1):

        dest, dist, profit, trips, ci = r

        export_data[f"#{i} Route"] = (
            f"{airport}->{dest}"
        )

        export_data[f"#{i} Profit"] = (
            profit
        )

        export_data[f"#{i} Trips"] = (
            trips
        )

        export_data[f"#{i} CI"] = (
            ci
        )

        export_data[f"#{i} Range"] = (
            dist
        )

    export_view = ExportView(export_data)

    await ctx.send(embed=embed)

    await ctx.send(
        "Download Route Report",
        view=export_view
    )
            
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
# =========================
# KEEP ALIVE (ONLY ONCE)
# =========================
keep_alive()

# =========================
# SAFE START (IMPORTANT FIX)
# =========================
if __name__ == "__main__":
    bot.run(TOKEN)
