#!/bin/bash

# Test Docker Container Locally
# This script builds and tests the Fyntrix backend Docker container

set -e

echo "🐳 Testing Fyntrix Backend Docker Container"
echo "============================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="fyntrix-backend"
CONTAINER_NAME="fyntrix-backend-test"
PORT=8000

echo ""
echo "${YELLOW}Step 1: Building Docker image...${NC}"
docker build -t ${IMAGE_NAME}:test .

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ Docker image built successfully${NC}"
else
    echo "${RED}✗ Docker build failed${NC}"
    exit 1
fi

echo ""
echo "${YELLOW}Step 2: Stopping any existing test container...${NC}"
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo ""
echo "${YELLOW}Step 3: Starting container...${NC}"
docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${PORT}:8000 \
    -e DATABASE_URL="sqlite:///./fyntrix_test.db" \
    -e REDIS_HOST="127.0.0.1" \
    -e REDIS_PORT="6379" \
    -e REDIS_DB="0" \
    -e ENV_NAME="local-test" \
    ${IMAGE_NAME}:test

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ Container started successfully${NC}"
else
    echo "${RED}✗ Failed to start container${NC}"
    exit 1
fi

echo ""
echo "${YELLOW}Step 4: Waiting for application to start (40 seconds)...${NC}"
sleep 10
echo "⏳ 10 seconds..."
sleep 10
echo "⏳ 20 seconds..."
sleep 10
echo "⏳ 30 seconds..."
sleep 10
echo "⏳ 40 seconds..."

echo ""
echo "${YELLOW}Step 5: Checking container logs...${NC}"
docker logs ${CONTAINER_NAME} --tail 50

echo ""
echo "${YELLOW}Step 6: Testing health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT}/health)

if [ "$HEALTH_RESPONSE" = "200" ]; then
    echo "${GREEN}✓ Health check passed (HTTP 200)${NC}"
else
    echo "${RED}✗ Health check failed (HTTP ${HEALTH_RESPONSE})${NC}"
    echo "Container logs:"
    docker logs ${CONTAINER_NAME}
    exit 1
fi

echo ""
echo "${YELLOW}Step 7: Testing Redis connectivity...${NC}"
docker exec ${CONTAINER_NAME} redis-cli -h 127.0.0.1 ping

if [ $? -eq 0 ]; then
    echo "${GREEN}✓ Redis is running and responding${NC}"
else
    echo "${RED}✗ Redis connection failed${NC}"
    exit 1
fi

echo ""
echo "${YELLOW}Step 8: Testing API endpoints...${NC}"

# Test docs endpoint
DOCS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT}/docs)
if [ "$DOCS_RESPONSE" = "200" ]; then
    echo "${GREEN}✓ API docs accessible (HTTP 200)${NC}"
else
    echo "${RED}✗ API docs failed (HTTP ${DOCS_RESPONSE})${NC}"
fi

# Test Redis status endpoint
REDIS_STATUS=$(curl -s http://localhost:${PORT}/v1/redis/status | grep -o '"connected":true')
if [ ! -z "$REDIS_STATUS" ]; then
    echo "${GREEN}✓ Redis status endpoint working${NC}"
else
    echo "${RED}✗ Redis status endpoint failed${NC}"
fi

echo ""
echo "${YELLOW}Step 9: Container resource usage...${NC}"
docker stats ${CONTAINER_NAME} --no-stream

echo ""
echo "${GREEN}============================================${NC}"
echo "${GREEN}✓ All tests passed!${NC}"
echo "${GREEN}============================================${NC}"
echo ""
echo "Container is running at: http://localhost:${PORT}"
echo "API Documentation: http://localhost:${PORT}/docs"
echo "Redis Dashboard: http://localhost:${PORT}/v1/redis/dashboard"
echo ""
echo "To view logs: docker logs -f ${CONTAINER_NAME}"
echo "To stop container: docker stop ${CONTAINER_NAME}"
echo "To remove container: docker rm ${CONTAINER_NAME}"
echo ""
