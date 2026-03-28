# Base image ligera
FROM python:3.11-slim

# Evita problemas de buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    && apt-get clean

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