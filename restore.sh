#!/bin/bash

# Create directory structure
mkdir -p storage/{originals,processed/{avif,webp},temp}
mkdir -p nginx/conf.d
mkdir -p app
touch app/__init__.py

# Create .env
cat > .env << EOF
# Server Configuration
DEBUG=True
HOST=0.0.0.0
PORT=8000
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Storage Configuration
STORAGE_PATH=/app/storage
MAX_FILE_SIZE=10
EOF

# Create .env.example
cat > .env.example << "EOL"
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
STORAGE_PATH=/app/storage
MAX_WORKERS=2  # Number of parallel image processing processes
AVIF_EFFORT=2  # AVIF compression setting (2 = good trade-off)
EOL

# Create .gitignore
cat > .gitignore << "EOL"
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg
.env
.env.*
!.env.example
.venv
.coverage
coverage.xml
.pytest_cache/
.DS_Store
.idea/
.vscode/
storage/*
!storage/.gitkeep
logs/*
!logs/.gitkeep
EOL

# Create docker-compose.yml
cat > docker-compose.yml << "EOL"
version: '3.8'

services:
  api:
    build: 
      context: .
      dockerfile: Dockerfile
    volumes:
      - .:/app
      - ./storage:/app/storage
    ports:
      - "8000:8000"
    environment:
      - DEBUG=1
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - bragi-network

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./storage:/var/www/storage:ro
    depends_on:
      - api
    networks:
      - bragi-network

networks:
  bragi-network:
    driver: bridge
EOL

# Create Dockerfile
cat > Dockerfile << "EOL"
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    libvips \
    libvips-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create necessary directories
RUN mkdir -p storage/originals storage/processed/avif storage/processed/webp logs

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOL

# Create requirements.txt
cat > requirements.txt << "EOL"
fastapi==0.104.1
uvicorn==0.24.0
python-multipart==0.0.6
pydantic==2.4.2
pyvips==2.2.1
python-dotenv==1.0.0
aiofiles==23.2.1
pytest==7.4.3
black==23.10.1
flake8==6.1.0
EOL

# Create Makefile
cat > Makefile << "EOL"
.PHONY: build up down logs test lint format

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

test:
	docker-compose run --rm api pytest

lint:
	docker-compose run --rm api flake8 .
	docker-compose run --rm api black . --check

format:
	docker-compose run --rm api black .
EOL

# Create README.md
cat > README.md << "EOL"
# Bragi Image Server

Ein hochperformanter Image Server für automatische Bildoptimierung und -konvertierung.

## Features

- Automatische Konvertierung in AVIF und WebP
- Responsive Bildgrößen (1920px, 1280px, 800px)
- Effizientes Caching
- Asynchrone Verarbeitung
- Docker-basierte Deployment

## Technologie-Stack

- FastAPI Backend
- Nginx Reverse Proxy
- libvips für Bildverarbeitung
- Docker & Docker Compose
- Ubuntu VPS Host

## Installation

1. Repository klonen:
   \`\`\`bash
   git clone https://github.com/losspamerianos/bragi.git
   cd bragi
   \`\`\`

2. Umgebungsvariablen konfigurieren:
   \`\`\`bash
   cp .env.example .env
   # .env nach Bedarf anpassen
   \`\`\`

3. Docker Container starten:
   \`\`\`bash
   make build
   make up
   \`\`\`

## Entwicklung

- Code formatieren: \`make format\`
- Tests ausführen: \`make test\`
- Linting durchführen: \`make lint\`
- Logs anzeigen: \`make logs\`

## Lizenz

MIT
EOL

# Create nginx.conf
cat > nginx/nginx.conf << "EOL"
user  nginx;
worker_processes  auto;

error_log  /var/log/nginx/error.log notice;
pid        /var/run/nginx.pid;

events {
    worker_connections  1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    log_format  main  '\$remote_addr - \$remote_user [\$time_local] "\$request" '
                      '\$status \$body_bytes_sent "\$http_referer" '
                      '"\$http_user_agent" "\$http_x_forwarded_for"';

    access_log  /var/log/nginx/access.log  main;

    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;

    keepalive_timeout  65;

    # GZIP configuration
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript application/rss+xml application/atom+xml image/svg+xml;

    include /etc/nginx/conf.d/*.conf;
}
EOL

# Create nginx default.conf
cat > nginx/conf.d/default.conf << "EOL"
server {
    listen 80;
    server_name localhost;

    client_max_body_size 10M;

    # API endpoints
    location /api/ {
        proxy_pass http://api:8000/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Cached images
    location /storage/ {
        alias /var/www/storage/;
        expires 7d;
        add_header Cache-Control "public, no-transform";
        try_files \$uri @backend;
    }

    # Fallback to API for image processing
    location @backend {
        proxy_pass http://api:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOL

# Create empty files for git to track empty directories
touch storage/.gitkeep

# Make the script executable
chmod +x \$0

echo "Project structure has been restored!"
