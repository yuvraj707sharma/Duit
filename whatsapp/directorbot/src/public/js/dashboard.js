// Subpath detection for reverse proxy
let basePath = window.location.pathname.replace(/\/+$/, '');
if (basePath.endsWith('.html') || basePath.includes('.htm')) {
  basePath = basePath.substring(0, basePath.lastIndexOf('/'));
}
if (basePath === '/' || !basePath) {
  basePath = '';
}

function resolveUrl(url) {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  const clean = url.startsWith('/') ? url : `/${url}`;
  return `${basePath}${clean}`;
}

// Auto-prefix relative API calls, ensure cookie credentials, handle 401
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  if (typeof url === 'string' && url.startsWith('/api/')) {
    url = resolveUrl(url);
  }

  // Use HttpOnly secure cookie for session auth (never read raw bearer from localStorage)
  options.credentials = options.credentials || 'same-origin';

  return originalFetch.call(this, url, options).then(res => {
    if (res.status === 401 && typeof url === 'string' && !url.includes('/api/auth/login')) {
      window.location.replace(resolveUrl('/login.html'));
    }
    return res;
  });
};

// Socket.io Connection
const socket = io({
  path: (basePath ? `${basePath}/socket.io` : '/socket.io')
});

// Toast notification helper
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.style.cssText = `
    background: #1e293b; color: #f8fafc; border: 1px solid #334155;
    padding: 12px 18px; border-radius: 10px; margin-top: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.5); font-size: 13px;
    animation: fadeIn 0.2s ease-in-out;
  `;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Global Instant Logout Handler
window.executeLogout = function(e) {
  if (e) {
    try { e.preventDefault(); e.stopPropagation(); } catch (err) {}
  }
  try {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_user');
    sessionStorage.clear();
  } catch (err) {}

  document.cookie = "auth_token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
  window.location.href = resolveUrl('/logout');
};

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initAuthSession();
  setupNavigation();
  setupSocketListeners();
  loadStats();
  loadSkillsTable();
  loadActivityLogs();
  setupSettingsForm();
  setupChangePasswordForm();

  const options = { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' };
  const todayStr = new Date().toLocaleDateString('en-US', options);
  const dateElem = document.getElementById('current-date-display');
  if (dateElem) dateElem.textContent = `Today: ${todayStr}`;

  // Periodic Refresh
  setInterval(loadStats, 10000);
  setInterval(loadActivityLogs, 8000);
});

// User Session
async function initAuthSession() {
  const logoutBtn = document.getElementById('btn-logout');
  if (logoutBtn) logoutBtn.onclick = window.executeLogout;

  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (data && data.success && data.user) {
      const u = data.user;
      const emailElem = document.getElementById('user-display-email');
      const settingsEmail = document.getElementById('settings-current-email');
      const avatarElem = document.getElementById('user-avatar-initials');

      if (emailElem) emailElem.textContent = u.email || 'admin@zoro.ai';
      if (settingsEmail) settingsEmail.textContent = u.email || 'admin@zoro.ai';
      if (avatarElem) {
        const initials = (u.name || u.email || 'ZR').substring(0, 2).toUpperCase();
        avatarElem.textContent = initials;
      }
    }
  } catch (err) {
    console.error('Failed to load user profile:', err);
  }
}

