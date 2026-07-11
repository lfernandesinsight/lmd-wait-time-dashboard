# Dockerfile do serviço ETL.
# Build context é a raiz do projeto (por causa do requirements.txt),
# por isso o docker-compose aponta dockerfile: etl/Dockerfile com context: .

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY etl/ ./

# Roda uma vez e sai (não é um serviço de longa duração).
# Uso: docker compose run --rm etl
CMD ["python", "main.py"]
