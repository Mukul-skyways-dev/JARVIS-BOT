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

        # FROM SIDE
        cursor.execute("""
        SELECT f_city, f_country
        FROM routes
        WHERE f_iata = ?
        LIMIT 1
        """, (iata,))

        row = cursor.fetchone()

        # TO SIDE
        if not row:

            cursor.execute("""
            SELECT t_city, t_country
            FROM routes
            WHERE t_iata = ?
            LIMIT 1
            """, (iata,))

            row = cursor.fetchone()

        if row:

            city = row[0]
            country = row[1]

            return f"{iata} — {city}, {country}"

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
# AIRCRAFT VISUAL SYSTEM V3
# CLEAN + STABLE VERSION
# =========================================================

def draw_aircraft_card(
    plane,
    result,
    route,
    frm,
    to
):

    W = 1600
    H = 900

    img = Image.new(
        "RGB",
        (W, H),
        (8, 12, 20)
    )

    draw = ImageDraw.Draw(img)

    # =====================================================
    # BACKGROUND GLOW
    # =====================================================

    glow = Image.new(
        "RGBA",
        (W, H),
        (0, 0, 0, 0)
    )

    gd = ImageDraw.Draw(glow)

    gd.ellipse(
        (-200, -100, 700, 700),
        fill=(0, 170, 255, 70)
    )

    gd.ellipse(
        (1000, 250, 1700, 950),
        fill=(255, 80, 150, 50)
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(140)
    )

    img.paste(glow, (0, 0), glow)

    # =====================================================
    # GLASS PANEL
    # =====================================================

    panel = Image.new(
        "RGBA",
        (1450, 700),
        (255, 255, 255, 22)
    )

    panel = panel.filter(
        ImageFilter.GaussianBlur(2)
    )

    img.paste(
        panel,
        (75, 110),
        panel
    )

    draw.rounded_rectangle(
        (
            75,
            110,
            1525,
            810
        ),
        radius=34,
        outline=(255, 255, 255),
        width=2
    )

    # =====================================================
    # FONTS
    # =====================================================

    try:

        title_font = ImageFont.truetype(
            "arial.ttf",
            42
        )

        text_font = ImageFont.truetype(
            "arial.ttf",
            26
        )

        small_font = ImageFont.truetype(
            "arial.ttf",
            22
        )

    except:

        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # =====================================================
    # HEADER
    # =====================================================

    draw.text(
        (120, 45),
        "JARVIS • Dynamic Aviation Visual System",
        fill=(255, 255, 255),
        font=title_font
    )

    draw.text(
        (120, 95),
        f"{frm.upper()} → {to.upper()}",
        fill=(90, 220, 255),
        font=text_font
    )

    # =====================================================
    # AIRCRAFT VALUES
    # =====================================================

    capacity = max(
        int(float(plane["capacity"])),
        100
    )

    aircraft_range = max(
        int(float(plane["range"])),
        1000
    )

    body_len = min(
        max(
            700,
            700 + int(capacity * 0.15)
        ),
        1050
    )

    body_x = 250
    body_y = 320

    body_h = 120

    # =====================================================
    # FUSELAGE
    # =====================================================

    draw.rounded_rectangle(
        (
            body_x,
            body_y,
            body_x + body_len,
            body_y + body_h
        ),
        radius=60,
        fill=(225, 232, 242)
    )

    # nose
    draw.polygon(
        [
            (
                body_x + body_len,
                body_y + 10
            ),

            (
                body_x + body_len + 120,
                body_y + 60
            ),

            (
                body_x + body_len,
                body_y + 110
            )
        ],
        fill=(225, 232, 242)
    )

    # tail
    draw.polygon(
        [
            (
                body_x + 50,
                body_y
            ),

            (
                body_x - 80,
                body_y - 130
            ),

            (
                body_x + 90,
                body_y
            )
        ],
        fill=(190, 205, 220)
    )

    # =====================================================
    # WINGS
    # =====================================================

    wing_y = body_y + 60

    wing_span = min(
        max(
            240,
            240 + int(aircraft_range / 80)
        ),
        380
    )

    # upper wing
    draw.polygon(
        [
            (
                body_x + 470,
                wing_y
            ),

            (
                body_x + 170,
                wing_y - wing_span
            ),

            (
                body_x + 560,
                wing_y
            )
        ],
        fill=(180, 195, 215)
    )

    # lower wing
    draw.polygon(
        [
            (
                body_x + 470,
                wing_y
            ),

            (
                body_x + 170,
                wing_y + wing_span
            ),

            (
                body_x + 560,
                wing_y
            )
        ],
        fill=(180, 195, 215)
    )

    # =====================================================
    # ENGINES
    # =====================================================

    engine_color = (100, 120, 140)

    # upper
    draw.ellipse(
        (
            body_x + 360,
            wing_y - 160,
            body_x + 430,
            wing_y - 90
        ),
        fill=engine_color
    )

    # lower
    draw.ellipse(
        (
            body_x + 360,
            wing_y + 90,
            body_x + 430,
            wing_y + 160
        ),
        fill=engine_color
    )

    # =====================================================
    # WINDOWS
    # =====================================================

    window_y = body_y + 28

    total_windows = min(
        max(
            int(capacity / 12),
            28
        ),
        48
    )

    spacing = int(
        (body_len - 140) / total_windows
    )

    for i in range(total_windows):

        wx = body_x + 70 + (i * spacing)

        draw.rounded_rectangle(
            (
                wx,
                window_y,
                wx + 12,
                window_y + 12
            ),
            radius=3,
            fill=(70, 190, 255)
        )

    # =====================================================
    # CABIN CLASS BAR
    # =====================================================

    y_seats = max(result["y"], 0)
    j_seats = max(result["j"], 0)
    f_seats = max(result["f"], 0)

    total = max(
        y_seats + j_seats + f_seats,
        1
    )

    cabin_x = body_x + 80
    cabin_y = body_y + 68

    cabin_w = body_len - 160
    cabin_h = 26

    f_w = int((f_seats / total) * cabin_w)
    j_w = int((j_seats / total) * cabin_w)
    y_w = cabin_w - f_w - j_w

    current_x = cabin_x

    # FIRST
    if f_w > 0:

        draw.rounded_rectangle(
            (
                current_x,
                cabin_y,
                current_x + f_w,
                cabin_y + cabin_h
            ),
            radius=10,
            fill=(255, 80, 140)
        )

        current_x += f_w + 4

    # BUSINESS
    if j_w > 0:

        draw.rounded_rectangle(
            (
                current_x,
                cabin_y,
                current_x + j_w,
                cabin_y + cabin_h
            ),
            radius=10,
            fill=(255, 190, 40)
        )

        current_x += j_w + 4

    # ECONOMY
    if y_w > 0:

        draw.rounded_rectangle(
            (
                current_x,
                cabin_y,
                current_x + y_w,
                cabin_y + cabin_h
            ),
            radius=10,
            fill=(60, 200, 255)
        )

    # =====================================================
    # AIRCRAFT NAME
    # =====================================================

    draw.text(
        (
            body_x + 220,
            body_y + 150
        ),
        plane["name"],
        fill=(255, 255, 255),
        font=text_font
    )

    # =====================================================
    # STATS
    # =====================================================

    sx = 120
    sy = 610

    stats = [

        f"Distance        : {int(route['distance']):,} km",
        f"Trips / Day     : {result['trips']}",
        f"Flight Time     : {format_time(result['time'])}",
        f"Daily Profit    : ${result['profit_day']:,}",
        f"Fuel / Day      : ${result['fuel_day']:,}",
        f"CO2 / Day       : ${result['co2_day']:,}",
        f"Confidence Index: {result['ci']}%"
    ]

    for i, line in enumerate(stats):

        draw.text(
            (
                sx,
                sy + i * 36
            ),
            line,
            fill=(255, 255, 255),
            font=text_font
        )

    # =====================================================
    # LEGEND
    # =====================================================

    lx = 1120
    ly = 620

    legend = [

        ("First Class", (255, 80, 140)),
        ("Business", (255, 190, 40)),
        ("Economy", (60, 200, 255))
    ]

    for i, item in enumerate(legend):

        yy = ly + i * 52

        draw.rounded_rectangle(
            (
                lx,
                yy,
                lx + 34,
                yy + 34
            ),
            radius=8,
            fill=item[1]
        )

        draw.text(
            (
                lx + 50,
                yy + 3
            ),
            item[0],
            fill=(255, 255, 255),
            font=small_font
        )

    # =====================================================
    # SAVE
    # =====================================================

    temp = tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False
    )

    img.save(
        temp.name,
        quality=95
    )

    return temp.name


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
# TESTING FUEL DB
# =========================
@bot.command()
async def testfuel(ctx):
    cursor_dyn.execute("SELECT * FROM fuel_data LIMIT 5")
    rows = cursor_dyn.fetchall()

    if not rows:
        await ctx.send("No data found")
        return

    msg = ""
    for r in rows:
        msg += f"{r['day']} | {r['time']} | {r['fuel']} | {r['co2']}\n"

    await ctx.send(f"```{msg}```")

