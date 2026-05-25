#!/bin/bash

# Laravel Reverb Server Startup Script
# This script starts the Reverb WebSocket server for real-time broadcasting

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${GREEN}Laravel Reverb Server Launcher${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

# Check if .env file exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found!${NC}"
    echo "Please ensure you have configured your .env file."
    exit 1
fi

# Check Node.js version
NODE_VERSION=$(node -v)
echo -e "📦 Node.js version: ${GREEN}$NODE_VERSION${NC}"

# Get environment variables
DB_HOST=$(grep "DB_HOST=" "$SCRIPT_DIR/.env" | cut -d '=' -f2)
REVERB_HOST=$(grep "REVERB_HOST=" "$SCRIPT_DIR/.env" | cut -d '=' -f2)
REVERB_PORT=$(grep "REVERB_PORT=" "$SCRIPT_DIR/.env" | cut -d '=' -f2)

echo -e "🌐 Reverb will run at: ${GREEN}$REVERB_HOST:$REVERB_PORT${NC}"
echo -e "🗄️  Database: ${GREEN}$DB_HOST${NC}"
echo ""

# Parse command line arguments
DEBUG_MODE=false
CUSTOM_PORT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --debug)
            DEBUG_MODE=true
            shift
            ;;
        --port)
            CUSTOM_PORT="$2"
            shift 2
            ;;
        --help)
            echo "Usage: ./start-reverb.sh [options]"
            echo ""
            echo "Options:"
            echo "  --debug     Enable debug mode for detailed output"
            echo "  --port PORT Override the default port (8080)"
            echo "  --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Build the command
COMMAND="php artisan reverb:start"

if [ ! -z "$CUSTOM_PORT" ]; then
    COMMAND="$COMMAND --port=$CUSTOM_PORT"
    echo -e "  Using custom port: ${GREEN}$CUSTOM_PORT${NC}"
fi

if [ "$DEBUG_MODE" = true ]; then
    COMMAND="$COMMAND --debug"
    echo -e "  Debug mode: ${GREEN}enabled${NC}"
fi

echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}Starting Reverb server...${NC}"
echo -e "Command: ${YELLOW}$COMMAND${NC}"
echo ""

# Check if Reverb port is already in use
if [ ! -z "$REVERB_PORT" ]; then
    if lsof -Pi :$REVERB_PORT -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${YELLOW}⚠️  Warning: Port $REVERB_PORT is already in use!${NC}"
        echo "Please ensure no other Reverb process is running."
        echo "To kill existing process: sudo kill -9 \$(lsof -t -i:$REVERB_PORT)"
        echo ""
    fi
fi

# Start the server
cd "$SCRIPT_DIR"
eval $COMMAND

# If we reach here, the server was stopped
echo ""
echo -e "${YELLOW}Reverb server stopped.${NC}"

