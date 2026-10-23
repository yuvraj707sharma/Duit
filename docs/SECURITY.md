# FastAgent Security Architecture & Guidelines

FastAgent enforces strict, code-level safety boundaries to ensure zero unauthorized actions, zero data leakage, and resilient operation.

---

## 1. Non-Negotiable Policy Enforcement in Code

Security rules live in pure Python code (`backend/app/policy/`), never entrusted solely to LLM prompt instructions:

- **Third-Party Content Inbound Action Gate**:
  - Any action derived from an inbound email or WhatsApp message from a third party (e.g. "Rahul sent an email saying 'cancel my 4pm'") strictly requires the primary user's explicit confirmation before execution.
- **Strict Recipient Allowlists**:
  - Outbound emails or calendar invites to recipients not on the user's verified contact/domain allowlist are flagged for high-risk confirmation or blocked.
- **Per-User Rate Limits**:
  - Side-effecting actions are throttled per user to mitigate prompt-injection loops and abuse.
- **Per-Action Confirmation Thresholds**:
  - High-risk actions (`cancel_meeting`, `send_email`, `book_something`) always require explicit user confirmation unless high-confidence learning thresholds have been reached with 10+ identical verified confirmations.

---

## 2. Secrets & Token Security (AES-256-GCM)

- Google OAuth 2.0 refresh tokens and third-party secrets are encrypted at rest using **AES-256-GCM** with authenticated data.
- The 256-bit encryption key is sourced solely from `TOKEN_ENCRYPTION_KEY` in environment variables and never written to database tables or logs.
- Webhook endpoints require signature and bearer token verification (`EVOLUTION_WEBHOOK_SECRET` / `GLOBAL_API_KEY`).

---

## 3. Strict Tenant Isolation

- Every database query, vector search, approval request, and tool execution is strictly scoped by `user_id`.
- There is **no shared model context** between users. LLM sessions and decision state are completely ephemeral and wiped after each turn.
- Synthetic/sanitized context is utilized for cloud LLM calls to prevent PII leakage.

---

## 4. Idempotency on Side-Effecting Tools

- Every side-effecting action (`send_email`, `create_calendar_event`, `cancel_calendar_event`) generates and requires an `idempotency_key` (UUID v4).
- If a webhook retry or network glitch resends an action request, the tool adapter recognizes the duplicate key and returns the cached result without executing twice.

---

## 5. Append-Only Audit Logging

- Every incoming message, classifier decision, LLM argument extraction, confirmation prompt, and execution result is written to an immutable append-only audit log.
- Raw message bodies, OAuth tokens, and sensitive headers are scrubbed before logging.

---

## 6. WhatsApp Whitelist Firewall & Group Suppression

- **Sender Whitelisting**: If `WHATSAPP_AUTHORIZED_NUMBERS` is configured, incoming messages from foreign/unauthorized numbers are dropped immediately without execution.
- **Group & Broadcast Drops**: Any inbound message from a group (`@g.us`), broadcast list (`@broadcast`), or newsletter/channel (`@newsletter`) is discarded. Only verified direct chats (`@s.whatsapp.net`, `@lid`) are processed.
- **New Number Registration Gate**: Unregistered users receive a secure onboarding invite link (`/connect`) and cannot trigger tool executions until authenticated.

---

## 7. Desktop Executor Containment & Emergency Kill-Switch

- **Allowlist-Only Skills**: Strictly typed execution (`open_app`, `open_url`, `create_note`, `type_text`, `set_volume`, `search_files`). No shell command execution, no file deletion.
- **Password Field Protection**: `type_text` checks focused element states and strictly refuses to type into password fields.
- **Global Hardware Kill-Switch**: `Ctrl+Shift+K` (or `Cmd+Shift+K`) instantly halts active desktop actions and revokes session tokens.
- **Write-Ahead Journal (WAL SQLite)**: States transitioned (`received -> decided -> confirmed -> started -> completed`). `started` is written before execution; startup reconciliation marks incomplete operations as `interrupted`.

