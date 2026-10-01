FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 STATE_FILE=/data/processed.json
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
RUN useradd -m bot && mkdir /data && chown bot /data
USER bot
VOLUME /data

CMD ["python", "main.py"]
