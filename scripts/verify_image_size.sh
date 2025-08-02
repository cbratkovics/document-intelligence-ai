#!/bin/bash
# Image size verification script for Document Intelligence AI
# Verifies that Docker images meet size requirements (< 1GB, no layer > 500MB)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MAX_IMAGE_SIZE_GB=1
MAX_LAYER_SIZE_MB=500
IMAGE_NAME_PREFIX="document-intelligence-ai"

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to convert bytes to human readable format
bytes_to_human() {
    local bytes=$1
    if [ $bytes -ge 1073741824 ]; then
        echo "$(echo "scale=2; $bytes/1073741824" | bc)GB"
    elif [ $bytes -ge 1048576 ]; then
        echo "$(echo "scale=2; $bytes/1048576" | bc)MB"
    elif [ $bytes -ge 1024 ]; then
        echo "$(echo "scale=2; $bytes/1024" | bc)KB"
    else
        echo "${bytes}B"
    fi
}

# Function to get image size in bytes
get_image_size() {
    local image_name=$1
    docker image inspect "$image_name" --format='{{.Size}}' 2>/dev/null || echo "0"
}

# Function to analyze image layers
analyze_layers() {
    local image_name=$1
    print_color $BLUE "Analyzing layers for $image_name..."
    
    # Get layer information
    local layers=$(docker history "$image_name" --format "table {{.Size}}\t{{.CreatedBy}}" --no-trunc | tail -n +2)
    local layer_count=0
    local oversized_layers=0
    local total_size=0
    
    echo "$layers" | while IFS=$'\t' read -r size created_by; do
        layer_count=$((layer_count + 1))
        
        # Skip empty layers
        if [[ "$size" == "0B" ]]; then
            continue
        fi
        
        # Convert size to bytes for comparison
        local size_bytes=0
        if [[ "$size" =~ ([0-9.]+)GB ]]; then
            size_bytes=$(echo "${BASH_REMATCH[1]} * 1073741824" | bc | cut -d. -f1)
        elif [[ "$size" =~ ([0-9.]+)MB ]]; then
            size_bytes=$(echo "${BASH_REMATCH[1]} * 1048576" | bc | cut -d. -f1)
        elif [[ "$size" =~ ([0-9.]+)KB ]]; then
            size_bytes=$(echo "${BASH_REMATCH[1]} * 1024" | bc | cut -d. -f1)
        elif [[ "$size" =~ ([0-9.]+)B ]]; then
            size_bytes=${BASH_REMATCH[1]}
        fi
        
        total_size=$((total_size + size_bytes))
        
        # Check if layer exceeds maximum size
        local max_layer_bytes=$((MAX_LAYER_SIZE_MB * 1048576))
        if [ $size_bytes -gt $max_layer_bytes ]; then
            oversized_layers=$((oversized_layers + 1))
            print_color $RED "  ❌ Layer $layer_count: $size (exceeds ${MAX_LAYER_SIZE_MB}MB limit)"
            echo "     Command: $(echo "$created_by" | cut -c1-80)..."
        else
            print_color $GREEN "  ✅ Layer $layer_count: $size"
        fi
    done
    
    echo "$oversized_layers"
}

# Function to verify single image
verify_image() {
    local image_name=$1
    local variant=$2
    
    print_color $BLUE "\n🔍 Verifying image: $image_name ($variant)"
    print_color $BLUE "================================================"
    
    # Check if image exists
    if ! docker image inspect "$image_name" >/dev/null 2>&1; then
        print_color $RED "❌ Image $image_name not found"
        return 1
    fi
    
    # Get image size
    local size_bytes=$(get_image_size "$image_name")
    local size_human=$(bytes_to_human $size_bytes)
    local size_gb=$(echo "scale=2; $size_bytes/1073741824" | bc)
    
    print_color $YELLOW "Image size: $size_human ($size_gb GB)"
    
    # Check image size limit
    local max_size_bytes=$((MAX_IMAGE_SIZE_GB * 1073741824))
    local size_check_passed=true
    
    if [ $size_bytes -gt $max_size_bytes ]; then
        print_color $RED "❌ Image size exceeds ${MAX_IMAGE_SIZE_GB}GB limit"
        size_check_passed=false
    else
        print_color $GREEN "✅ Image size within ${MAX_IMAGE_SIZE_GB}GB limit"
    fi
    
    # Analyze layers
    local oversized_layers=$(analyze_layers "$image_name")
    local layers_check_passed=true
    
    if [ "$oversized_layers" -gt 0 ]; then
        print_color $RED "❌ $oversized_layers layer(s) exceed ${MAX_LAYER_SIZE_MB}MB limit"
        layers_check_passed=false
    else
        print_color $GREEN "✅ All layers within ${MAX_LAYER_SIZE_MB}MB limit"
    fi
    
    # Overall result
    if [ "$size_check_passed" = true ] && [ "$layers_check_passed" = true ]; then
        print_color $GREEN "✅ $variant image verification PASSED"
        return 0
    else
        print_color $RED "❌ $variant image verification FAILED"
        return 1
    fi
}

