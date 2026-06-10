# =============================================================================
# src/workers/celery_app.py — Configuração do Celery
#
# O que é o Celery?
#   Celery é uma fila de tarefas distribuída para Python.
#   Permite executar funções pesadas em BACKGROUND, sem bloquear a API.
#
# Analogia simples:
#   Imagine uma lanchonete (API).
#   O atendente (endpoint) recebe o pedido, anota num bilhete (mensagem Kafka)
#   e entrega para a cozinha (Celery Worker) processar.
#   O cliente (cliente HTTP) não precisa esperar o preparo — recebe a
#   confirmação do pedido imediatamente.
#
# Componentes:
#   celery_app   → instância principal configurada
#   broker       → onde as tarefas são enfileiradas (Redis banco 1)
#   backend      → onde os resultados são armazenados (Redis banco 2)
#
# Como subir o Worker localmente:
#   celery -A src.workers.celery_app worker --loglevel=info
# =============================================================================

from celery import Celery

from src.config import settings


# Cria a instância do Celery
# "poke_workers" é apenas o nome interno desta instância
celery_app = Celery(
    "poke_workers",

    # broker: fila onde os jobs são depositados
    # A API escreve aqui; o Worker lê daqui
    broker=settings.CELERY_BROKER_URL,

    # backend: onde guardar o resultado de cada job executado
    # Permite consultar depois se a tarefa foi concluída/falhou
    backend=settings.CELERY_RESULT_BACKEND,

    # Lista os módulos que contêm as @celery_app.task
    # O Celery precisa importá-los para "conhecer" as tarefas disponíveis
    include=["src.workers.tasks"],
)

# =============================================================================
# Configurações de comportamento do Celery
# =============================================================================
celery_app.conf.update(
    # Serializa mensagens como JSON (legível e seguro)
    task_serializer     = "json",
    result_serializer   = "json",
    accept_content      = ["json"],

    # Fuso horário UTC — padrão para sistemas distribuídos
    timezone            = "UTC",
    enable_utc          = True,

    # Registra o estado "STARTED" quando a tarefa começa a executar
    # Útil para monitoramento — você sabe se a tarefa travou ou está rodando
    task_track_started  = True,

    # prefetch_multiplier=1 → o Worker pega uma tarefa por vez
    # Evita que um Worker "segure" muitas tarefas enquanto outros ficam ociosos
    # Importante para tarefas longas (como download de imagens)
    worker_prefetch_multiplier = 1,

    # Tempo máximo (segundos) que uma tarefa pode rodar antes de ser cancelada
    task_soft_time_limit = 120,
    task_time_limit      = 180,
)
