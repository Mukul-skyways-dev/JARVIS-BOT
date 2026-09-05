# =========================================================
#  aerion_portal_sync.py  —  AERION Tier 5: Portal Deep Integration
#
#  Features:
#    1. Supabase Realtime — instant Discord notifications on portal events
#    2. /invoice — PDF invoice for any AERO Points transaction
#    3. /webhookconfig — admin control for event→channel routing
#    4. /portalsync — manual sync status + stats
#
#  Integration in bot1_aerion.py:
#    from aerion_portal_sync import register_portal_sync
#    # in on_ready():
#    register_portal_sync(bot, SUPABASE_URL, SUPABASE_KEY,
#                         supabase_get, check_membership)
#
#  Requirements: websockets, reportlab (both available on Render)
# =========================================================

import os, json, asyncio, io, random, string
from datetime import datetime, timezone, timedelta
import discord
from discord import app_commands
import pytz
import websockets
import websockets.exceptions

# ── PDF (reportlab) ──────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

_IST     = pytz.timezone("Asia/Kolkata")
BOT_NAME = "AERION"
BOT_VER  = "V3 ALPHA"

# ── Injected refs ──────────────────────────────────────────
_bot          = None
_SUPA_URL     = ""
_SUPA_KEY     = ""
_supa_get     = None
_check_member = None

# ── Webhook config: { event_type: channel_id } ────────────
# Persisted in memory (reset on restart — use DB for permanent)
_webhook_config: dict = {
    "share_entry":    0,   # new share entry on portal
    "new_member":     0,   # new player registered
    "points_credit":  0,   # AERO points credited
    "membership":     0,   # membership activated/renewed
    "default":        0,   # fallback channel
}

# ── Realtime state ─────────────────────────────────────────
_realtime_connected = False
_realtime_last_ping = None
_realtime_events_total = 0
_realtime_ws = None

# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────
def _now_ist():  return datetime.now(_IST)
def _now_utc():  return datetime.now(timezone.utc)
def _ts():       return _now_ist().strftime("%d %b %Y  %I:%M %p IST")
def _env(k):     return os.getenv(k, "")

def _fmt(v):
    try:
        v = float(v)
        if v >= 1e9: return f"${v/1e9:.3f}B"
        if v >= 1e6: return f"${v/1e6:.2f}M"
        return f"${v:,.0f}"
    except: return str(v)

def _gen_invoice_id():
    chars = string.ascii_uppercase + string.digits
    return "INV-" + ''.join(random.choices(chars, k=10))

async def _get_channel(event_type: str):
    """Get the Discord channel for a given event type."""
    ch_id = _webhook_config.get(event_type) or _webhook_config.get("default") or 0
    if not ch_id: return None
    return _bot.get_channel(int(ch_id))

# ─────────────────────────────────────────────────────────
#  GATE
# ─────────────────────────────────────────────────────────
async def _gate(ctx) -> bool:
    if not _check_member: return True
    try:
        status = await _check_member(str(ctx.author.id))
    except: return True
    if not status["linked"]:
        await ctx.send("❌ Link your portal account with `/link <code>` first.",
                       ephemeral=True)
        return False
    if not status["has_access"]:
        cost = 1000 if status["is_new"] else 100
        await ctx.send(
            f"🔒 AERION membership required. Use `/subscribe` ({cost:,} AERO pts).",
            ephemeral=True)
        return False
    return True

# ─────────────────────────────────────────────────────────
#  SUPABASE REALTIME  (WebSocket)
# ─────────────────────────────────────────────────────────
def _realtime_url():
    url = _SUPA_URL.replace("https://", "wss://").replace("http://", "ws://")
    return f"{url}/realtime/v1/websocket?apikey={_SUPA_KEY}&vsn=1.0.0"

def _join_msg(topic: str, ref: str = "1"):
    return json.dumps({
        "topic": topic,
        "event": "phx_join",
        "payload": {
            "config": {
                "broadcast":  {"ack": False, "self": False},
                "presence":   {"key": ""},
                "postgres_changes": [
                    {"event": "*", "schema": "public", "table": topic.split(":")[-1]}
                ],
            }
        },
        "ref": ref,
    })

