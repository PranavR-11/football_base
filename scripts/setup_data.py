#!/usr/bin/env python3
"""
Data setup and validation script for Football Analytics AI
"""
import os
import sys
from pathlib import Path

def check_data_files():
    """Check if required data files exist"""
    required_files = [
        "./data/FINAL_with_rag.csv",
        "./data/vectorstore/index.faiss",
        "./data/vectorstore/metadata.pkl"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required data files:")
        for file in missing_files:
            print(f"   - {file}")
        print("\n📋 To fix this:")
        print("1. Ensure you have the football dataset CSV file")
        print("2. Run: python scripts/batch_embed.py to generate embeddings")
        print("3. Check that data/ directory has proper structure")
        return False
    
    print("✅ All required data files found")
    return True

def check_environment():
    """Check environment variables"""
    required_env = ["OPENAI_API_KEY"]
    missing_env = []
    
    for env_var in required_env:
        if not os.getenv(env_var):
            missing_env.append(env_var)
    
    if missing_env:
        print("❌ Missing environment variables:")
        for var in missing_env:
            print(f"   - {var}")
        print("\n📋 To fix this:")
        print("1. Copy .env.example to .env")
        print("2. Fill in your actual API keys")
        return False
    
    print("✅ Environment variables configured")
    return True

def main():
    print("🏈 Football Analytics AI - Setup Validation")
    print("=" * 50)
    
    data_ok = check_data_files()
    env_ok = check_environment()
    
    if data_ok and env_ok:
        print("\n🎉 Setup validation passed! You're ready to run the application.")
        return 0
    else:
        print("\n⚠️  Setup validation failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())