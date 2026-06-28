# Aegis MemoryAgent — deployable to Alibaba Cloud (ECS / Function Compute / Container).
FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
ENV MEMORY_DIR=/data/memory
VOLUME ["/data"]
# Default: interactive CLI. For a service, swap to the FastAPI app (see DEPLOY.md).
CMD ["python", "-m", "memoryagent.cli"]
