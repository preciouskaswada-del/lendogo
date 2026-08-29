FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y libmagic1 gcc

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

CMD gunicorn lendogo.wsgi:application --bind 0.0.0.0:8080
