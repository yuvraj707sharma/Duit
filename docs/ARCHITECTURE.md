# FastAgent Architecture

FastAgent solves the speed, cost, and safety dilemma of conversational AI assistants through a **4-stage deterministic cascade**. Instead of querying an expensive, slow, non-deterministic cloud LLM for every message, FastAgent routes requests through fast, cheap, and safe localized stages.

---

## The 4-Stage Cascade

```
Incoming User Message (WhatsApp / Web)
                  │
                  ▼
┌───────────────────────────────────────────────┐
│ Stage 1: Hard Rules in Code                   │
│ - Exact blocklists & emergency cancel/stop    │  ──(Matches rule)──► Direct response (<1ms)
│ - Syntax allowlists & regex pre-filtering     │
└───────────────────────────────────────────────┘
                  │ (Passes through)
                  ▼
┌───────────────────────────────────────────────┐
│ Stage 2: Fast Decision Layer (Laya)           │
│ - Multilingual Router (mmBERT / ModernBERT)   │  ──(High conf, zero args)──► Read actions (<25ms)
│ - Classify Intent, Risk, Needs-Confirmation   │
│ - Calibrated confidence estimation            │
└───────────────────────────────────────────────┘
                  │ (Requires extraction / low conf)
                  ▼
┌───────────────────────────────────────────────┐
│ Stage 3: Targeted LLM Extraction (Gemini/Qwen)│
│ - Extract tool arguments (JSON schema bound)  │  ──(Extracted structured JSON)
│ - Draft email / meeting invitation text       │
└───────────────────────────────────────────────┘
                  │
                  ▼
┌───────────────────────────────────────────────┐
│ Stage 4: Code Policy Engine & Approvals       │
│ - Check recipient allowlists & rate limits    │
│ - Inbound 3rd-party trigger safety check      │
│ - Risk & confidence evaluation                │
└───────────────────────────────────────────────┘
         │                             │
    (Approved)                 (Needs Confirmation)
         │                             │
         ▼                             ▼
┌──────────────────┐          ┌────────────────────────────────┐
│ Side-Effect Tool │          │ WhatsApp / App Confirmation:   │
│ (Idempotent call)│          │ "Send this email? [Yes / No]"  │
└──────────────────┘          └────────────────────────────────┘
         │                             │
         └──────────────┬──────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────┐
│ Append-Only Audit Log & Learning Dataset      │
│ - Vector embedding for few-shot correction    │
│ - Updates user-specific approval thresholds   │
└───────────────────────────────────────────────┘
```

---

## Message Processing Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as User (WhatsApp / Web)
    participant WH as Webhook / API Gateway
    participant Orch as Cascade Orchestrator
    participant Rules as Stage 1: Rules Engine
    participant Laya as Stage 2: Laya Decision Layer
    participant LLM as Stage 3: LLM Provider (Gemini/Qwen)
    participant Policy as Stage 4: Policy Engine
    participant Tools as Google Tools (Gmail/Calendar)
    participant DB as Postgres + Vector / Audit Log

    User->>WH: "Move my 4pm meeting with Rahul to tomorrow 5pm"
    WH->>Orch: Dispatch message (user_id, channel, text)
    
    rect rgb(240, 248, 255)
    Note over Orch,Rules: Stage 1: Hard Rules (<1ms)
    Orch->>Rules: Check hard rules & allowlists
    Rules-->>Orch: Pass-through (no static rule match)
    end

    rect rgb(255, 250, 240)
    Note over Orch,Laya: Stage 2: Laya Multilingual Decision (<30ms)
    Orch->>Laya: predict(state, questions=[intent, risk, needs_conf])
    Laya-->>Orch: {intent: reschedule_meeting, risk: medium, needs_conf: true, confidence: 0.94}
    end

    rect rgb(245, 255, 245)
    Note over Orch,LLM: Stage 3: Targeted Argument Extraction (~350ms)
    Orch->>LLM: Extract arguments (Schema: RescheduleCalendarEvent)
    LLM-->>Orch: {event_id: "evt_123", new_start: "2026-10-02T17:00:00Z", new_end: "2026-10-02T18:00:00Z"}
    end

    rect rgb(255, 240, 245)
    Note over Orch,Policy: Stage 4: Policy & Safety Validation (<2ms)
    Orch->>Policy: Evaluate action safety(user_id, action, args, confidence)
    Policy-->>Orch: Confirmation Required (Risk: Medium, Side-effecting calendar modification)
    end

    Orch->>DB: Store pending approval record & audit log
    Orch->>User: "Should I move 'Sync with Rahul' to tomorrow at 5:00 PM? Reply YES to confirm."
    
    User->>WH: "YES"
    WH->>Orch: Handle confirmation reply
    Orch->>Tools: Execute reschedule_meeting(idempotency_key="uuid-1234", ...)
    Tools-->>Orch: Success (Calendar event updated)
    Orch->>DB: Log explicit approval -> Feed to Learning Dataset
    Orch->>User: "Moved your meeting with Rahul to tomorrow at 5:00 PM."
```

---

## Component Architecture

1. **Backend Service (`backend/app`)**:
   - **`api/`**: FastAPI REST endpoints for WhatsApp webhooks, OAuth2 flows, approvals API, and Prometheus `/metrics`.
   - **`channels/`**: `MessagingChannel` interface isolating `EvolutionChannel` and `MockChannel`.
   - **`cascade/`**: The 4-stage orchestrator coordinating hard rules, Laya System 1 predictions, and LLM extractions.
   - **`llm/`**: `LLMProvider` interface implementing `GeminiProvider` (with sanitized/synthetic data), `OllamaProvider` (local Qwen), and `MockLLMProvider`.
   - **`tools/`**: Side-effecting adapters (`GmailToolAdapter`, `CalendarToolAdapter`, `MockTools`) with mandatory idempotency keys.
   - **`policy/`**: Strict in-code safety engine handling tenant isolation, allowlists, rate limiting, and third-party trigger gates.
   - **`learning/`**: Append-only log recording all user decisions/corrections, powering pgvector few-shot retrieval and automated confidence threshold tuning.
   - **`security/`**: AES-256-GCM token encryption and OAuth2 state verification.
2. **Frontend (`web/`)**:
   - React + Vite + TypeScript web dashboard and Capacitor Android mobile app.
   - Live approval queue, action log, per-stage latency telemetry, and learning curve tracker.
3. **Infrastructure**:
   - Docker Compose orchestrating PostgreSQL 16 with pgvector, Redis, Evolution Go, Laya Serve, Backend API, and Worker.
