# DUIT

> **Your Desktop, on WhatsApp. Autonomous Personal Chief of Staff with Meta AI & Local Sidecar**  
> *Tagline: Just say it, ho gaya.*

DUIT bridges the gap between where users live (WhatsApp) and where their work resides (their local desktop workstation). Backed by Meta AI models and the lightweight `@shed` desktop bridge, DUIT transforms natural conversational requests in Hindi, English, or Hinglish into verified, policy-governed local actions.

Whether you are away from your laptop, traveling, or commuting, you can text DUIT from your phone to manage your computer, synthesize communications, and execute workflows remotely with zero context switching.

---

## Key Features

- **Remote Desktop Control from Anywhere:** Discover local applications, open coding workspaces in IDEs, search files, and control active windows on your laptop while away from your desk.
- **Smart Multi-Profile Browser Targeting:** Automatically inspects Chromium state across Google Chrome and Microsoft Edge, allowing users to direct browsing tasks into specific user profiles (e.g., college, work, personal) via natural language.
- **Unified Communication Intelligence:** Bridges WhatsApp messages and Gmail in one brain. Automatically archives incoming chats into MySQL, answers queries like *"Summarize my last 10 WhatsApp client chats"*, and drafts customized emails without placeholder templates.
- **WhatsApp Native Onboarding:** Connects seamlessly using standard 8-character phone pairing codes - zero complex API setups, proprietary client apps, or QR camera hurdles for the end user.
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
 │ - Contextual email synthesis (no placeholder templates)                  │
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
               (Check calendar, open app)  (Send email, delete meeting)
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
 │ - Desktop Sidecar: App launch, multi-profile browser, note creation      │
 │ - Google Suite Tools: Calendar CRUD, Gmail sending/searching             │
 │ - Visual Verification: SAM 3.1 UI bounding box & process check           │
 └───────────────────────────────────┬──────────────────────────────────────┘
                                     │
                                     ▼
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Write-Ahead Journal & Audit Log (SQLite WAL)                             │
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
4. **WhatsApp Phone Number Pairing Code:** Users pair their personal WhatsApp account directly with DUIT by texting `pair <phone>` or via the Command Center web UI using an 8-character code, bypassing complex QR scanning hurdles.

---

## Project Structure

```text
Inovvate/
│
├── backend/                        # Core Python Engine
│   ├── app/
│   │   ├── api/                    # FastAPI Endpoints (webhooks, auth, desktop, whatsapp, approvals)
│   │   ├── cascade/                # 4-stage cascade (orchestrator, rules, decision, schemas)
│   │   ├── channels/               # Messaging channels (Evolution WhatsApp, mock)
│   │   ├── desktop/                # Desktop backend (presence, journal, skills, context_store, meta_vision)
│   │   ├── db/                     # Database models, repository, and SQLite/PostgreSQL layer
│   │   ├── policy/                 # In-code safety policy engine, confirmations, and risk rules
│   │   ├── llm/                    # Meta Model API Provider (Muse Spark 1.3, Wonder, token cache)
│   │   ├── tools/                  # Google adapters (Calendar, Gmail, Contacts, Briefing PDF)
│   │   └── security/               # AES-256-GCM encryption & OAuth token management
│   └── tests/                      # 63 automated unit & integration tests
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
│   └── directorbot/                # Node.js Baileys gateway with pairing codes & MySQL chat archival
│       ├── server.js               # Web Command Center & Pairing API
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
- Windows 10/11 (for desktop sidecar and binary execution)

### 2. Run Automated Test Suite
All 63 automated tests run locally with mock fixtures:
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
# Open http://localhost:5122 for the Command Center dashboard
```

---

## Non-Negotiable Safety & Engineering Invariants

1. **Policy in Code:** Permissions, confirmations, and rate limits live strictly in Python code (`backend/app/policy/`), never entrusted solely to LLM prompt instructions.
2. **Third-Party Inbound Taint Gate:** Actions triggered by inbound emails or messages from third parties strictly require user confirmation.
3. **Idempotency Keys:** Every side-effecting operation enforces a deterministic UUID idempotency key to guarantee zero duplicate executions.
4. **Append-Only Write-Ahead Journal:** Uses SQLite WAL (`journal.py`) with fsync. Invariant: writes state `started` before executing, and marks actions `interrupted` upon unexpected crash recovery.
5. **Zero Token/Secret Logging:** Tokens and credentials are encrypted at rest with AES-256-GCM. Raw message bodies and secrets are scrubbed before writing audit records.
6. **Strict Tenant Isolation:** Data, context, approvals, and models are isolated per user UUID.