# =========================
# CHANNEL ID 
# =========================
CHANNEL_ID = os.getenv("CHANNEL_ID")
# =========================
# FUEL COMMAND 
# =========================
@bot.command()
async def fuel(ctx):

    try:
        # =========================
        # FETCH LATEST DATA
        # =========================
        cursor_dyn.execute("""
            SELECT fuel, co2
            FROM fuel_data
            ORDER BY id DESC
            LIMIT 12
        """)

        rows = cursor_dyn.fetchall()

        if len(rows) < 4:
            return await ctx.send(
                "❌ Not enough fuel data"
            )

        # =========================
        # DATA LISTS
        # =========================
        fuels = [
            float(r["fuel"])
            for r in rows
        ]

        co2s = [
            float(r["co2"])
            for r in rows
        ]

        # =========================
        # CURRENT VALUES
        # =========================
        current_fuel = fuels[0]
        current_co2 = co2s[0]

        # =========================
        # AVERAGES
        # =========================
        recent_avg = sum(fuels[:4]) / 4
        old_avg = sum(fuels[4:8]) / 4

        movement = recent_avg - old_avg

        # =========================
        # SMART PREDICTION
        # =========================
        predicted = (
            current_fuel
            + (movement * 0.25)
        )

        # smoothing
        predicted = (
            (predicted * 0.6)
            + (recent_avg * 0.4)
        )

        # anti spike protection
        max_change = 120

        if predicted > current_fuel + max_change:
            predicted = current_fuel + max_change

        elif predicted < current_fuel - max_change:
            predicted = current_fuel - max_change

        predicted = int(predicted)

        # =========================
        # CO2 PREDICTION
        # =========================
        recent_co2 = sum(co2s[:4]) / 4
        old_co2 = sum(co2s[4:8]) / 4

        co2_move = recent_co2 - old_co2

        predicted_co2 = (
            current_co2
            + (co2_move * 0.25)
        )

        predicted_co2 = int(
            (predicted_co2 * 0.6)
            + (recent_co2 * 0.4)
        )

        # =========================
        # TREND SYSTEM
        # =========================
        if movement > 40:
            trend = "🔺 Strong Rising"

        elif movement > 10:
            trend = "🟧 Rising"

        elif movement < -40:
            trend = "🔻 Strong Falling"

        elif movement < -10:
            trend = "🟦 Falling"

        else:
            trend = "➡ Stable"

        # =========================
        # VOLATILITY
        # =========================
        volatility = int(
            max(fuels[:6])
            - min(fuels[:6])
        )

        # =========================
        # EMBED
        # =========================
        embed = discord.Embed(
            title="⛽ Smart Fuel Prediction",
            color=0x0A1AFF
        )

        embed.add_field(
            name="Current Fuel",
            value=f"${int(current_fuel):,}",
            inline=True
        )

        embed.add_field(
            name="Predicted Fuel",
            value=f"${predicted:,}",
            inline=True
        )

        embed.add_field(
            name="Trend",
            value=trend,
            inline=True
        )

        embed.add_field(
            name="Current CO2",
            value=f"${int(current_co2):,}",
            inline=True
        )

        embed.add_field(
            name="Predicted CO2",
            value=f"${predicted_co2:,}",
            inline=True
        )

        embed.add_field(
            name="Volatility",
            value=f"{volatility}",
            inline=True
        )

        embed.set_footer(
            text="JARVIS • Smart Fuel Analytics"
        )

        await ctx.send(embed=embed)

    except Exception as e:

        await ctx.send(
            f"❌ Fuel system error:\n```{e}```"
        )

# =========================
# AUTO ALERT LOOP
# =========================
async def fuel_alert_loop():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)

    last_sent = None

    while not bot.is_closed():
        cursor_dyn.execute("""
            SELECT fuel FROM fuel_data 
            ORDER BY day DESC, time DESC 
            LIMIT 5
        """)
        rows = cursor_dyn.fetchall()

        fuels = [r["fuel"] for r in rows]
        avg = sum(fuels) / len(fuels)
        current = fuels[0]

        msg = None
        if current < avg - 100:
            msg = f"🟢 Fuel Low Alert: {current}"
        elif current > avg + 100:
            msg = f"🔴 Fuel High Alert: {current}"

        if msg and msg != last_sent and channel:
            await channel.send(msg)
            last_sent = msg

        await asyncio.sleep(1800)  # 30 min


# =========================
# DAILY FORECAST
# =========================
async def daily_forecast():
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)

    IST = pytz.timezone("Asia/Kolkata")

    while not bot.is_closed():
        now = datetime.now(IST)

        if now.hour == 0 and now.minute == 0:
            cursor_dyn.execute("""
                SELECT fuel FROM fuel_data 
                ORDER BY day DESC, time DESC 
                LIMIT 24
            """)
            rows = cursor_dyn.fetchall()

            fuels = [r["fuel"] for r in rows]
            avg = sum(fuels) / len(fuels)

            embed = discord.Embed(
                title="🌙 24h Fuel Forecast",
                description=f"Expected Avg Fuel: {int(avg)}",
                color=0x0A1AFF
            )

            if channel:
                await channel.send(embed=embed)

            await asyncio.sleep(60)

        await asyncio.sleep(30)


# =========================
# GRAPH COMMAND
# =========================
@bot.command()
async def fuelgraph(ctx):
    cursor_dyn.execute("""
        SELECT fuel FROM fuel_data 
        ORDER BY day DESC, time DESC 
        LIMIT 10
    """)
    rows = cursor_dyn.fetchall()

    fuels = [r["fuel"] for r in rows][::-1]

    plt.figure()
    plt.plot(fuels)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    await ctx.send(file=discord.File(buf, "fuel.png"))

# ================= STS - DB (USE EXISTING conn_dyn) =================
cursor_dyn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT)")
cursor_dyn.execute("CREATE TABLE IF NOT EXISTS shares (user_id TEXT, value REAL, date TEXT, window_id TEXT)")
cursor_dyn.execute("""CREATE TABLE IF NOT EXISTS activity (
user_id TEXT PRIMARY KEY,
total INT DEFAULT 0, attended INT DEFAULT 0, missed INT DEFAULT 0,
streak INT DEFAULT 0, last_window TEXT, miss_streak INT DEFAULT 0)""")
conn_dyn.commit()


# ================= GLOBAL =================
current_window = {"id": None, "open_time": None}


# ================= UI SYSTEM =================
class UI:

    @staticmethod
    def embed(title, desc="", color=0x0A1AFF):
        e = discord.Embed(title=title, description=desc, color=color)
        e.set_footer(text="JARVIS • AM4 System")
        return e

    # 🔥 matplotlib graph (UPGRADE)
    @staticmethod
    def graph_image(data):
        if not data:
            return None

        plt.figure()
        plt.plot(data)

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    # keep same logic but cleaner UI
    @staticmethod
    def vertical_compare(v1, v2, name1, name2):
        maxv = max(v1, v2) or 1
        h1 = int((v1/maxv)*10)
        h2 = int((v2/maxv)*10)

        lines = ""
        for lvl in range(10,0,-1):
            col1 = "🟩" if h1>=lvl else "⬛"
            col2 = "🟦" if h2>=lvl else "⬛"
            lines += f"{col1}   {col2}\n"

        lines += "—"*10 + "\n"
        lines += f"{name1[:3]}   {name2[:3]}"

        return f"```{lines}```"


# ================= HELPERS =================
def now(): return datetime.now()
def window_id(): return now().date().isoformat()
def money(x): return f"${x:,.2f}"

def parse(v):
    try:
        v=v.lower().replace(",","").strip()
        if "b" in v: return float(v.replace("b",""))*1e9
        if "m" in v: return float(v.replace("m",""))*1e6
        return float(v)
    except:
        return None


# ================= REGISTER =================
async def register(user):
    uid=str(user.id)
    cursor_dyn.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not cursor_dyn.fetchone():
        cursor_dyn.execute("INSERT INTO users VALUES (?,?)",(uid,str(user)))
        cursor_dyn.execute("INSERT INTO activity VALUES (?,0,0,0,0,NULL,0)",(uid,))
        conn_dyn.commit()


# ================= MODAL =================
class ShareModal(Modal, title="Submit Value 🚀"):
    value = TextInput(label="Enter Value")

    async def on_submit(self, interaction):
        val = parse(self.value.value)
        if val is None or val<=0:
            return await interaction.response.send_message("Invalid value",ephemeral=True)

        uid=str(interaction.user.id)
        await register(interaction.user)

        cursor_dyn.execute("SELECT * FROM shares WHERE user_id=? AND window_id=?", (uid,current_window["id"]))
        if cursor_dyn.fetchone():
            return await interaction.response.send_message("Already submitted",ephemeral=True)

        cursor_dyn.execute("INSERT INTO shares VALUES (?,?,?,?)",(uid,val,now().isoformat(),current_window["id"]))
        cursor_dyn.execute("""UPDATE activity SET attended=attended+1,total=total+1,
        streak=streak+1,miss_streak=0,last_window=? WHERE user_id=?""",(current_window["id"],uid))
        conn_dyn.commit()

        await interaction.response.send_message(f"✅ Submitted {money(val)}",ephemeral=True)


# ================= VIEW =================
class ShareView(View):
    @discord.ui.button(label="Submit Value",style=discord.ButtonStyle.green)
    async def submit(self,interaction,button):
        if not current_window["id"]:
            return await interaction.response.send_message("Window closed",ephemeral=True)
        await interaction.response.send_modal(ShareModal())


# ================= ADMIN =================
class AdminPanel(View):

    async def interaction_check(self, interaction):
        return interaction.guild and interaction.user.guild_permissions.manage_guild

    @discord.ui.button(label="Open Window",style=discord.ButtonStyle.green)
    async def open_w(self,interaction,button):
        current_window["id"]=window_id()
        current_window["open_time"]=now()

        ch=bot.get_channel(CHANNEL_ID)
        if ch:
            await ch.send(embed=UI.embed("📢 Window Open"),view=ShareView())

        await interaction.response.send_message("Opened")

    @discord.ui.button(label="Close Window",style=discord.ButtonStyle.red)
    async def close_w(self,interaction,button):
        current_window["id"]=None
        current_window["open_time"]=None
        await interaction.response.send_message("Closed")

    @discord.ui.button(label="Today Data",style=discord.ButtonStyle.blurple)
    async def today(self,interaction,button):
        data=cursor_dyn.execute("SELECT user_id,value FROM shares WHERE window_id=?", (window_id(),)).fetchall()
        txt="\n".join([f"<@{u}> → {money(v)}" for u,v in data]) or "No data"
        await interaction.response.send_message(embed=UI.embed("📊 Today Data",txt))

    @discord.ui.button(label="Reset Today",style=discord.ButtonStyle.gray)
    async def reset(self,interaction,button):
        cursor_dyn.execute("DELETE FROM shares WHERE window_id=?", (window_id(),))
        conn_dyn.commit()
        await interaction.response.send_message("Reset done")


# ================= COMMAND =================
@bot.command(aliases=["admin"])
async def panel(ctx):
    if not ctx.guild:
        return await ctx.send("Server only")
    if not ctx.author.guild_permissions.manage_guild:
        return await ctx.send("Admin only")

    await ctx.send(embed=UI.embed("⚙ Control Panel"),view=AdminPanel())

