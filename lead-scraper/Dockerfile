# -------------------------------------------------------
# Stage 1 — Build do frontend React com Node
# -------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY lead-scraper/frontend/package*.json ./
RUN npm install

COPY lead-scraper/frontend/ ./
RUN npm run build


# -------------------------------------------------------
# Stage 2 — Imagem oficial do Playwright (Ubuntu Jammy)
# Já vem com todas as dependências do Chromium instaladas.
# Usar python:3.11-slim causava falha por pacotes ausentes
# no Debian Trixie (ttf-unifont, ttf-ubuntu-font-family).
# -------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Instalar dependências Python
COPY lead-scraper/backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Instalar apenas o browser (sem --with-deps, pois a imagem já tem tudo)
RUN playwright install chromium

# Copiar o código do backend
COPY lead-scraper/backend/ ./backend/

# Copiar o build do React gerado no Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
