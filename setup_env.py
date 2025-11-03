#!/usr/bin/env python3
"""
Quick environment setup for Football Analytics AI
"""

import os
import sys

def setup_environment():
    """Set up the environment file with proper values"""
    
    print("🏈 Football Analytics AI - Environment Setup")
    print("=" * 50)
    
    if os.path.exists('.env'):
        print("📄 Found existing .env file")
        with open('.env', 'r') as f:
            content = f.read()
        
        if 'sk-your-openai-api-key-here' in content:
            print("⚠️  .env file has placeholder values")
        else:
            print("✅ .env file appears to be configured")
            return True
    
    print("\n🔑 You need to set up your OpenAI API key")
    print("1. Go to: https://platform.openai.com/api-keys")
    print("2. Create a new API key")
    print("3. Copy the key (starts with 'sk-proj-' or 'sk-')")
    
    api_key = input("\n📝 Paste your OpenAI API key here: ").strip()
    
    if not api_key:
        print("❌ No API key provided")
        return False
    
    if not api_key.startswith('sk-'):
        print("❌ Invalid API key format (should start with 'sk-')")
        return False
    
    # Create .env file
    env_content = f"""# Football Analytics AI Environment Configuration
OPENAI_API_KEY={api_key}
MCP_API_KEY=dev-token-12345

# Data Configuration
DATA_PATH=./data/FINAL_with_rag.csv
VECTORSTORE_DIR=./data/vectorstore
AGENT_CACHE_DB=./data/agent_cache.sqlite

# Server Configuration
MCP_URL=http://localhost:8080/invoke
MCP_TIMEOUT=30

# Model Configuration
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small
OPENAI_TEMPERATURE=0.0

# Performance Settings
DEFAULT_SEASONS_BACK=5
TOP_RAG_MIN_SCORE=0.7
CACHE_TTL_SECS=86400
CACHE_MAX_ENTRIES=2000
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✅ .env file created successfully!")
    print("\n🔒 IMPORTANT: Never commit your .env file to version control!")
    
    return True

if __name__ == "__main__":
    if setup_environment():
        print("\n🎉 Environment setup complete!")
        print("📋 Next steps:")
        print("   1. Run: python3 run_system.py")
        print("   2. Open: http://localhost:3000")
    else:
        print("\n❌ Environment setup failed")
        sys.exit(1)