# ================= GRAPH =================
@bot.command()
async def graph(ctx, member: discord.User=None):
    member = member or ctx.author
    await register(member)

    uid = str(member.id)

    data = [x["value"] for x in cursor_dyn.execute(
        "SELECT value FROM shares WHERE user_id=? ORDER BY date", (uid,)
    ).fetchall()]

    if not data:
        return await ctx.send("No data")

    avg = sum(data)/len(data)
    mx = max(data)
    mn = min(data)

    # 🔥 matplotlib dark blue graph
    plt.figure()
    plt.plot(data)
    plt.gca().set_facecolor("#0A1AFF")
    plt.gcf().patch.set_facecolor("#0A1AFF")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    embed = UI.embed(f"📊 Full Growth - {member}")
    embed.add_field(name="Average", value=money(avg))
    embed.add_field(name="High", value=money(mx))
    embed.add_field(name="Low", value=money(mn))
    embed.add_field(name="Total Entries", value=str(len(data)))

    await ctx.send(embed=embed, file=discord.File(buf, "graph.png"))


# ================= COMPARE =================
@bot.command()
async def compareplayer(ctx, a: discord.User, b: discord.User):

    d1 = [x["value"] for x in cursor_dyn.execute(
        "SELECT value FROM shares WHERE user_id=?", (str(a.id),)
    ).fetchall()]

    d2 = [x["value"] for x in cursor_dyn.execute(
        "SELECT value FROM shares WHERE user_id=?", (str(b.id),)
    ).fetchall()]

    if not d1 or not d2:
        return await ctx.send("Not enough data")

    avg1 = sum(d1)/len(d1)
    avg2 = sum(d2)/len(d2)

    # 🔥 matplotlib vertical bar (dark blue)
    labels = [a.name, b.name]
    values = [avg1, avg2]

    plt.figure()
    bars = plt.bar(labels, values)

    plt.gca().set_facecolor("#0A1AFF")
    plt.gcf().patch.set_facecolor("#0A1AFF")

    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2, h, int(h),
                 ha='center', va='bottom')

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    winner = a if avg1 > avg2 else b

    embed = UI.embed("⚔ Player Comparison")
    embed.add_field(name=a.name, value=f"Avg: {money(avg1)}\nEntries: {len(d1)}")
    embed.add_field(name=b.name, value=f"Avg: {money(avg2)}\nEntries: {len(d2)}")
    embed.add_field(name="Winner", value=winner.mention, inline=False)

    await ctx.send(embed=embed, file=discord.File(buf, "compareplayer.png"))


# ================= STATS =================
@bot.command()
async def stats(ctx, member: discord.User=None):
    member = member or ctx.author
    await register(member)

    uid = str(member.id)

    latest = cursor_dyn.execute(
        "SELECT value FROM shares WHERE user_id=? ORDER BY date DESC LIMIT 1", (uid,)
    ).fetchone()

    act = cursor_dyn.execute(
        "SELECT total,attended,missed,streak FROM activity WHERE user_id=?", (uid,)
    ).fetchone()

    if not latest or not act:
        return await ctx.send("No data")

    total, attended, missed, streak = act
    cons = (attended/total*100) if total else 0

    embed = UI.embed(f"📊 Detailed Stats - {member}")
    embed.add_field(name="Latest", value=money(latest["value"]))
    embed.add_field(name="Consistency", value=f"{cons:.1f}%")
    embed.add_field(name="Rank", value=rank(cons))
    embed.add_field(name="Streak", value=streak)
    embed.add_field(name="Missed", value=missed)
    embed.add_field(name="Total Entries", value=total)

    await ctx.send(embed=embed)


# ================= LEADERBOARD (Share rank) =================
@bot.command()
async def shareboard (ctx):

    data = cursor_dyn.execute("""
    SELECT users.username, AVG(shares.value) as avg_val
    FROM shares JOIN users ON users.user_id=shares.user_id
    GROUP BY shares.user_id ORDER BY avg_val DESC LIMIT 5
    """).fetchall()

    txt = "\n".join([f"{i+1}. {u} → {money(v)}" for i,(u,v) in enumerate(
        [(r["username"], r["avg_val"]) for r in data]
    )])

    await ctx.send(embed=UI.embed("🏆 Leaderboard", txt))

# =========================
# START TASKS
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.loop.create_task(fuel_alert_loop())
    bot.loop.create_task(daily_forecast())

# =========================
# AI COMMAND 
# =========================
@bot.command()
async def ask(ctx, *, question):

    msg = await ctx.send("🧠 Thinking...")

    try:
        response = groq.chat.completions.create(
            model="llama-3.3-70b-versatile",

            messages=[
                {
                    "role": "system",
                    "content": """
                    You are JARVIS, an advanced AM4 aviation intelligence assistant.

                    Your main expertise:
                    - Airline Manager 4
                    - routes
                    - fuel strategy
                    - aircraft comparison
                    - airline growth
                    - alliance systems
                    - aviation analytics

                    You also casually chat naturally like a smart AI assistant.

                    Keep responses clean, smart, and helpful.
                    """
                },

                {
                    "role": "user",
                    "content": question
                }
            ],

            temperature=0.7,
            max_tokens=700
        )

        reply = response.choices[0].message.content

        await msg.edit(content=reply[:2000])

    except Exception as e:
        await msg.edit(content=f"❌ AI Error:\n```{e}```")

# =========================================================
# JARVIS ALLIANCE ANALYTICS SYSTEM
# FULL PRODUCTION MODULE
# SQLITE + DISCORD.PY
# =========================================================

import os
import io
import math
import random
import string
import sqlite3
import datetime
import tempfile

import discord
import matplotlib.pyplot as plt

from discord.ext import commands
from discord.ui import (
    View,
    Button,
    Modal,
    TextInput
)

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageFilter
)

# =========================================================
# DATABASE
# =========================================================

alliance_db = sqlite3.connect(
    "new_am4.db"
)

alliance_db.row_factory = sqlite3.Row

alliance_cursor = alliance_db.cursor()

# =========================================================
# CREATE TABLES
# =========================================================

alliance_cursor.execute("""

CREATE TABLE IF NOT EXISTS alliances (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    alliance_name TEXT UNIQUE,
    alliance_code TEXT UNIQUE,

    registered_rank INTEGER,

    logo_url TEXT,

    created_at TEXT
)

""")

alliance_cursor.execute("""

CREATE TABLE IF NOT EXISTS alliance_daily (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    alliance_code TEXT,

    entry_date TEXT,

    current_value REAL,

    total_members TEXT,

    season_won INTEGER,

    total_flights INTEGER,

    current_rank INTEGER
)

""")

alliance_db.commit()

# =========================================================
# AUTHORIZED ROLE
# =========================================================

AUTHORIZED_ROLE = "ALLIANCE ADM"

# =========================================================
# ROLE CHECK
# =========================================================

def has_alliance_permission(member):

    if member.guild_permissions.administrator:
        return True

    for role in member.roles:

        if role.name == AUTHORIZED_ROLE:
            return True

    return False

# =========================================================
# GENERATE CODE
# =========================================================

def generate_alliance_code():

    chars = string.ascii_uppercase + string.digits

    return "".join(
        random.choice(chars)
        for _ in range(5)
    )

# =========================================================
# CALCULATE GROWTH
# =========================================================

def calculate_growth(entries):

    if len(entries) < 2:
        return 0

    first = entries[0]["current_value"]
    last = entries[-1]["current_value"]

    if first <= 0:
        return 0

    growth = (
        (last - first) / first
    ) * 100

    return round(growth, 2)

# =========================================================
# CALCULATE SCORE
# =========================================================

def calculate_score(entry):

    value_score = entry["current_value"] / 1000000000

    rank_score = (
        200 - entry["current_rank"]
    ) * 4

    season_score = (
        entry["season_won"] * 150
    )

    flights_score = (
        entry["total_flights"] / 100000
    )

    final_score = (

        value_score
        + rank_score
        + season_score
        + flights_score
    )

    return round(final_score, 2)

# =========================================================
# PREDICTION ENGINE
# =========================================================

def predict_rank(entries):

    if len(entries) < 3:
        return "Insufficient Data"

    latest = entries[-1]

    growth = calculate_growth(entries)

    current_rank = latest["current_rank"]

    predicted = max(

        1,

        int(
            current_rank
            - (growth / 3)
        )
    )

    return predicted

# =========================================================
# GRAPH GENERATOR
# =========================================================

def create_growth_graph(entries, alliance_name):

    dates = []
    values = []

    for e in entries[-5:]:

        dates.append(
            e["entry_date"][5:]
        )

        values.append(
            e["current_value"] / 1000000000
        )

    plt.figure(
        figsize=(8, 4)
    )

    ax = plt.gca()

    ax.set_facecolor("#202225")

    plt.plot(
        dates,
        values,
        linewidth=3
    )

    plt.title(
        f"{alliance_name} Growth"
    )

    plt.xlabel("Date")
    plt.ylabel("Value (B)")

    plt.grid(True)

    temp = tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False
    )

    plt.savefig(
        temp.name,
        bbox_inches="tight",
        transparent=False
    )

    plt.close()

    return temp.name

# =========================================================
# EXPORT VIEW
# =========================================================

class AllianceExportView(View):

    def __init__(

        self,
        alliance_name,
        latest,
        growth,
        prediction

    ):

        super().__init__(
            timeout=120
        )

        self.alliance_name = alliance_name
        self.latest = latest
        self.growth = growth
        self.prediction = prediction

    @discord.ui.button(
        label="Export",
        style=discord.ButtonStyle.secondary
    )
    async def export_btn(

        self,
        interaction,
        button

    ):

        text = f"""

ALLIANCE REPORT

Alliance:
{self.alliance_name}

Value:
{self.latest['current_value']:,}

Rank:
#{self.latest['current_rank']}

Growth:
{self.growth}%

Prediction:
#{self.prediction}

Flights:
{self.latest['total_flights']:,}

Members:
{self.latest['total_members']}

"""

        file = discord.File(

            io.BytesIO(
                text.encode()
            ),

            filename="alliance_report.txt"
        )

        await interaction.response.send_message(

            file=file,

            ephemeral=True
        )

# =========================================================
# REGISTER MODAL
# =========================================================

