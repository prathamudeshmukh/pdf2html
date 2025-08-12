#!/bin/bash

# Deployment script for PDF2HTML API - Server Build Version
# Usage: ./deploy.sh [staging|production] [deploy|rollback|restart|logs|status|build]

set -e

ENVIRONMENT=${1:-staging}
ACTION=${2:-deploy}

if [[ ! "$ENVIRONMENT" =~ ^(staging|production)$ ]]; then
    echo "Error: Environment must be 'staging' or 'production'"
    exit 1
fi

# Set port based on environment
if [ "$ENVIRONMENT" = "staging" ]; then
    HEALTH_PORT="8001"
    COMPOSE_FILE="docker-compose.staging.yml"
else
    HEALTH_PORT="8002"
    COMPOSE_FILE="docker-compose.production.yml"
fi

echo "Starting $ACTION for $ENVIRONMENT environment..."

# Ensure we're in the project root directory
if [ ! -f "Dockerfile" ]; then
    echo "Error: Dockerfile not found. Please run this script from the project root directory."
    exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p logs
if [ "$ENVIRONMENT" = "production" ]; then
    mkdir -p backups
fi

# Create environment file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file for $ENVIRONMENT..."
    cat > .env << EOF
OPENAI_API_KEY=your-openai-api-key-here
ENVIRONMENT=$ENVIRONMENT
EOF
    echo "⚠️  Please update the .env file with your actual OpenAI API key before deploying"
    echo "   Edit: .env"
    exit 1
fi

# Function to build Docker image
build_image() {
    local env=$1
    echo "Building Docker image for $env environment..."
    
    # Build the image
    docker build -t pdf2html-api:$env .
    
    # Tag with timestamp for versioning
    docker tag pdf2html-api:$env pdf2html-api:$env-$(date +%Y%m%d-%H%M%S)
    
    echo "✅ Image built successfully: pdf2html-api:$env"
}

case $ACTION in
    "deploy")
        # Build the image locally
        build_image $ENVIRONMENT
        
        echo "Stopping current containers..."
        docker-compose -f deployment/$COMPOSE_FILE down
        
        echo "Starting new containers..."
        docker-compose -f deployment/$COMPOSE_FILE up -d
        
        echo "Waiting for health check..."
        sleep 30
        
        echo "Checking service health..."
        if curl -f http://localhost:$HEALTH_PORT/health > /dev/null 2>&1; then
            echo "✅ Deployment successful!"
            
            # Clean up old images (keep last 3 versions)
            echo "Cleaning up old images..."
            docker image prune -f
            
            # Keep only the last 3 images for this environment
            docker images pdf2html-api:$ENVIRONMENT --format "table {{.Repository}}:{{.Tag}}\t{{.CreatedAt}}" | tail -n +2 | sort -k2 -r | tail -n +4 | awk '{print $1}' | xargs -r docker rmi || true
            
            # Create backup
            echo "Creating backup..."
            docker-compose -f deployment/$COMPOSE_FILE exec -T pdf2html-api tar czf /app/backups/backup-$(date +%Y%m%d-%H%M%S).tar.gz /app/logs 2>/dev/null || true
        else
            echo "❌ Health check failed! Rolling back..."
            docker-compose -f deployment/$COMPOSE_FILE down
            docker-compose -f deployment/$COMPOSE_FILE up -d
            exit 1
        fi
        ;;
        
    "rollback")
        echo "Rolling back to previous version..."
        
        # Stop current containers
        docker-compose -f deployment/$COMPOSE_FILE down
        
        # Find the previous image tag
        PREVIOUS_IMAGE=$(docker images pdf2html-api:$ENVIRONMENT --format "table {{.Repository}}:{{.Tag}}" | tail -n +2 | head -n 1)
        
        if [ -z "$PREVIOUS_IMAGE" ]; then
            echo "❌ No previous image found for rollback!"
            exit 1
        fi
        
        echo "Rolling back to: $PREVIOUS_IMAGE"
        
        # Update docker-compose to use the previous image
        sed -i "s|image: pdf2html-api:$ENVIRONMENT|image: $PREVIOUS_IMAGE|" deployment/$COMPOSE_FILE
        
        # Start containers
        docker-compose -f deployment/$COMPOSE_FILE up -d
        
        echo "✅ Rollback completed!"
        ;;
        
    "build")
        # Just build the image without deploying
        build_image $ENVIRONMENT
        ;;
        
    "restart")
        echo "Restarting services..."
        docker-compose -f deployment/$COMPOSE_FILE restart
        echo "Restart completed!"
        ;;
        
    "logs")
        echo "Showing logs..."
        docker-compose -f deployment/$COMPOSE_FILE logs -f
        ;;
        
    "status")
        echo "Service status:"
        docker-compose -f deployment/$COMPOSE_FILE ps
        echo ""
        echo "Available images:"
        docker images pdf2html-api:$ENVIRONMENT
        echo ""
        echo "Health check:"
        curl -s http://localhost:$HEALTH_PORT/health | jq . || echo "Health check failed"
        ;;
        
    *)
        echo "Unknown action: $ACTION"
        echo "Available actions: deploy, rollback, build, restart, logs, status"
        exit 1
        ;;
esac 