#!/usr/bin/env python3
"""
Model initialization script for lazy-loading ML models.

This script downloads and initializes ML models on first use rather than
baking them into the Docker image, significantly reducing image size.
"""

import os
import sys
import logging
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model configurations
MODELS_CONFIG = {
    "sentence_transformer": {
        "name": "all-MiniLM-L6-v2",
        "size_mb": 90,
        "required": False,  # Only load if sentence-transformers is available
        "description": "Lightweight sentence embedding model"
    },
    "reranker": {
        "name": "cross-encoder/ms-marco-MiniLM-L-6-v2", 
        "size_mb": 90,
        "required": False,
        "description": "Cross-encoder reranking model"
    }
}

class ModelInitializer:
    """Handles lazy initialization of ML models"""
    
    def __init__(self, models_dir: str = None):
        self.models_dir = Path(models_dir or os.getenv('MODEL_CACHE_DIR', '/app/models'))
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = self.models_dir / 'init_status.json'
        
    def get_initialization_status(self) -> Dict[str, Any]:
        """Get the current model initialization status"""
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read status file: {e}")
        
        return {
            "initialized": False,
            "models": {},
            "last_update": None,
            "errors": []
        }
    
    def save_initialization_status(self, status: Dict[str, Any]):
        """Save model initialization status"""
        try:
            status["last_update"] = time.time()
            with open(self.status_file, 'w') as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save status file: {e}")
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Check which ML dependencies are available"""
        dependencies = {}
        
        try:
            import sentence_transformers
            dependencies['sentence_transformers'] = True
            logger.info("sentence-transformers is available")
        except ImportError:
            dependencies['sentence_transformers'] = False
            logger.info("sentence-transformers not available - using OpenAI embeddings only")
        
        return dependencies
    
    async def initialize_sentence_transformer(self, model_name: str) -> bool:
        """Initialize sentence transformer model"""
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Initializing SentenceTransformer: {model_name}")
            
            # Download and cache the model
            model = SentenceTransformer(model_name, cache_folder=str(self.models_dir))
            
            # Test the model with a simple embedding
            test_embedding = model.encode("test sentence")
            logger.info(f"Model {model_name} initialized successfully. Embedding dimension: {len(test_embedding)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize {model_name}: {e}")
            return False
    
    async def initialize_reranker_model(self, model_name: str) -> bool:
        """Initialize cross-encoder reranking model"""
        try:
            from sentence_transformers import CrossEncoder
            
            logger.info(f"Initializing CrossEncoder: {model_name}")
            
            # Download and cache the model
            model = CrossEncoder(model_name, cache_folder=str(self.models_dir))
            
            # Test the model
            test_score = model.predict([("test query", "test document")])
            logger.info(f"Reranker model {model_name} initialized successfully. Test score: {test_score}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize reranker {model_name}: {e}")
            return False
    
    async def initialize_models(self, force: bool = False) -> Dict[str, Any]:
        """Initialize all available models"""
        status = self.get_initialization_status()
        
        if status.get("initialized", False) and not force:
            logger.info("Models already initialized. Use --force to reinitialize.")
            return status
        
        logger.info("Starting model initialization...")
        
        # Check dependencies
        dependencies = self.check_dependencies()
        
        # Initialize models based on available dependencies
        errors = []
        models_status = {}
        
        if dependencies.get('sentence_transformers', False):
            # Initialize sentence transformer
            st_config = MODELS_CONFIG["sentence_transformer"]
            success = await self.initialize_sentence_transformer(st_config["name"])
            models_status["sentence_transformer"] = {
                "initialized": success,
                "model_name": st_config["name"],
                "size_mb": st_config["size_mb"] if success else 0
            }
            if not success:
                errors.append(f"Failed to initialize sentence transformer: {st_config['name']}")
            
            # Initialize reranker
            reranker_config = MODELS_CONFIG["reranker"]
            success = await self.initialize_reranker_model(reranker_config["name"])
            models_status["reranker"] = {
                "initialized": success,
                "model_name": reranker_config["name"],
                "size_mb": reranker_config["size_mb"] if success else 0
            }
            if not success:
                errors.append(f"Failed to initialize reranker: {reranker_config['name']}")
        else:
            logger.info("No local ML models will be initialized - using API-based models only")
            models_status["api_only"] = {
                "initialized": True,
                "model_name": "OpenAI API",
                "size_mb": 0
            }
        
        # Update status
        status.update({
            "initialized": True,
            "models": models_status,
            "errors": errors,
            "dependencies": dependencies
        })
        
        self.save_initialization_status(status)
        
        # Log summary
        total_size = sum(model.get("size_mb", 0) for model in models_status.values())
        initialized_count = sum(1 for model in models_status.values() if model.get("initialized", False))
        
        logger.info(f"Model initialization complete:")
        logger.info(f"  - {initialized_count} models initialized")
        logger.info(f"  - Total model size: ~{total_size}MB")
        logger.info(f"  - Errors: {len(errors)}")
        
        if errors:
            for error in errors:
                logger.warning(f"  - {error}")
        
        return status
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about available models"""
        status = self.get_initialization_status()
        dependencies = self.check_dependencies()
        
        return {
            "status": status,
            "dependencies": dependencies,
            "models_config": MODELS_CONFIG,
            "models_dir": str(self.models_dir)
        }


async def main():
    """Main initialization function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize ML models for Document Intelligence AI")
    parser.add_argument("--force", action="store_true", help="Force reinitialization of models")
    parser.add_argument("--info", action="store_true", help="Show model information and exit")
    parser.add_argument("--models-dir", help="Custom models directory")
    
    args = parser.parse_args()
    
    initializer = ModelInitializer(args.models_dir)
    
    if args.info:
        info = initializer.get_model_info()
        print(json.dumps(info, indent=2))
        return
    
    try:
        status = await initializer.initialize_models(force=args.force)
        
        if status.get("errors"):
            logger.warning("Some models failed to initialize, but the application can still run with API-based models")
            sys.exit(1 if len(status["errors"]) == len(MODELS_CONFIG) else 0)
        else:
            logger.info("All available models initialized successfully")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Model initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())