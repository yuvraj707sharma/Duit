# FastAgent ⚡

> **Ultra-Low-Latency, Safe, Multi-Channel AI Executive Assistant with Local Continuous Learning**  
> *Hackathon Project — Target Deadline: 24 October 2026*

FastAgent solves the latency, high cost, and safety challenges of generative AI assistants by routing commands through a **deterministic sub-50ms hybrid cascade**:

1. **Stage 1 (Hard Rules in Code):** Sub-millisecond static rules, emergency halts ("stop all", "ruk jao"), and input sanitation (<1ms).
2. **Stage 2 (Fast Local Decision Layer - Laya System 1):** Sub-25ms zero-shot multilingual intent, risk tier, and needs-confirmation classification (ModernBERT / mmBERT / ONNX).
3. **Stage 3 (Targeted Argument Extraction):** LLM calls (Gemini / local Ollama) invoked *only* when structured arguments or complex drafting are required.
4. **Stage 4 (Code Policy Engine & Human Confirmation):** Strict in-code safety gates (recipient allowlists, 3rd-party inbound taint gating, rate limits, and risk-tiered WhatsApp/Desktop confirmations).
5. **Execution Surfaces:**
   - **Google Suite Tools:** Real Google Calendar CRUD, Gmail sending/searching, and People/Contacts resolution.
   - **Desktop Executor (Electron + Python sidecar):** Frameless sidebar widget with push-to-talk mic, live status overlay with 2s cancel window, global kill-switch hotkey (`Ctrl+Shift+K`), and SQLite WAL write-ahead journal.
   - **Ultra-Low-Latency Local Voice STT Engine:** Local `faster-whisper` (CTranslate2 INT8) paired with Silero VAD (<80ms transcription), routing push-to-talk voice commands directly into the 4-stage cascade.
   - **Proactive Daily Automator:** Morning briefing generation, meeting conflict detection, and smart inbox triage.
   - **WhatsApp Multi-Tenant Bot:** Real-time WhatsApp interaction with phone whitelisting, group/broadcast drop defense, and self-service onboarding.

---

## 🏛️ System Architecture

```
                       USER INPUT
           (WhatsApp / Voice / Desktop Hotkey)
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Stage 1: Hard Rules in Code (<1ms)                     │
│ - Exact blocklists & emergency stops ("stop all")      │ ──(Match)──► Direct Action (<1ms)
│ - Syntax allowlists & regex pre-filtering              │
└───────────────────────────┬────────────────────────────┘
                            │ (Pass-through)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Stage 2: Fast Decision Layer (Laya System 1) (~15ms)   │
│ - Multilingual zero-shot classifier                    │ ──(Read query)──► Direct Tool (<25ms)
│ - Classify Intent, Risk Tier, Needs-Confirmation       │
└───────────────────────────┬────────────────────────────┘
                            │ (Needs structured arguments / drafting)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Stage 3: Targeted LLM Extraction (~350ms)              │
│ - Extract JSON schema arguments (Calendar / Gmail)     │
│ - Draft contextual email / message bodies              │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Stage 4: Code Policy Engine & Risk Tiering (<2ms)      │
│ - Check recipient allowlists & rate limits             │
│ - 3rd-party inbound taint verification                 │
│ - Risk-tiered confirmation gate                        │
└───────────────────────────┬────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
      [ Low Risk / Auto ]         [ High Risk / Destructive ]
      (Check calendar, open app)  (Send email, delete meeting)
              │                           │
              │                           ▼
              │                   Send Confirmation Prompt:
              │                   "👉 Reply YES to confirm, NO to cancel"
              │                           │
              └─────────────┬─────────────┘
                            │ (Approved)
                            ▼
┌────────────────────────────────────────────────────────┐
│ Execution Surfaces (Idempotent & Audited)              │
│ - Google Tools: Calendar, Gmail, Contacts              │
│ - Desktop Executor: App launch, notes, volume, search  │
│ - Presence Check: Cross-device laptop online/offline   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Write-Ahead Journal & Audit Log (SQLite WAL + Vector)  │
│ - States: received -> decided -> confirmed -> started  │
│   -> completed / failed / interrupted                  │
│ - Few-shot tuning from explicit user corrections       │
└────────────────────────────────────────────────────────┘
```

