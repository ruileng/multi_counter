#!/bin/bash

# Multi Counter Web Application - CentOS 8 Deployment Script
# Gunicorn + Supervisor + Nginx Architecture

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="multi-counter"
APP_USER="multi-counter"
APP_GROUP="multi-counter"
APP_DIR="/opt/multi-counter"
PYTHON_VERSION="3.9"
DOMAIN="your-domain.com"  # Change this to your actual domain

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run this script as root (use sudo)"
    exit 1
fi

log "🚀 Starting Multi Counter deployment on CentOS 8..."

# Update system
log "📦 Updating system packages..."
dnf update -y

# Install EPEL repository
log "📦 Installing EPEL repository..."
dnf install -y epel-release

# Install system dependencies
log "📦 Installing system dependencies..."
dnf groupinstall -y "Development Tools"
dnf install -y \
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-pip \
    python${PYTHON_VERSION}-devel \
    python${PYTHON_VERSION}-venv \
    nginx \
    supervisor \
    redis \
    git \
    wget \
    curl \
    htop \
    vim \
    unzip \
    gcc \
    gcc-c++ \
    make \
    cmake \
    pkg-config \
    libjpeg-turbo-devel \
    libpng-devel \
    libtiff-devel \
    libwebp-devel \
    openssl-devel \
    libffi-devel \
    zlib-devel \
    bzip2-devel \
    readline-devel \
    sqlite-devel \
    xz-devel \
    tk-devel \
    gdbm-devel \
    db4-devel \
    libpcap-devel \
    expat-devel

# Install OpenCV system dependencies
log "📦 Installing OpenCV system dependencies..."
dnf install -y \
    opencv \
    opencv-devel \
    opencv-python3 \
    mesa-libGL \
    mesa-libGL-devel \
    libXext \
    libSM \
    libXrender \
    libgomp

# Create application user and group
log "👤 Creating application user and group..."
if ! getent group "$APP_GROUP" > /dev/null 2>&1; then
    groupadd --system "$APP_GROUP"
    log "Created group: $APP_GROUP"
fi

if ! getent passwd "$APP_USER" > /dev/null 2>&1; then
    useradd --system --gid "$APP_GROUP" --shell /bin/bash --home-dir "$APP_DIR" --create-home "$APP_USER"
    log "Created user: $APP_USER"
fi

# Create directory structure
log "📁 Creating directory structure..."
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/logs"
mkdir -p "$APP_DIR/uploads"
mkdir -p "$APP_DIR/recordings"
mkdir -p "$APP_DIR/sessions"
mkdir -p "$APP_DIR/static"
mkdir -p "/var/log/$APP_NAME"
mkdir -p "/var/run/$APP_NAME"

# Set ownership
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
chown -R "$APP_USER:$APP_GROUP" "/var/log/$APP_NAME"
chown -R "$APP_USER:$APP_GROUP" "/var/run/$APP_NAME"

# Set permissions
chmod 755 "$APP_DIR"
chmod 755 "$APP_DIR/uploads"
chmod 755 "$APP_DIR/recordings"
chmod 700 "$APP_DIR/sessions"

log "📋 Copying application files..."
# Copy application files (assuming this script is run from the project directory)
if [ -f "app.py" ]; then
    cp -r . "$APP_DIR/"
    # Remove unnecessary files
    rm -rf "$APP_DIR/.git"
    rm -rf "$APP_DIR/__pycache__"
    rm -rf "$APP_DIR/*.pyc"
    chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
else
    warning "Application files not found in current directory. Please copy them manually to $APP_DIR"
fi

# Create Python virtual environment
log "🐍 Creating Python virtual environment..."
sudo -u "$APP_USER" python${PYTHON_VERSION} -m venv "$APP_DIR/venv"

# Activate virtual environment and install dependencies
log "📦 Installing Python dependencies..."
sudo -u "$APP_USER" bash -c "
    source '$APP_DIR/venv/bin/activate' && \
    pip install --upgrade pip setuptools wheel && \
    pip install -r '$APP_DIR/requirements.txt'
