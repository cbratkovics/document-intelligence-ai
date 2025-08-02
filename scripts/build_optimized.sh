#!/bin/bash
# Build script for optimized Docker images
# This script builds all variants of the optimized Docker images

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="document-intelligence-ai"
DOCKER_BUILDKIT=1
BUILD_CONTEXT="../"
DOCKERFILE="docker/Dockerfile.optimized"

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to build image with specified target
build_image() {
    local target=$1
    local tag_suffix=$2
    local description=$3
    
    print_color $BLUE "\n🔨 Building $description..."
    print_color $BLUE "Target: $target"
    print_color $BLUE "Tag: ${IMAGE_NAME}:${tag_suffix}"
    print_color $BLUE "========================================"
    
    local start_time=$(date +%s)
    
    if DOCKER_BUILDKIT=$DOCKER_BUILDKIT docker build \
        --target "$target" \
        --tag "${IMAGE_NAME}:${tag_suffix}" \
        --file "$DOCKERFILE" \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        "$BUILD_CONTEXT"; then
        
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        
        print_color $GREEN "✅ Successfully built ${IMAGE_NAME}:${tag_suffix} in ${duration}s"
        
        # Show image size
        local size=$(docker image inspect "${IMAGE_NAME}:${tag_suffix}" --format='{{.Size}}' | numfmt --to=iec)
        print_color $YELLOW "📏 Image size: $size"
        
        return 0
    else
        print_color $RED "❌ Failed to build ${IMAGE_NAME}:${tag_suffix}"
        return 1
    fi
}

# Function to clean up old images
cleanup_old_images() {
    print_color $BLUE "\n🧹 Cleaning up old images..."
    
    # Remove dangling images
    if docker image prune -f > /dev/null 2>&1; then
        print_color $GREEN "✅ Removed dangling images"
    fi
    
    # Remove old versions of our images (keep only latest)
    for tag in "optimized" "ml-optimized" "dev-optimized"; do
        local old_images=$(docker images "${IMAGE_NAME}" --filter "label=stage=${tag}" --format "{{.ID}}" | tail -n +2)
        if [ -n "$old_images" ]; then
            echo "$old_images" | xargs docker rmi -f > /dev/null 2>&1 || true
            print_color $GREEN "✅ Cleaned up old ${tag} images"
        fi
    done
}

# Function to verify builds
verify_builds() {
    print_color $BLUE "\n🔍 Verifying built images..."
    
    local all_success=true
    local images=("${IMAGE_NAME}:optimized" "${IMAGE_NAME}:ml-optimized" "${IMAGE_NAME}:dev-optimized")
    
    for image in "${images[@]}"; do
        if docker image inspect "$image" >/dev/null 2>&1; then
            local size=$(docker image inspect "$image" --format='{{.Size}}' | numfmt --to=iec)
            print_color $GREEN "✅ $image - Size: $size"
        else
            print_color $RED "❌ $image - Not found"
            all_success=false
        fi
    done
    
    if [ "$all_success" = true ]; then
        print_color $GREEN "🎉 All images built successfully!"
    else
        print_color $RED "❌ Some images failed to build"
        return 1
    fi
}

# Function to show build summary
show_summary() {
    print_color $BLUE "\n📊 Build Summary:"
    print_color $BLUE "=================="
    
    printf "%-30s %-15s %-20s\n" "Image" "Size" "Status"
    printf "%-30s %-15s %-20s\n" "-----" "----" "------"
    
    local images=(
        "${IMAGE_NAME}:optimized|Base Runtime"
        "${IMAGE_NAME}:ml-optimized|ML Runtime" 
        "${IMAGE_NAME}:dev-optimized|Dev Runtime"
    )
    
    for image_info in "${images[@]}"; do
        IFS='|' read -r image description <<< "$image_info"
        
        if docker image inspect "$image" >/dev/null 2>&1; then
            local size=$(docker image inspect "$image" --format='{{.Size}}' | numfmt --to=iec)
            printf "%-30s %-15s %-20s\n" "$description" "$size" "✅ Built"
        else
            printf "%-30s %-15s %-20s\n" "$description" "N/A" "❌ Failed"
        fi
    done
}

# Main build function
main() {
    print_color $GREEN "🐳 Optimized Docker Build Script"
    print_color $GREEN "================================"
    
    # Check for required tools
    if ! command -v docker &> /dev/null; then
        print_color $RED "❌ Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Change to project directory
    cd "$(dirname "$0")/.."
    
    local overall_success=true
    
    # Clean up old images first
    if [ "${CLEANUP:-true}" = "true" ]; then
        cleanup_old_images
    fi
    
    # Build base runtime image (smallest)
    if ! build_image "runtime" "optimized" "Base Runtime Image (API-only, no ML models)"; then
        overall_success=false
    fi
    
    # Build ML runtime image (includes ML dependencies)
    if ! build_image "ml-runtime" "ml-optimized" "ML Runtime Image (includes sentence-transformers)"; then
        overall_success=false
    fi
    
    # Build development image (includes dev tools)
    if ! build_image "dev-runtime" "dev-optimized" "Development Image (includes all dependencies and dev tools)"; then
        overall_success=false
    fi
    
    # Verify all builds
    if ! verify_builds; then
        overall_success=false
    fi
    
    # Show summary
    show_summary
    
    # Final result
    if [ "$overall_success" = true ]; then
        print_color $GREEN "\n🎉 All images built successfully!"
        print_color $YELLOW "\nNext steps:"
        echo "1. Run size verification: ./scripts/verify_image_size.sh"
        echo "2. Start services: docker-compose -f docker/docker-compose.optimized.yml up"
        echo "3. For ML features: docker-compose -f docker/docker-compose.optimized.yml --profile ml up"
        exit 0
    else
        print_color $RED "\n❌ Some builds failed"
        exit 1
    fi
}

# Help function
show_help() {
    echo "Optimized Docker Build Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help      Show this help message"
    echo "  --no-cleanup    Skip cleanup of old images"
    echo "  --base-only     Build only the base runtime image"
    echo "  --ml-only       Build only the ML runtime image"
    echo "  --dev-only      Build only the development image"
    echo ""
    echo "Environment Variables:"
    echo "  DOCKER_BUILDKIT  Enable Docker BuildKit (default: 1)"
    echo "  CLEANUP          Clean up old images (default: true)"
    echo ""
    echo "Examples:"
    echo "  $0                    # Build all images"
    echo "  $0 --base-only        # Build only base image"
    echo "  CLEANUP=false $0      # Build without cleanup"
}

# Parse command line arguments
BASE_ONLY=false
ML_ONLY=false
DEV_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        --base-only)
            BASE_ONLY=true
            shift
            ;;
        --ml-only)
            ML_ONLY=true
            shift
            ;;
        --dev-only)
            DEV_ONLY=true
            shift
            ;;
        *)
            print_color $RED "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Conditional building based on flags
if [ "$BASE_ONLY" = true ]; then
    build_image "runtime" "optimized" "Base Runtime Image"
elif [ "$ML_ONLY" = true ]; then
    build_image "ml-runtime" "ml-optimized" "ML Runtime Image"
elif [ "$DEV_ONLY" = true ]; then
    build_image "dev-runtime" "dev-optimized" "Development Image"
else
    main
fi