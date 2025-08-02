#!/bin/bash

# Script to build optimized Docker images

set -e

echo "🔧 Building Optimized Docker Images"
echo "=================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Build base runtime
echo -e "\n${YELLOW}Building base runtime (API-only)...${NC}"
docker build -f docker/Dockerfile.optimized \
    --target runtime-base \
    -t document-intelligence-ai:base \
    .

# Build ML runtime without sentence-transformers
echo -e "\n${YELLOW}Building ML runtime (without sentence-transformers)...${NC}"
docker build -f docker/Dockerfile.optimized \
    --target runtime-ml \
    -t document-intelligence-ai:ml \
    .

# Build development image
echo -e "\n${YELLOW}Building development image...${NC}"
docker build -f docker/Dockerfile.optimized \
    --target development \
    -t document-intelligence-ai:dev \
    .

# Display sizes
echo -e "\n${GREEN}=== Image Sizes ===${NC}"
docker images | grep -E "document-intelligence|REPOSITORY" | head -10

# Verify sizes
echo -e "\n${YELLOW}Verifying image sizes...${NC}"

# Check base image
BASE_SIZE=$(docker inspect document-intelligence-ai:base --format='{{.Size}}' 2>/dev/null || echo 0)
BASE_SIZE_MB=$((BASE_SIZE / 1048576))

if [ $BASE_SIZE_MB -lt 500 ]; then
    echo -e "${GREEN}✓ Base image: ${BASE_SIZE_MB}MB (under 500MB)${NC}"
else
    echo -e "${RED}✗ Base image: ${BASE_SIZE_MB}MB (exceeds 500MB)${NC}"
fi

# Check ML image
ML_SIZE=$(docker inspect document-intelligence-ai:ml --format='{{.Size}}' 2>/dev/null || echo 0)
ML_SIZE_MB=$((ML_SIZE / 1048576))

if [ $ML_SIZE_MB -lt 1024 ]; then
    echo -e "${GREEN}✓ ML image: ${ML_SIZE_MB}MB (under 1GB)${NC}"
else
    echo -e "${YELLOW}⚠ ML image: ${ML_SIZE_MB}MB (exceeds 1GB target)${NC}"
    echo -e "${YELLOW}  Note: sentence-transformers will be downloaded on first use${NC}"
fi

# Summary
echo -e "\n${GREEN}=== Build Summary ===${NC}"
echo "Base runtime: ${BASE_SIZE_MB}MB - API-only mode using OpenAI embeddings"
echo "ML runtime: ${ML_SIZE_MB}MB - Includes ML dependencies (models downloaded on demand)"
echo ""
echo "To use:"
echo "  Base: docker run -p 8000:8000 document-intelligence-ai:base"
echo "  ML:   docker run -p 8000:8000 -v ml-models:/app/models document-intelligence-ai:ml"