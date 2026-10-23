import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  Browsers
} from '@whiskeysockets/baileys';
import pino from 'pino';
import QRCode from 'qrcode';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import { query, logActivity, listSkills, createSkill, deleteSkill } from '../database/db.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Single Bot Session & Message Cache ───────────────────────────────────────
let botSock = null;
let botQR = null;
let botStatus = 'DISCONNECTED';
let botPhoneNumber = null;
let isManualDisconnect = false;
let ioInstance = null;
const processedMessageIds = new Set();
const messageStore = new Map();

function saveMessageToStore(key, message) {
  if (key?.id && message) {
    messageStore.set(key.id, message);
    if (messageStore.size > 2000) {
      const oldestKey = messageStore.keys().next().value;
      messageStore.delete(oldestKey);
    }
  }
}

export function setSocketIO(io) {
  ioInstance = io;
}

function getBotNumber() {
  if (botSock?.user?.id) {
    return botSock.user.id.split('@')[0].split(':')[0];
  }
  return botPhoneNumber;
}

function emitStatus() {
  if (ioInstance) {
    ioInstance.emit('status_update', {
      bot: { status: botStatus, qr: botQR, number: getBotNumber() }
    });
  }
}

// ── User State Machine ───────────────────────────────────────────────────────
// States: NEW | ONBOARDING_NAME | ONBOARDING_USE_CASE | ONBOARDING_AUTH | ACTIVE | BLOCKED
const ONBOARDING_QUESTIONS = [
  { field: 'name',     prompt: '👋 Welcome to *ZORO*! I\'m your personal AI assistant.\n\nTo get started, what\'s your name?' },
  { field: 'use_case', prompt: '✨ Nice to meet you, {name}!\n\nHow do you plan to use ZORO? Pick a number:\n\n1️⃣  Personal productivity (calendar, emails, reminders)\n2️⃣  Business & work tasks\n3️⃣  Research & learning\n4️⃣  Just exploring\n\nReply with 1, 2, 3, or 4.' },
  { field: 'google_auth', prompt: '🔗 Almost done! To unlock your Google Calendar & Gmail superpowers, tap the link below and sign in with Google:\n\n{auth_link}\n\n_(You can also skip this and use text-only features for now — reply "skip")_' }
];

const USE_CASE_MAP = { '1': 'Personal productivity', '2': 'Business & work', '3': 'Research & learning', '4': 'Exploring' };

// ── Backend API Call ─────────────────────────────────────────────────────────
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

async function callFastAgentBackend(phoneNumber, message) {
  try {
    const resp = await fetch(`${BACKEND_URL}/api/webhooks/whatsapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: phoneNumber,
        text: message,
        channel: 'whatsapp',
        idempotency_key: `wa_${phoneNumber}_${Date.now()}`
      })
    });

    if (!resp.ok) {
      const errText = await resp.text();
      console.error(`[FastAgent Backend] HTTP ${resp.status}: ${errText}`);
      return null;
    }

    const data = await resp.json();
    return data.reply || data.text || data.message || null;
  } catch (err) {
    console.error('[FastAgent Backend] Fetch error:', err.message);
    return null;
  }
}

// ── User DB Helpers ──────────────────────────────────────────────────────────
async function getUser(phone) {
  try {
    const rows = await query('SELECT * FROM fastagent_users WHERE phone = ?', [phone]);
    return rows.length > 0 ? rows[0] : null;
  } catch { return null; }
}

async function createUser(phone) {
  try {
    await query(
      `INSERT INTO fastagent_users (phone, state) VALUES (?, 'NEW')
       ON DUPLICATE KEY UPDATE state = state`,
      [phone]
    );
    return await getUser(phone);
  } catch (err) {
    console.error('[DB] createUser error:', err.message);
    return null;
  }
}

async function updateUser(phone, fields) {
  try {
    const setClauses = Object.keys(fields).map(k => `\`${k}\` = ?`).join(', ');
    const values = [...Object.values(fields), phone];
    await query(`UPDATE fastagent_users SET ${setClauses} WHERE phone = ?`, values);
  } catch (err) {
    console.error('[DB] updateUser error:', err.message);
  }
}

// ── Generate Google OAuth Onboarding Link ────────────────────────────────────
function generateAuthLink(phone) {
  const baseUrl = process.env.APP_PUBLIC_URL || `http://localhost:${process.env.PORT || 5122}`;
  const encoded = Buffer.from(phone).toString('base64url');
  return `${baseUrl}/auth/google?user=${encoded}`;
}

