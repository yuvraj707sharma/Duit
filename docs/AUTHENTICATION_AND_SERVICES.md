# 🔐 FastAgent Service Authentication & Identity Architecture

This document details how FastAgent securely verifies, authenticates, and connects external user services (Google Suite, Desktop Executor, WhatsApp Identity).

---

## 1. Identity & Multi-Tenant Binding

Every user in FastAgent is identified by a deterministic UUIDv5 identifier:

```python
user_uuid = get_user_uuid_from_channel_id(phone_number)
```

- When a user sends a message on WhatsApp (`+919876543210`), the phone number is converted to `user_uuid`.
- All tokens, pending approvals, desktop sessions, audit logs, and settings are strictly indexed by this `user_uuid`.
- **Zero Cross-Contamination**: User A cannot view, modify, or trigger actions on User B's profile.

---

## 2. Google Suite Service Authentication (Calendar, Gmail, Contacts)

### A. How FastAgent Checks If Google Is Authenticated
1. When an action requires Google Calendar (`calendar.create_event`, `calendar.list_events`) or Gmail (`email.send`, `email.search`):
2. FastAgent queries the `OAuthToken` store for `(user_id, provider='google')`.
3. Three possible states:

| Token State | FastAgent Behavior | User Experience |
| :--- | :--- | :--- |
| **Active & Valid** | Token is decrypted with AES-256-GCM and sent to Google API Client. | Action executes instantly (<50ms). |
| **Expired (has refresh token)** | Transparent auto-refresh using `flow.refresh_token` without prompting user. Updated token re-encrypted. | Action executes without disruption. |
| **Missing / Not Connected** | Tool returns structured failure: `{"success": false, "error": "Google account not linked", "auth_url": "/api/auth/google/url?user_id=..."}`. | FastAgent sends WhatsApp message with a 1-click Google OAuth button. |

### B. Encryption at Rest
- Tokens are encrypted using **AES-256-GCM** via `backend.app.security.crypto.encrypt_token()`.
- Sourced from `TOKEN_ENCRYPTION_KEY` in `.env`.
- Plaintext tokens are never written to disk, database, or logs.

---

## 3. Desktop Executor Authentication & Presence

### A. How FastAgent Checks If Desktop Is Connected
1. The local Python sidecar on the user's laptop connects outbound over WebSocket:
   ```text
   ws://localhost:8000/api/desktop/ws?user_id={user_id}
   Header: x-shared-secret: {DESKTOP_SHARED_SECRET}
   ```
2. The sidecar maintains an active heartbeat ping every 5 seconds.
3. The server tracks `last_heartbeat` in `PresenceManager` ([`backend/app/desktop/presence.py`](file:///e:/Inovvate/backend/app/desktop/presence.py)).
4. `presence_manager.is_online(user_id)` returns `True` if `(now - last_heartbeat) < 30.0` seconds.

### B. Cross-Channel Delegation Check
- When a user on WhatsApp says: *"Open VS Code on my laptop"*:
  1. FastAgent checks `presence_manager.is_online(user_id)`.
  2. If `False`: FastAgent immediately replies: `"Laptop offline"`.
  3. If `True`: FastAgent dispatches the allowlisted command over the WebSocket to the laptop sidecar.

---

## 4. WhatsApp Onboarding & Verification Gate

```
Incoming WhatsApp Message
           │
           ▼
┌──────────────────────────────────────┐
│ Whitelist Gatekeeper                 │
│ Check WHATSAPP_AUTHORIZED_NUMBERS    │
└──────────────────┬───────────────────┘
                   │
    ┌──────────────┴──────────────┐
    ▼                             ▼
Unauthorized Number         Whitelisted Number
(Dropped immediately)             │
                                  ▼
                   ┌──────────────────────────────┐
                   │ Is User Registered?          │
                   │ (repository.is_user_reg.)    │
                   └──────────────┬───────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
   New / Unregistered Phone                         Registered Phone
         │                                                 │
         ▼                                                 ▼
Send Onboarding Card:                              Process through
"Link your accounts at:                            4-Stage Cascade
 fastagent.ai/connect"                             (Sub-50ms)
(NO tools executed)
```

1. **If New Phone**: FastAgent sends a welcoming onboarding card directing the user to connect their Google Suite and Desktop executor at `/connect`.
2. **If Registered Phone**: FastAgent loads the user's tenant profile and executes actions through the cascade.
