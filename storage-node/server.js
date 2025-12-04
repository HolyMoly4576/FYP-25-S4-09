const express = require('express');
const axios = require('axios');
const {v4: uuidv4} = require('uuid');
const fs = require('fs').promises;
const path = require('path');
const app = express();

app.use(express.json());

// Master node connection instead of direct database
const MASTER_NODE_HOST = process.env.MASTER_NODE_HOST || 'master_node';
const MASTER_NODE_PORT = process.env.MASTER_NODE_PORT || 3000;
const MASTER_NODE_URL = `http://${MASTER_NODE_HOST}:${MASTER_NODE_PORT}`;

const NODE_ID = uuidv4();
const NODE_PORT = process.env.NODE_PORT || 3000;
const NODE_ROLE = process.env.NODE_ROLE || 'STORAGE';
const NODE_HOSTNAME = process.env.NODE_HOSTNAME || `storage-node-${NODE_ID.slice(0, 8)}`;
const STORAGE_PATH = process.env.STORAGE_PATH || '/storage';
const HEARTBEAT_INTERVAL = parseInt(process.env.HEARTBEAT_INTERVAL) || 10000;

async function registerWithMaster(){
    try {
        const apiEndpoint = `http://${NODE_HOSTNAME}:${NODE_PORT}`;
        const response = await axios.post(`${MASTER_NODE_URL}/register-node`, {
            nodeId: NODE_ID,
            apiEndpoint: apiEndpoint,
            nodeRole: NODE_ROLE,
            hostname: NODE_HOSTNAME
        });
        
        if (response.data.success) {
            console.log(`Storage Node ${NODE_ID} registered with master node.`);
            console.log('Hostname:', NODE_HOSTNAME);
            console.log('Role:', NODE_ROLE);
            console.log('Master Node:', MASTER_NODE_URL);
        } else {
            throw new Error('Failed to register with master node');
        }
    } catch (error) {
        console.error('Error registering with master node:', error.message);
        console.log('Retrying in 5 seconds...');
        setTimeout(registerWithMaster, 5000);
    }
}

