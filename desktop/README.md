# FastAgent — Desktop Executor & Sidecar 🖥️⚡

FastAgent Desktop is an ultra-fast, local Windows executor and floating HUD widget that gives FastAgent the ability to interact with your computer, open applications, search files, manage workflows, and listen to voice commands.

---

## 🏛️ Architecture: How FastAgent Controls Windows

```
┌────────────────────────────────────────────────────────┐
│ FastAgent Desktop App (.exe)                           │
│                                                        │
│  ┌─────────────────────────┐  IPC  ┌────────────────┐ │
│  │ Frameless Electron UI   │◄─────►│ Windows Sidecar│ │
│  │ • Push-To-Talk Mic      │       │ • Process Exec │ │
│  │ • 2s Status Overlay     │       │ • SQLite WAL   │ │
│  │ • Ctrl+Shift+K Hotkey   │       │ • faster-whisp.│ │
│  └─────────────────────────┘       └───────┬────────┘ │
└────────────────────────────────────────────┼───────────┘
                                             │ Outbound WebSocket
                                             ▼
                               ┌─────────────────────────┐
                               │ FastAgent 4-Stage Hub   │
                               │ (Cascade & Policy Engine│
                               └─────────────────────────┘
```

### 1. Electron Frontend (`src/` & `electron/`)
* **Frameless HUD Widget:** Sits on the right edge of your desktop, collapsible into a subtle 80x80 floating pill or expandable to a 380x600 command hub.
* **Global Kill-Switch (`Ctrl+Shift+K`):** Registers an OS-level keyboard hook. Pressing `Ctrl+Shift+K` at any moment instantly aborts running desktop actions.
* **2-Second Cancel Window:** Destructive or automated actions trigger a floating countdown overlay giving the user a 2-second grace period to cancel before execution.

### 2. Local Python Sidecar (`sidecar/`)
* **OS Application Management (`skills.py`):** Launches and monitors approved Windows applications (`notepad`, `calculator`, `code`, `browser`, `terminal`).
* **Strict Whitelist & Safety:** Completely blocks destructive shell scripts (`rm`, `format`, `eval`) via in-code policy validation.
* **Crash-Resilient WAL Journal (`journal.py`):** Writes every action state to an SQLite Write-Ahead Log (`received` → `started` → `completed`). If the computer crashes or reboots mid-action, it reconciles cleanly on next boot.
* **Encrypted Context Store (`context_store.py`):** Keeps recent operation context encrypted at rest with AES-256-GCM, automatically redacting passwords, secrets, and typed text.
* **Local STT Engine (`voice_stt.py`):** Uses `faster-whisper` + Silero VAD for sub-100ms offline voice transcription.

---

## 🚀 How to Run in Development

```powershell
# In terminal 1: Start the FastAgent Backend Gateway
cd e:\Inovvate
python -m uvicorn backend.app.main:app --port 8000

# In terminal 2: Start the Desktop Sidecar Agent
cd e:\Inovvate\desktop\sidecar
python runner.py

# In terminal 3: Start the Desktop Electron HUD Widget
cd e:\Inovvate\desktop
npm install
npm run electron:dev
```

---

## 📦 How to Build the Standalone `.exe`

### 1. Compile the Python Sidecar to `.exe`
```powershell
cd e:\Inovvate\desktop
pip install pyinstaller
npm run build:sidecar
```
* Generates `dist/FastAgentSidecar.exe` (a single, self-contained Windows executable).

### 2. Package the Full Electron Desktop App to `.exe`
```powershell
cd e:\Inovvate\desktop
npm run build:exe
```
* Generates `dist-exe/FastAgent-Setup.exe` and portable `FastAgent.exe`.
* Double-clicking this `.exe` launches the full widget and local system automator!
