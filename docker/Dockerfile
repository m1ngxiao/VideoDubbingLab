FROM python:3.10-slim

WORKDIR /workspace/video-dubbing-lab

RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/workspace/video-dubbing-lab

CMD ["python", "-m", "app.cli", "check-env"]
