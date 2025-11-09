const express = require('express');
const {Pool} = require('pg');
const {v4: uuidv4} = require('uuid');
const fs = require('fs').promises;
const path = require('path');
const app = express();

app.use(express.json());

const pool = new Pool({
    host: process.env.DB_HOST || 'postgres',
    port: process.env.DB_PORT || 5432,
    user: process.env.DB_USER || 'user',
    password: process.env.DB_PASSWORD || 'password',
    database: process.env.DB_NAME || 'database',
});

const NODE_ID = uuidv4();
const NODE_PORT = process.env.NODE_PORT || 3000;
const NODE_ROLE = process.env.NODE_ROLE || 'STORAGE';
const NODE_HOSTNAME = process.env.NODE_HOSTNAME || `node-${NODE_ID.slice(0, 8)}`;
const STORAGE_PATH = process.env.STORAGE_PATH || '/storage';
const HEARTBEAT_INTERVAL = parseInt(process.env.HEARTBEAT_INTERVAL) || 10000;

async function initialiseDB(){
    try {
        const apiEndpoint = `http://${NODE_HOSTNAME}:${NODE_PORT}`;
        await pool.query(`
            INSERT INTO NODE(
            NODE_ID,
            API_ENDPOINT,
            NODE_ROLE,
            HOSTNAME,
            IS_ACTIVE,
            UPTIMED_AT,
            HEARTBEAT_AT
            ) VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (NODE_ID) DO UPDATE SET
            IS_ACTIVE = TRUE,
            UPTIMED_AT = CURRENT_TIMESTAMP,
            HEARTBEAT_AT = CURRENT_TIMESTAMP
        `, [NODE_ID, apiEndpoint, NODE_ROLE, NODE_HOSTNAME, true]);
        const totalBytes = 12 * 1024 * 1024 * 1024; // 12 GB
        await pool.query(`
            INSERT INTO NODE_CAPACITY (NODE_ID, TOTAL_BYTES, USED_BYTES, AVAILABLE_BYTES)
            values ($1, $2, 0, $2)
            ON CONFLICT (NODE_ID) DO UPDATE SET
            UPDATED_AT = CURRENT_TIMESTAMP
        `, [NODE_ID, totalBytes]);
        console.log(`Node ${NODE_ID} initialised in database.`);
        console.log('Hostname:', NODE_HOSTNAME);
        console.log('Role:', NODE_ROLE);
    } catch (error) {
        console.error('Error initialising node in database:', error);
        process.exit(1);
    }
}

async function heartbeat(){
    try{
        const initTime = Date.now();
        await pool.query(`
            UPDATE NODE
            SET HEARTBEAT_AT = CURRENT_TIMESTAMP,
            LATENCY_MS = $1,
            IS_ACTIVE = TRUE
            WHERE NODE_ID = $2
        `, [Date.now() - initTime, NODE_ID]);

        await pool.query(`
            INSERT INTO NODE_HEARTBEAT(NODE_ID, HEARTBEAT_AT, LATENCY_MS)
            VALUES ($1, CURRENT_TIMESTAMP, $2)
            ON CONFLICT (NODE_ID) DO UPDATE SET
            HEARTBEAT_AT = CURRENT_TIMESTAMP,
            LATENCY_MS = $2
        `, [NODE_ID, Date.now() - initTime]);

        console.log('Heartbeat sent for node', NODE_ID);
        console.log('Heartbeat latency (ms):', Date.now() - initTime);
        console.log(`Sent at: ${new Date().toISOString()}`);
    } catch (error) {
        console.error('Error sending heartbeat:', error);
    }
}

async function updateCapacity(){
    try {
        const files = await fs.readdir(STORAGE_PATH);
        let usedBytes = 0;
        for (const file of files){
            const stats = await fs.stat(path.join(STORAGE_PATH, file));
            usedBytes += stats.size;
        }
        const totalBytesResult = await pool.query('SELECT TOTAL_BYTES FROM NODE_CAPACITY WHERE NODE_ID = $1', [NODE_ID]);
        const totalBytes = totalBytesResult.rows[0]?.total_bytes || 12 * 1024 * 1024 * 1024;
        const availableBytes = totalBytes - usedBytes;

        await pool.query(`
            UPDATE NODE_CAPACITY
            SET USED_BYTES = $1, 
            AVAILABLE_BYTES = $2, 
            UPDATED_AT = CURRENT_TIMESTAMP
            WHERE NODE_ID = $3
        `, [usedBytes, availableBytes, NODE_ID]);

        console.log(`Node ${NODE_ID} capacity updated.`);
        console.log(`Available Bytes: ${availableBytes}`);
        console.log(`Used Bytes: ${usedBytes}`);
    } catch (error) {
        console.error('Error updating node capacity:', error);
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
