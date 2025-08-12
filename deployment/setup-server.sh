#!/bin/bash

# Server setup script for PDF2HTML API deployment
# Run this script on your Hetzner server to prepare it for deployment
# This script is designed to work with existing Docker containers

set -e

echo "Setting up Hetzner server for PDF2HTML API deployment..."
echo "Note: This script will work with your existing Docker setup"

# Check if Docker is already installed
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "Docker installed. Please log out and back in for group changes to take effect."
    echo "Then run this script again."
    exit 0
else
    echo "Docker is already installed: $(docker --version)"
fi

# Check if Docker Compose is already installed
if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose not found. Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
else
    echo "Docker Compose is already installed: $(docker-compose --version)"
fi

# Check for existing Traefik setup
if docker ps --format "table {{.Names}}" | grep -q "traefik"; then
    echo "Traefik container already exists. Skipping Traefik setup."
    echo "Please ensure your existing Traefik is configured to handle:"
    echo "- staging.pdf2html.yourdomain.com"
    echo "- api.pdf2html.yourdomain.com"
    echo "- grafana.yourdomain.com (optional)"
    echo "- monitoring.yourdomain.com (optional)"
    TRAEFIK_EXISTS=true
else
    echo "Setting up Traefik for reverse proxy and SSL..."
    mkdir -p /opt/traefik
    cat > /opt/traefik/docker-compose.yml << 'EOF'
version: '3.8'

services:
  traefik:
    image: traefik:v2.10
    container_name: traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik.yml:/etc/traefik/traefik.yml:ro
      - ./acme.json:/acme.json
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.traefik.rule=Host(`traefik.yourdomain.com`)"
      - "traefik.http.routers.traefik.service=api@internal"
      - "traefik.http.routers.traefik.middlewares=auth"
      - "traefik.http.middlewares.auth.basicauth.users=admin:$$2y$$10$$hashed_password_here"
    networks:
      - traefik_network

networks:
  traefik_network:
    external: true
EOF

    cat > /opt/traefik/traefik.yml << 'EOF'
api:
  dashboard: true
  insecure: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entrypoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    network: traefik_network

certificatesResolvers:
  letsencrypt:
    acme:
      email: your-email@example.com
      storage: acme.json
      httpChallenge:
        entryPoint: web
EOF

    touch /opt/traefik/acme.json
    chmod 600 /opt/traefik/acme.json
    
    # Create external network if it doesn't exist
    docker network create traefik_network 2>/dev/null || echo "Network traefik_network already exists"
    
    TRAEFIK_EXISTS=false
fi

# Create directories for staging and production
echo "Creating deployment directories..."
sudo mkdir -p /opt/pdf2html-api-staging
sudo mkdir -p /opt/pdf2html-api-production
sudo mkdir -p /opt/pdf2html-api-staging/logs
sudo mkdir -p /opt/pdf2html-api-production/logs
sudo mkdir -p /opt/pdf2html-api-production/backups

# Set proper permissions
sudo chown -R $USER:$USER /opt/pdf2html-api-staging
sudo chown -R $USER:$USER /opt/pdf2html-api-production
if [ "$TRAEFIK_EXISTS" = false ]; then
    sudo chown -R $USER:$USER /opt/traefik
fi

# Create environment files
echo "Creating environment files..."
cat > /opt/pdf2html-api-staging/.env << 'EOF'
DOCKER_USERNAME=your-docker-username
OPENAI_API_KEY=your-openai-api-key
ENVIRONMENT=staging
EOF

cat > /opt/pdf2html-api-production/.env << 'EOF'
DOCKER_USERNAME=your-docker-username
OPENAI_API_KEY=your-openai-api-key
ENVIRONMENT=production
EOF

# Copy docker-compose files with network configuration
echo "Creating docker-compose files..."
cat > /opt/pdf2html-api-staging/docker-compose.yml << 'EOF'
version: '3.8'