"

# Configure Redis
log "🔴 Configuring Redis..."
systemctl enable redis
systemctl start redis

# Configure Redis for session storage
cat > /etc/redis.conf.d/multi-counter.conf << EOF
# Multi Counter Redis Configuration
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
EOF

systemctl restart redis

# Configure Supervisor
log "👁️ Configuring Supervisor..."
cp "$APP_DIR/deploy/supervisor.conf" /etc/supervisord.d/multi-counter.conf

# Update supervisor configuration with correct paths
sed -i "s|/opt/multi-counter|$APP_DIR|g" /etc/supervisord.d/multi-counter.conf
sed -i "s|user=multi-counter|user=$APP_USER|g" /etc/supervisord.d/multi-counter.conf
sed -i "s|group=multi-counter|group=$APP_GROUP|g" /etc/supervisord.d/multi-counter.conf

# Enable and start supervisor
systemctl enable supervisord
systemctl start supervisord

# Reload supervisor configuration
supervisorctl reread
supervisorctl update

# Configure Nginx
log "🌐 Configuring Nginx..."
cp "$APP_DIR/deploy/nginx.conf" "/etc/nginx/conf.d/$APP_NAME.conf"

# Update nginx configuration with correct domain
sed -i "s|your-domain.com|$DOMAIN|g" "/etc/nginx/conf.d/$APP_NAME.conf"
sed -i "s|/opt/multi-counter|$APP_DIR|g" "/etc/nginx/conf.d/$APP_NAME.conf"

# Test nginx configuration
nginx -t

# Enable and start nginx
systemctl enable nginx
systemctl start nginx

# Configure firewall
log "🔥 Configuring firewall..."
if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --permanent --add-port=8000/tcp  # For direct access if needed
    firewall-cmd --reload
    log "Firewall configured"
else
    warning "Firewalld is not running. Please configure firewall manually."
fi

# Configure SELinux
log "🔒 Configuring SELinux..."
if getenforce | grep -q "Enforcing"; then
    setsebool -P httpd_can_network_connect 1
    setsebool -P httpd_can_network_relay 1
    semanage fcontext -a -t httpd_var_run_t "/var/run/$APP_NAME(/.*)?"
    semanage fcontext -a -t httpd_log_t "/var/log/$APP_NAME(/.*)?"
    semanage fcontext -a -t httpd_var_lib_t "$APP_DIR/uploads(/.*)?"
    semanage fcontext -a -t httpd_var_lib_t "$APP_DIR/recordings(/.*)?"
    restorecon -R "/var/run/$APP_NAME"
    restorecon -R "/var/log/$APP_NAME"
    restorecon -R "$APP_DIR/uploads"
    restorecon -R "$APP_DIR/recordings"
    log "SELinux configured"
else
    warning "SELinux is not enforcing. Consider enabling it for better security."
fi

# Create systemd service (alternative to supervisor)
log "⚙️ Creating systemd service..."
cat > "/etc/systemd/system/$APP_NAME.service" << EOF
[Unit]
Description=Multi Counter Web Application
After=network.target

[Service]
Type=notify
User=$APP_USER
Group=$APP_GROUP
RuntimeDirectory=$APP_NAME
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/gunicorn --config $APP_DIR/gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable the service (but don't start it since we're using supervisor)
systemctl daemon-reload
# systemctl enable $APP_NAME  # Uncomment if you want to use systemd instead of supervisor

