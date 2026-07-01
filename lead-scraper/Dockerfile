# -------------------------------------------------------
# Stage 1 — Build do frontend React com Node
# -------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Instalar dependências primeiro (melhor cache do Docker)
COPY frontend/package*.json ./
RUN npm install

# Copiar código e gerar o build de produção
COPY frontend/ ./
RUN npm run build
# Resultado: /app/frontend/dist/


# -------------------------------------------------------
# Stage 2 — Backend Python com Playwright
# -------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Dependências de sistema para o Chromium headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 \
    libx11-6 libx11-xcb1 libxcb1 libxext6 \
    wget curl ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências Python
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Instalar o Chromium do Playwright (com todas as dependências)
RUN playwright install chromium --with-deps

# Copiar o código do backend
COPY backend/ ./backend/

# Copiar o build do React gerado no Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Porta exposta para o EasyPanel/Traefik
EXPOSE 8000

# Diretório de trabalho do servidor
WORKDIR /app/backend

# Iniciar o servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
