FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BEATBRIDGE_DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY beatbridge ./beatbridge
COPY scripts ./scripts
COPY main.py main-spot-to-yt.py README.md ./

CMD ["python", "main.py", "--check-auth", "--no-browser", "--no-notify"]
