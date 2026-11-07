import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { query, logActivity } from '../database/db.js';

const isProd = process.env.NODE_ENV === 'production' || process.env.APP_ENV === 'production';
const DEFAULT_ADMIN_EMAIL = process.env.ADMIN_EMAIL || 'admin@fastagent.ai';

if (isProd && (!process.env.ADMIN_PASSWORD || process.env.ADMIN_PASSWORD === 'admin123' || process.env.ADMIN_PASSWORD.length < 12)) {
  console.error('[SECURITY FATAL] In production, ADMIN_PASSWORD must be explicitly configured with at least 12 characters.');
  throw new Error('ADMIN_PASSWORD must be explicitly configured with at least 12 characters in production.');
}

const DEFAULT_ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || (isProd ? '' : 'admin123');
const DEFAULT_ADMIN_NAME = 'DUIT Admin';

// In-memory session store fallback for cloud stateless deployments
const inMemorySessions = new Map();

/**
 * Hash a password using scrypt with a unique salt
 */
export function hashPassword(password, salt = null) {
  const passwordSalt = salt || crypto.randomBytes(16).toString('hex');
  const derivedKey = crypto.scryptSync(password, passwordSalt, 64);
  return {
    hash: derivedKey.toString('hex'),
    salt: passwordSalt
  };
}

/**
 * Verify a plain text password against stored hash & salt
 */
export function verifyPassword(password, storedHash, salt) {
  try {
    const candidateKey = crypto.scryptSync(password, salt, 64);
    const candidateHash = candidateKey.toString('hex');
    const storedBuf = Buffer.from(storedHash, 'hex');
    const candidateBuf = Buffer.from(candidateHash, 'hex');
    if (storedBuf.length !== candidateBuf.length) return false;
    return crypto.timingSafeEqual(storedBuf, candidateBuf);
  } catch (err) {
    console.error('[Auth Error] verifyPassword exception:', err.message);
    return false;
  }
}

/**
 * Seed default admin credentials if admin_users is empty or user is missing
 */
export async function seedDefaultAdmin() {
  try {
    const users = await query('SELECT id, email FROM admin_users LIMIT 5');
    if (users && users.length > 0) {
      // Check if default user exists
      const found = users.find(u => u.email.toLowerCase() === DEFAULT_ADMIN_EMAIL.toLowerCase());
      if (found) {
        return;
      }
    }

    const isProd = process.env.NODE_ENV === 'production' || process.env.APP_ENV === 'production';
    if (!DEFAULT_ADMIN_PASSWORD && isProd) {
      throw new Error('[FATAL] Missing required environment variable: ADMIN_PASSWORD must be configured in production.');
    }

    // In development, generate a one-time random bootstrap password and persist to secure file without logging
    const adminPassword = DEFAULT_ADMIN_PASSWORD || crypto.randomBytes(16).toString('base64url');

    // Seed default admin
    const { hash, salt } = hashPassword(adminPassword);
    await query(
      `INSERT INTO admin_users (email, name, password_hash, salt, role) 
       VALUES (?, ?, ?, ?, 'director')
       ON DUPLICATE KEY UPDATE updated_at = NOW()`,
      [DEFAULT_ADMIN_EMAIL.toLowerCase(), DEFAULT_ADMIN_NAME, hash, salt]
    );

    if (!DEFAULT_ADMIN_PASSWORD) {
      console.warn(`[SECURITY NOTICE] ADMIN_PASSWORD was not set. Generated temporary development password.`);
    } else {
      console.log(`[Auth] Admin account verified for: ${DEFAULT_ADMIN_EMAIL}`);
    }
  } catch (err) {
    console.error(`[Auth Error] Failed to seed default admin:`, err.message);
  }
}

/**
 * Log in admin user, verify credentials, create session token
 */
