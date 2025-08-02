# Optimized Docker Solution for Document Intelligence AI

This directory contains an optimized Docker solution that reduces image size from 3.31GB to < 1GB while maintaining all functionality through lazy-loading of ML models.

## 📁 Files Overview

### Core Files
- **`Dockerfile.optimized`** - Multi-stage optimized Dockerfile with three targets
- **`docker-compose.optimized.yml`** - Optimized compose file with profiles and volumes
- **`.dockerignore`** - Comprehensive ignore file to reduce build context

### Requirements Files
- **`requirements-base.txt`** - Core dependencies (FastAPI, basic libraries)
- **`requirements-ml.txt`** - ML dependencies (sentence-transformers, PyTorch)
- **`requirements-dev.txt`** - Development dependencies (testing, code quality)

### Scripts
- **`scripts/init_models.py`** - Model initialization script for lazy loading
- **`scripts/build_optimized.sh`** - Build script for all image variants
- **`scripts/verify_image_size.sh`** - Size verification script

## 🎯 Optimization Strategy

### 1. Multi-Stage Build Architecture

The Dockerfile uses a multi-stage approach with three targets:

```
Builder Stage → Runtime Stage → ML Runtime → Dev Runtime
    (build)         (base)        (optional)    (optional)
```

### 2. Lazy Model Loading

Instead of baking ML models into the image:
- Models are downloaded on first use
- Cached in persistent volumes
- Reduces image size by ~2GB
- Faster container startup

### 3. Layer Optimization

- Combined RUN commands to reduce layers
- Package manager cache cleanup
- Build dependencies removed in final stage
- No layer exceeds 500MB

## 🚀 Usage

### Quick Start

1. **Build optimized images:**
   ```bash
   cd docker
   ./scripts/build_optimized.sh
   ```

2. **Verify image sizes:**
   ```bash
   ./scripts/verify_image_size.sh
   ```

3. **Start services:**
   ```bash
   # Base runtime (API-only, ~600MB)
   docker-compose -f docker-compose.optimized.yml up

   # With ML capabilities (~900MB + models downloaded on demand)
   docker-compose -f docker-compose.optimized.yml --profile ml up

   # Development environment
   docker-compose -f docker-compose.optimized.yml --profile dev up
   ```

### Image Variants

#### 1. Base Runtime (`document-intelligence-ai:optimized`)
- **Size:** ~600MB
- **Use case:** Production API with OpenAI embeddings
- **Features:** FastAPI, Redis, ChromaDB client
- **ML Models:** None (uses OpenAI API)

#### 2. ML Runtime (`document-intelligence-ai:ml-optimized`)
- **Size:** ~900MB (without models)
- **Use case:** Production with local ML models
- **Features:** Base + sentence-transformers
- **ML Models:** Downloaded on first use

#### 3. Dev Runtime (`document-intelligence-ai:dev-optimized`)
- **Size:** ~1GB
- **Use case:** Development and testing
- **Features:** ML + dev tools, hot reload
- **ML Models:** Downloaded on first use

### Environment Variables

```bash
# Model caching
MODEL_CACHE_DIR=/app/models
HF_HOME=/app/models
TRANSFORMERS_CACHE=/app/models

# Feature flags
USE_LOCAL_MODELS=true  # Enable local ML models

# External services
OPENAI_API_KEY=your_key_here
REDIS_URL=redis://redis:6379
CHROMA_HOST=chromadb
CHROMA_PORT=8000
```

## 📊 Size Comparison

| Component | Original | Optimized | Savings |
|-----------|----------|-----------|---------|
| Base Image | 3.31GB | 600MB | 82% |
| With ML | 3.31GB | 900MB | 73% |
| Build Context | 500MB | 50MB | 90% |

## 🔧 Development Workflow

### Building Images

```bash
# Build all variants
./scripts/build_optimized.sh

# Build specific variant
./scripts/build_optimized.sh --base-only
./scripts/build_optimized.sh --ml-only
./scripts/build_optimized.sh --dev-only

# Build without cleanup
CLEANUP=false ./scripts/build_optimized.sh
```

### Running Services

