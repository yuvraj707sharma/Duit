FROM python:3.11.10-slim-bookworm

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy source code
COPY backend/ /app/backend/
COPY contracts/ /app/contracts/

ENV PYTHONPATH=/app

EXPOSE ${PORT:-8000}

# Use shell form so $PORT from Render is expanded at runtime
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
