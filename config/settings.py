"""
Centralized configuration for Football Analytics AI
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Centralized configuration class"""
    
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MCP_API_KEY: str = os.getenv("MCP_API_KEY", "dev-token")
    FOOTBALL_API_KEY: str = os.getenv("FOOTBALL_API_KEY", "")
    
    # Model Configuration
    OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    OPENAI_EMBED_MODEL: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.0"))
    
    # Data Paths
    DATA_PATH: str = os.getenv("DATA_PATH", "./data/FINAL_with_rag.csv")
    VECTORSTORE_DIR: str = os.getenv("VECTORSTORE_DIR", "./data/vectorstore")
    AGENT_CACHE_DB: str = os.getenv("AGENT_CACHE_DB", "./data/agent_cache.sqlite")
    
    # Server Configuration
    MCP_URL: str = os.getenv("MCP_URL", "http://localhost:8080/invoke")
    MCP_TIMEOUT: int = int(os.getenv("MCP_TIMEOUT", "30"))
    
    # Performance Settings
    DEFAULT_SEASONS_BACK: int = int(os.getenv("DEFAULT_SEASONS_BACK", "5"))
    K_DEFAULT: int = int(os.getenv("K_DEFAULT", "5"))
    TOP_RAG_MIN_SCORE: float = float(os.getenv("TOP_RAG_MIN_SCORE", "0.7"))
    CACHE_TTL_SECS: int = int(os.getenv("CACHE_TTL_SECS", "86400"))
    CACHE_MAX_ENTRIES: int = int(os.getenv("CACHE_MAX_ENTRIES", "2000"))
    
    # Debug Settings
    AGENT_DEBUG: bool = os.getenv("AGENT_DEBUG", "1") not in ("0", "false", "False", "")
    
    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of issues"""
        issues = []
        
        if not cls.OPENAI_API_KEY or cls.OPENAI_API_KEY == "sk-your-openai-api-key-here":
            issues.append("OPENAI_API_KEY not properly configured")
        
        if not os.path.exists(cls.DATA_PATH):
            issues.append(f"Data file not found: {cls.DATA_PATH}")
        
        if not os.path.exists(cls.VECTORSTORE_DIR):
            issues.append(f"Vector store directory not found: {cls.VECTORSTORE_DIR}")
        
        return issues
    
    @classmethod
    def is_valid(cls) -> bool:
        """Check if configuration is valid"""
        return len(cls.validate()) == 0

# Global config instance
config = Config()