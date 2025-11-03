#!/usr/bin/env python3
"""
Football Analytics AI - System Startup Script
Handles environment setup and component launching
"""

import os
import sys
import subprocess
import time
import requests
from pathlib import Path

def check_python_environment():
    """Ensure we're using the right Python with all dependencies"""
    print("🔍 Checking Python environment...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        return False
    
    print(f"✅ Python {sys.version}")
    
    # Check critical dependencies
    required_packages = [
        'fastapi', 'uvicorn', 'openai', 'langchain', 
        'pandas', 'numpy', 'faiss', 'matplotlib'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✅ {package}")
        except ImportError:
            missing.append(package)
            print(f"❌ {package}")
    
    if missing:
        print(f"\n📦 Installing missing packages: {', '.join(missing)}")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install'
            ] + missing)
            print("✅ Packages installed successfully")
        except subprocess.CalledProcessError:
            print("❌ Failed to install packages")
            return False
    
    return True

def check_environment_variables():
    """Check if environment variables are properly set"""
    print("\n🔍 Checking environment variables...")
    
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        print("📋 Please copy .env.template to .env and fill in your API keys")
        return False
    
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-dotenv'])
        from dotenv import load_dotenv
        load_dotenv()
    
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key or openai_key == 'sk-your-openai-api-key-here':
        print("❌ OPENAI_API_KEY not properly set")
        print("📋 Please add your real OpenAI API key to .env file")
        return False
    
    print("✅ Environment variables configured")
    return True

def check_data_files():
    """Check if required data files exist"""
    print("\n🔍 Checking data files...")
    
    required_files = [
        './data/FINAL_with_rag.csv',
        './data/vectorstore/index.faiss',
        './data/vectorstore/metadata.pkl'
    ]
    
    missing = []
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path}")
        else:
            missing.append(file_path)
            print(f"❌ {file_path}")
    
    if missing:
        print("\n📋 Missing data files. Please ensure you have:")
        print("1. The football dataset CSV file")
        print("2. Generated FAISS embeddings (run: python3 scripts/batch_embed.py)")
        return False
    
    return True

def start_mcp_server():
    """Start the MCP server"""
    print("\n🚀 Starting MCP Server...")
    
    cmd = [
        sys.executable, '-m', 'uvicorn', 
        'mcp.mcp_server:app',
        '--reload',
        '--host', '0.0.0.0',
        '--port', '8080'
    ]
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a bit and check if it started
        time.sleep(3)
        
        try:
            response = requests.get('http://localhost:8080/.well-known/mcp/health', timeout=5)
            if response.status_code == 200:
                print("✅ MCP Server started successfully on port 8080")
                return process
            else:
                print(f"❌ MCP Server health check failed: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ MCP Server not responding: {e}")
        
        return process
        
    except Exception as e:
        print(f"❌ Failed to start MCP Server: {e}")
        return None

def start_api_server():
    """Start the FastAPI backend"""
    print("\n🚀 Starting FastAPI Backend...")
    
    cmd = [
        sys.executable, '-m', 'uvicorn',
        'api.main:app',
        '--reload',
        '--host', '0.0.0.0',
        '--port', '8000'
    ]
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a bit and check if it started
        time.sleep(3)
        
        try:
            response = requests.get('http://localhost:8000/health', timeout=5)
            if response.status_code == 200:
                print("✅ FastAPI Backend started successfully on port 8000")
                return process
            else:
                print(f"❌ FastAPI Backend health check failed: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ FastAPI Backend not responding: {e}")
        
        return process
        
    except Exception as e:
        print(f"❌ Failed to start FastAPI Backend: {e}")
        return None

def start_frontend():
    """Start the Next.js frontend"""
    print("\n🚀 Starting Next.js Frontend...")
    
    # Check if node_modules exists
    if not os.path.exists('web/node_modules'):
        print("📦 Installing frontend dependencies...")
        try:
            subprocess.check_call(['npm', 'install'], cwd='web')
        except subprocess.CalledProcessError:
            print("❌ Failed to install frontend dependencies")
            return None
    
    cmd = ['npm', 'run', 'dev']
    
    try:
        process = subprocess.Popen(cmd, cwd='web', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a bit for Next.js to start
        time.sleep(5)
        
        try:
            response = requests.get('http://localhost:3000', timeout=10)
            if response.status_code == 200:
                print("✅ Next.js Frontend started successfully on port 3000")
                return process
            else:
                print(f"❌ Frontend health check failed: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Frontend not responding: {e}")
        
        return process
        
    except Exception as e:
        print(f"❌ Failed to start Frontend: {e}")
        return None

def main():
    """Main startup sequence"""
    print("🏈 Football Analytics AI - System Startup")
    print("=" * 50)
    
    # Step 1: Check Python environment
    if not check_python_environment():
        print("\n❌ Python environment check failed")
        return 1
    
    # Step 2: Check environment variables
    if not check_environment_variables():
        print("\n❌ Environment variables check failed")
        return 1
    
    # Step 3: Check data files
    if not check_data_files():
        print("\n❌ Data files check failed")
        return 1
    
    print("\n✅ All checks passed! Starting services...")
    
    # Start services
    processes = []
    
    # Start MCP Server
    mcp_process = start_mcp_server()
    if mcp_process:
        processes.append(('MCP Server', mcp_process))
    
    # Start API Server
    api_process = start_api_server()
    if api_process:
        processes.append(('API Server', api_process))
    
    # Start Frontend
    frontend_process = start_frontend()
    if frontend_process:
        processes.append(('Frontend', frontend_process))
    
    if not processes:
        print("\n❌ No services started successfully")
        return 1
    
    print(f"\n🎉 Started {len(processes)} services successfully!")
    print("\n🌐 Access your application at:")
    print("   • Frontend: http://localhost:3000")
    print("   • API Docs: http://localhost:8000/docs")
    print("   • MCP Health: http://localhost:8080/.well-known/mcp/health")
    
    print("\n⚠️  Press Ctrl+C to stop all services")
    
    try:
        # Keep running until interrupted
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down services...")
        for name, process in processes:
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"✅ {name} stopped")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"🔥 {name} force killed")
            except Exception as e:
                print(f"❌ Error stopping {name}: {e}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())