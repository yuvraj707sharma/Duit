# Reference Repositories Analysis & Role Assignments

This document provides architectural notes and role assignments for the reference repositories analyzed prior to building **FastAgent**.

---

## 1. `laya`

- **What it does:**
  A fast, non-autoregressive "System 1" decision engine with calibrated probabilities. It provides instant routing, question classification, intent extraction, risk assessment, and confidence scoring without the latency or token cost of large autoregressive LLMs.
- **Real Public API (verified from source):**
  - **Python Library (`laya/__init__.py`, `laya/router.py`, `laya/structured.py`):**
    - `laya.Router(default="multilingual", models=..., min_confidence=...)`
    - `Router.predict(state: str, questions: dict, model=None, min_confidence=None, ...)` -> returns answers and decision metadata (`RouteDecision`).
    - `laya.decide(state: str, questions: dict, ...)` / `laya.decide_batch(...)` -> `DecisionResult`
    - `laya.confidence.check_min_confidence(answer, min_confidence=...)` / `flag_low_confidence(...)`
    - `laya.email.clean_email_body(raw_email: str)`
    - `laya.lang.analyse(text: str)` / `detect_script(text: str)` / `is_english(text: str)`
  - **HTTP Server (`laya/serve.py` / `laya-serve`):**
    - `POST /v1/systemone` — payload `{"state": "...", "questions": {...}, "model": "...", "min_confidence": ...}` -> returns `{"answers": {...}, "usage": {"input_tokens": int, "output_tokens": int}}`
    - `GET /health` — health check and device report (`{"status": "ok", "device": "..."}`)
    - `GET /models` — lists loaded and available checkpoints
- **License:** Apache 2.0 (`LICENSE`)
- **Setup Requirements:**
  - Python 3.10+, PyTorch or ONNX runtime.
  - Hugging Face checkpoints: `convaiinnovations/laya` (English ModernBERT-large), `convaiinnovations/laya-multilingual` (mmBERT-base, 100+ languages including Hindi/Hinglish), `convaiinnovations/laya-typed-decisions`.
  - Config env vars: `LAYA_HOST`, `LAYA_PORT`, `LAYA_DEVICE`, `LAYA_PRELOAD`, `LAYA_MODELS`, `LAYA_API_KEY`, `LAYA_MAX_CONCURRENT`.
- **Platform Limits:**
  - Max choice options per question: <= 100 (engineering best practice: <= 20).
  - Max total options across questions: 512.
  - Context length limit: 512–1024 tokens depending on checkpoint.
- **Assigned Role:** **`USE`**
  - *Reason:* Primary decision layer for FastAgent via `laya-serve` container and `Router(default="multilingual")` adapter. Handles multilingual intent routing, risk scoring, and needs-confirmation classification with sub-50ms latency.

---

## 2. `evolution-go`

- **What it does:**
  A high-performance WhatsApp API server written in Go, wrapping the `whatsmeow` library. Exposes REST endpoints and webhooks for real-time bi-directional WhatsApp messaging, instance management, and QR/passkey pairing.
- **Real Public API (verified from `pkg/routes/routes.go` and handlers):**
  - **Instance Management:**
    - `POST /instance/create`
    - `GET /instance/all`
    - `GET /instance/info/:instanceId`
    - `DELETE /instance/delete/:instanceId`
    - `POST /instance/connect`
    - `GET /instance/status`
    - `GET /instance/qr`
    - `POST /instance/pair`
    - `POST /instance/disconnect`
    - `DELETE /instance/logout`
  - **Messaging & Dispatch:**
    - `POST /send/text` (body: `{"number": "...", "text": "..."}`)
    - `POST /send/button`, `POST /send/list`, `POST /send/poll`, `POST /send/media`, `POST /send/contact`, `POST /send/location`
    - `POST /message/markread`
    - `POST /message/react`
    - `POST /message/delete`
  - **System & Ceremonies:**
    - `GET /server/ok`
    - `GET /passkey-ceremony/:token`, `POST /passkey-ceremony/:token/response`, `POST /passkey-ceremony/:token/confirm`
  - **Webhook Dispatches:**
    - Emits HTTP POST events (`messages.upsert`, `connection.update`, `qrcode.updated`) to configured `WEBHOOK_URL`.
- **License:** Apache 2.0 (`LICENSE`)
- **Setup Requirements:**
  - Docker container (`evoapicloud/evolution-go` or Go 1.22+ build).
  - PostgreSQL databases for authentication & session storage (`POSTGRES_AUTH_DB`, `POSTGRES_USERS_DB`).
  - Environment variables: `GLOBAL_API_KEY`, `SERVER_PORT`, `WEBHOOK_URL`.
