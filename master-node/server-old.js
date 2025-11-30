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
    
} catch (error) {
    console.error('Error connecting to database:', error);
    process.exit(1);
}

const NODE_ID = uuidv4();
const NODE_PORT = process.env.NODE_PORT || 3000;
const NODE_ROLE = process.env.NODE_ROLE || 'MASTER';
const NODE_HOSTNAME = process.env.NODE_HOSTNAME || `master-node`;
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
    SET heartbeat_at = datetime('now'), latency_ms = ?, is_active = TRUE
    WHERE node_id = ?
`);

const insertHeartbeatStmt = db.prepare(`
    INSERT OR REPLACE INTO node_heartbeat (heartbeat_id, node_id, heartbeat_at, latency_ms)
    VALUES (?, ?, datetime('now'), ?)
`);

async function ensureStorageDirectory() {
    try {
        await fs.access(STORAGE_PATH);
    } catch {
        await fs.mkdir(STORAGE_PATH, { recursive: true });
    }
}

async function initialiseDB(){
    try {
        await ensureStorageDirectory();
        
        const apiEndpoint = `http://${NODE_HOSTNAME}:${NODE_PORT}`;
        insertNodeStmt.run(NODE_ID, apiEndpoint, NODE_ROLE, NODE_HOSTNAME, true);
        
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

async function heartbeat(){
    try{
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

const getCapacityStmt = db.prepare(`SELECT total_bytes FROM node_capacity WHERE node_id = ?`);
const updateCapacityStmt = db.prepare(`
    UPDATE node_capacity 
    SET used_bytes = ?, available_bytes = ?, updated_at = datetime('now')
    WHERE node_id = ?
`);

async function updateCapacity(){
    try {
        const files = await fs.readdir(STORAGE_PATH);
        let usedBytes = 0;
        for (const file of files){
            const stats = await fs.stat(path.join(STORAGE_PATH, file));
            usedBytes += stats.size;
        }
        const capacityResult = getCapacityStmt.get(NODE_ID);
        const totalBytes = capacityResult?.total_bytes || 12 * 1024 * 1024 * 1024;
        const availableBytes = totalBytes - usedBytes;

        updateCapacityStmt.run(usedBytes, availableBytes, NODE_ID);

        console.log(`Master Node ${NODE_ID} capacity updated.`);
        console.log(`Available Bytes: ${availableBytes}`);
        console.log(`Used Bytes: ${usedBytes}`);
    } catch (error) {
        console.error('Error updating master node capacity:', error);
    }
}

app.get('/health', (req, res) => {
    res.json({
        status: 'Healthy',
        nodeId: NODE_ID,
        hostname: NODE_HOSTNAME,
        role: NODE_ROLE,
    });
});

app.post('/fragments', async (req, res) => {
    try {
        try {
            const { fragmentId, data, bytes, contentHash } = req.body;
            if (!fragmentId || !data) {
                return res.status(400).json({ error: 'Missing fragmentId or data' });
            }
        } catch (error) {
            console.error('Error processing fragment:', error);
            return res.status(500).json({ error: 'Internal server error' });
        }
    const fragmentPath = path.join(STORAGE_PATH, `${fragmentId}.bin`);
    await fs.writeFile(fragmentPath, Buffer.from(data, 'base64'));
    await pool.query(`
        INSERT INTO FRAGMENT_LOCATION(FRAGMENT_ID, NODE_ID, FRAGMENT_ADDRESS, STORED_AT, BYTES, LAST_CHECKED_AT)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP, $4, CURRENT_TIMESTAMP)
    `, [fragmentId, NODE_ID, fragmentPath, bytes || data.length]);
    await updateCapacity();
    res.json({
        success: true,
        fragmentId: fragmentId,
        nodeId: NODE_ID,
        path: fragmentPath
    });
    } catch (error) {
        console.error('Error storing fragment:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/fragments/fragments/:id', async (req, res) => {
    try {
        const {fragmentId} = req.params;
        const result = await pool.query(`
            SELECT FRAGMENT_ADDRESS FROM FRAGMENT_LOCATION
            WHERE FRAGMENT_ID = $1 AND NODE_ID = $2`,
            [fragmentId, NODE_ID]);
        if (result.rows.length === 0){
            return res.status(404).json({error: 'Fragment not found on this node'});
        }
        const {fragment_address, status} = result.rows[0];
        if (status !== 'ACTIVE'){
            return res.status(410).json({error: 'Fragment is inactive'});
        }
        const data = await fs.readFile(fragment_address);
        await pool.query(`
            UPDATE FRAGMENT_LOCATION
            SET LAST_CHECKED_AT = CURRENT_TIMESTAMP
            WHERE FRAGMENT_ID = $1 AND NODE_ID = $2
        `, [fragmentId, NODE_ID]);
        res.json({
            fragmentId: fragmentId,
            data: data.toString('base64'),
            bytes: data.length
        });
    } catch (error) {
        console.error('Error retrieving fragment:', error);
        res.status(500).json({error: 'Internal server error' });
    }
});

app.delete('/fragments/:fragmentsId', async (req, res) => {
    try{
        const {fragmentId} = req.params;

        const result = await pool.query(`
            SELECT FRAGMENT_ADDRESS FROM FRAGMENT_LOCATION
            WHERE FRAGMENT_ID = $1 AND NODE_ID = $2
        `, [fragmentId, NODE_ID]);
        if (result.rows.length === 0) {
            return res.status(404).json({error: 'Fragment not found on this node'});
        }
        const {fragment_address} = result.rows[0];
        await fs.unlink(fragment_address);
        await pool.query(`
            UPDATE FRAGMENT_LOCATION
            SET STATUS = 'INACTIVE',
            LAST_CHECKED_AT = CURRENT_TIMESTAMP
            WHERE FRAGMENT_ID = $1 AND NODE_ID = $2
        `, [fragmentId, NODE_ID]);
        await updateCapacity();
        res.json({
            success: true,
            fragmentId: fragmentId
        });
    } catch (error) {
        console.error('Error deleting fragment:', error);
        res.status(500).json({error: 'Internal server error'});
    }
});

app.get('/status', async (req, res) => {
    try {
        const capacityResult = await pool.query(`
            SELECT * FROM NODE_CAPACITY WHERE NODE_ID = $1
        `, [NODE_ID]);
        const nodeResult = await pool.query(`
            SELECT * FROM NODE WHERE NODE_ID = $1
        `, [NODE_ID]);
        res.json({
            node: nodeResult.rows[0],
            capacity: capacityResult.rows[0]
        });
    } catch (error) {
        console.error('Error retrieving node status:', error);
        res.status(500).json({error: 'Internal server error'});
    }
});

process.on('SIGTERM', async () => {
    console.log('Shutting down node...');
    try {
        await pool.query(`
            UPDATE NODE
            SET IS_ACTIVE = FALSE
            WHERE NODE_ID = $1
        `, [NODE_ID]);
    } catch (error) {
        console.error('Error shutting down node:', error);
    }
    process.exit(0);
});

async function startServer(){
    await initialiseDB();
    setInterval(heartbeat, HEARTBEAT_INTERVAL);
    setInterval(updateCapacity, HEARTBEAT_INTERVAL * 6);
    app.listen(NODE_PORT, '0.0.0.0', () => {
        console.log(`Node server running on port ${NODE_PORT}`);
    });
}

startServer().catch((error) => {
    console.error('Error starting node server:', error);
    process.exit(1);
});