class AllianceRegisterModal(Modal):

    def __init__(self):

        super().__init__(
            title="Register Alliance"
        )

        self.name = TextInput(
            label="Alliance Name",
            required=True
        )

        self.rank = TextInput(
            label="Current Ingame Rank",
            required=True
        )

        self.add_item(self.name)
        self.add_item(self.rank)

    async def on_submit(

        self,
        interaction

    ):

        if not has_alliance_permission(
            interaction.user
        ):

            return await interaction.response.send_message(

                "Unauthorized",

                ephemeral=True
            )

        alliance_cursor.execute(
            """
            SELECT *
            FROM alliances
            WHERE alliance_name = ?
            """,
            (
                self.name.value,
            )
        )

        exists = alliance_cursor.fetchone()

        if exists:

            return await interaction.response.send_message(

                "Alliance already exists",

                ephemeral=True
            )

        code = generate_alliance_code()

        alliance_cursor.execute(
            """

            INSERT INTO alliances (

                alliance_name,
                alliance_code,
                registered_rank,
                created_at

            )

            VALUES (?, ?, ?, ?)

            """,
            (

                self.name.value,

                code,

                int(self.rank.value),

                str(
                    datetime.date.today()
                )
            )
        )

        alliance_db.commit()

        await interaction.response.send_message(

            f"Alliance Registered\nCode: {code}",

            ephemeral=True
        )

# =========================================================
# DAILY ENTRY MODAL
# =========================================================

class DailyEntryModal(Modal):

    def __init__(self):

        super().__init__(
            title="Daily Alliance Entry"
        )

        self.code = TextInput(
            label="Alliance Code",
            required=True
        )

        self.value = TextInput(
            label="Current Value",
            required=True
        )

        self.members = TextInput(
            label="Members (43/60)",
            required=True
        )

        self.season = TextInput(
            label="Season Won",
            required=True
        )

        self.flights = TextInput(
            label="Total Flights",
            required=True
        )

        self.rank = TextInput(
            label="Current Rank",
            required=True
        )

        self.add_item(self.code)
        self.add_item(self.value)
        self.add_item(self.members)
        self.add_item(self.season)
        self.add_item(self.flights)
        self.add_item(self.rank)

    async def on_submit(

        self,
        interaction

    ):

        if not has_alliance_permission(
            interaction.user
        ):

            return await interaction.response.send_message(

                "Unauthorized",

                ephemeral=True
            )

        today = str(
            datetime.date.today()
        )

        alliance_cursor.execute(
            """
            SELECT *
            FROM alliance_daily
            WHERE alliance_code = ?
            AND entry_date = ?
            """,
            (
                self.code.value.upper(),
                today
            )
        )

        exists = alliance_cursor.fetchone()

        if exists:

            return await interaction.response.send_message(

                "Today's entry already exists",

                ephemeral=True
            )

        alliance_cursor.execute(
            """

            INSERT INTO alliance_daily (

                alliance_code,
                entry_date,

                current_value,
                total_members,

                season_won,
                total_flights,

                current_rank

            )

            VALUES (?, ?, ?, ?, ?, ?, ?)

            """,
            (

                self.code.value.upper(),

                today,

                float(self.value.value),

                self.members.value,

                int(self.season.value),

                int(self.flights.value),

                int(self.rank.value)
            )
        )

        alliance_db.commit()

        await interaction.response.send_message(

            "Daily entry saved",

            ephemeral=True
        )

# =========================================================
# DELETE ENTRY MODAL
# =========================================================

class DeleteEntryModal(Modal):

    def __init__(self):

        super().__init__(
            title="Delete Entry"
        )

        self.code = TextInput(
            label="Alliance Code"
        )

        self.date = TextInput(
            label="Date YYYY-MM-DD"
        )

        self.add_item(self.code)
        self.add_item(self.date)

    async def on_submit(

        self,
        interaction

    ):

        if not has_alliance_permission(
            interaction.user
        ):

            return await interaction.response.send_message(

                "Unauthorized",

                ephemeral=True
            )

        alliance_cursor.execute(
            """
            DELETE FROM alliance_daily
            WHERE alliance_code = ?
            AND entry_date = ?
            """,
            (
                self.code.value.upper(),
                self.date.value
            )
        )

        alliance_db.commit()

        await interaction.response.send_message(

            "Entry deleted",

            ephemeral=True
        )

# =========================================================
# EDIT ENTRY MODAL
# =========================================================

class EditEntryModal(Modal):

    def __init__(self):

        super().__init__(
            title="Edit Entry"
        )

        self.code = TextInput(
            label="Alliance Code"
        )

        self.date = TextInput(
            label="Date YYYY-MM-DD"
        )

        self.value = TextInput(
            label="New Value"
        )

        self.rank = TextInput(
            label="New Rank"
        )

        self.flights = TextInput(
            label="New Flights"
        )

        self.add_item(self.code)
        self.add_item(self.date)
        self.add_item(self.value)
        self.add_item(self.rank)
        self.add_item(self.flights)

    async def on_submit(

        self,
        interaction

    ):

        if not has_alliance_permission(
            interaction.user
        ):

            return await interaction.response.send_message(

                "Unauthorized",

                ephemeral=True
            )

        alliance_cursor.execute(
            """

            UPDATE alliance_daily

            SET

            current_value = ?,
            current_rank = ?,
            total_flights = ?

            WHERE alliance_code = ?
            AND entry_date = ?

            """,
            (

                float(self.value.value),

                int(self.rank.value),

                int(self.flights.value),

                self.code.value.upper(),

                self.date.value
            )
        )

        alliance_db.commit()

        await interaction.response.send_message(

            "Entry updated",

            ephemeral=True
        )

# =========================================================
# MAIN DASHBOARD VIEW
# =========================================================

class AllianceMainView(View):

    def __init__(self):

        super().__init__(
            timeout=300
        )

    @discord.ui.button(
        label="Register",
        style=discord.ButtonStyle.primary
    )
    async def register_btn(

        self,
        interaction,
        button

    ):

        await interaction.response.send_modal(
            AllianceRegisterModal()
        )

    @discord.ui.button(
        label="Daily Entry",
        style=discord.ButtonStyle.success
    )
    async def daily_btn(

        self,
        interaction,
        button

    ):

        await interaction.response.send_modal(
            DailyEntryModal()
        )

    @discord.ui.button(
        label="Edit Entry",
        style=discord.ButtonStyle.secondary
    )
    async def edit_btn(

        self,
        interaction,
        button

    ):

        await interaction.response.send_modal(
            EditEntryModal()
        )

    @discord.ui.button(
        label="Delete Entry",
        style=discord.ButtonStyle.danger
    )
    async def delete_btn(

        self,
        interaction,
        button

    ):

        await interaction.response.send_modal(
            DeleteEntryModal()
        )

# =========================================================
# MAIN MENU COMMAND
# =========================================================

@bot.command()
async def alliance_menu(ctx):

    embed = discord.Embed(

        title="Alliance Analytics System",

        description=(
            "Production Alliance Management Dashboard"
        ),

        color=0x2b2d31
    )

    await ctx.send(

        embed=embed,

        view=AllianceMainView()
    )

# =========================================================
# SINGLE ALLIANCE DASHBOARD
# =========================================================

@bot.command()
async def alliance(ctx, code):

    alliance_cursor.execute(
        """
        SELECT *
        FROM alliances
        WHERE alliance_code = ?
        """,
        (
            code.upper(),
        )
    )

    alliance = alliance_cursor.fetchone()

    if not alliance:

        return await ctx.send(
            "Alliance not found"
        )

    alliance_cursor.execute(
        """
        SELECT *
        FROM alliance_daily
        WHERE alliance_code = ?
        ORDER BY entry_date ASC
        """,
        (
            code.upper(),
        )
    )

    entries = alliance_cursor.fetchall()

    if not entries:

        return await ctx.send(
            "No entries available"
        )

    latest = entries[-1]

    growth = calculate_growth(entries)

    prediction = predict_rank(entries)

    score = calculate_score(latest)

    trend = "↑"

    if growth < 0:
        trend = "↓"

    graph_path = create_growth_graph(
        entries,
        alliance["alliance_name"]
    )

    graph_file = discord.File(
        graph_path,
        filename="graph.png"
    )

    embed = discord.Embed(

        title=alliance["alliance_name"],

        color=0x2b2d31
    )

    if alliance["logo_url"]:

        embed.set_thumbnail(
            url=alliance["logo_url"]
        )

    embed.add_field(

        name="Current Status",

        value=(

            f"Value: ${latest['current_value']:,}\n"
            f"Rank: #{latest['current_rank']}\n"
            f"Members: {latest['total_members']}\n"
            f"Flights: {latest['total_flights']:,}\n"
            f"Season Won: {latest['season_won']}"
        ),

        inline=False
    )

    embed.add_field(

        name="Analytics",

        value=(

            f"Growth: {trend} {growth}%\n"
            f"Prediction: #{prediction}\n"
            f"Bot Score: {score}"
        ),

        inline=False
    )

    suggestion = "Stable"

    if growth > 15:
        suggestion = "High Momentum"

    elif growth < 0:
        suggestion = "Needs Recovery"

    embed.add_field(

        name="Suggestion",

        value=suggestion,

        inline=False
    )

    embed.set_image(
        url="attachment://graph.png"
    )

    await ctx.send(

        embed=embed,

        file=graph_file,

        view=AllianceExportView(

            alliance["alliance_name"],
            latest,
            growth,
            prediction
        )
    )

# =========================================================
# GLOBAL RANKING
# =========================================================

@bot.command()
async def alliance_rankings(ctx):

    alliance_cursor.execute(
        """
        SELECT *
        FROM alliances
        """
    )

    alliances = alliance_cursor.fetchall()

    ranking_data = []

    for a in alliances:

        alliance_cursor.execute(
            """
            SELECT *
            FROM alliance_daily
            WHERE alliance_code = ?
            ORDER BY entry_date ASC
            """,
            (
                a["alliance_code"],
            )
        )

        entries = alliance_cursor.fetchall()

        if not entries:
            continue

        latest = entries[-1]

        score = calculate_score(
            latest
        )

        growth = calculate_growth(
            entries
        )

        ranking_data.append(

            (

                score,
                a,
                latest,
                growth
            )
        )

    ranking_data.sort(
        reverse=True,
        key=lambda x: x[0]
    )

    embed = discord.Embed(

        title="Global Alliance Rankings",

        color=0x2b2d31
    )

    text = ""

    for i, data in enumerate(ranking_data[:15]):

        score, a, latest, growth = data

        arrow = "↑"

        if growth < 0:
            arrow = "↓"

        text += (

            f"#{i+1} "
            f"{a['alliance_name']}\n"

            f"Rank #{latest['current_rank']} • "
            f"{arrow} {growth}%\n\n"
        )

    embed.description = text

    await ctx.send(embed=embed)