---

## 🔐 How FastAgent Checks User & Service Authentication

FastAgent enforces **cryptographic multi-tenant isolation** across all surfaces:

```
 WhatsApp Number (+91...) ──► Deterministic UUIDv5 ──► Tenant Profile
                                                           │
                        ┌──────────────────────────────────┴──────────────────────────────────┐
                        ▼                                                                     ▼
             Google Suite OAuth                                                     Desktop Sidecar Tunnel
    (Encrypted Tokens: AES-256-GCM)                                              (WebSocket Tunnel + Heartbeats)
```

1. **Deterministic User Identity**:
   - When a message arrives from WhatsApp or Web, FastAgent converts the phone number into a stable UUIDv5: `get_user_uuid_from_channel_id(phone)`.
   - All approvals, tokens, journal entries, and audit logs are scoped strictly to this `user_uuid`.

2. **Google OAuth Authentication Check**:
   - Before executing calendar or Gmail operations, FastAgent checks `OAuthToken` in the database for `(user_id, provider='google')`.
   - **Valid Token**: Decrypted using AES-256-GCM and used to call Google APIs.
   - **Expired Token**: FastAgent uses the encrypted refresh token to retrieve a fresh access token transparently.
   - **Missing / Unauthenticated**: The tool immediately returns:
     `{"success": false, "error": "Google account not linked", "auth_url": "/api/auth/google/url?user_id=..."}`
     FastAgent sends an onboarding card over WhatsApp with a direct one-click authorization link.

3. **Desktop Executor Presence & Authentication Check**:
   - The desktop sidecar connects outbound to `ws://localhost:8000/api/desktop/ws?user_id={user_id}` using a shared secret.
   - The sidecar sends heartbeats every 5 seconds.
   - `presence_manager.is_online(user_id)` evaluates whether a heartbeat was received within the last 30 seconds.
   - If a user on WhatsApp asks: *"Open VS Code on my laptop"*, FastAgent checks presence:
     - **Online**: Command is dispatched to the desktop over WebSocket and executed.
     - **Offline**: FastAgent immediately replies: `"Laptop offline"`.

4. **New WhatsApp User Onboarding Gate & 1-Click Google OAuth**:
   - If `WHATSAPP_REQUIRE_REGISTRATION=True` and a new number texts the bot, FastAgent drops all destructive tool executions and dispatches a dedicated onboarding link:
     > *"👋 Welcome to **FastAgent**! Your phone number is not yet connected.\nClick here to link your Google Calendar, Email, and Desktop: http://localhost:8000/connect?phone=..."*
   - **One-Click Mobile Portal (`/connect?phone=...`)**:
     - FastAgent provides a clean, responsive mobile web onboarding portal.
     - Users click a standard, trusted **"Sign in with Google"** button (zero API keys or OAuth credentials required from the user).
   - **Production Token Isolation & Cryptographic AAD Binding**:
     - The OAuth callback (`/api/auth/google/callback`) exchanges the code, encrypts both `access_token` and `refresh_token` using AES-256-GCM bound to the user's UUID in the AAD, and persists them into the `OAuthToken` PostgreSQL table.
     - Upon successful connection, FastAgent automatically displays `/connect/success` with a "Return to WhatsApp" button and dispatches an instant WhatsApp welcome message.
     - Tools (`GoogleCalendarTool`, `GmailTool`) decrypt only the active caller's tokens on the fly, guaranteeing 100% tenant isolation across multiple concurrent user profiles.

---

## 📂 Project Structure