services:
  pdf2html-api:
    image: ${DOCKER_USERNAME}/pdf2html-api:staging
    container_name: pdf2html-api-staging
    ports:
      - "8001:8000"  # Using different port to avoid conflicts
    environment:
      - HOST=0.0.0.0
      - PORT=8000
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ENVIRONMENT=staging
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.pdf2html-staging.rule=Host(`staging.pdf2html.yourdomain.com`)"
      - "traefik.http.routers.pdf2html-staging.tls=true"
      - "traefik.http.services.pdf2html-staging.loadbalancer.server.port=8000"
    networks:
      - traefik_network

networks:
  traefik_network:
    external: true
EOF

cat > /opt/pdf2html-api-production/docker-compose.yml << 'EOF'
version: '3.8'

services:
  pdf2html-api:
    image: ${DOCKER_USERNAME}/pdf2html-api:production
    container_name: pdf2html-api-production
    ports:
      - "8002:8000"  # Using different port to avoid conflicts
    environment:
      - HOST=0.0.0.0
      - PORT=8000
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ENVIRONMENT=production
    volumes:
      - ./logs:/app/logs
      - ./backups:/app/backups
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.pdf2html-production.rule=Host(`api.pdf2html.yourdomain.com`)"
      - "traefik.http.routers.pdf2html-production.tls=true"
      - "traefik.http.services.pdf2html-production.loadbalancer.server.port=8000"
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    networks:
      - traefik_network

networks:
  traefik_network:
    external: true
EOF

# Start Traefik if we set it up
if [ "$TRAEFIK_EXISTS" = false ]; then
    echo "Starting Traefik..."
    cd /opt/traefik
    docker-compose up -d
fi

# Create systemd service for auto-start
echo "Creating systemd services..."
sudo tee /etc/systemd/system/pdf2html-staging.service > /dev/null << 'EOF'
[Unit]
Description=PDF2HTML API Staging
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/pdf2html-api-staging
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/pdf2html-production.service > /dev/null << 'EOF'
[Unit]
Description=PDF2HTML API Production
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/pdf2html-api-production
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable services
sudo systemctl enable pdf2html-staging.service
sudo systemctl enable pdf2html-production.service

# Setup firewall (only if not already configured)
if ! sudo ufw status | grep -q "Status: active"; then
    echo "Setting up firewall..."
    sudo ufw allow 22/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw --force enable
else
    echo "Firewall already active. Please ensure ports 80, 443, 8001, and 8002 are allowed."
fi

# Setup log rotation
echo "Setting up log rotation..."
sudo tee /etc/logrotate.d/pdf2html-api > /dev/null << 'EOF'
/opt/pdf2html-api-*/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        docker exec pdf2html-api-staging kill -HUP 1 || true
        docker exec pdf2html-api-production kill -HUP 1 || true
    endscript
}
EOF

echo "Server setup completed!"
echo ""
echo "Summary of what was configured:"
echo "✅ Docker and Docker Compose (if not already installed)"
echo "✅ Traefik reverse proxy (if not already running)"
echo "✅ PDF2HTML API staging environment at /opt/pdf2html-api-staging"
echo "✅ PDF2HTML API production environment at /opt/pdf2html-api-production"
echo "✅ Systemd services for auto-start"
echo "✅ Log rotation configuration"
echo ""
echo "Port assignments:"
echo "- Staging API: localhost:8001 (staging.pdf2html.yourdomain.com)"
echo "- Production API: localhost:8002 (api.pdf2html.yourdomain.com)"
echo ""
echo "Next steps:"
echo "1. Update the .env files with your actual credentials:"
echo "   - /opt/pdf2html-api-staging/.env"
echo "   - /opt/pdf2html-api-production/.env"
echo "2. Update the Traefik configuration with your domain"
echo "3. Configure your DNS to point to this server"
echo "4. Test the deployment with: docker-compose up -d"
echo ""
echo "Remember to:"
echo "- Replace 'your-docker-username' with your actual Docker Hub username"
echo "- Replace 'your-openai-api-key' with your actual OpenAI API key"
echo "- Replace 'yourdomain.com' with your actual domain"
echo "- Replace 'your-email@example.com' with your actual email for Let's Encrypt"
echo ""
echo "If you have existing Traefik, ensure it's configured to handle the PDF2HTML API domains." 