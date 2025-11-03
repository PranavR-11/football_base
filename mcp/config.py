# mcp/config.py - Clean configuration with proper error handling
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def _find_dotenv_file() -> Optional[str]:
    """Find .env file with proper fallback logic."""
    try:
        from dotenv import find_dotenv
        dotenv_path = find_dotenv()
        
        # find_dotenv() can return empty string, not just None
        if dotenv_path and os.path.exists(dotenv_path):
            return dotenv_path
    except ImportError:
        logger.warning("python-dotenv not installed, skipping .env file loading")
    
    # Fallback: look for .env in project root (assuming this file is in mcp/)
    project_root = Path(__file__).resolve().parents[1]
    fallback_path = project_root / ".env"
    
    if fallback_path.exists():
        return str(fallback_path)
    
    return None

def _load_environment():
    """Load environment variables from .env file if present."""
    dotenv_path = _find_dotenv_file()
    
    if dotenv_path:
        try:
            from dotenv import load_dotenv
            # Don't override existing environment variables
            load_dotenv(dotenv_path, override=False)
            logger.info(f"Loaded environment from: {dotenv_path}")
        except ImportError:
            logger.warning("python-dotenv not installed, using system environment only")
    else:
        logger.info("No .env file found, using system environment only")

# Load environment once at import
_load_environment()

def get_openai_api_key() -> str:
    """Get OpenAI API key with proper error handling."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not found. Please:\n"
            "1. Set it in your .env file: OPENAI_API_KEY=your_key_here\n"
            "2. Or export it in your shell: export OPENAI_API_KEY=your_key_here"
        )
    return key

def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get configuration value with optional default."""
    return os.getenv(key, default)

# Configuration constants - read dynamically when needed
def get_data_csv_path() -> str:
    return get_config_value("DATA_PATH", "./data/FINAL_with_rag.csv")

def get_vector_dir() -> str:
    return get_config_value("VECTORSTORE_DIR", "./data/vectorstore")

def get_embedding_model() -> str:
    return get_config_value("OPENAI_EMBED_MODEL", "text-embedding-3-small")

def get_k_default() -> int:
    return int(get_config_value("K_DEFAULT", "5"))

def get_default_seasons_back() -> int:
    return int(get_config_value("DEFAULT_SEASONS_BACK", "5"))