# =========================================================
# ALLIANCE COMPARE
# =========================================================

@bot.command()
async def alliance_compare(

    ctx,
    code1,
    code2

):

    def fetch(code):

        alliance_cursor.execute(
            """
            SELECT *
            FROM alliances
            WHERE alliance_code = ?
            """,
            (
                code.upper(),
            )
        )

        a = alliance_cursor.fetchone()

        alliance_cursor.execute(
            """
            SELECT *
            FROM alliance_daily
            WHERE alliance_code = ?
            ORDER BY entry_date ASC
            """,
            (
                code.upper(),
            )
        )

        entries = alliance_cursor.fetchall()

        if not a or not entries:
            return None

        latest = entries[-1]

        growth = calculate_growth(entries)

        score = calculate_score(latest)

        return (
            a,
            latest,
            growth,
            score
        )

    A = fetch(code1)
    B = fetch(code2)

    if not A or not B:

        return await ctx.send(
            "Alliance not found"
        )

    embed = discord.Embed(

        title="Alliance Comparison",

        color=0x2b2d31
    )

    embed.add_field(

        name=A[0]["alliance_name"],

        value=(

            f"Rank: #{A[1]['current_rank']}\n"
            f"Growth: {A[2]}%\n"
            f"Score: {A[3]}"
        ),

        inline=True
    )

    embed.add_field(

        name=B[0]["alliance_name"],

        value=(

            f"Rank: #{B[1]['current_rank']}\n"
            f"Growth: {B[2]}%\n"
            f"Score: {B[3]}"
        ),

        inline=True
    )

    await ctx.send(embed=embed)

# =========================================================
# LOGO COMMAND
# =========================================================

@bot.command()
async def alliance_logo(

    ctx,
    code,
    url

):

    if not has_alliance_permission(
        ctx.author
    ):

        return await ctx.send(
            "Unauthorized"
        )

    alliance_cursor.execute(
        """
        UPDATE alliances
        SET logo_url = ?
        WHERE alliance_code = ?
        """,
        (
            url,
            code.upper()
        )
    )

    alliance_db.commit()

    await ctx.send(
        "Logo updated"
    )
# =========================================================
# PAGINATION VIEW
# =========================================================

class AllianceRankingView(View):

    def __init__(self, data, season_name):

        super().__init__(timeout=300)

        self.data = data
        self.page = 0
        self.per_page = 5
        self.season_name = season_name

    def total_pages(self):

        return math.ceil(
            len(self.data) / self.per_page
        )

    def get_page_data(self):

        start = self.page * self.per_page
        end = start + self.per_page

        return self.data[start:end]

    def build_embed(self):

        embed = discord.Embed(
            title=f"Alliance Global Rankings • {self.season_name}",
            color=0x1e1f22
        )

        embed.description = (
            "Dynamic ranking system based on:\n"
            "Growth • Value • Flights • Stability • Seasons"
        )

        page_data = self.get_page_data()

        for idx, row in enumerate(page_data):

            global_rank = (
                self.page * self.per_page
            ) + idx + 1

            trend = "▲" if row["movement"] > 0 else (
                "▼" if row["movement"] < 0 else "▬"
            )

            movement_text = (
                f"{trend} {abs(row['movement'])}"
            )

            value_text = (
                f"${int(row['current_value']):,}"
            )

            growth_text = (
                f"{row['growth_rate']:.2f}%"
            )

            embed.add_field(
                name=(
                    f"#{global_rank} • "
                    f"{row['alliance_name']}"
                ),
                value=(
                    f"Bot Score: "
                    f"`{row['bot_score']}`\n"

                    f"Growth: "
                    f"`{growth_text}`\n"

                    f"Movement: "
                    f"`{movement_text}`\n"

                    f"Current Rank: "
                    f"`#{row['rank']}`\n"

                    f"Value: "
                    f"`{value_text}`\n"

                    f"Members: "
                    f"`{row['members']}`\n"

                    f"Seasons: "
                    f"`{row['season_won']}`"
                ),
                inline=False
            )

        embed.set_footer(
            text=(
                f"Page "
                f"{self.page + 1}/"
                f"{self.total_pages()}"
            )
        )

        return embed

    async def update_buttons(self):

        self.prev_button.disabled = (
            self.page <= 0
        )

        self.next_button.disabled = (
            self.page >= self.total_pages() - 1
        )

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary
    )
    async def prev_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        self.page -= 1

        await self.update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary
    )
    async def next_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        self.page += 1

        await self.update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

# =========================================================
# RANKING SCORE ENGINE
# =========================================================

def calculate_bot_score(entry):

    try:

        value_score = (
            float(entry["current_value"]) / 1_000_000
        )

        flight_score = (
            float(entry["total_flights"]) / 1000
        )

        member_score = (
            int(
                str(entry["members"]).split("/")[0]
            ) * 2
        )

        season_score = (
            int(entry["season_won"]) * 15
        )

        growth_score = (
            float(entry["growth_rate"]) * 4
        )

        rank_bonus = (
            max(
                0,
                100 - int(entry["rank"])
            )
        )

        final_score = (
            value_score +
            flight_score +
            member_score +
            season_score +
            growth_score +
            rank_bonus
        )

        return round(final_score, 2)

    except:
        return 0

# =========================================================
# GROWTH CALCULATOR
# =========================================================

def calculate_growth_rate(entries):

    try:

        if len(entries) < 2:
            return 0

        first = float(
            entries[0]["current_value"]
        )

        latest = float(
            entries[-1]["current_value"]
        )

        if first <= 0:
            return 0

        growth = (
            ((latest - first) / first) * 100
        )

        return round(growth, 2)

    except:
        return 0

# =========================================================
# RANK MOVEMENT
# =========================================================

def calculate_rank_movement(entries):

    try:

        if len(entries) < 2:
            return 0

        old_rank = int(entries[-2]["rank"])
        new_rank = int(entries[-1]["rank"])

        if new_rank < old_rank:
            return old_rank - new_rank

        elif new_rank > old_rank:
            return -(new_rank - old_rank)

        return 0

    except:
        return 0

# =========================================================
# RANK PREDICTION
# =========================================================

def predict_future_rank(entries):

    try:

        latest = int(entries[-1]["rank"])

        growth = calculate_growth_rate(
            entries
        )

        prediction = latest

        if growth >= 15:
            prediction -= 3

        elif growth >= 8:
            prediction -= 2

        elif growth >= 3:
            prediction -= 1

        elif growth <= -10:
            prediction += 3

        elif growth <= -5:
            prediction += 2

        return max(prediction, 1)

    except:
        return "N/A"

# =========================================================
# FETCH ALLIANCE FULL DATA
# =========================================================

def fetch_alliance_history(code):

    cursor.execute("""
    SELECT *
    FROM alliance_daily_logs
    WHERE alliance_code = ?
    ORDER BY entry_date ASC
    """, (code,))

    rows = cursor.fetchall()

    return rows

# =========================================================
# GLOBAL RANKING DATA BUILDER
# =========================================================

def build_global_rankings():

    cursor.execute("""
    SELECT *
    FROM alliance_registry
    """)

    alliances = cursor.fetchall()

    final_data = []

    for a in alliances:

        code = a["alliance_code"]

        history = fetch_alliance_history(
            code
        )

        if not history:
            continue

        latest = history[-1]

        growth_rate = calculate_growth_rate(
            history
        )

        movement = calculate_rank_movement(
            history
        )

        prediction = predict_future_rank(
            history
        )

        bot_score = calculate_bot_score({

            "current_value":
            latest["current_value"],

            "total_flights":
            latest["total_flights"],

            "members":
            latest["members"],

            "season_won":
            latest["season_won"],

            "growth_rate":
            growth_rate,

            "rank":
            latest["rank"]
        })

        final_data.append({

            "alliance_name":
            a["alliance_name"],

            "alliance_code":
            code,

            "current_value":
            latest["current_value"],

            "members":
            latest["members"],

            "season_won":
            latest["season_won"],

            "rank":
            latest["rank"],

            "growth_rate":
            growth_rate,

            "movement":
            movement,

            "prediction":
            prediction,

            "bot_score":
            bot_score
        })

    final_data.sort(
        key=lambda x: x["bot_score"],
        reverse=True
    )

    return final_data

# =========================================================
# GLOBAL RANKING COMMAND
# =========================================================

@bot.command()
async def arank(ctx):

    data = build_global_rankings()

    if not data:

        return await ctx.send(
            "No alliance data found"
        )

    view = AllianceRankingView(
        data,
        "Global Season"
    )

    await view.update_buttons()

    await ctx.send(
        embed=view.build_embed(),
        view=view
    )
# =========================================================
# SINGLE ALLIANCE DASHBOARD
# =========================================================

class AllianceDashboardView(View):

    def __init__(self, alliance_data, history):

        super().__init__(timeout=300)

        self.data = alliance_data
        self.history = history

    def build_embed(self):

        latest = self.history[-1]

        growth_rate = calculate_growth_rate(
            self.history
        )

        movement = calculate_rank_movement(
            self.history
        )

        prediction = predict_future_rank(
            self.history
        )

        trend = "▲" if movement > 0 else (
            "▼" if movement < 0 else "▬"
        )

        bot_score = calculate_bot_score({

            "current_value":
            latest["current_value"],

            "total_flights":
            latest["total_flights"],

            "members":
            latest["members"],

            "season_won":
            latest["season_won"],

            "growth_rate":
            growth_rate,

            "rank":
            latest["rank"]
        })

        embed = discord.Embed(
            title=(
                f"{self.data['alliance_name']} "
                f"• Alliance Dashboard"
            ),
            color=0x1e1f22
        )

        embed.description = (
            f"Alliance Code: "
            f"`{self.data['alliance_code']}`\n\n"

            f"Advanced analytics based on\n"
            f"historical performance trends."
        )

        embed.add_field(
            name="Current Statistics",
            value=(

                f"Current Rank: "
                f"`#{latest['rank']}`\n"

                f"Bot Rank Score: "
                f"`{bot_score}`\n"

                f"Current Value: "
                f"`$"
                f"{int(latest['current_value']):,}`\n"

                f"Members: "
                f"`{latest['members']}`\n"

                f"Season Wins: "
                f"`{latest['season_won']}`\n"

                f"Flights: "
                f"`{int(latest['total_flights']):,}`"
            ),
            inline=False
        )

        embed.add_field(
            name="Growth Analysis",
            value=(

                f"Growth Rate: "
                f"`{growth_rate:.2f}%`\n"

                f"Rank Movement: "
                f"`{trend} "
                f"{abs(movement)}`\n"

                f"Predicted Rank: "
                f"`#{prediction}`\n"

                f"Entries Analysed: "
                f"`{len(self.history)}`"
            ),
            inline=False
        )

        suggestion = build_suggestion_text(
            growth_rate,
            movement
        )

        embed.add_field(
            name="AI Suggestions",
            value=suggestion,
            inline=False
        )

        latest_date = latest["entry_date"]

        embed.set_footer(
            text=(
                f"Last Updated • "
                f"{latest_date}"
            )
        )

        return embed

