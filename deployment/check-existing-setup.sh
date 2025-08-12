#!/bin/bash

# Script to check existing Docker setup and help configure PDF2HTML API deployment

echo "🔍 Checking your existing Docker setup..."

echo ""
echo "📋 Running Docker containers:"
docker ps --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"

echo ""
echo "🌐 Docker networks:"
docker network ls

echo ""
echo "📁 Docker volumes:"
docker volume ls

echo ""
echo "🔌 Port usage:"
echo "Checking which ports are currently in use..."
netstat -tlnp 2>/dev/null | grep LISTEN | grep -E ':(80|443|8000|8001|8002|3000|9090|8080)' || echo "No relevant ports found in netstat"

echo ""
echo "📊 System resources:"
echo "Memory usage:"
free -h
echo ""
echo "Disk usage:"
df -h /opt /var/lib/docker 2>/dev/null || echo "Could not check disk usage"

echo ""
echo "🔧 Recommendations for PDF2HTML API deployment:"
echo ""

# Check if Traefik exists
if docker ps --format "{{.Names}}" | grep -q "traefik"; then
    echo "✅ Traefik is running - PDF2HTML API will use your existing Traefik"
    echo "   Make sure to configure these domains in your Traefik:"
    echo "   - staging.pdf2html.yourdomain.com"
    echo "   - api.pdf2html.yourdomain.com"
else
    echo "⚠️  No Traefik found - the setup script will install Traefik"
fi

# Check port conflicts
if netstat -tlnp 2>/dev/null | grep -q ":8001"; then
    echo "⚠️  Port 8001 is in use - staging environment may conflict"
else
    echo "✅ Port 8001 is available for staging"
fi

if netstat -tlnp 2>/dev/null | grep -q ":8002"; then
    echo "⚠️  Port 8002 is in use - production environment may conflict"
else
    echo "✅ Port 8002 is available for production"
fi

# Check available disk space
DISK_SPACE=$(df /opt | tail -1 | awk '{print $4}')
DISK_SPACE_GB=$((DISK_SPACE / 1024 / 1024))
if [ $DISK_SPACE_GB -gt 5 ]; then
    echo "✅ Sufficient disk space available ($DISK_SPACE_GB GB)"
else
    echo "⚠️  Low disk space ($DISK_SPACE_GB GB) - consider cleanup"
fi

echo ""
echo "📝 Next steps:"
echo "1. Review the port assignments above"
echo "2. If you have existing Traefik, ensure it can handle the PDF2HTML domains"
echo "3. Run the setup script: ./deployment/setup-server.sh"
echo "4. Update environment files with your credentials"
echo "5. Test the deployment"

echo ""
echo "🔗 Useful commands:"
echo "- View all containers: docker ps -a"
echo "- View container logs: docker logs <container-name>"
echo "- Stop a container: docker stop <container-name>"
echo "- Remove a container: docker rm <container-name>"
echo "- View network details: docker network inspect <network-name>" 