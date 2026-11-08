FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-job.txt .
RUN pip install --no-cache-dir -r requirements-job.txt
COPY src ./src
COPY data/snapshot ./data/snapshot
ENV PYTHONPATH=/app/src
ENV JRR_ROOT=/app
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "jrr.k8s_entry"]