async function heartbeat(){
    try{
        const initTime = Date.now();
        const latency = Date.now() - initTime;
        
        const response = await axios.post(`${MASTER_NODE_URL}/node-heartbeat`, {
            nodeId: NODE_ID,
            latency: latency
        });

        if (response.data.success) {
            console.log('Heartbeat sent for storage node', NODE_ID);
            console.log('Heartbeat latency (ms):', latency);
            console.log(`Sent at: ${new Date().toISOString()}`);
        }
    } catch (error) {
        console.error('Error sending heartbeat to master node:', error.message);
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
        const totalBytes = 100 * 1024 * 1024 * 1024; // 100GB default
        const availableBytes = totalBytes - usedBytes;

        // Send capacity update to master node
        try {
            await axios.post(`${MASTER_NODE_URL}/update-capacity`, {
                nodeId: NODE_ID,
                totalBytes: totalBytes,
                usedBytes: usedBytes,
                availableBytes: availableBytes
            });
        } catch (error) {
            console.error('Error updating capacity with master node:', error.message);
        }

        console.log(`Storage Node ${NODE_ID} capacity updated.`);
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
        const { fragmentId, data, bytes, contentHash } = req.body;
        if (!fragmentId || !data) {
            return res.status(400).json({ error: 'Missing fragmentId or data' });
        }

        // Store fragment locally
        const fragmentPath = path.join(STORAGE_PATH, `${fragmentId}.bin`);
        await fs.writeFile(fragmentPath, Buffer.from(data, 'base64'));

        // Notify master node about fragment storage
        try {
            await axios.post(`${MASTER_NODE_URL}/fragments`, {
                fileId: req.body.fileId || 'unknown',
                nodeId: NODE_ID,
                fragmentOrder: req.body.fragmentOrder || 0,
                fragmentSize: bytes || data.length,
                fragmentHash: contentHash || 'unknown'
            });
        } catch (error) {
            console.error('Error notifying master node:', error.message);
            // Continue anyway - fragment is stored locally
        }

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

// List all fragments stored on this node
app.get('/fragments', async (req, res) => {
    try {
        const files = await fs.readdir(STORAGE_PATH);
        const fragments = [];
        
        for (const file of files) {
            if (file.endsWith('.bin')) {
                const fragmentId = file.replace('.bin', '');
                const fragmentPath = path.join(STORAGE_PATH, file);
                
                try {
                    const stats = await fs.stat(fragmentPath);
                    fragments.push({
                        fragmentId: fragmentId,
                        bytes: stats.size,
                        storedAt: stats.mtime.toISOString(),
                        path: fragmentPath
                    });
                } catch (error) {
                    console.error(`Error getting stats for fragment ${fragmentId}:`, error.message);
                    // Continue with other fragments
                }
            }
        }
        
        res.json({
            success: true,
            nodeId: NODE_ID,
            fragmentCount: fragments.length,
            fragments: fragments
        });
    } catch (error) {
        console.error('Error listing fragments:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/fragments/:fragmentId', async (req, res) => {
    try {
        const { fragmentId } = req.params;
        const fragmentPath = path.join(STORAGE_PATH, `${fragmentId}.bin`);
        
        try {
            const data = await fs.readFile(fragmentPath);
            res.json({
                success: true,
                fragmentId: fragmentId,
                data: data.toString('base64'),
                bytes: data.length
            });
        } catch (error) {
            if (error.code === 'ENOENT') {
                return res.status(404).json({ error: 'Fragment not found' });
            }
            throw error;
        }
    } catch (error) {
        console.error('Error retrieving fragment:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.delete('/fragments/:fragmentId', async (req, res) => {
    try {
        const { fragmentId } = req.params;
        const fragmentPath = path.join(STORAGE_PATH, `${fragmentId}.bin`);
        
        try {
            await fs.unlink(fragmentPath);
            
            // Notify master node about fragment deletion
            try {
                await axios.delete(`${MASTER_NODE_URL}/fragments/${fragmentId}`);
            } catch (error) {
                console.error('Error notifying master node:', error.message);
                // Continue anyway - fragment is deleted locally
            }
            
            await updateCapacity();
            res.json({
                success: true,
                fragmentId: fragmentId
            });
        } catch (error) {
            if (error.code === 'ENOENT') {
                return res.status(404).json({ error: 'Fragment not found' });
            }
            throw error;
        }
    } catch (error) {
        console.error('Error deleting fragment:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.get('/status', async (req, res) => {
    try {
        // Get storage directory size
        const stats = await fs.stat(STORAGE_PATH);
        const storageInfo = {
            nodeId: NODE_ID,
            nodeType: 'storage',
            status: 'active',
            storageUsed: await getDirectorySize(STORAGE_PATH),
            capacity: TOTAL_CAPACITY,
            address: `http://${NODE_HOST}:${NODE_PORT}`,
            lastUpdated: new Date().toISOString()
        };
        
        res.json(storageInfo);
    } catch (error) {
        console.error('Error retrieving node status:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

// Helper function to get directory size
async function getDirectorySize(dirPath) {
    let size = 0;
    try {
        const files = await fs.readdir(dirPath);
        for (const file of files) {
            const filePath = path.join(dirPath, file);
            const stats = await fs.stat(filePath);
            if (stats.isFile()) {
                size += stats.size;
            }
        }
    } catch (error) {
        console.error('Error calculating directory size:', error);
    }
    return size;
}

process.on('SIGTERM', async () => {
    console.log('Shutting down node...');
    try {
        await axios.post(`${MASTER_NODE_URL}/nodes/deregister`, {
            nodeId: NODE_ID
        });
    } catch (error) {
        console.error('Error deregistering from master node:', error);
    }
    process.exit(0);
});

async function startServer(){
    await registerWithMaster();
    
    // Ensure storage directory exists
    try {
        await fs.mkdir(STORAGE_PATH, { recursive: true });
        console.log(`Storage directory created/verified: ${STORAGE_PATH}`);
    } catch (error) {
        console.error(`Error creating storage directory: ${error.message}`);
    }
    
    setInterval(heartbeat, HEARTBEAT_INTERVAL);
    setInterval(updateCapacity, HEARTBEAT_INTERVAL * 6);
    app.listen(NODE_PORT, '0.0.0.0', () => {
        console.log(`Storage Node server running on port ${NODE_PORT}`);
        console.log(`Connected to Master Node: ${MASTER_NODE_URL}`);
    });
}

startServer().catch((error) => {
    console.error('Error starting node server:', error);
    process.exit(1);
});
