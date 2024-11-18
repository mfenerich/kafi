FROM python:3.10-slim AS base

# Install netcat-openbsd for wait-for-it.sh
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pip and build tools
RUN pip install --upgrade pip setuptools wheel

# Copy the wait-for-it.sh script into the container
COPY .devcontainer/wait-for-it.sh /wait-for-it.sh

# Make the script executable
RUN chmod +x /wait-for-it.sh

# Set entrypoint and command
ENTRYPOINT ["/wait-for-it.sh", "kafka:9092", "--strict", "--"]
CMD ["bash"]
