#!/usr/bin/env python3
"""Health check script for Docker containers."""

import sys
import importlib

def check_core_dependencies():
    """Check if core dependencies are available."""
    required_modules = [
        "fastapi",
        "uvicorn", 
        "pydantic",
        "redis",
        "httpx",
        "prometheus_client"
    ]
    
    missing = []
    for module in required_modules:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    
    if missing:
        print(f"ERROR: Missing core dependencies: {', '.join(missing)}")
        return False
    
    print("✓ Core dependencies OK")
    return True

def check_ml_dependencies():
    """Check if ML dependencies are available."""
    ml_modules = [
        "langchain",
        "chromadb",
        "pandas",
        "celery"
    ]
    
    available = []
    missing = []
    
    for module in ml_modules:
        try:
            importlib.import_module(module)
            available.append(module)
        except ImportError:
            missing.append(module)
    
    if available:
        print(f"✓ ML dependencies available: {', '.join(available)}")
    if missing:
        print(f"ℹ ML dependencies missing: {', '.join(missing)}")
        print("  (This is OK for base runtime)")
    
    return len(available) > 0

def main():
    """Run health checks."""
    print("=== Docker Health Check ===")
    print(f"Python {sys.version}")
    
    # Core dependencies are required
    if not check_core_dependencies():
        sys.exit(1)
    
    # ML dependencies are optional
    check_ml_dependencies()
    
    # Try to import config without full app
    try:
        from src.core.config import settings
        print(f"✓ Configuration loaded: {settings.app_name} v{settings.app_version}")
    except Exception as e:
        print(f"⚠ Could not load configuration: {e}")
    
    print("\n✓ Health check passed!")

if __name__ == "__main__":
    main()