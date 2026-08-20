FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py timeparse.py ./

# база й лог живуть у томі, щоб переживали перезбірку образу
ENV DB_PATH=/data/reminders.db \
    LOG_PATH=/data/bot.log \
    PYTHONUNBUFFERED=1
VOLUME /data

CMD ["python", "bot.py"]
