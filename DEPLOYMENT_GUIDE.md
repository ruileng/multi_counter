# 🚀 Multi Counter Production Deployment Guide

## 📋 Overview

This guide covers deploying the Multi Counter Web Application on **CentOS 8** using the **Gunicorn + Supervisor + Nginx** architecture for production-ready deployment with:

- ✅ **Multi-user session isolation** (Redis-backed sessions)
- ✅ **Real-time video processing** with WebSocket support
- ✅ **Auto-restart on failure** (Supervisor monitoring)
- ✅ **Load balancing ready** (Nginx reverse proxy)
- ✅ **SSL/HTTPS support** (easily configurable)
- ✅ **Automatic backups and monitoring**

## 🏗️ Architecture Overview

```
Internet → Nginx (Port 80/443) → Gunicorn (Port 8000) → Flask App
                ↓
            Static Files
            Video Streaming
            Load Balancing
                ↓
         Supervisor Process Manager
                ↓
         Multi-Worker Flask App
                ↓
         Redis (Session Storage)
```

## 🛠️ Quick Deployment

### 1. **Automated Installation**

```bash
# Clone the repository
git clone <your-repo-url>
cd multi_counter

# Make installation script executable
chmod +x deploy/install.sh

# Run installation (as root)
sudo ./deploy/install.sh
```

### 2. **Manual Configuration**

After installation, update these configurations:

```bash
# 1. Update domain name
sudo nano /etc/nginx/conf.d/multi-counter.conf
# Change "your-domain.com" to your actual domain

# 2. Update secret key
sudo nano /opt/multi-counter/.env
# Change SECRET_KEY to a secure random string

# 3. Restart services
sudo supervisorctl restart multi-counter
sudo systemctl reload nginx
```

## 📖 Detailed Setup Instructions

### **System Requirements**

- **OS**: CentOS 8 (or RHEL 8/Rocky Linux 8)
- **RAM**: Minimum 4GB, Recommended 8GB+
- **CPU**: Minimum 2 cores, Recommended 4+ cores
- **Storage**: Minimum 20GB free space
- **Network**: Public IP with ports 80/443 open

### **Pre-Installation Setup**

```bash
# Update system
sudo dnf update -y

# Install basic tools
sudo dnf install -y git wget curl vim htop
```

### **Step-by-Step Manual Installation**

#### **1. Install System Dependencies**

```bash
# Install EPEL repository
sudo dnf install -y epel-release

# Install development tools
sudo dnf groupinstall -y "Development Tools"

# Install Python and system libraries
sudo dnf install -y \
    python3.9 python3.9-pip python3.9-devel python3.9-venv \
    nginx supervisor redis \
    gcc gcc-c++ make cmake pkg-config \
    libjpeg-turbo-devel libpng-devel libtiff-devel \
    opencv opencv-devel mesa-libGL libXext libSM libXrender
```

#### **2. Create Application User**

```bash
# Create system user for the application
sudo groupadd --system multi-counter
sudo useradd --system --gid multi-counter --shell /bin/bash \
    --home-dir /opt/multi-counter --create-home multi-counter
```

#### **3. Setup Application Directory**

```bash
# Create directory structure
sudo mkdir -p /opt/multi-counter/{uploads,recordings,sessions,static,logs}
sudo mkdir -p /var/log/multi-counter
sudo mkdir -p /var/run/multi-counter

# Set permissions
sudo chown -R multi-counter:multi-counter /opt/multi-counter
sudo chown -R multi-counter:multi-counter /var/log/multi-counter
sudo chown -R multi-counter:multi-counter /var/run/multi-counter
```

#### **4. Deploy Application Code**

```bash
# Copy application files
sudo cp -r . /opt/multi-counter/
sudo chown -R multi-counter:multi-counter /opt/multi-counter

# Create Python virtual environment
sudo -u multi-counter python3.9 -m venv /opt/multi-counter/venv

# Install Python dependencies
sudo -u multi-counter bash -c "
    source /opt/multi-counter/venv/bin/activate && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r /opt/multi-counter/requirements.txt
"
```

#### **5. Configure Redis**

```bash
# Start and enable Redis
sudo systemctl enable redis
sudo systemctl start redis

# Configure Redis for sessions
sudo tee /etc/redis.conf.d/multi-counter.conf << EOF
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
EOF

sudo systemctl restart redis
```

#### **6. Configure Supervisor**

