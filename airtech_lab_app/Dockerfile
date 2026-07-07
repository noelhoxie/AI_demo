FROM python:3.11-slim

# Install Node.js 20 for frontend build
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies (separate layer for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Frontend — install deps, build, then drop node_modules
COPY frontend/package*.json frontend/
RUN cd frontend && npm install --legacy-peer-deps

COPY frontend/ frontend/
RUN cd frontend && npm run build && rm -rf node_modules

# App source
COPY api.py agent.py config.py db.py databricks_client.py ./

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "180", "api:app"]
