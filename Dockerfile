FROM python:3.11-slim

# System deps for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download model at build time so it's baked into the image
RUN python -c "from engine.model_utils import ensure_model_file; ensure_model_file()"

EXPOSE 8000

ENV KIRTI_HOST=0.0.0.0
ENV KIRTI_PORT=8000
ENV KIRTI_WORKERS=1

CMD ["python", "run.py"]