```bash
# Copy supervisor configuration
sudo cp /opt/multi-counter/deploy/supervisor.conf /etc/supervisord.d/multi-counter.conf

# Start and enable supervisor
sudo systemctl enable supervisord
sudo systemctl start supervisord

# Load new configuration
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start multi-counter
```

#### **7. Configure Nginx**

```bash
# Copy nginx configuration
sudo cp /opt/multi-counter/deploy/nginx.conf /etc/nginx/conf.d/multi-counter.conf

# Update domain name (replace your-domain.com)
sudo sed -i 's/your-domain.com/YOUR_ACTUAL_DOMAIN/g' /etc/nginx/conf.d/multi-counter.conf

# Test configuration
sudo nginx -t

# Start and enable nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

#### **8. Configure Firewall**

```bash
# Open HTTP/HTTPS ports
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 🔧 Configuration Details

### **Environment Variables (.env)**

```bash
# Flask Configuration
SECRET_KEY=your-super-secret-key-change-this-in-production
FLASK_ENV=production
FLASK_DEBUG=False

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Application Settings
MAX_CONTENT_LENGTH=104857600  # 100MB
UPLOAD_FOLDER=uploads
SESSION_TIMEOUT=3600  # 1 hour

# Server Configuration
HOST=0.0.0.0
PORT=8000
WORKERS=4
```

### **Gunicorn Configuration (gunicorn.conf.py)**

Key settings for production:

```python
# Worker configuration
workers = 4  # CPU cores * 2 + 1
worker_class = "sync"
timeout = 300  # 5 minutes for video processing
max_requests = 1000  # Restart workers after 1000 requests

# Logging
accesslog = "/var/log/multi-counter/access.log"
errorlog = "/var/log/multi-counter/error.log"
loglevel = "info"
```

### **Nginx Configuration**

Key features:
- **Static file serving** for uploads/recordings
- **Video streaming optimization** (no buffering)
- **Rate limiting** for API endpoints
- **Security headers**
- **SSL/HTTPS ready**

### **Supervisor Configuration**

Automatic process management:
- **Auto-restart** on failure
- **Log rotation**
- **Resource monitoring**
- **Graceful shutdown**

## 🔒 Security Configuration

### **SSL/HTTPS Setup**

