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
