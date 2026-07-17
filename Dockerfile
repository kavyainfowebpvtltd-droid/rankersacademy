FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
default-libmysqlclient-dev \
build-essential \
pkg-config

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn","sds_main.wsgi:application","--bind","0.0.0.0:8000"]
