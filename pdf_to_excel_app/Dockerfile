# syntax=docker/dockerfile:1
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng \
    libgl1 libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/

RUN mkdir -p /root/.streamlit && \
    bash -lc 'cat > /root/.streamlit/config.toml <<EOF
[server]
headless = true
port = 8501
address = "0.0.0.0"
fileWatcherType = "none"

[browser]
gatherUsageStats = false
EOF'

EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
