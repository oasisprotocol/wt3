#!/bin/bash
set -e

export DOCKER_BUILDKIT=1

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed."
        echo "Please install Docker first."
        echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
        exit 1
    fi
}

show_help() {
    echo "WT3 Docker Helper Script"
    echo ""
    echo "Usage: ./scripts/docker-run.sh [command] [service]"
    echo ""
    echo "Commands:"
    echo "  start       Build and start the containers in detached mode"
    echo "  stop        Stop the containers"
    echo "  restart     Restart the containers"
    echo "  logs        Show container logs (follow mode)"
    echo "  build       Rebuild the Docker images"
    echo "  clean       Remove all Docker artifacts (images, containers, volumes)"
    echo "  status      Check container status"
    echo "  help        Show this help message"
    echo ""
    echo "Services (optional):"
    echo "  signal      Only affect the signal service container"
    echo "  wt3         Only affect the wt3 container"
    echo "  (none)      Affect all containers"
    echo ""
}

check_env_file() {
    if [ ! -f .env ]; then
        echo "Warning: .env file not found. Creating from .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            echo "Created .env file. Please edit it to add your API keys and credentials."
            echo "Press Enter to continue or Ctrl+C to abort..."
            read
        else
            echo "Error: .env.example file not found. Please create a .env file manually."
            exit 1
        fi
    fi
}

load_env_vars() {
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi
}

start_container() {
    check_env_file
    load_env_vars
    
    if [ "$1" == "signal" ]; then
        echo "Starting Signal Service container..."
        docker pull docker.io/ahmedatoasis/wt3-signal@sha256:4f3a96735e5650cee8ca14903cba5b84b700506d51da8eb32a37e2d726d27f6e
        docker run -d --name wt3-signal-service \
            -v /run/rofl-appd.sock:/run/rofl-appd.sock \
            -v /storage:/storage \
            -e AGE_PRIVATE_KEY=${AGE_PRIVATE_KEY} \
            -p 8000:8000 \
            --restart always \
            docker.io/ahmedatoasis/wt3-signal@sha256:4f3a96735e5650cee8ca14903cba5b84b700506d51da8eb32a37e2d726d27f6e
        echo "Signal Service container started. Use './scripts/docker-run.sh logs signal' to view logs."
    elif [ "$1" == "wt3" ]; then
        echo "Building and starting WT3 container..."
        docker build --platform linux/amd64 -f Dockerfile -t docker.io/ahmedatoasis/wt3 .
        docker run -d --name wt3-main \
            -v /run/rofl-appd.sock:/run/rofl-appd.sock \
            -v /storage:/storage \
            -e GROK_API_KEY=${GROK_API_KEY} \
            -e TWITTER_BEARER_TOKEN=${TWITTER_BEARER_TOKEN} \
            -e TWITTER_API_KEY=${TWITTER_API_KEY} \
            -e TWITTER_API_SECRET=${TWITTER_API_SECRET} \
            -e TWITTER_ACCESS_TOKEN=${TWITTER_ACCESS_TOKEN} \
            -e TWITTER_ACCESS_TOKEN_SECRET=${TWITTER_ACCESS_TOKEN_SECRET} \
            -e SIGNAL_SERVICE_URL=${SIGNAL_SERVICE_URL} \
            --restart always \
            docker.io/ahmedatoasis/wt3
        echo "WT3 container started. Use './scripts/docker-run.sh logs wt3' to view logs."
    else
        echo "Building and starting all containers..."
        # Start Signal Service first
        docker pull docker.io/ahmedatoasis/wt3-signal@sha256:4f3a96735e5650cee8ca14903cba5b84b700506d51da8eb32a37e2d726d27f6e
        docker run -d --name wt3-signal-service \
            -v /run/rofl-appd.sock:/run/rofl-appd.sock \
            -v /storage:/storage \
            -e AGE_PRIVATE_KEY=${AGE_PRIVATE_KEY} \
            -p 8000:8000 \
            --restart always \
            docker.io/ahmedatoasis/wt3-signal@sha256:4f3a96735e5650cee8ca14903cba5b84b700506d51da8eb32a37e2d726d27f6e
            
        # Then start WT3
        docker build --platform linux/amd64 -f Dockerfile -t docker.io/ahmedatoasis/wt3 .
        docker run -d --name wt3-main \
            -v /run/rofl-appd.sock:/run/rofl-appd.sock \
            -v /storage:/storage \
            -e GROK_API_KEY=${GROK_API_KEY} \
            -e TWITTER_BEARER_TOKEN=${TWITTER_BEARER_TOKEN} \
            -e TWITTER_API_KEY=${TWITTER_API_KEY} \
            -e TWITTER_API_SECRET=${TWITTER_API_SECRET} \
            -e TWITTER_ACCESS_TOKEN=${TWITTER_ACCESS_TOKEN} \
            -e TWITTER_ACCESS_TOKEN_SECRET=${TWITTER_ACCESS_TOKEN_SECRET} \
            -e SIGNAL_SERVICE_URL=${SIGNAL_SERVICE_URL} \
            --restart always \
            docker.io/ahmedatoasis/wt3
        echo "Containers started. Use './scripts/docker-run.sh logs' to view logs."
    fi
}

