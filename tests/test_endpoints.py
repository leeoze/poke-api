# =============================================================================
# tests/test_endpoints.py — Testes de integração dos endpoints da API
#
# O que testamos aqui?
#   • Estrutura (schema) das respostas — garantindo que os campos corretos
#     existem e têm os tipos corretos
#   • Lógica de paginação — next/previous/total calculados corretamente
#   • Cenários de erro — 404, 409, 422 com mensagens adequadas
#   • CRUD completo — criar, ler, atualizar, deletar
#
# Boas práticas de testes aplicadas:
#   • Cada teste é independente (banco zerado entre testes pelo conftest)
#   • Nomes descritivos: test_<oque_testa>_<cenario>_<resultado_esperado>
#   • Um assert principal por teste (facilita identificar a falha)
#   • Fixtures reutilizáveis para dados comuns (sample_pokemon)
# =============================================================================

import pytest
from httpx import AsyncClient


# =============================================================================
# Função auxiliar para criar Pokémons nos testes
# =============================================================================

async def criar_pokemon(client: AsyncClient, name: str, **kwargs) -> dict:
    """
    Cria um Pokémon via API e retorna os dados da resposta.
    Usado para preparar dados antes de testar outros comportamentos.

    Args:
        client: Cliente HTTP de teste
        name:   Nome único do Pokémon
        **kwargs: Campos opcionais para sobrescrever os padrões
    """
    payload = {
        "name":    name,
        "height":  kwargs.get("height", 5),
        "weight":  kwargs.get("weight", 50),
        "types":   kwargs.get("types", ["normal"]),
        "sprites": kwargs.get("sprites", {"front_default": None, "back_default": None}),
    }
    response = await client.post("/pokemons/", json=payload)
    assert response.status_code == 201, f"Falha ao criar '{name}': {response.text}"
    return response.json()


# =============================================================================
# Testes de Schema — valida a estrutura do JSON retornado
# =============================================================================

@pytest.mark.asyncio
async def test_criar_pokemon_retorna_schema_correto(client: AsyncClient):
    """
    Verifica que o POST retorna todos os campos esperados com os tipos corretos.
    Este é o teste mais fundamental: garante que o "contrato" da API está correto.
    """
    payload = {
        "name":    "bulbasaur",
        "height":  7,
        "weight":  69,
        "types":   ["grass", "poison"],
        "sprites": {
            "front_default": "https://example.com/bulbasaur.png",
            "back_default":  "https://example.com/bulbasaur-back.png",
        },
    }

    response = await client.post("/pokemons/", json=payload)

    assert response.status_code == 201
    data = response.json()

    # Verifica presença e tipo de cada campo
    assert "id" in data and isinstance(data["id"], int)
    assert data["name"]   == "bulbasaur"
    assert data["height"] == 7
    assert data["weight"] == 69
    assert set(data["types"]) == {"grass", "poison"}
    assert "front_default" in data["sprites"]
    assert "back_default"  in data["sprites"]


@pytest.mark.asyncio
async def test_buscar_pokemon_por_id_retorna_schema_correto(
    client: AsyncClient, sample_pokemon: dict
):
    """Verifica que GET /pokemons/{id} retorna os dados corretos do Pokémon."""
    pokemon_id = sample_pokemon["id"]
    response   = await client.get(f"/pokemons/{pokemon_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"]   == pokemon_id
    assert data["name"] == "pikachu"
    assert isinstance(data["types"], list)
    assert "sprites" in data


@pytest.mark.asyncio
async def test_nome_normalizado_para_minusculo(client: AsyncClient):
    """Verifica que nomes com maiúsculas são normalizados para minúsculo."""
    response = await client.post("/pokemons/", json={
        "name":   "CHARMANDER",
        "height": 6, "weight": 85, "types": ["fire"], "sprites": {},
    })
    assert response.status_code == 201
    assert response.json()["name"] == "charmander"


# =============================================================================
# Testes de Paginação — valida a lógica de navegação entre páginas
# =============================================================================

@pytest.mark.asyncio
async def test_listagem_retorna_estrutura_de_paginacao(client: AsyncClient):
    """
    Verifica que GET /pokemons/ retorna a estrutura completa com
    campos 'data' (lista) e 'pagination' (metadados).
    """
    response = await client.get("/pokemons/")

    assert response.status_code == 200
    body = response.json()

    # Deve ter os dois campos principais
    assert "data"       in body
    assert "pagination" in body

    # Valores padrão de paginação
    pagination = body["pagination"]
    assert pagination["limit"]  == 20
    assert pagination["offset"] == 0
    assert isinstance(pagination["total"], int)


