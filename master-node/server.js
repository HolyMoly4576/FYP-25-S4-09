const express = require('express');
const { Pool } = require('pg');
const { v4: uuidv4 } = require('uuid');
const fs = require('fs').promises;
const path = require('path');
const app = express();

app.use(express.json());

// PostgreSQL connection pool
let pool;

// Initialize PostgreSQL database connection
try {
    const connectionString = process.env.DATABASE_URL || 
        `postgresql://${process.env.POSTGRES_USER || 'user'}:${process.env.POSTGRES_PASSWORD || 'password'}@${process.env.POSTGRES_HOST || 'postgres_db'}:${process.env.POSTGRES_PORT || 5432}/${process.env.POSTGRES_DB || 'database'}`;
    
    pool = new Pool({
        connectionString: connectionString,
        max: 20,
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: 2000,
    });
    
    console.log('Connected to PostgreSQL database');
    
    // Test connection
    pool.query('SELECT NOW()', (err, res) => {
        if (err) {
            console.error('Error connecting to PostgreSQL:', err);
            process.exit(1);
        } else {
            console.log('PostgreSQL connection successful:', res.rows[0]);
        }
    });
    
} catch (error) {
    console.error('Error initializing PostgreSQL connection:', error);
    process.exit(1);
}

// Helper function to execute queries
async function query(text, params) {
    const start = Date.now();
    try {
        const res = await pool.query(text, params);
        const duration = Date.now() - start;
        console.log('Executed query', { text, duration, rows: res.rowCount });
        return res;
    } catch (error) {
        console.error('Query error:', error);
        throw error;
    }
}

const NODE_ID = uuidv4();
const NODE_PORT = process.env.NODE_PORT || 3000;
const NODE_ROLE = 'MASTER';
const NODE_HOSTNAME = process.env.NODE_HOSTNAME || 'master-node';
const STORAGE_PATH = process.env.STORAGE_PATH || '/data/storage';
const HEARTBEAT_INTERVAL = parseInt(process.env.HEARTBEAT_INTERVAL) || 10000;

// Note: Database schema initialization should be done via Database.sql migration
// This file assumes the schema already exists in PostgreSQL

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
        
        // Insert or update master node record
        await query(`
            INSERT INTO node (node_id, api_endpoint, node_role, hostname, is_active, uptimed_at, heartbeat_at)
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            ON CONFLICT (node_id) DO UPDATE SET
                api_endpoint = EXCLUDED.api_endpoint,
                is_active = EXCLUDED.is_active,
                heartbeat_at = NOW()
        `, [NODE_ID, apiEndpoint, NODE_ROLE, NODE_HOSTNAME, true]);
        
        const totalBytes = 12 * 1024 * 1024 * 1024; // 12 GB
        
        // Insert or update capacity
        await query(`
            INSERT INTO node_capacity (node_id, total_bytes, used_bytes, available_bytes, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (node_id) DO UPDATE SET
                total_bytes = EXCLUDED.total_bytes,
                updated_at = NOW()
        `, [NODE_ID, totalBytes, 0, totalBytes]);
        
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
        
        await query(`
            UPDATE node 
            SET heartbeat_at = NOW(), latency_ms = $1, is_active = true
            WHERE node_id = $2
        `, [latency, NODE_ID]);
        
        await query(`
            INSERT INTO node_heartbeat (heartbeat_id, node_id, heartbeat_at, latency_ms)
            VALUES ($1, $2, NOW(), $3)
        `, [uuidv4(), NODE_ID, latency]);
        
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
        
        const capacityResult = await query('SELECT total_bytes FROM node_capacity WHERE node_id = $1', [NODE_ID]);
        const totalBytes = capacityResult.rows[0]?.total_bytes || 12 * 1024 * 1024 * 1024;
        const availableBytes = totalBytes - usedBytes;
        
        await query(`
            UPDATE node_capacity 
            SET used_bytes = $1, available_bytes = $2, updated_at = NOW()
            WHERE node_id = $3
        `, [usedBytes, availableBytes, NODE_ID]);
        
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
        database: 'PostgreSQL'
    });
});

