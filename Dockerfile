ARG PYTHON_IMAGE=mirror.gcr.io/library/python:3.12-slim
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 \
    --index-url ${PIP_INDEX_URL} -r requirements.txt

COPY . .