1. **Obtain SSL Certificate** (Let's Encrypt recommended):

```bash
# Install certbot
sudo dnf install -y python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

2. **Update Nginx Configuration**:

Uncomment the HTTPS server block in `/etc/nginx/conf.d/multi-counter.conf`

### **Firewall Configuration**

```bash
# Basic firewall setup
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-service=ssh

# Optional: Restrict SSH access
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='YOUR_IP' service name='ssh' accept"

sudo firewall-cmd --reload
```

### **SELinux Configuration**

```bash
# Allow nginx to proxy
sudo setsebool -P httpd_can_network_connect 1
sudo setsebool -P httpd_can_network_relay 1

# Set proper contexts
sudo semanage fcontext -a -t httpd_var_lib_t "/opt/multi-counter/uploads(/.*)?"
sudo semanage fcontext -a -t httpd_var_lib_t "/opt/multi-counter/recordings(/.*)?"
sudo restorecon -R /opt/multi-counter/uploads
sudo restorecon -R /opt/multi-counter/recordings
```

## 📊 Monitoring & Maintenance

### **Application Status**

```bash
# Check application status
sudo supervisorctl status multi-counter

# View logs
sudo tail -f /var/log/multi-counter/supervisor.log
sudo tail -f /var/log/multi-counter/access.log
sudo tail -f /var/log/multi-counter/error.log

# Check system services
sudo systemctl status nginx
sudo systemctl status redis
sudo systemctl status supervisord
```

### **Performance Monitoring**

```bash
# System resources
htop
free -h
df -h

# Application metrics
curl http://localhost:8000/health  # If health endpoint exists

# Nginx status
curl http://localhost/nginx_status  # If configured
```

### **Log Management**

Automatic log rotation is configured for:
- Application logs (daily, keep 52 days)
- Nginx logs (daily, keep 52 days)
- Supervisor logs (50MB max, 5 backups)

### **Backup Strategy**

Automated daily backups include:
- **Application data**: uploads, recordings, sessions
- **Configuration files**: .env, gunicorn.conf.py, nginx.conf
- **Counter configurations**: custom counters and settings

```bash
# Manual backup
sudo -u multi-counter /opt/multi-counter/backup.sh

# Restore from backup
sudo tar -xzf /opt/backups/multi-counter/multi-counter-data-YYYYMMDD_HHMMSS.tar.gz -C /
```

## 🚀 Scaling & Performance

### **Horizontal Scaling**

1. **Multiple App Servers**:
   - Deploy on multiple servers
   - Use shared Redis for sessions
   - Configure Nginx load balancing

2. **Database Scaling**:
   - Use Redis Cluster for sessions
   - Separate file storage (NFS/S3)

### **Vertical Scaling**

1. **Increase Workers**:
   ```python
   # In gunicorn.conf.py
   workers = multiprocessing.cpu_count() * 2 + 1
   ```

2. **Memory Optimization**:
   ```python
   # Restart workers more frequently
   max_requests = 500
   max_requests_jitter = 50
   ```

### **Performance Tuning**

1. **Nginx Optimization**:
   ```nginx
   # Increase worker connections
   worker_connections 2048;
   
   # Enable caching
   proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=app_cache:10m;
   ```

2. **Redis Optimization**:
   ```
   # Increase memory
   maxmemory 512mb
   
   # Optimize for sessions
   maxmemory-policy allkeys-lru
   ```

## 🐛 Troubleshooting

### **Common Issues**

1. **Application Won't Start**:
   ```bash
   # Check logs
   sudo tail -f /var/log/multi-counter/supervisor.log
   
   # Check permissions
   sudo ls -la /opt/multi-counter/
   
   # Test manually
   sudo -u multi-counter /opt/multi-counter/venv/bin/python /opt/multi-counter/app.py
   ```

2. **Video Streaming Issues**:
   ```bash
   # Check camera permissions
   sudo usermod -a -G video multi-counter
   
   # Check OpenCV installation
   sudo -u multi-counter /opt/multi-counter/venv/bin/python -c "import cv2; print(cv2.__version__)"
   ```

3. **Session Issues**:
   ```bash
   # Check Redis connection
   redis-cli ping
   
   # Check Redis logs
   sudo journalctl -u redis
   ```

4. **Nginx Issues**:
   ```bash
   # Test configuration
   sudo nginx -t
   
   # Check error logs
   sudo tail -f /var/log/nginx/error.log
   ```

### **Performance Issues**

1. **High CPU Usage**:
   - Reduce video resolution in processing
   - Increase worker count
   - Optimize counter algorithms

2. **High Memory Usage**:
   - Reduce max_requests in Gunicorn
   - Optimize video frame buffering
   - Check for memory leaks

3. **Slow Response Times**:
   - Enable Nginx caching
   - Optimize database queries
   - Use CDN for static files

## 📞 Support & Updates

### **Updating the Application**

```bash
# 1. Backup current version
sudo -u multi-counter /opt/multi-counter/backup.sh

# 2. Copy new files
sudo cp -r new_version/* /opt/multi-counter/
sudo chown -R multi-counter:multi-counter /opt/multi-counter

# 3. Update dependencies
sudo -u multi-counter bash -c "
    source /opt/multi-counter/venv/bin/activate && \
    pip install -r /opt/multi-counter/requirements.txt
"

# 4. Restart application
sudo supervisorctl restart multi-counter
```

### **Health Checks**

```bash
# Quick health check script
#!/bin/bash
echo "=== Multi Counter Health Check ==="
echo "App Status: $(supervisorctl status multi-counter | awk '{print $2}')"
echo "Nginx Status: $(systemctl is-active nginx)"
echo "Redis Status: $(systemctl is-active redis)"
echo "Disk Usage: $(df -h /opt | tail -1 | awk '{print $5}')"
echo "Memory Usage: $(free -h | grep Mem | awk '{print $3"/"$2}')"
echo "Active Sessions: $(redis-cli eval 'return #redis.call(\"keys\", \"session:*\")' 0)"
```

## 🎉 Conclusion

Your Multi Counter Web Application is now deployed with:

- ✅ **Production-ready architecture** (Gunicorn + Supervisor + Nginx)
- ✅ **Multi-user session management** with Redis
- ✅ **Real-time video processing** with optimized streaming
- ✅ **Automatic monitoring and restart** capabilities
- ✅ **Security hardening** with firewall and SELinux
- ✅ **Backup and log rotation** automation
- ✅ **SSL/HTTPS ready** configuration

**Access your application at**: `http://your-domain.com`

**Management commands**:
- Start: `sudo supervisorctl start multi-counter`
- Stop: `sudo supervisorctl stop multi-counter`
- Restart: `sudo supervisorctl restart multi-counter`
- Status: `sudo supervisorctl status multi-counter`
- Logs: `sudo tail -f /var/log/multi-counter/supervisor.log`

🚀 **Happy counting with your production-ready Multi Counter application!** 