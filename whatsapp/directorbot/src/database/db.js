import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
dotenv.config();

let pool = null;
let isConnected = false;

const dbConfig = {
  host: process.env.MYSQL_HOST || 'localhost',
  port: parseInt(process.env.MYSQL_PORT || '3306'),
  user: process.env.MYSQL_USER || 'root',
  password: process.env.MYSQL_PASSWORD || '',
  database: process.env.MYSQL_DATABASE || 'executive_ai_db',
  waitForConnections: true,
  connectionLimit: 10,
  queueLimit: 0
};

export async function initDatabase() {
  try {
    // First connect without database to create database if it does not exist
    const rootConnection = await mysql.createConnection({
      host: dbConfig.host,
      port: dbConfig.port,
      user: dbConfig.user,
      password: dbConfig.password
    });

    await rootConnection.query(`CREATE DATABASE IF NOT EXISTS \`${dbConfig.database}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`);
    await rootConnection.end();

    // Now initialize the pool
    pool = mysql.createPool(dbConfig);

    // Test connection
    const connection = await pool.getConnection();
    connection.release();
    isConnected = true;
    console.log(`[Database] Connected successfully to MySQL database "${dbConfig.database}"`);

    // Create required tables
    await createTables();
    return true;
  } catch (error) {
    isConnected = false;
    console.error(`[Database Error] Failed to connect to MySQL:`, error.message);
    return false;
  }
}

