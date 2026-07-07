#!/bin/bash
set -e

echo "→ Installing frontend dependencies..."
cd frontend && npm install

echo "→ Building React app..."
npm run build

echo "→ Build complete. Output: frontend/dist/"
echo ""
echo "To deploy:"
echo "  databricks bundle deploy --target dev"
