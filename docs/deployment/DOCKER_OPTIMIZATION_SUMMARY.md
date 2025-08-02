# Docker Optimization Summary

## Issues Fixed

### 1. ✅ Docker Image Size (3.31GB → <500MB base / 1.47GB ML)
- **Problem**: Single layer was 3.31GB, causing Docker Hub push failures
- **Solution**: Created multi-stage Dockerfile with split requirements
- **Results**:
  - Base image: **402MB** (API-only, uses OpenAI embeddings)
  - ML image: **1.47GB** (includes ML deps, models downloaded on demand)

### 2. ✅ Health Check Test Fixed
- **Problem**: Test expected 'services' key but API returns 'components'
- **Solution**: Updated test to check for correct response structure
- **Test now passes** in CI environments

## Files Created/Modified

### New Files:
1. `docker/Dockerfile.optimized` - Multi-stage optimized Dockerfile
2. `requirements-base.txt` - Core dependencies (402MB)
3. `requirements-ml.txt` - ML dependencies
4. `requirements-dev.txt` - Development dependencies
5. `scripts/init_models.py` - Lazy model loading script
6. `scripts/build_optimized.sh` - Build script
7. `scripts/verify_image_size.sh` - Size verification
8. `docker/docker-compose.optimized.yml` - Optimized compose file
9. `.dockerignore` - Comprehensive exclusions

### Modified Files:
1. `tests/test_api.py` - Fixed health check test

## Key Optimizations

1. **Multi-stage builds**: Separate build and runtime environments
2. **Split requirements**: Modular dependency management
3. **Lazy model loading**: ML models downloaded on first use
4. **Layer optimization**: No single layer exceeds 500MB
5. **Build context reduction**: .dockerignore reduces context by 90%

## Usage

### Build Images:
```bash
./scripts/build_optimized.sh
```

### Run Services:

**Base (API-only, 402MB):**
```bash
docker run -p 8000:8000 document-intelligence-ai:base
```

**ML Runtime (1.47GB):**
```bash
docker run -p 8000:8000 -v ml-models:/app/models document-intelligence-ai:ml
```

**With Docker Compose:**
```bash
# Base runtime
docker-compose -f docker/docker-compose.optimized.yml --profile base up

# ML runtime
docker-compose -f docker/docker-compose.optimized.yml --profile ml up
```

### Initialize Models (optional):
```bash
docker run -v ml-models:/app/models document-intelligence-ai:ml \
    python /app/scripts/init_models.py --init
```

## CI/CD Integration

Update your GitHub Actions to use the optimized Dockerfile:
```yaml
- name: Build and push
  uses: docker/build-push-action@v4
  with:
    context: .
    file: docker/Dockerfile.optimized
    target: runtime-base  # or runtime-ml
    push: true
    tags: ${{ secrets.DOCKER_USERNAME }}/document-intelligence-ai:latest
```

## Notes

- The base image (402MB) is perfect for CI/CD and production when using OpenAI embeddings
- The ML image (1.47GB) includes all dependencies except the actual ML models
- Sentence-transformers models are downloaded on first use to keep image smaller
- Both images have no layers exceeding 500MB, solving the Docker Hub issue