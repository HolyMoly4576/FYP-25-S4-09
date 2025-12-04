# Environment Configuration Guide for Master Node Architecture

## Current Architecture: FastAPI → Master Node → PostgreSQL

This guide explains the environment variables needed for the Master Node architecture.

### ✅ Required Variables (Active)

```bash
# Master Node Configuration (PRIMARY)
MASTER_NODE_URL=http://master_node:3000

# Test Database (for unit testing only)
TEST_DATABASE_URL=postgresql+psycopg2://test_user:test_password@test_postgres_db:5432/test_fyp

# JWT Configuration
JWT_SECRET_KEY=your-secret-key-here-change-in-production-very-long-and-secure
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Application Environment
ENVIRONMENT=docker
```

### ❌ Deprecated Variables (Commented Out)

These variables are no longer used because all database operations go through the Master Node:

```bash
# DATABASE_URL=postgresql+psycopg2://user:password@postgres_db:5432/database
# POSTGRES_HOST=postgres_db
# POSTGRES_PORT=5433
# POSTGRES_USER=user
# POSTGRES_PASSWORD=password
# POSTGRES_DB=database
```

### 🏗️ Architecture Flow

1. **FastAPI** reads `MASTER_NODE_URL` from .env
2. **FastAPI** sends all SQL queries to Master Node via HTTP
3. **Master Node** executes queries directly on PostgreSQL
4. **Master Node** returns results to FastAPI

### 🧪 Testing Configuration

For unit tests, `TEST_DATABASE_URL` is used to connect directly to the test database, bypassing the Master Node.

### 🔧 Local Development

If running locally (not in Docker):
```bash
MASTER_NODE_URL=http://localhost:8000
```

### 🐳 Docker Configuration

If running in Docker (current setup):
```bash
MASTER_NODE_URL=http://master_node:3000
```

### ⚠️ Important Notes

1. **No direct database connections**: FastAPI never connects to PostgreSQL directly
2. **Master Node handles all SQL**: All database operations go through Master Node
3. **Environment-specific URLs**: Use container names in Docker, localhost for local development
4. **Security**: Change JWT_SECRET_KEY in production to a long, secure value

### 🚀 Production Considerations

For production deployment:
1. Generate a strong JWT_SECRET_KEY (32+ characters)
2. Use environment-specific MASTER_NODE_URL
3. Ensure Master Node and PostgreSQL are properly secured
4. Set appropriate ACCESS_TOKEN_EXPIRE_MINUTES (consider security vs user experience)