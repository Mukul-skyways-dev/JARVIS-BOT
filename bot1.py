import discord
import random
import json
from discord.ext import commands
from discord import app_commands
from discord.ui import Modal, TextInput, View, Button
from typing import Literal
import edge_tts

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
import re
import os
import requests
from openai import OpenAI
import pytz

from export_view import ExportView
from am4_agent import setup_agent

# =========================================================
# KEEP ALIVE / PORT BINDING (Render requires a bound port on
# Web Service plans, or it times out waiting for one)
# =========================================================
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "JARVIS is alive"

def run():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

from datetime import datetime, timedelta, timezone
import asyncio
import time
from PIL import Image, ImageDraw, ImageFont
from contextlib import contextmanager

# =========================
# BOT CONFIG
# =========================
TOKEN = os.getenv("TOKEN")

groq = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# =========================================================
# GROQ CONVERSATIONAL AI — memory + real-data tool calling
# =========================================================
# Per-user short-term conversation memory (in-memory, resets on
# restart — not persisted to disk). Each entry is a list of
# {"role": ..., "content": ...} dicts, oldest first.
_conversation_memory = {}
MEMORY_TURNS = 6  # keep last 6 user+assistant messages (~3 exchanges)

def _get_history(user_id):
    return _conversation_memory.setdefault(user_id, [])

def _remember(user_id, user_message, assistant_reply):
    history = _get_history(user_id)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_reply})
    if len(history) > MEMORY_TURNS:
        del history[:-MEMORY_TURNS]

GROQ_SYSTEM_PROMPT = (
    "You are AERION, a Discord bot for an AM4 (Airline Manager 4) game "
    "alliance called AERO ETERNAL CORP.. ALWAYS reply in English only, "
    "regardless of what language the user writes in. Keep replies short "
    "(2-4 sentences), friendly, a little witty. You have tools to look "
    "up REAL aircraft specs, route demand/distance, and airport info — "
    "always use a tool instead of guessing when the user asks about "
    "something a tool can answer. For full route profit/config "
    "calculations, tell the user to run !route, !best_r, !compare, "
    "!whatif, or !best_world instead — those use the real profit engine "
    "and you don't have access to it directly but when usee say about to do it then use it by yourself.."
    "you are developed by Mukul khandelwal known as skyways in the group."
    "you are developed at LOOP LOGIC GEN X2B CODEBASE."
    "you are backed with LOOP LOGIC T100 XC3702 1TB GIGA6 SERVER."
)

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_aircraft",
            "description": "Get real specs for an aircraft: capacity, range, speed, fuel burn, CO2, purchase cost.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Aircraft name or shortcode, e.g. 'A380' or 'b744'"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_route",
            "description": "Get real distance and passenger demand (Economy/Business/First) between two airports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "frm": {"type": "string", "description": "Origin IATA code, e.g. DEL"},
                    "to": {"type": "string", "description": "Destination IATA code, e.g. BOM"}
                },
                "required": ["frm", "to"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_airport",
            "description": "Get real info about an airport: full name, city, country, runway length, hub cost.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "IATA code, ICAO code, or city name"}
                },
                "required": ["query"]
            }
        }
    }
]

def _tool_lookup_aircraft(name):
    p = get_plane(name)
    if not p:
        return {"error": f"No aircraft found matching '{name}'"}
    return {
        "name": p["name"], "shortcode": p["shortname"], "capacity_units": p["capacity"],
        "range_km": p["range"], "speed_kmh": p["speed"], "fuel_per_km": p["fuel"],
        "co2_per_km": p["co2"], "purchase_cost_usd": p["cost"]
    }

def _tool_lookup_route(frm, to):
    r = get_route(frm, to)
    if not r:
        return {"error": f"No route on file between '{frm}' and '{to}'"}
    return {"distance_km": r["distance"], "demand_economy": r["y"], "demand_business": r["j"], "demand_first": r["f"]}

def _tool_lookup_airport(query):
    raw = query.strip()
    code_upper = raw.upper()
    city_query = resolve_city_alias(raw)
    with get_static_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM airports WHERE iata = ? OR icao = ? LIMIT 1", (code_upper, code_upper))
        row = cursor.fetchone()
        if not row:
            cursor.execute("""
                SELECT * FROM airports WHERE LOWER(name) LIKE ? OR LOWER(fullname) LIKE ?
                ORDER BY market DESC LIMIT 1
            """, (f"%{city_query}%", f"%{city_query}%"))
            row = cursor.fetchone()
    if not row:
        return {"error": f"No airport found matching '{query}'"}
    return {
        "iata": row["iata"], "icao": row["icao"], "name": row["fullname"], "city": row["name"],
        "country": row["country"], "runway_ft": row["rwy"], "hub_cost_usd": row["hub_cost"]
    }

def _execute_tool(name, args):
    try:
        if name == "lookup_aircraft":
            return _tool_lookup_aircraft(args.get("name", ""))
        elif name == "lookup_route":
            return _tool_lookup_route(args.get("frm", ""), args.get("to", ""))
        elif name == "lookup_airport":
            return _tool_lookup_airport(args.get("query", ""))
        return {"error": "unknown tool"}
    except Exception as e:
        return {"error": str(e)}

async def get_groq_reply(user_id, user_message):
    """Calls Groq with conversation memory + real-data tools. Runs
    blocking API calls in a thread so it doesn't freeze the event loop."""
    history = _get_history(user_id)
    messages = [{"role": "system", "content": GROQ_SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]

    try:
        response = await asyncio.to_thread(
            groq.chat.completions.create,
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=GROQ_TOOLS,
            tool_choice="auto",
            max_tokens=300,
            temperature=0.7
        )
        reply_msg = response.choices[0].message

        if reply_msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": reply_msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in reply_msg.tool_calls
                ]
            })
            for tc in reply_msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                result = _execute_tool(tc.function.name, args)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

            follow_up = await asyncio.to_thread(
                groq.chat.completions.create,
                model="openai/gpt-oss-120b",
                messages=messages,
                max_tokens=300,
                temperature=0.7
            )
            final_text = follow_up.choices[0].message.content
        else:
            final_text = reply_msg.content

        _remember(user_id, user_message, final_text)
        return final_text
    except Exception as e:
        print(f"⚠️ Groq API error: {e}")
        return None

WELCOME_ROLE_NAME = "Member"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, max_messages=None)

# ========================
# Share Module import 
# ========================
exec(open("share_module.py").read())

# =========================
# DATABASE AUTO DOWNLOAD
# =========================

DB_URL = "https://github.com/Mukul-skyways-dev/JARVIS-BOT/releases/download/Dv1/am4_data.db.updated"
DB_FILE = "am4_data.db"

