import express from 'express';
import http from 'http';
import { Server } from 'socket.io';
import cors from 'cors';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';

import { initDatabase, query, getSetting, setSetting, logActivity, getDbStatus, listSkills, createSkill, deleteSkill } from './src/database/db.js';
import { loginUser, validateSession, logoutSession, changeUserPassword } from './src/services/authService.js';
import {
  startBotSession,
  getWhatsAppStatus,
  setSocketIO,
  sendTestPing,
  disconnectBotSession
} from './src/whatsapp/baileysManager.js';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: '*' } });

setSocketIO(io);

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Helper to reliably detect subpath for reverse proxy (e.g. /directorbot)
function detectSubpath(req) {
  // 1. Explicit env var
  if (process.env.APP_BASE_PATH) {
    return process.env.APP_BASE_PATH.replace(/\/+$/, '');
  }

  // 2. X-Forwarded-Prefix header from reverse proxy
  if (req.headers['x-forwarded-prefix']) {
    return req.headers['x-forwarded-prefix'].replace(/\/+$/, '');
  }

  // 3. Request URL or original URL
  if (req.originalUrl && req.originalUrl.startsWith('/directorbot')) {
    return '/directorbot';
  }
  if (req.url && req.url.startsWith('/directorbot')) {
    return '/directorbot';
  }

  // 4. X-Original-URI header
  if (req.headers['x-original-uri'] && req.headers['x-original-uri'].startsWith('/directorbot')) {
    return '/directorbot';
  }

  // 5. Host matching ai.jecrcuniversity.edu.in
  const host = req.headers['x-forwarded-host'] || req.headers.host || '';
  if (host.includes('ai.jecrcuniversity.edu.in')) {
    return '/directorbot';
  }

  // 6. Referer header check
  if (req.headers.referer && req.headers.referer.includes('/directorbot')) {
    return '/directorbot';
  }

  // 7. Configured Google Redirect URI
  const googleUri = process.env.GOOGLE_REDIRECT_URI || '';
  if (googleUri.includes('/directorbot')) {
    return '/directorbot';
  }

  return '';
}

// Subpath & Reverse Proxy Compatibility Middleware
app.use((req, res, next) => {
  req.subpath = detectSubpath(req);

  if (req.url === '/directorbot') {
    return res.redirect('/directorbot/');
  }
  if (req.url.startsWith('/directorbot/')) {
    req.url = req.url.substring('/directorbot'.length);
    if (!req.url.startsWith('/')) req.url = '/' + req.url;
  }
  next();
});

// Cookie Parser Helper
function parseCookies(req) {
  const list = {};
  const cookieHeader = req.headers?.cookie;
  if (!cookieHeader) return list;
  cookieHeader.split(';').forEach(cookie => {
    let [name, ...rest] = cookie.split('=');
    name = name?.trim();
    if (!name) return;
    const value = rest.join('=').trim();
    list[name] = decodeURIComponent(value);
  });
  return list;
}

// Token Extractor
function extractToken(req) {
  const authHeader = req.headers['authorization'];
  if (authHeader && authHeader.startsWith('Bearer ')) {
    return authHeader.substring(7).trim();
  }
  if (req.headers['x-auth-token']) {
    return req.headers['x-auth-token'];
  }
  const cookies = parseCookies(req);
  if (cookies['auth_token']) {
    return cookies['auth_token'];
  }
  if (req.query && req.query.token) {
    return req.query.token;
  }
  return null;
}

// Login Page Route: If already authenticated, redirect to root dashboard (unless logging out)
app.get('/login.html', async (req, res) => {
  const subpath = req.subpath || detectSubpath(req);
  if (req.query.logout === 'true') {
    return res.sendFile(path.join(__dirname, 'src/public/login.html'));
  }
  const token = extractToken(req);
  if (token) {
    const user = await validateSession(token);
    if (user) {
      return res.redirect(`${subpath || ''}/`);
    }
  }
  res.sendFile(path.join(__dirname, 'src/public/login.html'));
});

// Protect Root Page: Unauthenticated users are redirected to /login.html with subpath
app.get(['/', '/index.html'], async (req, res) => {
  const subpath = req.subpath || detectSubpath(req);
  const token = extractToken(req);
  if (!token) {
    return res.redirect(`${subpath || ''}/login.html`);
  }
  const user = await validateSession(token);
  if (!user) {
    return res.redirect(`${subpath || ''}/login.html`);
  }
  res.sendFile(path.join(__dirname, 'src/public/index.html'));
});

