#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Agent Platform — Starting Up     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"

# Check .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ No .env found. Copying .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Edit .env with your API keys, then re-run.${NC}"
    exit 1
fi

# Load env
export $(grep -v '^#' .env | xargs)

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3.11+ required${NC}"
    exit 1
fi

# Check venv
if [ ! -d .venv ]; then
    echo -e "${GREEN}Creating virtual environment...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[test]"
else
    source .venv/bin/activate
fi

# Check Ollama
if ! curl -s "$OLLAMA_BASE_URL/api/tags" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Ollama not running. Start it with: ollama serve${NC}"
    echo -e "${YELLOW}  Then pull models: ollama pull nomic-embed-text${NC}"
    echo -e "${YELLOW}  ollama pull qwen2.5-coder:14b${NC}"
fi

# Create data directories
mkdir -p data logs config

# Start
echo -e "${GREEN}Starting agent platform...${NC}"
python3 -m core.cli "$@"
