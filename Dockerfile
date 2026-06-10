# =============================================================================
# Dockerfile — Build multi-stage com Poetry
#
# O que é multi-stage build?
#   É uma técnica para criar imagens Docker menores e mais seguras.
#   Dividimos em dois estágios:
#
#   Stage 1 "builder":
#     • Instala Poetry e todas as dependências
#     • Constrói os pacotes Python
#     • Contém ferramentas de build (gcc, etc.) — necessárias para compilar
#
#   Stage 2 "runtime":
#     • Copia APENAS os pacotes compilados do stage 1
#     • Não carrega Poetry, gcc, pip, nem nada de build
#     • Resultado: imagem final muito menor (~300MB vs ~600MB)
#     • Menor superfície de ataque (segurança)
#
# Comandos:
#   docker build -t poke-api .                    → build
#   docker run -p 8000:8000 poke-api              → executa
#   docker build --target builder -t poke-api-dev → só o stage de dev
# =============================================================================

# =============================================================================
# STAGE 1: builder — instala dependências
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Variáveis que tornam o Python mais previsível em containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Impede o pip de verificar versões (mais rápido no build)
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Configura o Poetry para não criar virtualenv (já estamos em container)
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_VERSION=1.8.3

# Instala dependências de sistema necessárias para compilar pacotes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala o Poetry via pip
RUN pip install "poetry==${POETRY_VERSION}"

# Copia os arquivos de definição de dependências primeiro
# (Docker cacheia este layer se pyproject.toml não mudar — builds mais rápidos)
COPY pyproject.toml poetry.lock* ./

# Instala APENAS dependências de produção (sem --dev)
# --no-root = não instala o projeto em si, só as dependências
RUN poetry install --only=main --no-root

# Copia o código fonte
COPY src/ ./src/


# =============================================================================
# STAGE 2: runtime — imagem de produção enxuta
# =============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app"

# Apenas bibliotecas de runtime (sem compiladores)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia os pacotes Python instalados pelo builder
# (site-packages contém todas as bibliotecas)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copia o código fonte da aplicação
COPY --from=builder /app/src ./src/

# ── Segurança: executa como usuário não-root ──────────────────────────────
# Rodar como root em container é risco de segurança
# Se o processo for comprometido, o atacante tem privilégios limitados
RUN groupadd --gid 1001 appgroup && \
    useradd  --uid 1001 --gid appgroup --no-create-home appuser && \
    chown -R appuser:appgroup /app

USER appuser

# Porta exposta pelo container (deve coincidir com o uvicorn)
EXPOSE 8000

# Health check do Docker — verifica se a aplicação está respondendo
# --interval=30s  → verifica a cada 30 segundos
# --timeout=10s   → aguarda até 10s pela resposta
# --retries=3     → marca como unhealthy após 3 falhas consecutivas
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando de inicialização
# --host 0.0.0.0  → aceita conexões de qualquer IP (necessário em container)
# --workers 2     → 2 processos workers (ajuste conforme núcleos da CPU)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
