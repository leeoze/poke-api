# =============================================================================
# src/kafka/producer.py — Publicador de eventos no Apache Kafka
#
# O que é o Kafka?
#   O Apache Kafka é um sistema de mensageria (message broker) distribuído.
#   Funciona como uma "fila de eventos" entre serviços.
#
# Por que usar Kafka aqui?
#   Quando um Pokémon é criado ou atualizado, precisamos executar
#   tarefas pesadas (ex: download de sprites) SEM travar a resposta HTTP.
#   O fluxo é:
#
#   API (rápida)          Kafka          Celery Worker (lento, background)
#   POST /pokemons   →   evento       →   baixa imagens, comprime, cacheia
#        ↓
#   Responde 201 imediatamente (sem esperar o download)
#
# O Kafka garante que:
#   • A mensagem não se perde mesmo se o Worker estiver offline
#   • Múltiplos Workers podem processar em paralelo
#   • É possível "replay" de eventos históricos
#
# Tópico usado:
#   "pokemon-events" → recebe eventos "pokemon.created" e "pokemon.updated"
# =============================================================================

import json
import logging
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)


async def publish_pokemon_event(event_type: str, data: dict[str, Any]) -> None:
    """
    Publica um evento estruturado no tópico Kafka configurado.

    O evento tem o formato:
    {
        "event": "pokemon.created",   ← tipo do evento
        "data": {                      ← payload com os dados do Pokémon
            "id": 25,
            "name": "pikachu",
            ...
        }
    }

    Tratamento de falhas:
        Se o Kafka não estiver disponível (ex: durante testes ou inicialização),
        a função registra um aviso nos logs mas NÃO lança exceção.
        Isso garante que a API responda normalmente mesmo sem Kafka.

    Args:
        event_type: Identificador do evento ("pokemon.created", "pokemon.updated")
        data:       Dicionário com os dados do Pokémon serializado
    """
    try:
        # Importação local para evitar erro de import se aiokafka não estiver
        # instalado ou se Kafka não estiver configurado no ambiente de testes
        from aiokafka import AIOKafkaProducer

        # Serializa o evento para bytes JSON — o Kafka só aceita bytes
        payload = json.dumps(
            {"event": event_type, "data": data},
            ensure_ascii=False,  # preserva caracteres UTF-8 (acentos, etc.)
        ).encode("utf-8")

        # Criamos o producer, enviamos e fechamos — stateless para simplicidade
        # Em produção de alto volume, mantenha o producer aberto como singleton
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            # Aguarda confirmação de pelo menos 1 broker (segurança mínima)
            acks="all",
        )

        await producer.start()
        try:
            await producer.send_and_wait(settings.KAFKA_TOPIC_POKEMON, payload)
            logger.info(
                "Evento Kafka publicado: event=%s pokemon_id=%s",
                event_type,
                data.get("id"),
            )
        finally:
            # SEMPRE fecha o producer para liberar a conexão
            await producer.stop()

    except Exception as exc:
        # Falha no Kafka é não-crítica: logamos e continuamos
        # A API não pode ficar presa por causa de uma fila de mensagens
        logger.warning(
            "Falha ao publicar evento Kafka (event=%s): %s", event_type, exc
        )
