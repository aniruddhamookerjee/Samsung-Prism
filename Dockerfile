# Samsung PRISM XR Hackathon 2026 - Track 3: Path Finder
# Docker container for reproducible standalone evaluation of src/main.py

FROM python:3.11-slim

# Set environment variables for single-threaded deterministic execution
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

WORKDIR /app

# Install minimal dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and execution assets
COPY src/ ./src/
COPY README.md .

# Default execution interface:
# Example: docker run --rm -v $(pwd)/data:/data pathfinder /data/degraded/imu0/data.csv /data/output.txt
ENTRYPOINT ["python", "src/main.py"]
CMD ["--help"]