```bash
# Production (base runtime)
docker-compose -f docker-compose.optimized.yml up -d

# With monitoring
docker-compose -f docker-compose.optimized.yml --profile monitoring up -d

# Development
docker-compose -f docker-compose.optimized.yml --profile dev up

# ML-enabled
docker-compose -f docker-compose.optimized.yml --profile ml up
```

### Model Management

```bash
# Initialize models manually
docker run --rm -v model_cache:/app/models \\
  document-intelligence-ai:ml-optimized \\
  python scripts/init_models.py

# Check model status
docker run --rm -v model_cache:/app/models \\
  document-intelligence-ai:ml-optimized \\
  python scripts/init_models.py --info

# Force re-initialization
docker run --rm -v model_cache:/app/models \\
  document-intelligence-ai:ml-optimized \\
  python scripts/init_models.py --force
```

## 🔍 Monitoring and Health Checks

### Health Endpoints

- **`/health`** - Comprehensive health check
- **`/ready`** - Kubernetes readiness probe
- **`/metrics`** - Prometheus metrics

### Verification

```bash
# Check image sizes
./scripts/verify_image_size.sh

# Custom size limits
./scripts/verify_image_size.sh --size 2 --layer 750

# Check specific image
./scripts/verify_image_size.sh --image document-intelligence-ai:optimized
```

## 🛠️ Troubleshooting

### Common Issues

1. **Image too large:**
   ```bash
   # Check layer sizes
   docker history document-intelligence-ai:optimized
   
   # Analyze what's taking space
   docker run --rm document-intelligence-ai:optimized du -sh /*
   ```

2. **Models not downloading:**
   ```bash
   # Check model initialization logs
   docker logs <container_id>
   
   # Manually initialize
   docker exec <container_id> python scripts/init_models.py --force
   ```

3. **Build failures:**
   ```bash
   # Clean build cache
   docker builder prune -a
   
   # Build with more verbose output
   DOCKER_BUILDKIT=0 docker build --no-cache -f docker/Dockerfile.optimized .
   ```

### Performance Tuning

```bash
# Resource limits in docker-compose.optimized.yml
deploy:
  resources:
    limits:
      memory: 1G      # Adjust based on needs
      cpus: '1.0'
    reservations:
      memory: 512M
      cpus: '0.5'
```

## 📈 Best Practices

1. **Use appropriate variant for your needs:**
   - Base runtime for API-only deployments
   - ML runtime when you need local models
   - Dev runtime only for development

2. **Persistent volumes for models:**
   - Models are cached between container restarts
   - Reduces startup time after first initialization

3. **Health checks:**
   - Configure appropriate timeouts
   - ML variant needs longer startup time

4. **Resource management:**
   - Set memory limits based on model requirements
   - Monitor actual usage and adjust

5. **Security:**
   - Use non-root user (already configured)
   - Scan images for vulnerabilities
   - Keep base images updated

## 🔄 Migration from Original

To migrate from the original Docker setup:

1. **Build new images:**
   ```bash
   ./scripts/build_optimized.sh
   ```

2. **Update environment variables:**
   ```bash
   # Add model cache variables
   MODEL_CACHE_DIR=/app/models
   USE_LOCAL_MODELS=true  # if using ML variant
   ```

3. **Switch compose files:**
   ```bash
   # Stop old services
   docker-compose -f docker-compose.yml down
   
   # Start optimized services
   docker-compose -f docker-compose.optimized.yml up -d
   ```

4. **Initialize models (if using ML variant):**
   ```bash
   # Models will initialize automatically on first use
   # Or manually: python scripts/init_models.py
   ```

## 📝 Configuration Reference

### Docker Build Args

- `BUILDKIT_INLINE_CACHE=1` - Enable build cache
- Custom base image can be specified in Dockerfile

### Volume Mounts

- `model_cache:/app/models` - Persistent model storage
- `../data:/app/data` - Application data
- `../logs:/app/logs` - Application logs
- `../src:/app/src` - Source code (dev only)

### Profiles

- `ml` - Enable ML-capable services
- `dev` - Enable development services
- `monitoring` - Enable Prometheus/Grafana

This optimized solution maintains full functionality while dramatically reducing image size and improving deployment efficiency.