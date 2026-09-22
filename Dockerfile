# syntax=docker/dockerfile:1

# Base image ligera
FROM python:3.11-slim

# Evita problemas de buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    ca-certificates \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Confia opcionalmente en la CA del proxy/antivirus local sin desactivar TLS.
RUN --mount=type=secret,id=local_ca,required=false \
    if [ -s /run/secrets/local_ca ]; then \
        cp /run/secrets/local_ca /usr/local/share/ca-certificates/vexxo-local-ca.crt; \
        update-ca-certificates; \
    fi

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar proyecto
COPY . .

# Puerto (Cloud Run usa 8080)
ENV PORT=8080

# Comando de arranque
CMD ["gunicorn", "backend.wsgi:application", "--bind", "0.0.0.0:8080"]
