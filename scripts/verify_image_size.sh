#!/bin/bash

# Script to verify Docker image sizes and layer breakdown

set -e

echo "🔍 Docker Image Size Verification"
echo "================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to format bytes to human readable
format_bytes() {
    local bytes=$1
    if [ $bytes -lt 1024 ]; then
        echo "${bytes}B"
    elif [ $bytes -lt 1048576 ]; then
        echo "$(awk "BEGIN {printf \"%.1f\", $bytes/1024}")KB"
    elif [ $bytes -lt 1073741824 ]; then
        echo "$(awk "BEGIN {printf \"%.1f\", $bytes/1048576}")MB"
    else
        echo "$(awk "BEGIN {printf \"%.2f\", $bytes/1073741824}")GB"
    fi
}

# Check if image name is provided
IMAGE_NAME=${1:-"document-intelligence-ai:ml"}

echo -e "\nChecking image: ${YELLOW}$IMAGE_NAME${NC}"

# Get image size
IMAGE_SIZE=$(docker inspect $IMAGE_NAME --format='{{.Size}}' 2>/dev/null || echo 0)

if [ $IMAGE_SIZE -eq 0 ]; then
    echo -e "${RED}✗ Image not found: $IMAGE_NAME${NC}"
    exit 1
fi

IMAGE_SIZE_HUMAN=$(format_bytes $IMAGE_SIZE)

# Check if image is under 1GB
if [ $IMAGE_SIZE -lt 1073741824 ]; then
    echo -e "${GREEN}✓ Total image size: $IMAGE_SIZE_HUMAN (under 1GB target)${NC}"
else
    echo -e "${RED}✗ Total image size: $IMAGE_SIZE_HUMAN (exceeds 1GB target)${NC}"
fi

# Get layer information
echo -e "\n${YELLOW}Layer breakdown:${NC}"
echo "=================="

# Get layer sizes
docker history $IMAGE_NAME --format "table {{.CreatedBy}}\t{{.Size}}" | head -20 | while IFS=$'\t' read -r created size; do
    # Skip header
    if [[ $created == "CREATED BY" ]]; then
        continue
    fi
    
    # Parse size
    if [[ $size == "0B" ]]; then
        continue
    fi
    
    # Convert size to bytes for comparison
    size_bytes=0
    if [[ $size =~ ([0-9.]+)([KMGT]?B) ]]; then
        num=${BASH_REMATCH[1]}
        unit=${BASH_REMATCH[2]}
        
        case $unit in
            "B") size_bytes=$(echo "$num" | awk '{print int($1)}') ;;
            "KB") size_bytes=$(echo "$num" | awk '{print int($1 * 1024)}') ;;
            "MB") size_bytes=$(echo "$num" | awk '{print int($1 * 1048576)}') ;;
            "GB") size_bytes=$(echo "$num" | awk '{print int($1 * 1073741824)}') ;;
        esac
    fi
    
    # Truncate command for display
    cmd_display=$(echo "$created" | cut -c1-60)
    if [ ${#created} -gt 60 ]; then
        cmd_display="${cmd_display}..."
    fi
    
    # Check if layer exceeds 500MB
    if [ $size_bytes -gt 524288000 ]; then
        echo -e "${RED}✗ $size\t$cmd_display${NC}"
    else
        echo -e "${GREEN}✓ $size\t$cmd_display${NC}"
    fi
done

# Summary
echo -e "\n${YELLOW}Summary:${NC}"
echo "========="

# Count layers over 500MB
LARGE_LAYERS=$(docker history $IMAGE_NAME --format "{{.Size}}" | grep -E "[5-9][0-9]{2}MB|[0-9]+GB" | wc -l)

if [ $LARGE_LAYERS -eq 0 ]; then
    echo -e "${GREEN}✓ No layers exceed 500MB${NC}"
else
    echo -e "${RED}✗ $LARGE_LAYERS layer(s) exceed 500MB${NC}"
fi

if [ $IMAGE_SIZE -lt 1073741824 ] && [ $LARGE_LAYERS -eq 0 ]; then
    echo -e "${GREEN}✓ Image meets all size requirements!${NC}"
else
    echo -e "${RED}✗ Image does not meet size requirements${NC}"
fi

# Show top 5 largest layers
echo -e "\n${YELLOW}Top 5 largest layers:${NC}"
docker history $IMAGE_NAME --format "table {{.Size}}\t{{.CreatedBy}}" | \
    grep -v "CREATED BY" | \
    grep -v "0B" | \
    sort -k1 -hr | \
    head -5 | \
    while IFS=$'\t' read -r size cmd; do
        cmd_display=$(echo "$cmd" | cut -c1-50)
        if [ ${#cmd} -gt 50 ]; then
            cmd_display="${cmd_display}..."
        fi
        echo "  $size - $cmd_display"
    done