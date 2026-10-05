# FastAgent Third-Party Resources & Setup Guide

This guide provides concrete, verified instructions for setting up the external components of FastAgent.

---

## 1. Laya (Fast System 1 Decision Layer)

Laya runs as a containerized HTTP service (`laya-serve`) or directly in Python.

### Running via Docker
FastAgent's `docker-compose.yml` launches `laya-serve`:
```yaml
laya:
  image: python:3.11-slim
  command: >
    sh -c "pip install torch laya uvicorn fastapi &&
           python -m laya.serve"
  environment:
    - LAYA_HOST=0.0.0.0
    - LAYA_PORT=8001
    - LAYA_MODELS=multilingual
    - LAYA_PRELOAD=1
  ports:
    - "8001:8001"
```

### Direct Python Usage
```python
from laya import Router

# Initialize multilingual router (handles English, Hindi, Hinglish, etc.)
router = Router(default="multilingual")

# Make a zero-latency calibrated decision
decision = router.predict(
    state="Bhai Rahul ko mail bhej do meeting confirm karne ke liye",
    questions={
        "intent": {
            "type": "choice",
            "criteria": {
                "schedule_meeting": "Schedule a calendar event",
                "send_email": "Draft or send an email",
                "other": "Other requests"
            }
        },
        "risk": {
            "type": "choice",
            "criteria": {
                "low": "Read only or harmless action",
                "high": "Sends communication or changes calendar"
            }
        }
    }
)
```

---

## 2. Evolution Go (WhatsApp Gateway)

Evolution Go provides a WhatsApp Web bridge over REST and Webhooks.

### Docker Configuration
In `docker-compose.yml`:
```yaml
evolution-go:
  image: evoapicloud/evolution-go:latest
  environment:
    - SERVER_PORT=8080
    - GLOBAL_API_KEY=evolution_dev_api_key_12345
    - POSTGRES_AUTH_DB=postgresql://fastagent:fastagent_dev_password@postgres:5432/evogo_auth?sslmode=disable
    - POSTGRES_USERS_DB=postgresql://fastagent:fastagent_dev_password@postgres:5432/evogo_users?sslmode=disable
    - WEBHOOK_URL=http://backend:8000/api/webhooks/evolution
  ports:
    - "8080:8080"
  depends_on:
    - postgres
```

### WhatsApp Instance Pairing
1. Create instance:
   ```bash
   curl -X POST http://localhost:8080/instance/create \
     -H "apikey: evolution_dev_api_key_12345" \
     -H "Content-Type: application/json" \
     -d '{"instanceName": "fastagent-primary", "integration": "WHATSAPP-BAILEYS"}'
   ```
2. Fetch QR Code:
   ```bash
   curl -X GET http://localhost:8080/instance/qr \
     -H "apikey: evolution_dev_api_key_12345"
   ```
3. Scan the QR code in WhatsApp -> Linked Devices.

---

## 3. Ollama (Local Qwen LLM)

For offline, private, or local testing:

1. Install Ollama from [ollama.ai](https://ollama.ai).
2. Pull the recommended multilingual instruction model:
   ```bash
   ollama run qwen2.5:7b-instruct
   ```
3. Configure `.env`:
   ```env
   DEFAULT_LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=qwen2.5:7b-instruct
   ```

---

## 4. Google OAuth 2.0 (Gmail & Google Calendar)

### Setup in Google Cloud Console
1. Create a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable APIs:
   - **Google Calendar API**
   - **Gmail API**
3. Configure OAuth Consent Screen (External or Internal for testing).
4. Add Narrow Scopes:
   - `https://www.googleapis.com/auth/calendar.events` (Manage calendar events)
   - `https://www.googleapis.com/auth/calendar.readonly` (Read calendar)
   - `https://www.googleapis.com/auth/gmail.send` (Send emails)
   - `https://www.googleapis.com/auth/gmail.readonly` (Read emails)
5. Create OAuth 2.0 Client ID (Web Application):
   - Authorized redirect URIs: `http://localhost:8000/api/auth/google/callback`
6. Copy Client ID and Client Secret into `.env`.
