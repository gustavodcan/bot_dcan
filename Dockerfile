FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    locales \
    libleptonica-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl && \
    curl -L -o /usr/share/tesseract-ocr/4.00/tessdata/por.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/por.traineddata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 10000

CMD ["python", "app.py"]