// ── Send WhatsApp Message ────────────────────────────────────────────────────
async function sendMessage(jid, text) {
  try {
    if (!botSock) throw new Error('Bot socket not connected');
    const sent = await botSock.sendMessage(jid, { text });
    if (sent?.key && sent.message) {
      saveMessageToStore(sent.key, sent.message);
    }
    return sent;
  } catch (err) {
    console.error(`[Bot Send Error] jid=${jid}:`, err.message);
  }
}

// ── Main Message Handler ─────────────────────────────────────────────────────
async function handleFastAgentMessage(jid, phone, text) {
  const cleanPhone = phone.replace(/[^0-9]/g, '');
  const trimmedText = text.trim();

  // Get or create user record
  let user = await getUser(cleanPhone);
  if (!user) {
    user = await createUser(cleanPhone);
    if (!user) {
      await sendMessage(jid, '⚠️ Something went wrong. Please try again in a moment.');
      return;
    }
  }

  await logActivity('FASTAGENT_WA', `Inbound from ${cleanPhone} [state=${user.state}]: "${trimmedText.substring(0, 80)}"`, 'INFO');

  // ── Handle blocked users ─────────────────────────────────────────────────
  if (user.state === 'BLOCKED') {
    // Silent drop
    return;
  }

  // ── NEW user — start onboarding ──────────────────────────────────────────
  if (user.state === 'NEW') {
    await updateUser(cleanPhone, { state: 'ONBOARDING_NAME' });
    await sendMessage(jid, ONBOARDING_QUESTIONS[0].prompt);
    return;
  }

  // ── ONBOARDING: Collect Name ─────────────────────────────────────────────
  if (user.state === 'ONBOARDING_NAME') {
    let cleanName = trimmedText
      .replace(/^(my name is|i am|i'm|call me|myself|this is|mera naam)\s+/i, '')
      .slice(0, 80)
      .replace(/[^a-zA-Z0-9 _\-.']/g, '')
      .trim();

    const lower = cleanName.toLowerCase();
    const commonGreetings = ['hi', 'hy', 'hello', 'hey', 'hii', 'hiii', 'hola', 'namaste', 'start', 'help', 'yo', 'suno'];

    if (!cleanName || cleanName.length < 2 || commonGreetings.includes(lower)) {
      await sendMessage(jid, '🙂 Please tell me your name so I can personalize your assistant (e.g. "Yuvraj" or "Amit").');
      return;
    }
    await updateUser(cleanPhone, { name: cleanName, state: 'ONBOARDING_USE_CASE' });
    const useCasePrompt = ONBOARDING_QUESTIONS[1].prompt.replace('{name}', cleanName);
    await sendMessage(jid, useCasePrompt);
    return;
  }

  // ── ONBOARDING: Collect Use Case ─────────────────────────────────────────
  if (user.state === 'ONBOARDING_USE_CASE') {
    const choice = trimmedText.slice(0, 1);
    const useCase = USE_CASE_MAP[choice];
    if (!useCase) {
      await sendMessage(jid, '👆 Please reply with 1, 2, 3, or 4 to pick your use case.');
      return;
    }
    await updateUser(cleanPhone, { use_case: useCase, state: 'ONBOARDING_AUTH' });

    const authLink = generateAuthLink(cleanPhone);
    const authPrompt = ONBOARDING_QUESTIONS[2].prompt.replace('{auth_link}', authLink);
    await sendMessage(jid, authPrompt);
    return;
  }

  // ── ONBOARDING: Google Auth ──────────────────────────────────────────────
  if (user.state === 'ONBOARDING_AUTH') {
    const lower = trimmedText.toLowerCase();
    if (lower === 'skip' || lower === 'later' || lower === 'no') {
      await updateUser(cleanPhone, { state: 'ACTIVE' });
      await sendMessage(jid,
        `✅ *You're all set, ${user.name || 'there'}!*\n\nYou can connect Google later by typing *"connect google"*.\n\n🤖 ZORO is ready. Just text me anything — I can help with tasks, questions, scheduling, and more!\n\nType *"help"* anytime to see what I can do.`
      );
    } else {
      // User might have already authenticated via the link and come back
      // Check if token exists for this user
      const tokenRow = await query('SELECT id FROM google_tokens WHERE phone = ? LIMIT 1', [cleanPhone]).catch(() => []);
      if (tokenRow.length > 0) {
        await updateUser(cleanPhone, { state: 'ACTIVE', google_connected: 1 });
        await sendMessage(jid,
          `🎉 *Google connected successfully, ${user.name || 'there'}!*\n\n✅ Calendar & Gmail are now live.\n🤖 ZORO is ready — text me anything!\n\nType *"help"* to see what I can do.`
        );
      } else {
        const authLink = generateAuthLink(cleanPhone);
        await sendMessage(jid,
          `🔗 It looks like the Google connection isn't done yet. Please tap this link to connect:\n\n${authLink}\n\n_Or reply "skip" to continue without Google._`
        );
      }
    }
    return;
  }

  // ── ACTIVE user — handle special commands then route to FastAgent ────────
  if (user.state === 'ACTIVE') {
    const lower = trimmedText.toLowerCase();

    // Re-connect Google
    if (lower === 'connect google' || lower === 'link google' || lower === 'google connect') {
      const authLink = generateAuthLink(cleanPhone);
      await sendMessage(jid, `🔗 Tap below to connect your Google account:\n\n${authLink}`);
      return;
    }

    // Help command
    if (lower === 'help' || lower === '/help') {
      await sendMessage(jid,
        `🤖 *ZORO — What I can do:*\n\n📅 *Calendar* — "Schedule a meeting tomorrow at 3pm"\n📧 *Email* — "Draft an email to John about the project"\n⚡ *Skills* — Type *"skills"* to view and add modular agent skills\n✅ *Tasks* — "Remind me to call Dr. Sharma at 6pm"\n🔍 *Research* — Ask me anything\n📊 *Summarise* — "Summarise my emails from today"\n\n⚙️ Commands:\n• *skills* — View active skills & templates\n• *add skill: <Name> — <Prompt>* — Create custom skill\n• *connect google* — Link your Google account\n• *status* — Check your account status\n• *help* — Show this menu\n\n_Powered by ZORO AI_ ⚔️`
      );
      return;
    }

    // Skills hub command
    if (lower === 'skills' || lower === '/skills' || lower === 'my skills') {
      const skills = await listSkills(cleanPhone);
      let msg = `⚡ *ZORO Skills Hub*\n\nHere are your active agent skills:\n`;
      skills.forEach((s, i) => {
        msg += `\n${i + 1}. *${s.name}*\n   • Trigger: _${s.trigger_keywords || s.slug}_\n   • ${s.description || 'Specialized agent prompt'}\n`;
      });
      msg += `\n💡 *Add Your Own Skill:*\nReply with:\n*add skill: <Name> — <Instructions>*\n\n_Example:_\nadd skill: Diet Coach — You are a nutritionist. Analyze meal descriptions, estimate calories, and suggest healthier alternatives.`;
      await sendMessage(jid, msg);
      return;
    }

    // Add Skill command
    if (lower.startsWith('add skill:') || lower.startsWith('add skill :')) {
      const payload = trimmedText.replace(/^add skill\s*:\s*/i, '').trim();
      const delimiter = payload.includes('—') ? '—' : (payload.includes('-') ? '-' : ':');
      const parts = payload.split(delimiter);
      if (parts.length < 2) {
        await sendMessage(jid, `⚠️ *Format:* \`add skill: <Skill Name> — <AI Instructions>\`\n\n_Example:_\nadd skill: Diet Coach — You are a nutritionist. Analyze meal descriptions and calculate macros.`);
        return;
      }
      const skillName = parts[0].trim();
      const systemPrompt = parts.slice(1).join(delimiter).trim();
      const slug = skillName.toLowerCase().replace(/[^a-z0-9]/g, '_').slice(0, 32);

      await createSkill({
        name: skillName,
        slug: slug,
        user_phone: cleanPhone,
        description: `Custom skill created by user`,
        system_prompt: systemPrompt,
        trigger_keywords: skillName.toLowerCase()
      });

      // Sync with FastAgent backend
      try {
        const backendUrl = process.env.FASTAGENT_API_URL || 'http://localhost:8000';
        await fetch(`${backendUrl}/api/skills`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: cleanPhone,
            name: skillName,
            slug: slug,
            system_prompt: systemPrompt,
            trigger_keywords: skillName.toLowerCase()
          })
        });
      } catch (err) {
        // Backend offline or in-memory, MySQL still holds it
      }

      await sendMessage(jid, `🎉 *Skill Added Successfully!*\n\n🧩 *${skillName}* is now active.\nJust message me with your request or mention *${skillName}* to trigger it!`);
      return;
    }

    // Remove Skill command
    if (lower.startsWith('remove skill:') || lower.startsWith('delete skill:')) {
      const skillName = trimmedText.replace(/^(remove|delete)\s+skill\s*:\s*/i, '').trim().toLowerCase();
      const skills = await listSkills(cleanPhone);
      const target = skills.find(s => s.name.toLowerCase() === skillName || s.slug.toLowerCase() === skillName);
      if (target) {
        await deleteSkill(target.skill_id);
        await sendMessage(jid, `🗑️ Skill *${target.name}* has been removed.`);
      } else {
        await sendMessage(jid, `⚠️ Skill not found. Type *"skills"* to list your active skills.`);
      }
      return;
    }

    // Status command
    if (lower === 'status' || lower === '/status') {
      const googleStatus = user.google_connected ? '✅ Connected' : '❌ Not connected';
      const skills = await listSkills(cleanPhone);
      await sendMessage(jid,
        `📊 *Your ZORO Status:*\n\n👤 Name: ${user.name || 'Not set'}\n📱 Phone: +${cleanPhone}\n🎯 Use case: ${user.use_case || 'Not set'}\n🧩 Active Skills: ${skills.length}\n🔗 Google: ${googleStatus}\n✨ Account: Active\n\n_Type "skills" to manage skills or "help" for options._`
      );
      return;
    }

    // Route to FastAgent backend
    await sendMessage(jid, '⏳ _Thinking..._');

    const reply = await callFastAgentBackend(cleanPhone, trimmedText);

    if (reply) {
      await sendMessage(jid, reply);
    } else {
      // Fallback — basic Gemini-less reply
      await sendMessage(jid,
        `🤔 I'm having trouble reaching the ZORO brain right now. Please try again in a moment.\n\n_If this persists, type "status" to check your connection._`
      );
    }

    await logActivity('FASTAGENT_WA', `Reply sent to ${cleanPhone}`, 'INFO');
    return;
  }

  // Fallback for unknown state
  await updateUser(cleanPhone, { state: 'NEW' });
  await sendMessage(jid, '👋 Let\'s start fresh! ' + ONBOARDING_QUESTIONS[0].prompt);
}

function clearAuthDir() {
  const authDir = path.join(__dirname, '../../storage/auth_bot');
  try {
    if (fs.existsSync(authDir)) {
      const files = fs.readdirSync(authDir);
      for (const file of files) {
        fs.rmSync(path.join(authDir, file), { recursive: true, force: true });
      }
      console.log('[FastAgent Bot] Stale auth credentials cleared from storage/auth_bot');
    }
  } catch (err) {
    console.error('[FastAgent Bot] Error clearing auth_bot dir:', err.message);
  }
}

// ── BOT SESSION ───────────────────────────────────────────────────────────────
export async function startBotSession() {
  // If an existing socket is active, clean it up before re-creating
  if (botSock) {
    try {
      botSock.ev.removeAllListeners();
      botSock.end?.();
    } catch (e) {}
    botSock = null;
  }

  const authDir = path.join(__dirname, '../../storage/auth_bot');
  if (!fs.existsSync(authDir)) fs.mkdirSync(authDir, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const { version } = await fetchLatestBaileysVersion();

  const authLogger = pino({ level: 'silent' });
  botSock = makeWASocket({
    version,
    logger: authLogger,
    printQRInTerminal: true,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, authLogger)
    },
    browser: ['ZORO', 'Chrome', '120.0.0'],
    syncFullHistory: false,
    markOnlineOnConnect: true,
    getMessage: async (key) => {
      const msg = messageStore.get(key.id);
      return msg || undefined;
    }
  });

  botSock.ev.on('creds.update', saveCreds);

  botSock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      botQR = await QRCode.toDataURL(qr, { margin: 2, scale: 8 });
      botStatus = 'SCAN_QR';
      console.log('[FastAgent Bot] 📱 New QR code generated! Scan via Dashboard or Terminal.');
      emitStatus();
    }

    if (connection === 'open') {
      botQR = null;
      botStatus = 'CONNECTED';
      botPhoneNumber = botSock?.user?.id ? botSock.user.id.split('@')[0].split(':')[0] : null;
      emitStatus();
      await logActivity('FASTAGENT_WA', `FastAgent WhatsApp bot connected successfully on +${botPhoneNumber || 'unknown'}`, 'INFO');
      console.log(`[FastAgent Bot] WhatsApp connected on +${botPhoneNumber}. Ready to serve users.`);
    }

    if (connection === 'close') {
      if (isManualDisconnect) return;
      const statusCode = (lastDisconnect?.error)?.output?.statusCode;
      const isLoggedOut = statusCode === DisconnectReason.loggedOut || statusCode === 401 || statusCode === 403;

      botStatus = 'DISCONNECTED';
      emitStatus();

      if (isLoggedOut) {
        console.log('[FastAgent Bot] Session logged out or expired. Resetting credentials and generating a fresh QR code...');
        await logActivity('FASTAGENT_WA', 'Bot session expired or logged out. Resetting credentials for fresh QR pairing.', 'WARN');
        clearAuthDir();
        botQR = null;
        botPhoneNumber = null;
        botStatus = 'AWAITING_QR';
        emitStatus();
        setTimeout(() => {
          startBotSession().catch(err => console.error('[FastAgent Bot] Restart error:', err.message));
        }, 1200);
      } else {
        console.log(`[FastAgent Bot] Connection closed (${statusCode || 'unknown'}). Reconnecting in 5s...`);
        setTimeout(() => {
          startBotSession().catch(err => console.error('[FastAgent Bot] Reconnect error:', err.message));
        }, 5000);
      }
    }
  });

  // ── Handle incoming messages ──────────────────────────────────────────────
  botSock.ev.on('messages.upsert', async ({ messages, type }) => {
    for (const msg of messages) {
      if (msg.key?.id && msg.message) {
        saveMessageToStore(msg.key, msg.message);
      }

      // Ignore own messages
      if (!msg.message || msg.key.fromMe) continue;

      // Deduplicate messages across repeated events
      const msgId = msg.key.id;
      if (msgId) {
        if (processedMessageIds.has(msgId)) continue;
        processedMessageIds.add(msgId);
        if (processedMessageIds.size > 2000) {
          const first = processedMessageIds.values().next().value;
          processedMessageIds.delete(first);
        }
      }

      const rawJid = msg.key.remoteJid;
      if (!rawJid) continue;
      if (rawJid.endsWith('@g.us') || rawJid.endsWith('@broadcast') || rawJid.endsWith('@newsletter') || rawJid === 'status@broadcast') continue;

      // CRITICAL: Always reply to rawJid so the active Signal ratchet/LID decrypts immediately
      const replyJid = rawJid;
      let phone = '';

      if (rawJid.endsWith('@s.whatsapp.net')) {
        phone = rawJid.split('@')[0].split(':')[0];
      } else if (rawJid.endsWith('@lid')) {
        // Resolve internal LID to the user's real phone number for DB identification
        try {
          const pn = await botSock.signalRepository?.lidMapping?.getPNForLID(rawJid);
          if (pn && pn.includes('@s.whatsapp.net')) {
            phone = pn.split('@')[0].split(':')[0];
          }
        } catch {}

        if (!phone) {
          phone = rawJid.split('@')[0].split(':')[0];
        }
      } else if (msg.key.participant?.includes('@s.whatsapp.net')) {
        phone = msg.key.participant.split('@')[0].split(':')[0];
      }

      // Guard: strictly ignore invalid internal IDs or empty phone
      if (!phone || phone.length < 5) {
        continue;
      }

      // Extract text from various message types
      const text =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        msg.message.imageMessage?.caption ||
        msg.message.videoMessage?.caption ||
        msg.message.buttonsResponseMessage?.selectedDisplayText ||
        msg.message.listResponseMessage?.title ||
        '';

      if (!text.trim()) continue;

      // Handle message asynchronously so we don't block the event loop
      handleFastAgentMessage(replyJid, phone, text).catch(err => {
        console.error(`[FastAgent] Unhandled error for ${phone}:`, err.message);
      });
    }
  });
}

