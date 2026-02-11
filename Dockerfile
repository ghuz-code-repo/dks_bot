FROM python:3.11-slim

# Устанавливаем часовой пояс Ташкента (UTC+5)
ENV TZ=Asia/Tashkent

# Исправленный блок установки системных зависимостей
RUN apt-get update || (sleep 5 && apt-get update) && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data

CMD ["python", "main.py"]