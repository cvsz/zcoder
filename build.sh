#!/bin/bash
# Build script for AI Model Coder CLI standalone executable
# Creates a single executable that doesn't require Python

set -e

echo "🔨 AI Model Coder CLI - Standalone Build"
echo "=========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found"
    exit 1
fi

echo "✅ Python found"
echo ""

# Create build virtual environment
echo "📦 Creating build environment..."
if [ ! -d "build-venv" ]; then
    python3 -m venv build-venv
fi

source build-venv/bin/activate

# Install dependencies
echo "📦 Installing build dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install pyinstaller anthropic python-dotenv > /dev/null 2>&1
echo "✅ Dependencies installed"
echo ""

# Create output directory
mkdir -p dist

# Build executable
echo "🔨 Building standalone executable..."
echo "   This may take 1-2 minutes..."
echo ""

pyinstaller --onefile \
    --name ai-coder \
    --console \
    --hidden-import=anthropic \
    --strip \
    main.py

echo ""
echo "✅ Build complete!"
echo ""

# Check output
if [ -f "dist/ai-coder" ]; then
    ls -lh dist/ai-coder
    echo ""
    echo "🎉 Standalone executable created: dist/ai-coder"
    echo ""
    echo "Next steps:"
    echo "1. Copy 'dist/ai-coder' to any location"
    echo "2. Set API key: export ANTHROPIC_API_KEY='sk-ant-...'"
    echo "3. Run: ./ai-coder -p 'Create code'"
    echo ""
else
    echo "❌ Build failed"
    exit 1
fi

# Cleanup
echo "🧹 Cleaning up build files..."
rm -rf build ai-coder.spec > /dev/null 2>&1
echo "✅ Cleanup complete"
echo ""

echo "Ready to deploy! The executable in dist/ is self-contained."
