#!/bin/bash

echo "=== Project Setup Verification ==="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Function to check existence
check_exists() {
    if [ -e "$1" ]; then
        echo -e "${GREEN}✓${NC} $2"
        return 0
    else
        echo -e "${RED}✗${NC} $2"
        return 1
    fi
}

echo "1. Checking directory structure..."
check_exists "docker" "docker/"
check_exists "scripts/docker" "scripts/docker/"
check_exists "scripts/setup" "scripts/setup/"
check_exists "docs" "docs/"
check_exists "data/uploads" "data/uploads/"
check_exists "data/models" "data/models/"
check_exists "data/cache" "data/cache/"

echo -e "\n2. Checking Docker files..."
check_exists "docker/Dockerfile" "docker/Dockerfile"
check_exists "docker/docker-compose.yml" "docker/docker-compose.yml"
check_exists "docker/docker-compose.optimized.yml" "docker/docker-compose.optimized.yml"

# Check for files that should NOT exist
if [ ! -f "Dockerfile.optimized" ]; then
    echo -e "${GREEN}✓${NC} No root Dockerfile.optimized"
else
    echo -e "${RED}✗${NC} Root Dockerfile.optimized exists (should be removed)"
fi

echo -e "\n3. Checking requirements files..."
for req in requirements.txt requirements-base.txt requirements-ml.txt requirements-dev.txt; do
    check_exists "$req" "$req"
done

echo -e "\n4. Checking documentation..."
check_exists "README.md" "README.md"
check_exists "docs/ARCHITECTURE.md" "docs/ARCHITECTURE.md"
check_exists "docs/PERFORMANCE.md" "docs/PERFORMANCE.md"
check_exists ".dockerignore" ".dockerignore"
check_exists ".gitignore" ".gitignore"

echo -e "\n5. Checking Python source structure..."
check_exists "src/api/main.py" "src/api/main.py"
check_exists "src/core/config.py" "src/core/config.py"
check_exists "src/rag/retriever.py" "src/rag/retriever.py"
check_exists "tests/test_api.py" "tests/test_api.py"

echo -e "\n6. Docker image status..."
echo "Local images:"
docker images | grep document-intelligence || echo "  No local images found"

echo -e "\n7. Git status..."
if [ -d ".git" ]; then
    echo "Branch: $(git branch --show-current)"
    echo "Modified files: $(git status --porcelain | wc -l)"
else
    echo "Not a git repository"
fi

echo -e "\n=== Verification Complete ==="