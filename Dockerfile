# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    libpq-dev \
    wget \
    redis-server \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files first to leverage Docker cache
COPY requirements.txt requirements_phase2.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements_phase2.txt

# Copy the rest of the application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/cache /app/.cache /app/migrations /var/log/supervisor /var/run/redis

# Expose the application port (Render uses PORT env variable)
EXPOSE 8000

# Specify environment variables
ENV PYTHONPATH=/app \
    PORT=8000 \
    REDIS_HOST=127.0.0.1 \
    REDIS_PORT=6379 \
    REDIS_DB=0

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Run supervisor to manage both Redis and the app
CMD ["/app/start.sh"]