// Static files (explicitly excluding auto-serving index.html so / is guarded)
app.use(express.static(path.join(__dirname, 'src/public'), { index: false }));
app.use('/storage', express.static(path.join(__dirname, 'storage')));

// Helper to get dashboard root URL for redirects
async function getDashboardRedirectUrl() {
  const redirectUri = (await getSetting('GOOGLE_REDIRECT_URI')) || process.env.GOOGLE_REDIRECT_URI || '';
  if (redirectUri.includes('/auth/google/callback')) {
    return redirectUri.replace(/\/auth\/google\/callback.*$/, '');
  }
  return '';
}

// --- Google OAuth2 Routes (Per-User, phone-keyed) ---
// The /auth/google?user=<base64phone> route initiates OAuth for a specific WhatsApp user.
app.get('/auth/google', async (req, res) => {
  try {
    const { google } = await import('googleapis');
    const clientId = (await getSetting('GOOGLE_CLIENT_ID')) || process.env.GOOGLE_CLIENT_ID;
    const clientSecret = (await getSetting('GOOGLE_CLIENT_SECRET')) || process.env.GOOGLE_CLIENT_SECRET;
    const redirectUri = process.env.GOOGLE_REDIRECT_URI || `http://localhost:${process.env.PORT || 5122}/auth/google/callback`;

    if (!clientId || !clientSecret) {
      return res.status(500).send('<h3>Google OAuth not configured.</h3><p>Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env</p>');
    }

    const oAuth2Client = new google.auth.OAuth2(clientId, clientSecret, redirectUri);
    const scopes = [
      'https://www.googleapis.com/auth/calendar',
      'https://www.googleapis.com/auth/gmail.modify',
      'https://www.googleapis.com/auth/userinfo.email',
      'https://www.googleapis.com/auth/userinfo.profile'
    ];

    // Preserve phone in state param so callback can link token back to user
    const userParam = req.query.user || '';
    const authUrl = oAuth2Client.generateAuthUrl({
      access_type: 'offline',
      prompt: 'consent',
      scope: scopes,
      state: userParam
    });

    res.redirect(authUrl);
  } catch (err) {
    res.status(500).send(`<h3>Google OAuth Error</h3><p>${err.message}</p>`);
  }
});

