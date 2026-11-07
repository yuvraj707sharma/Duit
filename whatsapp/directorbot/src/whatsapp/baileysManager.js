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
const blockedNotifyCache = new Map();
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
  { field: 'name',     prompt: 'Welcome to *DUIT*! I am your personal AI assistant.\n\nTo get started, what is your name?' },
  { field: 'use_case', prompt: 'Nice to meet you, {name}!\n\nHow do you plan to use DUIT? Pick a number:\n\n1. Personal productivity (calendar, emails, reminders)\n2. Business & work tasks\n3. Research & learning\n4. Just exploring\n\nReply with 1, 2, 3, or 4.' },
  { field: 'google_auth', prompt: 'Almost done! To unlock your Google Calendar & Gmail superpowers, tap the link below and sign in with Google:\n\n{auth_link}\n\n_(You can also skip this and use text-only features for now - reply "skip")_' }
];

const USE_CASE_MAP = { '1': 'Personal productivity', '2': 'Business & work', '3': 'Research & learning', '4': 'Exploring' };

// ── Backend API Call ─────────────────────────────────────────────────────────
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const GATEWAY_SHARED_SECRET = process.env.GATEWAY_SHARED_SECRET || 'duit_secret_wa_prod_2026';

async function callFastAgentBackend(phoneNumber, message) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (GATEWAY_SHARED_SECRET) {
      headers['x-gateway-secret'] = GATEWAY_SHARED_SECRET;
    }

    const resp = await fetch(`${BACKEND_URL}/api/webhooks/whatsapp`, {
      method: 'POST',
      headers,
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

// In-memory fallback for user states and chat transcripts when running in cloud mode without MySQL
const inMemoryUsers = new Map();
const inMemoryChats = [];

// ── User DB Helpers ──────────────────────────────────────────────────────────
async function getUser(phone) {
  try {
    const rows = await query('SELECT * FROM fastagent_users WHERE phone = ?', [phone]);
    if (rows && rows.length > 0) return rows[0];
  } catch {}
  return inMemoryUsers.get(phone) || null;
}

async function createUser(phone) {
  const newUser = { phone, state: 'ACTIVE', name: '', use_case: '', google_connected: 0 };
  inMemoryUsers.set(phone, newUser);
  try {
    await query(
      `INSERT INTO fastagent_users (phone, state) VALUES (?, 'ACTIVE')
       ON DUPLICATE KEY UPDATE state = state`,
      [phone]
    );
    const rows = await query('SELECT * FROM fastagent_users WHERE phone = ?', [phone]);
    if (rows && rows.length > 0) return rows[0];
  } catch (err) {}
  return newUser;
}

async function updateUser(phone, fields) {
  const existing = inMemoryUsers.get(phone) || { phone, state: 'ACTIVE' };
  inMemoryUsers.set(phone, { ...existing, ...fields });
  try {
    const setClauses = Object.keys(fields).map(k => `\`${k}\` = ?`).join(', ');
    const values = [...Object.values(fields), phone];
    await query(`UPDATE fastagent_users SET ${setClauses} WHERE phone = ?`, values);
  } catch (err) {}
}

export function getAppPublicUrl() {
  if (process.env.APP_PUBLIC_URL && !process.env.APP_PUBLIC_URL.includes('localhost')) {
    return process.env.APP_PUBLIC_URL.replace(/\/+$/, '');
  }
  if (process.env.RENDER_EXTERNAL_URL) {
    return process.env.RENDER_EXTERNAL_URL.replace(/\/+$/, '');
  }
  return 'https://duit-whatsapp.onrender.com';
}

// ── Cloud Session Persistence (Survives container rebuilds on Render) ─────────
async function restoreSessionFromCloud(authDir) {
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (GATEWAY_SHARED_SECRET) {
      headers['x-gateway-secret'] = GATEWAY_SHARED_SECRET;
    }
    const resp = await fetch(`${BACKEND_URL}/api/webhooks/session-state/auth_bot`, { headers });
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.files && Object.keys(data.files).length > 0) {
      console.log(`[Baileys Cloud Sync] Restoring ${Object.keys(data.files).length} session files from cloud storage...`);
      for (const [fname, content] of Object.entries(data.files)) {
        const filePath = path.join(authDir, fname);
        fs.writeFileSync(filePath, content, 'utf8');
      }
      console.log('[Baileys Cloud Sync] Session files restored successfully.');
    }
  } catch (err) {
    console.warn('[Baileys Cloud Sync] Could not restore session from cloud:', err.message);
  }
}