async function createTables() {
  if (!pool) return;

  const tables = [
    // System Settings Table
    `CREATE TABLE IF NOT EXISTS \`system_settings\` (
      \`key_name\` VARCHAR(100) PRIMARY KEY,
      \`value\` TEXT,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;`,

    // Google Tokens Table — per WhatsApp user OAuth tokens
    `CREATE TABLE IF NOT EXISTS \`google_tokens\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`phone\` VARCHAR(30),
      \`email\` VARCHAR(255),
      \`refresh_token\` TEXT,
      \`access_token\` TEXT,
      \`expiry_date\` BIGINT,
      \`scope\` TEXT,
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX \`idx_gt_phone\` (\`phone\`),
      INDEX \`idx_gt_email\` (\`email\`)
    ) ENGINE=InnoDB;`,

    // FastAgent Users — multi-tenant WhatsApp user registry
    `CREATE TABLE IF NOT EXISTS \`fastagent_users\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`phone\` VARCHAR(30) NOT NULL UNIQUE,
      \`name\` VARCHAR(150),
      \`use_case\` VARCHAR(100),
      \`state\` ENUM('NEW','ONBOARDING_NAME','ONBOARDING_USE_CASE','ONBOARDING_AUTH','ACTIVE','BLOCKED') DEFAULT 'NEW',
      \`google_connected\` BOOLEAN DEFAULT FALSE,
      \`google_email\` VARCHAR(255),
      \`message_count\` INT DEFAULT 0,
      \`last_seen\` TIMESTAMP NULL,
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX \`idx_fa_phone\` (\`phone\`),
      INDEX \`idx_fa_state\` (\`state\`)
    ) ENGINE=InnoDB;`,

    // Schedules & Meetings Table (Entered by PA or WhatsApp)
    `CREATE TABLE IF NOT EXISTS \`schedules\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`date\` DATE NOT NULL,
      \`time_slot\` VARCHAR(50) NOT NULL,
      \`title\` VARCHAR(255) NOT NULL,
      \`description\` TEXT,
      \`location\` VARCHAR(255) DEFAULT 'Director Office / Online',
      \`priority\` VARCHAR(20) DEFAULT 'Normal',
      \`created_by\` VARCHAR(50) DEFAULT 'PA',
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;`,

    // WhatsApp Chats Cache Table (Silent listener of Director's phone)
    `CREATE TABLE IF NOT EXISTS \`whatsapp_chats\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`msg_id\` VARCHAR(150) UNIQUE,
      \`owner_phone\` VARCHAR(50) NOT NULL,
      \`chat_jid\` VARCHAR(100) NOT NULL,
      \`sender_name\` VARCHAR(150),
      \`sender_phone\` VARCHAR(50),
      \`message_text\` TEXT,
      \`timestamp\` BIGINT NOT NULL,
      \`is_from_me\` BOOLEAN DEFAULT FALSE,
      \`ai_summary\` TEXT,
      \`ai_urgency\` VARCHAR(20) DEFAULT 'Normal',
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX \`idx_chat_jid\` (\`chat_jid\`),
      INDEX \`idx_chat_owner_timestamp\` (\`owner_phone\`, \`timestamp\`),
      INDEX \`idx_timestamp\` (\`timestamp\`)
    ) ENGINE=InnoDB;`,

    // WhatsApp Synced Contacts Table
    `CREATE TABLE IF NOT EXISTS \`whatsapp_contacts\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`jid\` VARCHAR(100) UNIQUE,
      \`phone\` VARCHAR(50),
      \`name\` VARCHAR(150),
      \`notify\` VARCHAR(150),
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX \`idx_phone\` (\`phone\`),
      INDEX \`idx_name\` (\`name\`)
    ) ENGINE=InnoDB;`,

    // Email Summaries Table (Analyzed from Gmail API)
    `CREATE TABLE IF NOT EXISTS \`email_summaries\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`gmail_id\` VARCHAR(100) UNIQUE,
      \`sender_email\` VARCHAR(255),
      \`sender_name\` VARCHAR(150),
      \`subject\` VARCHAR(500),
      \`snippet\` TEXT,
      \`date_received\` VARCHAR(100),
      \`priority\` VARCHAR(20) DEFAULT 'Normal',
      \`summary\` TEXT,
      \`action_required\` TEXT,
      \`is_processed\` BOOLEAN DEFAULT FALSE,
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX \`idx_priority\` (\`priority\`),
      INDEX \`idx_gmail_id\` (\`gmail_id\`)
    ) ENGINE=InnoDB;`,

    // Email Drafts Table (Director Command with Confirmation)
    `CREATE TABLE IF NOT EXISTS \`email_drafts\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`recipient_email\` VARCHAR(255) NOT NULL,
      \`recipient_name\` VARCHAR(150),
      \`subject\` VARCHAR(500) NOT NULL,
      \`body\` TEXT NOT NULL,
      \`status\` ENUM('PENDING_VERIFICATION', 'VERIFIED_SENT', 'CANCELLED') DEFAULT 'PENDING_VERIFICATION',
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`sent_at\` TIMESTAMP NULL,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;`,

    // Daily Executive Briefings Table
    `CREATE TABLE IF NOT EXISTS \`briefings\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`briefing_date\` DATE UNIQUE,
      \`pdf_filename\` VARCHAR(255),
      \`summary_text\` MEDIUMTEXT,
      \`edtech_news\` JSON,
      \`is_sent_to_director\` BOOLEAN DEFAULT FALSE,
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;`,

    // Activity Logs Table for Dashboard Feed
    `CREATE TABLE IF NOT EXISTS \`activity_logs\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`level\` VARCHAR(20) DEFAULT 'INFO',
      \`module\` VARCHAR(50) NOT NULL,
      \`message\` TEXT NOT NULL,
      \`metadata\` JSON,
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX \`idx_created_at\` (\`created_at\`)
    ) ENGINE=InnoDB;`,

    // Administrator & Executive Login Users
    `CREATE TABLE IF NOT EXISTS \`admin_users\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`email\` VARCHAR(255) NOT NULL UNIQUE,
      \`name\` VARCHAR(150) DEFAULT 'Director',
      \`password_hash\` VARCHAR(255) NOT NULL,
      \`salt\` VARCHAR(64) NOT NULL,
      \`role\` VARCHAR(50) DEFAULT 'director',
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX \`idx_user_email\` (\`email\`)
    ) ENGINE=InnoDB;`,

    // Auth Sessions & Active Tokens
    `CREATE TABLE IF NOT EXISTS \`auth_sessions\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`token\` VARCHAR(128) NOT NULL UNIQUE,
      \`user_id\` INT NOT NULL,
      \`email\` VARCHAR(255) NOT NULL,
      \`expires_at\` TIMESTAMP NOT NULL,
      \`user_agent\` VARCHAR(255),
      \`ip_address\` VARCHAR(64),
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      INDEX \`idx_session_token\` (\`token\`),
      INDEX \`idx_session_expires\` (\`expires_at\`),
      FOREIGN KEY (\`user_id\`) REFERENCES \`admin_users\`(\`id\`) ON DELETE CASCADE
    ) ENGINE=InnoDB;`,

    // FastAgent Skills Table — modular dynamic agent skills
    `CREATE TABLE IF NOT EXISTS \`fastagent_skills\` (
      \`id\` INT AUTO_INCREMENT PRIMARY KEY,
      \`skill_id\` VARCHAR(50) UNIQUE,
      \`user_phone\` VARCHAR(30) DEFAULT 'GLOBAL',
      \`name\` VARCHAR(150) NOT NULL,
      \`slug\` VARCHAR(100) NOT NULL,
      \`description\` TEXT,
      \`system_prompt\` TEXT NOT NULL,
      \`trigger_keywords\` VARCHAR(255),
      \`webhook_url\` VARCHAR(500),
      \`is_active\` BOOLEAN DEFAULT TRUE,
      \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      \`updated_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      INDEX \`idx_skill_user\` (\`user_phone\`),
      INDEX \`idx_skill_slug\` (\`slug\`)
    ) ENGINE=InnoDB;`
  ];

  for (const tableSql of tables) {
    try {
      await pool.query(tableSql);
    } catch (err) {
      console.error(`[Database Error] Error creating table:`, err.message);
    }
  }

  // Safe ALTER TABLE migrations to ensure updated_at exists on older installations
  const safeAlterColumns = [
    `ALTER TABLE email_drafts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`,
    `ALTER TABLE google_tokens ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`,
    `ALTER TABLE whatsapp_chats ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`,
    `ALTER TABLE schedules ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`,
    `ALTER TABLE briefings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`,
    `ALTER TABLE email_summaries ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`
  ];

  for (const alterSql of safeAlterColumns) {
    try {
      await pool.query(alterSql);
    } catch (err) {
      // Column already exists or table not ready, safely ignore
    }

    try {
      await pool.query(`ALTER TABLE whatsapp_chats ADD COLUMN owner_phone VARCHAR(50) NULL`);
      await pool.query(`UPDATE whatsapp_chats SET owner_phone = sender_phone WHERE owner_phone IS NULL`);
      await pool.query(`ALTER TABLE whatsapp_chats MODIFY COLUMN owner_phone VARCHAR(50) NOT NULL`);
      await pool.query(`CREATE INDEX idx_chat_owner_timestamp ON whatsapp_chats (owner_phone, timestamp)`);
    } catch (err) {
      if (!String(err.message).includes('Duplicate')) throw err;
    }
  }

  // Seed default admin credentials
  try {
    const { seedDefaultAdmin } = await import('../services/authService.js');
    await seedDefaultAdmin();
  } catch (err) {
    console.error('[Database Error] Failed to seed default admin:', err.message);
  }

  // Seed default agent skills
  try {
    await seedDefaultSkills();
  } catch (err) {
    console.error('[Database Error] Failed to seed default skills:', err.message);
  }

  console.log(`[Database] All MySQL tables verified/created successfully.`);
}

