#!/bin/bash
# Setup script for AI Model Coder CLI

set -e

echo "🚀 AI Model Coder CLI Setup"
echo "================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python $PYTHON_VERSION found"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "ℹ️  Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "✅ pip upgraded"

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Setup .env file
if [ ! -f ".env" ]; then
    echo "🔑 Setting up environment file..."
    cp .env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  Please edit .env and add your Anthropic API key:"
    echo "   ANTHROPIC_API_KEY=sk-ant-your-key-here"
else
    echo "ℹ️  .env file already exists"
fi

echo ""
echo "================================"
echo "✅ Setup complete!"
echo ""
echo "To get started:"
echo "1. Edit .env and add your API key"
echo "2. Run: source venv/bin/activate"
echo "3. Try: python main.py -p 'Hello world'"
echo ""
echo "For more examples: python main.py -h"
echo ""