# Create log rotation
log "📋 Configuring log rotation..."
cat > "/etc/logrotate.d/$APP_NAME" << EOF
/var/log/$APP_NAME/*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 $APP_USER $APP_GROUP
    postrotate
        supervisorctl restart $APP_NAME > /dev/null 2>&1 || true
    endscript
}

/var/log/nginx/$APP_NAME-*.log {
    daily
    missingok
    rotate 52
    compress
    delaycompress
    notifempty
    create 644 nginx nginx
    postrotate
        systemctl reload nginx > /dev/null 2>&1 || true
    endscript
}
EOF

# Create backup script
log "💾 Creating backup script..."
cat > "$APP_DIR/backup.sh" << 'EOF'
#!/bin/bash

# Multi Counter Backup Script
BACKUP_DIR="/opt/backups/multi-counter"
DATE=$(date +%Y%m%d_%H%M%S)
APP_DIR="/opt/multi-counter"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup application data
tar -czf "$BACKUP_DIR/multi-counter-data-$DATE.tar.gz" \
    "$APP_DIR/uploads" \
    "$APP_DIR/recordings" \
    "$APP_DIR/sessions" \
    "$APP_DIR/configs" \
    "$APP_DIR/counters"

# Backup configuration
tar -czf "$BACKUP_DIR/multi-counter-config-$DATE.tar.gz" \
    "$APP_DIR/.env" \
    "$APP_DIR/gunicorn.conf.py" \
    "/etc/nginx/conf.d/multi-counter.conf" \
    "/etc/supervisord.d/multi-counter.conf"

# Remove backups older than 30 days
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x "$APP_DIR/backup.sh"
chown "$APP_USER:$APP_GROUP" "$APP_DIR/backup.sh"

# Create monitoring script
log "📊 Creating monitoring script..."
cat > "$APP_DIR/monitor.sh" << 'EOF'
#!/bin/bash

# Multi Counter Monitoring Script
APP_NAME="multi-counter"
LOG_FILE="/var/log/$APP_NAME/monitor.log"

# Check if application is running
if supervisorctl status $APP_NAME | grep -q "RUNNING"; then
    echo "$(date): $APP_NAME is running" >> "$LOG_FILE"
else
    echo "$(date): $APP_NAME is not running, attempting restart" >> "$LOG_FILE"
    supervisorctl restart $APP_NAME
fi

# Check disk space
DISK_USAGE=$(df /opt | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "$(date): WARNING - Disk usage is ${DISK_USAGE}%" >> "$LOG_FILE"
fi

# Check memory usage
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [ "$MEMORY_USAGE" -gt 80 ]; then
    echo "$(date): WARNING - Memory usage is ${MEMORY_USAGE}%" >> "$LOG_FILE"
fi
EOF

chmod +x "$APP_DIR/monitor.sh"
chown "$APP_USER:$APP_GROUP" "$APP_DIR/monitor.sh"

# Add monitoring to crontab
(crontab -u "$APP_USER" -l 2>/dev/null; echo "*/5 * * * * $APP_DIR/monitor.sh") | crontab -u "$APP_USER" -
(crontab -u "$APP_USER" -l 2>/dev/null; echo "0 2 * * * $APP_DIR/backup.sh") | crontab -u "$APP_USER" -

# Start the application
log "🚀 Starting Multi Counter application..."
supervisorctl start multi-counter

# Wait a moment for startup
sleep 5

# Check status
log "📊 Checking application status..."
supervisorctl status multi-counter
systemctl status nginx
systemctl status redis

# Display final information
log "✅ Deployment completed successfully!"
echo
info "🌐 Application URL: http://$DOMAIN"
info "📁 Application Directory: $APP_DIR"
info "👤 Application User: $APP_USER"
info "📋 Logs Directory: /var/log/$APP_NAME"
echo
info "🔧 Management Commands:"
info "  - Start: supervisorctl start multi-counter"
info "  - Stop: supervisorctl stop multi-counter"
info "  - Restart: supervisorctl restart multi-counter"
info "  - Status: supervisorctl status multi-counter"
info "  - Logs: tail -f /var/log/$APP_NAME/supervisor.log"
echo
info "🔄 To update the application:"
info "  1. Copy new files to $APP_DIR"
info "  2. Run: supervisorctl restart multi-counter"
echo
warning "⚠️  Don't forget to:"
warning "  1. Change the SECRET_KEY in $APP_DIR/.env"
warning "  2. Configure your domain name in nginx config"
warning "  3. Set up SSL certificates for HTTPS"
warning "  4. Configure Redis password if needed"
echo
log "🎉 Multi Counter is now running! Happy counting!"
EOF 