```text
fastagent/
│
├── backend/                        # Core Python Engine
│   ├── app/
│   │   ├── api/                    # FastAPI Endpoints (webhooks, auth, desktop, whatsapp, approvals)
│   │   ├── cascade/                # 4-stage cascade (orchestrator, rules, decision, laya)
│   │   ├── channels/               # Messaging channels (Evolution WhatsApp, mock)
│   │   ├── desktop/                # Desktop backend (presence, journal, skills, context_store, sidecar)
│   │   ├── db/                     # Database models, repository, and SQLite/PostgreSQL layer
│   │   ├── policy/                 # In-code safety policy engine, confirmations, and risk rules
│   │   ├── tools/                  # Google adapters (Calendar, Gmail, Contacts, Daily Automator)
│   │   ├── security/               # AES-256-GCM encryption & OAuth token management
│   │   └── learning/               # Continual learning, few-shot tuning, threshold calibration
│   └── tests/                      # 58 passing unit & integration tests (Cascade, WhatsApp, Desktop, STT, OAuth)
│
├── contracts/                      # Source of Truth Schemas
│   ├── openapi.json                # API specification
│   ├── intent.json                 # Valid intent types (<20 bounded)
│   └── tool_calls.json             # Typed tool schemas with idempotency keys
│
├── desktop/                        # Standalone Windows Desktop App & OS Executor (.exe)
│   ├── electron/                   # Main & Preload scripts (global kill-switch hotkey Ctrl+Shift+K)
│   ├── src/                        # UI components (StatusOverlay, Push-To-Talk Mic, Floating HUD)
│   ├── sidecar/                    # Local Python OS executor (skills, SQLite WAL journal, faster-whisper)
│   └── package.json                # electron-builder config to package standalone .exe
│
├── whatsapp/                       # WhatsApp Integration & Gateway Module
│   ├── evolution-go/               # High-performance Go WhatsApp multi-device server
│   └── directorbot/                # Node.js Baileys client with interactive terminal QR pairing
│
├── eval/                           # Benchmarking & Golden Datasets
│   ├── dataset/                    # Golden evaluation datasets (507+ curated queries)
│   ├── bench_routers.py            # Latency and routing accuracy benchmark suite
│   └── learning_curve.py           # Active learning threshold tuning simulation
│
├── web/                            # Web & Mobile Dashboard (Capacitor ready)
│
└── loadtest/                       # k6 Performance & Load Testing Scripts
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.11+
- Node.js 20+
- (Optional) Docker for full containerized stack

### 2. Run Automated Test Suite
All 58 tests run locally with mock fixtures:
```bash
pytest backend/tests/
```

### 3. Run Router Benchmarks
```bash
python eval/bench_routers.py --router embed
```

### 4. Start the Backend API Server
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Launch the Desktop Executor (Electron Sidebar)
```bash
cd desktop
npm install
npm run dev
```
- **Global Hotkey:** `Ctrl+Shift+K` (or `Cmd+Shift+K`) toggles emergency kill-switch.
- **Push-to-Talk:** Hold the mic button to speak; status overlay displays `Heard: ... -> Doing: ...` with a 2-second cancel countdown.

### 6. Launch the Web Dashboard
```bash
cd web
npm install
npm run dev
# Open http://localhost:5173
```

---

## 🔒 Non-Negotiable Safety & Engineering Invariants

1. **Policy in Code:** Permissions, confirmations, and rate limits live strictly in Python code (`backend/app/policy/`), never entrusted solely to LLM prompt instructions.
2. **Third-Party Inbound Taint Gate:** Actions triggered by inbound emails or messages from third parties strictly require user confirmation.
3. **Idempotency Keys:** Every side-effecting operation enforces a deterministic UUID idempotency key to guarantee zero duplicate executions.
4. **Append-Only Write-Ahead Journal:** Uses SQLite WAL (`journal.py`) with fsync. Invariant: writes state `started` before executing, and marks actions `interrupted` upon unexpected crash recovery.
5. **Zero Token/Secret Logging:** Tokens and credentials are encrypted at rest with AES-256-GCM. Raw message bodies and secrets are scrubbed before writing audit records.
6. **Strict Tenant Isolation:** Data, context, approvals, and models are isolated per user UUID.
