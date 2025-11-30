const express = require('express');
const Database = require('better-sqlite3');
const { v4: uuidv4 } = require('uuid');
const fs = require('fs').promises;
const path = require('path');
const app = express();

app.use(express.json());

// Initialize SQLite database
const dbPath = process.env.DB_PATH || '/data/master.db';
let db;

// Initialize database connection
try {
    db = new Database(dbPath);
    console.log(`Connected to SQLite database at: ${dbPath}`);
    
    // Enable foreign keys and WAL mode for better concurrency
    db.pragma('foreign_keys = ON');
    db.pragma('journal_mode = WAL');
    
    // Initialize database schema - Complete schema from Database.sql adapted for SQLite
    const initSQL = `
        -- Roles table
        CREATE TABLE IF NOT EXISTS roles (
            role_name TEXT PRIMARY KEY CHECK (role_name IN ('ADMIN', 'USER')),
            description TEXT
        );

        -- Account table (main user accounts)
        CREATE TABLE IF NOT EXISTS account (
            account_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            account_type TEXT NOT NULL CHECK (account_type IN ('FREE', 'PAID', 'SYSADMIN')) DEFAULT 'FREE'
        );

        -- Account roles (many-to-many)
        CREATE TABLE IF NOT EXISTS account_role (
            account_id TEXT REFERENCES account(account_id),
            role_name TEXT REFERENCES roles(role_name),
            PRIMARY KEY (account_id, role_name)
        );

        -- Paid account details
        CREATE TABLE IF NOT EXISTS paid_account (
            account_id TEXT PRIMARY KEY,
            storage_limit_gb INTEGER NOT NULL DEFAULT 30,
            monthly_cost REAL NOT NULL DEFAULT 10.00,
            start_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            renewal_date DATETIME NOT NULL,
            end_date DATETIME, -- NULL if active
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'CANCELLED', 'EXPIRED')) DEFAULT 'ACTIVE',
            FOREIGN KEY (account_id) REFERENCES account(account_id) ON DELETE CASCADE
        );

        -- Free account details
        CREATE TABLE IF NOT EXISTS free_account (
            account_id TEXT PRIMARY KEY,
            storage_limit_gb INTEGER NOT NULL DEFAULT 2,
            FOREIGN KEY (account_id) REFERENCES account(account_id) ON DELETE CASCADE
        );

        -- Folder hierarchy
        CREATE TABLE IF NOT EXISTS folder (
            folder_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            account_id TEXT NOT NULL,
            parent_folder_id TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES account(account_id) ON DELETE CASCADE,
            FOREIGN KEY (parent_folder_id) REFERENCES folder(folder_id) ON DELETE CASCADE
        );

        -- System admin accounts
        CREATE TABLE IF NOT EXISTS sysadmin_account (
            account_id TEXT PRIMARY KEY,
            FOREIGN KEY (account_id) REFERENCES account(account_id) ON DELETE CASCADE
        );

        -- Erasure coding profiles
        CREATE TABLE IF NOT EXISTS erasure_profile (
            erasure_id TEXT PRIMARY KEY CHECK (erasure_id IN ('LOW', 'MEDIUM', 'HIGH')) DEFAULT 'MEDIUM',
            k INTEGER NOT NULL,
            m INTEGER NOT NULL,
            bytes INTEGER NOT NULL,
            notes TEXT
        );

        -- Account erasure coding settings
        CREATE TABLE IF NOT EXISTS account_erasure (
            account_id TEXT PRIMARY KEY,
            erasure_id TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES account(account_id) ON DELETE CASCADE,
            FOREIGN KEY (erasure_id) REFERENCES erasure_profile(erasure_id)
        );

        -- File objects (high-level file metadata)
        CREATE TABLE IF NOT EXISTS file_objects (
            file_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size BIGINT NOT NULL,
            uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            logical_path TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES account(account_id)
        );

        -- File versions
        CREATE TABLE IF NOT EXISTS file_versions (
            version_id TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            erasure_id TEXT NOT NULL,
            bytes BIGINT NOT NULL,
            content_hash TEXT NOT NULL,
            uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (file_id) REFERENCES file_objects(file_id) ON DELETE CASCADE,
            FOREIGN KEY (erasure_id) REFERENCES erasure_profile(erasure_id)
        );

        -- File segments
        CREATE TABLE IF NOT EXISTS file_segments (
            segment_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            erasure_id TEXT NOT NULL,
            num_segment INTEGER NOT NULL,
            bytes BIGINT NOT NULL,
            content_hash TEXT NOT NULL,
            stored_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (version_id) REFERENCES file_versions(version_id) ON DELETE CASCADE,
            FOREIGN KEY (erasure_id) REFERENCES erasure_profile(erasure_id)
        );

        -- File fragments
        CREATE TABLE IF NOT EXISTS file_fragments (
            fragment_id TEXT PRIMARY KEY,
            segment_id TEXT NOT NULL,
            num_fragment INTEGER NOT NULL,
            bytes BIGINT NOT NULL,
            content_hash TEXT NOT NULL,
            stored_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (segment_id) REFERENCES file_segments(segment_id) ON DELETE CASCADE
        );

        -- Nodes table
        CREATE TABLE IF NOT EXISTS node (
            node_id TEXT PRIMARY KEY,
            api_endpoint TEXT NOT NULL,
            node_role TEXT NOT NULL CHECK (node_role IN ('STORAGE', 'MASTER', 'FOLLOWER')),
            hostname TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            uptimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            heartbeat_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            latency_ms INTEGER NOT NULL DEFAULT 0
        );

        -- Node heartbeat history
        CREATE TABLE IF NOT EXISTS node_heartbeat (
            heartbeat_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            uptimed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            heartbeat_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (node_id) REFERENCES node(node_id)
        );

        -- Node capacity
        CREATE TABLE IF NOT EXISTS node_capacity (
            node_id TEXT PRIMARY KEY,
            total_bytes BIGINT NOT NULL,
            used_bytes BIGINT NOT NULL,
            available_bytes BIGINT NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES node(node_id)
        );

        -- Fragment locations
        CREATE TABLE IF NOT EXISTS fragment_location (
            fragment_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            fragment_address TEXT NOT NULL,
            stored_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            bytes BIGINT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE')) DEFAULT 'ACTIVE',
            last_checked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (fragment_id) REFERENCES file_fragments(fragment_id) ON DELETE CASCADE,
            FOREIGN KEY (node_id) REFERENCES node(node_id) ON DELETE CASCADE
        );

        -- File encryption keys
        CREATE TABLE IF NOT EXISTS file_keys (
            key_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            encryption_key TEXT NOT NULL,
            key_created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (version_id) REFERENCES file_versions(version_id) ON DELETE CASCADE
        );

        -- Key shares (for distributed key management)
        CREATE TABLE IF NOT EXISTS key_share (
            key_id TEXT PRIMARY KEY,
            key_share_id BIGINT NOT NULL,
            node_id TEXT NOT NULL,
            share_bytes BIGINT NOT NULL,
            share_address TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (key_id) REFERENCES file_keys(key_id) ON DELETE CASCADE,
            FOREIGN KEY (node_id) REFERENCES node(node_id) ON DELETE CASCADE
        );

        -- Repair jobs
        CREATE TABLE IF NOT EXISTS repair_jobs (
            job_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY (version_id) REFERENCES file_versions(version_id) ON DELETE CASCADE
        );

        -- Workers for repair jobs
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            fragment_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ASSIGNED', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
            assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            FOREIGN KEY (job_id) REFERENCES repair_jobs(job_id) ON DELETE CASCADE,
            FOREIGN KEY (fragment_id) REFERENCES file_fragments(fragment_id) ON DELETE CASCADE,
            FOREIGN KEY (node_id) REFERENCES node(node_id) ON DELETE CASCADE
        );

        -- Create indexes for better performance
        CREATE INDEX IF NOT EXISTS idx_folder_account ON folder(account_id);
        CREATE INDEX IF NOT EXISTS idx_folder_parent ON folder(parent_folder_id);
        CREATE INDEX IF NOT EXISTS idx_file_objects_account_id ON file_objects(account_id);
        CREATE INDEX IF NOT EXISTS idx_file_versions_file_id ON file_versions(file_id);
        CREATE INDEX IF NOT EXISTS idx_file_segments_version_id ON file_segments(version_id);
        CREATE INDEX IF NOT EXISTS idx_file_fragments_segment_id ON file_fragments(segment_id);
        CREATE INDEX IF NOT EXISTS idx_fragment_location_node_id ON fragment_location(node_id);
        CREATE INDEX IF NOT EXISTS idx_file_keys_version_id ON file_keys(version_id);
        CREATE INDEX IF NOT EXISTS idx_key_share_node_id ON key_share(node_id);
        CREATE INDEX IF NOT EXISTS idx_repair_jobs_version_id ON repair_jobs(version_id);
        CREATE INDEX IF NOT EXISTS idx_workers_job_id ON workers(job_id);
        CREATE INDEX IF NOT EXISTS idx_workers_fragment_id ON workers(fragment_id);
        CREATE INDEX IF NOT EXISTS idx_workers_node_id ON workers(node_id);
    `;
    
    db.exec(initSQL);
    console.log('Database schema initialized');
    
    // Insert initial seed data
    const seedSQL = `
        -- Insert default roles
        INSERT OR IGNORE INTO roles(role_name, description) VALUES 
        ('ADMIN', 'Administrator role'),
        ('USER', 'Standard user role');

        -- Insert default erasure profiles
        INSERT OR IGNORE INTO erasure_profile (erasure_id, k, m, bytes, notes) VALUES
        ('LOW', 4, 2, 1024, 'Low redundancy'),
        ('MEDIUM', 6, 3, 2048, 'Medium redundancy'),
        ('HIGH', 8, 4, 4096, 'High redundancy');
    `;
    
    db.exec(seedSQL);
    console.log('Seed data initialized');

} catch (error) {
    console.error('Error connecting to database:', error);
    process.exit(1);
}