async function seedDefaultSkills() {
  if (!pool) return;
  const countRes = await query('SELECT COUNT(*) as cnt FROM fastagent_skills');
  if (countRes[0] && countRes[0].cnt > 0) {
    return; // Already seeded
  }

  const defaultSkills = [
    {
      skill_id: 'skill_expense',
      user_phone: 'GLOBAL',
      name: 'Receipt & Expense Tracker',
      slug: 'expense_tracker',
      description: 'Extracts items, amounts, tax, vendors, and categories from receipts or expense texts.',
      system_prompt: 'You are an expert Expense Tracker. Analyze the user\'s receipt or expense notes. Extract: 1. Vendor/Store 2. Items & Amounts 3. Total Amount & Currency 4. Date 5. Category (Food, Travel, Bills, Work, Personal). Output a clean, markdown expense summary table.',
      trigger_keywords: 'expense, bill, receipt, kharcha, spend, paid, invoice',
      webhook_url: null
    },
    {
      skill_id: 'skill_action_items',
      user_phone: 'GLOBAL',
      name: 'Meeting Action Item Extractor',
      slug: 'action_items',
      description: 'Extracts tasks, assignees, deadlines, and next steps from meeting transcripts or discussion notes.',
      system_prompt: 'You are an Executive Chief of Staff. Extract all actionable decisions and tasks from the meeting notes or text. Output a markdown table with: Task, Assignee/Owner, Deadline, Priority (Urgent/Normal), and Recommended Next Steps.',
      trigger_keywords: 'action items, meeting minutes, mom, meeting notes, action tasks, discussion notes',
      webhook_url: null
    },
    {
      skill_id: 'skill_copywriter',
      user_phone: 'GLOBAL',
      name: 'Sales Outreach Copywriter',
      slug: 'sales_copywriter',
      description: 'Crafts high-converting B2B outreach messages, cold emails, and pitch proposals.',
      system_prompt: 'You are a World-Class B2B Copywriter. Craft high-converting cold emails or messages using PAS (Problem-Agitate-Solution). Include: 1. Compelling subject lines 2. Personalized hook 3. Value proposition 4. Clear low-friction CTA. Keep under 120 words.',
      trigger_keywords: 'cold email, pitch, outreach, copy, sales message, proposal',
      webhook_url: null
    },
    {
      skill_id: 'skill_code_debugger',
      user_phone: 'GLOBAL',
      name: 'Code Reviewer & Debugger',
      slug: 'code_debugger',
      description: 'Analyzes code snippets, explains errors/stack traces, and provides tested clean fixes.',
      system_prompt: 'You are a Principal Software Engineer. Diagnose the code or stack trace, explain the root cause concisely, and provide the minimal, tested fix code snippet with clean documentation.',
      trigger_keywords: 'code, error, bug, trace, python, debug, fix, traceback',
      webhook_url: null
    }
  ];

  for (const s of defaultSkills) {
    await query(
      `INSERT INTO fastagent_skills (skill_id, user_phone, name, slug, description, system_prompt, trigger_keywords, webhook_url, is_active)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)
       ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description), system_prompt=VALUES(system_prompt)`,
      [s.skill_id, s.user_phone, s.name, s.slug, s.description, s.system_prompt, s.trigger_keywords, s.webhook_url]
    );
  }
  console.log('[Database] Default FastAgent skills seeded successfully.');
}

