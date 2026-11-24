# Minitools Makefile - Simplified Docker commands
.PHONY: help build up down arxiv medium google youtube shell test clean logs

# Detect OS and set appropriate docker-compose file
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    # macOS detected
    COMPOSE_FILE := docker-compose.mac.yml
    OLLAMA_MSG := "Note: On macOS, Ollama must be running natively for GPU support (Metal/MPS)"
else ifeq ($(OS),Windows_NT)
    # Windows detected
    COMPOSE_FILE := docker-compose.windows.yml
    OLLAMA_MSG := "Note: Windows with NVIDIA GPU support enabled"
else
    # Linux or other OS - use default
    COMPOSE_FILE := docker-compose.yml
    OLLAMA_MSG := "Note: Using default Docker configuration"
endif

# Allow override via environment variable
ifdef DOCKER_COMPOSE_FILE
    COMPOSE_FILE := $(DOCKER_COMPOSE_FILE)
endif

# Default target
help:
	@echo "Minitools - Quick Commands"
	@echo ""
	@echo "Data Collection:"
	@echo "  make arxiv [options]  - Search and translate ArXiv papers"
	@echo "  make medium [options] - Process Medium Daily Digest"
	@echo "  make google [options] - Process Google Alerts"
	@echo "  make youtube [options] - Summarize YouTube video"
	@echo ""
	@echo "Examples:"
	@echo "  make -- arxiv --date 2025-09-04 --min-upvotes 20"
	@echo "  make -- medium --date 2024-01-15 --notion"
	@echo "  make -- google --hours 24"
	@echo "  make -- youtube --url https://youtube.com/watch?v=..."
	@echo ""
	@echo "Note: Use -- (double dash) before target name when passing options with dashes"
	@echo ""
	@echo "Test Modes (process 1 item):"
	@echo "  make arxiv-test       - Test ArXiv with 1 paper"
	@echo "  make medium-test      - Test Medium with 1 article"
	@echo ""
	@echo "Docker Management:"
	@echo "  make build            - Build Docker images"
	@echo "  make build-dev        - Build with development target (includes whisper)"
	@echo "  make up               - Start services in background"
	@echo "  make down             - Stop all services"
	@echo "  make restart          - Restart all services"
	@echo ""
	@echo "Development:"
	@echo "  make shell            - Open interactive shell in container"
	@echo "  make jupyter          - Start Jupyter notebook (localhost:8888)"
	@echo "  make test             - Test Ollama connection"
	@echo "  make logs             - Show container logs"
	@echo "  make clean            - Clean up containers and volumes"
	@echo ""
	@echo "Platform Setup:"
	@echo "  make setup            - Run platform-specific setup script"
	@echo ""
	@echo $(OLLAMA_MSG)

# Platform-specific setup
setup:
ifeq ($(UNAME_S),Darwin)
	@echo "Running macOS setup..."
	@chmod +x setup-mac.sh
	@./setup-mac.sh
else ifeq ($(OS),Windows_NT)
	@echo "Running Windows setup..."
	@powershell -ExecutionPolicy Bypass -File setup-windows.ps1
else
	@echo "Running Linux setup..."
	@echo "Please ensure Docker and NVIDIA Container Toolkit are installed"
	@docker-compose -f $(COMPOSE_FILE) build
endif

# Build commands
build:
	docker-compose -f $(COMPOSE_FILE) build

build-dev:
	BUILD_TARGET=development docker-compose -f $(COMPOSE_FILE) build

# Service management
up:
ifeq ($(UNAME_S),Darwin)
	@echo "On macOS: Ensure Ollama.app is running for GPU support"
	@echo "Checking Ollama status..."
	@curl -s http://localhost:11434/api/tags > /dev/null && echo "✓ Ollama is running" || echo "⚠ Ollama is not running - please start Ollama.app"
else
	docker-compose -f $(COMPOSE_FILE) up -d ollama ollama-setup
	@echo "Waiting for Ollama to be ready..."
	@sleep 15
	@echo "Ollama services started"
endif

down:
	docker-compose -f $(COMPOSE_FILE) down

restart: down up

# Main tools - simplified commands
# Use filter-out to remove make targets from arguments
arxiv:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools minitools-arxiv $(filter-out $@,$(MAKECMDGOALS))

medium:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools minitools-medium $(filter-out $@,$(MAKECMDGOALS))

google:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools minitools-google-alerts $(filter-out $@,$(MAKECMDGOALS))

youtube:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools minitools-youtube $(filter-out $@,$(MAKECMDGOALS))

# Catch all target to prevent "No rule to make target" errors
%:
	@:

# Test modes
arxiv-test:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools minitools-arxiv --test

medium-test:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools minitools-medium --test

# Development tools
shell:
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools bash

jupyter:
	docker-compose -f $(COMPOSE_FILE) --profile development up jupyter

test:
ifeq ($(UNAME_S),Darwin)
	@echo "Testing Ollama connection (native)..."
	@curl -s http://localhost:11434/api/tags > /dev/null && echo "✓ Ollama is accessible" || echo "✗ Ollama is not running"
else
	@echo "Testing Ollama connection (Docker)..."
	@docker-compose -f $(COMPOSE_FILE) run --rm minitools curl -s http://ollama:11434/api/tags > /dev/null && echo "✓ Ollama is accessible" || echo "✗ Ollama is not running"
endif

# Logs and cleanup
logs:
	docker-compose -f $(COMPOSE_FILE) logs -f

logs-ollama:
ifeq ($(UNAME_S),Darwin)
	@echo "On macOS, Ollama runs natively. Check Ollama.app logs."
else
	docker-compose -f $(COMPOSE_FILE) logs -f ollama
endif

clean:
	docker-compose -f $(COMPOSE_FILE) down -v
	@echo "Cleaned up containers and volumes"

# Note: The catch-all target (%) allows passing arguments directly
# Use -- (double dash) before target name when passing options with dashes
# Examples:
#   make -- arxiv --date 2025-09-04 --min-upvotes 20
#   make -- medium --date 2024-01-15 --notion
#   make -- google --hours 24
#   make -- youtube --url https://youtube.com/watch?v=...