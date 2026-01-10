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
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files first to leverage Docker cache
COPY requirements.txt requirements_phase2.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements_phase2.txt

# Copy the rest of the application files
COPY . .

# Create necessary directories
RUN mkdir -p /app/data /app/cache /app/.cache /app/migrations

# Expose the application port (Render uses PORT env variable)
EXPOSE 8000

# Specify environment variables
ENV PYTHONPATH=/app \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Run the application (Render will provide PORT env variable)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info
