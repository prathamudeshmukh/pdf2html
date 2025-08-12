#!/bin/bash

# Deployment script for PDF2HTML API
# Usage: ./deploy.sh [staging|production] [rollback]

set -e

ENVIRONMENT=${1:-staging}
ACTION=${2:-deploy}

if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo "Error: Environment must be 'staging' or 'production'"
    exit 1
fi

DEPLOY_DIR="/opt/pdf2html-api-$ENVIRONMENT"
SERVICE_NAME="pdf2html-$ENVIRONMENT"

# Set port based on environment
if [ "$ENVIRONMENT" = "staging" ]; then
    HEALTH_PORT="8001"
else
    HEALTH_PORT="8002"
fi

echo "Starting $ACTION for $ENVIRONMENT environment..."

cd "$DEPLOY_DIR"

case $ACTION in
    "deploy")
        echo "Pulling latest image..."
        docker-compose pull
        
        echo "Stopping current containers..."
        docker-compose down
        
        echo "Starting new containers..."
        docker-compose up -d
        
        echo "Waiting for health check..."
        sleep 30
        
        echo "Checking service health..."
        if curl -f http://localhost:$HEALTH_PORT/health > /dev/null 2>&1; then
            echo "✅ Deployment successful!"
            
            # Clean up old images
            echo "Cleaning up old images..."
            docker image prune -f
            
            # Create backup
            echo "Creating backup..."
            docker-compose exec -T pdf2html-api tar czf /app/backups/backup-$(date +%Y%m%d-%H%M%S).tar.gz /app/logs 2>/dev/null || true
        else
            echo "❌ Health check failed! Rolling back..."
            docker-compose down
            docker-compose up -d
            exit 1
        fi
        ;;
        
    "rollback")
        echo "Rolling back to previous version..."
        
        # Stop current containers
        docker-compose down
        
        # Pull the previous image tag
        if [ "$ENVIRONMENT" = "production" ]; then
            docker pull ${DOCKER_USERNAME}/pdf2html-api:latest
        else
            docker pull ${DOCKER_USERNAME}/pdf2html-api:staging
        fi
        
        # Start containers
        docker-compose up -d
        
        echo "Rollback completed!"
        ;;
        
    "restart")
        echo "Restarting services..."
        docker-compose restart
        echo "Restart completed!"
        ;;
        
    "logs")
        echo "Showing logs..."
        docker-compose logs -f
        ;;
        
    "status")
        echo "Service status:"
        docker-compose ps
        echo ""
        echo "Health check:"
        curl -s http://localhost:$HEALTH_PORT/health | jq . || echo "Health check failed"
        ;;
        
    *)
        echo "Unknown action: $ACTION"
        echo "Available actions: deploy, rollback, restart, logs, status"
        exit 1
        ;;
esac 