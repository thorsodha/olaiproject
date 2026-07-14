# Use an official lightweight Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging for live stream logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies needed for certain Python libraries if applicable
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker's caching mechanism
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY main.py .
COPY ta_analyzer.py .
COPY dashboard_generator.py .
COPY config.py .
COPY sparkline_generator.py .
COPY htmlgraph_generator.py .
COPY price_fetcherv2.py .
COPY watchlist.xlsx .

# --- FIX: Create the required production directories ---
RUN mkdir -p /app/oslobors

# Expose the default Cloud Run port
EXPOSE 8080

# --- UPDATED STARTUP COMMAND FOR PRODUCTION ---
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "30", "main:app"]



