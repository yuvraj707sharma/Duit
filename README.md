<div align="center">

<img src="backend/app/static/duit-mascot.png" alt="DUIT Mascot" width="160" />

# DUIT
### Your Desktop & WhatsApp Executive Assistant
**Autonomous Personal Chief of Staff with Meta AI, WhatsApp Intelligence & Local Desktop Sidecar**  
*Tagline: Just say it, ho gaya.*

[![Tests](https://img.shields.io/badge/pytest-75%20passed-brightgreen.svg)](backend/tests/)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node->=20.0.0-green.svg)](https://nodejs.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Cloud-orange.svg)](https://github.com/yuvraj707sharma/Duit)
[![Live Landing](https://img.shields.io/badge/Landing%20Page-GitHub%20Pages-purple.svg)](https://yuvraj707sharma.github.io/Duit/)

</div>

---

## The Primary Unique Selling Proposition (USP)

> **DUIT securely reads and understands your WhatsApp messages to answer your real-time queries, retrieve critical details from past conversations, and bridge your chats directly with Google Workspace and your local desktop.**

### Why This Is Revolutionary
Most AI assistants are isolated chatbots: they don't know what happens in your real life, can't check what your client sent you, and can't execute tasks on your physical computer.

DUIT solves this by connecting where you communicate (**WhatsApp**) with where your knowledge and tools live (**WhatsApp Chats + Google Suite + Your Local Desktop**):

1. **Secure WhatsApp Chat Retrieval & Memory:**
   - *"What did Rahul say about the project invoice?"*
   - *"Summarize my last 10 client chats on WhatsApp and highlight action items."*
   - *"Did anyone message me about the venue booking today?"*
   - *"Find the deadline Vikram sent on WhatsApp and schedule it on my Google Calendar."*
2. **End-to-End Privacy & Strict Tenant Isolation:**
   - WhatsApp messages are indexed with deterministic cryptographic tenant isolation (UUIDv5).
   - In-code security filters ensure zero token leakage, prompt injection defense, and private, encrypted storage.
3. **From Chat to Real Desktop Action:**
   - Backed by the lightweight native desktop bridge (`DUITDesktop.exe`), natural language requests trigger real actions on your physical PC even when you are away from your desk: opening files, launching apps in specific browser profiles, finding documents, or running code in VS Code.
4. **Natural Hinglish & Multilingual Understanding:**
   - Fluid support for everyday conversational Hindi, Hinglish, and English via text and voice messages.

---

## Key Features

- **WhatsApp Message Intelligence:** Securely parses, indexes, and queries personal/client WhatsApp chats so you never lose context or miss an important commitment.
- **Remote Desktop Control from Anywhere:** Discover local applications, open coding workspaces in IDEs, search files, and control active windows on your laptop while away from your desk.
- **Smart Multi-Profile Browser Targeting:** Automatically inspects Chromium state across Google Chrome and Microsoft Edge, directing browsing tasks into specific user profiles (e.g., college, work, personal) via natural language.
- **Unified Communication Brain:** Bridges WhatsApp chats, Gmail, and Google Calendar. Contextual email synthesis drafts customized responses without placeholder templates.
- **WhatsApp Native Onboarding:** Connects seamlessly using phone pairing codes or single-scan Baileys integration - zero complex API setups, proprietary client apps, or camera hurdles for end users.
- **Meta AI Model Integration:**
  - **Meta Muse Spark (`muse-spark-1.3`):** High-speed multilingual reasoning, intent classification, and structured JSON tool parameter extraction.
  - **Meta Muse Wonder (`muse-wonder-1.0`):** Long-horizon planning and multi-step desktop workflow orchestration.
  - **Meta SAM 3.1 (`sam-3.1`):** Visual UI grounding to detect buttons, windows, and fields on screen for visual action verification.
- **Strict Policy & Verification Engine:** Every side-effecting action is governed by an in-code allowlist security policy, write-ahead journaling (WAL) for crash resilience, and visual screen verification to prove task completion.
- **Standalone Windows Executable:** Runs locally as a standalone native binary (`dist/DUITDesktop.exe`) with minimal resource footprint.

---

## System Architecture

```text
                                 USER INPUT
                  (WhatsApp / Local Voice Push-To-Talk)
                                     │
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Stage 1: Hard Rules in Code (<1ms)                                       │
 │ - Exact blocklists & emergency stops ("stop all", "ruk jao")             │ ──(Match)──► Direct Action (<1ms)
 │ - Syntax allowlists & input pre-filtering                                │
 └───────────────────────────────────┬──────────────────────────────────────┘
                                     │ (Pass-through)
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Stage 2: Fast Decision Layer (Laya System 1) (~15ms)                     │
 │ - Multilingual zero-shot classifier                                      │ ──(Read query)──► Direct Tool (<25ms)
 │ - Classify Intent, Risk Tier, Needs-Confirmation                         │
 └───────────────────────────────────┬──────────────────────────────────────┘
                                     │ (Needs structured arguments / drafting)
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Stage 3: Meta AI Reasoning Engine (Muse Spark 1.3)                       │
 │ - Multilingual argument extraction (Hindi / Hinglish / English)          │
 │ - Dynamic parameter mapping (target app, URL, browser profile)           │
 │ - Contextual email & chat synthesis (no placeholder templates)           │
 │ - Token-conservation in-memory cache                                     │
 └───────────────────────────────────┬──────────────────────────────────────┘
                                     │
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Stage 4: Code Policy Engine & Risk Tiering (<2ms)                        │
 │ - Strict security allowlists (blocks rmdir, del, format, eval, shell)    │
 │ - 3rd-party inbound taint verification                                   │
 │ - Human confirmation gate for destructive actions                        │
 └───────────────────────────────────┬──────────────────────────────────────┘
                                     │
                       ┌─────────────┴─────────────┐
                       ▼                           ▼
               [ Low Risk / Auto ]         [ High Risk / Destructive ]
               (Check calendar, open app,  (Send email, delete meeting,
                query WhatsApp chat)        wipe file)
                       │                           │
                       │                           ▼
                       │                   Send Confirmation Card:
                       │                   "Reply YES to confirm, NO to cancel"
                       │                           │
                       └─────────────┬─────────────┘
                                     │ (Approved)
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Execution Surfaces (Idempotent & Audited)                                │
 │ - WhatsApp Engine: Chat search, message summarization, chat archival     │
 │ - Desktop Sidecar: App launch, multi-profile browser, note creation      │
 │ - Google Suite Tools: Calendar CRUD, Gmail search/send, Contacts, Drive  │
 │ - Visual Verification: SAM 3.1 UI bounding box & process check           │
 └───────────────────────────────────┬──────────────────────────────────────┘
                                     │
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Write-Ahead Journal & Audit Log (PostgreSQL / SQLite WAL)                │
 │ - States: received -> decided -> confirmed -> started                    │
 │   -> completed / failed / interrupted                                    │
 └──────────────────────────────────────────────────────────────────────────┘
```

---

## Authentication & Multi-Tenant Isolation

DUIT enforces cryptographic multi-tenant isolation across all channels:

```text
 WhatsApp Phone (+91...) ──► Deterministic UUIDv5 ──► Tenant Profile
                                                           │
                        ┌──────────────────────────────────┴──────────────────────────────────┐
                        ▼                                                                     ▼
             Google Suite OAuth                                                     Desktop Sidecar Tunnel
     (Encrypted Tokens: AES-256-GCM)                                              (WebSocket Tunnel + Heartbeats)
```

1. **Deterministic User Identity:** Phone numbers are mapped to a stable UUIDv5 (`get_user_uuid_from_channel_id`). All approvals, tokens, journal entries, and audit logs are scoped strictly to this tenant UUID.
2. **Google OAuth AES-256-GCM Storage:** Access and refresh tokens are encrypted at rest with AES-256-GCM using tenant-bound Additional Authenticated Data (AAD).
3. **Desktop Sidecar Presence Check:** The desktop sidecar maintains active WebSocket heartbeats every 5 seconds. If a remote WhatsApp message requests a desktop action while the machine is offline, DUIT immediately replies with the machine's offline status.
4. **WhatsApp Bot Gateway:** WhatsApp users interact with a single official bot number. Administrators manage pairing, sessions, and whitelisting via the password-protected DUIT Command Center.

---

## Project Structure

```text
Inovvate/
│
├── backend/                        # Core Python Engine
│   ├── app/
│   │   ├── api/                    # FastAPI Endpoints (webhooks, auth, desktop, whatsapp, waitlist, approvals)
│   │   ├── cascade/                # 4-stage cascade (orchestrator, rules, decision, schemas)
│   │   ├── channels/               # Messaging channels (Evolution WhatsApp, Baileys, mock)
│   │   ├── desktop/                # Desktop backend (presence, journal, skills, context_store, meta_vision)
│   │   ├── db/                     # Database models, repository, PostgreSQL & SQLite layer
│   │   ├── policy/                 # In-code safety policy engine, confirmations, and risk rules
│   │   ├── llm/                    # Meta Model API Provider (Muse Spark 1.3, Wonder, token cache)
│   │   ├── tools/                  # Google adapters (Calendar, Gmail, Contacts, Drive, Docs, Sheets)
│   │   ├── static/                 # Production landing assets, DUIT mascots, and styles
│   │   └── security/               # AES-256-GCM encryption & OAuth token management
│   └── tests/                      # 75 automated unit & integration tests
│
├── contracts/                      # Source of Truth Schemas
│   ├── openapi.json                # API specification
│   ├── intent.json                 # Valid intent types (<20 bounded)
│   └── tool_calls.json             # Typed tool schemas with idempotency keys & profile support
│
├── desktop/                        # Standalone Windows Desktop App & Sidecar
│   ├── electron/                   # Main & Preload scripts (global kill-switch hotkey Ctrl+Shift+K)
│   ├── src/                        # React / Vite UI with DUIT Logo & Cream Mascot branding
│   ├── sidecar/                    # Local Python OS executor (skills, SQLite WAL journal, runner.py)
│   └── package.json                # electron-builder & Vite build scripts
│
├── dist/                           # Compiled Distribution Binaries
│   └── DUITDesktop.exe             # Single-file standalone Windows desktop binary (~127 MB)
│
├── whatsapp/                       # WhatsApp Integration & Gateway Module
│   └── directorbot/                # Node.js Baileys gateway with cloud gateway fallback
│       ├── server.js               # Web Command Center & Pairing API
│       ├── Dockerfile              # Production Docker container definition for Render
│       └── src/public/             # Brand-styled Command Center UI (logo, mascot, analytics)
│
├── eval/                           # Benchmarking & Golden Datasets
│   ├── test_all_70_scenarios.py    # 70 production benchmark scenarios covering multi-turn flows
│   ├── test_all_personas.py        # Multi-persona evaluation suites
│   └── dataset/                    # Golden evaluation datasets
│
└── shed/                           # Remote Agent Sandboxed Execution Bridge
```

---

## Quick Start Guide

### 1. Prerequisites
- Python 3.11+
- Node.js 20+
- Windows 10/11 (for local desktop sidecar and binary execution)

### 2. Run Automated Test Suite
All 75 automated tests run locally with mock fixtures:
```bash
pytest backend/tests/
```

### 3. Start the Backend API Server
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run the Standalone Desktop Application
Run the pre-compiled binary:
```bash
./dist/DUITDesktop.exe
```
Or start the development sidecar:
```bash
python desktop/sidecar/runner.py
```

### 5. Launch WhatsApp Gateway & Command Center
```bash
cd whatsapp/directorbot
npm install
npm start
# Open http://localhost:10000 for the Command Center dashboard
```

---

## Cloud Deployment (Render)

DUIT is deployed with a production-ready cloud architecture:
- **Backend Service:** `duit-backend` (FastAPI + Meta AI decision layer) on Render.
- **Database:** Render PostgreSQL (Singapore region, low-latency).
- **WhatsApp Gateway:** `duit-whatsapp` (Node.js Baileys Docker container) on Render.
- **Landing Page:** [GitHub Pages Live Landing](https://yuvraj707sharma.github.io/Duit/) with live Early Access waitlist.

---

## Non-Negotiable Safety & Engineering Invariants

1. **Policy in Code:** Permissions, confirmations, and rate limits live strictly in Python code (`backend/app/policy/`), never entrusted solely to LLM prompt instructions.
2. **Third-Party Inbound Taint Gate:** Actions triggered by inbound emails or messages from third parties strictly require user confirmation.
3. **Idempotency Keys:** Every side-effecting operation enforces a deterministic UUID idempotency key to guarantee zero duplicate executions.
4. **Append-Only Write-Ahead Journal:** Uses SQLite/PostgreSQL WAL (`journal.py`) with fsync. Invariant: writes state `started` before executing, and marks actions `interrupted` upon unexpected crash recovery.
5. **Zero Token/Secret Logging:** Tokens and credentials are encrypted at rest with AES-256-GCM. Raw message bodies and secrets are scrubbed before writing audit records.
6. **Strict Tenant Isolation:** Data, context, approvals, and models are isolated per user UUID.