const NODE_ID = uuidv4();
const NODE_PORT = process.env.NODE_PORT || 3000;
const NODE_ROLE = 'MASTER';
const NODE_HOSTNAME = process.env.NODE_HOSTNAME || 'master-node';
const STORAGE_PATH = process.env.STORAGE_PATH || '/data/storage';
const HEARTBEAT_INTERVAL = parseInt(process.env.HEARTBEAT_INTERVAL) || 10000;

// Prepared statements for better performance
const insertNodeStmt = db.prepare(`
    INSERT OR REPLACE INTO node (
        node_id, api_endpoint, node_role, hostname, is_active, uptimed_at, heartbeat_at
    ) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
`);

const insertCapacityStmt = db.prepare(`
    INSERT OR REPLACE INTO node_capacity (node_id, total_bytes, used_bytes, available_bytes, updated_at)
    VALUES (?, ?, 0, ?, datetime('now'))
`);

const updateHeartbeatStmt = db.prepare(`
    UPDATE node 
    SET heartbeat_at = datetime('now'), latency_ms = ?, is_active = 1
    WHERE node_id = ?
`);

const insertHeartbeatStmt = db.prepare(`
    INSERT OR REPLACE INTO node_heartbeat (heartbeat_id, node_id, heartbeat_at, latency_ms)
    VALUES (?, ?, datetime('now'), ?)
`);

