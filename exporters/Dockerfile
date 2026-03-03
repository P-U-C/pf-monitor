FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    prometheus-client \
    requests

COPY postfiatd_exporter.py .

EXPOSE 9750

CMD ["python", "postfiatd_exporter.py"]