# =========================================================
# SUGGESTION ENGINE
# =========================================================

def build_suggestion_text(
    growth_rate,
    movement
):

    suggestions = []

    if growth_rate >= 15:

        suggestions.append(
            "Excellent long-term growth detected."
        )

        suggestions.append(
            "Alliance momentum is highly stable."
        )

    elif growth_rate >= 5:

        suggestions.append(
            "Alliance growth trend is healthy."
        )

    elif growth_rate < 0:

        suggestions.append(
            "Performance decline detected."
        )

        suggestions.append(
            "Increase activity consistency."
        )

    if movement > 0:

        suggestions.append(
            "Recent rank climb detected."
        )

    elif movement < 0:

        suggestions.append(
            "Rank drop observed recently."
        )

    if not suggestions:

        suggestions.append(
            "Alliance remains stable."
        )

    return "\n".join(
        f"• {x}" for x in suggestions
    )

# =========================================================
# GRAPH RENDER SYSTEM
# =========================================================

def generate_alliance_graph(
    history,
    alliance_name
):

    values = []
    labels = []

    recent = history[-5:]

    for row in recent:

        values.append(
            float(row["current_value"])
        )

        labels.append(
            row["entry_date"][-5:]
        )

    plt.figure(
        figsize=(8, 4)
    )

    fig = plt.gcf()

    fig.patch.set_facecolor(
        "#1b1c20"
    )

    ax = plt.gca()

    ax.set_facecolor(
        "#23252b"
    )

    plt.plot(
        labels,
        values,
        linewidth=3
    )

    plt.title(
        alliance_name,
        color="white"
    )

    plt.xticks(color="white")
    plt.yticks(color="white")

    for spine in ax.spines.values():
        spine.set_color("gray")

    temp = tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False
    )

    plt.savefig(
        temp.name,
        bbox_inches="tight",
        transparent=False
    )

    plt.close()

    return temp.name

# =========================================================
# ALLIANCE DASHBOARD COMMAND
# =========================================================

@bot.command()
async def alliance(ctx, code):

    code = code.upper()

    cursor.execute("""
    SELECT *
    FROM alliance_registry
    WHERE alliance_code = ?
    """, (code,))

    alliance = cursor.fetchone()

    if not alliance:

        return await ctx.send(
            "Alliance not found"
        )

    history = fetch_alliance_history(
        code
    )

    if not history:

        return await ctx.send(
            "No entries found"
        )

    view = AllianceDashboardView(
        alliance,
        history
    )

    embed = view.build_embed()

    graph_path = generate_alliance_graph(
        history,
        alliance["alliance_name"]
    )

    file = discord.File(
        graph_path,
        filename="graph.png"
    )

    embed.set_image(
        url="attachment://graph.png"
    )

    await ctx.send(
        embed=embed,
        file=file,
        view=view
    )

# =========================================================
# DELETE ENTRY SYSTEM
# =========================================================

@bot.command()
@commands.has_role(ALLOWED_ROLE)
async def delete_entry(
    ctx,
    alliance_code,
    entry_date
):

    alliance_code = alliance_code.upper()

    cursor.execute("""
    DELETE FROM alliance_daily_logs
    WHERE alliance_code = ?
    AND entry_date = ?
    """, (
        alliance_code,
        entry_date
    ))

    conn.commit()

    await ctx.send(
        f"Deleted entry for "
        f"{alliance_code} • {entry_date}"
    )

# =========================================================
# ENTRY HISTORY VIEW
# =========================================================

@bot.command()
async def history(ctx, alliance_code):

    alliance_code = alliance_code.upper()

    history = fetch_alliance_history(
        alliance_code
    )

    if not history:

        return await ctx.send(
            "No history found"
        )

    embed = discord.Embed(
        title=(
            f"{alliance_code} "
            f"• Entry History"
        ),
        color=0x1e1f22
    )

    recent = history[-10:]

    for row in reversed(recent):

        embed.add_field(
            name=row["entry_date"],
            value=(

                f"Rank: "
                f"`#{row['rank']}`\n"

                f"Value: "
                f"`$"
                f"{int(row['current_value']):,}`\n"

                f"Flights: "
                f"`"
                f"{int(row['total_flights']):,}`\n"

                f"Members: "
                f"`{row['members']}`"
            ),
            inline=False
        )

    await ctx.send(embed=embed)

# =========================================================
# ALLIANCE VS SYSTEM
# =========================================================

@bot.command()
async def alliance_compare(
    ctx,
    code1,
    code2
):

    code1 = code1.upper()
    code2 = code2.upper()

    cursor.execute("""
    SELECT *
    FROM alliance_registry
    WHERE alliance_code = ?
    """, (code1,))

    a1 = cursor.fetchone()

    cursor.execute("""
    SELECT *
    FROM alliance_registry
    WHERE alliance_code = ?
    """, (code2,))

    a2 = cursor.fetchone()

    if not a1 or not a2:

        return await ctx.send(
            "Alliance not found"
        )

    h1 = fetch_alliance_history(code1)
    h2 = fetch_alliance_history(code2)

    if not h1 or not h2:

        return await ctx.send(
            "Missing history data"
        )

    l1 = h1[-1]
    l2 = h2[-1]

    g1 = calculate_growth_rate(h1)
    g2 = calculate_growth_rate(h2)

    s1 = calculate_bot_score({

        "current_value":
        l1["current_value"],

        "total_flights":
        l1["total_flights"],

        "members":
        l1["members"],

        "season_won":
        l1["season_won"],

        "growth_rate":
        g1,

        "rank":
        l1["rank"]
    })

    s2 = calculate_bot_score({

        "current_value":
        l2["current_value"],

        "total_flights":
        l2["total_flights"],

        "members":
        l2["members"],

        "season_won":
        l2["season_won"],

        "growth_rate":
        g2,

        "rank":
        l2["rank"]
    })

    winner = (
        a1["alliance_name"]
        if s1 > s2
        else a2["alliance_name"]
    )

    embed = discord.Embed(
        title="Alliance Comparison",
        color=0x1e1f22
    )

    embed.add_field(
        name=a1["alliance_name"],
        value=(

            f"Bot Score: `{s1}`\n"
            f"Growth: `{g1:.2f}%`\n"
            f"Rank: `#{l1['rank']}`\n"
            f"Value: `$"
            f"{int(l1['current_value']):,}`"
        ),
        inline=True
    )

    embed.add_field(
        name=a2["alliance_name"],
        value=(

            f"Bot Score: `{s2}`\n"
            f"Growth: `{g2:.2f}%`\n"
            f"Rank: `#{l2['rank']}`\n"
            f"Value: `$"
            f"{int(l2['current_value']):,}`"
        ),
        inline=True
    )

    embed.add_field(
        name="Prediction",
        value=(
            f"`{winner}` "
            f"currently leads the comparison."
        ),
        inline=False
    )

    await ctx.send(embed=embed)
# =========================================================
# PAGINATION VIEW
# =========================================================

class AllianceRankingView(View):

    def __init__(self, embeds):

        super().__init__(timeout=180)

        self.embeds = embeds
        self.page = 0

    async def update_msg(self, interaction):

        await interaction.response.edit_message(
            embed=self.embeds[self.page],
            view=self
        )

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary
    )
    async def prev_page(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        if self.page > 0:
            self.page -= 1

        await self.update_msg(interaction)

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.primary
    )
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        if self.page < len(self.embeds) - 1:
            self.page += 1

        await self.update_msg(interaction)

# =========================================================
# BUILD GLOBAL RANKING EMBEDS
# =========================================================