- **Platform Limits:**
  - WhatsApp Web protocol rate limits and phone pairing requirements.
  - Requires persistent database storage for session tokens.
- **Assigned Role:** **`USE`**
  - *Reason:* Primary WhatsApp integration engine placed strictly behind FastAgent's `MessagingChannel` interface, isolated so official WhatsApp Cloud API or Telegram can be swapped in without leaking Evolution-specific structures.

---

## 3. `laya-mlx`

- **What it does:**
  Apple Silicon MLX-native implementation of Laya for hardware-accelerated local inference on macOS M-series chips.
- **Real Public API (verified from source):**
  - `laya_mlx.Agent`, `laya_mlx.Router`, `laya_mlx.load()`
  - CLI/Server: `laya-mlx-serve`
- **License:** Apache 2.0 (`LICENSE`)
- **Setup Requirements:** macOS with Apple Silicon (M1/M2/M3/M4), `mlx`, `mlx-lm`, Python 3.10+.
- **Platform Limits:** Metal framework dependent; non-functional on Linux x86_64, Windows, or cloud container runtimes without Apple hardware.
- **Assigned Role:** **`SKIP`**
  - *Reason:* FastAgent runs on a cross-platform Docker Compose stack (Linux/Windows containers); MLX is strictly Apple Silicon macOS only and cannot run in standard server containers.

---

## 4. `save-token-jev-clean`

- **What it does:**
  A context compaction engine for coding agent transcripts. It evaluates multi-turn tool traces and selectively drops unneeded tool outputs while preserving user/assistant text verbatim.
- **Real Public API (verified from source):**
  - CLI: `save-token-jev compact --format <anthropic|openai|opencode|codex-jsonl> --input <file> --output <file>`
  - Adapters: `CodexAdapter`, `OpenCodeAdapter`, `ClaudeAdapter`, `AnthropicAdapter`, `OpenAIAdapter`.
- **License:** MIT (`LICENSE`)
- **Setup Requirements:** Node.js 20+, `TYPESAFE_API_KEY`.
- **What it adds beyond Laya:** Specifically designed for coding agent transcript pruning (multi-turn tool execution logs in IDE environments like Codex or Claude Code).
- **Platform Limits:** Node.js runtime; requires external Jev API key for scoring tool traces.
- **Assigned Role:** **`REFERENCE-ONLY`**
  - *Reason:* FastAgent is a conversational personal assistant for WhatsApp/chat scheduling and email, not an IDE coding agent. We borrow its clean adapter abstractions and fail-open design principles without adding a Node.js runtime dependency to the backend.

---

## 5. `agentscope`

- **What it does:**
  A heavy multi-agent runtime framework with actor models, agent-to-agent message passing pipelines, and LLM orchestration abstractions.
- **Real Public API (verified from source):**
  - `agentscope.agents.AgentBase`, `DialogAgent`, `UserAgent`, `DictDialogAgent`
  - `agentscope.message.Msg`
  - `agentscope.pipelines.SequentialPipeline`, `IfElsePipeline`, `SwitchPipeline`
  - `agentscope.models.load_model_by_config()`
- **License:** Apache 2.0 (`LICENSE`)
- **Setup Requirements:** Python 3.9+, extensive third-party dependency tree.
- **Platform Limits:** Substantial framework overhead, prompt-driven orchestrations, lack of hardcoded deterministic safety rules.
- **Assigned Role:** **`REFERENCE-ONLY`**
  - *Reason:* FastAgent requires deterministic, sub-100ms cascade logic, hardcoded safety policy engines in Python/Pydantic, and strict tenant isolation. AgentScope is too heavy and prompt-centric for our latency and safety constraints.

---

## Summary of Role Assignments

| Repository | Assigned Role | Rationale |
|---|---|---|
| **`laya`** | **`USE`** | Fast System 1 decision engine for intent, risk, and confidence classification via `laya-serve` & `Router(default="multilingual")`. |
| **`evolution-go`** | **`USE`** | WhatsApp messaging gateway integrated behind `MessagingChannel`. |
| **`laya-mlx`** | **`SKIP`** | Restricted to Apple Silicon macOS; incompatible with Docker Compose on Linux/Windows. |
| **`save-token-jev-clean`** | **`REFERENCE-ONLY`** | Coding agent transcript compaction not needed; borrow adapter patterns. |
| **`agentscope`** | **`REFERENCE-ONLY`** | Heavyweight agent framework; FastAgent uses lean, deterministic Python cascade orchestrator. |
