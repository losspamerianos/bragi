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