app.get('/auth/google/callback', async (req, res) => {
  const { code, error, state } = req.query;
  const baseUrl = process.env.APP_PUBLIC_URL || `http://localhost:${process.env.PORT || 5122}`;

  if (error) {
    return res.send(`<h3>Auth failed: ${error}</h3><p>You can close this window and try again on WhatsApp.</p>`);
  }
  if (!code) {
    return res.send('<h3>Missing authorization code.</h3>');
  }

  try {
    const { google } = await import('googleapis');
    const clientId = (await getSetting('GOOGLE_CLIENT_ID')) || process.env.GOOGLE_CLIENT_ID;
    const clientSecret = (await getSetting('GOOGLE_CLIENT_SECRET')) || process.env.GOOGLE_CLIENT_SECRET;
    const redirectUri = process.env.GOOGLE_REDIRECT_URI || `${baseUrl}/auth/google/callback`;

    const oAuth2Client = new google.auth.OAuth2(clientId, clientSecret, redirectUri);
    const { tokens } = await oAuth2Client.getToken(code);
    oAuth2Client.setCredentials(tokens);

    // Get user's Google email
    const oauth2 = google.oauth2({ version: 'v2', auth: oAuth2Client });
    const userInfo = await oauth2.userinfo.get();
    const googleEmail = userInfo.data.email || '';

    // Decode phone from state
    let phone = '';
    if (state) {
      try { phone = Buffer.from(state, 'base64url').toString('utf8'); } catch {}
    }

    // Save token keyed by phone (and email)
    await query(
      `INSERT INTO google_tokens (phone, email, refresh_token, access_token, expiry_date, scope)
       VALUES (?, ?, ?, ?, ?, ?)
       ON DUPLICATE KEY UPDATE
         email = VALUES(email),
         refresh_token = COALESCE(VALUES(refresh_token), refresh_token),
         access_token = VALUES(access_token),
         expiry_date = VALUES(expiry_date),
         scope = VALUES(scope),
         updated_at = CURRENT_TIMESTAMP`,
      [
        phone || null,
        googleEmail,
        tokens.refresh_token || null,
        tokens.access_token || null,
        tokens.expiry_date || null,
        (tokens.scope || '').substring(0, 500)
      ]
    );

    // Mark user as google-connected
    if (phone) {
      await query(
        'UPDATE fastagent_users SET google_connected = 1, google_email = ?, state = IF(state = \'ONBOARDING_AUTH\', \'ACTIVE\', state) WHERE phone = ?',
        [googleEmail, phone]
      );
    }

    await logActivity('GOOGLE_AUTH', `Google OAuth success for phone=${phone || 'unknown'} email=${googleEmail}`, 'INFO');

    // Pretty success page
    res.send(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>FastAgent — Connected!</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#0f0f1a;color:#fff;margin:0}
.card{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:40px;border-radius:20px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.5);max-width:400px}
.check{font-size:60px;margin-bottom:20px}.title{font-size:24px;font-weight:700;margin-bottom:10px}
.sub{color:#94a3b8;font-size:14px;margin-bottom:20px}.email{background:#1e293b;padding:10px 20px;border-radius:10px;font-family:monospace;font-size:13px;margin-bottom:24px}
.tip{color:#64748b;font-size:12px}</style></head>
<body><div class="card">
  <div class="check">✅</div>
  <div class="title">Google Connected!</div>
  <div class="sub">Your account is now linked to FastAgent</div>
  <div class="email">${googleEmail}</div>
  <div class="tip">You can close this window.<br/>Go back to WhatsApp to continue chatting! 🚀</div>
</div></body></html>`);
  } catch (err) {
    console.error('[Google OAuth Callback Error]:', err.message);
    res.send(`<h3>Auth failed</h3><p>${err.message}</p><p>Close this window and try again on WhatsApp.</p>`);
  }
});

// --- Auth API Endpoints ---
app.post('/api/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    const ip = req.ip || req.headers['x-forwarded-for'] || req.socket?.remoteAddress || '';
    const userAgent = req.headers['user-agent'] || '';

    const result = await loginUser(email, password, userAgent, ip);
    if (!result.success) {
      return res.status(401).json(result);
    }

    const isHttps = req.secure || req.headers['x-forwarded-proto'] === 'https';
    res.cookie('auth_token', result.token, {
      maxAge: 30 * 24 * 60 * 60 * 1000,
      path: '/',
      sameSite: 'lax',
      secure: isHttps
    });

    res.json(result);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.all(['/logout', '/directorbot/logout', '/api/auth/logout', '/directorbot/api/auth/logout'], async (req, res) => {
  const subpath = req.subpath || detectSubpath(req);
  try {
    const token = extractToken(req);
    if (token) {
      await logoutSession(token);
    }
  } catch (err) {}

  res.clearCookie('auth_token', { path: '/' });
  res.clearCookie('auth_token', { path: '/directorbot' });
  res.clearCookie('auth_token', { path: '/directorbot/' });
  res.setHeader('Set-Cookie', [
    'auth_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0',
    'auth_token=; Path=/directorbot; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0',
    'auth_token=; Path=/directorbot/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0'
  ]);

  if (req.headers.accept?.includes('application/json') && req.method === 'POST') {
    return res.json({ success: true, message: 'Logged out successfully' });
  }

  return res.redirect(`${subpath || ''}/login.html?logout=true`);
});

// Guard Middleware for all remaining /api/* endpoints
app.use('/api', async (req, res, next) => {
  if (req.path === '/auth/login') return next();

  const token = extractToken(req);
  if (!token) {
    return res.status(401).json({ success: false, error: 'Unauthorized: Authentication required.' });
  }

  const user = await validateSession(token);
  if (!user) {
    return res.status(401).json({ success: false, error: 'Session expired or invalid. Please log in again.' });
  }

  req.user = user;
  req.authToken = token;
  next();
});

// Authenticated user profile
app.get('/api/auth/me', (req, res) => {
  res.json({ success: true, user: req.user });
});

// Change Password endpoint
app.post('/api/auth/change-password', async (req, res) => {
  try {
    const { currentPassword, newPassword } = req.body;
    if (!req.user || !req.user.id) {
      return res.status(401).json({ success: false, error: 'Unauthorized' });
    }
    const result = await changeUserPassword(req.user.id, currentPassword, newPassword);
    if (!result.success) {
      return res.status(400).json(result);
    }
    res.json(result);
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// Disconnect Google Account (per user by phone)
app.post('/api/google/disconnect/:phone', async (req, res) => {
  try {
    const phone = req.params.phone.replace(/[^0-9]/g, '');
    await query('DELETE FROM google_tokens WHERE phone = ?', [phone]);
    await query('UPDATE fastagent_users SET google_connected = 0, google_email = NULL WHERE phone = ?', [phone]);
    await logActivity('GOOGLE_AUTH', `Google disconnected for phone=${phone}`, 'INFO');
    res.json({ success: true, message: 'Google account disconnected.' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/test/whatsapp-ping', async (req, res) => {
  try {
    const { phone } = req.body;
    if (!phone) return res.status(400).json({ success: false, error: 'phone is required' });
    const cleanPhone = phone.replace(/[^0-9]/g, '');
    const jid = cleanPhone.length === 10 ? `91${cleanPhone}@s.whatsapp.net` : `${cleanPhone}@s.whatsapp.net`;
    const result = await sendTestPing(jid);
    if (!result.success) return res.status(400).json(result);
    res.json({ success: true, message: `Test ping sent to ${cleanPhone}` });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// --- API Endpoints ---

// 1. Overall System Status
app.get('/api/status', async (req, res) => {
  try {
    const db = getDbStatus();
    const wa = getWhatsAppStatus();

    // Check backend health
    let backendOk = false;
    try {
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
      const resp = await fetch(`${backendUrl}/health`, { signal: AbortSignal.timeout(3000) });
      backendOk = resp.ok;
    } catch {}

    const userCount = await query('SELECT COUNT(*) as cnt FROM fastagent_users').then(r => r[0]?.cnt || 0).catch(() => 0);
    const activeCount = await query("SELECT COUNT(*) as cnt FROM fastagent_users WHERE state = 'ACTIVE'").then(r => r[0]?.cnt || 0).catch(() => 0);

    res.json({
      database: db,
      whatsapp: wa,
      backend: { url: process.env.BACKEND_URL || 'http://localhost:8000', healthy: backendOk },
      users: { total: userCount, active: activeCount }
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 2. Dashboard Quick Stats
app.get('/api/stats', async (req, res) => {
  try {
    const today = new Date().toISOString().split('T')[0];
    const [totalUsers] = await query('SELECT COUNT(*) as cnt FROM fastagent_users');
    const [activeUsers] = await query("SELECT COUNT(*) as cnt FROM fastagent_users WHERE state = 'ACTIVE'");
    const [newToday] = await query('SELECT COUNT(*) as cnt FROM fastagent_users WHERE DATE(created_at) = ?', [today]);
    const [googleConnected] = await query('SELECT COUNT(*) as cnt FROM fastagent_users WHERE google_connected = 1');
    res.json({
      totalUsers: totalUsers?.cnt || 0,
      activeUsers: activeUsers?.cnt || 0,
      newToday: newToday?.cnt || 0,
      googleConnected: googleConnected?.cnt || 0
    });
  } catch (err) {
    res.json({ totalUsers: 0, activeUsers: 0, newToday: 0, googleConnected: 0 });
  }
});

// 3. WhatsApp Bot Control
app.post('/api/whatsapp/disconnect', async (req, res) => {
  try {
    await disconnectBotSession();
    res.json({ success: true, message: 'Bot disconnected. Rescan QR from dashboard to reconnect.' });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 4. System Reset (Admin Only)
app.post('/api/system/reset', async (req, res) => {
  try {
    const { clearUsers, clearLogs, clearTokens, disconnectBot } = req.body;
    const clearedItems = [];
    if (clearLogs) { await query('TRUNCATE TABLE activity_logs'); clearedItems.push('Activity logs'); }
    if (clearTokens) { await query('TRUNCATE TABLE google_tokens'); clearedItems.push('Google tokens'); }
    if (clearUsers) { await query('TRUNCATE TABLE fastagent_users'); clearedItems.push('All users'); }
    if (disconnectBot) { await disconnectBotSession(); clearedItems.push('Bot WhatsApp session'); }
    await logActivity('SYSTEM_RESET', `Reset: ${clearedItems.join(', ')}`, 'WARN');
    res.json({ success: true, message: clearedItems.join(', ') || 'Nothing selected' });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});



// 5. Skills Management
app.get('/api/skills', async (req, res) => {
  try {
    const { user_phone } = req.query;
    const skills = await listSkills(user_phone || null);
    res.json(skills);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/skills', async (req, res) => {
  try {
    const { name, system_prompt, description, trigger_keywords, webhook_url, user_phone } = req.body;
    if (!name || !system_prompt) {
      return res.status(400).json({ error: 'Name and system_prompt are required' });
    }
    const result = await createSkill({
      name,
      system_prompt,
      description,
      trigger_keywords,
      webhook_url,
      user_phone: user_phone || 'GLOBAL'
    });
    if (result.success) {
      res.status(201).json(result);
    } else {
      res.status(500).json(result);
    }
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete('/api/skills/:skill_id', async (req, res) => {
  try {
    const { skill_id } = req.params;
    const result = await deleteSkill(skill_id);
    if (result.success) {
      res.json({ success: true, message: `Skill ${skill_id} deleted` });
    } else {
      res.status(404).json(result);
    }
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 8. Settings Management
app.get('/api/settings', async (req, res) => {
  try {
    const keys = [
      'GOOGLE_CLIENT_ID',
      'GOOGLE_CLIENT_SECRET',
      'BACKEND_URL'
    ];

    const settings = {};
    for (const k of keys) {
      settings[k] = (await getSetting(k)) || process.env[k] || '';
    }

    // Mask sensitive keys for security in UI
    const masked = { ...settings };
    if (masked.GOOGLE_CLIENT_SECRET) masked.GOOGLE_CLIENT_SECRET = '••••••••••••';

    res.json({ settings: masked, rawConfigured: {
      hasGoogleId: !!settings.GOOGLE_CLIENT_ID,
      hasGoogleSecret: !!settings.GOOGLE_CLIENT_SECRET,
      hasBackend: !!settings.BACKEND_URL
    }});
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/settings', async (req, res) => {
  try {
    const allowed = [
      'GOOGLE_CLIENT_ID',
      'GOOGLE_CLIENT_SECRET',
      'BACKEND_URL'
    ];

    for (const key of allowed) {
      if (req.body[key] !== undefined && req.body[key] !== null && !String(req.body[key]).includes('••••')) {
        await setSetting(key, req.body[key]);
      }
    }

    await logActivity('SETTINGS', 'System settings updated via Web Dashboard', 'INFO');
    res.json({ success: true, message: 'Settings saved successfully' });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// --- FastAgent Users API ---
app.get('/api/users', async (req, res) => {
  try {
    const users = await query('SELECT id, phone, name, use_case, state, google_connected, google_email, message_count, last_seen, created_at FROM fastagent_users ORDER BY id DESC LIMIT 100');
    res.json(users);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/users/:phone/block', async (req, res) => {
  try {
    await query("UPDATE fastagent_users SET state = 'BLOCKED' WHERE phone = ?", [req.params.phone]);
    await logActivity('ADMIN', `User ${req.params.phone} blocked`, 'WARN');
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/users/:phone/unblock', async (req, res) => {
  try {
    await query("UPDATE fastagent_users SET state = 'ACTIVE' WHERE phone = ?", [req.params.phone]);
    await logActivity('ADMIN', `User ${req.params.phone} unblocked`, 'INFO');
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 9. Activity Logs Feed
app.get('/api/logs', async (req, res) => {
  try {
    const logs = await query('SELECT * FROM activity_logs ORDER BY id DESC LIMIT 40');
    res.json(logs);
  } catch (err) {
    res.json([]);
  }
});

// Diagnostic chat search endpoint
app.get('/api/debug/search-chats', async (req, res) => {
  const q = req.query.q || '';
  if (!q) return res.json({ count: 0, query: '', sample: [] });
  try {
    const rows = await query(
      `SELECT id, chat_jid, sender_name, sender_phone, message_text, timestamp, is_from_me 
       FROM whatsapp_chats 
       WHERE sender_name LIKE ? OR sender_phone LIKE ? OR chat_jid LIKE ? OR message_text LIKE ? 
       ORDER BY id DESC LIMIT 50`,
      [`%${q}%`, `%${q}%`, `%${q}%`, `%${q}%`]
    );
    res.json({ count: rows.length, query: q, sample: rows });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// --- Server Startup ---
const PORT = process.env.PORT || 5122;

async function bootstrap() {
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  console.log('   🤖  FastAgent WhatsApp Bot  —  Starting up   ');
  console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

  // 1. Init Database (auto-creates all tables)
  const dbOk = await initDatabase();
  if (!dbOk) {
    console.error('[ERROR] Database connection failed. Check MySQL config in .env');
    process.exit(1);
  }

  // 2. Start WhatsApp Bot Session
  console.log('[WhatsApp] Starting FastAgent bot session...');
  startBotSession().catch(err => console.error('[Bot WA Error]:', err.message));

  // 3. Start Web Server
  server.listen(PORT, () => {
    const baseUrl = process.env.APP_PUBLIC_URL || `http://localhost:${PORT}`;
    console.log(`[Server] Admin Dashboard → ${baseUrl}`);
    console.log(`[Server] Google OAuth URI → ${baseUrl}/auth/google/callback`);
    console.log(`[Server] Backend URL     → ${process.env.BACKEND_URL || 'http://localhost:8000'}`);
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
  });
}

bootstrap();
