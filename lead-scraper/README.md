# 🔍 Buscador de Leads — Google Maps

Ferramenta para coletar contatos de empresas no Google Maps e extrair números de WhatsApp automaticamente.

## Arquitetura

```
┌─────────────────────────────────────────────────┐
│  Nginx (porta 80)                               │
│  ├── /         → React build (dist/)            │
│  └── /api/     → FastAPI (127.0.0.1:8000)       │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  FastAPI (uvicorn)                              │
│  ├── POST /api/search    → inicia scraping      │
│  ├── GET  /api/status/id → SSE com progresso    │
│  └── GET  /api/export/id → download .xlsx       │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  Playwright (Chromium headless)                 │
│  └── Scraping do Google Maps                    │
└─────────────────────────────────────────────────┘
```

---

## Deploy no VPS Hostinger — Ubuntu 22.04

### Pré-requisitos

- VPS Ubuntu 22.04 com acesso root via SSH
- Domínio ou IP público configurado

---

### 1. Conectar no VPS e atualizar o sistema

```bash
ssh root@SEU_IP_VPS

apt update && apt upgrade -y
```

---

### 2. Instalar Python 3.11

```bash
# Python 3.11 já vem com Ubuntu 22.04, mas confirmar versão:
python3 --version

# Se não tiver 3.11:
apt install -y software-properties-common
add-apt-repository ppa:deadsnakes/ppa
apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

---

### 3. Instalar Node.js 18+

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
node --version   # deve mostrar v20.x.x
npm --version
```

---

### 4. Instalar Nginx

```bash
apt install -y nginx
systemctl enable nginx
systemctl start nginx
```

---

### 5. Instalar dependências do Playwright (Chromium)

```bash
# Bibliotecas do sistema necessárias para o Chromium headless
apt install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libasound2 libpango-1.0-0 libcairo2 \
    xvfb fonts-liberation
```

---

### 6. Criar estrutura de diretórios e copiar os arquivos

```bash
# Criar diretório do projeto
mkdir -p /var/www/lead-scraper

# Opção A: Clonar do repositório git
git clone https://github.com/SEU_USUARIO/lead-scraper.git /var/www/lead-scraper

# Opção B: Copiar manualmente via SCP (do seu computador local):
# scp -r ./lead-scraper root@SEU_IP_VPS:/var/www/lead-scraper
```

---

### 7. Configurar o backend Python

```bash
cd /var/www/lead-scraper

# Criar virtualenv
python3.11 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install --upgrade pip
pip install -r backend/requirements.txt

# Instalar o Chromium do Playwright
playwright install chromium

# Definir onde o Playwright vai salvar os browsers
export PLAYWRIGHT_BROWSERS_PATH=/var/www/lead-scraper/.playwright
playwright install chromium --with-deps

# Desativar virtualenv por enquanto
deactivate
```

---

### 8. Build do frontend React

```bash
cd /var/www/lead-scraper/frontend

# Instalar dependências Node
npm install

# Gerar build de produção (cria a pasta dist/)
npm run build

# Verificar que foi criado
ls -la dist/
```

---

### 9. Configurar o Nginx

```bash
# Copiar a configuração
cp /var/www/lead-scraper/nginx.conf /etc/nginx/sites-available/lead-scraper

# Ativar o site
ln -sf /etc/nginx/sites-available/lead-scraper /etc/nginx/sites-enabled/lead-scraper

# Remover o site default (opcional, mas recomendado)
rm -f /etc/nginx/sites-enabled/default

# Testar a configuração
nginx -t

# Se OK, recarregar
systemctl reload nginx
```

**Opcional:** Se tiver um domínio, edite o nginx.conf e substitua `server_name _;` por:
```
server_name meudominio.com www.meudominio.com;
```

---

### 10. Configurar o serviço systemd do backend

```bash
# Copiar o arquivo de serviço
cp /var/www/lead-scraper/lead-scraper.service /etc/systemd/system/

# Ajustar permissões do diretório
chown -R www-data:www-data /var/www/lead-scraper

# Reload do systemd para reconhecer o novo serviço
systemctl daemon-reload

# Habilitar para iniciar automaticamente no boot
systemctl enable lead-scraper

# Iniciar o serviço
systemctl start lead-scraper

# Verificar que está rodando
systemctl status lead-scraper
```