let syncTimeout = null;
export function triggerSessionSyncToCloud(authDir) {
  if (syncTimeout) clearTimeout(syncTimeout);
  syncTimeout = setTimeout(async () => {
    try {
      if (!fs.existsSync(authDir)) return;
      const files = fs.readdirSync(authDir);
      const filesMap = {};
      for (const file of files) {
        if (file.endsWith('.json')) {
          const filePath = path.join(authDir, file);
          try {
            filesMap[file] = fs.readFileSync(filePath, 'utf8');
          } catch {}
        }
      }
      if (Object.keys(filesMap).length === 0) return;

      const headers = { 'Content-Type': 'application/json' };
      if (GATEWAY_SHARED_SECRET) {
        headers['x-gateway-secret'] = GATEWAY_SHARED_SECRET;
      }
      await fetch(`${BACKEND_URL}/api/webhooks/session-state`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          session_id: 'auth_bot',
          files: filesMap
        })
      });
      console.log(`[Baileys Cloud Sync] Synced ${Object.keys(filesMap).length} session files to cloud database.`);
    } catch (err) {
      console.warn('[Baileys Cloud Sync] Session sync error:', err.message);
    }
  }, 2000);
}

// ── Generate Google OAuth Onboarding Link ────────────────────────────────────
function generateAuthLink(phone) {
  const baseUrl = getAppPublicUrl();
  const encoded = Buffer.from(phone).toString('base64url');
  return `${baseUrl}/auth/google?user=${encoded}`;
}

function stripEmojis(str) {
  if (!str || typeof str !== 'string') return str;
  return str
    .replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{2300}-\u{23FF}\u{2B50}\u{FE0F}\u{200D}]/gu, '')
    .replace(/[✅❌📅✉️🤔💡🎉⚠️🗑️📊✨⚔️📍⏰📌🔗🧩⚡]/g, '')
    .replace(/  +/g, ' ')
    .trim();
}

