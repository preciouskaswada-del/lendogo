FROM python:3.11-slim
WORKDIR /app
RUN apt-get update
RUN apt-get install -y libmagic1
RUN apt-get install -y gcc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD gunicorn lendogo.wsgi:application --bind 0.0.0.0:$PORT