async def _handle_realtime_event(raw: str):
    """Parse a Supabase Realtime event and dispatch to Discord."""
    global _realtime_events_total
    try:
        msg = json.loads(raw)
    except: return

    event_type = msg.get("event", "")
    payload    = msg.get("payload", {})

    # Heartbeat reply
    if event_type == "phx_reply" and payload.get("status") == "ok":
        return

    # Postgres change event
    if event_type == "postgres_changes":
        data  = payload.get("data", {})
        table = data.get("table", "")
        etype = data.get("type", "")  # INSERT / UPDATE / DELETE
        rec   = data.get("record", {})
        _realtime_events_total += 1

        if table == "share_entries" and etype == "INSERT":
            await _on_share_entry(rec)
        elif table == "share_users" and etype == "INSERT":
            await _on_new_member(rec)
        elif table == "point_transactions" and etype == "INSERT":
            await _on_points_transaction(rec)

async def _on_share_entry(rec: dict):
    """New share entry submitted on portal → notify Discord."""
    ch = await _get_channel("share_entry")
    if not ch: return

    sts_id = rec.get("sts_id", "?")
    value  = rec.get("value", 0)
    allia  = rec.get("alliance", "—")

    # Try to get player name
    name = sts_id
    try:
        rows = await _supa_get("share_users",
            {"sts_id": f"eq.{sts_id}", "select": "name,discord_id"})
        if rows:
            name = rows[0].get("name") or sts_id
            disc_id = rows[0].get("discord_id")
    except: disc_id = None

    embed = discord.Embed(
        title="📤 New Share Entry — AERO Portal",
        color=0x00ff88,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Player",   value=f"**{name}** (`{sts_id}`)", inline=True)
    embed.add_field(name="Alliance", value=allia,                       inline=True)
    embed.add_field(name="Value",    value=_fmt(value),                 inline=True)
    if disc_id:
        embed.add_field(name="Discord", value=f"<@{disc_id}>",         inline=True)
    embed.set_footer(text=f"{BOT_NAME} Portal Sync • {_ts()}")

    await ch.send(embed=embed)

async def _on_new_member(rec: dict):
    """New player registered on portal → notify Discord."""
    ch = await _get_channel("new_member")
    if not ch: return

    embed = discord.Embed(
        title="🆕 New Player Registered — AERO Portal",
        color=0x00d4ff,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Name",     value=rec.get("name","?"),     inline=True)
    embed.add_field(name="STS ID",   value=f"`{rec.get('sts_id','?')}`", inline=True)
    embed.add_field(name="Airline",  value=rec.get("airline","—"),  inline=True)
    embed.add_field(name="Alliance", value=rec.get("alliance","—"), inline=True)
    disc_id = rec.get("discord_id")
    if disc_id:
        embed.add_field(name="Discord", value=f"<@{disc_id}>",     inline=True)
    embed.set_footer(text=f"{BOT_NAME} Portal Sync • {_ts()}")
    await ch.send(embed=embed)

async def _on_points_transaction(rec: dict):
    """AERO Points transaction on portal → notify Discord."""
    amount = float(rec.get("amount", 0))
    if amount == 0: return   # skip zero-amount system entries

    ch = await _get_channel("points_credit" if amount > 0 else "default")
    if not ch: return

    sts_id = rec.get("sts_id","?")
    reason = rec.get("reason","—")
    color  = 0x00ff88 if amount > 0 else 0xff4757
    sign   = "+" if amount > 0 else ""

    embed = discord.Embed(
        title=f"{'💰 AERO Points Credited' if amount>0 else '💸 AERO Points Deducted'}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="STS ID", value=f"`{sts_id}`",   inline=True)
    embed.add_field(name="Amount", value=f"{sign}{amount:,.0f} pts", inline=True)
    embed.add_field(name="Reason", value=reason[:200],    inline=False)
    embed.set_footer(text=f"{BOT_NAME} Portal Sync • {_ts()}")
    await ch.send(embed=embed)

# ── Realtime connection loop ───────────────────────────────
async def _realtime_loop():
    global _realtime_connected, _realtime_last_ping, _realtime_ws

    await _bot.wait_until_ready()
    print("[PORTAL SYNC] Realtime loop started")

    tables = ["share_entries", "share_users", "point_transactions"]
    retry_delay = 5

    while not _bot.is_closed():
        try:
            url = _realtime_url()
            print(f"[PORTAL SYNC] Connecting to Supabase Realtime...")

            async with websockets.connect(
                url,
                ping_interval=25,
                ping_timeout=10,
                close_timeout=10,
            ) as ws:
                _realtime_ws = ws
                _realtime_connected = True
                _realtime_last_ping = _now_ist()
                retry_delay = 5   # reset on success
                print("[PORTAL SYNC] ✅ Connected to Supabase Realtime")

                # Subscribe to each table
                for i, table in enumerate(tables, 1):
                    topic = f"realtime:public:{table}"
                    await ws.send(_join_msg(topic, str(i)))
                    await asyncio.sleep(0.3)
                print(f"[PORTAL SYNC] Subscribed to: {tables}")

                # Listen loop
                async for raw in ws:
                    _realtime_last_ping = _now_ist()
                    await _handle_realtime_event(raw)

        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError, asyncio.TimeoutError) as e:
            _realtime_connected = False
            _realtime_ws = None
            print(f"[PORTAL SYNC] Disconnected: {e}. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)   # exponential backoff, max 2 min

        except Exception as e:
            _realtime_connected = False
            _realtime_ws = None
            print(f"[PORTAL SYNC] Unexpected error: {e}. Retrying in {retry_delay}s...")
            await asyncio.sleep(retry_delay)

# ─────────────────────────────────────────────────────────
#  /invoice  —  Generate PDF invoice for any transaction
# ─────────────────────────────────────────────────────────
async def _build_invoice_pdf(txn_data: dict, player: dict) -> io.BytesIO | None:
    """Build a professional PDF invoice and return as BytesIO."""
    if not HAS_PDF:
        return None

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AerionTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=rl_colors.HexColor("#00d4ff"),
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    sub_style = ParagraphStyle(
        "AerionSub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=rl_colors.HexColor("#888888"),
        alignment=TA_CENTER,
        spaceAfter=16,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=8,
        textColor=rl_colors.HexColor("#888888"),
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=11,
        textColor=rl_colors.HexColor("#111111"),
    )

    story = []

    # ── Header ────────────────────────────────────────────
    story.append(Paragraph("AERION", title_style))
    story.append(Paragraph("AERO CROWN DYNASTY OFFICIAL BOT • AERO Points System", sub_style))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=rl_colors.HexColor("#00d4ff"), spaceAfter=12))

    # ── Invoice meta ──────────────────────────────────────
    inv_id   = txn_data.get("invoice_id", _gen_invoice_id())
    issued   = _now_ist().strftime("%d %b %Y  %I:%M %p IST")
    txn_type = txn_data.get("type", "Transaction")

    meta = [
        ["INVOICE ID",       inv_id],
        ["ISSUED",           issued],
        ["TRANSACTION TYPE", txn_type],
        ["STATUS",           "✓ CONFIRMED"],
    ]
    meta_table = Table(meta, colWidths=[55*mm, 110*mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("TEXTCOLOR",   (0,0), (0,-1), rl_colors.HexColor("#888888")),
        ("TEXTCOLOR",   (1,0), (1,-1), rl_colors.HexColor("#111111")),
        ("FONTNAME",    (0,0), (0,-1), "Helvetica"),
        ("FONTNAME",    (1,0), (1,-1), "Helvetica-Bold"),
        ("TOPPADDING",  (0,0), (-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=rl_colors.HexColor("#dddddd"), spaceAfter=12))

    # ── Player details ────────────────────────────────────
    story.append(Paragraph("BILLED TO", label_style))
    story.append(Spacer(1, 4))
    bill_data = [
        ["Name",      player.get("name","—")],
        ["STS ID",    player.get("sts_id","—")],
        ["Airline",   player.get("airline","—")],
        ["Alliance",  player.get("alliance","—")],
        ["Discord",   player.get("discord_tag","—")],
    ]
    bill_table = Table(bill_data, colWidths=[45*mm, 120*mm])
    bill_table.setStyle(TableStyle([
        ("FONTSIZE",     (0,0),(-1,-1), 10),
        ("TEXTCOLOR",    (0,0),(0,-1), rl_colors.HexColor("#666666")),
        ("TEXTCOLOR",    (1,0),(1,-1), rl_colors.HexColor("#111111")),
        ("TOPPADDING",   (0,0),(-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 2),
    ]))
    story.append(bill_table)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=rl_colors.HexColor("#dddddd"), spaceAfter=12))

    # ── Line items ────────────────────────────────────────
    story.append(Paragraph("TRANSACTION DETAILS", label_style))
    story.append(Spacer(1, 6))

    items = txn_data.get("items", [
        {"description": txn_data.get("reason","—"),
         "qty": 1,
         "amount": txn_data.get("amount", 0)}
    ])

    item_rows = [["Description", "Qty", "Amount (AERO Pts)"]]
    total = 0
    for item in items:
        amt = float(item.get("amount", 0))
        total += amt
        item_rows.append([
            item.get("description","—"),
            str(item.get("qty", 1)),
            f"{'+' if amt>=0 else ''}{amt:,.0f}",
        ])

    item_rows.append(["", "", ""])  # spacer row
    item_rows.append(["TOTAL", "", f"{'+' if total>=0 else ''}{total:,.0f} pts"])

    item_table = Table(item_rows, colWidths=[100*mm, 25*mm, 40*mm])
    item_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0,0), (-1,0), rl_colors.HexColor("#00d4ff")),
        ("TEXTCOLOR",    (0,0), (-1,0), rl_colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 9),
        ("TOPPADDING",   (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("ALIGN",        (1,0), (-1,-1), "CENTER"),
        ("ALIGN",        (2,0), (-1,-1), "RIGHT"),
        # Total row
        ("FONTNAME",     (0,-1),(-1,-1), "Helvetica-Bold"),
        ("BACKGROUND",   (0,-1),(-1,-1), rl_colors.HexColor("#f0faff")),
        ("LINEABOVE",    (0,-1),(-1,-1), 1, rl_colors.HexColor("#00d4ff")),
        # Grid
        ("INNERGRID",    (0,0), (-1,-2), 0.25, rl_colors.HexColor("#eeeeee")),
        ("BOX",          (0,0), (-1,-2), 0.5,  rl_colors.HexColor("#cccccc")),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 16))

    # ── Balance ───────────────────────────────────────────
    new_balance = txn_data.get("new_balance")
    if new_balance is not None:
        story.append(Paragraph(
            f"New AERO Points Balance: <b>{new_balance:,}</b>",
            ParagraphStyle("Balance", parent=styles["Normal"],
                           fontSize=10, alignment=TA_RIGHT,
                           textColor=rl_colors.HexColor("#00aa88"))
        ))
        story.append(Spacer(1, 12))

    # ── Footer ────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=rl_colors.HexColor("#dddddd"), spaceAfter=8))
    story.append(Paragraph(
        f"Generated by {BOT_NAME} {BOT_VER} • AERO CROWN DYNASTY OFFICIAL BOT • {issued}",
        ParagraphStyle("Footer", parent=styles["Normal"],
                       fontSize=7, textColor=rl_colors.HexColor("#aaaaaa"),
                       alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        "This is an automated document generated by the AERION system. "
        "AERO Points are virtual currency within the AERO CROWN DYNASTY ecosystem.",
        ParagraphStyle("FooterNote", parent=styles["Normal"],
                       fontSize=6, textColor=rl_colors.HexColor("#bbbbbb"),
                       alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf

async def _cmd_invoice(ctx, txn_id: str = None, sts_id: str = None):
    await ctx.defer(ephemeral=True)
    if not await _gate(ctx): return

    me = await _supa_get("share_users",
        {"discord_id": f"eq.{str(ctx.author.id)}",
         "select": "sts_id,name,airline,alliance,aero_points"})

    if not me:
        return await ctx.send("❌ Link your portal account first with `/link <code>`.",
                              ephemeral=True)

    player = me[0]

    # Fetch transaction
    txn_rows = []
    if txn_id:
        try:
            txn_rows = await _supa_get("point_transactions", {
                "reason": f"ilike.*{txn_id}*",
                "sts_id": f"eq.{player['sts_id']}",
                "select": "*",
                "order":  "created_at.desc",
                "limit":  "1",
            })
        except Exception as e:
            print(f"[INVOICE] txn fetch error: {e}")

    if not txn_rows:
        # Fetch latest transaction
        try:
            txn_rows = await _supa_get("point_transactions", {
                "sts_id": f"eq.{player['sts_id']}",
                "select": "*",
                "order":  "created_at.desc",
                "limit":  "1",
            })
        except Exception as e:
            return await ctx.send(f"❌ Could not fetch transactions: {e}", ephemeral=True)

    if not txn_rows:
        return await ctx.send("❌ No transactions found for your account.", ephemeral=True)

    txn    = txn_rows[0]
    inv_id = _gen_invoice_id()

    txn_data = {
        "invoice_id":  inv_id,
        "type":        "AERO Points Transaction",
        "reason":      txn.get("reason", "—"),
        "amount":      float(txn.get("amount", 0)),
        "new_balance": player.get("aero_points"),
        "items": [{
            "description": txn.get("reason","—"),
            "qty": 1,
            "amount": float(txn.get("amount", 0)),
        }]
    }

    player_data = {
        "name":        player.get("name","—"),
        "sts_id":      player.get("sts_id","—"),
        "airline":     player.get("airline","—"),
        "alliance":    player.get("alliance","—"),
        "discord_tag": str(ctx.author),
    }

    embed = discord.Embed(
        title=f"🧾 Invoice — {inv_id}",
        color=0x00d4ff
    )
    embed.add_field(name="Player",      value=player.get("name","—"),     inline=True)
    embed.add_field(name="STS ID",      value=f"`{player.get('sts_id')}`",inline=True)
    embed.add_field(name="Amount",      value=f"{'+' if txn_data['amount']>=0 else ''}{txn_data['amount']:,.0f} AERO pts", inline=True)
    embed.add_field(name="Reason",      value=txn_data["reason"][:200],   inline=False)
    embed.add_field(name="Balance",     value=f"{player.get('aero_points',0):,} AERO pts", inline=True)
    embed.add_field(name="Invoice ID",  value=f"`{inv_id}`",              inline=True)
    embed.set_footer(text=f"{BOT_NAME} • AERO Points System • {_ts()}")

    # Generate PDF
    if HAS_PDF:
        try:
            pdf_buf = await asyncio.to_thread(_build_invoice_pdf_sync, txn_data, player_data)
            if pdf_buf:
                await ctx.send(
                    embed=embed,
                    file=discord.File(pdf_buf, filename=f"AERION_Invoice_{inv_id}.pdf"),
                    ephemeral=True
                )
                return
        except Exception as e:
            print(f"[INVOICE] PDF error: {e}")

    await ctx.send(embed=embed, ephemeral=True)

def _build_invoice_pdf_sync(txn_data, player):
    """Synchronous wrapper for PDF generation (for asyncio.to_thread)."""
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    story = []

    # Header
    story.append(Paragraph("AERION",
        ps("T", fontSize=24, textColor=rl_colors.HexColor("#00d4ff"),
           spaceAfter=2, alignment=TA_CENTER, fontName="Helvetica-Bold")))
    story.append(Paragraph("AERO CROWN DYNASTY  •  AERO Points Invoice",
        ps("S", fontSize=9, textColor=rl_colors.HexColor("#888888"),
           spaceAfter=14, alignment=TA_CENTER)))
    story.append(HRFlowable(width="100%", thickness=2,
                             color=rl_colors.HexColor("#00d4ff"), spaceAfter=12))

    # Meta
    issued  = datetime.now(_IST).strftime("%d %b %Y  %I:%M %p IST")
    inv_id  = txn_data.get("invoice_id","—")
    meta = [
        ["INVOICE ID",       inv_id],
        ["DATE ISSUED",      issued],
        ["TYPE",             txn_data.get("type","Transaction")],
        ["STATUS",           "CONFIRMED"],
    ]
    mt = Table(meta, colWidths=[55*mm, 110*mm])
    mt.setStyle(TableStyle([
        ("FONTSIZE",    (0,0),(-1,-1), 9),
        ("TEXTCOLOR",   (0,0),(0,-1), rl_colors.HexColor("#888888")),
        ("FONTNAME",    (0,0),(0,-1), "Helvetica"),
        ("FONTNAME",    (1,0),(1,-1), "Helvetica-Bold"),
        ("TOPPADDING",  (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
    ]))
    story.append(mt)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=rl_colors.HexColor("#dddddd"), spaceAfter=10))

    # Billed to
    story.append(Paragraph("BILLED TO",
        ps("BL", fontSize=8, textColor=rl_colors.HexColor("#888888"), spaceAfter=4)))
    bill = [
        ["Name",     player.get("name","—")],
        ["STS ID",   player.get("sts_id","—")],
        ["Airline",  player.get("airline","—")],
        ["Alliance", player.get("alliance","—")],
        ["Discord",  player.get("discord_tag","—")],
    ]
    bt = Table(bill, colWidths=[40*mm, 125*mm])
    bt.setStyle(TableStyle([
        ("FONTSIZE",     (0,0),(-1,-1), 10),
        ("TEXTCOLOR",    (0,0),(0,-1), rl_colors.HexColor("#666666")),
        ("TOPPADDING",   (0,0),(-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 2),
    ]))
    story.append(bt)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=rl_colors.HexColor("#dddddd"), spaceAfter=10))

    # Items
    story.append(Paragraph("TRANSACTION DETAILS",
        ps("DH", fontSize=8, textColor=rl_colors.HexColor("#888888"), spaceAfter=6)))

    items = txn_data.get("items", [])
    rows  = [["Description", "Qty", "AERO Points"]]
    total = 0
    for item in items:
        amt = float(item.get("amount",0)); total += amt
        rows.append([item.get("description","—"), str(item.get("qty",1)),
                     f"{'+' if amt>=0 else ''}{amt:,.0f}"])
    rows.append(["", "", ""])
    rows.append(["TOTAL", "", f"{'+' if total>=0 else ''}{total:,.0f} pts"])

    it = Table(rows, colWidths=[100*mm, 25*mm, 40*mm])
    it.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), rl_colors.HexColor("#00d4ff")),
        ("TEXTCOLOR",    (0,0),(-1,0), rl_colors.white),
        ("FONTNAME",     (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0),(-1,-1), 9),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
        ("ALIGN",        (1,0),(-1,-1), "CENTER"),
        ("ALIGN",        (2,0),(-1,-1), "RIGHT"),
        ("FONTNAME",     (0,-1),(-1,-1), "Helvetica-Bold"),
        ("BACKGROUND",   (0,-1),(-1,-1), rl_colors.HexColor("#f0faff")),
        ("LINEABOVE",    (0,-1),(-1,-1), 1, rl_colors.HexColor("#00d4ff")),
        ("INNERGRID",    (0,0),(-1,-2), 0.25, rl_colors.HexColor("#eeeeee")),
        ("BOX",          (0,0),(-1,-2), 0.5, rl_colors.HexColor("#cccccc")),
    ]))
    story.append(it)
    story.append(Spacer(1, 10))

    nb = txn_data.get("new_balance")
    if nb is not None:
        story.append(Paragraph(
            f"New Balance: <b>{nb:,} AERO Points</b>",
            ps("NB", fontSize=10, alignment=TA_RIGHT,
               textColor=rl_colors.HexColor("#00aa88"))))
        story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=rl_colors.HexColor("#dddddd"), spaceAfter=8))
    story.append(Paragraph(
        f"Generated by AERION {BOT_VER}  •  AERO CROWN DYNASTY  •  {issued}",
        ps("FT", fontSize=7, textColor=rl_colors.HexColor("#aaaaaa"), alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)
    return buf

# ─────────────────────────────────────────────────────────
#  /webhookconfig  —  Admin: configure event→channel routing
# ─────────────────────────────────────────────────────────
class _WebhookConfigView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx

    def _embed(self):
        e = discord.Embed(
            title="⚙️ AERION Portal Sync — Webhook Config",
            description=(
                "Configure which Discord channel receives each portal event.\n"
                "Click a button to set the **current channel** for that event."
            ),
            color=0x00d4ff
        )
        for ev, ch_id in _webhook_config.items():
            e.add_field(
                name=ev.replace("_"," ").title(),
                value=f"<#{ch_id}>" if ch_id else "❌ Not set",
                inline=True
            )
        e.add_field(
            name="Realtime Status",
            value=("🟢 Connected" if _realtime_connected else "🔴 Disconnected")
                  + f"\nEvents received: {_realtime_events_total:,}",
            inline=False
        )
        e.set_footer(text=f"{BOT_NAME} Portal Sync • {_ts()}")
        return e

    async def _set_channel(self, interaction, event_type):
        _webhook_config[event_type] = interaction.channel_id
        await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="📤 Share Entry", style=discord.ButtonStyle.primary)
    async def set_share(self, i, b): await self._set_channel(i, "share_entry")

    @discord.ui.button(label="🆕 New Member", style=discord.ButtonStyle.primary)
    async def set_member(self, i, b): await self._set_channel(i, "new_member")

    @discord.ui.button(label="💰 Points", style=discord.ButtonStyle.primary)
    async def set_points(self, i, b): await self._set_channel(i, "points_credit")

    @discord.ui.button(label="🎫 Membership", style=discord.ButtonStyle.primary)
    async def set_membership(self, i, b): await self._set_channel(i, "membership")

    @discord.ui.button(label="📡 Default", style=discord.ButtonStyle.secondary)
    async def set_default(self, i, b): await self._set_channel(i, "default")

    @discord.ui.button(label="🔄 Reconnect Realtime", style=discord.ButtonStyle.green)
    async def reconnect(self, i, b):
        global _realtime_ws
        if _realtime_ws:
            try: await _realtime_ws.close()
            except: pass
        await i.response.send_message(
            "🔄 Realtime reconnecting... check status in 10 seconds.",
            ephemeral=True)

# ─────────────────────────────────────────────────────────
#  /portalsync  —  Status dashboard
# ─────────────────────────────────────────────────────────
async def _cmd_portalsync(ctx):
    await ctx.defer(ephemeral=True)

    # Fetch quick stats from portal
    stats = {}
    try:
        rows = await _supa_get("share_entries", {"select": "id", "limit": "1000"})
        stats["Total Entries"] = len(rows)
    except: stats["Total Entries"] = "?"
    try:
        rows = await _supa_get("share_users", {"select": "sts_id"})
        stats["Portal Players"] = len(rows)
    except: stats["Portal Players"] = "?"
    try:
        rows = await _supa_get("point_transactions",
            {"select": "id", "order": "created_at.desc", "limit": "1"})
        stats["Last Transaction"] = rows[0].get("created_at","?")[:10] if rows else "?"
    except: stats["Last Transaction"] = "?"

    e = discord.Embed(
        title="🌐 AERION Portal Sync Status",
        color=0x00ff88 if _realtime_connected else 0xff4757
    )
    e.add_field(
        name="Realtime Connection",
        value=("🟢 **LIVE** — Supabase Realtime active"
               if _realtime_connected
               else "🔴 **DISCONNECTED** — Attempting reconnect..."),
        inline=False
    )
    e.add_field(name="Events Received", value=f"{_realtime_events_total:,}", inline=True)
    e.add_field(
        name="Last Activity",
        value=(_realtime_last_ping.strftime("%I:%M %p IST")
               if _realtime_last_ping else "—"),
        inline=True
    )
    for k, v in stats.items():
        e.add_field(name=k, value=str(v), inline=True)

    # Channel config
    cfg_lines = []
    for ev, ch_id in _webhook_config.items():
        cfg_lines.append(f"`{ev}` → {'<#'+str(ch_id)+'>' if ch_id else '❌ not set'}")
    e.add_field(name="Event Routing", value="\n".join(cfg_lines) or "—", inline=False)
    e.set_footer(text=f"{BOT_NAME} Portal Sync • {_ts()}")
    await ctx.send(embed=e, ephemeral=True)

# ─────────────────────────────────────────────────────────
#  REGISTER
# ─────────────────────────────────────────────────────────
def register_portal_sync(bot_instance, supa_url, supa_key, supa_get_fn,
                          check_member_fn=None):
    global _bot, _SUPA_URL, _SUPA_KEY, _supa_get, _check_member
    _bot          = bot_instance
    _SUPA_URL     = supa_url
    _SUPA_KEY     = supa_key
    _supa_get     = supa_get_fn
    _check_member = check_member_fn

    # Start Realtime loop
    bot_instance.loop.create_task(_realtime_loop())
    print("[PORTAL SYNC] Realtime subscription started")

    # ── /invoice ──────────────────────────────────────────
    @bot_instance.hybrid_command(
        name="invoice",
        description="Generate a PDF invoice for your latest AERO Points transaction"
    )
    @app_commands.describe(
        txn_id="Transaction/Invoice ID (optional — leave blank for latest)"
    )
    async def invoice(ctx, txn_id: str = None):
        await _cmd_invoice(ctx, txn_id=txn_id)

    # ── /webhookconfig ────────────────────────────────────
    @bot_instance.hybrid_command(
        name="webhookconfig",
        description="[Admin] Configure which channel receives each portal event"
    )
    async def webhookconfig(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Admin only.", ephemeral=True)
        view  = _WebhookConfigView(ctx)
        embed = view._embed()
        await ctx.send(embed=embed, view=view, ephemeral=True)

    # ── /portalsync ───────────────────────────────────────
    @bot_instance.hybrid_command(
        name="portalsync",
        description="View AERION Portal Sync status — Realtime connection + event routing"
    )
    async def portalsync(ctx):
        await _cmd_portalsync(ctx)

    print("[PORTAL SYNC] Commands ready: /invoice /webhookconfig /portalsync")
