FROM python:3.12-slim

ARG VERSION=dev
LABEL org.opencontainers.image.title="pf-monitor postfiatd exporter" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/P-U-C/pf-monitor"

WORKDIR /app

RUN pip install --no-cache-dir \
    prometheus-client \
    requests

COPY postfiatd_exporter.py .

EXPOSE 9750

CMD ["python", "postfiatd_exporter.py"]
