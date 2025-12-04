#!/usr/bin/env node

/**
 * Master Node PostgreSQL Connection Test
 * 
 * This script tests the connection between Master Node and PostgreSQL
 * Run this to verify that the Master Node can properly communicate with the database
 */

const { Pool } = require('pg');

async function testConnection() {
    console.log('🔍 Testing Master Node -> PostgreSQL Connection');
    console.log('================================================');
    
    // Use the same connection logic as the main server
    const connectionString = process.env.DATABASE_URL || 
        `postgresql://${process.env.POSTGRES_USER || 'user'}:${process.env.POSTGRES_PASSWORD || 'password'}@${process.env.POSTGRES_HOST || 'postgres_db'}:${process.env.POSTGRES_PORT || 5432}/${process.env.POSTGRES_DB || 'database'}`;
    
    console.log('Connection String:', connectionString.replace(/password=[^&\s]+/, 'password=***'));
    
    const pool = new Pool({
        connectionString: connectionString,
        max: 5,
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: 5000,
    });
    
    try {
        console.log('\n📡 Attempting to connect...');
        
        // Test basic connection
        const testResult = await pool.query('SELECT NOW() as current_time, version() as pg_version');
        console.log('✅ Connection successful!');
        console.log('Current time:', testResult.rows[0].current_time);
        console.log('PostgreSQL version:', testResult.rows[0].pg_version.split(' ')[0]);
        
        // Test database schema
        console.log('\n📊 Checking database schema...');
        const tableCount = await pool.query(`
            SELECT COUNT(*) as table_count 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        `);
        
        console.log(`Found ${tableCount.rows[0].table_count} tables in public schema`);
        
        // Check critical tables
        const criticalTables = ['account', 'node', 'file_objects', 'file_fragments'];
        console.log('\n🔍 Verifying critical tables...');
        
        for (const table of criticalTables) {
            const tableExists = await pool.query(
                'SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema = $1 AND table_name = $2)',
                ['public', table]
            );
            
            const status = tableExists.rows[0].exists ? '✅' : '❌';
            console.log(`${status} Table '${table}': ${tableExists.rows[0].exists ? 'EXISTS' : 'MISSING'}`);
        }
        
        // Test query operations
        console.log('\n🧪 Testing CRUD operations...');
        
        // Test SELECT
        try {
            await pool.query('SELECT COUNT(*) FROM account');
            console.log('✅ SELECT operations: Working');
        } catch (error) {
            console.log('❌ SELECT operations: Failed -', error.message);
        }
        
        // Test connection pool
        console.log('\n📈 Connection Pool Status:');
        console.log('Total connections:', pool.totalCount);
        console.log('Idle connections:', pool.idleCount);
        console.log('Waiting clients:', pool.waitingCount);
        
        console.log('\n🎉 Master Node -> PostgreSQL connection test completed successfully!');
        
    } catch (error) {
        console.error('\n❌ Connection test failed:');
        console.error('Error:', error.message);
        console.error('Code:', error.code);
        
        if (error.code === 'ENOTFOUND') {
            console.error('💡 Hint: Check if PostgreSQL host is reachable');
        } else if (error.code === 'ECONNREFUSED') {
            console.error('💡 Hint: Check if PostgreSQL service is running');
        } else if (error.code === '28P01') {
            console.error('💡 Hint: Check PostgreSQL username/password');
        } else if (error.code === '3D000') {
            console.error('💡 Hint: Check if database exists');
        }
        
        process.exit(1);
    } finally {
        await pool.end();
        console.log('\n🔌 Connection pool closed');
    }
}

// Handle graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n\n⏹️  Test interrupted by user');
    process.exit(0);
});

// Run the test
testConnection().catch((error) => {
    console.error('Unexpected error:', error);
    process.exit(1);
});