# Function to show optimization recommendations
show_recommendations() {
    print_color $BLUE "\n💡 Optimization Recommendations:"
    print_color $BLUE "=================================="
    echo "1. Use multi-stage builds to reduce final image size"
    echo "2. Combine RUN commands to reduce layer count"
    echo "3. Remove package manager caches: rm -rf /var/lib/apt/lists/*"
    echo "4. Use .dockerignore to exclude unnecessary files"
    echo "5. Use specific base image tags instead of 'latest'"
    echo "6. Remove development dependencies in production images"
    echo "7. Use --no-cache-dir flag with pip install"
    echo "8. Consider using distroless or alpine base images"
    echo "9. Lazy-load ML models instead of baking them into the image"
    echo "10. Use external volumes for large data and model files"
}

# Function to compare images
compare_images() {
    print_color $BLUE "\n📊 Image Size Comparison:"
    print_color $BLUE "=========================="
    
    printf "%-30s %-15s %-15s\n" "Image" "Size" "Status"
    printf "%-30s %-15s %-15s\n" "-----" "----" "------"
    
    for image in "${IMAGE_NAME_PREFIX}:optimized" "${IMAGE_NAME_PREFIX}:ml-optimized" "${IMAGE_NAME_PREFIX}:dev-optimized"; do
        if docker image inspect "$image" >/dev/null 2>&1; then
            local size_bytes=$(get_image_size "$image")
            local size_human=$(bytes_to_human $size_bytes)
            local max_size_bytes=$((MAX_IMAGE_SIZE_GB * 1073741824))
            local status="✅ OK"
            
            if [ $size_bytes -gt $max_size_bytes ]; then
                status="❌ TOO LARGE"
            fi
            
            printf "%-30s %-15s %-15s\n" "$image" "$size_human" "$status"
        else
            printf "%-30s %-15s %-15s\n" "$image" "N/A" "NOT FOUND"
        fi
    done
}

# Main function
main() {
    print_color $GREEN "🐳 Docker Image Size Verification Script"
    print_color $GREEN "========================================"
    print_color $YELLOW "Target: Images < ${MAX_IMAGE_SIZE_GB}GB, Layers < ${MAX_LAYER_SIZE_MB}MB"
    
    # Check for required commands
    if ! command -v docker &> /dev/null; then
        print_color $RED "❌ Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v bc &> /dev/null; then
        print_color $RED "❌ bc (basic calculator) is not installed"
        print_color $YELLOW "Install with: apt-get install bc (Ubuntu/Debian) or brew install bc (macOS)"
        exit 1
    fi
    
    local overall_success=true
    local images_to_check=(
        "${IMAGE_NAME_PREFIX}:optimized|Base Runtime"
        "${IMAGE_NAME_PREFIX}:ml-optimized|ML Runtime"
        "${IMAGE_NAME_PREFIX}:dev-optimized|Dev Runtime"
    )
    
    # Verify each image
    for image_info in "${images_to_check[@]}"; do
        IFS='|' read -r image_name variant <<< "$image_info"
        
        if ! verify_image "$image_name" "$variant"; then
            overall_success=false
        fi
    done
    
    # Show comparison
    compare_images
    
    # Show recommendations if any image failed
    if [ "$overall_success" = false ]; then
        show_recommendations
    fi
    
    # Final result
    print_color $BLUE "\n🏁 Final Result:"
    print_color $BLUE "================"
    
    if [ "$overall_success" = true ]; then
        print_color $GREEN "🎉 All images passed size verification!"
        exit 0
    else
        print_color $RED "❌ Some images failed size verification"
        exit 1
    fi
}

# Help function
show_help() {
    echo "Docker Image Size Verification Script"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help     Show this help message"
    echo "  -s, --size     Maximum image size in GB (default: $MAX_IMAGE_SIZE_GB)"
    echo "  -l, --layer    Maximum layer size in MB (default: $MAX_LAYER_SIZE_MB)"
    echo "  -i, --image    Specific image to check (can be used multiple times)"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Check all default images"
    echo "  $0 -s 2 -l 750                      # Custom size limits"
    echo "  $0 -i document-intelligence-ai:optimized  # Check specific image"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--size)
            MAX_IMAGE_SIZE_GB="$2"
            shift 2
            ;;
        -l|--layer)
            MAX_LAYER_SIZE_MB="$2"
            shift 2
            ;;
        -i|--image)
            SPECIFIC_IMAGE="$2"
            shift 2
            ;;
        *)
            print_color $RED "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Run main function
main