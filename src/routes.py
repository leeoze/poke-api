# =============================================================================
# src/routes.py — Endpoints da API (rotas CRUD para Pokémons)
#
# O que é CRUD?
#   Create → POST   /pokemons/         Cria um Pokémon
#   Read   → GET    /pokemons/         Lista todos (com paginação)
#          → GET    /pokemons/{id}     Busca um pelo ID
#   Update → PUT    /pokemons/{id}     Atualiza um Pokémon
#   Delete → DELETE /pokemons/{id}     Remove um Pokémon
#
# Estratégia de cache:
#   • Leituras (GET): verifica Redis primeiro → PostgreSQL se não tiver
#   • Escritas (POST/PUT/DELETE): invalida o cache relacionado
#
# Estratégia de eventos:
#   • POST e PUT: publica evento no Kafka → Celery Worker processa em background
# =============================================================================

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache import (
    cache_delete,
    cache_delete_pattern,
    cache_get,
    cache_set,
    pokemon_cache_key,
    pokemon_list_cache_key,
)
from src.database import get_db
from src.kafka.producer import publish_pokemon_event
from src.models import Pokemon
from src.schemas import (
    PaginatedPokemonResponse,
    PaginationMeta,
    PokemonCreate,
    PokemonResponse,
    PokemonUpdate,
)

# APIRouter agrupa as rotas deste módulo com um prefixo comum
# prefix="/pokemons" → todas as rotas começam com /pokemons
# tags=["Pokémons"]  → agrupamento visual no Swagger UI (/docs)
router = APIRouter(prefix="/pokemons", tags=["Pokémons"])
logger = logging.getLogger(__name__)


# =============================================================================
# Funções auxiliares internas (prefixo _ indica uso privado)
# =============================================================================

def _build_pagination(total: int, limit: int, offset: int) -> PaginationMeta:
    """
    Calcula os links de navegação entre páginas.

    Lógica:
      next     → existe se ainda há mais itens depois desta página
      previous → existe se não estamos na primeira página (offset > 0)

    Exemplo com 50 Pokémons, limit=20, offset=20 (página 2):
      next     = "/pokemons?limit=20&offset=40"  (há mais 10 itens)
      previous = "/pokemons?limit=20&offset=0"   (há uma página anterior)
    """
    next_offset = offset + limit
    prev_offset = offset - limit

    return PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        # next existe apenas se o próximo offset não ultrapassar o total
        next=(
            f"/pokemons?limit={limit}&offset={next_offset}"
            if next_offset < total
            else None
        ),
        # previous existe apenas se o offset atual for maior que zero
        previous=(
            f"/pokemons?limit={limit}&offset={prev_offset}"
            if prev_offset >= 0 and offset > 0
            else None
        ),
    )


def _pokemon_to_dict(pokemon: Pokemon) -> dict:
    """
    Converte um objeto SQLAlchemy Pokemon em dicionário serializável.
    Usa o schema Pydantic para garantir formato correto antes de cachear.
    """
    return PokemonResponse.model_validate(pokemon).model_dump()


# =============================================================================
# GET /pokemons/ — Lista paginada de todos os Pokémons
# =============================================================================
@router.get(
    "/",
    response_model=PaginatedPokemonResponse,
    summary="Listar todos os Pokémons",
    description="Retorna lista paginada. Use `limit` e `offset` para navegar.",
)
async def list_pokemons(
    # Query parameters com valores padrão e validação automática
    limit:  int = Query(default=20, ge=1,  le=100, description="Itens por página (máx 100)"),
    offset: int = Query(default=0,  ge=0,          description="Itens a pular"),
    db:     AsyncSession = Depends(get_db),
):
    """
    Fluxo:
    1. Monta a chave de cache com limit e offset
    2. Se encontrar no Redis → retorna imediatamente (não consulta o banco)
    3. Se não → busca no PostgreSQL, salva no Redis, retorna
    """

    # ── 1. Tenta buscar do cache ───────────────────────────────────────────
    cache_key = pokemon_list_cache_key(limit, offset)
    cached = await cache_get(cache_key)
    if cached:
        # Retorna direto do Redis — sem tocar no PostgreSQL
        return cached

    # ── 2. Busca no PostgreSQL ─────────────────────────────────────────────
    # COUNT(*) → total de registros (para calcular paginação)
    total_result = await db.execute(select(func.count()).select_from(Pokemon))
    total: int = total_result.scalar_one()

    # SELECT com OFFSET e LIMIT → a "página" de resultados
    result = await db.execute(select(Pokemon).offset(offset).limit(limit))
    pokemons = result.scalars().all()

    # ── 3. Monta e cacheia a resposta ─────────────────────────────────────
    response = PaginatedPokemonResponse(
        data=[PokemonResponse.model_validate(p) for p in pokemons],
        pagination=_build_pagination(total, limit, offset),
    )

    await cache_set(cache_key, response.model_dump())
    return response


# =============================================================================
# GET /pokemons/{id} — Detalhe de um Pokémon específico
# =============================================================================
@router.get(
    "/{pokemon_id}",
    response_model=PokemonResponse,
    summary="Buscar Pokémon por ID",
)
async def get_pokemon(
    pokemon_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Busca um Pokémon pelo ID numérico.
    Retorna 404 se não existir.
    """

    # ── Tenta buscar do cache ─────────────────────────────────────────────
    cache_key = pokemon_cache_key(pokemon_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # ── Busca no banco ────────────────────────────────────────────────────
    result = await db.execute(select(Pokemon).where(Pokemon.id == pokemon_id))
    pokemon: Optional[Pokemon] = result.scalar_one_or_none()

    # 404 — Pokémon não encontrado
    if not pokemon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pokémon com id={pokemon_id} não encontrado.",
        )

    # Cacheia e retorna
    data = _pokemon_to_dict(pokemon)
    await cache_set(cache_key, data)
    return data


# =============================================================================
# POST /pokemons/ — Criar novo Pokémon
# =============================================================================
@router.post(
    "/",
    response_model=PokemonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar Pokémon",
)
async def create_pokemon(
    payload: PokemonCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria um novo Pokémon.

    Regras:
      • Nome deve ser único (retorna 409 se já existir)
      • Após criar, invalida todo o cache de listas
      • Publica evento no Kafka para processamento assíncrono dos sprites
    """

    # ── Verifica duplicidade de nome ──────────────────────────────────────
    existing = await db.execute(
        select(Pokemon).where(Pokemon.name == payload.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pokémon com nome '{payload.name}' já existe.",
        )

    # ── Cria o registro no banco ──────────────────────────────────────────
    # model_dump() converte o schema Pydantic em dicionário
    # **payload.model_dump() desempacota como argumentos nomeados
    pokemon = Pokemon(**payload.model_dump())
    db.add(pokemon)

    # flush() envia o INSERT ao banco sem commitar —
    # isso preenche o pokemon.id gerado pelo banco
    await db.flush()
    await db.refresh(pokemon)  # atualiza o objeto com os valores do banco

    # ── Invalida cache de listas ─────────────────────────────────────────
    # Qualquer lista em cache está desatualizada agora
    await cache_delete_pattern("pokemon:list:*")

    # ── Publica evento no Kafka ───────────────────────────────────────────
    # O Celery Worker vai baixar e processar os sprites em background
    await publish_pokemon_event("pokemon.created", _pokemon_to_dict(pokemon))

    logger.info("Pokémon criado: id=%s nome=%s", pokemon.id, pokemon.name)
    return pokemon


# =============================================================================
# PUT /pokemons/{id} — Atualizar Pokémon existente
# =============================================================================
@router.put(
    "/{pokemon_id}",
    response_model=PokemonResponse,
    summary="Atualizar Pokémon",
)
async def update_pokemon(
    pokemon_id: int,
    payload:    PokemonUpdate,
    db:         AsyncSession = Depends(get_db),
):
    """
    Atualização parcial — envie apenas os campos que deseja alterar.
    Retorna 404 se o Pokémon não existir.
    """

    # ── Busca o Pokémon existente ─────────────────────────────────────────
    result = await db.execute(select(Pokemon).where(Pokemon.id == pokemon_id))
    pokemon: Optional[Pokemon] = result.scalar_one_or_none()

    if not pokemon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pokémon com id={pokemon_id} não encontrado.",
        )

    # ── Aplica apenas os campos enviados ─────────────────────────────────
    # exclude_unset=True → ignora campos não enviados na requisição
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        # sprites é um objeto SpriteSchema — precisa ser convertido para dict
        if field == "sprites" and value is not None:
            value = value if isinstance(value, dict) else value.model_dump()
        setattr(pokemon, field, value)

    await db.flush()
    await db.refresh(pokemon)

    # ── Invalida cache deste Pokémon e todas as listas ────────────────────
    await cache_delete(pokemon_cache_key(pokemon_id))
    await cache_delete_pattern("pokemon:list:*")

    # ── Publica evento no Kafka ───────────────────────────────────────────
    await publish_pokemon_event("pokemon.updated", _pokemon_to_dict(pokemon))

    logger.info("Pokémon atualizado: id=%s", pokemon_id)
    return pokemon


# =============================================================================
# DELETE /pokemons/{id} — Remover Pokémon
# =============================================================================
@router.delete(
    "/{pokemon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deletar Pokémon",
)
async def delete_pokemon(
    pokemon_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Remove o Pokémon do banco de dados.
    Retorna 204 No Content em caso de sucesso (sem body de resposta).
    Retorna 404 se não existir.
    """

    # ── Busca o Pokémon ───────────────────────────────────────────────────
    result = await db.execute(select(Pokemon).where(Pokemon.id == pokemon_id))
    pokemon: Optional[Pokemon] = result.scalar_one_or_none()

    if not pokemon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pokémon com id={pokemon_id} não encontrado.",
        )

    # ── Remove do banco ───────────────────────────────────────────────────
    await db.delete(pokemon)

    # ── Invalida o cache ─────────────────────────────────────────────────
    await cache_delete(pokemon_cache_key(pokemon_id))
    await cache_delete_pattern("pokemon:list:*")

    logger.info("Pokémon deletado: id=%s", pokemon_id)
    # Retorno implícito None → FastAPI envia 204 No Content
