# FastAgent ⚡

> **Fast, Cheap, Safe AI Scheduling & Email Assistant with Continuous Learning**  
> *Hackathon Project — Target Deadline: 24 October 2026*

FastAgent solves the latency, cost, and safety dilemma of generative AI assistants by routing messages through a **deterministic 4-stage cascade**:

1. **Stage 1 (Hard Rules in Code):** Sub-millisecond deterministic emergency stops, greetings, and security blocklists.
2. **Stage 2 (Fast Decision Layer - Laya System 1):** Sub-25ms multilingual intent, risk, and needs-confirmation classification with calibrated confidence (ModernBERT / mmBERT).
3. **Stage 3 (Targeted LLM Extraction):** Free-tier Gemini or local Ollama (Qwen) called *only* when structured arguments or email drafts are needed.
4. **Stage 4 (Code Policy Engine & Human Confirmation):** Strict in-code safety gates (recipient allowlists, 3rd-party inbound trigger gates, per-user rate limits, and WhatsApp confirmation prompts).

---

## Architecture Overview

```
WhatsApp / Web Message
       │
       ▼
┌───────────────────────────────┐
│ Stage 1: Hard Rules in Code   │  ──(Rule match)──► Direct response (<1ms)
└───────────────────────────────┘
       │ (Pass)
       ▼
┌───────────────────────────────┐
│ Stage 2: Laya Multilingual    │  ──(Read query)──► Direct Tool (<25ms)
└───────────────────────────────┘
       │ (Side-effect / args needed)
       ▼
┌───────────────────────────────┐
│ Stage 3: Targeted LLM Extract │
└───────────────────────────────┘
       │
       ▼
┌───────────────────────────────┐
│ Stage 4: Code Policy Engine   │
└───────────────────────────────┘
   │                         │
 (Approved)           (Needs Confirmation)
   │                         │
   ▼                         ▼
Execute Tool           Send WhatsApp / App Confirmation
   │                         │
   └────────────┬────────────┘
                │
                ▼
┌───────────────────────────────┐
│ Append-Only Audit & Learning  │
│ Log (pgvector Few-Shot Tuning)│
└───────────────────────────────┘
```

---

## Quick Start (Zero External Accounts Needed)

The repository ships with complete mock adapters (`MockChannel`, `MockLLMProvider`, `MockCalendarTool`, `MockGmailTool`) enabling the full pipeline to run offline immediately:

### 1. Run Automated Test Suite
```bash
pytest backend/tests/
```

### 2. Run Router Benchmarks
```bash
python eval/bench_routers.py
```

### 3. Run Active Learning Curve Simulation
```bash
python eval/learning_curve.py
```

### 4. Boot Full Containerized Stack
```bash
docker compose up -d
```

### 5. Launch Web / Mobile Dashboard
```bash
cd web
npm install
npm run dev
# Open http://localhost:5173
```

---

## Non-Negotiable Engineering Guardrails

- **Code-Level Policy Engine:** Security and confirmation gates live in pure Python (`backend/app/policy/`), never entrusted solely to prompt instructions.
- **Third-Party Content Inbound Action Gate:** Any outbound action triggered by an inbound email or WhatsApp message from a third party strictly requires the primary user's explicit confirmation.
- **Side-Effect Idempotency Keys:** Every side-effecting tool execution (`send_email`, `create_calendar_event`, `cancel_calendar_event`) generates and enforces a unique UUID idempotency key to prevent double executions.
- **Strict Tenant Isolation:** Every database record, audit log, and vector search is strictly scoped by `user_id`. No model state or context is shared across users.
- **Zero Token/Secret Leakage:** Refresh tokens encrypted with AES-256-GCM. Raw message bodies and secrets are never logged.
- **Active Learning on Explicit Actions Only:** Learns and tunes confidence thresholds only from explicit user approvals, edits, or rejections—never from silence.

---

## Repository Structure

```
fastagent/
  AGENTS.md             # Developer & AI assistant operating principles
  README.md             # Project documentation & overview
  docker-compose.yml    # Full local containerized infrastructure
  .env.example          # Environment variable template
  contracts/            # OpenAPI specification and JSON schemas (Source of Truth)
    decision.json
    intent.json
    tool_calls.json
    openapi.json
  docs/
    ARCHITECTURE.md     # Detailed sequence diagram and component breakdown
    RESOURCES.md        # Concrete setup guides for Laya, Evolution Go, Ollama, Google
    SECURITY.md         # Policy enforcement, AES-256-GCM crypto, tenant isolation
    DEMO.md             # Step-by-step walkthrough of demo scenarios
    REPO_NOTES.md       # Reference repositories analysis and role assignments
  backend/
    app/
      api/              # Webhooks, approvals, Google OAuth, metrics endpoints
      channels/         # MessagingChannel (Evolution Go WhatsApp & Mock)
      cascade/          # Stage 1 Rules, Stage 2 Laya Decision, Cascade Orchestrator
      llm/              # LLMProvider (Gemini, Ollama Qwen, Mock)
      tools/            # Calendar & Gmail adapters with idempotency keys
      policy/           # In-code PolicyEngine, recipient allowlists, rate limits
      learning/         # Append-only dataset log, few-shot vector retrieval, thresholds
      security/         # AES-256-GCM token encryption and OAuth helpers
      db/               # SQLAlchemy models & database connection
    tests/              # Negation, prompt injection, idempotency, tenant isolation tests
  eval/
    dataset/            # Multilingual evaluation dataset
    bench_routers.py    # Router accuracy & latency benchmark
    learning_curve.py   # Active learning curve accuracy simulator
  loadtest/
    basic.js            # k6 load testing script
  web/                  # React + Vite + TypeScript + Tailwind + Capacitor app
```
