FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tps/ tps/
COPY templates/ templates/
COPY static/ static/
COPY scripts/ scripts/

RUN useradd -r -s /bin/false tps

ENV TPS_HOST=0.0.0.0 \
    TPS_PORT=8000 \
    TPS_WORKSPACE=/data

VOLUME ["/data"]

RUN chown tps /app && chmod +x scripts/start.sh
USER tps

EXPOSE 8000

CMD ["bash", "scripts/start.sh"]