// Navigation / Tabs
function setupNavigation() {
  const menuButtons = document.querySelectorAll('.menu-item');
  menuButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll('.menu-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  const activeBtn = document.querySelector(`.menu-item[data-tab="${tabId}"]`);
  const activeContent = document.getElementById(tabId);

  if (activeBtn) activeBtn.classList.add('active');
  if (activeContent) activeContent.classList.add('active');

  if (tabId === 'tab-users') loadUsersTable();
  if (tabId === 'tab-skills') loadSkillsTable();
  if (tabId === 'tab-logs') loadActivityLogsTable();
  if (tabId === 'tab-settings') loadSettings();
  if (tabId === 'tab-overview') { loadStats(); loadSkillsTable(); }
}

// Socket.io Listeners
function setupSocketListeners() {
  socket.on('connect', () => {
    console.log('[Socket] Connected to ZORO WhatsApp gateway');
  });

  socket.on('status_update', (data) => {
    updateWhatsAppUI(data);
  });
}

function updateWhatsAppUI(waData) {
  if (!waData || !waData.bot) return;

  const botStatus = waData.bot.status;
  const qr = waData.bot.qr;

  const botPill = document.getElementById('bot-status-pill');
  const qrPill = document.getElementById('bot-qr-status-pill');
  const healthText = document.getElementById('health-text');
  const botDot = document.getElementById('bot-dot');
  const qrContainer = document.getElementById('bot-qr-container');

  const botNumber = waData.bot.number;

  if (botPill) {
    botPill.textContent = botNumber ? `CONNECTED (+${botNumber})` : botStatus;
    botPill.className = `status-indicator-pill ${botStatus.toLowerCase()}`;
  }
  if (qrPill) {
    qrPill.textContent = botNumber ? `Status: CONNECTED (+${botNumber})` : `Status: ${botStatus}`;
    qrPill.className = `status-indicator-pill ${botStatus.toLowerCase()}`;
  }

  if (botStatus === 'CONNECTED') {
    if (healthText) healthText.textContent = botNumber ? `Bot Live (+${botNumber})` : 'Bot Live & Serving';
    if (botDot) botDot.className = 'pulsing-dot online';
    if (qrContainer) {
      qrContainer.innerHTML = `
        <div style="text-align:center; color: #10b981; padding: 20px;">
          <svg width="64" height="64" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <h4 style="margin-top:12px; font-weight:700; color:#10b981;">Connected & Active</h4>
          ${botNumber ? `<div style="margin-top:8px; font-size:1.1rem; font-weight:700; font-family:var(--font-mono); color:#a5b4fc;">📱 +${botNumber}</div>` : ''}
          <p style="font-size:0.8rem; color:#64748b; margin-top:6px;">Bot is live and listening on WhatsApp</p>
        </div>`;
    }
  } else if (botStatus === 'SCAN_QR' && qr) {
    if (healthText) healthText.textContent = 'Action Required: Scan QR';
    if (botDot) botDot.className = 'pulsing-dot action-needed';
    if (qrContainer) {
      qrContainer.innerHTML = `<img src="${qr}" alt="ZORO WhatsApp Pairing QR Code">`;
    }
  } else {
    if (healthText) healthText.textContent = 'Bot Disconnected';
    if (botDot) botDot.className = 'pulsing-dot offline';
    if (qrContainer) {
      qrContainer.innerHTML = `
        <div style="text-align:center; color: #94a3b8; padding: 20px;">
          <div class="spinner" style="display:inline-block; border-color:var(--accent-indigo);"></div>
          <p style="font-size:0.85rem; color:#64748b; margin-top:12px;">Starting session or awaiting QR...</p>
        </div>`;
    }
  }
}

// Stats & Status Fetch
async function loadStats() {
  try {
    const [statsRes, statusRes] = await Promise.all([
      fetch('/api/stats').catch(() => null),
      fetch('/api/status').catch(() => null)
    ]);

    if (statsRes && statsRes.ok) {
      const stats = await statsRes.json();
      const totalElem = document.getElementById('stat-total-users');
      const activeElem = document.getElementById('stat-active-users');
      const googleElem = document.getElementById('stat-google-connected');
      const newElem = document.getElementById('stat-new-today');
      const badgeElem = document.getElementById('users-count-badge');

      if (totalElem) totalElem.textContent = stats.totalUsers || 0;
      if (activeElem) activeElem.textContent = stats.activeUsers || 0;
      if (googleElem) googleElem.textContent = stats.googleConnected || 0;
      if (newElem) newElem.textContent = stats.newToday || 0;
      if (badgeElem) badgeElem.textContent = stats.totalUsers || 0;
    }

    if (statusRes && statusRes.ok) {
      const status = await statusRes.json();
      if (status.whatsapp) {
        updateWhatsAppUI(status.whatsapp);
      }

      const backendPill = document.getElementById('backend-status-pill');
      const backendText = document.getElementById('backend-status-text');
      if (backendPill && status.backend) {
        if (status.backend.healthy) {
          backendPill.textContent = 'Connected (HTTP 200)';
          backendPill.className = 'status-indicator-pill connected';
        } else {
          backendPill.textContent = 'Unreachable';
          backendPill.className = 'status-indicator-pill offline';
        }
      }
      if (backendText && status.backend?.url) {
        backendText.textContent = `Target: ${status.backend.url}`;
      }
    }
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

// Users Directory Table
async function loadUsersTable() {
  const tbody = document.getElementById('users-table-body');
  const countBadge = document.getElementById('table-user-count');
  if (!tbody) return;

  try {
    const res = await fetch('/api/users');
    const users = await res.json();

    if (!Array.isArray(users) || users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No users registered yet. Send "Hi" from any WhatsApp number to get started!</td></tr>`;
      if (countBadge) countBadge.textContent = '0 Users';
      return;
    }

    if (countBadge) countBadge.textContent = `${users.length} Users`;

    tbody.innerHTML = users.map(u => {
      const isBlocked = u.state === 'BLOCKED';
      const isActive = u.state === 'ACTIVE';
      const stateBadge = isBlocked
        ? `<span class="badge badge-blocked">BLOCKED</span>`
        : isActive
        ? `<span class="badge badge-active">ACTIVE</span>`
        : `<span class="badge badge-onboarding">${u.state}</span>`;

      const googleBadge = u.google_connected
        ? `<span class="badge badge-google" title="${u.google_email || ''}">✓ Connected (${u.google_email || 'Linked'})</span>`
        : `<span style="color:#64748b; font-size:12px;">Not Linked</span>`;

      const blockBtn = isBlocked
        ? `<button class="btn btn-xs btn-outline" onclick="unblockUser('${u.phone}')">Unblock</button>`
        : `<button class="btn btn-xs btn-danger" onclick="blockUser('${u.phone}')">Block</button>`;

      const pingBtn = `<button class="btn btn-xs btn-secondary" onclick="quickPingUser('${u.phone}')" title="Send WhatsApp Ping">Ping</button>`;

      const disconnectGoogleBtn = u.google_connected
        ? `<button class="btn btn-xs btn-outline" onclick="disconnectGoogle('${u.phone}')" title="Unlink Google token">Unlink G</button>`
        : '';

      const lastSeenStr = u.last_seen ? new Date(u.last_seen).toLocaleString() : 'Never';

      return `
        <tr>
          <td><strong style="color:#1d4ed8; font-size:1.02rem;">+${u.phone}</strong></td>
          <td>${escapeHtml(u.name || 'Pending')}</td>
          <td><span style="font-size:12px; color:var(--text-muted);">${escapeHtml(u.use_case || 'Not set')}</span></td>
          <td>${stateBadge}</td>
          <td>${googleBadge}</td>
          <td><strong>${u.message_count || 0}</strong></td>
          <td><span style="font-size:12px; color:var(--text-sub);">${lastSeenStr}</span></td>
          <td>
            <div style="display:flex; gap:6px; align-items:center;">
              ${pingBtn}
              ${blockBtn}
              ${disconnectGoogleBtn}
            </div>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state text-danger">Error loading users: ${err.message}</td></tr>`;
  }
}

// User Actions
window.blockUser = async function(phone) {
  if (!confirm(`Are you sure you want to block +${phone}? Their messages will be silently dropped.`)) return;
  try {
    const res = await fetch(`/api/users/${phone}/block`, { method: 'POST' });
    if (res.ok) {
      showToast(`User +${phone} blocked.`);
      loadUsersTable();
    }
  } catch (err) {
    showToast(`Failed to block user: ${err.message}`, 'error');
  }
};

window.unblockUser = async function(phone) {
  try {
    const res = await fetch(`/api/users/${phone}/unblock`, { method: 'POST' });
    if (res.ok) {
      showToast(`User +${phone} unblocked.`);
      loadUsersTable();
    }
  } catch (err) {
    showToast(`Failed to unblock user: ${err.message}`, 'error');
  }
};

window.disconnectGoogle = async function(phone) {
  if (!confirm(`Revoke Google OAuth tokens for +${phone}?`)) return;
  try {
    const res = await fetch(`/api/google/disconnect/${phone}`, { method: 'POST' });
    if (res.ok) {
      showToast(`Google tokens disconnected for +${phone}.`);
      loadUsersTable();
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
};

window.quickPingUser = function(phone) {
  const input = document.getElementById('ping-phone-input');
  if (input) input.value = phone;
  switchTab('tab-overview');
  sendTestPingFromUI();
};

// WhatsApp Ping Sandbox
window.sendTestPingFromUI = async function() {
  const input = document.getElementById('ping-phone-input');
  const resultDiv = document.getElementById('ping-result-msg');
  const phone = input?.value.trim();

  if (!phone) {
    if (resultDiv) resultDiv.innerHTML = `<span style="color:#f43f5e;">Please enter a phone number.</span>`;
    return;
  }

  if (resultDiv) resultDiv.innerHTML = `<span style="color:#94a3b8;">Sending ping to +${phone}...</span>`;

  try {
    const res = await fetch('/api/test/whatsapp-ping', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      if (resultDiv) resultDiv.innerHTML = `<span style="color:#10b981;">✓ ${data.message}</span>`;
      showToast(`Ping sent to +${phone}!`);
    } else {
      if (resultDiv) resultDiv.innerHTML = `<span style="color:#f43f5e;">✗ ${data.error || 'Failed to send ping'}</span>`;
    }
  } catch (err) {
    if (resultDiv) resultDiv.innerHTML = `<span style="color:#f43f5e;">✗ Network error: ${err.message}</span>`;
  }
};

// Bot Disconnect Session
window.disconnectBotSession = async function() {
  if (!confirm('Disconnect WhatsApp session? This will force a new QR code scan.')) return;
  try {
    const res = await fetch('/api/whatsapp/disconnect', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || 'Bot disconnected.');
    loadStats();
  } catch (err) {
    showToast('Failed to disconnect bot: ' + err.message, 'error');
  }
};

// Reset Users Data
window.resetUsersData = async function() {
  if (!confirm('DANGER: Clear all registered users and reset their onboarding state?')) return;
  try {
    const res = await fetch('/api/system/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clearUsers: true })
    });
    const data = await res.json();
    showToast('Reset completed: ' + (data.message || 'Users cleared'));
    loadStats();
    loadUsersTable();
  } catch (err) {
    showToast('Reset failed: ' + err.message, 'error');
  }
};

// Activity Logs
async function loadActivityLogs() {
  const container = document.getElementById('live-activity-feed');
  if (!container) return;

  try {
    const res = await fetch('/api/logs');
    const logs = await res.json();

    if (!Array.isArray(logs) || logs.length === 0) {
      container.innerHTML = `<div class="empty-state">No activity recorded yet.</div>`;
      return;
    }

    container.innerHTML = logs.slice(0, 15).map(log => {
      const timeStr = log.created_at ? new Date(log.created_at).toLocaleTimeString() : '';
      return `
        <div class="activity-item" style="padding: 8px 12px; border-bottom: 1px solid var(--border-color); font-size:12px;">
          <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
            <strong style="color:#facc15;">${escapeHtml(log.category || 'SYSTEM')}</strong>
            <span style="color:#71717a;">${timeStr}</span>
          </div>
          <div style="color:var(--text-main); word-break:break-word;">${escapeHtml(log.message || '')}</div>
        </div>
      `;
    }).join('');
  } catch (err) {}
}

async function loadActivityLogsTable() {
  const tbody = document.getElementById('logs-full-table-body');
  if (!tbody) return;

  try {
    const res = await fetch('/api/logs');
    const logs = await res.json();

    if (!Array.isArray(logs) || logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No logs found.</td></tr>`;
      return;
    }

    tbody.innerHTML = logs.map(l => {
      const time = l.created_at ? new Date(l.created_at).toLocaleString() : '';
      const levelClass = l.level === 'WARN' ? 'color:#854d0e; background:#fef9c3; padding:2px 6px; border-radius:4px;' : l.level === 'ERROR' ? 'color:#b91c1c; background:#fee2e2; padding:2px 6px; border-radius:4px;' : 'color:#15803d; background:#f0fdf4; padding:2px 6px; border-radius:4px;';
      return `
        <tr>
          <td style="font-size:12px; color:var(--text-sub); white-space:nowrap;">${time}</td>
          <td><strong style="color:#facc15;">${escapeHtml(l.category)}</strong></td>
          <td><span style="${levelClass} font-weight:700;">${l.level}</span></td>
          <td style="word-break:break-word;">${escapeHtml(l.message)}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state text-danger">Error: ${err.message}</td></tr>`;
  }
}

// Settings Handlers
async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    if (data && data.settings) {
      const s = data.settings;
      const be = document.getElementById('setting-backend-url');
      const gid = document.getElementById('setting-google-id');
      const gsec = document.getElementById('setting-google-secret');
      if (be) be.value = s.BACKEND_URL || '';
      if (gid) gid.value = s.GOOGLE_CLIENT_ID || '';
      if (gsec) gsec.value = s.GOOGLE_CLIENT_SECRET || '';
    }
  } catch (err) {
    console.error('Failed to load settings:', err);
  }
}

function setupSettingsForm() {
  const form = document.getElementById('settings-form');
  const statusElem = document.getElementById('settings-save-status');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      BACKEND_URL: document.getElementById('setting-backend-url')?.value.trim(),
      GOOGLE_CLIENT_ID: document.getElementById('setting-google-id')?.value.trim(),
      GOOGLE_CLIENT_SECRET: document.getElementById('setting-google-secret')?.value.trim()
    };

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        if (statusElem) {
          statusElem.textContent = '✓ Configuration saved successfully!';
          statusElem.style.color = '#10b981';
          setTimeout(() => { statusElem.textContent = ''; }, 3000);
        }
        showToast('Settings saved successfully!');
      }
    } catch (err) {
      if (statusElem) {
        statusElem.textContent = '✗ Error saving: ' + err.message;
        statusElem.style.color = '#f43f5e';
      }
    }
  });
}

