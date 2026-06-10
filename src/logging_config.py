# =============================================================================
# src/logging_config.py — Configuração de logging com envio ao Logstash
#
# Problema original:
#   O logging só escrevia no stdout (terminal do container).
#   O Logstash escuta na porta TCP 5044, mas ninguém enviava nada.
#
# Solução aplicada:
#   Adicionamos um segundo handler (LogstashHandler) que envia cada log
#   como JSON via TCP direto para o Logstash na porta 5044.
#
# Fluxo corrigido:
#   FastAPI gera log
#     ├── StreamHandler  → stdout do container (visível no docker logs)
#     └── LogstashHandler → TCP 5044 → Logstash → Elasticsearch → Kibana
# =============================================================================

import logging
import logging.handlers
import sys
import socket
import json

from src.config import settings
from datetime import datetime



class LogstashTCPHandler(logging.Handler):
    """
    Handler customizado que envia cada log como JSON via TCP para o Logstash.

    Por que criar um handler customizado?
      A biblioteca python-logstash existe, mas adiciona dependência extra.
      Este handler faz exatamente o necessário: serializa o log em JSON
      e envia via socket TCP para host:porta do Logstash.

    Comportamento em caso de falha:
      Se o Logstash estiver offline, o log é descartado silenciosamente.
      A aplicação NUNCA deve travar por causa do sistema de logs.
    """

    def __init__(self, host: str, port: int):
        super().__init__()
        self.host = host
        self.port = port

    def emit(self, record: logging.LogRecord) -> None:
        """
        Chamado automaticamente pelo Python para cada log gerado.
        Serializa o LogRecord em JSON e envia via TCP.
        """
        try:
            # Monta o dicionário com os campos do log
            log_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "level":     record.levelname,
                "logger":    record.name,
                "message":   record.getMessage(),
            }

            # Adiciona campos extras passados via extra={} no logger
            # ex: logger.info("msg", extra={"request_id": "abc", "duration_ms": 42})
            for key, value in record.__dict__.items():
                if key not in (
                    "name", "msg", "args", "levelname", "levelno",
                    "pathname", "filename", "module", "exc_info",
                    "exc_text", "stack_info", "lineno", "funcName",
                    "created", "msecs", "relativeCreated", "thread",
                    "threadName", "processName", "process", "message",
                    "taskName",
                ):
                    log_entry[key] = value

            # Serializa para JSON e adiciona newline (necessário para json_lines)
            payload = json.dumps(log_entry, default=str) + "\n"

            # Envia via TCP — cria nova conexão a cada log (simples e robusto)
            with socket.create_connection(
                (self.host, self.port), timeout=2
            ) as sock:
                sock.sendall(payload.encode("utf-8"))

        except Exception:
            # Nunca deixa o sistema de logs derrubar a aplicação
            self.handleError(record)


def configure_logging() -> None:
    """
    Configura dois handlers:
      1. StreamHandler  → escreve JSON no stdout (visível em docker compose logs)
      2. LogstashTCPHandler → envia JSON via TCP para Logstash:5044

    Deve ser chamada UMA VEZ em main.py antes de qualquer outra coisa.
    """
    from pythonjsonlogger import jsonlogger

    # ── Handler 1: stdout (terminal / docker logs) ────────────────────────
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        rename_fields={
            "asctime":   "timestamp",
            "name":      "logger",
            "levelname": "level",
        },
    )
    stream_handler.setFormatter(stream_formatter)

    # ── Handler 2: Logstash via TCP ───────────────────────────────────────
    logstash_handler = LogstashTCPHandler(
        host=settings.LOGSTASH_HOST,
        port=settings.LOGSTASH_PORT,
    )
    # Nível mínimo: só envia INFO ou acima para o Logstash
    # (evita flood de DEBUG no Elasticsearch)
    logstash_handler.setLevel(logging.INFO)

    # ── Configura o root logger com os dois handlers ──────────────────────
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(logstash_handler)

    # Silencia loggers muito verbosos de bibliotecas externas
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.DEBUG else logging.WARNING
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiokafka").setLevel(logging.WARNING)