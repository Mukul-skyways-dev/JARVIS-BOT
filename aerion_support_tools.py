"""
AERION Support Tools
====================

Command module for AM4 calculator/support features that do not require a live
connection to Airline Manager 4.

The module deliberately does not read game state. It uses the query functions
from bot1.py through QUERY_MAP:

    setup_support_tools(bot, {
        "get_route": get_route,
        "get_plane": get_plane,
        "get_all_planes": get_all_planes,
        "calc": calc,
        "find_optimal_ci": find_optimal_ci,
        "airport_name": airport_name,
        "airport_city_country": airport_city_country,
        "airport_autocomplete": airport_autocomplete,
        "aircraft_autocomplete": aircraft_autocomplete,
        "membership_required": membership_required,
    })

Commands registered:
    /compare_route
    /routecoach
    /market
    /buyadvisor
    /support
    /learn
    /faq
    /troubleshoot
    /routecard

There is intentionally no /scenario command in this module.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands


DEFAULT_FUEL_PRICE = 0.70
DEFAULT_CO2_PRICE = 0.12

_bot: Optional[commands.Bot] = None
_q: Dict[str, Callable[..., Any]] = {}
_db_path = "aerion_support.db"
_registered = False


# ---------------------------------------------------------------------------
# Small storage layer
# ---------------------------------------------------------------------------

def _ensure_storage() -> None:
    with sqlite3.connect(_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS support_market (
                scope TEXT PRIMARY KEY,
                fuel_price REAL,
                co2_price REAL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _scope(ctx: commands.Context) -> str:
    # A DM has no guild. A guild-specific market is useful because different
    # Discord servers may discuss different in-game market snapshots.
    return str(ctx.guild.id) if ctx.guild else f"user:{ctx.author.id}"


def _get_market(ctx: commands.Context) -> tuple[float, float, bool]:
    with sqlite3.connect(_db_path) as conn:
        row = conn.execute(
            "SELECT fuel_price, co2_price FROM support_market WHERE scope = ?",
            (_scope(ctx),),
        ).fetchone()
    if not row:
        return DEFAULT_FUEL_PRICE, DEFAULT_CO2_PRICE, False
    return float(row[0]), float(row[1]), True


def _set_market(ctx: commands.Context, fuel: float, co2: float) -> None:
    with sqlite3.connect(_db_path) as conn:
        conn.execute(
            """
            INSERT INTO support_market(scope, fuel_price, co2_price, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scope) DO UPDATE SET
                fuel_price = excluded.fuel_price,
                co2_price = excluded.co2_price,
                updated_at = excluded.updated_at
            """,
            (
                _scope(ctx),
                fuel,
                co2,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()


def _reset_market(ctx: commands.Context) -> None:
    with sqlite3.connect(_db_path) as conn:
        conn.execute("DELETE FROM support_market WHERE scope = ?", (_scope(ctx),))
        conn.commit()


# ---------------------------------------------------------------------------
# Shared calculation/query helpers
# ---------------------------------------------------------------------------

def _route(frm: str, to: str) -> Optional[dict]:
    return _q["get_route"](frm.upper().strip(), to.upper().strip())


def _plane(name: str) -> Optional[dict]:
    return _q["get_plane"](name)


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _with_market(result: dict, fuel_price: float, co2_price: float) -> dict:
    """
    Adjust the existing calc() result for manually entered market prices.

    The base engine already gives us physical fuel/CO2 quantities. We only
    replace their dollar costs and recalculate the dependent profit fields.
    This keeps the formula/query mapping in bot1.py as the source of truth.
    """
    out = dict(result)
    out["fuel"] = int(round(_num(result.get("fuel_lb")) * fuel_price))
    out["co2"] = int(round(_num(result.get("co2_q")) * co2_price))

    maintenance = _num(result.get("acheck")) + _num(result.get("repair"))
    out["total_cost"] = int(round(out["fuel"] + out["co2"] + maintenance))
    out["profit_trip"] = int(round(_num(result.get("income_trip")) - out["total_cost"]))
    out["fuel_day"] = int(round(out["fuel"] * _num(result.get("trips"))))
    out["co2_day"] = int(round(out["co2"] * _num(result.get("trips"))))
    out["income_day"] = int(round(_num(result.get("income_trip")) * _num(result.get("trips"))))
    out["profit_day"] = int(round(out["profit_trip"] * _num(result.get("trips"))))

    income = _num(result.get("income_trip"))
    out["ci"] = int((out["profit_trip"] / income) * 100) if income else 0
    return out


def _calculate(
    route: dict,
    plane: dict,
    user_id: int,
    ci: int,
    fuel_price: float,
    co2_price: float,
) -> dict:
    raw = _q["calc"](route, plane, user_id, cost_index=max(0, min(200, int(ci))))
    return _with_market(raw, fuel_price, co2_price)


def _best_ci(
    route: dict,
    plane: dict,
    user_id: int,
    fuel_price: float,
    co2_price: float,
) -> dict:
    best = None
    for ci in range(0, 201, 10):
        result = _calculate(route, plane, user_id, ci, fuel_price, co2_price)
        if best is None or result["profit_day"] > best["profit_day"]:
            best = result
    return best or _calculate(route, plane, user_id, 200, fuel_price, co2_price)


def _market_text(ctx: commands.Context) -> str:
    fuel, co2, manual = _get_market(ctx)
    source = "manual server snapshot" if manual else "engine defaults"
    return f"Fuel: **${fuel:.3f}/lb**\nCO₂: **${co2:.3f}/quintal**\nSource: `{source}`"


def _guard(fn):
    guard = _q.get("membership_required")
    return guard(fn) if guard else fn


def _attach_autocomplete(command: Any, mapping: dict) -> None:
    """
    Attach autocomplete handlers after a dynamically-created hybrid command.

    HybridCommand owns an app_commands.Command internally. Keeping this in a
    small compatibility helper prevents an autocomplete problem from
    preventing the entire support module from loading.
    """
    app_command = getattr(command, "app_command", None)
    if app_command is None:
        return
    for parameter, callback in mapping.items():
        if not callback:
            continue
        try:
            app_command.autocomplete(parameter)(callback)
        except Exception as exc:
            print(f"[AERION SUPPORT] autocomplete skipped for {parameter}: {exc}")


def _airport_label(iata: str) -> str:
    try:
        return _q["airport_name"](iata)
    except Exception:
        return iata.upper()


def _location(iata: str) -> str:
    try:
        return _q["airport_city_country"](iata)
    except Exception:
        return iata.upper()


def _route_display(frm: str, to: str) -> str:
    return f"{frm.upper()} → {to.upper()}\n{_location(frm)} → {_location(to)}"


def _range_warning(route: dict, plane: dict) -> Optional[str]:
    distance = _num(route.get("distance"))
    aircraft_range = _num(plane.get("range"))
    if distance > aircraft_range:
        return (
            f"❌ Route distance is **{distance:,.0f} km**, but this aircraft "
            f"has only **{aircraft_range:,.0f} km** range."
        )
    return None


def _result_line(label: str, result: dict) -> str:
    return (
        f"**{label}**\n"
        f"Profit/day: {_money(result['profit_day'])} • "
        f"Profit/flight: {_money(result['profit_trip'])}\n"
        f"CI: `{result['cost_index']}` • Trips: `{result['trips']}` • "
        f"Seats: `{result['y']}Y / {result['j']}J / {result['f']}F`"
    )


# ---------------------------------------------------------------------------
# Support content
# ---------------------------------------------------------------------------

FAQS = {
    "cost-index": (
        "Cost Index controls the speed-versus-cost trade-off. A higher CI "
        "usually shortens flight time but increases fuel and CO₂ expense. "
        "Use `/routecoach` to scan CI 0–200 for the best daily profit."
    ),
    "seat-config": (
        "Seat configuration should follow route demand while respecting the "
        "aircraft's weighted capacity. `/routecoach` shows the engine's "
        "recommended Y/J/F configuration."
    ),
    "a-check": (
        "A-check and repair costs are included in the route result. Compare "
        "them with `/compare_route` rather than choosing an aircraft only by "
        "purchase price."
    ),
    "stopover": (
        "When a route is outside an aircraft's range, the main `/route` "
        "command searches for a reachable stopover. `/routecoach` will still "
        "warn you when the selected direct leg is impossible."
    ),
    "cargo": (
        "Cargo demand is included by the main route engine where it exists in "
        "the database. If your current in-game market differs, use the manual "
        "market values before comparing scenarios."
    ),
    "membership": (
        "Use `/link` to connect your portal profile, `/aerion` to see status, "
        "and `/subscribe` to activate or renew membership."
    ),
}

FAQ_ALIASES = {
    "ci": "cost-index",
    "cost index": "cost-index",
    "seats": "seat-config",
    "seat": "seat-config",
    "configuration": "seat-config",
    "maintenance": "a-check",
    "repair": "a-check",
    "range": "stopover",
    "portal": "membership",
}

TROUBLESHOOTING = {
    "low-profit": (
        "Check these in order:\n"
        "1. Run `/routecoach` and use its recommended CI.\n"
        "2. Compare a smaller and larger aircraft with `/compare_route`.\n"
        "3. Check whether your manual fuel/CO₂ prices are current.\n"
        "4. Verify that your cabin configuration follows demand."
    ),
    "loss": (
        "A loss usually comes from high operating cost, a weak demand mix, "
        "too few profitable trips, or an outdated market assumption. Run "
        "`/routecoach` first; it will identify the most direct warning."
    ),
    "insufficient-range": (
        "The aircraft cannot fly that direct leg. Use the main `/route` "
        "command to evaluate an automatic stopover, or choose an aircraft "
        "with a longer range."
    ),
    "wrong-seats": (
        "Do not fill seats equally by default. Demand is different for Y, J, "
        "and F. `/routecoach` calculates a demand-aware configuration."
    ),
    "market": (
        "The bot is not connected to the game market. Enter the values you "
        "see in AM4 with `/market set fuel:<value> co2:<value>`."
    ),
}


def _find_topic(query: str, collection: dict, aliases: dict) -> Optional[str]:
    cleaned = " ".join((query or "").lower().strip().split())
    if cleaned in collection:
        return cleaned
    if cleaned in aliases:
        return aliases[cleaned]
    for key in collection:
        if key in cleaned or cleaned in key:
            return key
    return None


class SupportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    async def _send_topic(self, interaction: discord.Interaction, topic: str):
        text = FAQS.get(topic, TROUBLESHOOTING.get(topic, "No guide found."))
        embed = discord.Embed(
            title=f"🧭 AERION Support • {topic.replace('-', ' ').title()}",
            description=text,
            color=0x00D4FF,
        )
        embed.set_footer(text="Use /routecoach for a route-specific diagnosis.")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Route Help", style=discord.ButtonStyle.primary, row=0)
    async def route_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_topic(interaction, "low-profit")

    @discord.ui.button(label="Aircraft & Seats", style=discord.ButtonStyle.secondary, row=0)
    async def aircraft_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_topic(interaction, "seat-config")

    @discord.ui.button(label="Cost Index", style=discord.ButtonStyle.success, row=0)
    async def ci_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_topic(interaction, "cost-index")

    @discord.ui.button(label="Market Inputs", style=discord.ButtonStyle.danger, row=1)
    async def market_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_topic(interaction, "market")

    @discord.ui.button(label="Membership", style=discord.ButtonStyle.secondary, row=1)
    async def membership_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._send_topic(interaction, "membership")

    @discord.ui.button(label="Close", style=discord.ButtonStyle.grey, row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(view=None)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def setup_support_tools(
    bot_instance: commands.Bot,
    query_map: dict,
    db_path: str = "aerion_support.db",
) -> bool:
    """
    Register every support command once.

    query_map is intentionally supplied by bot1.py. That preserves the
    existing database/query mapping and prevents this module from opening or
    duplicating the AM4 route databases.
    """
    global _bot, _q, _db_path, _registered

    if _registered:
        return False

    required = {
        "get_route",
        "get_plane",
        "get_all_planes",
        "calc",
        "airport_name",
        "airport_city_country",
    }
    missing = sorted(required - set(query_map))
    if missing:
        raise ValueError(f"AERION support tools missing query map keys: {', '.join(missing)}")

    _bot = bot_instance
    _q = dict(query_map)
    _db_path = db_path
    _ensure_storage()

    airport_ac = _q.get("airport_autocomplete")
    aircraft_ac = _q.get("aircraft_autocomplete")

    # ------------------------- /compare_route -------------------------
    @bot_instance.hybrid_command(
        name="compare_route",
        description="Compare two aircraft on a real database route",
    )
    @app_commands.describe(
        frm="Origin airport",
        to="Destination airport",
        plane1="First aircraft",
        plane2="Second aircraft",
        ci="Cost Index to compare, 0-200",
    )
    @_guard
    async def compare_route(
        ctx: commands.Context,
        frm: str,
        to: str,
        plane1: str,
        plane2: str,
        ci: int = 200,
    ):
        await ctx.defer()
        route = _route(frm, to)
        p1 = _plane(plane1)
        p2 = _plane(plane2)
        if not route:
            return await ctx.send(f"❌ Route not found: `{frm.upper()} → {to.upper()}`")
        if not p1 or not p2:
            return await ctx.send("❌ One or both aircraft could not be found.")

        fuel, co2, manual = _get_market(ctx)
        r1 = _calculate(route, p1, ctx.author.id, ci, fuel, co2)
        r2 = _calculate(route, p2, ctx.author.id, ci, fuel, co2)

        embed = discord.Embed(
            title=f"⚖️ Route Comparison • {frm.upper()} → {to.upper()}",
            description=(
                f"{_location(frm)} → {_location(to)}\n"
                f"Market: {'manual snapshot' if manual else 'engine defaults'} • CI `{max(0, min(200, ci))}`"
            ),
            color=0x3498DB,
        )
        embed.add_field(name=f"✈️ {p1['name']}", value=_result_line("Result", r1), inline=False)
        embed.add_field(name=f"✈️ {p2['name']}", value=_result_line("Result", r2), inline=False)

        winner = p1["name"] if r1["profit_day"] > r2["profit_day"] else p2["name"]
        difference = abs(r1["profit_day"] - r2["profit_day"])
        embed.add_field(
            name="Recommendation",
            value=f"**{winner}** leads by approximately **{_money(difference)}/day**.",
            inline=False,
        )
        embed.set_footer(text="AERION Support Tools • Uses your existing route engine")
        await ctx.send(embed=embed)

    _attach_autocomplete(
        compare_route,
        {
            "frm": airport_ac,
            "to": airport_ac,
            "plane1": aircraft_ac,
            "plane2": aircraft_ac,
        },
    )

    # --------------------------- /routecoach --------------------------
    @bot_instance.hybrid_command(
        name="routecoach",
        description="Diagnose a route and recommend aircraft settings",
    )
    @app_commands.describe(
        frm="Origin airport",
        to="Destination airport",
        plane_name="Aircraft",
        ci="Your current Cost Index, 0-200",
    )
    @_guard
    async def routecoach(
        ctx: commands.Context,
        frm: str,
        to: str,
        plane_name: str,
        ci: int = 200,
    ):
        await ctx.defer()
        route = _route(frm, to)
        plane = _plane(plane_name)
        if not route:
            return await ctx.send(f"❌ Route not found: `{frm.upper()} → {to.upper()}`")
        if not plane:
            return await ctx.send(f"❌ Aircraft not found: `{plane_name}`")

        range_error = _range_warning(route, plane)
        fuel, co2, manual = _get_market(ctx)
        current = _calculate(route, plane, ctx.author.id, ci, fuel, co2)
        optimal = _best_ci(route, plane, ctx.author.id, fuel, co2)

        warnings = []
        if range_error:
            warnings.append(range_error)
        if current["profit_day"] <= 0:
            warnings.append("⚠️ This configuration is currently losing money.")
        if optimal["cost_index"] != current["cost_index"]:
            delta = optimal["profit_day"] - current["profit_day"]
            if delta > 0:
                warnings.append(
                    f"💡 CI `{optimal['cost_index']}` may improve daily profit by about `{_money(delta)}`."
                )
        if route.get("y", 0) and current["y"] == 0:
            warnings.append("⚠️ Economy demand is available but no Economy seats were assigned.")
        if route.get("j", 0) and current["j"] == 0:
            warnings.append("⚠️ Business demand is available but no Business seats were assigned.")
        if route.get("f", 0) and current["f"] == 0:
            warnings.append("⚠️ First demand is available but no First seats were assigned.")

        embed = discord.Embed(
            title=f"🧭 Route Coach • {frm.upper()} → {to.upper()}",
            description=(
                f"**Aircraft:** {plane['name']}\n"
                f"**Distance:** {_num(route['distance']):,.0f} km\n"
                f"**Market:** {'manual snapshot' if manual else 'engine defaults'}"
            ),
            color=0x2ECC71 if current["profit_day"] > 0 else 0xE74C3C,
        )
        embed.add_field(name="Current Setup", value=_result_line("Your input", current), inline=False)
        embed.add_field(name="Best CI Found", value=_result_line("Recommended", optimal), inline=False)
        embed.add_field(
            name="Coach Notes",
            value="\n".join(warnings) if warnings else "✅ No major issue found with this setup.",
            inline=False,
        )
        embed.set_footer(text="This is a calculator recommendation, not live game data.")
        await ctx.send(embed=embed)

    _attach_autocomplete(
        routecoach,
        {
            "frm": airport_ac,
            "to": airport_ac,
            "plane_name": aircraft_ac,
        },
    )

    # ----------------------------- /market ----------------------------
    @bot_instance.hybrid_command(
        name="market",
        description="Set, show, or reset manual fuel and CO2 prices",
    )
    @app_commands.describe(
        action="set, show, or reset",
        fuel="Fuel price per lb, required for set",
        co2="CO2 price per quintal, required for set",
    )
    async def market(
        ctx: commands.Context,
        action: str = "show",
        fuel: Optional[float] = None,
        co2: Optional[float] = None,
    ):
        action = action.lower().strip()
        if action == "show":
            embed = discord.Embed(title="📈 AERION Market Snapshot", color=0x00D4FF)
            embed.description = _market_text(ctx)
            embed.set_footer(text="Prices are manually entered and are not read from AM4.")
            return await ctx.send(embed=embed, ephemeral=True)

        if action == "reset":
            _reset_market(ctx)
            return await ctx.send(
                "✅ Manual prices reset. Support calculations now use engine defaults.",
                ephemeral=True,
            )

        if action != "set":
            return await ctx.send("❌ Action must be `set`, `show`, or `reset`.", ephemeral=True)
        if fuel is None or co2 is None or fuel < 0 or co2 < 0:
            return await ctx.send(
                "❌ Use both values, for example: `/market set fuel:0.72 co2:0.14`.",
                ephemeral=True,
            )
        if fuel > 1000 or co2 > 1000:
            return await ctx.send("❌ Those prices look too high. Check the units.", ephemeral=True)

        _set_market(ctx, fuel, co2)
        await ctx.send(
            f"✅ Manual market snapshot saved for this server.\n"
            f"Fuel: **${fuel:.3f}/lb**\nCO₂: **${co2:.3f}/quintal**",
            ephemeral=True,
        )

    # --------------------------- /buyadvisor --------------------------
    @bot_instance.hybrid_command(
        name="buyadvisor",
        description="Find suitable aircraft for a route and manual budget",
    )
    @app_commands.describe(
        frm="Origin airport",
        to="Destination airport",
        budget="Maximum aircraft purchase budget",
    )
    @_guard
    async def buyadvisor(
        ctx: commands.Context,
        frm: str,
        to: str,
        budget: float,
    ):
        await ctx.defer()
        route = _route(frm, to)
        if not route:
            return await ctx.send(f"❌ Route not found: `{frm.upper()} → {to.upper()}`")
        if budget <= 0:
            return await ctx.send("❌ Budget must be greater than zero.")

        fuel, co2, manual = _get_market(ctx)
        candidates = []
        for plane in _q["get_all_planes"]():
            if _num(plane.get("cost")) > budget:
                continue
            if _range_warning(route, plane):
                continue
            try:
                result = _best_ci(route, plane, ctx.author.id, fuel, co2)
                if result["profit_day"] <= 0:
                    continue
                payback = _num(plane.get("cost")) / max(result["profit_day"], 1)
                candidates.append((result["profit_day"], payback, plane, result))
            except Exception as exc:
                print(f"[AERION SUPPORT] buyadvisor skipped {plane.get('name')}: {exc}")

        if not candidates:
            return await ctx.send(
                "❌ No profitable aircraft found within that budget and route range."
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        lines = []
        for index, (profit, payback, plane, result) in enumerate(candidates[:5], 1):
            lines.append(
                f"**{index}. {plane['name']}** — "
                f"{_money(profit)}/day • payback `{payback:,.0f}d` • "
                f"best CI `{result['cost_index']}`"
            )

        embed = discord.Embed(
            title=f"🛒 Aircraft Purchase Advisor • {frm.upper()} → {to.upper()}",
            description=(
                f"Budget: **{_money(budget)}**\n"
                f"Market: {'manual snapshot' if manual else 'engine defaults'}\n\n"
                + "\n".join(lines)
            ),
            color=0xF1C40F,
        )
        embed.set_footer(text="Recommendations use your budget input; the bot cannot see your current fleet.")
        await ctx.send(embed=embed)

    _attach_autocomplete(
        buyadvisor,
        {
            "frm": airport_ac,
            "to": airport_ac,
        },
    )

    # ------------------------------ /support --------------------------
    @bot_instance.hybrid_command(
        name="support",
        description="Open the AERION AM4 support center",
    )
    async def support(ctx: commands.Context):
        embed = discord.Embed(
            title="🧭 AERION AM4 Support Center",
            description=(
                "Choose a help area below. I use the AM4 reference database "
                "and your command inputs; I do not connect to the live game.\n\n"
                "For a specific route, use `/routecoach`."
            ),
            color=0x00D4FF,
        )
        embed.add_field(
            name="Useful commands",
            value=(
                "`/compare_route` • Compare aircraft on a real route\n"
                "`/market` • Enter current fuel/CO₂ prices\n"
                "`/buyadvisor` • Check aircraft against a budget\n"
                "`/faq` • Learn a mechanic\n"
                "`/troubleshoot` • Diagnose a problem"
            ),
            inline=False,
        )
        await ctx.send(embed=embed, view=SupportView())

    # ------------------------------- /learn ----------------------------
    lessons = {
        1: (
            "Understanding Demand",
            "Y is Economy, J is Business, and F is First demand. "
            "The best configuration is not always an equal split.",
            "Run `/routecoach` and compare the demand fields with the seat fields.",
        ),
        2: (
            "Cost Index",
            "A high Cost Index makes the aircraft faster but usually increases "
            "fuel and CO₂ cost. The best value depends on the route.",
            "Use `/routecoach` to scan the full CI range.",
        ),
        3: (
            "Aircraft Choice",
            "Purchase price is only one part of the decision. Range, capacity, "
            "speed, fuel, maintenance, and route demand all matter.",
            "Use `/compare_route` instead of comparing aircraft on a generic route.",
        ),
        4: (
            "Market Prices",
            "The bot cannot see the AM4 market. Enter your current prices with "
            "`/market set` before making a detailed comparison.",
            "Use `/market show` to confirm which values your calculations use.",
        ),
        5: (
            "Stopovers",
            "A stopover can make an otherwise unreachable route possible, but "
            "the legs should be evaluated separately.",
            "Use the main `/route` command for automatic stopover analysis.",
        ),
    }

    @bot_instance.hybrid_command(
        name="learn",
        description="Study an AM4 lesson",
    )
    @app_commands.describe(lesson="Lesson number from 1 to 5")
    async def learn(ctx: commands.Context, lesson: int = 1):
        if lesson not in lessons:
            return await ctx.send("❌ Choose a lesson from `1` to `5`.", ephemeral=True)
        title, body, practice = lessons[lesson]
        embed = discord.Embed(
            title=f"🎓 AM4 Lesson {lesson}/5 • {title}",
            description=body,
            color=0x9B59B6,
        )
        embed.add_field(name="Practice", value=practice, inline=False)
        if lesson < len(lessons):
            embed.set_footer(text=f"Next lesson: /learn lesson:{lesson + 1}")
        else:
            embed.set_footer(text="Course complete • Use /support whenever you need a refresher")
        await ctx.send(embed=embed)

    # -------------------------------- /faq -----------------------------
    @bot_instance.hybrid_command(
        name="faq",
        description="Answer an AM4 mechanics question",
    )
    @app_commands.describe(topic="Examples: cost-index, seats, a-check, range, cargo, membership")
    async def faq(ctx: commands.Context, *, topic: str):
        key = _find_topic(topic, FAQS, FAQ_ALIASES)
        if not key:
            choices = ", ".join(sorted(FAQS))
            return await ctx.send(f"❌ Topic not found. Try: `{choices}`", ephemeral=True)
        embed = discord.Embed(
            title=f"❓ AM4 FAQ • {key.replace('-', ' ').title()}",
            description=FAQS[key],
            color=0x3498DB,
        )
        embed.set_footer(text="Use /support for the interactive help center.")
        await ctx.send(embed=embed)

    # --------------------------- /troubleshoot ------------------------
    @bot_instance.hybrid_command(
        name="troubleshoot",
        description="Get help with a common AM4 problem",
    )
    @app_commands.describe(issue="Examples: low-profit, loss, range, wrong-seats, market")
    async def troubleshoot(ctx: commands.Context, *, issue: str):
        aliases = {
            "profit": "low-profit",
            "losing": "loss",
            "negative": "loss",
            "too far": "insufficient-range",
            "out of range": "insufficient-range",
            "seat": "wrong-seats",
            "fuel": "market",
            "co2": "market",
        }
        key = _find_topic(issue, TROUBLESHOOTING, aliases)
        if not key:
            choices = ", ".join(sorted(TROUBLESHOOTING))
            return await ctx.send(f"❌ Issue not found. Try: `{choices}`", ephemeral=True)
        embed = discord.Embed(
            title=f"🛠️ Troubleshooter • {key.replace('-', ' ').title()}",
            description=TROUBLESHOOTING[key],
            color=0xE67E22,
        )
        embed.set_footer(text="For a precise result, run /routecoach with your route and aircraft.")
        await ctx.send(embed=embed)

    # ---------------------------- /routecard ---------------------------
    @bot_instance.hybrid_command(
        name="routecard",
        description="Create a shareable route recommendation card",
    )
    @app_commands.describe(
        frm="Origin airport",
        to="Destination airport",
        plane_name="Aircraft",
        ci="Cost Index, 0-200",
    )
    @_guard
    async def routecard(
        ctx: commands.Context,
        frm: str,
        to: str,
        plane_name: str,
        ci: int = 200,
    ):
        await ctx.defer()
        route = _route(frm, to)
        plane = _plane(plane_name)
        if not route or not plane:
            return await ctx.send("❌ Route or aircraft not found.")

        fuel, co2, manual = _get_market(ctx)
        result = _calculate(route, plane, ctx.author.id, ci, fuel, co2)
        optimal = _best_ci(route, plane, ctx.author.id, fuel, co2)

        embed = discord.Embed(
            title=f"🛫 AERION Route Card • {frm.upper()} → {to.upper()}",
            description=(
                f"**Aircraft:** {plane['name']}\n"
                f"**Distance:** {_num(route['distance']):,.0f} km\n"
                f"**Market:** {'manual snapshot' if manual else 'engine defaults'}"
            ),
            color=0x00FF88 if result["profit_day"] > 0 else 0xE74C3C,
        )
        embed.add_field(
            name="Recommended Configuration",
            value=(
                f"**Seats:** {result['y']}Y / {result['j']}J / {result['f']}F\n"
                f"**Ticket prices:** Y ${result['y_price']:,} • "
                f"J ${result['j_price']:,} • F ${result['f_price']:,}\n"
                f"**CI:** {result['cost_index']} • **Trips:** {result['trips']}/day"
            ),
            inline=False,
        )
        embed.add_field(
            name="Economics",
            value=(
                f"**Income/day:** {_money(result['income_day'])}\n"
                f"**Fuel/day:** {_money(result['fuel_day'])}\n"
                f"**CO₂/day:** {_money(result['co2_day'])}\n"
                f"**Profit/day:** {_money(result['profit_day'])}"
            ),
            inline=True,
        )
        embed.add_field(
            name="Coach Recommendation",
            value=(
                f"Best scanned CI: **{optimal['cost_index']}**\n"
                f"Best scanned profit: **{_money(optimal['profit_day'])}/day**"
            ),
            inline=True,
        )
        embed.set_footer(text="AERION • Manual calculator and support output")
        await ctx.send(embed=embed)

    _attach_autocomplete(
        routecard,
        {
            "frm": airport_ac,
            "to": airport_ac,
            "plane_name": aircraft_ac,
        },
    )

    _registered = True
    print(
        "[AERION SUPPORT] Commands registered: "
        "/compare_route /routecoach /market /buyadvisor /support "
        "/learn /faq /troubleshoot /routecard"
    )
    return True