function setupChangePasswordForm() {
  const form = document.getElementById('form-change-password');
  const msgElem = document.getElementById('pwd-change-msg');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const currentPassword = document.getElementById('pwd-current').value;
    const newPassword = document.getElementById('pwd-new').value;
    const confirmPassword = document.getElementById('pwd-confirm').value;

    if (newPassword !== confirmPassword) {
      if (msgElem) {
        msgElem.textContent = '❌ New passwords do not match';
        msgElem.style.color = '#f43f5e';
      }
      return;
    }

    try {
      const res = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ currentPassword, newPassword })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        if (msgElem) {
          msgElem.textContent = '✓ Passcode updated successfully!';
          msgElem.style.color = '#10b981';
        }
        form.reset();
        showToast('Passcode updated successfully!');
      } else {
        if (msgElem) {
          msgElem.textContent = '❌ ' + (data.error || 'Failed to update passcode');
          msgElem.style.color = '#f43f5e';
        }
      }
    } catch (err) {
      if (msgElem) {
        msgElem.textContent = '❌ Network error';
        msgElem.style.color = '#f43f5e';
      }
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

window.scrollToSkillForm = function() {
  const card = document.getElementById('add-skill-card');
  if (card) {
    card.scrollIntoView({ behavior: 'smooth' });
    document.getElementById('skill-name')?.focus();
  }
};

window.loadSkillsTable = async function() {
  const tbody = document.getElementById('skills-table-body');
  const countBadge = document.getElementById('skills-count-badge');
  if (!tbody) return;

  try {
    const res = await fetch('/api/skills');
    const skills = await res.json();

    if (countBadge && Array.isArray(skills)) {
      countBadge.textContent = skills.length;
    }

    if (!skills || !Array.isArray(skills) || skills.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">No skills registered yet. Create your first skill below!</td></tr>`;
      return;
    }

    tbody.innerHTML = skills.map(s => {
      const isGlobal = s.user_phone === 'GLOBAL';
      const scopeBadge = isGlobal
        ? `<span class="badge" style="background:rgba(250,204,21,0.15); color:#facc15; border:1px solid #facc15; font-weight:700;">Global</span>`
        : `<span class="badge" style="background:rgba(234,179,8,0.2); color:#fef08a; border:1px solid #ca8a04; font-weight:700;">User: +${escapeHtml(s.user_phone)}</span>`;
      
      const keywords = s.trigger_keywords ? s.trigger_keywords.split(',').map(k => `<span class="badge" style="background:#18181b; color:#facc15; border:1px solid #27272a; margin:2px;">${escapeHtml(k.trim())}</span>`).join(' ') : '<em style="color:#71717a;">Any topic</em>';
      
      const promptSnippet = escapeHtml(s.system_prompt || '');
      const webhook = s.webhook_url ? `<a href="${escapeHtml(s.webhook_url)}" target="_blank" style="color:#facc15; text-decoration:underline; font-size:12px;">Endpoint</a>` : '<span style="color:#71717a; font-size:12px;">None (Native LLM)</span>';

      return `
        <tr>
          <td>
            <div style="font-weight:700; font-size:14px; color:#ffffff; display:flex; align-items:center; gap:8px;">
              ${escapeHtml(s.name)}
              ${scopeBadge}
            </div>
            <div style="font-size:12px; color:#a1a1aa; margin-top:3px;">${escapeHtml(s.description || '')}</div>
          </td>
          <td>${keywords}</td>
          <td>
            <div style="font-size:12px; color:#f4f4f5; max-height:60px; overflow-y:auto; background:#000000; padding:6px; border:1px solid #27272a; border-radius:4px; font-family:inherit;">
              ${promptSnippet}
            </div>
          </td>
          <td>${webhook}</td>
          <td>
            <button class="btn btn-outline btn-sm" style="color:#dc2626; border-color:#fca5a5;" onclick="handleDeleteSkill('${escapeHtml(s.skill_id)}')">Delete</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-state" style="color:#ef4444;">Failed to load skills: ${err.message}</td></tr>`;
  }
};

window.handleCreateSkill = async function(e) {
  e.preventDefault();
  const name = document.getElementById('skill-name').value.trim();
  const trigger_keywords = document.getElementById('skill-keywords').value.trim();
  const description = document.getElementById('skill-description').value.trim();
  const system_prompt = document.getElementById('skill-prompt').value.trim();
  const webhook_url = document.getElementById('skill-webhook').value.trim();

  try {
    const res = await fetch('/api/skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        trigger_keywords,
        description,
        system_prompt,
        webhook_url: webhook_url || null,
        user_phone: 'GLOBAL'
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Skill "${name}" deployed successfully!`);
      document.getElementById('create-skill-form').reset();
      loadSkillsTable();
    } else {
      showToast(data.error || 'Failed to create skill', 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  }
};

window.handleDeleteSkill = async function(skillId) {
  if (!confirm('Are you sure you want to remove this skill?')) return;
  try {
    const res = await fetch(`/api/skills/${skillId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast('Skill removed');
      loadSkillsTable();
    } else {
      showToast(data.error || 'Failed to remove skill', 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  }
};

const LIBRARY_TEMPLATES = {
  pdf_generator: {
    name: 'PDF & Report Generator',
    trigger_keywords: 'pdf, export pdf, generate report, meeting pdf',
    description: 'Compiles meeting minutes, schedules, and analytics into downloadable PDF reports.',
    system_prompt: 'You are an executive document assistant. Summarize requested records into clean, structured Markdown ready for PDF compilation.'
  },
  web_researcher: {
    name: 'Web Research & Intelligence',
    trigger_keywords: 'research, google search, find info, search web',
    description: 'Automates live fact-checking, flight lookups, and company background research.',
    system_prompt: 'You are an executive research analyst. Provide concise, bulleted insights, verified facts, and direct answers without fluff.'
  },
  cron_scheduler: {
    name: 'Recurring Automation & Reminders',
    trigger_keywords: 'remind me daily, recurring, every day, briefing',
    description: 'Sets up daily briefings, recurring reminders, and automated health checks.',
    system_prompt: 'You are an automated scheduling bot. Formulate recurring daily or weekly reminders with exact times and clear summary checkpoints.'
  },
  code_auditor: {
    name: 'Desktop Code Auditor',
    trigger_keywords: 'review code, audit, inspect git, check diff',
    description: 'Reviews code snippets, inspects git diffs, and flags security flaws or syntax bugs.',
    system_prompt: 'You are a Senior Principal Software Engineer. Review the supplied code for bugs, race conditions, security flaws, and performance optimizations.'
  },
  sql_analyst: {
    name: 'Database & SQL Analyst',
    trigger_keywords: 'sql, query database, database stats, db count',
    description: 'Runs read-only queries, generates SQL reports, and explains database metrics.',
    system_prompt: 'You are a database engineer. Generate safe, read-only SELECT queries and format the query results in clean Markdown tables.'
  }
};

window.installLibrarySkill = async function(templateKey) {
  const tpl = LIBRARY_TEMPLATES[templateKey];
  if (!tpl) return;
  try {
    const res = await fetch('/api/skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...tpl,
        user_phone: 'GLOBAL'
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(`Skill "${tpl.name}" installed from library!`);
      loadSkillsTable();
    } else {
      showToast(data.error || 'Failed to install skill', 'error');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
  }
};