// ── Public Status / Control ──────────────────────────────────────────────────
export function getWhatsAppStatus() {
  return {
    bot: { status: botStatus, qr: botQR, number: getBotNumber() }
  };
}

export async function disconnectBotSession() {
  isManualDisconnect = true;
  try {
    if (botSock) {
      botSock.ev.removeAllListeners();
      await botSock.logout().catch(() => {});
      botSock.end?.();
      botSock = null;
    }
  } catch (err) {
    console.error('[Bot Disconnect Warning]:', err.message);
  }

  // Wipe stale auth credentials so a fresh QR is generated
  clearAuthDir();

  botStatus = 'AWAITING_QR';
  botQR = null;
  botPhoneNumber = null;
  emitStatus();
  isManualDisconnect = false;

  await logActivity('FASTAGENT_WA', 'Bot disconnected by admin. Generating fresh QR code.', 'INFO');
  console.log('[FastAgent Bot] Session wiped. Initializing fresh session for new QR scan...');

  setTimeout(() => {
    startBotSession().catch(err => console.error('[FastAgent Bot] Rescan start error:', err.message));
  }, 600);
}

export async function sendTestPing(targetJid) {
  if (!botSock || botStatus !== 'CONNECTED') {
    return { success: false, error: 'Bot not connected' };
  }
  try {
    await botSock.sendMessage(targetJid, { text: '🏓 *ZORO ping!* Bot is alive and connected.' });
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
}
