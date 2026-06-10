# =============================================================================
# src/workers/tasks.py — Tarefas assíncronas em background (Celery)
#
# O que são Tasks Celery?
#   São funções Python decoradas com @celery_app.task que rodam em background,
#   fora do ciclo de requisição/resposta da API.
#
# Fluxo completo neste projeto:
#
#   1. API cria/atualiza Pokémon (routes.py)
#        ↓
#   2. Publica evento no Kafka (kafka/producer.py)
#        ↓
#   3. Esta tarefa lê o evento e processa em background:
#      - Baixa as imagens de sprites das URLs
#      - Registra métricas de tamanho/tipo
#      - Em produção: comprimiria e salvaria num bucket S3/MinIO
#        ↓
#   4. Resultado salvo no Redis (backend do Celery)
#
# Por que separar do request HTTP?
#   Download de imagens pode levar segundos. Se fizéssemos isso dentro
#   do endpoint, o cliente esperaria. Com Celery, o endpoint responde
#   em <100ms e o download acontece em paralelo.
# =============================================================================

import json
import logging
from typing import Any

import httpx

from src.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    # bind=True → permite acessar `self` para retry e metadados da tarefa
    bind=True,

    # Nome explícito — facilita monitoramento no Flower (UI do Celery)
    name="tasks.process_pokemon_event",

    # Quantas vezes tentar novamente em caso de falha
    max_retries=3,

    # Segundos de espera entre tentativas (evita sobrecarregar serviços com erro)
    default_retry_delay=15,
)
def process_pokemon_event(self, event_payload: str) -> dict[str, Any]:
    """
    Processa um evento de Pokémon recebido do Kafka.

    Responsabilidades:
      1. Deserializa o payload JSON do evento
      2. Extrai as URLs de sprites do Pokémon
      3. Faz download de cada imagem
      4. Retorna um relatório com status de cada download

    Args:
        event_payload: String JSON com o evento. Formato:
            {
                "event": "pokemon.created",
                "data": {
                    "id": 25,
                    "name": "pikachu",
                    "sprites": {
                        "front_default": "https://...",
                        "back_default": "https://..."
                    }
                }
            }

    Returns:
        Dicionário com resultado do processamento:
        {
            "pokemon_id": 25,
            "sprites_processed": {
                "front_default": {"status": "downloaded", "size_bytes": 1234},
                "back_default": {"status": "error", "reason": "timeout"}
            }
        }
    """
    try:
        # Passo 1: Deserializa o JSON recebido do Kafka
        event = json.loads(event_payload)
        event_type   = event.get("event", "unknown")
        pokemon_data = event.get("data", {})
        pokemon_id   = pokemon_data.get("id")

        logger.info(
            "Processando evento '%s' para Pokémon id=%s",
            event_type,
            pokemon_id,
        )

        # Passo 2: Extrai as URLs dos sprites
        sprites: dict = pokemon_data.get("sprites") or {}
        resultados: dict[str, Any] = {}

        # Passo 3: Baixa cada sprite
        for sprite_key, url in sprites.items():
            # Pula sprites sem URL definida
            if not url:
                resultados[sprite_key] = {"status": "skipped", "reason": "url vazia"}
                continue

            try:
                # httpx.get é síncrono — correto pois tasks Celery são síncronas
                # timeout=10 evita que o worker fique preso indefinidamente
                response = httpx.get(url, timeout=10, follow_redirects=True)
                response.raise_for_status()  # lança exceção se status >= 400

                resultados[sprite_key] = {
                    "status":       "downloaded",
                    "size_bytes":   len(response.content),
                    "content_type": response.headers.get("content-type", "unknown"),
                }
                logger.debug(
                    "Sprite baixado: %s → %d bytes",
                    sprite_key,
                    len(response.content),
                )

                # 💡 Em produção, aqui você salvaria a imagem em:
                # - S3/MinIO (armazenamento de objetos)
                # - Redis (cache de bytes) com TTL longo
                # - Disco local (simples mas não escalável)

            except httpx.TimeoutException:
                logger.warning("Timeout ao baixar sprite: %s", sprite_key)
                resultados[sprite_key] = {"status": "error", "reason": "timeout"}

            except httpx.HTTPError as exc:
                logger.warning("Erro HTTP ao baixar sprite %s: %s", sprite_key, exc)
                resultados[sprite_key] = {"status": "error", "reason": str(exc)}

        resultado_final = {
            "pokemon_id":        pokemon_id,
            "sprites_processed": resultados,
        }

        logger.info("Tarefa concluída para Pokémon id=%s", pokemon_id)
        return resultado_final

    except Exception as exc:
        # Se falhar por razão inesperada, tenta novamente após delay
        logger.error("Falha na tarefa (tentativa %d): %s", self.request.retries, exc, exc_info=True)
        # countdown: aumenta o tempo de espera a cada retry (exponencial simples)
        raise self.retry(exc=exc, countdown=15 * (self.request.retries + 1))
