#!/bin/bash

# Deployment script for multi-environment projects using docker-compose
# Usage: ./scripts/deploy.sh [staging|production]

set -e

ENVIRONMENT=${1:-staging}
SERVER_USER=${HETZNER_USER:-root}
SERVER_HOST=${HETZNER_HOST}
PROJECT_NAME="pdf2html-api"
PROJECT_DIR="/home/$SERVER_USER/$PROJECT_NAME-$ENVIRONMENT"

if [ -z "$SERVER_HOST" ]; then
    echo "Error: HETZNER_HOST environment variable is not set"
    exit 1
fi

case $ENVIRONMENT in
    "staging"|"production")
        echo "Deploying to $ENVIRONMENT environment..."
        ;;
    *)
        echo "Error: Invalid environment. Use 'staging' or 'production'"
        exit 1
        ;;
esac

# Set environment-specific variables
if [ "$ENVIRONMENT" = "production" ]; then
    SERVICE_NAME="$PROJECT_NAME-prod"
    PORT="8000"
else
    SERVICE_NAME="$PROJECT_NAME-staging"
    PORT="8001"
fi

# Remove existing container with the same name if it exists
if docker ps -a --format '{{.Names}}' | grep -Eq "^$SERVICE_NAME$"; then
  docker rm -f $SERVICE_NAME
fi

set -e
cd $PROJECT_DIR

# Export environment variables for docker-compose
export BEARER_TOKEN_STAGING
export BEARER_TOKEN_PROD
export SENTRY_DSN
export PDFTRON_LICENSE_KEY
export OPENAI_API_KEY

docker compose pull $SERVICE_NAME || true
docker compose up -d --build $SERVICE_NAME
sleep 5
if ! docker compose ps $SERVICE_NAME | grep -q 'Up'; then \
      echo 'Container failed to start. Logs:' && docker compose logs $SERVICE_NAME && exit 1; \
fi

echo "Deployment to $ENVIRONMENT completed successfully!"
echo "Service: $SERVICE_NAME"
echo "Health check: curl -H 'Authorization: Bearer YOUR_TOKEN' http://$SERVER_HOST:$PORT/health" 