def build_alliance_rank_pages():

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    ORDER BY current_value DESC
    """)

    rows = cursor.fetchall()

    latest = {}

    for row in rows:

        name = row["alliance_name"]

        if name not in latest:
            latest[name] = row

    alliances = list(latest.values())

    # =====================================================
    # BOT RANK LOGIC
    # =====================================================

    scored = []

    for row in alliances:

        value_score = row["current_value"] / 1000000
        member_score = extract_members(row["members"])
        season_score = row["season_won"] * 150
        flight_score = row["total_flights"] / 50000

        total_score = (
            value_score
            + member_score
            + season_score
            + flight_score
        )

        scored.append(
            (
                total_score,
                row
            )
        )

    scored.sort(
        reverse=True,
        key=lambda x: x[0]
    )

    embeds = []

    page_size = 8

    for page_start in range(
        0,
        len(scored),
        page_size
    ):

        chunk = scored[
            page_start:
            page_start + page_size
        ]

        embed = discord.Embed(
            title="Alliance Global Rankings",
            color=0x2b2d31
        )

        desc = ""

        for i, item in enumerate(chunk):

            global_rank = (
                page_start + i + 1
            )

            score = item[0]
            row = item[1]

            growth = calculate_growth(
                row["alliance_name"]
            )

            trend = get_trend_arrow(
                growth
            )

            desc += (
                f"**#{global_rank} • "
                f"{row['alliance_name']}**\n"

                f"Game Rank: "
                f"#{row['rank']}\n"

                f"Growth: "
                f"{growth:.2f}% {trend}\n"

                f"Value: "
                f"${row['current_value']:,}\n"

                f"Members: "
                f"{row['members']}\n"

                f"Seasons: "
                f"{row['season_won']}\n\n"
            )

        embed.description = desc

        embed.set_footer(
            text=(
                f"Page "
                f"{len(embeds)+1}/"
                f"{math.ceil(len(scored)/page_size)}"
            )
        )

        embeds.append(embed)

    return embeds

# =========================================================
# GLOBAL RANKING COMMAND
# =========================================================

@bot.command()
async def alliances(ctx):

    embeds = build_alliance_rank_pages()

    if not embeds:

        return await ctx.send(
            "No alliance data found."
        )

    view = AllianceRankingView(
        embeds
    )

    await ctx.send(
        embed=embeds[0],
        view=view
    )
# =========================================================
# GROWTH CALCULATION
# =========================================================

def calculate_growth(alliance_name):

    cursor.execute("""
    SELECT current_value
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date ASC
    """, (alliance_name,))

    rows = cursor.fetchall()

    if len(rows) < 2:
        return 0

    first = rows[0]["current_value"]
    last = rows[-1]["current_value"]

    if first <= 0:
        return 0

    growth = (
        ((last - first) / first)
        * 100
    )

    return round(growth, 2)

# =========================================================
# TREND ARROW
# =========================================================

def get_trend_arrow(growth):

    if growth > 0:
        return "▲"

    elif growth < 0:
        return "▼"

    return "■"

# =========================================================
# RANK PREDICTION
# =========================================================

def predict_rank(alliance_name):

    cursor.execute("""
    SELECT current_value
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date ASC
    """, (alliance_name,))

    rows = cursor.fetchall()

    if len(rows) < 3:
        return "Stable"

    values = [
        x["current_value"]
        for x in rows
    ]

    diffs = []

    for i in range(1, len(values)):

        diffs.append(
            values[i] - values[i - 1]
        )

    avg_gain = (
        sum(diffs) / len(diffs)
    )

    if avg_gain > 50000000:
        return "Strong Rise"

    elif avg_gain > 10000000:
        return "Rising"

    elif avg_gain < -50000000:
        return "Heavy Drop"

    elif avg_gain < -10000000:
        return "Dropping"

    return "Stable"

# =========================================================
# PERFORMANCE SUGGESTION ENGINE
# =========================================================

def generate_suggestion(data):

    members = extract_members(
        data["members"]
    )

    growth = calculate_growth(
        data["alliance_name"]
    )

    rank = data["rank"]

    suggestions = []

    if members < 45:

        suggestions.append(
            "Recruit more active members."
        )

    if growth < 0:

        suggestions.append(
            "Alliance value is decreasing."
        )

    if rank > 100:

        suggestions.append(
            "Focus on improving global rank."
        )

    if data["season_won"] == 0:

        suggestions.append(
            "No season wins recorded yet."
        )

    if not suggestions:

        suggestions.append(
            "Alliance performance is healthy."
        )

    return "\n".join(
        f"• {x}"
        for x in suggestions
    )

# =========================================================
# GRAPH GENERATOR
# =========================================================

def generate_growth_graph(alliance_name):

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date ASC
    LIMIT 5
    """, (alliance_name,))

    rows = cursor.fetchall()

    values = [
        row["current_value"]
        for row in rows
    ]

    dates = [
        row["entry_date"][-5:]
        for row in rows
    ]

    if len(values) <= 1:
        return None

    plt.figure(
        figsize=(8, 4)
    )

    ax = plt.gca()

    # =====================================================
    # GRAPH STYLE
    # =====================================================

    ax.set_facecolor("#1e1e1e")

    plt.gcf().patch.set_facecolor(
        "#1e1e1e"
    )

    plt.plot(
        dates,
        values,
        linewidth=4
    )

    plt.grid(
        alpha=0.2
    )

    plt.xticks(
        color="white"
    )

    plt.yticks(
        color="white"
    )

    plt.title(
        f"{alliance_name} Growth",
        color="white"
    )

    # =====================================================
    # SAVE
    # =====================================================

    temp = tempfile.NamedTemporaryFile(
        suffix=".png",
        delete=False
    )

    plt.savefig(
        temp.name,
        bbox_inches="tight",
        facecolor="#1e1e1e"
    )

    plt.close()

    return temp.name

# =========================================================
# SINGLE ALLIANCE DASHBOARD
# =========================================================

@bot.command()
async def alliance(
    ctx,
    alliance_name
):

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date DESC
    LIMIT 1
    """, (alliance_name,))

    data = cursor.fetchone()

    if not data:

        return await ctx.send(
            "Alliance not found."
        )

    growth = calculate_growth(
        alliance_name
    )

    trend = get_trend_arrow(
        growth
    )

    prediction = predict_rank(
        alliance_name
    )

    suggestion = generate_suggestion(
        data
    )

    embed = discord.Embed(
        title=f"{alliance_name} Dashboard",
        color=0x2b2d31
    )

    embed.add_field(
        name="Overview",
        value=(

            f"Current Value:\n"
            f"${data['current_value']:,}\n\n"

            f"Members:\n"
            f"{data['members']}\n\n"

            f"Global Rank:\n"
            f"#{data['rank']}\n\n"

            f"Season Wins:\n"
            f"{data['season_won']}"
        ),
        inline=True
    )

    embed.add_field(
        name="Growth Analytics",
        value=(

            f"Growth Rate:\n"
            f"{growth:.2f}% {trend}\n\n"

            f"Prediction:\n"
            f"{prediction}\n\n"

            f"Flights:\n"
            f"{data['total_flights']:,}"
        ),
        inline=True
    )

    embed.add_field(
        name="Suggestions",
        value=suggestion,
        inline=False
    )

    graph_path = generate_growth_graph(
        alliance_name
    )

    if graph_path:

        file = discord.File(
            graph_path,
            filename="graph.png"
        )

        embed.set_image(
            url="attachment://graph.png"
        )

        await ctx.send(
            embed=embed,
            file=file
        )

    else:

        await ctx.send(
            embed=embed
        )
# =========================================================
# DELETE ENTRY
# =========================================================

@bot.command()
@commands.has_role(ALLOWED_ROLE)
async def delete_alliance_entry(
    ctx,
    alliance_name,
    entry_id: int
):

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE id = ?
    AND alliance_name = ?
    """, (
        entry_id,
        alliance_name
    ))

    row = cursor.fetchone()

    if not row:

        return await ctx.send(
            "Entry not found."
        )

    cursor.execute("""
    DELETE FROM alliance_daily
    WHERE id = ?
    """, (entry_id,))

    db.commit()

    await ctx.send(
        f"Deleted entry #{entry_id}"
    )

# =========================================================
# EXPORT CSV
# =========================================================