@pytest.mark.asyncio
async def test_paginacao_links_next_e_previous(client: AsyncClient):
    """
    Testa a lógica de next/previous em três cenários:
      • Primeira página → previous = null, next existe
      • Página do meio  → ambos existem
      • Última página   → next = null, previous existe
    """
    # Cria 5 Pokémons para ter dados suficientes
    nomes = ["rattata", "geodude", "snorlax", "mewtwo", "eevee"]
    for nome in nomes:
        await criar_pokemon(client, nome)

    # ── Primeira página (offset=0, limit=2) ───────────────────────────────
    r1 = await client.get("/pokemons/?limit=2&offset=0")
    p1 = r1.json()["pagination"]
    assert p1["next"]     == "/pokemons?limit=2&offset=2"
    assert p1["previous"] is None  # não há página anterior à primeira

    # ── Página do meio (offset=2, limit=2) ────────────────────────────────
    r2 = await client.get("/pokemons/?limit=2&offset=2")
    p2 = r2.json()["pagination"]
    assert p2["next"]     == "/pokemons?limit=2&offset=4"
    assert p2["previous"] == "/pokemons?limit=2&offset=0"

    # ── Última página (offset=4, limit=2 — só 1 resultado) ────────────────
    r3 = await client.get("/pokemons/?limit=2&offset=4")
    p3 = r3.json()["pagination"]
    assert p3["next"]     is None  # não há próxima página
    assert p3["previous"] == "/pokemons?limit=2&offset=2"


@pytest.mark.asyncio
async def test_paginacao_total_corresponde_ao_banco(client: AsyncClient):
    """
    Verifica que o campo 'total' reflete exatamente quantos registros existem.
    """
    for nome in ["charmander", "squirtle", "jigglypuff"]:
        await criar_pokemon(client, nome)

    response   = await client.get("/pokemons/?limit=1&offset=0")
    pagination = response.json()["pagination"]

    assert pagination["total"]       == 3  # exatamente 3 criados
    assert len(response.json()["data"]) == 1  # página com 1 item (limit=1)


# =============================================================================
# Testes de Erro — valida retornos de status codes de falha
# =============================================================================

@pytest.mark.asyncio
async def test_buscar_pokemon_inexistente_retorna_404(client: AsyncClient):
    """
    O sistema deve retornar 404 com mensagem clara quando o ID não existe.
    """
    response = await client.get("/pokemons/999999")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "999999" in data["detail"]  # mensagem menciona o ID buscado


@pytest.mark.asyncio
async def test_atualizar_pokemon_inexistente_retorna_404(client: AsyncClient):
    """PUT em ID inexistente deve retornar 404."""
    response = await client.put("/pokemons/999999", json={"height": 10})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_deletar_pokemon_inexistente_retorna_404(client: AsyncClient):
    """DELETE em ID inexistente deve retornar 404."""
    response = await client.delete("/pokemons/999999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_criar_pokemon_duplicado_retorna_409(
    client: AsyncClient, sample_pokemon: dict
):
    """
    Tentar criar um Pokémon com nome já existente deve retornar 409 Conflict.
    O sample_pokemon já criou 'pikachu', então tentamos criar novamente.
    """
    payload = {
        "name": "pikachu",  # já existe
        "height": 4, "weight": 60, "types": ["electric"], "sprites": {},
    }
    response = await client.post("/pokemons/", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_criar_pokemon_com_altura_negativa_retorna_422(client: AsyncClient):
    """
    Dados inválidos (height negativo) devem ser rejeitados pelo Pydantic
    com status 422 Unprocessable Entity — antes mesmo de chegar ao banco.
    """
    response = await client.post("/pokemons/", json={
        "name":   "missingno",
        "height": -1,  # inválido: gt=0 no schema
        "weight": 10,
        "types":  ["???"],
        "sprites": {},
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_criar_pokemon_sem_nome_retorna_422(client: AsyncClient):
    """Campos obrigatórios ausentes devem retornar 422."""
    response = await client.post("/pokemons/", json={
        "height": 5, "weight": 50, "types": ["fire"],
        # "name" ausente
    })
    assert response.status_code == 422


# =============================================================================
# Testes de CRUD completo
# =============================================================================

@pytest.mark.asyncio
async def test_atualizar_peso_do_pokemon(client: AsyncClient, sample_pokemon: dict):
    """Atualização parcial deve modificar só o campo enviado."""
    pokemon_id = sample_pokemon["id"]
    response   = await client.put(f"/pokemons/{pokemon_id}", json={"weight": 999})

    assert response.status_code == 200
    assert response.json()["weight"] == 999
    # Os outros campos não devem ter mudado
    assert response.json()["name"] == "pikachu"


@pytest.mark.asyncio
async def test_deletar_pokemon_e_confirmar_remocao(
    client: AsyncClient, sample_pokemon: dict
):
    """
    Após deletar, o Pokémon não deve mais existir.
    Testa dois endpoints em sequência: DELETE e depois GET.
    """
    pokemon_id = sample_pokemon["id"]

    # 1. Deleta
    delete_response = await client.delete(f"/pokemons/{pokemon_id}")
    assert delete_response.status_code == 204  # sem body

    # 2. Confirma que foi removido
    get_response = await client.get(f"/pokemons/{pokemon_id}")
    assert get_response.status_code == 404


# =============================================================================
# Teste de Health Check
# =============================================================================

@pytest.mark.asyncio
async def test_health_check_retorna_ok(client: AsyncClient):
    """O endpoint /health deve retornar 200 com status 'ok'."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"]  == "ok"
    assert "version" in data