def download_db():
    print("🔄 Checking database...")
    print("⬇ Downloading database from GitHub Release...")
    try:
        with requests.get(DB_URL, timeout=30, stream=True) as response:
            response.raise_for_status()
            with open(DB_FILE, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        print("✅ Database downloaded successfully")
    except Exception as e:
        print("❌ DB download failed:", e)

download_db()

# =========================================================
# WORLD MAP DATA (one-time download, cached — for routemap's real
# geography, not fetched fresh every restart like am4_data.db is)
# =========================================================
WORLD_MAP_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"
WORLD_MAP_FILE = "world_countries.geojson"

def download_world_map():
    if os.path.exists(WORLD_MAP_FILE):
        return
    print("🔄 Downloading world map data (one-time, ~800KB, public domain)...")
    try:
        with requests.get(WORLD_MAP_URL, timeout=30, stream=True) as response:
            response.raise_for_status()
            with open(WORLD_MAP_FILE, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        print("✅ World map data downloaded")
    except Exception as e:
        print("❌ World map download failed:", e)

download_world_map()


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
def get_dyn_db():
    conn = sqlite3.connect("new_am4.db", timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# =========================================================
# STATIC DATA (aircraft + airports) — separate, stable file.
# NOT auto-downloaded/overwritten like am4_data.db is — this one
# is committed directly to the repo and only changes when you
# manually re-migrate and re-upload a new version.
# =========================================================
STATIC_DB_FILE = "static_data.db"

@contextmanager
def get_static_db():
    conn = sqlite3.connect(STATIC_DB_FILE, timeout=10)
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
@bot.hybrid_command(description="Show the JARVIS command menu")
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

_PLANES_CACHE = None

def get_all_planes():
    global _PLANES_CACHE
    if _PLANES_CACHE is not None:
        return _PLANES_CACHE
    with get_static_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, shortname, speed, fuel, co2, cost, capacity, range, check_cost
            FROM aircraft
            WHERE priority = 0
        """)
        planes = []
        for r in cursor.fetchall():
            planes.append({
                "name": r[0],
                "shortname": r[1],
                "speed": to_float(r[2]),
                "fuel": to_float(r[3]),
                "co2": to_float(r[4]),
                "cost": to_int(r[5]),
                "capacity": to_int(r[6]),
                "range": to_float(r[7]),
                "check_cost": to_int(r[8])
            })
        _PLANES_CACHE = planes
        return planes

def get_plane(name):
    key = norm(name)
    for p in get_all_planes():
        if key in norm(p["name"]) or key in norm(p["shortname"]):
            return p
    return None

# =========================================================
# AUTOCOMPLETE — live suggestions for airport/aircraft params
# =========================================================
async def aircraft_autocomplete(interaction: discord.Interaction, current: str):
    current_norm = norm(current) if current else ""
    matches = []
    for p in get_all_planes():
        if not current_norm or current_norm in norm(p["name"]) or current_norm in norm(p["shortname"]):
            label = f"{p['name']} ({p['shortname']})"
            matches.append(app_commands.Choice(name=label[:100], value=p["shortname"]))
        if len(matches) >= 25:
            break
    return matches

async def airport_autocomplete(interaction: discord.Interaction, current: str):
    current_norm = (current or "").strip().lower()
    matches = []
    try:
        with get_static_db() as conn:
            cursor = conn.cursor()
            if current_norm:
                cursor.execute("""
                    SELECT iata, name, fullname, country FROM airports
                    WHERE LOWER(iata) LIKE ? OR LOWER(name) LIKE ? OR LOWER(fullname) LIKE ?
                    ORDER BY market DESC
                    LIMIT 25
                """, (f"%{current_norm}%", f"%{current_norm}%", f"%{current_norm}%"))
            else:
                cursor.execute("SELECT iata, name, fullname, country FROM airports ORDER BY market DESC LIMIT 25")
            for row in cursor.fetchall():
                label = f"{row['iata']} — {row['name']}, {row['country']}"
                matches.append(app_commands.Choice(name=label[:100], value=row["iata"]))
    except Exception as e:
        print("airport_autocomplete error:", e)
    return matches

# =========================
# CALC ENGINE V4 — real formulas, verified against official reference data
# =========================
# Everything below was checked against a real am4help bot screenshot
# (DEL->BOM, A380-800, both easy & realism) unless flagged otherwise.
#
# CONFIRMED (exact or near-exact match against a real reference,
# DEL->BOM A380-800):
#   - trips/day    = ceil(total_demand / capacity)
#   - seat config  = weighted capacity (Y=1, J=2, F=3 units), filled in
#                    order F, J, Y using floor(demand_class / trips),
#                    capped by remaining weighted capacity
#   - ticket price = autoprice x optimal multiplier (Y x1.10, J x1.08, F x1.06)
#   - fuel qty     = distance x aircraft fuel stat x CI factor (verified
#                    to the unit: 25,337.4 lb computed vs 25,337 lb real)
#   - co2 qty      = distance x aircraft co2 stat x (Y+2J+3F config-weighted)
#                    x CI factor (verified: 109,270 computed vs 108,552 real)
#   - repair cost  = 0.0000075 x aircraft cost (expected wear)
#   - A-check realism = exactly 2x A-check easy
#
# APPROXIMATED (flagged — refine later with more reference samples):
#   - Fuel/CO2 DOLLAR cost = quantity x current market price per unit.
#     We don't have a live market feed wired in here, so
#     FUEL_PRICE_PER_LB / CO2_PRICE_PER_QUINTAL below are fixed
#     estimates calibrated against the one reference we have — real
#     prices move with the in-game market, same as the fuel bot tracks.
#   - A-check absolute cost: we only have ONE confirmed reference ratio
#     (check_cost -> per-trip amount), not the real check-interval
#     formula, so acheck_k below is empirical, not derived.
#
# Cost Index (CI) is not hardcoded at 200. Real formula (confirmed,
# R^2=1): effective_speed = base_speed * (0.0035*CI + 0.3). CI also
# scales fuel/CO2 quantity (both confirmed formulas below). Lower CI =
# slower/cheaper, higher CI = faster/pricier — there's a genuine
# profit-maximizing CI per route, which is exactly the kind of thing a
# static calculator won't tell you. See find_optimal_ci().
FUEL_PRICE_PER_LB = 0.70       # $/lb — calibrated against reference; approximate
CO2_PRICE_PER_QUINTAL = 0.12   # $/quintal — calibrated against reference; approximate

def calc(route, plane, user_id, mods=None, cost_index=200):
    mode = get_user_mode(user_id)
    dist = float(route["distance"])
    base_speed = float(plane["speed"])
    if mods and "speed" in mods:
        base_speed *= 1.1

    cost_index = max(0, min(200, cost_index))
    speed = base_speed * (0.0035 * cost_index + 0.3)
    time = dist / speed if speed else 1

    y = int(route["y"])
    j = int(route["j"])
    f = int(route["f"])
    cap = int(plane["capacity"])  # weighted capacity units (Y=1, J=2, F=3)
    total_demand = y + j + f

    # ---- Trips/day: ceil(demand / capacity), capped by technical max ----
    demand_trips = max(1, -(-total_demand // cap)) if cap else 1
    technical_max = max(1, int(24 / time)) if time else 1
    trips = min(demand_trips, technical_max)

    # ---- Best seat configuration: F -> J -> Y, weighted capacity ----
    remaining = cap
    f_c = min(f // trips if trips else 0, remaining // 3)
    remaining -= f_c * 3
    j_c = min(j // trips if trips else 0, remaining // 2)
    remaining -= j_c * 2
    y_c = min(y // trips if trips else 0, remaining // 1)

    # ---- Ticket pricing: autoprice x optimal multiplier ----
    if mode == "easy":
        y_auto = (0.4 * dist) + 170
        j_auto = (0.8 * dist) + 560
        f_auto = (1.2 * dist) + 1200
        acheck_k = 0.004444  # empirical — see note above
        cargo_mul = 0.5
        k_gm = 1.0  # contribution multiplier — easy
    else:
        y_auto = (0.3 * dist) + 150
        j_auto = (0.6 * dist) + 500
        f_auto = (0.9 * dist) + 1000
        acheck_k = 0.008889  # empirical — see note above
        cargo_mul = 0.35
        k_gm = 1.5  # contribution multiplier — realism

    y_price = y_auto * 1.10
    j_price = j_auto * 1.08
    f_price = f_auto * 1.06

    income_trip = (y_c * y_price) + (j_c * j_price) + (f_c * f_price)
    cargo = float(route.get("cargo", 0))
    cargo_income = cargo * cargo_mul
    income_trip += cargo_income

    # ---- Fuel & CO2 — confirmed formulas, now CI-scaled ----
    # IMPORTANT: these formulas compute a physical QUANTITY (lb / quintals),
    # verified to the unit against a real reference (am4help output for
    # DEL->BOM, A380-800: our fuel_lb formula gave 25,337.4 lb vs their
    # exact 25,337 lb; our co2_qty gave 109,270 vs their 108,552 quintals).
    # Cost = quantity x current market price per unit. We don't have a
    # live market feed wired into this bot, so FUEL_PRICE_PER_LB and
    # CO2_PRICE_PER_QUINTAL below are fixed estimates calibrated against
    # that same reference (~$0.70/lb, ~$0.12/quintal) — real prices move
    # with the in-game fuel/CO2 market, so treat these as approximate
    # until live prices are wired in.
    fuel_factor = (cost_index / 500) + 0.6
    fuel_lb = dist * float(plane["fuel"]) * fuel_factor
    if mods and "fuel" in mods:
        fuel_lb *= 0.9
    fuel = fuel_lb * FUEL_PRICE_PER_LB

    # CO2 quantity: config-only, weighted Y=1/J=2/F=3 (NOT load+config
    # combined — that earlier assumption double-counted and was the bug).
    co2_weighted = y_c + (2 * j_c) + (3 * f_c)
    co2_factor = (cost_index / 2000) + 0.9
    co2_q = dist * float(plane["co2"]) * co2_weighted * co2_factor
    if mods and "co2" in mods:
        co2_q *= 0.9
    co2 = co2_q * CO2_PRICE_PER_QUINTAL

    # ---- Repair (confirmed) & A-check (approximated) ----
    aircraft_cost = float(plane.get("cost", 0))
    repair = 0.0000075 * aircraft_cost

    check_cost = float(plane.get("check_cost", 0))
    acheck = check_cost * acheck_k

    total_cost = fuel + co2 + acheck + repair
    profit_trip = income_trip - total_cost
    ci_margin = int((profit_trip / income_trip) * 100) if income_trip else 0

    # ---- Contribution — confirmed formula ----
    # $C = min(k_gm * k * d * (3 - CI/100), 152) per flight
    if dist < 6000:
        k_dist = 0.0064
    elif dist < 10000:
        k_dist = 0.0032
    else:
        k_dist = 0.0048
    contribution_trip = min(k_gm * k_dist * dist * (3 - cost_index / 100), 152)
    contribution_trip = max(0, contribution_trip)

    income_day = income_trip * trips
    fuel_day = fuel * trips
    co2_day = co2 * trips
    profit_day = profit_trip * trips
    contribution_day = contribution_trip * trips

    return {
        "mode": mode,
        "distance": int(dist),
        "time": round(time, 2),
        "trips": trips,
        "cost_index": cost_index,
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
        "ci": ci_margin,
        "contribution_trip": round(contribution_trip, 2),
        "contribution_day": round(contribution_day, 2),
        "income_day": int(income_day),
        "fuel_day": int(fuel_day),
        "co2_day": int(co2_day),
        "profit_day": int(profit_day)
    }

def find_optimal_ci(route, plane, user_id, mods=None, step=10):
    """Scans CI 0-200 and returns the result for whichever CI gives the
    best daily profit, plus the one that gives the best daily
    contribution — these are usually NOT the same CI. A calculator
    that always assumes CI=200 misses this trade-off entirely."""
    best_profit_result = None
    best_contribution_result = None

    for ci_candidate in range(0, 201, step):
        result = calc(route, plane, user_id, mods=mods, cost_index=ci_candidate)
        if best_profit_result is None or result["profit_day"] > best_profit_result["profit_day"]:
            best_profit_result = result
        if best_contribution_result is None or result["contribution_day"] > best_contribution_result["contribution_day"]:
            best_contribution_result = result

    return best_profit_result, best_contribution_result

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

with get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if "last_used" not in existing_columns:
        print("🔧 Migrating 'users' table: adding missing last_used column")
        cursor.execute("ALTER TABLE users ADD COLUMN last_used REAL DEFAULT 0")
        conn.commit()

COOLDOWN = 3

async def add_usage(user):
    """Runs as a background task (fire-and-forget from on_command) so
    it never adds latency to any command's response."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    discord_id = str(user.id)
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        rows = await supabase_get("bot_usage_leaderboard", {
            "discord_id": f"eq.{discord_id}",
            "select": "last_used,points"
        })
        if rows:
            last_used_raw = rows[0].get("last_used")
            if last_used_raw:
                last_used_dt = datetime.fromisoformat(last_used_raw.replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - last_used_dt).total_seconds() < COOLDOWN:
                    return
            new_points = (rows[0].get("points") or 0) + 1
            await supabase_patch("bot_usage_leaderboard", {"discord_id": f"eq.{discord_id}"}, {
                "points": new_points, "username": user.name, "last_used": now_iso
            })
        else:
            await supabase_post("bot_usage_leaderboard", {
                "discord_id": discord_id, "username": user.name, "points": 1, "last_used": now_iso
            })
    except Exception as e:
        print(f"[USAGE] Failed to record usage for {discord_id} ({user}): {e}")

# =========================================================
# LEADERBOARD VIEW
# =========================================================
class LeaderboardView(View):
    def __init__(self, data):
        super().__init__(timeout=180)
        self.page = 0
        self.data = data

    @staticmethod
    async def fetch_data():
        if not SUPABASE_URL or not SUPABASE_KEY:
            return []
        try:
            rows = await supabase_get("bot_usage_leaderboard", {
                "select": "username,points",
                "order": "points.desc",
                "limit": "100"
            })
            return [(r.get("username") or "Unknown", r.get("points") or 0) for r in rows]
        except Exception as e:
            print(f"[LEADERBOARD] Fetch failed: {e}")
            return []

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
        self.data = await LeaderboardView.fetch_data()
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
        await interaction.response.edit_message(embed=self.build_embed(), attachments=[], view=self)
        
# =========================================================
# PORTAL LINKING + AERO POINTS (Supabase REST)
# =========================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def _supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

async def supabase_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = await asyncio.to_thread(requests.get, url, headers=_supabase_headers(), params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

async def supabase_patch(table, params, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = await asyncio.to_thread(
        requests.patch,
        url,
        headers=_supabase_headers(),
        params=params,
        json=data,
        timeout=10
    )
    resp.raise_for_status()

    # Supabase can return 204 No Content for a successful PATCH.
    if resp.status_code == 204 or not resp.content:
        return None

    return resp.json()

async def supabase_post(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = await asyncio.to_thread(requests.post, url, headers=_supabase_headers(), json=data, timeout=10)
    resp.raise_for_status()
    return resp.json()

# Which commands earn AERO points, and how many. Trivial commands
# (menu, leaderboard, difficulty, airport/aircraft lookups) are
# deliberately excluded so points can't be farmed by spamming cheap
# commands.
COMMAND_POINTS = {
    "route": 3, "best_r": 2, "best_short": 2, "best_long": 2,
    "best_world": 3, "best": 2, "compare": 2, "whatif": 3, "routemap": 2
}
POINT_COOLDOWN_SECONDS = 20
_last_point_credit = {}  # discord_id (str) -> unix timestamp, simple anti-spam

async def credit_aero_points(discord_id, command_name):
    """Runs as a background task (fire-and-forget) so it never adds
    latency to the command's actual response. Every outcome — success,
    skip, or failure — is printed so Render logs show exactly what
    happened and why."""
    points = COMMAND_POINTS.get(command_name)
    if not points:
        return  # not a point-eligible command

    now = time.time()
    last = _last_point_credit.get(discord_id, 0)
    if now - last < POINT_COOLDOWN_SECONDS:
        print(f"[AERO POINTS] {discord_id} used '{command_name}' -> skipped (cooldown)")
        return
    _last_point_credit[discord_id] = now

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[AERO POINTS] SUPABASE_URL/SUPABASE_KEY not set — skipping credit")
        return

    try:
        rows = await supabase_get("share_users", {"discord_id": f"eq.{discord_id}", "select": "sts_id,aero_points"})
        if not rows:
            print(f"[AERO POINTS] {discord_id} used '{command_name}' -> not linked, no credit given")
            return

        sts_id = rows[0]["sts_id"]
        current_points = rows[0].get("aero_points") or 0
        new_points = current_points + points

        await supabase_patch("share_users", {"sts_id": f"eq.{sts_id}"}, {"aero_points": new_points})
        await supabase_post("point_transactions", {
            "sts_id": sts_id,
            "amount": points,
            "reason": f"JARVIS command: {command_name}",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        print(f"[AERO POINTS] Discord {discord_id} used '{command_name}' -> +{points} points "
              f"(STS: {sts_id}, new total: {new_points})")
    except Exception as e:
        print(f"[AERO POINTS] Credit failed for {discord_id} on '{command_name}': {e}")

@bot.hybrid_command(name="link", description="Link your Discord account to your AERO portal profile using a one-time code")
@app_commands.describe(code="The code shown on your portal profile (valid 10 minutes, single use)")
async def link(ctx, code: str):
    await ctx.defer(ephemeral=True)

    if not SUPABASE_URL or not SUPABASE_KEY:
        return await ctx.send("⚠️ Portal linking isn't configured on this bot yet.")

    clean_code = code.strip().upper()
    try:
        rows = await supabase_get("discord_link_codes", {
            "code": f"eq.{clean_code}",
            "used": "eq.false",
            "select": "*"
        })
    except Exception as e:
        print(f"[LINK] Supabase lookup failed for code '{clean_code}': {e}")
        return await ctx.send("⚠️ Couldn't reach the portal right now — try again shortly.")

    if not rows:
        print(f"[LINK] {ctx.author} ({ctx.author.id}) tried invalid/used code '{clean_code}'")
        return await ctx.send("❌ Invalid or already-used code. Generate a new one on the portal.")

    row = rows[0]
    try:
        created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - created).total_seconds() > 600:
            print(f"[LINK] {ctx.author} ({ctx.author.id}) tried expired code '{clean_code}'")
            return await ctx.send("❌ Code expired — generate a new one on the portal (valid 10 minutes).")
    except Exception:
        pass  # if the timestamp can't be parsed, don't block linking over it

    sts_id = row["sts_id"]
    try:
        await supabase_patch("share_users", {"sts_id": f"eq.{sts_id}"}, {"discord_id": str(ctx.author.id)})
        await supabase_patch("discord_link_codes", {"id": f"eq.{row['id']}"}, {"used": True})
    except Exception as e:
        print(f"[LINK] Supabase update failed linking {ctx.author.id} -> {sts_id}: {e}")
        return await ctx.send("⚠️ Linking failed — try again shortly.")

    print(f"[LINK] Discord {ctx.author} ({ctx.author.id}) linked to STS {sts_id}")
    await ctx.send(f"✅ Linked! Your JARVIS activity will now credit AERO points to **{sts_id}**.")

@bot.hybrid_command(name="myaeropoints", description="Check your linked AERO portal points balance")
async def myaeropoints(ctx):
    await ctx.defer(ephemeral=True)

    if not SUPABASE_URL or not SUPABASE_KEY:
        return await ctx.send("⚠️ Portal linking isn't configured on this bot yet.")

    try:
        rows = await supabase_get("share_users", {"discord_id": f"eq.{ctx.author.id}", "select": "sts_id,aero_points,name"})
    except Exception as e:
        print(f"[AERO POINTS] Balance check failed for {ctx.author.id}: {e}")
        return await ctx.send("⚠️ Couldn't reach the portal right now.")

    if not rows:
        return await ctx.send("❌ Your Discord isn't linked yet — generate a code on the portal, then use `/link <code>`.")

    row = rows[0]
    label = row.get("name") or row["sts_id"]
    await ctx.send(f"💰 **{label}** — AERO Points: **{(row.get('aero_points') or 0):,}**")

# =========================
# AUTO TRACK - NEW
# =========================
@bot.event
async def on_command(ctx):
    asyncio.create_task(add_usage(ctx.author))
    asyncio.create_task(credit_aero_points(str(ctx.author.id), ctx.command.name))

@bot.hybrid_command(description="Show the JARVIS usage leaderboard")
async def leaderboard(ctx):
    await ctx.defer()
    data = await LeaderboardView.fetch_data()
    if not data:
        return await ctx.send("❌ No usage data yet")
    view = LeaderboardView(data)
    await ctx.send(embed=view.build_embed(), view=view)

# =========================================================
# AIRPORT HELPER
# =========================================================
def airport_name(iata):
    iata = iata.upper()
    try:
        with get_static_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, country, fullname FROM airports WHERE iata = ? LIMIT 1", (iata,))
            row = cursor.fetchone()
            if row:
                city, country, full_name = row[0], row[1], row[2]
                return f"{iata} • {full_name}\n{city}, {country}"
    except Exception as e:
        print("airport_name (static_data.db) error:", e)

    # Fallback to the routes table if the airport isn't in static_data.db yet
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT f_city, f_country, f_name FROM routes WHERE f_iata = ? LIMIT 1", (iata,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("SELECT t_city, t_country, t_name FROM routes WHERE t_iata = ? LIMIT 1", (iata,))
                row = cursor.fetchone()
            if row:
                city, country, airport = row[0], row[1], row[2]
                return f"{iata} • {airport}\n{city}, {country}"
    except Exception as e:
        print("airport_name (routes fallback) error:", e)
    return iata

# =========================================================
# CITY NAME ALIASES + !airport / !aircraft LOOKUP COMMANDS
# =========================================================
CITY_ALIASES = {
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "bangalore": "bengaluru",
    "peking": "beijing",
    "canton": "guangzhou",
    "saigon": "ho chi minh city",
    "rangoon": "yangon",
    "constantinople": "istanbul",
    "leningrad": "saint petersburg",
    "new amsterdam": "amsterdam",
}

def resolve_city_alias(query):
    key = query.strip().lower()
    return CITY_ALIASES.get(key, key)

@bot.hybrid_command(description="Look up an airport by IATA/ICAO code or city name (old names work too)")
@app_commands.describe(query="e.g. BOM, or 'bombay', or 'mumbai'")
@app_commands.autocomplete(query=airport_autocomplete)
async def airport(ctx, *, query: str):
    await ctx.defer()
    raw = query.strip()
    code_upper = raw.upper()
    city_query = resolve_city_alias(raw)

    with get_static_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM airports WHERE iata = ? OR icao = ? LIMIT 1", (code_upper, code_upper))
        row = cursor.fetchone()
        rows = [row] if row else []

        if not rows:
            cursor.execute("""
                SELECT * FROM airports
                WHERE LOWER(name) LIKE ? OR LOWER(fullname) LIKE ?
                ORDER BY market DESC
                LIMIT 5
            """, (f"%{city_query}%", f"%{city_query}%"))
            rows = cursor.fetchall()

    if not rows:
        return await ctx.send(f"❌ No airport found matching **{query}**")

    if len(rows) > 1:
        options = "\n".join(f"• `{r['iata']}` — {r['fullname']}, {r['name']}" for r in rows)
        embed = discord.Embed(
            title=f"🔎 Multiple airports match \"{query}\"",
            description=options + "\n\nTry the exact IATA code for a direct match.",
            color=0xffaa00
        )
        return await ctx.send(embed=embed)

    a = rows[0]
    embed = discord.Embed(title=f"🛫 {a['iata']} • {a['fullname']}", color=0x2ecc71)
    embed.add_field(name="📍 Location", value=f"{a['name']}, {a['country']}", inline=True)
    embed.add_field(name="🛬 ICAO", value=a['icao'] or "N/A", inline=True)
    embed.add_field(name="🛤️ Runway", value=f"{a['rwy']:,} ft" if a['rwy'] else "N/A", inline=True)
    embed.add_field(name="💰 Hub Cost", value=f"${a['hub_cost']:,}" if a['hub_cost'] else "N/A", inline=True)
    embed.add_field(name="📊 Market Size", value=str(a['market']) if a['market'] else "N/A", inline=True)
    embed.add_field(name="🧭 Runway Heading", value=a['rwy_codes'] or "N/A", inline=True)
    embed.set_footer(text="JARVIS • Airport Database System")

    if a['rwy'] and a['rwy_codes']:
        img_buf = draw_runway_image(a)
        file = discord.File(img_buf, filename="runway.png")
        embed.set_image(url="attachment://runway.png")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

@bot.hybrid_command(description="Full spec card for an aircraft")
@app_commands.describe(name="e.g. a380, or b744")
@app_commands.autocomplete(name=aircraft_autocomplete)
async def aircraft(ctx, *, name: str):
    plane = get_plane(name)
    if not plane:
        return await ctx.send(f"❌ No aircraft found matching **{name}**")

    embed = discord.Embed(title=f"✈️ {plane['name']} ({plane['shortname']})", color=0x3498db)
    embed.add_field(name="👥 Capacity", value=f"{plane['capacity']:,} units", inline=True)
    embed.add_field(name="🛫 Range", value=f"{plane['range']:,.0f} km", inline=True)
    embed.add_field(name="⚡ Speed", value=f"{plane['speed']:,.1f} km/h", inline=True)
    embed.add_field(name="⛽ Fuel Consumption", value=f"{plane['fuel']:,.2f}", inline=True)
    embed.add_field(name="🌱 CO2 Consumption", value=f"{plane['co2']:,.3f}", inline=True)
    embed.add_field(name="💰 Cost", value=f"${plane['cost']:,}", inline=True)
    embed.add_field(name="🔧 A-Check Cost (reference)", value=f"${plane['check_cost']:,}", inline=True)
    embed.set_footer(text="JARVIS • Aircraft Database System")
    await ctx.send(embed=embed)

# =========================================================
# AIRCRAFT VISUAL SYSTEM (Memory Optimized)
# =========================================================
def draw_runway_image(airport_row):
    """Top-down runway diagram from the airport's rwy (length, ft) and
    rwy_codes (heading pair, e.g. '06/24'). Our data model stores one
    runway per airport row, so this draws exactly one strip — if an
    airport genuinely has multiple physical runways, only the one on
    record here will show."""
    W, H = 640, 640
    img = Image.new("RGB", (W, H), (10, 15, 25))
    draw = ImageDraw.Draw(img)

    rwy_length_ft = airport_row["rwy"] or 0
    rwy_codes = (airport_row["rwy_codes"] or "").strip()
    iata = airport_row["iata"]
    city = airport_row["name"]
    fullname = airport_row["fullname"]

    try:
        title_font = ImageFont.truetype("arial.ttf", 24)
        label_font = ImageFont.truetype("arial.ttf", 18)
        small_font = ImageFont.truetype("arial.ttf", 13)
        rwy_num_font = ImageFont.truetype("arial.ttf", 30)
    except:
        title_font = ImageFont.load_default()
        label_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
        rwy_num_font = ImageFont.load_default()

    draw.text((28, 22), f"{iata} • {fullname}", fill=(150, 200, 255), font=title_font)
    draw.text((28, 54), f"{city}", fill=(150, 160, 170), font=small_font)

    try:
        end1_str, end2_str = rwy_codes.split("/")
        heading1 = int(end1_str) * 10
    except:
        end1_str, end2_str = "??", "??"
        heading1 = 0

    # Draw the strip horizontally on its own transparent layer, then
    # rotate the whole layer to the runway's real heading.
    strip_w, strip_h = 400, 44
    layer = Image.new("RGBA", (strip_w + 140, strip_h + 140), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    lx = (layer.width - strip_w) // 2
    ly = (layer.height - strip_h) // 2

    ldraw.rectangle((lx, ly, lx + strip_w, ly + strip_h), fill=(45, 48, 55))
    ldraw.rectangle((lx, ly, lx + strip_w, ly + 3), fill=(230, 230, 230))
    ldraw.rectangle((lx, ly + strip_h - 3, lx + strip_w, ly + strip_h), fill=(230, 230, 230))

    dash_w, gap = 16, 10
    cx = lx
    cy = ly + strip_h // 2 - 2
    while cx < lx + strip_w:
        ldraw.rectangle((cx, cy, min(cx + dash_w, lx + strip_w), cy + 4), fill=(255, 255, 255))
        cx += dash_w + gap

    for side_x in (lx + 12, lx + strip_w - 18):
        for i in range(4):
            by = ly + 6 + i * 9
            ldraw.rectangle((side_x, by, side_x + 6, by + 6), fill=(255, 255, 255))

    ldraw.text((lx + 14, ly + strip_h + 6), end1_str.zfill(2), fill=(255, 255, 255), font=rwy_num_font)
    ldraw.text((lx + strip_w - 44, ly - 38), end2_str.zfill(2), fill=(255, 255, 255), font=rwy_num_font)

    rotated = layer.rotate(-heading1, resample=Image.BICUBIC, expand=True)
    paste_x = (W - rotated.width) // 2
    paste_y = (H - rotated.height) // 2 + 30
    img.paste(rotated, (paste_x, paste_y), rotated)

    # Compass indicator (approximate — cosmetic, not survey-grade)
    draw.line((W - 55, 60, W - 55, 32), fill=(150, 200, 255), width=2)
    draw.polygon([(W - 61, 40), (W - 49, 40), (W - 55, 28)], fill=(150, 200, 255))
    draw.text((W - 62, 62), "N", fill=(150, 200, 255), font=small_font)

    length_m = int(rwy_length_ft * 0.3048) if rwy_length_ft else 0
    length_text = f"Length: {rwy_length_ft:,} ft ({length_m:,} m)" if rwy_length_ft else "Length: N/A"
    draw.text((28, H - 54), length_text, fill=(200, 210, 220), font=label_font)
    draw.text((28, H - 28), f"Runway {end1_str}/{end2_str}", fill=(150, 160, 170), font=small_font)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def draw_aircraft_card(plane, result, route, frm, to):
    W = 1200
    H = 700
    
    img = Image.new("RGB", (W, H), (10, 15, 25))
    draw = ImageDraw.Draw(img)
    
    # Simple background - no gradient (memory efficient)
    draw.rectangle((0, 0, W, H), fill=(10, 15, 25))
    
    # Glass card panel
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
    
    # Header
    from_airport = airport_name(frm)
    to_airport = airport_name(to)
    draw.text((80, 70), "JARVIS AVIATION VISUAL SYSTEM", fill=(150, 200, 255), font=title_font)
    draw.text((80, 120), from_airport, fill=(100, 180, 255), font=header_font)
    draw.text((80, 155), "▼", fill=(255, 255, 255), font=text_font)
    draw.text((80, 185), to_airport, fill=(100, 180, 255), font=header_font)
    
    # Aircraft fuselage (simplified)
    capacity = max(int(float(plane["capacity"])), 100)
    fuselage_length = min(max(450, 450 + int(capacity * 0.1)), 650)
    fuselage_height = min(max(60, 60 + int(capacity * 0.005)), 85)
    fuselage_x = 200
    fuselage_y = 270
    
    # Main fuselage
    draw.rounded_rectangle(
        (fuselage_x, fuselage_y, fuselage_x + fuselage_length, fuselage_y + fuselage_height),
        radius=fuselage_height // 2,
        fill=(220, 225, 240)
    )
    
    # Cockpit windows
    cockpit_x = fuselage_x + fuselage_length - 55
    cockpit_y = fuselage_y + (fuselage_height // 2) - 12
    draw.rounded_rectangle(
        (cockpit_x, cockpit_y, cockpit_x + 40, cockpit_y + 24),
        radius=8,
        fill=(80, 150, 230)
    )
    
    # Windows (simplified)
    window_count = min(max(int(capacity / 15), 12), 30)
    window_spacing = (fuselage_length - 160) // window_count
    for i in range(window_count):
        window_x = fuselage_x + 60 + (i * window_spacing)
        draw.rounded_rectangle(
            (window_x, fuselage_y + 18, window_x + 12, fuselage_y + 32),
            radius=3,
            fill=(70, 150, 220)
        )
    
    # Aircraft title
    draw.text(
        (fuselage_x + 100, fuselage_y + fuselage_height - 25),
        plane["name"],
        fill=(30, 35, 45),
        font=header_font
    )
    
    # Seat config bar
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
    
    # Stats panel
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
    
    # Right panel
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
    
    # CI Meter
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
    
    # Footer
    footer_y = H - 40
    draw.text((W // 2 - 120, footer_y), "AERO CROWN DYNASTY • JARVIS INTELLIGENCE", fill=(80, 85, 110), font=small_font)
    
    temp = io.BytesIO()
    img.save(temp, format='PNG', optimize=True, compress_level=6)
    img.close()
    temp.seek(0)
    return temp

def format_time(minutes):
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"

# =========================================================
# ROUTE COMMAND
# =========================================================
from matplotlib.colors import LinearSegmentedColormap

_JARVIS_CMAP = LinearSegmentedColormap.from_list("jarvis_radar", ["#a855f7", "#00e5ff", "#00ff88"])

def draw_flight_radar(origin_iata, plane, routes_data):
    """routes_data: list of dicts with dest_iata, dest_lat, dest_lng,
    profit_day, trips, ci, distance. Draws a two-panel display:

    LEFT — a real, bright daylight lat/lng map, tightly zoomed to the
    actual bounding box of the origin + its destinations (not a fixed
    wide view) — routes are glowing lines colored by profit.

    RIGHT — 'Profit Velocity': distance vs profit/day glow-scatter,
    dark data-panel styling.
    """
    fig = plt.figure(figsize=(13, 5.6))
    fig.patch.set_facecolor("#0d1117")

    origin_lat = routes_data[0]["origin_lat"]
    origin_lng = routes_data[0]["origin_lng"]

    # ============ LEFT: DAYLIGHT MAP, ZOOMED TO THE ROUTE CLUSTER ============
    ax1 = fig.add_subplot(1, 2, 1)
    ax1.set_facecolor("#dff2fb")  # bright daylight ocean
    ax1.set_aspect("equal")

    all_lats = [origin_lat] + [r["dest_lat"] for r in routes_data]
    all_lngs = [origin_lng] + [r["dest_lng"] for r in routes_data]
    lat_min, lat_max = min(all_lats), max(all_lats)
    lng_min, lng_max = min(all_lngs), max(all_lngs)
    lat_pad = max((lat_max - lat_min) * 0.2, 3)
    lng_pad = max((lng_max - lng_min) * 0.2, 3)
    view_lat_min, view_lat_max = lat_min - lat_pad, lat_max + lat_pad
    view_lng_min, view_lng_max = lng_min - lng_pad, lng_max + lng_pad

    # Context airports within the zoomed view — tan/land-toned dots
    with get_static_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT lat, lng FROM airports
            WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?
        """, (view_lat_min, view_lat_max, view_lng_min, view_lng_max))
        ctx_pts = cursor.fetchall()
    if ctx_pts:
        ax1.scatter([p["lng"] for p in ctx_pts], [p["lat"] for p in ctx_pts],
                    s=4, color="#c9b896", zorder=1, linewidths=0, alpha=0.9)

    max_profit = max((r["profit_day"] for r in routes_data), default=1) or 1
    day_cmap = LinearSegmentedColormap.from_list("jarvis_day", ["#3b3b98", "#c0392b", "#e67e22"])
    for r in routes_data:
        t = max(0, min(1, r["profit_day"] / max_profit))
        color = day_cmap(t)
        lw = 0.8 + t * 2.4
        ax1.plot([origin_lng, r["dest_lng"]], [origin_lat, r["dest_lat"]],
                  color=color, linewidth=lw * 2.5, alpha=0.15, zorder=2, solid_capstyle="round")
        ax1.plot([origin_lng, r["dest_lng"]], [origin_lat, r["dest_lat"]],
                  color=color, linewidth=lw, alpha=0.95, zorder=3, solid_capstyle="round")
        ax1.scatter([r["dest_lng"]], [r["dest_lat"]], s=22 + t * 42, color=color, zorder=4,
                    edgecolors="#0d1117", linewidths=0.6)

    # Origin marker — bold, high-contrast against the bright map
    ax1.scatter([origin_lng], [origin_lat], s=260, color="#1a1a2e", alpha=0.18, zorder=5, edgecolors="none")
    ax1.scatter([origin_lng], [origin_lat], s=90, color="#1a1a2e", zorder=6, edgecolors="#ffffff", linewidths=1.5)

    ax1.set_xlim(view_lng_min, view_lng_max)
    ax1.set_ylim(view_lat_min, view_lat_max)
    ax1.set_xticks([])
    ax1.set_yticks([])
    for spine in ax1.spines.values():
        spine.set_visible(False)
    ax1.set_title(f"ROUTE MAP • {origin_iata}", color="#1a1a2e", fontsize=13, fontweight="bold", loc="left", pad=10)

    # ============ RIGHT: PROFIT VELOCITY (dark data panel) ============
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.set_facecolor("#0a0e1a")

    distances = [r["distance"] for r in routes_data]
    profits = [r["profit_day"] for r in routes_data]
    trips = [r["trips"] for r in routes_data]
    cis = [r["ci"] for r in routes_data]

    sizes = [30 + t * 45 for t in trips]
    colors = [_JARVIS_CMAP(max(0, min(1, c / 60))) for c in cis]

    ax2.scatter(distances, profits, s=[s * 4 for s in sizes], c=colors, alpha=0.08, edgecolors="none", zorder=2)
    ax2.scatter(distances, profits, s=[s * 2 for s in sizes], c=colors, alpha=0.15, edgecolors="none", zorder=3)
    ax2.scatter(distances, profits, s=sizes, c=colors, alpha=0.9, edgecolors="none", zorder=4)

    ax2.set_xlabel("Distance (km)", color="#8e9ac0", fontsize=10)
    ax2.set_ylabel("Profit / day ($)", color="#8e9ac0", fontsize=10)
    ax2.tick_params(colors="#8e9ac0", labelsize=8)
    ax2.grid(alpha=0.08, color="#8e9ac0", linestyle=":")
    for spine in ax2.spines.values():
        spine.set_color("#2a3450")
    ax2.set_title("PROFIT VELOCITY", color="#00ff88", fontsize=13, fontweight="bold", loc="left", pad=10)

    fig.text(0.5, 0.02, f"Aircraft: {plane['name']}  •  Node size = trips/day  •  Node color = CI margin",
              color="#4a5570", fontsize=8, ha="center")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="#0d1117", dpi=100)
    buf.seek(0)
    plt.close(fig)
    return buf


def get_top_alternative_routes(origin, plane, user_id, exclude_dest=None, limit=3):
    """Top profitable routes from `origin` with `plane`, excluding the
    current destination — used for the 'Related Routes' summary."""
    origin = origin.upper()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (origin,))
        routes = cursor.fetchall()

    results = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            if exclude_dest and dest.upper() == exclude_dest.upper():
                continue
            distance = float(dist)
            if distance > float(plane["range"]):
                continue
            y, j, f = int(y), int(j), int(f)
            if y + j + f == 0:
                continue
            route_dict = {"distance": distance, "y": y, "j": j, "f": f, "cargo": 0}
            result = calc(route_dict, plane, user_id)
            if result["profit_day"] <= 0:
                continue
            results.append((dest, result["profit_day"]))
        except:
            continue

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]

async def generate_voice_audio(text, voice="en-US-ChristopherNeural"):
    """Turns dynamic text into an in-memory MP3 using a male neural
    voice (Microsoft Edge TTS — free, no ffmpeg/voice-client needed).
    This is a standalone audio file attached to the message, not a
    live voice-channel broadcast."""
    try:
        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice=voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"⚠️ Voice summary generation failed: {e}")
        return None

def build_route_voice_text(frm, to, plane, result, stop_airport=None):
    """Builds a plain-language summary straight from the real calc()
    result — every number here is read live from `result`, nothing
    scripted or hardcoded."""
    via = f" via {stop_airport}" if stop_airport else ""
    parts = [
        f"Route analysis for {frm.upper()} to {to.upper()}{via}, using the {plane['name']}.",
        f"Distance is {result['distance']} kilometers, running {result['trips']} trips per day.",
    ]
    if result["profit_day"] > 0:
        parts.append(
            f"Daily profit comes to {result['profit_day']} dollars, "
            f"with a cost index margin of {result['ci']} percent."
        )
    else:
        parts.append("Warning — this route is currently running at a loss.")
    if result.get("contribution_day"):
        parts.append(f"Alliance contribution is about {round(result['contribution_day'])} dollars per day.")
    return " ".join(parts)

@bot.hybrid_command(description="Full route analysis — profit, demand, seat config, pricing, contribution")
@app_commands.describe(frm="Origin airport", to="Destination airport", plane_name="Aircraft", ci="Cost Index 0-200 (default 200)")
@app_commands.autocomplete(frm=airport_autocomplete, to=airport_autocomplete, plane_name=aircraft_autocomplete)
async def route(ctx, frm: str, to: str, plane_name: str, ci: int = 200):
    await ctx.defer()
    route = get_route(frm, to)
    plane = get_plane(plane_name)
    if not route:
        return await ctx.send("❌ Route not found")
    if not plane:
        return await ctx.send("❌ Plane not found")
    
    distance_total = float(route["distance"])
    plane_range = float(plane["range"])
    stop_airport = None
    stop_leg1 = None
    stop_leg2 = None

    if distance_total > plane_range:
        # Best Stopover Selector: evaluate every airport reachable from
        # the origin (leg1 <= range) from which the destination is ALSO
        # reachable (leg2 <= range), and pick whichever gives the best
        # combined profit — not just the geographically nearest one.
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes
                WHERE f_iata = ? AND CAST(distance AS REAL) <= ?
                LIMIT 200
            """, (frm.upper(), plane_range))
            leg1_candidates = cursor.fetchall()

        best_combined_profit = -1
        for cand in leg1_candidates:
            cand_iata, cand_dist, cy, cj, cf = cand
            if int(cy) + int(cj) + int(cf) == 0:
                continue
            leg2_route = get_route(cand_iata, to)
            if not leg2_route or leg2_route["distance"] > plane_range:
                continue
            leg1_route = {"distance": float(cand_dist), "y": int(cy), "j": int(cj), "f": int(cf), "cargo": 0}
            try:
                leg1_result = calc(leg1_route, plane, ctx.author.id, cost_index=ci)
                leg2_result = calc(leg2_route, plane, ctx.author.id, cost_index=ci)
                combined = leg1_result["profit_day"] + leg2_result["profit_day"]
            except:
                continue
            if combined > best_combined_profit:
                best_combined_profit = combined
                stop_airport = cand_iata
                stop_leg1 = leg1_result
                stop_leg2 = leg2_result

    result = calc(route, plane, ctx.author.id, cost_index=ci)
    mode = result["mode"]
    
    from_txt = airport_name(frm)
    to_txt = airport_name(to)
    if stop_airport:
        stop_txt = airport_name(stop_airport)
        legs = [("┌", from_txt), ("├", stop_txt), ("└", to_txt)]
    else:
        legs = [("┌", from_txt), ("└", to_txt)]
    route_display = format_route_display(legs)

    embed = discord.Embed(title=f"{plane['name']} • Route Analysis V4.0", description=f"```{route_display}```", color=route_health_color(result["ci"]))
    embed.add_field(name="✈ Flight Info", value=f"**Distance:** {int(distance_total):,} km\n**Trips:** {result['trips']}/day\n**Flight Time:** {result['time']} hr\n**Mode:** {mode.upper()}\n**Cost Index:** {result['cost_index']}", inline=False)
    embed.add_field(name="📊 Demand", value=f"**Y:** {route['y']}\n**J:** {route['j']}\n**F:** {route['f']}", inline=True)
    embed.add_field(name="⚙ Configuration", value=f"**Y:** {result['y']}\n**J:** {result['j']}\n**F:** {result['f']}", inline=True)
    embed.add_field(name="🎟 Ticket Pricing", value=f"**Y:** ${result['y_price']:,}\n**J:** ${result['j_price']:,}\n**F:** ${result['f_price']:,}", inline=True)
    embed.add_field(name="💰 Per Flight", value=f"**Income:** ${result['income_trip']:,}\n**Fuel:** ${result['fuel']:,}\n**CO2:** ${result['co2']:,}\n**Maint:** ${result['acheck'] + result['repair']:,}\n\n**Profit:** ${result['profit_trip']:,}\n**CI Margin:** {result['ci']}%\n**Contribution:** ${result['contribution_trip']:,}", inline=False)
    embed.add_field(name="📅 Per Day", value=f"**Income:** ${result['income_day']:,}\n**Fuel:** ${result['fuel_day']:,}\n**CO2:** ${result['co2_day']:,}\n**Maint:** ${(result['acheck'] + result['repair']) * result['trips']:,}\n\n**Profit:** ${result['profit_day']:,}\n**Contribution:** ${result['contribution_day']:,}\n**Flights:** {result['trips']}", inline=False)

    if stop_airport and stop_leg1 and stop_leg2:
        embed.add_field(
            name="🔀 Best Stopover (auto-selected by combined profit)",
            value=f"**{frm.upper()} → {stop_airport}:** ${stop_leg1['profit_day']:,}/day\n"
                  f"**{stop_airport} → {to.upper()}:** ${stop_leg2['profit_day']:,}/day\n"
                  f"**Combined:** ${stop_leg1['profit_day'] + stop_leg2['profit_day']:,}/day",
            inline=False
        )

    # ---- Break-even Calculator (feature 2) ----
    aircraft_cost = plane.get("cost", 0)
    if result["profit_day"] > 0 and aircraft_cost:
        payback_days = aircraft_cost / result["profit_day"]
        annual_roi = (result["profit_day"] * 365 / aircraft_cost) * 100
        embed.add_field(
            name="💵 Break-Even",
            value=f"**Payback:** {payback_days:,.0f} days\n**Annual ROI:** {annual_roi:,.0f}%",
            inline=True
        )
    elif aircraft_cost:
        embed.add_field(name="💵 Break-Even", value="⚠️ Route runs at a loss — no payback at this CI/mode.", inline=True)

    # ---- Fleet Saturation Planner (feature 4) ----
    total_demand = route["y"] + route["j"] + route["f"]
    cap = plane.get("capacity", 0)
    demand_trips_needed = max(1, -(-total_demand // cap)) if cap else 1
    technical_max = max(1, int(24 / result["time"])) if result["time"] else 1
    if demand_trips_needed > technical_max:
        fleet_needed = -(-demand_trips_needed // technical_max)
        embed.add_field(
            name="✈️ Fleet Saturation",
            value=f"**{fleet_needed} aircraft** needed to fully cover this route's demand\n(1 aircraft only manages {result['trips']}/{demand_trips_needed} required trips)",
            inline=True
        )
    else:
        embed.add_field(name="✈️ Fleet Saturation", value="✅ 1 aircraft fully covers this route's demand", inline=True)

    # ---- CI Optimization — the value-add a fixed-CI calculator can't offer ----
    best_profit, best_contrib = find_optimal_ci(route, plane, ctx.author.id)
    if best_profit["cost_index"] != ci or best_contrib["cost_index"] != ci:
        opt_lines = []
        if best_profit["cost_index"] != ci:
            opt_lines.append(f"💰 **Max Profit:** CI {best_profit['cost_index']} → ${best_profit['profit_day']:,}/day ({best_profit['trips']} trips)")
        if best_contrib["cost_index"] != ci:
            opt_lines.append(f"🏆 **Max Contribution:** CI {best_contrib['cost_index']} → ${best_contrib['contribution_day']:,}/day ({best_contrib['trips']} trips)")
        if opt_lines:
            embed.add_field(name="🎯 CI Optimization (vs. your CI " + str(ci) + ")", value="\n".join(opt_lines), inline=False)

    alternatives = get_top_alternative_routes(frm, plane, ctx.author.id, exclude_dest=to, limit=3)
    if alternatives:
        alt_text = "\n".join(f"• {frm.upper()} → **{d}** ({airport_city_country(d)}) — ${p:,}/day" for d, p in alternatives)
        embed.add_field(name="🔗 Related Routes from " + frm.upper(), value=alt_text, inline=False)

    embed.set_footer(text="JARVIS • AERO CROWN DYNASTY OFFICIAL BOT")
    
    report_data = {
        "Route": f"{frm.upper()} -> {to.upper()}",
        "Aircraft": plane["name"],
        "Distance": f"{int(distance_total):,} km",
        "Mode": mode.upper(),
        "Cost Index": result["cost_index"],
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
        "Contribution/Day": result["contribution_day"],
        "CI": f"{result['ci']}%"
    }
    
    img_buf = draw_aircraft_card(plane, result, route, frm, to)
    image_file = discord.File(img_buf, filename="route.png")
    embed.set_image(url="attachment://route.png")

    await ctx.send(embed=embed, file=image_file, view=ExportView(report_data))

    # Voice summary sent as a quick separate follow-up — this way the
    # main result never waits on the edge-tts network round-trip.
    voice_text = build_route_voice_text(frm, to, plane, result, stop_airport=stop_airport)
    voice_buf = await generate_voice_audio(voice_text)
    if voice_buf:
        await ctx.send(file=discord.File(voice_buf, filename="route_summary.mp3"))

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

@bot.hybrid_command(description="Compare two aircraft head-to-head (e.g. 'A320 vs B737')")
async def compare(ctx, *, planes_input: str):
    await ctx.defer()
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
@bot.hybrid_command(description="Best aircraft for a specific route")
@app_commands.describe(frm="Origin airport", to="Destination airport")
@app_commands.autocomplete(frm=airport_autocomplete, to=airport_autocomplete)
async def best(ctx, frm: str, to: str):
    route = get_route(frm, to)
    if not route:
        return await ctx.send("Route not found")
    await ctx.defer()
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
    route_display = format_route_display([("┌", airport_name(frm)), ("└", airport_name(to))])
    embed = discord.Embed(title="Best Aircraft", description=f"```{route_display}```", color=route_health_color(best_calc["ci"]))
    embed.add_field(name="Aircraft", value=f"**{best_plane['name']}**", inline=False)
    embed.add_field(name="Profit/Day", value=f"**{money(best_calc['profit_day'])}**", inline=True)
    embed.add_field(name="Trips/Day", value=f"**{best_calc['trips']}**", inline=True)
    embed.add_field(name="Mode", value=f"**{best_calc['mode'].upper()}**", inline=False)
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
def airport_city_country(iata):
    """Compact 'City, Country' form for use in lists (vs. airport_name()'s
    multi-line form, which is meant for single-route headline display)."""
    full = airport_name(iata)
    if "\n" in full:
        return full.split("\n", 1)[1]
    return iata

def format_route_display(legs):
    """Tree-style connector formatting for a route's airports.
    legs: list of (connector_char, airport_text) where airport_text is
    airport_name()'s 'IATA • Name\\nCity, Country' output. Draws:
        ┌ DEL • Indira Gandhi Intl
        │   New Delhi, India
        ├ XXX • Stopover Name          (only if a stopover leg is passed)
        │   City, Country
        └ BOM • Chhatrapati Shivaji Intl
            Mumbai, India
    """
    lines = []
    for i, (connector, text) in enumerate(legs):
        parts = text.split("\n", 1)
        lines.append(f"{connector} {parts[0]}")
        if len(parts) > 1:
            cont_char = "│" if i < len(legs) - 1 else " "
            lines.append(f"{cont_char}   {parts[1]}")
    return "\n".join(lines)

def route_health_color(ci_margin):
    """Embed strip color reflecting profit-margin health — green/amber/red,
    no extra emoji needed."""
    if ci_margin >= 30:
        return 0x2ecc71  # healthy
    elif ci_margin >= 15:
        return 0xf1c40f  # thin but workable
    else:
        return 0xe74c3c  # weak/risky

def _looks_like_airport_code(token):
    return token.isalpha() and 2 <= len(token) <= 4

async def _best_world_scan(ctx, plane_name):
    """Old behaviour, unchanged: world-wide top-10 scan for one aircraft."""
    plane = get_plane(plane_name)
    if not plane:
        return await ctx.send("❌ Plane not found")

    msg = await ctx.send(f"🔍 Scanning routes world-wide for **{plane['name']}**... this can take a few seconds.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f_iata, t_iata, distance, dem_y, dem_j, dem_f FROM routes
            WHERE CAST(distance AS REAL) <= ?
            LIMIT 8000
        """, (float(plane["range"]),))
        candidates = cursor.fetchall()

    results = []
    for r in candidates:
        try:
            frm_i, to_i, dist, y, j, f = r
            y, j, f = int(y), int(j), int(f)
            if y + j + f == 0:
                continue
            route_dict = {"distance": float(dist), "y": y, "j": j, "f": f, "cargo": 0}
            result = calc(route_dict, plane, ctx.author.id)
            if result["profit_day"] <= 0:
                continue
            results.append((frm_i, to_i, float(dist), result["profit_day"], result["trips"], result["ci"]))
        except:
            continue

    if not results:
        return await msg.edit(content=f"❌ No profitable routes found world-wide for **{plane['name']}**.")

    results.sort(key=lambda x: x[3], reverse=True)
    top = results[:10]

    text = ""
    for i, res in enumerate(top, 1):
        frm_i, to_i, dist, profit, trips, ci = res
        text += f"**{i}. {frm_i} → {to_i}**\n${profit:,}/day  •  {int(dist):,} km  •  {trips} trips/day  •  CI margin {ci}%\n\n"

    embed = discord.Embed(
        title=f"🌍 World's Best Routes • {plane['name']}",
        description=text,
        color=0x00e5ff
    )
    embed.set_footer(text=f"Scanned {len(candidates):,} candidate routes (capped at 8,000 for performance) • JARVIS")
    await msg.edit(content=None, embed=embed)

async def _best_world_from_origin(ctx, origin, plane_name, max_distance):
    """New mode: !best_world <origin> <plane> [max_km] — scan every
    route FROM this one origin (same engine as !best_r), optionally
    capped by max_distance. If you already know both endpoints, use
    !route instead — this is for 'where should I fly FROM here'."""
    plane = get_plane(plane_name)
    if not plane:
        return await ctx.send("❌ Plane not found")

    results, total_routes = scan_routes_from_origin(ctx, origin, plane, max_distance=max_distance)

    if total_routes == 0:
        return await ctx.send(f"❌ No routes found from **{origin}**")

    if not results:
        limit_note = f" within your {max_distance:,} km limit" if max_distance else ""
        return await ctx.send(
            f"❌ No profitable routes found from **{origin}** with **{plane['name']}**{limit_note}."
        )

    top = results[:10]
    origin_txt = airport_name(origin)
    text = ""
    for i, res in enumerate(top, 1):
        dest, dist, profit, trips, ci = res
        dest_loc = airport_city_country(dest)
        text += f"**{i}. {origin} → {dest}** ({dest_loc})\n${profit:,}/day  •  {dist:,} km  •  {trips} trips/day  •  CI margin {ci}%\n\n"

    embed = discord.Embed(
        title=f"🌍 Best Routes from {origin} • {plane['name']}",
        description=f"**From:** {origin_txt}\n\n{text}",
        color=0x00e5ff
    )
    limit_note = f" • Capped at {max_distance:,} km" if max_distance else ""
    embed.set_footer(text=f"Scanned {total_routes:,} routes from {origin}{limit_note} • JARVIS")
    await ctx.send(embed=embed)

@bot.hybrid_command(name="best_world", description="World-wide best routes for an aircraft, OR best routes from one origin with a distance cap")
@app_commands.describe(query="Just an aircraft (world-scan), OR 'ORIGIN AIRCRAFT [max_km]' for one origin")
async def best_world(ctx, *, query: str):
    await ctx.defer()
    tokens = query.strip().split()

    specific_mode = len(tokens) >= 2 and _looks_like_airport_code(tokens[0])

    if not specific_mode:
        return await _best_world_scan(ctx, query)

    origin = tokens[0].upper()
    rest = tokens[1:]
    max_distance = None
    if rest and re.match(r"^\d+(km)?$", rest[-1], re.IGNORECASE):
        max_distance = int(re.sub(r"\D", "", rest[-1]))
        rest = rest[:-1]
    plane_name = " ".join(rest).strip()

    if not plane_name:
        return await ctx.send("❌ Give an aircraft name — e.g. `best_world DEL A380` or `best_world DEL A380 9500km`")

    await _best_world_from_origin(ctx, origin, plane_name, max_distance)



def draw_whatif_heatmap(planes, ci_values, matrix, frm, to):
    """Aircraft x Cost-Index profit/day heatmap — feature 3."""
    fig, ax = plt.subplots(figsize=(7.5, 1.6 + 1.1 * len(planes)))
    fig.patch.set_facecolor("#0a0e1a")
    ax.set_facecolor("#0a0e1a")

    n_rows = len(planes)
    n_cols = len(ci_values)

    valid_vals = [v for row in matrix for v in row if v is not None]
    vmin, vmax = (min(valid_vals), max(valid_vals)) if valid_vals else (0, 1)
    if vmax == vmin:
        vmax = vmin + 1

    for i in range(n_rows):
        for j in range(n_cols):
            val = matrix[i][j]
            if val is None:
                color = "#2a3450"
                label = "OUT OF\nRANGE"
                text_color = "#8e9ac0"
            else:
                t = (val - vmin) / (vmax - vmin)
                color = _JARVIS_CMAP(t)
                label = f"${val:,.0f}"
                text_color = "#0a0e1a"
            rect = plt.Rectangle((j, n_rows - i - 1), 1, 1, facecolor=color, edgecolor="#0a0e1a", linewidth=2)
            ax.add_patch(rect)
            ax.text(j + 0.5, n_rows - i - 1 + 0.5, label, ha="center", va="center",
                    color=text_color, fontsize=8.5, fontweight="bold")

    ax.set_xlim(0, n_cols)
    ax.set_ylim(0, n_rows)
    ax.set_xticks([j + 0.5 for j in range(n_cols)])
    ax.set_xticklabels([f"CI {c}" for c in ci_values], color="#8e9ac0", fontsize=9)
    ax.set_yticks([n_rows - i - 1 + 0.5 for i in range(n_rows)])
    ax.set_yticklabels([p["name"] for p in planes], color="#8e9ac0", fontsize=9)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(f"PROFIT/DAY MATRIX • {frm.upper()} → {to.upper()}", color="#00e5ff", fontsize=12, fontweight="bold", pad=12)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor="#0a0e1a", dpi=100)
    buf.seek(0)
    plt.close(fig)
    return buf

@bot.hybrid_command(name="whatif", description="Compare 2-4 aircraft across Cost Index settings in one heatmap")
@app_commands.describe(frm="Origin airport", to="Destination airport", planes="Comma-separated aircraft, e.g. 'a380, 777, 747'")
@app_commands.autocomplete(frm=airport_autocomplete, to=airport_autocomplete)
async def whatif(ctx, frm: str, to: str, *, planes: str):
    await ctx.defer()
    route = get_route(frm, to)
    if not route:
        return await ctx.send("❌ Route not found")

    plane_names = [p.strip() for p in planes.split(",") if p.strip()][:4]
    resolved_planes = []
    for name in plane_names:
        p = get_plane(name)
        if p:
            resolved_planes.append(p)
    if len(resolved_planes) < 2:
        return await ctx.send("❌ Need at least 2 valid aircraft, comma-separated — e.g. `a380, 777, 747`")

    ci_values = [0, 70, 140, 200]
    matrix = []
    for p in resolved_planes:
        row_vals = []
        for ci_val in ci_values:
            if route["distance"] > p["range"]:
                row_vals.append(None)
                continue
            result = calc(route, p, ctx.author.id, cost_index=ci_val)
            row_vals.append(result["profit_day"])
        matrix.append(row_vals)

    img_buf = draw_whatif_heatmap(resolved_planes, ci_values, matrix, frm, to)
    file = discord.File(img_buf, filename="whatif.png")
    embed = discord.Embed(title=f"🧮 What-If Matrix • {frm.upper()} → {to.upper()}", description="Profit/day across aircraft & Cost Index — greener = better", color=0xa855f7)
    embed.set_image(url="attachment://whatif.png")
    embed.set_footer(text="JARVIS • AERO CROWN DYNASTY OFFICIAL BOT")
    await ctx.send(embed=embed, file=file)

@bot.hybrid_command(name="routemap", description="Flight Radar — glowing route map + profit-vs-distance chart from an airport")
@app_commands.describe(airport="Origin airport", plane_name="Aircraft")
@app_commands.autocomplete(airport=airport_autocomplete, plane_name=aircraft_autocomplete)
async def routemap(ctx, airport: str, *, plane_name: str):
    await ctx.defer()
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        return await ctx.send("❌ Plane not found")

    with get_static_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT lat, lng FROM airports WHERE iata = ? LIMIT 1", (airport,))
        origin_row = cursor.fetchone()
    if not origin_row:
        return await ctx.send(f"❌ No coordinates on file for **{airport}** — can't plot the radar.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (airport,))
        routes = cursor.fetchall()
    if not routes:
        return await ctx.send(f"❌ No routes found from **{airport}**")

    dest_iatas = [r[0] for r in routes]
    with get_static_db() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(dest_iatas))
        cursor.execute(f"SELECT iata, lat, lng FROM airports WHERE iata IN ({placeholders})", dest_iatas)
        coord_map = {row["iata"]: (row["lat"], row["lng"]) for row in cursor.fetchall()}

    routes_data = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = float(dist)
            if distance > float(plane["range"]):
                continue
            y, j, f = int(y), int(j), int(f)
            if y + j + f == 0:
                continue
            if dest not in coord_map:
                continue
            route_dict = {"distance": distance, "y": y, "j": j, "f": f, "cargo": 0}
            result = calc(route_dict, plane, ctx.author.id)
            if result["profit_day"] <= 0:
                continue
            dest_lat, dest_lng = coord_map[dest]
            routes_data.append({
                "dest_iata": dest, "dest_lat": dest_lat, "dest_lng": dest_lng,
                "origin_lat": origin_row["lat"], "origin_lng": origin_row["lng"],
                "profit_day": result["profit_day"], "trips": result["trips"],
                "ci": result["ci"], "distance": distance
            })
        except:
            continue

    if not routes_data:
        return await ctx.send(f"❌ No profitable routes found from **{airport}** with **{plane['name']}** to plot.")

    img_buf = draw_flight_radar(airport, plane, routes_data)
    file = discord.File(img_buf, filename="radar.png")
    embed = discord.Embed(
        title=f"📡 Flight Radar • {airport}",
        description=f"**{len(routes_data)}** profitable routes plotted with **{plane['name']}**",
        color=0x00e5ff
    )
    embed.set_image(url="attachment://radar.png")
    embed.set_footer(text="JARVIS • AERO CROWN DYNASTY OFFICIAL BOT")
    await ctx.send(embed=embed, file=file)

def scan_routes_from_origin(ctx, airport, plane, max_distance=None):
    """Shared by !best_r and best_world's origin-mode: scans every route
    from `airport` with `plane`, capped by the aircraft's real range
    (and further capped by max_distance if given), returns results
    sorted by profit/day descending. Each result:
    (dest, distance_int, profit_day, trips, ci)."""
    effective_range = min(float(plane["range"]), max_distance) if max_distance else float(plane["range"])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (airport,))
        routes = cursor.fetchall()

    results = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = float(dist)
            if distance > effective_range:
                continue
            y, j, f = int(y), int(j), int(f)
            if y + j + f == 0:
                continue
            route_dict = {"distance": distance, "y": y, "j": j, "f": f, "cargo": 0}
            result = calc(route_dict, plane, ctx.author.id)
            if result["profit_day"] <= 0:
                continue
            results.append((dest, int(distance), result["profit_day"], result["trips"], result["ci"]))
        except:
            continue

    results.sort(key=lambda x: x[2], reverse=True)
    return results, len(routes)

@bot.hybrid_command(name="best_r", aliases=["bestr", "top"], description="Top 5 most profitable routes from an airport")
@app_commands.describe(airport="Origin airport", plane_name="Aircraft")
@app_commands.autocomplete(airport=airport_autocomplete, plane_name=aircraft_autocomplete)
async def best_r(ctx, airport: str, *, plane_name: str):
    await ctx.defer()
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        return await ctx.send("❌ Plane not found")
    mode = get_user_mode(ctx.author.id)

    results, total_routes = scan_routes_from_origin(ctx, airport, plane)

    if total_routes == 0:
        return await ctx.send(f"❌ No routes found from **{airport}**")

    if not results:
        return await ctx.send(
            f"❌ No profitable routes found from **{airport}** with **{plane['name']}** "
            f"within its {int(plane['range']):,} km range.\n"
            f"Try a different aircraft, or check `!difficulty` — realism has higher costs than easy."
        )

    top = results[:5]

    origin_txt = airport_name(airport)
    text = ""
    for i, res in enumerate(top, start=1):
        dest, dist, profit, trips, ci = res
        dest_loc = airport_city_country(dest)
        text += f"**{i}. {airport} → {dest}** ({dest_loc})\n`Profit` ${profit:,}/day\n`Trips` {trips}/day\n`CI` {ci}%\n`Range` {dist:,} km\n\n"

    embed = discord.Embed(
        title=f"🏆 Best Routes • {plane['name']}",
        description=f"**From:** {origin_txt}\n\n{text}",
        color=0x2b2d31
    )
    embed.add_field(name="Analysis", value=f"`Airport:` {airport}\n`Aircraft:` {plane['name']}\n`Mode:` {mode.upper()}", inline=False)
    embed.set_footer(text="JARVIS • Smart Route Optimization")

    export_data = {"Airport": airport, "Aircraft": plane["name"], "Mode": mode}
    for i, res in enumerate(top, start=1):
        dest, dist, profit, trips, ci = res
        export_data[f"#{i} Route"] = f"{airport}->{dest}"
        export_data[f"#{i} Profit"] = profit
        export_data[f"#{i} Trips"] = trips
        export_data[f"#{i} CI"] = ci
        export_data[f"#{i} Range"] = dist
    export_view = ExportView(export_data)
    await ctx.send(embed=embed)
    await ctx.send("Download Route Report", view=export_view)

async def _best_route_by_distance(ctx, airport, plane_name, min_dist, max_dist, label, emoji, color):
    """Shared engine for best_short / best_long — same calc() everyone else uses."""
    await ctx.defer()
    airport = airport.upper()
    plane = get_plane(plane_name)
    if not plane:
        await ctx.send("❌ Plane not found")
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT t_iata, distance, dem_y, dem_j, dem_f FROM routes WHERE f_iata = ? LIMIT 300", (airport,))
        routes = cursor.fetchall()

    if not routes:
        await ctx.send(f"❌ No routes found from **{airport}**")
        return

    results = []
    for r in routes:
        try:
            dest, dist, y, j, f = r
            distance = to_float(dist)
            if distance <= min_dist or distance > max_dist or distance > plane["range"]:
                continue
            y, j, f = int(y), int(j), int(f)
            if y + j + f == 0:
                continue
            route_dict = {"distance": distance, "y": y, "j": j, "f": f, "cargo": 0}
            result = calc(route_dict, plane, ctx.author.id)
            if result["profit_day"] <= 0:
                continue
            results.append((dest, distance, result["profit_day"], result["trips"], result["ci"]))
        except:
            continue

    if not results:
        await ctx.send(
            f"❌ No profitable **{label}** routes found from **{airport}** with **{plane['name']}**.\n"
            f"Try a different aircraft, or check `!difficulty`."
        )
        return

    results.sort(key=lambda x: x[2], reverse=True)
    top = results[:5]

    origin_txt = airport_name(airport)
    text = ""
    for i, res in enumerate(top, 1):
        dest, dist, profit, trips, ci = res
        dest_loc = airport_city_country(dest)
        text += f"**{i}. {airport} → {dest}** ({dest_loc})\n📏 {int(dist):,} km  •  💰 ${profit:,}/day  •  🔁 {trips}/day  •  CI {ci}%\n\n"

    embed = discord.Embed(
        title=f"{emoji} Best {label.upper()} Routes • {plane['name']}",
        description=f"**From:** {origin_txt}\n\n{text}",
        color=color
    )
    embed.set_footer(text="JARVIS - AERO CROWN DYNASTY ™")
    await ctx.send(embed=embed)

@bot.hybrid_command(name="best_short", description="Top 5 profitable short-haul routes (<=3000km) from an airport")
@app_commands.describe(airport="Origin airport", plane_name="Aircraft")
@app_commands.autocomplete(airport=airport_autocomplete, plane_name=aircraft_autocomplete)
async def best_short(ctx, airport: str, *, plane_name: str):
    await _best_route_by_distance(ctx, airport, plane_name, min_dist=0, max_dist=3000, label="short", emoji="⚡", color=0x00ffcc)

@bot.hybrid_command(name="best_long", description="Top 5 profitable long-haul routes (>3000km) from an airport")
@app_commands.describe(airport="Origin airport", plane_name="Aircraft")
@app_commands.autocomplete(airport=airport_autocomplete, plane_name=aircraft_autocomplete)
async def best_long(ctx, airport: str, *, plane_name: str):
    await _best_route_by_distance(ctx, airport, plane_name, min_dist=3000, max_dist=float("inf"), label="long", emoji="🌍", color=0xff9900)

# =========================
# ON READY — sync slash commands
# =========================
_synced = False
_agent_loaded = False

@bot.event
async def on_ready():
    global _synced, _agent_loaded

    print(f"✅ JARVIS online as {bot.user}")

    if not _agent_loaded:
        try:
            setup_agent(bot, supabase_get, supabase_post)
            _agent_loaded = True
            print("🤖 AM4 Agent loaded successfully.")
        except Exception as e:
            print(f"❌ AM4 Agent setup failed: {e}")
            return

    if not _synced:
        try:
            synced_cmds = await bot.tree.sync()
            print(f"🔧 Synced {len(synced_cmds)} slash command(s).")
            _synced = True
        except Exception as e:
            print(f"⚠️ Slash command sync failed: {e}")
            
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
        async with message.channel.typing():
            ai_reply = await get_groq_reply(message.author.id, msg)
        if ai_reply:
            await message.channel.send(f"{message.author.mention} {ai_reply}")
        else:
            replies = [f"{message.author.mention} I'm not fully sure, but I can try helping. Can you rephrase?", f"{message.author.mention} 🤔 I need a bit more context.", f"{message.author.mention} I don't have a direct match for that, but I'm listening."]
            await message.channel.send(random.choice(replies))
    await bot.process_commands(message)


# =========================
# RUN BOT
# =========================
if __name__ == "__main__":
    keep_alive()
    if not TOKEN:
        print("ERROR: TOKEN environment variable missing.")
    else:
        bot.run(TOKEN)