@bot.command()
async def export_alliance(
    ctx,
    alliance_name
):

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date ASC
    """, (alliance_name,))

    rows = cursor.fetchall()

    if not rows:

        return await ctx.send(
            "Alliance not found."
        )

    temp = tempfile.NamedTemporaryFile(
        suffix=".csv",
        delete=False
    )

    with open(
        temp.name,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "Date",
            "Value",
            "Members",
            "Season Wins",
            "Flights",
            "Rank"
        ])

        for row in rows:

            writer.writerow([

                row["entry_date"],
                row["current_value"],
                row["members"],
                row["season_won"],
                row["total_flights"],
                row["rank"]
            ])

    await ctx.send(
        file=discord.File(
            temp.name,
            filename=f"{alliance_name}.csv"
        )
    )

# =========================================================
# COMPARE VIEW
# =========================================================

class CompareAllianceView(View):

    def __init__(
        self,
        embed_pages
    ):

        super().__init__(
            timeout=180
        )

        self.pages = embed_pages
        self.page = 0

    async def refresh(
        self,
        interaction
    ):

        await interaction.response.edit_message(
            embed=self.pages[self.page],
            view=self
        )

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary
    )
    async def previous_page(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        if self.page > 0:
            self.page -= 1

        await self.refresh(
            interaction
        )

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.primary
    )
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        if self.page < len(self.pages) - 1:
            self.page += 1

        await self.refresh(
            interaction
        )

# =========================================================
# ALLIANCE COMPARE
# =========================================================

@bot.command()
async def compare_alliance(
    ctx,
    alliance1,
    alliance2
):

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date DESC
    LIMIT 1
    """, (alliance1,))

    a1 = cursor.fetchone()

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date DESC
    LIMIT 1
    """, (alliance2,))

    a2 = cursor.fetchone()

    if not a1 or not a2:

        return await ctx.send(
            "Alliance not found."
        )

    pages = []

    # =====================================================
    # PAGE 1
    # =====================================================

    embed1 = discord.Embed(
        title="Alliance Comparison",
        color=0x2b2d31
    )

    embed1.add_field(
        name=alliance1,
        value=(

            f"Value:\n"
            f"${a1['current_value']:,}\n\n"

            f"Members:\n"
            f"{a1['members']}\n\n"

            f"Rank:\n"
            f"#{a1['rank']}\n\n"

            f"Growth:\n"
            f"{calculate_growth(alliance1)}%"
        ),
        inline=True
    )

    embed1.add_field(
        name=alliance2,
        value=(

            f"Value:\n"
            f"${a2['current_value']:,}\n\n"

            f"Members:\n"
            f"{a2['members']}\n\n"

            f"Rank:\n"
            f"#{a2['rank']}\n\n"

            f"Growth:\n"
            f"{calculate_growth(alliance2)}%"
        ),
        inline=True
    )

    pages.append(embed1)

    # =====================================================
    # PAGE 2
    # =====================================================

    embed2 = discord.Embed(
        title="Performance Analysis",
        color=0x2b2d31
    )

    better_growth = alliance1

    if (
        calculate_growth(alliance2)
        >
        calculate_growth(alliance1)
    ):

        better_growth = alliance2

    better_value = alliance1

    if (
        a2["current_value"]
        >
        a1["current_value"]
    ):

        better_value = alliance2

    embed2.description = (

        f"Better Growth:\n"
        f"**{better_growth}**\n\n"

        f"Higher Value:\n"
        f"**{better_value}**\n\n"

        f"Prediction:\n"
        f"{alliance1}: "
        f"{predict_rank(alliance1)}\n"

        f"{alliance2}: "
        f"{predict_rank(alliance2)}"
    )

    pages.append(embed2)

    view = CompareAllianceView(
        pages
    )

    await ctx.send(
        embed=pages[0],
        view=view
    )
# =========================================================
# MAIN DASHBOARD VIEW
# =========================================================

class AllianceDashboardView(View):

    def __init__(self):

        super().__init__(
            timeout=300
        )

    # =====================================================
    # GLOBAL RANKINGS
    # =====================================================

    @discord.ui.button(
        label="Global Rankings",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def global_rankings(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        embeds = build_alliance_rank_pages()

        if not embeds:

            return await interaction.response.send_message(
                "No alliance data found.",
                ephemeral=True
            )

        view = AllianceRankingView(
            embeds
        )

        await interaction.response.send_message(
            embed=embeds[0],
            view=view,
            ephemeral=True
        )

    # =====================================================
    # REGISTER ALLIANCE
    # =====================================================

    @discord.ui.button(
        label="Register Alliance",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def register_alliance_btn(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        if not any(
            role.name == ALLOWED_ROLE
            for role in interaction.user.roles
        ):

            return await interaction.response.send_message(
                "You are not authorized.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            RegisterAllianceModal()
        )

    # =====================================================
    # DAILY ENTRY
    # =====================================================

    @discord.ui.button(
        label="Daily Entry",
        style=discord.ButtonStyle.secondary,
        row=0
    )
    async def daily_entry_btn(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        if not any(
            role.name == ALLOWED_ROLE
            for role in interaction.user.roles
        ):

            return await interaction.response.send_message(
                "You are not authorized.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            DailyEntryModal()
        )

    # =====================================================
    # VIEW HISTORY
    # =====================================================

    @discord.ui.button(
        label="Alliance History",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def history_btn(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        await interaction.response.send_modal(
            HistoryModal()
        )

    # =====================================================
    # EXPORT
    # =====================================================

    @discord.ui.button(
        label="Export Data",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def export_btn(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        await interaction.response.send_modal(
            ExportModal()
        )

# =========================================================
# REGISTER MODAL
# =========================================================

class RegisterAllianceModal(
    discord.ui.Modal,
    title="Register Alliance"
):

    alliance_name = TextInput(
        label="Alliance Name",
        required=True,
        max_length=50
    )

    confirmation_rank = TextInput(
        label="Current Game Rank",
        required=True,
        max_length=10
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        code = generate_code()

        cursor.execute("""
        INSERT INTO alliance_registry
        (
            alliance_name,
            alliance_code,
            confirm_rank
        )
        VALUES (?, ?, ?)
        """, (
            str(self.alliance_name),
            code,
            int(self.confirmation_rank)
        ))

        db.commit()

        embed = discord.Embed(
            title="Alliance Registered",
            color=0x2b2d31
        )

        embed.description = (

            f"Alliance:\n"
            f"**{self.alliance_name}**\n\n"

            f"Alliance Code:\n"
            f"`{code}`"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

# =========================================================
# DAILY ENTRY MODAL
# =========================================================

class DailyEntryModal(
    discord.ui.Modal,
    title="Daily Alliance Entry"
):

    alliance_code = TextInput(
        label="Alliance Code",
        required=True,
        max_length=10
    )

    current_value = TextInput(
        label="Current Value",
        required=True
    )

    members = TextInput(
        label="Members (43/60)",
        required=True
    )

    season_won = TextInput(
        label="Season Won",
        required=True
    )

    extra_data = TextInput(
        label="Flights | Rank",
        placeholder="250000 | 52",
        required=True
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        # =================================================
        # VERIFY CODE
        # =================================================

        cursor.execute("""
        SELECT *
        FROM alliance_registry
        WHERE alliance_code = ?
        """, (
            str(self.alliance_code),
        ))

        registry = cursor.fetchone()

        if not registry:

            return await interaction.response.send_message(
                "Invalid alliance code.",
                ephemeral=True
            )

        alliance_name = registry[
            "alliance_name"
        ]

        # =================================================
        # SINGLE ENTRY PER DAY
        # =================================================

        today = str(
            datetime.date.today()
        )

        cursor.execute("""
        SELECT *
        FROM alliance_daily
        WHERE alliance_name = ?
        AND entry_date = ?
        """, (
            alliance_name,
            today
        ))

        existing = cursor.fetchone()

        if existing:

            return await interaction.response.send_message(
                "Today's entry already exists.",
                ephemeral=True
            )

        # =================================================
        # PARSE
        # =================================================

        extra = str(
            self.extra_data
        ).split("|")

        flights = int(
            extra[0].strip()
        )

        rank = int(
            extra[1].strip()
        )

        # =================================================
        # INSERT
        # =================================================

        cursor.execute("""
        INSERT INTO alliance_daily
        (
            alliance_name,
            current_value,
            members,
            season_won,
            total_flights,
            rank,
            entry_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (

            alliance_name,

            int(
                self.current_value
            ),

            str(self.members),

            int(
                self.season_won
            ),

            flights,
            rank,
            today
        ))

        db.commit()

        embed = discord.Embed(
            title="Daily Entry Added",
            color=0x2b2d31
        )

        embed.description = (

            f"Alliance:\n"
            f"**{alliance_name}**\n\n"

            f"Date:\n"
            f"{today}"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )
# =========================================================
# HISTORY MODAL
# =========================================================

class HistoryModal(
    discord.ui.Modal,
    title="Alliance History"
):

    alliance_name = TextInput(
        label="Alliance Name",
        required=True,
        max_length=50
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        cursor.execute("""
        SELECT *
        FROM alliance_daily
        WHERE alliance_name = ?
        ORDER BY entry_date DESC
        """, (
            str(self.alliance_name),
        ))

        rows = cursor.fetchall()

        if not rows:

            return await interaction.response.send_message(
                "Alliance not found.",
                ephemeral=True
            )

        embeds = []

        page_size = 5

        for start in range(
            0,
            len(rows),
            page_size
        ):

            chunk = rows[
                start:
                start + page_size
            ]

            embed = discord.Embed(
                title=f"{self.alliance_name} History",
                color=0x2b2d31
            )

            desc = ""

            for row in chunk:

                desc += (

                    f"Date: "
                    f"{row['entry_date']}\n"

                    f"Value: "
                    f"${row['current_value']:,}\n"

                    f"Members: "
                    f"{row['members']}\n"

                    f"Flights: "
                    f"{row['total_flights']:,}\n"

                    f"Rank: "
                    f"#{row['rank']}\n"

                    f"Season Wins: "
                    f"{row['season_won']}\n"

                    f"Entry ID: "
                    f"{row['id']}\n\n"
                )

            embed.description = desc

            embeds.append(embed)

        view = AllianceRankingView(
            embeds
        )

        await interaction.response.send_message(
            embed=embeds[0],
            view=view,
            ephemeral=True
        )

# =========================================================
# EXPORT MODAL
# =========================================================

class ExportModal(
    discord.ui.Modal,
    title="Export Alliance Data"
):

    alliance_name = TextInput(
        label="Alliance Name",
        required=True,
        max_length=50
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        cursor.execute("""
        SELECT *
        FROM alliance_daily
        WHERE alliance_name = ?
        ORDER BY entry_date ASC
        """, (
            str(self.alliance_name),
        ))

        rows = cursor.fetchall()

        if not rows:

            return await interaction.response.send_message(
                "Alliance not found.",
                ephemeral=True
            )

        temp = tempfile.NamedTemporaryFile(
            suffix=".csv",
            delete=False
        )

        with open(
            temp.name,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.writer(f)

            writer.writerow([

                "Date",
                "Value",
                "Members",
                "Season Wins",
                "Flights",
                "Rank"
            ])

            for row in rows:

                writer.writerow([

                    row["entry_date"],
                    row["current_value"],
                    row["members"],
                    row["season_won"],
                    row["total_flights"],
                    row["rank"]
                ])

        await interaction.response.send_message(
            file=discord.File(
                temp.name,
                filename=f"{self.alliance_name}.csv"
            ),
            ephemeral=True
        )

# =========================================================
# MAIN DASHBOARD COMMAND
# =========================================================

@bot.command()
async def alliancehub(ctx):

    embed = discord.Embed(
        title="Alliance Analytics Hub",
        color=0x2b2d31
    )

    embed.description = (

        "Central alliance management system.\n\n"

        "Features:\n"

        "• Global rankings\n"
        "• Alliance growth tracking\n"
        "• Prediction engine\n"
        "• Comparison system\n"
        "• Historical analytics\n"
        "• CSV exports\n"
        "• Alliance dashboards\n"
        "• Pagination system\n"
        "• Trend tracking"
    )

    embed.set_footer(
        text=(
            "JARVIS • "
            "Alliance Intelligence System"
        )
    )

    await ctx.send(
        embed=embed,
        view=AllianceDashboardView()
    )

# =========================================================
# LATEST ENTRY VIEWER
# =========================================================

@bot.command()
async def latest_alliance(
    ctx,
    alliance_name
):

    cursor.execute("""
    SELECT *
    FROM alliance_daily
    WHERE alliance_name = ?
    ORDER BY entry_date DESC
    LIMIT 1
    """, (
        alliance_name,
    ))

    row = cursor.fetchone()

    if not row:

        return await ctx.send(
            "Alliance not found."
        )

    embed = discord.Embed(
        title=f"{alliance_name} Latest Entry",
        color=0x2b2d31
    )

    embed.description = (

        f"Date:\n"
        f"{row['entry_date']}\n\n"

        f"Current Value:\n"
        f"${row['current_value']:,}\n\n"

        f"Members:\n"
        f"{row['members']}\n\n"

        f"Flights:\n"
        f"{row['total_flights']:,}\n\n"

        f"Rank:\n"
        f"#{row['rank']}\n\n"

        f"Season Wins:\n"
        f"{row['season_won']}"
    )

    await ctx.send(
        embed=embed
    )

# =========================================================
# ALLIANCE CODE LOOKUP
# =========================================================

@bot.command()
@commands.has_role(ALLOWED_ROLE)
async def alliance_code(
    ctx,
    alliance_name
):

    cursor.execute("""
    SELECT *
    FROM alliance_registry
    WHERE alliance_name = ?
    """, (
        alliance_name,
    ))

    row = cursor.fetchone()

    if not row:

        return await ctx.send(
            "Alliance not found."
        )

    embed = discord.Embed(
        title="Alliance Code",
        color=0x2b2d31
    )

    embed.description = (

        f"Alliance:\n"
        f"**{row['alliance_name']}**\n\n"

        f"Code:\n"
        f"`{row['alliance_code']}`"
    )

    await ctx.send(
        embed=embed
    )        
    
    
# =========================
# KEEP ALIVE (ONLY ONCE)
# =========================
keep_alive()

# =========================
# SAFE START (IMPORTANT FIX)
# =========================
if __name__ == "__main__":
    bot.run(TOKEN)
