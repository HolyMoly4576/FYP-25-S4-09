const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

// Initialize SQLite database for master node
const dbPath = process.env.DB_PATH || '/data/master.db';
const db = new Database(dbPath);

// Read SQL schema from the PostgreSQL schema and adapt it
const initSQL = `
-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Create extension equivalent (SQLite doesn't have uuid-ossp, we'll use JS uuid)
-- CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    user_type TEXT CHECK (user_type IN ('FREE', 'PREMIUM', 'ADMIN')) DEFAULT 'FREE',
    storage_limit_bytes BIGINT DEFAULT 5368709120,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Nodes table
CREATE TABLE IF NOT EXISTS node (
    node_id TEXT PRIMARY KEY,
    api_endpoint TEXT NOT NULL,
    node_role TEXT CHECK (node_role IN ('STORAGE', 'MASTER')) NOT NULL,
    hostname TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    uptimed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    latency_ms INTEGER DEFAULT 0
);

-- Node capacity table
CREATE TABLE IF NOT EXISTS node_capacity (
    node_id TEXT PRIMARY KEY,
    total_bytes BIGINT NOT NULL,
    used_bytes BIGINT DEFAULT 0,
    available_bytes BIGINT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (node_id) REFERENCES node(node_id) ON DELETE CASCADE
);

-- Node heartbeat table
CREATE TABLE IF NOT EXISTS node_heartbeat (
    heartbeat_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    uptimed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    heartbeat_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    latency_ms INTEGER DEFAULT 0,
    FOREIGN KEY (node_id) REFERENCES node(node_id) ON DELETE CASCADE,
    UNIQUE(node_id)
);

-- Files table
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    file_type TEXT,
    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- File fragments table
CREATE TABLE IF NOT EXISTS file_fragments (
    fragment_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    fragment_order INTEGER NOT NULL,
    fragment_size BIGINT NOT NULL,
    fragment_hash TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    FOREIGN KEY (node_id) REFERENCES node(node_id) ON DELETE CASCADE
);

-- Folders table
CREATE TABLE IF NOT EXISTS folders (
    folder_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    parent_folder_id TEXT,
    folder_name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (parent_folder_id) REFERENCES folders(folder_id) ON DELETE CASCADE
);

-- User storage table
CREATE TABLE IF NOT EXISTS user_storage (
    user_id TEXT PRIMARY KEY,
    used_bytes BIGINT DEFAULT 0,
    total_bytes BIGINT DEFAULT 5368709120,
    last_calculated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
CREATE INDEX IF NOT EXISTS idx_file_fragments_file_id ON file_fragments(file_id);
CREATE INDEX IF NOT EXISTS idx_file_fragments_node_id ON file_fragments(node_id);
CREATE INDEX IF NOT EXISTS idx_folders_user_id ON folders(user_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent_id ON folders(parent_folder_id);
CREATE INDEX IF NOT EXISTS idx_node_heartbeat_node_id ON node_heartbeat(node_id);
`;

try {
    console.log('Initializing master node database...');
    db.exec(initSQL);
    console.log('Database initialized successfully!');
    console.log(`Database location: ${dbPath}`);
} catch (error) {
    console.error('Error initializing database:', error);
    process.exit(1);
} finally {
    db.close();
}