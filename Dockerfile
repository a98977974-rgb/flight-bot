FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir pyTelegramBotAPI aiohttp pytz

CMD ["sh", "-c", "python *.py"]
