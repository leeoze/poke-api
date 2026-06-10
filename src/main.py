# =============================================================================
# src/main.py — Ponto de entrada da aplicação FastAPI
#
# Este arquivo é o "coração" da aplicação. Ele:
#   1. Inicializa o logging estruturado (JSON para o ELK)
#   2. Cria a instância do FastAPI com metadados
#   3. Registra middleware de rastreamento de requisições
#   4. Configura handler global de erros inesperados
#   5. Inclui as rotas (endpoints) definidas em routes.py
#   6. Expõe endpoint /health para health checks do Kubernetes
#
# Como o FastAPI funciona:
#   • Recebe requisições HTTP via ASGI (Asynchronous Server Gateway Interface)
#   • O servidor ASGI usado é o Uvicorn (iniciado pelo Docker/comando CLI)
#   • Cada requisição é processada de forma assíncrona (async/await)
# =============================================================================

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.config import settings
from src.database import create_tables
from src.logging_config import configure_logging
from src.routes import router

# =============================================================================
# 1. Inicializa o logging ANTES de qualquer outra coisa
# =============================================================================
configure_logging()
logger = logging.getLogger(__name__)

# =============================================================================
# 2. Lifespan — ciclo de vida da aplicação (startup + shutdown)
#
# O "lifespan" é a forma moderna do FastAPI para definir o que acontece
# quando a aplicação inicia e quando ela encerra.
# Substitui os decoradores @app.on_event("startup"/"shutdown") (obsoletos).
#
# Como funciona o @asynccontextmanager:
#   • Tudo ANTES do "yield" roda no startup
#   • Tudo DEPOIS do "yield" roda no shutdown
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ───────────────────────────────────────────────────────────
    logger.info(
        "Iniciando aplicação",
        extra={"app": settings.APP_NAME, "version": settings.APP_VERSION},
    )
    await create_tables()
    logger.info("Tabelas do banco de dados verificadas/criadas.")

    yield  # ← a aplicação roda aqui, atendendo requisições

    # ── SHUTDOWN ──────────────────────────────────────────────────────────
    # Executado quando a aplicação recebe SIGTERM (Kubernetes, Ctrl+C)
    logger.info("Encerrando aplicação.")


# =============================================================================
# 3. Cria a instância da aplicação FastAPI
# =============================================================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "API RESTful estilo PokéAPI — construída com FastAPI, PostgreSQL, "
        "Redis (cache), Celery (workers), Apache Kafka (eventos) e ELK Stack (logs)."
    ),
    # Registra o lifespan para startup/shutdown modernos
    lifespan=lifespan,
    # Swagger UI interativo (teste os endpoints no navegador)
    docs_url="/docs",
    # ReDoc — documentação alternativa mais elegante
    redoc_url="/redoc",
)


# =============================================================================
# 4. Middleware de rastreamento de requisições
# =============================================================================
@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    """
    Middleware executado em TODA requisição HTTP, antes e depois do endpoint.

    O que faz:
      • Gera um ID único (request_id) para rastrear a requisição nos logs
      • Mede o tempo de resposta
      • Registra entrada e saída de cada request em formato JSON estruturado
      • Adiciona o request_id no header de resposta (útil para debug)

    Esses logs aparecem no Kibana e permitem:
      - Ver quais endpoints são mais lentos
      - Rastrear uma requisição específica pelo request_id
      - Identificar picos de tráfego
    """
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()

    logger.info(
        "Requisição recebida",
        extra={
            "request_id": request_id,
            "method":     request.method,
            "path":       request.url.path,
            "client_ip":  request.client.host if request.client else "unknown",
        },
    )

    # Chama o próximo middleware ou o endpoint em si
    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "Requisição concluída",
        extra={
            "request_id":  request_id,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )

    # Adiciona o ID no header para o cliente poder referenciar nos relatórios
    response.headers["X-Request-ID"] = request_id
    return response


# =============================================================================
# 5. Handler global de exceções não tratadas
# =============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Captura qualquer exceção não tratada pelos endpoints.

    Sem isso, o FastAPI retornaria um erro 500 sem body.
    Com isso, sempre retornamos JSON consistente e logamos o stack trace.

    IMPORTANTE: HTTPExceptions lançadas nos endpoints NÃO chegam aqui —
    elas são tratadas diretamente pelo FastAPI com o status code correto.
    Aqui chegam apenas erros inesperados (bugs, falhas de banco, etc.).
    """
    logger.error(
        "Erro não tratado",
        extra={"path": request.url.path, "error": str(exc)},
        exc_info=True,  # inclui o stack trace completo no log
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor. Tente novamente em instantes."},
    )


# =============================================================================
# 6. Registra as rotas de Pokémons
# =============================================================================
app.include_router(router)


# =============================================================================
# 7. Endpoint de Health Check
# =============================================================================
@app.get(
    "/health",
    tags=["Monitoramento"],
    summary="Verificar saúde da aplicação",
    description="Usado pelo Kubernetes (liveness/readiness probe) e pelo Docker healthcheck.",
)
async def health_check():
    """
    Retorna 200 OK quando a aplicação está funcionando.

    O Kubernetes chama este endpoint periodicamente:
      - Se retornar 200 → container está saudável
      - Se falhar → Kubernetes reinicia o container automaticamente

    Poderia incluir verificação de banco/Redis, mas mantemos simples
    para não criar dependência circular nos probes.
    """
    return {"status": "ok", "version": settings.APP_VERSION}
