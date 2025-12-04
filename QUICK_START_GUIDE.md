# 🚀 Quick Start Guide - Distributed File Storage System

## 📋 Prerequisites
- Docker Desktop installed and running
- Python 3.11+ with virtual environment
- Git repository cloned locally

## 🔧 Backend Setup & Start

### 1. Start Docker Services
```bash
# Navigate to project directory
cd FYP-25-S4-09

# Start all backend services
docker-compose up -d

# Verify services are running
docker-compose ps
```

**Services Started:**
- PostgreSQL Database (port 5433)
- Master Node (port 8001) 
- FastAPI Service (port 8004)
- 12 Storage Nodes (ports 8100-8111)

### 2. Check Service Health
```bash
# Test API is running
curl http://localhost:8004/docs

# Test master node
curl http://localhost:8001/health

# Check database
docker exec postgres_db psql -U user -d database -c "SELECT COUNT(*) FROM account;"
```

## 🌐 Frontend Setup & Start

### 1. Activate Python Environment
```bash
# Windows
.\.venv\Scripts\Activate.ps1

# Linux/Mac  
source .venv/bin/activate
```

### 2. Start Web Interface
```bash
# Start the web server
python start_web_interface.py
```

**Web Interface Available At:**
- URL: `http://localhost:8080/simple_file_interface.html`
- Auto-opens in browser

## 🔑 Default Login Credentials
- **Username**: `alice`
- **Password**: `password123`

## ✅ Quick Verification

### Test Upload/Download
1. Open web interface: `http://localhost:8080/simple_file_interface.html`
2. Login with alice/password123
3. Select redundancy level (LOW/MEDIUM/HIGH)
4. Drag & drop a test file
5. Click download to verify reconstruction

### Database Verification
```bash
# Check uploaded files
docker exec postgres_db psql -U user -d database -c "
SELECT file_name, erasure_id, file_size, uploaded_at 
FROM file_objects fo 
JOIN file_versions fv ON fo.file_id = fv.file_id 
JOIN file_segments fs ON fv.version_id = fs.version_id 
ORDER BY uploaded_at DESC;
"

# Check fragment distribution
docker exec postgres_db psql -U user -d database -c "
SELECT COUNT(*) as total_fragments, erasure_id 
FROM file_fragments ff 
JOIN file_segments fs ON ff.segment_id = fs.segment_id 
GROUP BY erasure_id;
"
```

## 🛑 Stop Services

### Stop Frontend
```bash
# In terminal running web interface
Ctrl+C
```

### Stop Backend
```bash
# Stop all Docker services
docker-compose down

# Stop and remove volumes (clean reset)
docker-compose down -v
```

## 🔥 Troubleshooting

### Common Issues

**1. Port Already in Use**
```bash
# Check what's using ports
netstat -ano | findstr "8004"
netstat -ano | findstr "8080"

# Kill process if needed
taskkill /PID <process_id> /F
```

**2. Docker Services Not Starting**
```bash
# Check Docker Desktop is running
docker --version

# Restart services
docker-compose restart

# View logs
docker-compose logs fastapi
```

**3. Database Connection Failed**
```bash
# Wait for database to fully initialize (30-60 seconds)
docker exec postgres_db pg_isready -U user -d database

# Check database logs
docker-compose logs postgres_db
```

**4. CORS Errors in Browser**
- Ensure FastAPI service restarted after CORS configuration
- Use exact URLs (localhost vs 127.0.0.1)

## 📊 System Architecture

```
Web Interface (8080) 
    ↓ HTTP/REST API
FastAPI Service (8004)
    ↓ HTTP requests  
Master Node (8001)
    ↓ Database queries
PostgreSQL (5433)
    ↓ Fragment distribution
Storage Nodes (8100-8111)
```

## 🎯 Features Available

- ✅ Reed-Solomon erasure coding (LOW/MEDIUM/HIGH)
- ✅ Drag & drop file upload
- ✅ Distributed fragment storage
- ✅ Fault-tolerant reconstruction
- ✅ User authentication
- ✅ Real-time progress feedback
- ✅ File management interface

## 📝 API Endpoints

- **Auth**: `POST /auth/login`
- **Upload**: `POST /files/upload` 
- **Download**: `GET /files/download/{file_id}`
- **List Files**: `GET /files/list`
- **File Info**: `GET /files/info/{file_id}`
- **API Docs**: `http://localhost:8004/docs`

---

🎉 **System Ready!** Your distributed Reed-Solomon file storage system is now running and ready for demonstration!