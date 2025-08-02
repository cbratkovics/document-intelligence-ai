#!/bin/bash
set -euo pipefail

echo "=== Docker Debug Build ==="

# Clean everything first
echo "Cleaning Docker system..."
docker system prune -f

# Build with progress and debug
echo "Building image with debug output..."
DOCKER_BUILDKIT=1 docker build \
  --progress=plain \
  --no-cache \
  -f docker/Dockerfile \
  -t cbratkovics/document-intelligence-ai:debug \
  . 2>&1 | tee build-debug.log

# Analyze the image
echo "Analyzing image layers..."
docker history cbratkovics/document-intelligence-ai:debug --no-trunc --format "table {{.CreatedBy}}\t{{.Size}}"

# Check for large layers
echo "Checking for layers over 100MB..."
docker history cbratkovics/document-intelligence-ai:debug --format "{{.Size}}\t{{.CreatedBy}}" | grep -E "([0-9]{3,}MB|GB)"

# Try a test push to see exact error
echo "Attempting test push..."
docker tag cbratkovics/document-intelligence-ai:debug cbratkovics/document-intelligence-ai:test-$(date +%s)
docker push cbratkovics/document-intelligence-ai:test-$(date +%s) || true