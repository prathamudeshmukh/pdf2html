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

# Create deployment directory if it doesn't exist
if [ ! -d "$DEPLOY_DIR" ]; then
    echo "Creating deployment directory: $DEPLOY_DIR"
    sudo mkdir -p "$DEPLOY_DIR"
    sudo mkdir -p "$DEPLOY_DIR/logs"
    if [ "$ENVIRONMENT" = "production" ]; then
        sudo mkdir -p "$DEPLOY_DIR/backups"
    fi
    sudo chown -R $USER:$USER "$DEPLOY_DIR"
fi

cd "$DEPLOY_DIR"

# Create environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file for $ENVIRONMENT..."
    cat > .env << EOF
DOCKER_USERNAME=\${DOCKER_USERNAME:-your-docker-username}
OPENAI_API_KEY=\${OPENAI_API_KEY:-your-openai-api-key}
ENVIRONMENT=$ENVIRONMENT
EOF
    echo "⚠️  Please update the .env file with your actual credentials before deploying"
    echo "   Edit: $DEPLOY_DIR/.env"
    exit 1
fi

# Copy and configure docker-compose file if it doesn't exist
if [ ! -f "docker-compose.yml" ]; then
    echo "Setting up docker-compose.yml for $ENVIRONMENT..."
    
    # Find the project directory (assuming this script is in deployment/)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    
    # Copy the appropriate docker-compose file
    if [ "$ENVIRONMENT" = "staging" ]; then
        cp "$SCRIPT_DIR/docker-compose.staging.yml" docker-compose.yml
        # Modify for nginx compatibility
        sed -i 's/- "8000:8000"/- "8001:8000"/' docker-compose.yml
        sed -i 's/container_name: pdf2html-api/container_name: pdf2html-api-staging/' docker-compose.yml
    else
        cp "$SCRIPT_DIR/docker-compose.production.yml" docker-compose.yml
        # Modify for nginx compatibility
        sed -i 's/- "8000:8000"/- "8002:8000"/' docker-compose.yml
        sed -i 's/container_name: pdf2html-api/container_name: pdf2html-api-production/' docker-compose.yml
    fi
    
fi

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