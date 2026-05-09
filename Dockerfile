FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/main.py .
COPY backend/start.sh .

EXPOSE 8000

CMD ["bash", "start.sh"]