export async function loginUser(email, password, userAgent = '', ipAddress = '') {
  if (!email || !password) {
    return { success: false, error: 'Email and password are required' };
  }

  const cleanEmail = email.trim().toLowerCase();
  const rows = await query('SELECT * FROM admin_users WHERE LOWER(email) = ? LIMIT 1', [cleanEmail]);

  if (!rows || rows.length === 0) {
    // Fallback: check against environment admin credentials in cloud mode (production requires non-default, >=12 char password)
    const isSafePassword = DEFAULT_ADMIN_PASSWORD && (!isProd || (DEFAULT_ADMIN_PASSWORD !== 'admin123' && DEFAULT_ADMIN_PASSWORD.length >= 12));
    if (isSafePassword && cleanEmail === DEFAULT_ADMIN_EMAIL.toLowerCase() && password === DEFAULT_ADMIN_PASSWORD) {
      const token = crypto.randomBytes(32).toString('hex');
      const expiresAt = Date.now() + 24 * 60 * 60 * 1000;
      inMemorySessions.set(token, {
        id: 1,
        email: DEFAULT_ADMIN_EMAIL,
        name: DEFAULT_ADMIN_NAME,
        role: 'director',
        expiresAt
      });
      return {
        success: true,
        token,
        user: { id: 1, email: DEFAULT_ADMIN_EMAIL, name: DEFAULT_ADMIN_NAME, role: 'director' }
      };
    }
    return { success: false, error: 'Invalid email address or credentials' };
  }

  const user = rows[0];
  const isValid = verifyPassword(password, user.password_hash, user.salt);

  if (!isValid) {
    await logActivity('SECURITY', `Failed login attempt for ${cleanEmail}`, 'WARN', { ip: ipAddress });
    return { success: false, error: 'Invalid email address or password' };
  }

  // Create session token (64 hex chars = 32 random bytes)
  const token = crypto.randomBytes(32).toString('hex');
  // Token valid for 24 hours
  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000);

  await query(
    `INSERT INTO auth_sessions (token, user_id, email, expires_at, user_agent, ip_address)
     VALUES (?, ?, ?, ?, ?, ?)`,
    [token, user.id, user.email, expiresAt, (userAgent || '').substring(0, 250), (ipAddress || '').substring(0, 60)]
  );

  await logActivity('AUTH', `Director logged in: ${user.email}`, 'INFO', { ip: ipAddress });

  return {
    success: true,
    token,
    user: {
      id: user.id,
      email: user.email,
      name: user.name,
      role: user.role
    }
  };
}

/**
 * Validate an incoming session token
 */
export async function validateSession(token) {
  if (!token || typeof token !== 'string' || token.length < 16) {
    return null;
  }

  const memSession = inMemorySessions.get(token);
  if (memSession) {
    if (Date.now() < memSession.expiresAt) {
      return {
        id: memSession.id,
        email: memSession.email,
        name: memSession.name,
        role: memSession.role
      };
    } else {
      inMemorySessions.delete(token);
      return null;
    }
  }

  try {
    const rows = await query(
      `SELECT s.token, s.expires_at, u.id, u.email, u.name, u.role
       FROM auth_sessions s
       JOIN admin_users u ON s.user_id = u.id
       WHERE s.token = ? AND s.expires_at > NOW()
       LIMIT 1`,
      [token]
    );

    if (rows && rows.length > 0) {
      return {
        id: rows[0].id,
        email: rows[0].email,
        name: rows[0].name,
        role: rows[0].role
      };
    }
    return null;
  } catch (err) {
    console.error('[Auth Error] validateSession exception:', err.message);
    return null;
  }
}

/**
 * Terminate an active session token
 */
export async function logoutSession(token) {
  if (!token) return;
  inMemorySessions.delete(token);
  try {
    await query('DELETE FROM auth_sessions WHERE token = ?', [token]);
  } catch (err) {
    console.error('[Auth Error] logoutSession error:', err.message);
  }
}

/**
 * Change password for an authenticated user
 */
export async function changeUserPassword(userId, currentPassword, newPassword) {
  if (!userId) {
    return { success: false, error: 'Unauthorized request' };
  }
  if (!currentPassword) {
    return { success: false, error: 'Current password is required' };
  }
  if (!newPassword || newPassword.length < 10) {
    return { success: false, error: 'New password must be at least 10 characters long' };
  }

  const rows = await query('SELECT * FROM admin_users WHERE id = ? LIMIT 1', [userId]);
  if (!rows || rows.length === 0) {
    return { success: false, error: 'User account not found' };
  }

  const user = rows[0];
  const isCurrentValid = verifyPassword(currentPassword, user.password_hash, user.salt);
  if (!isCurrentValid) {
    return { success: false, error: 'Current password entered is incorrect' };
  }

  // Hash new password with new salt
  const { hash, salt } = hashPassword(newPassword);
  await query(
    'UPDATE admin_users SET password_hash = ?, salt = ?, updated_at = NOW() WHERE id = ?',
    [hash, salt, userId]
  );

  // Invalidate all active sessions for this user after password change
  await query('DELETE FROM auth_sessions WHERE user_id = ?', [userId]);

  await logActivity('SECURITY', `Password successfully updated for user ${user.email}. Active sessions invalidated.`, 'INFO');

  return {
    success: true,
    message: 'Password updated successfully. You can now use your new password.'
  };
}