---

### 11. Verificar que tudo está funcionando

```bash
# Checar se o backend responde na porta 8000
curl http://127.0.0.1:8000/api/health

# Checar se o Nginx está passando o proxy corretamente
curl http://SEU_IP_VPS/api/health

# Abrir no navegador
# http://SEU_IP_VPS
```

---

## Comandos úteis de manutenção

### Ver logs do backend em tempo real

```bash
journalctl -u lead-scraper -f
```

### Ver logs do Nginx

```bash
tail -f /var/log/nginx/lead-scraper.access.log
tail -f /var/log/nginx/lead-scraper.error.log
```

### Reiniciar o backend após atualização de código

```bash
# Recompilar o frontend se houve mudança
cd /var/www/lead-scraper/frontend
npm run build

# Reiniciar o serviço Python
systemctl restart lead-scraper
systemctl status lead-scraper
```

### Atualizar dependências Python

```bash
source /var/www/lead-scraper/venv/bin/activate
pip install -r /var/www/lead-scraper/backend/requirements.txt
deactivate
systemctl restart lead-scraper
```

### Verificar uso de memória e CPU

```bash
# Processos do serviço
ps aux | grep uvicorn

# Uso de memória geral
free -h

# Chromium pode consumir bastante RAM com scraping intenso
# Monitore com:
watch -n 2 'ps aux --sort=-%mem | head -15'
```

### Parar/iniciar manualmente

```bash
systemctl stop lead-scraper
systemctl start lead-scraper
```

---

## Solução de problemas comuns

### Playwright não encontra o Chromium

```bash
# Verificar que os browsers estão instalados
ls /var/www/lead-scraper/.playwright/

# Reinstalar se necessário
source /var/www/lead-scraper/venv/bin/activate
PLAYWRIGHT_BROWSERS_PATH=/var/www/lead-scraper/.playwright playwright install chromium --with-deps
deactivate
```

### Erro de permissão no www-data

```bash
chown -R www-data:www-data /var/www/lead-scraper
chmod -R 755 /var/www/lead-scraper
```

### Backend não inicia (porta 8000 em uso)

```bash
# Ver o que está usando a porta
lsof -i :8000

# Matar processo específico
kill -9 PID_DO_PROCESSO
```

### SSE não funciona (progresso não atualiza)

Verificar se o `proxy_buffering off` está na configuração do Nginx:
```bash
grep -n "proxy_buffering" /etc/nginx/sites-available/lead-scraper
# Deve mostrar: proxy_buffering off;
```

### Google Maps retorna poucos resultados

O Google Maps pode limitar resultados por localização muito ampla. Tente:
- Especificar cidade + estado (ex: "Salvador, BA" em vez de apenas "Brasil")
- Usar nicho mais específico (ex: "academia de musculação" em vez de "academia")
- Aguardar alguns minutos entre buscas para evitar rate limiting

---

## Estrutura de arquivos

```
lead-scraper/
├── backend/
│   ├── main.py               # FastAPI: endpoints de busca, SSE e export
│   ├── scraper.py            # Playwright: scraping do Google Maps
│   ├── whatsapp_extractor.py # httpx: extração de WhatsApp dos sites
│   ├── exporter.py           # openpyxl: geração do arquivo .xlsx
│   └── requirements.txt      # Dependências Python com versões fixadas
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Componente raiz, gerencia estado e SSE
│   │   ├── index.css         # Estilos globais
│   │   ├── main.jsx          # Entry point React
│   │   └── components/
│   │       ├── SearchForm.jsx   # Formulário de busca
│   │       ├── StatusBar.jsx    # Barra de progresso em tempo real
│   │       └── ResultsTable.jsx # Tabela de resultados e export
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── nginx.conf                # Configuração do Nginx com suporte a SSE
├── lead-scraper.service      # Serviço systemd para o backend
└── README.md
```