const getCapacityStmt = db.prepare(`SELECT total_bytes FROM node_capacity WHERE node_id = ?`);

const updateCapacityStmt = db.prepare(`
    UPDATE node_capacity 
    SET used_bytes = ?, available_bytes = ?, updated_at = datetime('now')
    WHERE node_id = ?
`);

// New prepared statements for complete schema
const insertAccountStmt = db.prepare(`
    INSERT INTO account (account_id, username, email, password_hash, account_type)
    VALUES (?, ?, ?, ?, ?)
`);

const insertFreeAccountStmt = db.prepare(`
    INSERT INTO free_account (account_id, storage_limit_gb)
    VALUES (?, ?)
`);

const insertAccountRoleStmt = db.prepare(`
    INSERT INTO account_role (account_id, role_name)
    VALUES (?, ?)
`);

const insertFileObjectStmt = db.prepare(`
    INSERT INTO file_objects (file_id, account_id, file_name, file_size, logical_path)
    VALUES (?, ?, ?, ?, ?)
`);

const insertFileVersionStmt = db.prepare(`
    INSERT INTO file_versions (version_id, file_id, erasure_id, bytes, content_hash)
    VALUES (?, ?, ?, ?, ?)
`);

const insertFileSegmentStmt = db.prepare(`
    INSERT INTO file_segments (segment_id, version_id, erasure_id, num_segment, bytes, content_hash)
    VALUES (?, ?, ?, ?, ?, ?)
`);

const insertFileFragmentStmt = db.prepare(`
    INSERT INTO file_fragments (fragment_id, segment_id, num_fragment, bytes, content_hash)
    VALUES (?, ?, ?, ?, ?)
`);

const insertFragmentLocationStmt = db.prepare(`
    INSERT INTO fragment_location (fragment_id, node_id, fragment_address, bytes, status)
    VALUES (?, ?, ?, ?, 'ACTIVE')
`);

const getAccountStmt = db.prepare(`
    SELECT account_id, username, email, account_type FROM account WHERE username = ? OR email = ?
`);

const getStorageNodesStmt = db.prepare(`
    SELECT node_id, api_endpoint, hostname FROM node WHERE node_role = 'STORAGE' AND is_active = 1
`);

const getErasureProfileStmt = db.prepare(`
    SELECT k, m, bytes FROM erasure_profile WHERE erasure_id = ?
`);

