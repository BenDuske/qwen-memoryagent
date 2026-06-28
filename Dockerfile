# Aegis MemoryAgent — deployable to Alibaba Cloud (ECS / Function Compute / Container).
FROM python:3.12-slim
WORKDIR /app
COPY . /app
# Install the package + the FastAPI service extra so the same image serves HTTP or CLI.
RUN pip install --no-cache-dir ".[service]"
ENV MEMORY_DIR=/data/memory
VOLUME ["/data"]
EXPOSE 8000
# Default: HTTP service (the deployable face). For the CLI instead, override with:
#   docker run ... aegis-memoryagent python -m memoryagent.cli
CMD ["python", "-m", "uvicorn", "memoryagent.app:app", "--host", "0.0.0.0", "--port", "8000"]