stop_container() {
    if [ "$1" == "signal" ]; then
        echo "Stopping Signal Service container..."
        docker stop wt3-signal-service
        docker rm wt3-signal-service
        echo "Signal Service container stopped."
    elif [ "$1" == "wt3" ]; then
        echo "Stopping WT3 container..."
        docker stop wt3-main
        docker rm wt3-main
        echo "WT3 container stopped."
    else
        echo "Stopping all containers..."
        docker stop wt3-signal-service wt3-main 2>/dev/null || true
        docker rm wt3-signal-service wt3-main 2>/dev/null || true
        echo "All containers stopped."
    fi
}

restart_container() {
    if [ "$1" == "signal" ]; then
        echo "Restarting Signal Service container..."
        docker restart wt3-signal-service
        echo "Signal Service container restarted."
    elif [ "$1" == "wt3" ]; then
        echo "Restarting WT3 container..."
        docker restart wt3-main
        echo "WT3 container restarted."
    else
        echo "Restarting all containers..."
        docker restart wt3-signal-service wt3-main
        echo "All containers restarted."
    fi
}

show_logs() {
    if [ "$1" == "signal" ]; then
        echo "Showing Signal Service container logs (Ctrl+C to exit)..."
        docker logs -f wt3-signal-service
    elif [ "$1" == "wt3" ]; then
        echo "Showing WT3 container logs (Ctrl+C to exit)..."
        docker logs -f wt3-main
    else
        echo "Showing all container logs (Ctrl+C to exit)..."
        echo "=== Signal Service Logs ==="
        docker logs wt3-signal-service
        echo ""
        echo "=== WT3 Logs ==="
        docker logs wt3-main
    fi
}

build_image() {
    check_env_file
    
    if [ "$1" == "signal" ]; then
        echo "Signal Service uses a pre-built image from DockerHub."
        echo "To update, pull the latest image: docker pull docker.io/ahmedatoasis/wt3-signal@sha256:4f3a96735e5650cee8ca14903cba5b84b700506d51da8eb32a37e2d726d27f6e"
    elif [ "$1" == "wt3" ]; then
        echo "Rebuilding WT3 Docker image..."
        docker build --platform linux/amd64 -f Dockerfile -t docker.io/ahmedatoasis/wt3 . --no-cache
        echo "WT3 image rebuilt. Use './scripts/docker-run.sh start wt3' to start the container."
    else
        echo "Rebuilding Docker images..."
        echo "Signal Service uses a pre-built image from DockerHub."
        docker build --platform linux/amd64 -f Dockerfile -t docker.io/ahmedatoasis/wt3 . --no-cache
        echo "WT3 image rebuilt. Use './scripts/docker-run.sh start' to start the containers."
    fi
}

check_status() {
    echo "Container status:"
    docker ps -a | grep 'wt3'
}

clean_docker() {
    echo "Cleaning all Docker artifacts..."
    docker stop wt3-signal-service wt3-main 2>/dev/null || true
    docker rm wt3-signal-service wt3-main 2>/dev/null || true
    docker rmi docker.io/ahmedatoasis/wt3 2>/dev/null || true
    echo "Docker artifacts cleaned. Use './scripts/docker-run.sh build' to rebuild the images."
}

check_docker

case "$1" in
    start)
        start_container "$2"
        ;;
    stop)
        stop_container "$2"
        ;;
    restart)
        restart_container "$2"
        ;;
    logs)
        show_logs "$2"
        ;;
    build)
        build_image "$2"
        ;;
    clean)
        clean_docker
        ;;
    status)
        check_status
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
