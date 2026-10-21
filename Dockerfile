FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Keep the database in a folder you can mount as a volume
ENV DATABASE=/data/database.db \
    PORT=5001
RUN mkdir -p /data

EXPOSE 5001

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} 'app:create_app()'"]
