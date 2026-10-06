# ESTÁGIO 1: Compilação dos Motores Go (Músculos Industriais)
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ESTÁGIO 2: Compilação dos Motores Go
FROM golang:1.21-alpine AS go-builder
WORKDIR /build

# Copia todos os fontes Go
COPY go_engines/ ./go_engines/

# Compila os binários nativos para Linux/AMD64
RUN go build -o semantic_chunker ./go_engines/chunker/main.go
RUN go build -o fast_processor ./go_engines/cleaner/main.go
RUN go build -o graph_turbo ./go_engines/graph/main.go

# ESTÁGIO 3: Ambiente de Execução Python (Cérebro Cognitivo)
FROM python:3.10-slim

# Evita a criação de arquivos .pyc e permite logs em tempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalação de dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cria pasta de binários
RUN mkdir -p /app/bin

# Copia os binários compilados no Estágio 1
COPY --from=go-builder /build/semantic_chunker /app/bin/
COPY --from=go-builder /build/fast_processor /app/bin/
COPY --from=go-builder /build/graph_turbo /app/bin/

# Garante que os motores sejam executáveis
RUN chmod +x /app/bin/*

# --- OTIMIZAÇÃO: Instala primeiro as bibliotecas gigantes ---
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.4.1+cpu \
    sentence-transformers==2.7.0 \
    llama-cpp-python \
    openai-whisper \
    scipy \
    numpy \
    matplotlib

# --- Instala o restante das dependências ---
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Baixa modelos spaCy ---
RUN python -m spacy download en_core_web_sm && \
    python -m spacy download pt_core_news_sm

# Copia o código fonte Python
COPY . .
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

EXPOSE 8000

CMD ["uvicorn", "bridge:app", "--host", "0.0.0.0", "--port", "8000"]
