# FastAgent — WhatsApp Module

This folder contains the WhatsApp integration for FastAgent.

## Structure

```
whatsapp/
├── directorbot/          # Main WhatsApp bot server (Node.js + Baileys)
│   ├── server.js         # Express API + Google OAuth + Admin dashboard
│   ├── src/
│   │   ├── whatsapp/
│   │   │   └── baileysManager.js   ← CORE: User state machine + message router
│   │   ├── database/
│   │   │   └── db.js               ← MySQL schema (auto-creates tables)
│   │   └── services/
│   │       └── authService.js      ← Admin login (dashboard)
│   └── .env.example
└── evolution-go/         # Evolution API (WhatsApp HTTP gateway, alternative)
```

## How It Works

1. **Single Bot Number** — One WhatsApp number runs 24/7
2. **User State Machine** — Every new user goes through:
   ```
   NEW → ONBOARDING_NAME → ONBOARDING_USE_CASE → ONBOARDING_AUTH → ACTIVE
   ```
3. **Google OAuth per User** — Each user gets their own secure Google token (Calendar + Gmail)
4. **FastAgent Backend** — ACTIVE users' messages are routed to the Python backend at `BACKEND_URL`

## Setup

### 1. MySQL — Create the database

```sql
-- Run these in your MySQL client (no need to create tables; app does it automatically)
CREATE DATABASE IF NOT EXISTS fastagent_wa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Configure `.env`

```bash
cd whatsapp/directorbot
cp .env.example .env
# Edit .env with your MySQL password and Google OAuth credentials
```

### 3. Google Cloud Setup

1. Go to https://console.cloud.google.com
2. Create a project → APIs & Services → Enable:
   - Google Calendar API
   - Gmail API
   - Google+ API (for user info)
3. Credentials → Create OAuth 2.0 Client ID (Web Application)
4. Add Authorized Redirect URI: `http://YOUR_SERVER:5122/auth/google/callback`
5. Copy Client ID and Client Secret into `.env`

### 4. Install & Run

```bash
cd whatsapp/directorbot
npm install
npm start
```

### 5. Connect WhatsApp

1. Open http://localhost:5122 in your browser
2. Login with admin credentials (default: `admin@fastagent.ai` / `admin123`)
3. Scan the QR code with your FastAgent WhatsApp number
4. The bot is now live! Text it from any phone to test

## Testing

Text the bot number from 3-5 different phones. Each user will go through onboarding independently.

```
User texts: "Hi"
Bot: "Welcome to FastAgent! What's your name?"
User: "Yuvraj"
Bot: "Nice to meet you, Yuvraj! How do you plan to use FastAgent? [1-4]"
User: "1"
Bot: "[Google auth link] — or reply 'skip'"
User: "skip"
Bot: "You're all set! FastAgent is ready. Text me anything..."
```

## Admin Dashboard

- **URL**: http://localhost:5122
- **Users**: `GET /api/users` — list all registered users
- **Stats**: `GET /api/stats` — total/active/new/google-connected counts
- **Status**: `GET /api/status` — bot status + backend health
- **Block user**: `POST /api/users/:phone/block`
- **Unblock user**: `POST /api/users/:phone/unblock`
- **Test ping**: `POST /api/test/whatsapp-ping` with `{ "phone": "919876543210" }`

## Environment Variables

| Variable | Description |
|---|---|
| `PORT` | Server port (default: 5122) |
| `APP_PUBLIC_URL` | Public URL (for OAuth redirect, e.g. `https://yourdomain.com`) |
| `MYSQL_HOST` | MySQL host |
| `MYSQL_PASSWORD` | MySQL password |
| `MYSQL_DATABASE` | Database name (default: `fastagent_wa`) |
| `BACKEND_URL` | FastAgent Python backend URL (default: `http://localhost:8000`) |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret |
| `GOOGLE_REDIRECT_URI` | Must match what you set in Google Console |
| `ADMIN_EMAIL` | Admin dashboard login email |
| `ADMIN_PASSWORD` | Admin dashboard login password |
