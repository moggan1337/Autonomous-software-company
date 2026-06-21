FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    COMPANY_DB=/data/company.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY company ./company
COPY web ./web
COPY run.py ./

# Company state lives on a volume so it survives container restarts.
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

CMD ["python", "run.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
