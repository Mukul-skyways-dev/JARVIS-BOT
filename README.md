# ✈️ AERION — JARVIS BOT

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-v2.3%2B-5865F2.svg?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![Flask](https://img.shields.io/badge/Flask-Keep--Alive-black.svg?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![AM4](https://img.shields.io/badge/Game-Airlines%20Manager%204-orange.svg)](#)

> **AERION (JARVIS-BOT)** is an enterprise-grade Discord bot and web management suite designed specifically for **Airlines Manager 4 (AM4)** alliances. It combines advanced route calculators, fleet performance analytics, Groq-powered AI assistance, a comprehensive alliance governance suite, and Supabase cloud synchronization.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
  - [Route & Fleet Intelligence](#-route--fleet-intelligence)
  - [AI Conversational Assistant](#-ai-conversational-assistant)
  - [Alliance Governance Suite](#-alliance-governance-suite)
  - [Membership & Role Management](#-membership--role-management)
  - [Community Share & Stock Analytics](#-community-share--stock-analytics)
  - [Web Admin Interface & Keep-Alive](#-web-admin-interface--keep-alive)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Configuration & Environment Variables](#-configuration--environment-variables)
- [Installation & Local Setup](#-installation--local-setup)
- [Deployment Guide](#-deployment-guide)
- [Commands Reference](#-commands-reference)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Overview

Operating a competitive alliance in **Airlines Manager 4** requires meticulous route planning, aircraft performance comparison, seat configuration optimization, and alliance governance. **AERION** streamlines the entire workflow directly inside Discord with hybrid commands (Slash + Text prefix) and automated cloud data synchronization.

---

## 🚀 Key Features

### 🛫 Route & Fleet Intelligence
- **Route Profit Calculator**: Evaluates distance, demand (Y/J/F), ticket pricing, optimal seat configurations, runway constraints, and contribution values.
- **Aircraft Specification & Comparison**: Head-to-head comparison tool (e.g. `A320 vs B737`) analyzing fuel consumption, speed, range, maintenance costs, and ROI.
- **Top Route Finder**: Identifies highest-yield routes from any hub, supporting distance caps, short-haul (`<=3000km`), and long-haul (`>3000km`) queries.
- **Visual Radar Maps**: Generates glowing route maps and profit-vs-distance scatter plots using `matplotlib` and `Pillow`.

### 🧠 AI Conversational Assistant
- **Groq LLM Integration**: High-speed conversational AI powered by Groq (via OpenAI-compatible API).
- **Contextual Memory**: Retains multi-turn conversation history per user with automatic pruning to prevent token bloat.
- **Real-time Tool Calling**: The AI dynamically fetches live AM4 aircraft specifications, airport codes, and route parameters during conversations.

### 🏛️ Alliance Governance Suite
- **Decentralized Voting Engine**: Create, monitor, and finalize binding alliance proposals and polls.
- **Treasury Management**: Track alliance capital allocations, budget thresholds, and member payouts with audit logs.
- **Dispute Resolution & Case Management**: Formal case tracking system with unique case IDs.
- **Tournament Brackets**: Integrated tournament bracket manager for internal alliance competitions.

### 👥 Membership & Role Management
- **Automated Verification**: Generates unique transaction IDs (`AER-XXXXXXXX`) for membership verification.
- **Tier-based Access**: Role gating for alliance executives, verified captains, and recruits.
- **Portal Synchronization**: Synchronizes user profiles and loyalty point balances (`myaeropoints`) with external web dashboards.

### 📈 Community Share & Stock Analytics
- **AM4 IPO & Stock Tracking**: Real-time evaluation of member share values and market capitalization.
- **Row-Level Security (RLS)**: Secure Supabase schema support ensuring data isolation across alliance members.

### 🌐 Web Admin Interface & Keep-Alive
- **Built-in Flask Server**: Runs on port `8080` (or `$PORT`) to handle cloud health checks (Render, Railway, Fly.io) preventing container spin-down.
- **Web Admin Endpoints**: REST API endpoints for live bot telemetry, server stats, and dynamic module configuration toggling.

---

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Bot Engine:** [discord.py](https://discordpy.readthedocs.io/) (v2.3+)
- **AI Engine:** [Groq API](https://console.groq.com/) via OpenAI client
- **Databases:**
  - **Cloud:** [Supabase](https://supabase.com/) (PostgreSQL REST API)
  - **Local Storage:** SQLite3 (`fuels.db`, `new_am4.db`, `static_data.db`)
- **Web Framework:** [Flask](https://flask.palletsprojects.com/)
- **Data & Visualization:** `matplotlib`, `numpy`, `Pillow`, `openpyxl`, `reportlab`, `python-docx`
- **Text-to-Speech:** `edge_tts`

---

## 📂 Project Structure

```text
JARVIS-BOT/
├── bot1.py                    # Main application: bot startup, hybrid commands, Flask web server & admin APIs
├── aerion_governance_suite.py # Governance suite: voting engine, proposals, treasury, cases, tournaments
├── aerion_membership.py       # Membership onboarding, tier checks, and role synchronization
├── aerion_intelligence.py     # Fuel price forecasts, route math, and market intelligence
├── aerion_alliance.py         # Alliance fleet statistics and leaderboard management
├── aerion_portal_sync.py      # Supabase cloud portal synchronization
├── aerion_support_tools.py    # Support utilities and administrative tools
├── aerion_command_control.py  # Bot executive command & control module
├── community_share_module.py  # AM4 community share valuation & tracking
├── community_share_schema.sql # Database schema for Supabase RLS share tracking
├── export.py                  # Document generation engine (DOCX, PDF, Excel)
├── export_view.py             # Discord UI interactive views for document export
├── fuels.db                   # SQLite fuel pricing history
├── new_am4.db                 # SQLite core game data
├── static_data.db             # Pre-indexed airports, routes, and aircraft specs
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation
