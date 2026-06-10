# =============================================================================
# src/cache.py — Camada de cache com Redis
#
# O que é cache?
#   Cache é uma memória temporária e ultra-rápida.
#   Em vez de buscar dados no banco PostgreSQL a cada requisição
#   (operação lenta — envolve disco e rede), guardamos a resposta
#   no Redis (memória RAM) por um tempo determinado (TTL).
#
# Como funciona o fluxo:
#   1. Requisição chega → verifica se existe no Redis (cache_get)
#   2a. Se SIM (Cache HIT) → retorna instantaneamente do Redis ✅
#   2b. Se NÃO (Cache MISS) → busca no PostgreSQL, salva no Redis (cache_set)
#   3. Quando um Pokémon é modificado/deletado → invalida o cache (cache_delete)
#
# Por que usar Redis?
#   • PostgreSQL: ~5-20ms por query
#   • Redis: <1ms por operação
#   Isso multiplica a capacidade de atendimento da API por 10x ou mais.
#
# Chaves de cache usadas neste projeto:
#   "pokemon:{id}"          → dados de um Pokémon específico
#   "pokemon:list:{l}:{o}"  → lista paginada com limit e offset
# =============================================================================

import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from src.config import settings

# Logger para registrar hits, misses e erros de cache
logger = logging.getLogger(__name__)

# Variável global que armazena a conexão Redis
# É criada uma única vez (singleton) para evitar reconexões desnecessárias
_redis_client: Optional[aioredis.Redis] = None


# =============================================================================
# Conexão com Redis
# =============================================================================
async def get_redis() -> aioredis.Redis:
    """
    Retorna a conexão Redis, criando uma nova se ainda não existir.
    Padrão Singleton: apenas uma conexão é mantida durante toda a execução.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,  # retorna strings, não bytes
        )
    return _redis_client


# =============================================================================
# Operações de Cache
# =============================================================================
async def cache_get(key: str) -> Optional[Any]:
    """
    Busca um valor no cache pelo nome da chave.

    Retorna o valor deserializado (dict, list, etc.) ou None se não encontrado.
    Erros de conexão com Redis são tratados aqui — a API continua funcionando
    mesmo se o Redis estiver fora do ar (degrada graciosamente).
    """
    try:
        client = await get_redis()
        raw = await client.get(key)

        if raw:
            logger.debug("Cache HIT: %s", key)
            return json.loads(raw)  # converte JSON string → Python dict/list

        logger.debug("Cache MISS: %s", key)
        return None

    except Exception as exc:
        # Cache indisponível não deve derrubar a API — apenas logamos e seguimos
        logger.warning("Erro ao ler cache (chave=%s): %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = settings.CACHE_TTL) -> None:
    """
    Salva um valor no cache com tempo de expiração (TTL).

    Args:
        key:   Identificador único no Redis (ex: "pokemon:25")
        value: Dado a ser armazenado (será convertido para JSON)
        ttl:   Segundos até expirar (padrão: 300s = 5 minutos)
    """
    try:
        client = await get_redis()
        # setex = SET com EXpiration (define e já configura o TTL)
        await client.setex(key, ttl, json.dumps(value))
        logger.debug("Cache SET: %s (ttl=%ss)", key, ttl)

    except Exception as exc:
        logger.warning("Erro ao gravar cache (chave=%s): %s", key, exc)


async def cache_delete(*keys: str) -> None:
    """
    Remove uma ou mais chaves do cache (invalidação pontual).
    Usado quando um Pokémon específico é atualizado ou deletado.

    Exemplo: cache_delete("pokemon:25")
    """
    if not keys:
        return
    try:
        client = await get_redis()
        await client.delete(*keys)
        logger.debug("Cache DELETE: %s", keys)

    except Exception as exc:
        logger.warning("Erro ao deletar cache: %s", exc)


async def cache_delete_pattern(pattern: str) -> None:
    """
    Remove TODAS as chaves que correspondem a um padrão (invalidação em lote).
    Usado quando qualquer Pokémon é criado/atualizado/deletado, pois todas
    as listas em cache precisam ser invalidadas.

    Exemplo: cache_delete_pattern("pokemon:list:*")
             Remove "pokemon:list:20:0", "pokemon:list:10:40", etc.

    ATENÇÃO: Em produção com muitas chaves, prefira SCAN ao invés de KEYS.
    Para este projeto o volume é pequeno, então KEYS é adequado.
    """
    try:
        client = await get_redis()
        keys = await client.keys(pattern)
        if keys:
            await client.delete(*keys)
            logger.debug(
                "Cache DELETE pattern '%s': %d chaves removidas", pattern, len(keys)
            )

    except Exception as exc:
        logger.warning("Erro ao deletar cache por padrão: %s", exc)


# =============================================================================
# Funções auxiliares para nomes de chaves consistentes
# =============================================================================
def pokemon_cache_key(pokemon_id: int) -> str:
    """
    Gera a chave de cache para um Pokémon individual.
    Exemplo: pokemon_cache_key(25) → "pokemon:25"
    """
    return f"pokemon:{pokemon_id}"


def pokemon_list_cache_key(limit: int, offset: int) -> str:
    """
    Gera a chave de cache para uma página da listagem.
    Exemplo: pokemon_list_cache_key(20, 40) → "pokemon:list:20:40"
    """
    return f"pokemon:list:{limit}:{offset}"
