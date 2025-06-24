# 🚀 Safe Deployment Guide for Existing Server

## 📋 Server Status Assessment

Since your server already has **Nginx** and **Redis** running with another project, and you can **stop the old project** during deployment, here's the safe deployment strategy:

## 🎯 Deployment Strategy

### **Directory Structure Recommendation**
```
/home/user/mall/          # Your existing mall project (keep as is)
/opt/multi-counter/       # New Multi Counter project (recommended location)
```

### **Nginx Configuration Structure**
```
/etc/nginx/conf.d/
├── mall.conf             # Your existing mall project (keep as is)
└── multi-counter.conf    # New Multi Counter project (we'll add this)
```
**Note**: Multiple `.conf` files can coexist! Each handles different domains/ports.

### **Port Usage**
- **Nginx**: Port 80/443 (shared between projects via different domains/paths)
- **Redis**: Port 6379 (shared, we'll use different database numbers)
- **Multi Counter**: Port 8000 (Gunicorn backend)
- **Mall Project**: Whatever port it currently uses

## 🛠️ Step-by-Step Safe Deployment

### **Phase 1: Preparation (No Service Interruption)**

#### 1. **Upload Project Files**
```bash
# Create project directory
sudo mkdir -p /opt/multi-counter
cd /opt/multi-counter

# Upload your project files here (via git, scp, or file transfer)
# Example with git:
git clone <your-repo-url> .

# Or if uploading files directly:
# Copy all your project files to /opt/multi-counter/
```

#### 2. **Install Python Dependencies**
```bash
# Create application user
sudo groupadd --system multi-counter
sudo useradd --system --gid multi-counter --shell /bin/bash \
    --home-dir /opt/multi-counter --create-home multi-counter

# Set ownership
sudo chown -R multi-counter:multi-counter /opt/multi-counter

# Create virtual environment
sudo -u multi-counter python3.9 -m venv /opt/multi-counter/venv

# Install dependencies
sudo -u multi-counter bash -c "
    source /opt/multi-counter/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r /opt/multi-counter/requirements.txt
"
```

#### 3. **Create Required Directories**
```bash
# Create application directories
sudo mkdir -p /opt/multi-counter/{uploads,recordings,sessions,static,logs}
sudo mkdir -p /var/log/multi-counter
sudo mkdir -p /var/run/multi-counter

# Set permissions
sudo chown -R multi-counter:multi-counter /opt/multi-counter
sudo chown -R multi-counter:multi-counter /var/log/multi-counter
sudo chown -R multi-counter:multi-counter /var/run/multi-counter
```

#### 4. **Configure Environment**
```bash
# Create .env file
sudo -u multi-counter tee /opt/multi-counter/.env << EOF
# Flask Configuration
SECRET_KEY=$(openssl rand -base64 32)
FLASK_ENV=production
FLASK_DEBUG=False

# Redis Configuration (using database 1 to avoid conflicts with mall project)
REDIS_URL=redis://localhost:6379/1

# Application Settings
MAX_CONTENT_LENGTH=104857600
UPLOAD_FOLDER=uploads
SESSION_TIMEOUT=3600

# Server Configuration
HOST=127.0.0.1
PORT=8000
WORKERS=4
EOF
```

### **Phase 2: Service Configuration (Still No Interruption)**

#### 5. **Configure Supervisor**
```bash
# Install supervisor if not already installed
sudo dnf install -y supervisor

# Copy supervisor configuration
sudo cp /opt/multi-counter/deploy/supervisor.conf /etc/supervisord.d/multi-counter.conf

# Update paths in supervisor config
sudo sed -i "s|/opt/multi-counter|/opt/multi-counter|g" /etc/supervisord.d/multi-counter.conf
sudo sed -i "s|user=multi-counter|user=multi-counter|g" /etc/supervisord.d/multi-counter.conf

# Enable supervisor (if not already enabled)
sudo systemctl enable supervisord
sudo systemctl start supervisord

# Reload supervisor configuration (this won't affect existing services)
sudo supervisorctl reread
sudo supervisorctl update
```

#### 6. **Test Application Startup**
```bash
# Start the Multi Counter application
sudo supervisorctl start multi-counter

# Check if it's running
sudo supervisorctl status multi-counter

# Test if the app responds
curl http://localhost:8000

# If there are issues, check logs
sudo tail -f /var/log/multi-counter/supervisor.log
```

### **Phase 3: Configure Nginx (Choose Your Strategy)**

#### **Option A: Different Domain/Subdomain (Recommended)**
If you have a different domain or subdomain for Multi Counter:

```bash
# Copy Multi Counter nginx configuration (this won't affect mall.conf)
sudo cp /opt/multi-counter/deploy/nginx.conf /etc/nginx/conf.d/multi-counter.conf

# Update domain name in nginx config
sudo sed -i 's/your-domain.com/counter.yourdomain.com/g' /etc/nginx/conf.d/multi-counter.conf
# OR
sudo sed -i 's/your-domain.com/yourcounterdomain.com/g' /etc/nginx/conf.d/multi-counter.conf

# Test nginx configuration (this should pass since mall.conf is still there)
sudo nginx -t

# If test passes, reload nginx (mall project keeps running)
sudo systemctl reload nginx
```

#### **Option B: Replace Mall Project (If You Want to Stop Mall)**
If you want to stop the mall project and use the same domain:

```bash
# Stop mall project first
sudo supervisorctl stop mall  # or whatever command stops your mall project

# Backup mall nginx config
sudo mv /etc/nginx/conf.d/mall.conf /etc/nginx/conf.d/mall.conf.disabled

# Copy Multi Counter nginx configuration
sudo cp /opt/multi-counter/deploy/nginx.conf /etc/nginx/conf.d/multi-counter.conf

# Update domain name to your existing domain
sudo sed -i 's/your-domain.com/YOUR_EXISTING_DOMAIN/g' /etc/nginx/conf.d/multi-counter.conf

# Test nginx configuration
sudo nginx -t

# If test passes, reload nginx
sudo systemctl reload nginx
```

#### **Option C: Path-Based Routing (Both Projects on Same Domain)**
If you want both projects accessible on the same domain:

```bash
# This requires modifying your existing mall.conf to add a location block
# Add this to your mall.conf BEFORE the main location / block:

sudo tee -a /etc/nginx/conf.d/mall.conf << 'EOF'

# Multi Counter application
location /counter {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /counter/static/ {
    alias /opt/multi-counter/static/;
}

location /counter/uploads/ {
    alias /opt/multi-counter/uploads/;
}
EOF

# Test nginx configuration
sudo nginx -t

# If test passes, reload nginx
sudo systemctl reload nginx
```

#### 7. **Configure Redis Database Separation**
```bash
# Redis is already running, we just need to ensure database separation
# Mall project probably uses: redis://localhost:6379/0 (default)
# Multi Counter uses: redis://localhost:6379/1 (configured in .env)

# Check Redis configuration
redis-cli ping

# Test database separation
redis-cli select 0  # Mall project database
redis-cli select 1  # Multi Counter database
redis-cli ping

# Optional: Set up Redis configuration for Multi Counter
sudo tee /etc/redis.conf.d/multi-counter.conf << EOF
# Multi Counter Redis Configuration
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
EOF

# Restart Redis to apply new configuration
sudo systemctl restart redis
```

### **Phase 4: Verification & Cleanup**

#### 8. **Verify Everything Works**
```bash
# Check all services
sudo systemctl status nginx
sudo systemctl status redis
sudo supervisorctl status multi-counter
sudo supervisorctl status  # Check all supervised processes

# Test applications
curl http://localhost:8000  # Multi Counter direct
curl http://YOUR_DOMAIN     # Through nginx

# Check logs for any errors
sudo tail -f /var/log/multi-counter/supervisor.log
sudo tail -f /var/log/nginx/multi-counter-access.log
sudo tail -f /var/log/nginx/multi-counter-error.log
```

#### 9. **Configure Firewall (if needed)**
```bash
# Check if firewall is running
sudo firewall-cmd --state

# If running, ensure HTTP/HTTPS ports are open
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 🔧 Configuration Details for Shared Server

### **Redis Database Separation**
```bash
# Mall project probably uses: redis://localhost:6379/0 (default)
# Multi Counter uses: redis://localhost:6379/1 (database 1)
# This ensures complete session isolation between projects
```

### **Nginx Multiple Projects**
```
/etc/nginx/conf.d/
├── mall.conf             # Your existing mall project (unchanged)
└── multi-counter.conf    # New Multi Counter project

# Each .conf file can have different:
# - server_name (different domains)
# - listen ports
# - location blocks
```

### **Process Management**
```bash
# Multi Counter management commands:
sudo supervisorctl start multi-counter
sudo supervisorctl stop multi-counter
sudo supervisorctl restart multi-counter
sudo supervisorctl status multi-counter

# View all processes:
sudo supervisorctl status

# View logs:
sudo tail -f /var/log/multi-counter/supervisor.log
```

## 🚨 Rollback Plan (If Needed)

If something goes wrong, here's how to quickly rollback:

```bash
# 1. Stop Multi Counter
sudo supervisorctl stop multi-counter

# 2. Remove Multi Counter nginx config (if using Option A or B)
sudo rm /etc/nginx/conf.d/multi-counter.conf

# 3. Restore mall nginx config (if using Option B)
sudo mv /etc/nginx/conf.d/mall.conf.disabled /etc/nginx/conf.d/mall.conf

# 4. Test and reload nginx
sudo nginx -t && sudo systemctl reload nginx

# 5. Start mall project (if it was stopped)
sudo supervisorctl start mall  # adjust command as needed

# 6. Verify mall project is working
curl http://YOUR_DOMAIN
```

## 📁 File Locations Summary

```
# Project Directories
/home/user/mall/                   # Your existing mall project (unchanged)
/opt/multi-counter/                # New Multi Counter project
├── app.py                         # Main application file
├── web_app.py                     # Flask web interface
├── requirements.txt               # Python dependencies
├── gunicorn.conf.py              # Gunicorn configuration
├── .env                          # Environment variables
├── uploads/                      # Uploaded videos
├── recordings/                   # Recorded sessions
├── sessions/                     # Session data
└── venv/                        # Python virtual environment

# Nginx Configuration
/etc/nginx/conf.d/
├── mall.conf                     # Your existing mall config (unchanged)
└── multi-counter.conf            # New Multi Counter config

# Supervisor Configuration
/etc/supervisord.d/
├── mall.conf                     # Your existing mall supervisor config
└── multi-counter.conf            # New Multi Counter supervisor config

# Logs
/var/log/multi-counter/           # Multi Counter logs
├── supervisor.log                # Supervisor logs
├── access.log                    # Gunicorn access logs
└── error.log                     # Gunicorn error logs
```

## 🔍 Troubleshooting Common Issues

### **Port Conflicts**
```bash
# Check what's using port 8000
sudo netstat -tlnp | grep :8000
sudo lsof -i :8000

# If port is busy, change it in gunicorn.conf.py and .env
```

### **Nginx Configuration Issues**
```bash
# Test nginx configuration
sudo nginx -t

# Check which configs are loaded
sudo nginx -T | grep "configuration file"

# Check error logs
sudo tail -f /var/log/nginx/error.log
```

### **Permission Issues**
```bash
# Fix ownership
sudo chown -R multi-counter:multi-counter /opt/multi-counter

# Fix SELinux contexts (if SELinux is enabled)
sudo restorecon -R /opt/multi-counter
```

### **Redis Connection Issues**
```bash
# Test Redis connection
redis-cli ping
redis-cli select 1  # Multi Counter database
redis-cli ping

# Check Redis logs
sudo journalctl -u redis
```

## ✅ Final Checklist

- [ ] Multi Counter application starts without errors
- [ ] Nginx configuration is valid (`sudo nginx -t`)
- [ ] Both projects can coexist (if using Option A or C)
- [ ] Redis database separation works
- [ ] Video upload and processing work
- [ ] Static files are served correctly
- [ ] Logs are being written properly
- [ ] Firewall allows HTTP/HTTPS traffic

## 🎉 Success!

Depending on your chosen option:

**Option A (Different Domain):**
- Mall: `http://yourdomain.com`
- Multi Counter: `http://counter.yourdomain.com`

**Option B (Replace Mall):**
- Multi Counter: `http://yourdomain.com`

**Option C (Path-Based):**
- Mall: `http://yourdomain.com`
- Multi Counter: `http://yourdomain.com/counter`

## 📞 Need Help?

If you encounter any issues during deployment:

1. **Check logs first**: All logs are in `/var/log/multi-counter/`
2. **Verify services**: `sudo supervisorctl status` and `sudo systemctl status nginx redis`
3. **Test connectivity**: `curl http://localhost:8000` and `curl http://YOUR_DOMAIN`
4. **Use the rollback plan** if needed to restore the old project quickly 