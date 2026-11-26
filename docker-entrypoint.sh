#!/bin/bash
set -e

# Initialize settings if not present
if [ ! -f "/app/settings.yaml" ]; then
    echo "Initializing settings.yaml from example..."
    cp /app/settings.yaml.example /app/settings.yaml
fi

# Check for required environment variables or files
check_requirements() {
    local tool=$1
    shift
    local requirements=("$@")
    
    for req in "${requirements[@]}"; do
        if [[ "$req" == *.* ]]; then
            # It's a file
            if [ ! -f "/app/$req" ]; then
                echo "Warning: Required file $req not found for $tool"
                return 1
            fi
        else
            # It's an environment variable
            if [ -z "${!req}" ]; then
                echo "Warning: Required environment variable $req not set for $tool"
                return 1
            fi
        fi
    done
    return 0
}

# Parse command and validate requirements
case "$1" in
    minitools-arxiv)
        echo "Running ArXiv collector..."
        if check_requirements "arxiv" "NOTION_API_KEY" "SLACK_WEBHOOK_URL"; then
            exec uv run "$@"
        else
            echo "Optional: Set NOTION_API_KEY and SLACK_WEBHOOK_URL for full functionality"
            exec uv run "$@"
        fi
        ;;
    
    minitools-medium)
        echo "Running Medium Daily Digest collector..."
        
        # Check for Gmail authentication (either credentials.json or token.pickle)
        if [ -f "/app/token.pickle" ]; then
            echo "Using existing Gmail authentication (token.pickle found)"
        elif [ -f "/app/credentials.json" ]; then
            echo "Gmail credentials found. Note: First-time OAuth authentication may be required."
            echo "If authentication fails in Docker, please:"
            echo "  1. Run the tool on your host machine first to complete OAuth flow"
            echo "  2. Copy the generated token.pickle to the project directory"
            echo "  3. Restart the Docker container"
        else
            echo "WARNING: No Gmail authentication files found (credentials.json or token.pickle)"
            echo ""
            echo "To fix this issue:"
            echo "  Option 1: Run authentication on host machine first"
            echo "    - Install minitools locally: pip install -e ."
            echo "    - Run: minitools-medium --test"
            echo "    - Complete OAuth in browser"
            echo "    - Copy token.pickle to project directory"
            echo ""
            echo "  Option 2: Provide credentials.json from Google Cloud Console"
            echo "    - Create OAuth 2.0 credentials at https://console.cloud.google.com"
            echo "    - Download credentials.json to project directory"
            echo ""
            echo "Attempting to continue, but authentication may fail..."
        fi
        
        # Check for API keys (warning only, don't exit)
        if [ -z "$NOTION_API_KEY" ]; then
            echo "Warning: NOTION_API_KEY not set - Notion publishing will be skipped"
        fi
        if [ -z "$SLACK_MEDIUM_WEBHOOK_URL" ] && [ -z "$SLACK_WEBHOOK_URL" ]; then
            echo "Warning: Slack webhook not set - Slack notifications will be skipped"
        fi
        
        exec uv run "$@"
        ;;
    
    minitools-google-alerts)
        echo "Running Google Alerts collector..."
        
        # Check for Gmail authentication (either credentials.json or token.pickle)
        if [ -f "/app/token.pickle" ]; then
            echo "Using existing Gmail authentication (token.pickle found)"
        elif [ -f "/app/credentials.json" ]; then
            echo "Gmail credentials found. Note: First-time OAuth authentication may be required."
            echo "If authentication fails in Docker, please:"
            echo "  1. Run the tool on your host machine first to complete OAuth flow"
            echo "  2. Copy the generated token.pickle to the project directory"
            echo "  3. Restart the Docker container"
        else
            echo "WARNING: No Gmail authentication files found (credentials.json or token.pickle)"
            echo ""
            echo "To fix this issue:"
            echo "  Option 1: Run authentication on host machine first"
            echo "    - Install minitools locally: pip install -e ."
            echo "    - Run: minitools-google-alerts --hours 1"
            echo "    - Complete OAuth in browser"
            echo "    - Copy token.pickle to project directory"
            echo ""
            echo "  Option 2: Provide credentials.json from Google Cloud Console"
            echo "    - Create OAuth 2.0 credentials at https://console.cloud.google.com"
            echo "    - Download credentials.json to project directory"
            echo ""
            echo "Attempting to continue, but authentication may fail..."
        fi
        
        # Check for API keys (warning only, don't exit)
        if [ -z "$NOTION_API_KEY" ]; then
            echo "Warning: NOTION_API_KEY not set - Notion publishing will be skipped"
        fi
        
        exec uv run "$@"
        ;;
    
    minitools-youtube)
        echo "Running YouTube summarizer..."
        if ! check_requirements "youtube" "NOTION_API_KEY"; then
            echo "Warning: Set NOTION_API_KEY for saving to Notion"
        fi
        exec uv run "$@"
        ;;
    
    bash|sh)
        echo "Starting interactive shell..."
        exec /bin/bash
        ;;
    
    test)
        echo "Testing Ollama connection..."
        curl -s http://ollama:11434/api/tags || echo "Failed to connect to Ollama"
        echo ""
        echo "Available commands:"
        echo "  minitools-arxiv       - Search and translate ArXiv papers"
        echo "  minitools-medium      - Process Medium Daily Digest"
        echo "  minitools-google-alerts - Process Google Alerts"
        echo "  minitools-youtube     - Summarize YouTube videos"
        ;;
    
    --help|"")
        echo "Minitools Docker Container"
        echo ""
        echo "Usage:"
        echo "  docker-compose run minitools minitools-arxiv [options]"
        echo "  docker-compose run minitools minitools-medium [options]"
        echo "  docker-compose run minitools minitools-google-alerts [options]"
        echo "  docker-compose run minitools minitools-youtube --url <youtube-url>"
        echo ""
        echo "Interactive shell:"
        echo "  docker-compose run minitools bash"
        echo ""
        echo "Test environment:"
        echo "  docker-compose run minitools test"
        echo ""
        echo "Development mode with Jupyter:"
        echo "  docker-compose --profile development up jupyter"
        echo "  Then access http://localhost:8888"
        ;;
    
    *)
        # Pass through any other command
        exec "$@"
        ;;
esac