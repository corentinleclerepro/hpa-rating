FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HPA_ENV=production \
    HPA_DATA_DIR=/state/private HPA_REGISTRY_DIR=/state/registry
WORKDIR /opt/hpa
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt \
 && groupadd --gid 10001 hpa && useradd --uid 10001 --gid hpa --no-create-home hpa \
 && install -d -m 0700 -o hpa -g hpa /state/private /state/registry
COPY hpa_shared hpa_shared
COPY run_production.py ./
USER hpa

FROM base AS guest
COPY app app
COPY data/referentiel.json data/referentiel-v1.json ./data/
CMD ["python", "run_production.py", "guest"]

FROM base AS admin
COPY administration administration
COPY run_admin.py ./
CMD ["python", "run_production.py", "admin"]