// Storage nodes register with master node
app.post('/register-node', async (req, res) => {
    try {
        const { nodeId, apiEndpoint, nodeRole, hostname } = req.body;
        
        if (!nodeId || !apiEndpoint || !nodeRole || !hostname) {
            return res.status(400).json({ error: 'Missing required fields' });
        }
        
        await query(`
            INSERT INTO node (node_id, api_endpoint, node_role, hostname, is_active, uptimed_at, heartbeat_at)
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            ON CONFLICT (node_id) DO UPDATE SET
                api_endpoint = EXCLUDED.api_endpoint,
                node_role = EXCLUDED.node_role,
                hostname = EXCLUDED.hostname,
                is_active = EXCLUDED.is_active
        `, [nodeId, apiEndpoint, nodeRole, hostname, true]);
        
        // Set default capacity for storage nodes
        if (nodeRole === 'STORAGE') {
            const defaultCapacity = 100 * 1024 * 1024 * 1024; // 100GB
            await query(`
                INSERT INTO node_capacity (node_id, total_bytes, used_bytes, available_bytes, updated_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (node_id) DO UPDATE SET
                    total_bytes = EXCLUDED.total_bytes,
                    updated_at = NOW()
            `, [nodeId, defaultCapacity, 0, defaultCapacity]);
        }
        
        console.log(`Node ${nodeId} registered as ${nodeRole}`);
        res.json({ success: true, message: 'Node registered successfully' });
    } catch (error) {
        console.error('Error registering node:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Storage nodes send heartbeats to master node
app.post('/node-heartbeat', async (req, res) => {
    try {
        const { nodeId, latency } = req.body;
        
        if (!nodeId) {
            return res.status(400).json({ error: 'Missing nodeId' });
        }
        
        const heartbeatLatency = latency || 0;
        await query(`
            UPDATE node 
            SET heartbeat_at = NOW(), latency_ms = $1, is_active = true
            WHERE node_id = $2
        `, [heartbeatLatency, nodeId]);
        
        await query(`
            INSERT INTO node_heartbeat (heartbeat_id, node_id, heartbeat_at, latency_ms)
            VALUES ($1, $2, NOW(), $3)
        `, [uuidv4(), nodeId, heartbeatLatency]);
        
        res.json({ success: true, message: 'Heartbeat recorded' });
    } catch (error) {
        console.error('Error recording heartbeat:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Storage nodes update their capacity
app.post('/update-capacity', async (req, res) => {
    try {
        const { nodeId, totalBytes, usedBytes, availableBytes } = req.body;
        
        if (!nodeId) {
            return res.status(400).json({ error: 'Missing nodeId' });
        }
        
        await query(`
            UPDATE node_capacity 
            SET used_bytes = $1, available_bytes = $2, updated_at = NOW()
            WHERE node_id = $3
        `, [usedBytes || 0, availableBytes || totalBytes, nodeId]);
        
        res.json({ success: true, message: 'Capacity updated' });
    } catch (error) {
        console.error('Error updating capacity:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Get all nodes
app.get('/nodes', async (req, res) => {
    try {
        const result = await query(`
            SELECT n.*, c.total_bytes, c.used_bytes, c.available_bytes 
            FROM node n 
            LEFT JOIN node_capacity c ON n.node_id = c.node_id 
            ORDER BY n.node_role, n.hostname
        `);
        
        res.json(result.rows);
    } catch (error) {
        console.error('Error retrieving nodes:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Database query endpoint for backend (now just a passthrough since we all use PostgreSQL)
app.post('/query', async (req, res) => {
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
        
        const result = await query(sql, params);
        
        res.json({ success: true, data: result.rows || result });
    } catch (error) {
        console.error('Error executing query:', error);
        res.status(500).json({ error: 'Database query error', details: error.message });
    }
});

// File fragment management
// Note: Fragments are stored in FILE_FRAGMENTS (with segment_id) and FRAGMENT_LOCATION (with node_id)
// This endpoint is kept for backward compatibility but should use the proper schema
app.post('/fragments', async (req, res) => {
    try {
        const { segmentId, numFragment, bytes, contentHash, nodeId, fragmentAddress } = req.body;
        
        if (!segmentId || numFragment === undefined || !bytes || !contentHash) {
            return res.status(400).json({ error: 'Missing required fields: segmentId, numFragment, bytes, contentHash' });
        }
        
        const fragmentId = uuidv4();
        
        // Insert into file_fragments table
        await query(`
            INSERT INTO file_fragments (fragment_id, segment_id, num_fragment, bytes, content_hash)
            VALUES ($1, $2, $3, $4, $5)
        `, [fragmentId, segmentId, numFragment, bytes, contentHash]);
        
        // If nodeId and fragmentAddress provided, also insert into fragment_location
        if (nodeId && fragmentAddress) {
            await query(`
                INSERT INTO fragment_location (fragment_id, node_id, fragment_address, bytes, status)
                VALUES ($1, $2, $3, $4, 'ACTIVE')
            `, [fragmentId, nodeId, fragmentAddress, bytes]);
        }
        
        res.json({ success: true, fragmentId });
    } catch (error) {
        console.error('Error storing fragment info:', error);
        res.status(500).json({ error: 'Internal server error', details: error.message });
    }
});

// Get fragments by file_id (through segments and versions)
app.get('/fragments/:fileId', async (req, res) => {
    try {
        const { fileId } = req.params;
        const result = await query(`
            SELECT 
                ff.fragment_id, 
                ff.segment_id,
                ff.num_fragment, 
                ff.bytes, 
                ff.content_hash,
                fl.node_id, 
                fl.fragment_address,
                n.api_endpoint, 
                n.hostname 
            FROM file_objects fo
            JOIN file_versions fv ON fo.file_id = fv.file_id
            JOIN file_segments fs ON fv.version_id = fs.version_id
            JOIN file_fragments ff ON fs.segment_id = ff.segment_id
            LEFT JOIN fragment_location fl ON ff.fragment_id = fl.fragment_id
            LEFT JOIN node n ON fl.node_id = n.node_id
            WHERE fo.file_id = $1 
            ORDER BY ff.num_fragment
        `, [fileId]);
        
        res.json(result.rows);
    } catch (error) {
        console.error('Error retrieving fragments:', error);
        res.status(500).json({ error: 'Internal server error', details: error.message });
    }
});

// Master node status
app.get('/status', async (req, res) => {
    try {
        const nodeResult = await query(`
            SELECT n.*, c.total_bytes, c.used_bytes, c.available_bytes 
            FROM node n 
            LEFT JOIN node_capacity c ON n.node_id = c.node_id 
            WHERE n.node_id = $1
        `, [NODE_ID]);
        
        const nodeInfo = nodeResult.rows[0];
        
        const accountsResult = await query('SELECT COUNT(*) as count FROM account');
        const filesResult = await query('SELECT COUNT(*) as count FROM file_objects');
        const fragmentsResult = await query('SELECT COUNT(*) as count FROM file_fragments');
        const nodesResult = await query(`SELECT COUNT(*) as count FROM node WHERE node_role = 'STORAGE' AND is_active = true`);
        
        const stats = {
            accounts: parseInt(accountsResult.rows[0].count),
            files: parseInt(filesResult.rows[0].count),
            fragments: parseInt(fragmentsResult.rows[0].count),
            storage_nodes: parseInt(nodesResult.rows[0].count)
        };
        
        res.json({
            master_node: nodeInfo,
            database: {
                type: 'PostgreSQL',
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
        await query('UPDATE node SET is_active = false WHERE node_id = $1', [NODE_ID]);
        await pool.end();
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
        console.log(`Master Node server with PostgreSQL database running on port ${NODE_PORT}`);
        console.log(`API available at: http://${NODE_HOSTNAME}:${NODE_PORT}`);
        console.log(`Database: PostgreSQL`);
    });
}

startServer().catch((error) => {
    console.error('Error starting master node server:', error);
    process.exit(1);
});

