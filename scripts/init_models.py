#!/usr/bin/env python3
"""
Model initialization script for lazy loading of ML models.
Downloads and caches models on first use to reduce Docker image size.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
import time

# Add src to path
sys.path.append('/app')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_CACHE_DIR = Path(os.getenv('MODEL_CACHE_DIR', '/app/models'))
STATUS_FILE = MODEL_CACHE_DIR / 'init_status.json'

# Models to download
MODELS_CONFIG = {
    'sentence-transformers': {
        'models': [
            'sentence-transformers/all-MiniLM-L6-v2',  # Small, fast model
            # Add more models as needed
        ],
        'optional': True,
        'description': 'Sentence transformer models for embeddings'
    }
}

def ensure_directories():
    """Ensure model directories exist"""
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Model cache directory: {MODEL_CACHE_DIR}")

def load_status() -> Dict[str, Any]:
    """Load initialization status"""
    if STATUS_FILE.exists():
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    return {
        'initialized': False,
        'timestamp': None,
        'models': {},
        'errors': []
    }

def save_status(status: Dict[str, Any]):
    """Save initialization status"""
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)

def download_sentence_transformer_models(model_names: List[str]) -> Dict[str, Any]:
    """Download sentence transformer models"""
    results = {}
    
    try:
        from sentence_transformers import SentenceTransformer
        
        for model_name in model_names:
            try:
                logger.info(f"Downloading model: {model_name}")
                start_time = time.time()
                
                # Download and cache the model
                model = SentenceTransformer(model_name, cache_folder=str(MODEL_CACHE_DIR))
                
                # Test the model
                test_embedding = model.encode("Test sentence")
                
                download_time = time.time() - start_time
                results[model_name] = {
                    'status': 'success',
                    'download_time': round(download_time, 2),
                    'embedding_dim': len(test_embedding)
                }
                logger.info(f"✓ Model {model_name} downloaded successfully ({download_time:.2f}s)")
                
            except Exception as e:
                logger.error(f"✗ Failed to download {model_name}: {e}")
                results[model_name] = {
                    'status': 'failed',
                    'error': str(e)
                }
                
    except ImportError:
        logger.warning("sentence-transformers not installed. Skipping model downloads.")
        for model_name in model_names:
            results[model_name] = {
                'status': 'skipped',
                'reason': 'sentence-transformers not installed'
            }
    
    return results

def initialize_models(force: bool = False) -> Dict[str, Any]:
    """Initialize all models"""
    ensure_directories()
    status = load_status()
    
    if status['initialized'] and not force:
        logger.info("Models already initialized. Use --force to re-initialize.")
        return status
    
    logger.info("Starting model initialization...")
    start_time = time.time()
    
    status['timestamp'] = time.time()
    status['errors'] = []
    
    # Download sentence transformer models
    if 'sentence-transformers' in MODELS_CONFIG:
        config = MODELS_CONFIG['sentence-transformers']
        results = download_sentence_transformer_models(config['models'])
        status['models']['sentence-transformers'] = results
        
        # Check for errors
        for model_name, result in results.items():
            if result['status'] == 'failed':
                status['errors'].append({
                    'model': model_name,
                    'error': result.get('error', 'Unknown error')
                })
    
    # Mark as initialized
    status['initialized'] = True
    status['init_time'] = round(time.time() - start_time, 2)
    
    # Save status
    save_status(status)
    
    # Summary
    total_models = sum(len(config['models']) for config in MODELS_CONFIG.values())
    successful = sum(
        1 for models in status['models'].values() 
        for result in models.values() 
        if result['status'] == 'success'
    )
    
    logger.info(f"\nInitialization complete!")
    logger.info(f"Total models: {total_models}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {len(status['errors'])}")
    logger.info(f"Time taken: {status['init_time']}s")
    
    return status

def check_models() -> bool:
    """Check if models are initialized"""
    status = load_status()
    if not status['initialized']:
        logger.warning("Models not initialized. Run with --init to initialize.")
        return False
    
    logger.info("Model status:")
    for category, models in status['models'].items():
        logger.info(f"\n{category}:")
        for model_name, result in models.items():
            if result['status'] == 'success':
                logger.info(f"  ✓ {model_name}")
            else:
                logger.info(f"  ✗ {model_name} ({result['status']})")
    
    return len(status['errors']) == 0

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Initialize ML models')
    parser.add_argument('--force', action='store_true', help='Force re-initialization')
    parser.add_argument('--check', action='store_true', help='Check model status')
    parser.add_argument('--init', action='store_true', help='Initialize models')
    
    args = parser.parse_args()
    
    if args.check:
        check_models()
    elif args.init or args.force:
        initialize_models(force=args.force)
    else:
        # Default action: initialize if not already done
        status = load_status()
        if not status['initialized']:
            initialize_models()
        else:
            check_models()

if __name__ == '__main__':
    main()