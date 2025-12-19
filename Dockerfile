# Use Python 3.12 as base image
FROM python:3.12-slim

# Set working directory to the parent of app
WORKDIR /workspace

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY app/requirements.txt ./app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r ./app/requirements.txt

# Copy application code maintaining the app directory structure
COPY app/ ./app/

# Copy .env file from the project root
COPY .env ./

# Add the workspace directory to Python path so app.* imports work
ENV PYTHONPATH=/workspace
ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=docker

# Expose port
EXPOSE 8000

# Command to run the application with increased limits
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "600", "--limit-max-requests", "1000", "--h11-max-incomplete-event-size", "134217728", "--timeout-graceful-shutdown", "60", "--backlog", "2048"]