// ── Send WhatsApp Message ────────────────────────────────────────────────────
async function sendMessage(jid, text) {
  try {
    if (!botSock) throw new Error('Bot socket not connected');
    const cleanedText = stripEmojis(text);
    const sent = await botSock.sendMessage(jid, { text: cleanedText });
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
    const now = Date.now();
    const lastNotified = blockedNotifyCache.get(cleanPhone) || 0;
    if (now - lastNotified > 30 * 60 * 1000) {
      blockedNotifyCache.set(cleanPhone, now);
      const blockedMsg = (
        `*Account Notice*\n\n` +
        `Your DUIT access has been restricted by the administrator.\n` +
        `Timestamp: ${new Date().toUTCString()}\n` +
        `Reason: Administrative policy restriction\n\n` +
        `To request an account review or appeal this hold, please reply with *APPEAL* and your request details.`
      );
      await sendMessage(jid, blockedMsg);
    }
    return;
  }

  // ── NEW user - start onboarding ──────────────────────────────────────────
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
      await sendMessage(jid, ' Please tell me your name so I can personalize your assistant (e.g. "Yuvraj" or "Amit").');
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
      await sendMessage(jid, ' Please reply with 1, 2, 3, or 4 to pick your use case.');
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
        `*You are all set, ${user.name || 'there'}!*\n\nYou can connect Google later by typing *"connect google"*.\n\nDUIT is ready. Just text me anything - I can help with tasks, questions, scheduling, and more!\n\nType *"help"* anytime to see what I can do.`
      );
    } else {
      // User might have already authenticated via the link and come back
      // Check if token exists for this user
      const tokenRow = await query('SELECT id FROM google_tokens WHERE phone = ? LIMIT 1', [cleanPhone]).catch(() => []);
      if (tokenRow.length > 0) {
        await updateUser(cleanPhone, { state: 'ACTIVE', google_connected: 1 });
        await sendMessage(jid,
          `*Google connected successfully, ${user.name || 'there'}!*\n\nCalendar & Gmail are now live.\nDUIT is ready - text me anything!\n\nType *"help"* to see what I can do.`
        );
      } else {
        const authLink = generateAuthLink(cleanPhone);
        await sendMessage(jid,
          `It looks like the Google connection is not done yet. Please tap this link to connect:\n\n${authLink}\n\n_Or reply "skip" to continue without Google._`
        );
      }
    }
    return;
  }

  // ── ACTIVE user - handle special commands then route to FastAgent ────────
  if (user.state === 'ACTIVE') {
    const lower = trimmedText.toLowerCase();

    // Re-connect Google: Only trigger on explicit commands, never conversational sentences
    const isGoogleConnect =
      /^(connect|link|login|reconnect)\s+(my\s+)?google(\s+account|\s+calendar|\s+services)?$/i.test(trimmedText) ||
      /^google\s+(connect|link|login)$/i.test(trimmedText) ||
      lower === 'connect google' ||
      lower === 'link google' ||
      lower === 'google';

    if (isGoogleConnect) {
      const authLink = generateAuthLink(cleanPhone);
      await sendMessage(jid, `*Link your Google Account with DUIT:*\n\nTap below to connect your Google Calendar & Gmail:\n\n${authLink}\n\n_Once connected, you can schedule meetings, check calendar, and manage emails live!_`);
      return;
    }

    // Help command
    if (lower === 'help' || lower === '/help') {
      await sendMessage(jid,
        `*DUIT - What I can do:*\n\n- *Calendar* - "Schedule a meeting tomorrow at 3pm"\n- *Email* - "Draft an email to John about the project"\n- *Skills* - Type *"skills"* to view and add modular agent skills\n- *Tasks* - "Remind me to call Dr. Sharma at 6pm"\n- *Research* - Ask me anything\n- *Summarise* - "Summarise my emails from today"\n\nCommands:\n- *skills* - View active skills & templates\n- *add skill: <Name> - <Prompt>* - Create custom skill\n- *connect google* - Link your Google account\n- *status* - Check your account status\n- *help* - Show this menu\n\n_Powered by DUIT AI_`
      );
      return;
    }

    // Skills hub command
    if (lower === 'skills' || lower === '/skills' || lower === 'my skills') {
      const skills = await listSkills(cleanPhone);
      let msg = `*DUIT Skills Hub*\n\nHere are your active agent skills:\n`;
      skills.forEach((s, i) => {
        msg += `\n${i + 1}. *${s.name}*\n   - Trigger: _${s.trigger_keywords || s.slug}_\n   - ${s.description || 'Specialized agent prompt'}\n`;
      });
      msg += `\n*Add Your Own Skill:*\nReply with:\n*add skill: <Name> - <Instructions>*\n\n_Example:_\nadd skill: Diet Coach - You are a nutritionist. Analyze meal descriptions, estimate calories, and suggest healthier alternatives.`;
      await sendMessage(jid, msg);
      return;
    }

    // Add Skill command
    if (lower.startsWith('add skill:') || lower.startsWith('add skill :')) {
      const payload = trimmedText.replace(/^add skill\s*:\s*/i, '').trim();
      const delimiter = payload.includes('-') ? '-' : (payload.includes('-') ? '-' : ':');
      const parts = payload.split(delimiter);
      if (parts.length < 2) {
        await sendMessage(jid, `*Format:* \`add skill: <Skill Name> - <AI Instructions>\`\n\n_Example:_\nadd skill: Diet Coach - You are a nutritionist. Analyze meal descriptions and calculate macros.`);
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

      await sendMessage(jid, `*Skill Added Successfully!*\n\n*${skillName}* is now active.\nJust message me with your request or mention *${skillName}* to trigger it!`);
      return;
    }

    // Remove Skill command
    if (lower.startsWith('remove skill:') || lower.startsWith('delete skill:')) {
      const skillName = trimmedText.replace(/^(remove|delete)\s+skill\s*:\s*/i, '').trim().toLowerCase();
      const skills = await listSkills(cleanPhone);
      const target = skills.find(s => s.name.toLowerCase() === skillName || s.slug.toLowerCase() === skillName);
      if (target) {
        await deleteSkill(target.skill_id);
        await sendMessage(jid, `Skill *${target.name}* has been removed.`);
      } else {
        await sendMessage(jid, `Skill not found. Type *"skills"* to list your active skills.`);
      }
      return;
    }

    // Status command
    if (lower === 'status' || lower === '/status') {
      const googleStatus = user.google_connected ? 'Connected' : 'Not connected';
      const skills = await listSkills(cleanPhone);
      await sendMessage(jid,
        `*Your DUIT Status:*\n\nName: ${user.name || 'Not set'}\nPhone: +${cleanPhone}\nUse case: ${user.use_case || 'Not set'}\nActive Skills: ${skills.length}\nGoogle: ${googleStatus}\nAccount: Active\n\n_Type "skills" to manage skills or "help" for options._`
      );
      return;
    }

    // WhatsApp Phone Pairing Code command
    if (lower.startsWith('pair ') || lower.startsWith('pair phone ') || lower.startsWith('link phone ') || lower === 'pair' || lower === 'link') {
      const matchPhone = trimmedText.match(/\+?[0-9]{10,15}/);
      const targetPhone = matchPhone ? matchPhone[0].replace(/[^0-9]/g, '') : cleanPhone;
      try {
        const pCode = await requestBotPairingCode(targetPhone);
        await sendMessage(jid, `*WhatsApp Pairing Code:*\n${pCode}\n\nTo link this phone:
1. Open WhatsApp on your phone
2. Tap *Settings* (or three dots) > *Linked Devices*
3. Tap *Link a Device*
4. Tap *Link with phone number instead* at the bottom
5. Enter this 8-character code: *${pCode}*
`);
      } catch (pErr) {
        await sendMessage(jid, `Could not generate pairing code: ${pErr.message}`);
      }
      return;
    }

    // WhatsApp Chats Reader & Structured Search Handler (supports English, Hinglish, and Hindi queries)
    const isChatQuery =
      /whatsapp (chats?|messages?)|text(ed)? me|recent (whatsapp )?chats?|read (my )?(whatsapp )?chats?|summarize (my )?(whatsapp )?chats?|check (my )?(whatsapp )?messages?|last \d+ (chats?|messages?)|summary of (my )?(last )?\d* ?(chats?|messages?)|(chats?|messages?) summary/i.test(trimmedText) ||
      /\b(ne kya (bola|bheja|kaha)|ka message|ke (message|messages|chat|chats)|se (baat|message)|(summary|summarize).*(message|messages|chat|chats)|(message|messages|chat|chats).*summary)\b/i.test(trimmedText) ||
      /\b(show|find|search|get|read)\s+(me\s+)?(all\s+)?(messages?|chats?|texts?)\s+(from|of|by)\s+/i.test(trimmedText) ||
      /\bwhat did\s+([a-zA-Z0-9_\-]+)\s+(say|send|text|write)\b/i.test(trimmedText) ||
      /\bsummary of\s+([a-zA-Z0-9_\-]+)\s+messages?\b/i.test(trimmedText);

    if (isChatQuery) {
      let contactFilter = '';
      const cMatch =
        trimmedText.match(/(?:from|by|of)\s+([a-zA-Z0-9_\-\.]+)/i) ||
        trimmedText.match(/([a-zA-Z0-9_\-\.]+)\s+(?:ne kya|ka message|ke chats?|ke messages?|ko kya)/i) ||
        trimmedText.match(/what did\s+([a-zA-Z0-9_\-]+)/i) ||
        trimmedText.match(/summary of\s+([a-zA-Z0-9_\-]+)\s+messages?/i);

      if (cMatch) {
        const candidate = cMatch[1].trim();
        const stopWords = ['my', 'the', 'recent', 'last', 'these', 'all', 'yesterday', 'today', 'whatsapp', 'chat', 'chats', 'message', 'messages'];
        if (!stopWords.includes(candidate.toLowerCase())) {
          contactFilter = candidate;
        }
      }

      let limitMatch = trimmedText.match(/\blast\s+(\d+)\b/i) || trimmedText.match(/(\d+)\s+(?:messages?|chats?)/i);
      let queryLimit = limitMatch ? Math.min(Math.max(parseInt(limitMatch[1], 10), 1), 30) : 15;

      let chatRows = [];
      try {
        if (contactFilter) {
          chatRows = await query(
            `SELECT sender_name, sender_phone, message_text, timestamp 
             FROM whatsapp_chats 
             WHERE (sender_phone = ? OR chat_jid LIKE ?) AND (sender_name LIKE ? OR sender_phone LIKE ?) AND is_from_me = 0
             ORDER BY timestamp DESC LIMIT ?`,
            [cleanPhone, `%${cleanPhone}%`, `%${contactFilter}%`, `%${contactFilter}%`, queryLimit]
          );
        } else {
          chatRows = await query(
            `SELECT sender_name, sender_phone, message_text, timestamp 
             FROM whatsapp_chats 
             WHERE (sender_phone = ? OR chat_jid LIKE ?) AND is_from_me = 0
             ORDER BY timestamp DESC LIMIT ?`,
            [cleanPhone, `%${cleanPhone}%`, queryLimit]
          );
        }
      } catch (dbErr) {
        console.error('[DB] Chat query error:', dbErr.message);
      }

      if (!chatRows || chatRows.length === 0) {
        if (contactFilter) {
          chatRows = inMemoryChats.filter(c => (c.owner_phone === cleanPhone || c.sender_phone === cleanPhone) && !c.is_from_me && ((c.sender_name && c.sender_name.toLowerCase().includes(contactFilter.toLowerCase())) || c.sender_phone.includes(contactFilter))).slice(0, queryLimit);
        } else {
          chatRows = inMemoryChats.filter(c => (c.owner_phone === cleanPhone || c.sender_phone === cleanPhone) && !c.is_from_me).slice(0, queryLimit);
        }
      }

      if (!chatRows || chatRows.length === 0) {
        await sendMessage(jid,
          contactFilter
            ? `I searched your archived WhatsApp history for "*${contactFilter}*". No matching messages were found.\n\n_Note: DUIT securely records incoming messages received while your WhatsApp bot is active._`
            : `I searched your archived WhatsApp history. No recorded messages were found from other contacts yet.\n\n_Note: DUIT securely records incoming messages received while your WhatsApp bot is active._`
        );
        return;
      }

      // Prepare formatted transcript for Meta AI summarization
      let transcriptText = '';
      chatRows.forEach((row, idx) => {
        const timeStr = new Date(Number(row.timestamp)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const dateStr = new Date(Number(row.timestamp)).toLocaleDateString();
        transcriptText += `${idx + 1}. [${dateStr} ${timeStr}] From ${row.sender_name || row.sender_phone}: "${row.message_text}"\n`;
      });

      // Query FastAgent backend to summarize the chat transcript via Meta AI
      let summaryReply = '';
      try {
        const sumPrompt = `The user asked: "${trimmedText}".
Here are the actual archived WhatsApp messages found${contactFilter ? ` for contact "${contactFilter}"` : ''} (${chatRows.length} message(s)):

${transcriptText}

Please summarize these messages clearly and concisely for an executive. Highlight key action items, urgent inquiries, and quotes requested. Strictly zero emojis.`;
        summaryReply = await callFastAgentBackend(cleanPhone, sumPrompt);
      } catch (sumErr) {
        console.error('[Summary AI Error]:', sumErr.message);
      }

      if (summaryReply && !summaryReply.toLowerCase().includes('google account not connected') && !summaryReply.toLowerCase().includes('connect google')) {
        let sourceList = chatRows.slice(0, 4).map(r => {
          const d = new Date(Number(r.timestamp));
          return `- ${r.sender_name || r.sender_phone} (${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})`;
        }).join('\n');
        await sendMessage(jid, `*WhatsApp Summary (${chatRows.length} message(s)${contactFilter ? ` for "${contactFilter}"` : ''}):*\n\n${summaryReply}\n\n*Verified Sources:*\n${sourceList}`);
      } else {
        let replyMsg = `*Recent WhatsApp Communications (${chatRows.length} message(s)${contactFilter ? ` for "${contactFilter}"` : ''}):*\n\n`;
        chatRows.forEach((row, idx) => {
          const timeStr = new Date(Number(row.timestamp)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const dateStr = new Date(Number(row.timestamp)).toLocaleDateString();
          replyMsg += `${idx + 1}. *${row.sender_name || row.sender_phone}* (${dateStr} ${timeStr}):\n   "${row.message_text}"\n\n`;
        });
        await sendMessage(jid, replyMsg.trim());
      }
      return;
    }

    }

    // Route directly to FastAgent backend without intermediate thinking message
    const reply = await callFastAgentBackend(cleanPhone, trimmedText);

    if (reply) {
      await sendMessage(jid, reply);
    } else {
      // Fallback
      await sendMessage(jid,
        `I am having trouble reaching the DUIT brain right now. Please try again in a moment.\n\n_If this persists, type "status" to check your connection._`
      );
    }

    await logActivity('FASTAGENT_WA', `Reply sent to ${cleanPhone}`, 'INFO');
    return;
  }

  // Fallback for unknown state
  await updateUser(cleanPhone, { state: 'NEW' });
  await sendMessage(jid, ' Let\'s start fresh! ' + ONBOARDING_QUESTIONS[0].prompt);
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

  // Restore existing session credentials from cloud PostgreSQL before starting Baileys
  await restoreSessionFromCloud(authDir);

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
    browser: ['DUIT', 'Chrome', '120.0.0'],
    syncFullHistory: false,
    markOnlineOnConnect: true,
    getMessage: async (key) => {
      const msg = messageStore.get(key.id);
      return msg || undefined;
    }
  });

  botSock.ev.on('creds.update', async () => {
    await saveCreds();
    triggerSessionSyncToCloud(authDir);
  });

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
      triggerSessionSyncToCloud(authDir);
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

      // Archive incoming message in memory and MySQL
      const senderName = msg.pushName || (msg.key.fromMe ? 'Me' : phone);
      const isFromMe = msg.key.fromMe ? 1 : 0;
      const ts = msg.messageTimestamp ? Number(msg.messageTimestamp) * 1000 : Date.now();
      const uniqueMsgId = msgId || `msg_${Date.now()}_${Math.random()}`;

      inMemoryChats.unshift({
        owner_phone: phone,
        msg_id: uniqueMsgId,
        sender_name: senderName,
        sender_phone: phone,
        message_text: text.trim(),
        timestamp: ts,
        is_from_me: isFromMe
      });
      if (inMemoryChats.length > 200) inMemoryChats.pop();

      query(
        `INSERT INTO whatsapp_chats (msg_id, chat_jid, sender_name, sender_phone, message_text, timestamp, is_from_me)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE message_text = VALUES(message_text), timestamp = VALUES(timestamp)`,
        [uniqueMsgId, rawJid, senderName, phone, text.trim(), ts, isFromMe]
      ).catch(err => console.error('[DB] Archive chat error:', err.message));

      query(
        `INSERT INTO whatsapp_contacts (jid, phone, name, notify)
         VALUES (?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE name = COALESCE(VALUES(name), name), notify = COALESCE(VALUES(notify), notify), updated_at = CURRENT_TIMESTAMP`,
        [rawJid, phone, senderName, senderName]
      ).catch(err => console.error('[DB] Archive contact error:', err.message));

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

export async function requestBotPairingCode(phoneNumber) {
  if (!botSock) {
    throw new Error('WhatsApp gateway is not running. Start the session first.');
  }
  const cleanPhone = String(phoneNumber).replace(/[^0-9]/g, '');
  if (!cleanPhone || cleanPhone.length < 10) {
    throw new Error('Please provide a valid phone number with country code (e.g. 919876543210).');
  }
  const code = await botSock.requestPairingCode(cleanPhone);
  return code;
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
    await botSock.sendMessage(targetJid, { text: '🏓 *DUIT ping!* Bot is alive and connected.' });
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
}