// Now create comprehensive seed data using the prepared statements
try {
    // Insert system admin account
    const adminId = uuidv4();
    insertAccountStmt.run(adminId, 'admin', 'admin@system.com', 'hashed_admin_password', 'SYSADMIN');
    insertAccountRoleStmt.run(adminId, 'ADMIN');
    
    // Insert test free user account
    const testUserId = uuidv4();
    insertAccountStmt.run(testUserId, 'testuser', 'testuser@example.com', 'testpassword', 'FREE');
    insertAccountRoleStmt.run(testUserId, 'USER');
    insertFreeAccountStmt.run(testUserId, 2); // 2GB limit
    
    // Insert demo free user
    const demoUserId = uuidv4();
    insertAccountStmt.run(demoUserId, 'demo', 'demo@example.com', 'demopassword', 'FREE');
    insertAccountRoleStmt.run(demoUserId, 'USER');
    insertFreeAccountStmt.run(demoUserId, 2); // 2GB limit
    
    // Insert premium user
    const premiumUserId = uuidv4();
    insertAccountStmt.run(premiumUserId, 'premium_user', 'premium@example.com', 'premiumpassword', 'PAID');
    insertAccountRoleStmt.run(premiumUserId, 'USER');
    
    // Insert paid account details for premium user
    const renewalDate = new Date();
    renewalDate.setMonth(renewalDate.getMonth() + 1);
    db.prepare(`
        INSERT OR IGNORE INTO paid_account (account_id, storage_limit_gb, monthly_cost, renewal_date, status)
        VALUES (?, ?, ?, ?, ?)
    `).run(premiumUserId, 100, 15.99, renewalDate.toISOString(), 'ACTIVE');
    
    // Insert account erasure preferences
    db.prepare(`INSERT OR IGNORE INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(adminId, 'HIGH');
    db.prepare(`INSERT OR IGNORE INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(testUserId, 'MEDIUM');
    db.prepare(`INSERT OR IGNORE INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(demoUserId, 'LOW');
    db.prepare(`INSERT OR IGNORE INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(premiumUserId, 'HIGH');
    
    // Create sample folders for test users
    const createFolderStmt = db.prepare(`
        INSERT OR IGNORE INTO folder (folder_id, name, account_id, parent_folder_id)
        VALUES (?, ?, ?, ?)
    `);
    
    // Test user folders
    const documentsId = uuidv4();
    const imagesId = uuidv4();
    const videosId = uuidv4();
    createFolderStmt.run(documentsId, 'Documents', testUserId, null);
    createFolderStmt.run(imagesId, 'Images', testUserId, null);
    createFolderStmt.run(videosId, 'Videos', testUserId, null);
    
    // Demo user folders
    const demoDocsId = uuidv4();
    const demoProjectsId = uuidv4();
    createFolderStmt.run(demoDocsId, 'My Documents', demoUserId, null);
    createFolderStmt.run(demoProjectsId, 'Projects', demoUserId, null);
    
    // Premium user folders
    const premiumDocsId = uuidv4();
    const premiumBackupsId = uuidv4();
    const premiumMediaId = uuidv4();
    createFolderStmt.run(premiumDocsId, 'Documents', premiumUserId, null);
    createFolderStmt.run(premiumBackupsId, 'Backups', premiumUserId, null);
    createFolderStmt.run(premiumMediaId, 'Media Library', premiumUserId, null);
    
    // Create some sample file records
    const sampleFiles = [
        { name: 'README.txt', size: 2048, account: testUserId },
        { name: 'demo_presentation.pptx', size: 5242880, account: demoUserId },
        { name: 'backup_data.zip', size: 104857600, account: premiumUserId }
    ];
    
    for (const file of sampleFiles) {
        const fileId = uuidv4();
        const versionId = uuidv4();
        insertFileObjectStmt.run(fileId, file.account, file.name, file.size, `/${file.name}`);
        insertFileVersionStmt.run(versionId, fileId, 'MEDIUM', file.size, `sha256_${fileId}`);
    }
    
    console.log('Comprehensive seed data created:');
    console.log('- 4 accounts (1 admin, 3 users with different tiers)');
    console.log('- Account erasure preferences configured');
    console.log('- Sample folder structures created');
    console.log('- Premium account with paid subscription setup');
    console.log('- Sample file metadata created');
    
} catch (error) {
    console.log('Seed data already exists or error creating them:', error.message);
}

async function ensureStorageDirectory() {
    try {
        await fs.access(STORAGE_PATH);
    } catch {
        await fs.mkdir(STORAGE_PATH, { recursive: true });
    }
}

async function initialiseDB() {
    try {
        await ensureStorageDirectory();
        
        const apiEndpoint = `http://${NODE_HOSTNAME}:${NODE_PORT}`;
        insertNodeStmt.run(NODE_ID, apiEndpoint, NODE_ROLE, NODE_HOSTNAME, 1); // 1 instead of true
        
        const totalBytes = 12 * 1024 * 1024 * 1024; // 12 GB
        insertCapacityStmt.run(NODE_ID, totalBytes, totalBytes);
        
        console.log(`Master Node ${NODE_ID} initialized in database.`);
        console.log('Hostname:', NODE_HOSTNAME);
        console.log('Role:', NODE_ROLE);
        console.log('Storage Path:', STORAGE_PATH);
    } catch (error) {
        console.error('Error initializing master node in database:', error);
        process.exit(1);
    }
}

async function heartbeat() {
    try {
        const initTime = Date.now();
        const latency = Date.now() - initTime;
        
        updateHeartbeatStmt.run(latency, NODE_ID);
        insertHeartbeatStmt.run(uuidv4(), NODE_ID, latency);
        
        console.log('Heartbeat sent for master node', NODE_ID);
        console.log('Heartbeat latency (ms):', latency);
        console.log(`Sent at: ${new Date().toISOString()}`);
    } catch (error) {
        console.error('Error sending heartbeat:', error);
    }
}

async function updateCapacity() {
    try {
        const files = await fs.readdir(STORAGE_PATH);
        let usedBytes = 0;
        
        for (const file of files) {
            const stats = await fs.stat(path.join(STORAGE_PATH, file));
            usedBytes += stats.size;
        }
        
        const capacityResult = getCapacityStmt.get(NODE_ID);
        const totalBytes = capacityResult?.total_bytes || 12 * 1024 * 1024 * 1024;
        const availableBytes = totalBytes - usedBytes;
        
        updateCapacityStmt.run(usedBytes, availableBytes, NODE_ID);
        
        console.log(`Master Node ${NODE_ID} capacity updated.`);
        console.log('Available Bytes:', availableBytes);
        console.log('Used Bytes:', usedBytes);
    } catch (error) {
        console.error('Error updating capacity:', error);
    }
}

// API endpoints
app.get('/health', (req, res) => {
    res.json({
        status: 'Healthy',
        nodeId: NODE_ID,
        hostname: NODE_HOSTNAME,
        role: NODE_ROLE,
        database: 'SQLite'
    });
});

// Storage nodes register with master node
app.post('/register-node', (req, res) => {
    try {
        const { nodeId, apiEndpoint, nodeRole, hostname } = req.body;
        
        if (!nodeId || !apiEndpoint || !nodeRole || !hostname) {
            return res.status(400).json({ error: 'Missing required fields' });
        }
        
        insertNodeStmt.run(nodeId, apiEndpoint, nodeRole, hostname, 1); // 1 instead of true
        
        // Set default capacity for storage nodes
        if (nodeRole === 'STORAGE') {
            const defaultCapacity = 100 * 1024 * 1024 * 1024; // 100GB
            insertCapacityStmt.run(nodeId, defaultCapacity, defaultCapacity);
        }
        
        console.log(`Node ${nodeId} registered as ${nodeRole}`);
        res.json({ success: true, message: 'Node registered successfully' });
    } catch (error) {
        console.error('Error registering node:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Storage nodes send heartbeats to master node
app.post('/node-heartbeat', (req, res) => {
    try {
        const { nodeId, latency } = req.body;
        
        if (!nodeId) {
            return res.status(400).json({ error: 'Missing nodeId' });
        }
        
        const heartbeatLatency = latency || 0;
        updateHeartbeatStmt.run(heartbeatLatency, nodeId);
        insertHeartbeatStmt.run(uuidv4(), nodeId, heartbeatLatency);
        
        res.json({ success: true, message: 'Heartbeat recorded' });
    } catch (error) {
        console.error('Error recording heartbeat:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Storage nodes update their capacity
app.post('/update-capacity', (req, res) => {
    try {
        const { nodeId, totalBytes, usedBytes, availableBytes } = req.body;
        
        if (!nodeId) {
            return res.status(400).json({ error: 'Missing nodeId' });
        }
        
        updateCapacityStmt.run(usedBytes || 0, availableBytes || totalBytes, nodeId);
        
        res.json({ success: true, message: 'Capacity updated' });
    } catch (error) {
        console.error('Error updating capacity:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Get all nodes
app.get('/nodes', (req, res) => {
    try {
        const nodes = db.prepare(`
            SELECT n.*, c.total_bytes, c.used_bytes, c.available_bytes 
            FROM node n 
            LEFT JOIN node_capacity c ON n.node_id = c.node_id 
            ORDER BY n.node_role, n.hostname
        `).all();
        
        res.json(nodes);
    } catch (error) {
        console.error('Error retrieving nodes:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Database query endpoint for backend
app.post('/query', (req, res) => {
    try {
        const { sql, params = [] } = req.body;
        
        console.log('Received query request:');
        console.log('SQL:', sql);
        console.log('Params:', params);
        
        if (!sql) {
            return res.status(400).json({ error: 'SQL query required' });
        }
        
        // Basic safety check - only allow SELECT, INSERT, UPDATE, DELETE
        const sqlLower = sql.trim().toLowerCase();
        if (!sqlLower.startsWith('select') && 
            !sqlLower.startsWith('insert') && 
            !sqlLower.startsWith('update') && 
            !sqlLower.startsWith('delete')) {
            return res.status(400).json({ error: 'Only SELECT, INSERT, UPDATE, DELETE queries allowed' });
        }
        
        let result;
        if (sqlLower.startsWith('select')) {
            result = db.prepare(sql).all(...params);
        } else {
            result = db.prepare(sql).run(...params);
        }
        
        res.json({ success: true, data: result });
    } catch (error) {
        console.error('Error executing query:', error);
        res.status(500).json({ error: 'Database query error', details: error.message });
    }
});

// File fragment management
app.post('/fragments', async (req, res) => {
    try {
        const { fileId, nodeId, fragmentOrder, fragmentSize, fragmentHash } = req.body;
        const fragmentId = uuidv4();
        
        db.prepare(`
            INSERT INTO file_fragments (fragment_id, file_id, node_id, fragment_order, fragment_size, fragment_hash)
            VALUES (?, ?, ?, ?, ?, ?)
        `).run(fragmentId, fileId, nodeId, fragmentOrder, fragmentSize, fragmentHash);
        
        res.json({ success: true, fragmentId });
    } catch (error) {
        console.error('Error storing fragment info:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/fragments/:fileId', (req, res) => {
    try {
        const { fileId } = req.params;
        const fragments = db.prepare(`
            SELECT ff.*, n.api_endpoint, n.hostname 
            FROM file_fragments ff 
            JOIN node n ON ff.node_id = n.node_id 
            WHERE ff.file_id = ? 
            ORDER BY ff.fragment_order
        `).all(fileId);
        
        res.json(fragments);
    } catch (error) {
        console.error('Error retrieving fragments:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// =================== NEW ADVANCED API ENDPOINTS ===================

// Account management endpoints
app.post('/accounts', (req, res) => {
    try {
        const { username, email, password_hash, account_type = 'FREE' } = req.body;
        
        if (!username || !email || !password_hash) {
            return res.status(400).json({ error: 'Missing required fields' });
        }
        
        const accountId = uuidv4();
        
        // Insert account
        insertAccountStmt.run(accountId, username, email, password_hash, account_type);
        
        // Create account-specific records
        if (account_type === 'FREE') {
            insertFreeAccountStmt.run(accountId, 2); // 2GB default
        }
        
        // Assign default role
        insertAccountRoleStmt.run(accountId, account_type === 'SYSADMIN' ? 'ADMIN' : 'USER');
        
        res.json({ success: true, accountId, message: 'Account created successfully' });
    } catch (error) {
        console.error('Error creating account:', error);
        if (error.code === 'SQLITE_CONSTRAINT') {
            res.status(409).json({ error: 'Username or email already exists' });
        } else {
            res.status(500).json({ error: 'Internal server error' });
        }
    }
});

app.get('/accounts/:username', (req, res) => {
    try {
        const { username } = req.params;
        const account = getAccountStmt.get(username, username);
        
        if (!account) {
            return res.status(404).json({ error: 'Account not found' });
        }
        
        res.json(account);
    } catch (error) {
        console.error('Error retrieving account:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// File management with new schema
app.post('/files', (req, res) => {
    try {
        const { account_id, file_name, file_size, logical_path, erasure_id = 'MEDIUM' } = req.body;
        
        if (!account_id || !file_name || !file_size || !logical_path) {
            return res.status(400).json({ error: 'Missing required fields' });
        }
        
        const fileId = uuidv4();
        const versionId = uuidv4();
        const contentHash = 'temp_hash_' + Date.now(); // Replace with actual hash
        
        // Insert file object
        insertFileObjectStmt.run(fileId, account_id, file_name, file_size, logical_path);
        
        // Insert file version
        insertFileVersionStmt.run(versionId, fileId, erasure_id, file_size, contentHash);
        
        res.json({ 
            success: true, 
            fileId, 
            versionId,
            message: 'File metadata created successfully' 
        });
    } catch (error) {
        console.error('Error creating file metadata:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Advanced fragment management
app.post('/file-fragments', (req, res) => {
    try {
        console.log('=== FRAGMENT DISTRIBUTION REQUEST ===');
        console.log('Request body:', JSON.stringify(req.body, null, 2));
        
        const { 
            version_id, 
            segment_id, 
            fragment_data, 
            erasure_id = 'MEDIUM' 
        } = req.body;
        
        console.log('Extracted values:', { version_id, segment_id, fragment_data_length: fragment_data?.length, erasure_id });
        
        if (!version_id || !fragment_data || !Array.isArray(fragment_data)) {
            console.log('Missing required fields validation failed');
            return res.status(400).json({ error: 'Missing required fields' });
        }
        
        const results = [];
        
        // Get available storage nodes
        const storageNodes = getStorageNodesStmt.all();
        console.log('Available storage nodes:', storageNodes.length);
        
        if (storageNodes.length === 0) {
            console.log('No storage nodes available');
            return res.status(503).json({ error: 'No storage nodes available' });
        }
        
        // Create segment record first (required for foreign key constraint)
        const actualSegmentId = segment_id || uuidv4();
        
        // Calculate total bytes and content hash for the segment
        const totalBytes = fragment_data.reduce((sum, fragment) => sum + (fragment.bytes || 0), 0);
        const segmentContentHash = require('crypto').createHash('sha256')
            .update(fragment_data.map(f => f.content_hash || '').join(''))
            .digest('hex');
        
        console.log('Creating segment record:', {
            segment_id: actualSegmentId,
            version_id,
            erasure_id,
            totalBytes,
            segmentContentHash
        });
        
        // Insert segment record
        insertFileSegmentStmt.run(
            actualSegmentId,
            version_id,
            erasure_id,
            0, // num_segment - for single segment files
            totalBytes,
            segmentContentHash
        );
        
        // Process each fragment
        for (let i = 0; i < fragment_data.length; i++) {
            const fragment = fragment_data[i];
            const fragmentId = uuidv4();
            const nodeId = storageNodes[i % storageNodes.length].node_id; // Round-robin distribution
            const fragmentAddress = `/storage/fragments/${fragmentId}`;
            
            console.log(`Processing fragment ${i}:`, {
                fragmentId,
                nodeId,
                segment_id: actualSegmentId,
                num_fragment: fragment.num_fragment || i,
                bytes: fragment.bytes,
                content_hash: fragment.content_hash || 'temp_hash'
            });
            
            // Insert fragment metadata
            insertFileFragmentStmt.run(
                fragmentId, 
                actualSegmentId, 
                fragment.num_fragment || i, 
                fragment.bytes, 
                fragment.content_hash || 'temp_hash'
            );
            
            // Insert fragment location
            insertFragmentLocationStmt.run(
                fragmentId, 
                nodeId, 
                fragmentAddress, 
                fragment.bytes
            );
            
            results.push({
                fragmentId,
                nodeId,
                nodeEndpoint: storageNodes.find(n => n.node_id === nodeId)?.api_endpoint,
                fragmentAddress
            });
        }
        
        console.log('Fragment distribution completed successfully');
        res.json({ 
            success: true, 
            fragments: results,
            message: 'Fragments distributed successfully' 
        });
    } catch (error) {
        console.error('Error distributing fragments:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Erasure coding profiles
app.get('/erasure-profiles', (req, res) => {
    try {
        const profiles = db.prepare(`SELECT * FROM erasure_profile`).all();
        res.json(profiles);
    } catch (error) {
        console.error('Error retrieving erasure profiles:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/erasure-profiles/:erasureId', (req, res) => {
    try {
        const { erasureId } = req.params;
        const profile = getErasureProfileStmt.get(erasureId);
        
        if (!profile) {
            return res.status(404).json({ error: 'Erasure profile not found' });
        }
        
        res.json(profile);
    } catch (error) {
        console.error('Error retrieving erasure profile:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// File retrieval with new schema
app.get('/files/:accountId', (req, res) => {
    try {
        const { accountId } = req.params;
        const files = db.prepare(`
            SELECT fo.*, fv.version_id, fv.erasure_id, fv.content_hash
            FROM file_objects fo
            JOIN file_versions fv ON fo.file_id = fv.file_id
            WHERE fo.account_id = ?
            ORDER BY fo.uploaded_at DESC
        `).all(accountId);
        
        res.json(files);
    } catch (error) {
        console.error('Error retrieving files:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Fragment locations for file reconstruction
app.get('/fragments/locations/:versionId', (req, res) => {
    try {
        const { versionId } = req.params;
        const fragments = db.prepare(`
            SELECT ff.fragment_id, ff.num_fragment, ff.bytes, 
                   fl.node_id, fl.fragment_address, 
                   n.api_endpoint, n.hostname
            FROM file_versions fv
            JOIN file_segments fs ON fv.version_id = fs.version_id
            JOIN file_fragments ff ON fs.segment_id = ff.segment_id
            JOIN fragment_location fl ON ff.fragment_id = fl.fragment_id
            JOIN node n ON fl.node_id = n.node_id
            WHERE fv.version_id = ? AND fl.status = 'ACTIVE' AND n.is_active = 1
            ORDER BY ff.num_fragment
        `).all(versionId);
        
        res.json(fragments);
    } catch (error) {
        console.error('Error retrieving fragment locations:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// =================== END NEW ENDPOINTS ===================

// Seed data management endpoint (for development/testing)
app.post('/admin/seed-data', (req, res) => {
    try {
        const { reset = false } = req.body;
        
        if (reset) {
            // Clear existing test data (but keep system accounts)
            db.prepare(`DELETE FROM fragment_location`).run();
            db.prepare(`DELETE FROM file_fragments`).run();
            db.prepare(`DELETE FROM file_segments`).run();
            db.prepare(`DELETE FROM file_versions`).run();
            db.prepare(`DELETE FROM file_objects`).run();
            db.prepare(`DELETE FROM folder WHERE name != 'Root'`).run();
            db.prepare(`DELETE FROM account_erasure`).run();
            db.prepare(`DELETE FROM paid_account`).run();
            db.prepare(`DELETE FROM free_account`).run();
            db.prepare(`DELETE FROM account_role WHERE account_id NOT IN (SELECT account_id FROM account WHERE username = 'admin')`).run();
            db.prepare(`DELETE FROM account WHERE username != 'admin'`).run();
            console.log('Existing test data cleared');
        }
        
        // Create sample test data
        const seedResults = {
            accounts: 0,
            folders: 0,
            sampleFiles: 0
        };
        
        // Create test accounts if they don't exist
        const existingUsers = db.prepare(`SELECT username FROM account WHERE username IN ('testuser', 'demo', 'premium_user')`).all();
        const existingUsernames = existingUsers.map(u => u.username);
        
        if (!existingUsernames.includes('testuser')) {
            const testUserId = uuidv4();
            insertAccountStmt.run(testUserId, 'testuser', 'testuser@example.com', 'testpassword', 'FREE');
            insertAccountRoleStmt.run(testUserId, 'USER');
            insertFreeAccountStmt.run(testUserId, 2);
            db.prepare(`INSERT INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(testUserId, 'MEDIUM');
            seedResults.accounts++;
        }
        
        if (!existingUsernames.includes('demo')) {
            const demoUserId = uuidv4();
            insertAccountStmt.run(demoUserId, 'demo', 'demo@example.com', 'demopassword', 'FREE');
            insertAccountRoleStmt.run(demoUserId, 'USER');
            insertFreeAccountStmt.run(demoUserId, 2);
            db.prepare(`INSERT INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(demoUserId, 'LOW');
            seedResults.accounts++;
        }
        
        if (!existingUsernames.includes('premium_user')) {
            const premiumUserId = uuidv4();
            insertAccountStmt.run(premiumUserId, 'premium_user', 'premium@example.com', 'premiumpass', 'PAID');
            insertAccountRoleStmt.run(premiumUserId, 'USER');
            
            const renewalDate = new Date();
            renewalDate.setMonth(renewalDate.getMonth() + 1);
            db.prepare(`INSERT INTO paid_account (account_id, storage_limit_gb, monthly_cost, renewal_date, status) VALUES (?, ?, ?, ?, ?)`).run(
                premiumUserId, 100, 15.99, renewalDate.toISOString(), 'ACTIVE'
            );
            db.prepare(`INSERT INTO account_erasure (account_id, erasure_id) VALUES (?, ?)`).run(premiumUserId, 'HIGH');
            seedResults.accounts++;
        }
        
        // Create sample folders for each user
        const users = db.prepare(`SELECT account_id, username FROM account WHERE username IN ('testuser', 'demo', 'premium_user')`).all();
        
        for (const user of users) {
            const folderNames = user.username === 'premium_user' ? 
                ['Documents', 'Backups', 'Media Library', 'Projects'] :
                ['Documents', 'Images', user.username === 'demo' ? 'Demo Files' : 'Personal'];
                
            for (const folderName of folderNames) {
                const existingFolder = db.prepare(`SELECT folder_id FROM folder WHERE name = ? AND account_id = ?`).get(folderName, user.account_id);
                if (!existingFolder) {
                    const folderId = uuidv4();
                    db.prepare(`INSERT INTO folder (folder_id, name, account_id, parent_folder_id) VALUES (?, ?, ?, ?)`).run(
                        folderId, folderName, user.account_id, null
                    );
                    seedResults.folders++;
                }
            }
        }
        
        // Create sample file metadata (without actual file data)
        for (const user of users) {
            const sampleFiles = [
                { name: 'README.txt', size: 1024, type: 'text/plain' },
                { name: 'sample-image.jpg', size: 2048576, type: 'image/jpeg' },
                { name: 'document.pdf', size: 512000, type: 'application/pdf' }
            ];
            
            for (const fileInfo of sampleFiles) {
                const existingFile = db.prepare(`SELECT file_id FROM file_objects WHERE file_name = ? AND account_id = ?`).get(fileInfo.name, user.account_id);
                if (!existingFile) {
                    const fileId = uuidv4();
                    const versionId = uuidv4();
                    
                    insertFileObjectStmt.run(fileId, user.account_id, fileInfo.name, fileInfo.size, `/${fileInfo.name}`);
                    insertFileVersionStmt.run(versionId, fileId, 'MEDIUM', fileInfo.size, `hash_${fileId}`);
                    seedResults.sampleFiles++;
                }
            }
        }
        
        res.json({
            success: true,
            message: 'Seed data created successfully',
            results: seedResults,
            reset: reset
        });
        
    } catch (error) {
        console.error('Error creating seed data:', error);
        res.status(500).json({ 
            error: 'Internal server error', 
            details: error.message 
        });
    }
});

// Get all accounts with details (for development/testing)
app.get('/admin/accounts', (req, res) => {
    try {
        const accounts = db.prepare(`
            SELECT 
                a.account_id, a.username, a.email, a.account_type, a.created_at,
                ar.role_name,
                ae.erasure_id,
                fa.storage_limit_gb as free_limit,
                pa.storage_limit_gb as paid_limit, pa.monthly_cost, pa.status as subscription_status
            FROM account a
            LEFT JOIN account_role ar ON a.account_id = ar.account_id
            LEFT JOIN account_erasure ae ON a.account_id = ae.account_id
            LEFT JOIN free_account fa ON a.account_id = fa.account_id
            LEFT JOIN paid_account pa ON a.account_id = pa.account_id
            ORDER BY a.created_at DESC
        `).all();
        
        res.json(accounts);
    } catch (error) {
        console.error('Error retrieving accounts:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Master node status
app.get('/status', (req, res) => {
    try {
        const nodeInfo = db.prepare(`
            SELECT n.*, c.total_bytes, c.used_bytes, c.available_bytes 
            FROM node n 
            LEFT JOIN node_capacity c ON n.node_id = c.node_id 
            WHERE n.node_id = ?
        `).get(NODE_ID);
        
        const stats = {
            accounts: db.prepare(`SELECT COUNT(*) as count FROM account`).get().count,
            files: db.prepare(`SELECT COUNT(*) as count FROM file_objects`).get().count,
            fragments: db.prepare(`SELECT COUNT(*) as count FROM file_fragments`).get().count,
            storage_nodes: db.prepare(`SELECT COUNT(*) as count FROM node WHERE node_role = 'STORAGE' AND is_active = 1`).get().count
        };
        
        res.json({
            master_node: nodeInfo,
            database: {
                type: 'SQLite',
                location: dbPath,
                status: 'active',
                schema_version: 'complete'
            },
            statistics: stats
        });
    } catch (error) {
        console.error('Error retrieving status:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

process.on('SIGTERM', async () => {
    console.log('Shutting down master node...');
    try {
        db.prepare(`UPDATE node SET is_active = 0 WHERE node_id = ?`).run(NODE_ID);
        db.close();
    } catch (error) {
        console.error('Error shutting down master node:', error);
    }
    process.exit(0);
});

async function startServer() {
    await initialiseDB();
    setInterval(heartbeat, HEARTBEAT_INTERVAL);
    setInterval(updateCapacity, HEARTBEAT_INTERVAL * 6);
    
    app.listen(NODE_PORT, '0.0.0.0', () => {
        console.log(`Master Node server with embedded database running on port ${NODE_PORT}`);
        console.log(`API available at: http://${NODE_HOSTNAME}:${NODE_PORT}`);
        console.log(`Database API at: http://${NODE_HOSTNAME}:${NODE_PORT}/query`);
        console.log(`Node registration: http://${NODE_HOSTNAME}:${NODE_PORT}/register-node`);
    });
}

startServer().catch((error) => {
    console.error('Error starting master node server:', error);
    process.exit(1);
});