export async function listSkills(userPhone = null) {
  try {
    let sql = 'SELECT * FROM fastagent_skills WHERE is_active = TRUE';
    const params = [];
    if (userPhone) {
      sql += ' AND (user_phone = "GLOBAL" OR user_phone = ?)';
      params.push(userPhone);
    }
    sql += ' ORDER BY created_at DESC';
    return await query(sql, params);
  } catch (err) {
    console.error('[Database Error] listSkills failed:', err.message);
    return [];
  }
}

export async function createSkill(skillData) {
  try {
    const skillId = skillData.skill_id || `skill_${Date.now().toString(36)}`;
    const slug = skillData.slug || (skillData.name || '').toLowerCase().replace(/[^a-z0-9]/g, '_').slice(0, 32);
    await query(
      `INSERT INTO fastagent_skills (skill_id, user_phone, name, slug, description, system_prompt, trigger_keywords, webhook_url, is_active)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, TRUE)`,
      [
        skillId,
        skillData.user_phone || 'GLOBAL',
        skillData.name,
        slug,
        skillData.description || '',
        skillData.system_prompt,
        skillData.trigger_keywords || '',
        skillData.webhook_url || null
      ]
    );
    return { success: true, skill_id: skillId };
  } catch (err) {
    console.error('[Database Error] createSkill failed:', err.message);
    return { success: false, error: err.message };
  }
}

export async function deleteSkill(skillId) {
  try {
    await query('DELETE FROM fastagent_skills WHERE skill_id = ?', [skillId]);
    return { success: true };
  } catch (err) {
    console.error('[Database Error] deleteSkill failed:', err.message);
    return { success: false, error: err.message };
  }
}

export async function findMatchingSkill(userPhone, text) {
  if (!text) return null;
  const skills = await listSkills(userPhone);
  const textLower = text.toLowerCase();

  for (const skill of skills) {
    if (skill.name && textLower.includes(skill.name.toLowerCase())) return skill;
    if (skill.slug && textLower.includes(skill.slug.toLowerCase())) return skill;
    if (skill.trigger_keywords) {
      const kws = skill.trigger_keywords.split(',').map(k => k.trim().toLowerCase()).filter(Boolean);
      for (const kw of kws) {
        if (textLower.includes(kw)) return skill;
      }
    }
  }
  return null;
}

export async function query(sql, params = []) {
  if (!pool) {
    return [];
  }
  try {
    const [rows] = await pool.query(sql, params);
    return rows;
  } catch (err) {
    return [];
  }
}

export async function getSetting(key, defaultValue = null) {
  try {
    const rows = await query('SELECT value FROM system_settings WHERE key_name = ?', [key]);
    if (rows.length > 0) {
      return rows[0].value;
    }
    return defaultValue;
  } catch {
    return defaultValue;
  }
}

export async function setSetting(key, value) {
  try {
    const stringValue = typeof value === 'object' ? JSON.stringify(value) : String(value);
    await query(
      `INSERT INTO system_settings (key_name, value) VALUES (?, ?) 
       ON DUPLICATE KEY UPDATE value = ?`,
      [key, stringValue, stringValue]
    );
    return true;
  } catch (err) {
    console.error(`[Database Error] setSetting failed for ${key}:`, err.message);
    return false;
  }
}

export async function logActivity(module, message, level = 'INFO', metadata = null) {
  try {
    const metaJson = metadata ? JSON.stringify(metadata) : null;
    await query(
      'INSERT INTO activity_logs (module, message, level, metadata) VALUES (?, ?, ?, ?)',
      [module, message, level, metaJson]
    );
  } catch (err) {
    console.error(`[Activity Log Error]:`, err.message);
  }
}

export function getDbStatus() {
  return {
    connected: isConnected,
    host: dbConfig.host,
    port: dbConfig.port,
    database: dbConfig.database
  };
}
