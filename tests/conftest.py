# =============================================================================
# tests/conftest.py — Configuração e fixtures compartilhadas dos testes
#
# O que é o conftest.py?
#   É um arquivo especial do pytest que define "fixtures" — funções que
#   preparam o ambiente antes dos testes e limpam depois.
#   Qualquer fixture definida aqui está disponível em TODOS os arquivos de teste.
#
# O que são fixtures?
#   São funções que fornecem dados ou objetos reutilizáveis para os testes.
#   Exemplo: em vez de criar um Pokémon manualmente em cada teste,
#   a fixture `sample_pokemon` faz isso uma vez e disponibiliza o resultado.
#
# Estratégia de banco de dados nos testes:
#   Usamos SQLite em memória (":memory:") em vez do PostgreSQL.
#   Vantagens:
#     • Não precisa de servidor de banco rodando
#     • Cada teste começa com banco limpo
#     • Testes rodam muito mais rápido
#   Como: substituímos a dependência `get_db` do FastAPI pela versão de teste
#
# Estratégia de cache nos testes:
#   O cache Redis é desabilitado via mock — funções de cache retornam
#   None (miss) e set/delete não fazem nada, evitando dependência do Redis.
# =============================================================================

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import Base, get_db
from src.main import app

# =============================================================================
# Banco de dados de teste — SQLite em memória
# =============================================================================

# URL especial: "sqlite+aiosqlite:///:memory:" cria um banco SQLite temporário
# na RAM que é destruído quando o processo encerra
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Engine de teste — separado do engine de produção
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,  # não imprime SQLs durante os testes (menos ruído)
    # check_same_thread=False é necessário para SQLite com async
    connect_args={"check_same_thread": False},
)

# Fábrica de sessões para os testes
TestAsyncSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# =============================================================================
# Fixtures de infraestrutura
# =============================================================================

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """
    Cria e destrói as tabelas antes/depois de CADA teste.
    autouse=True → aplicado automaticamente em todos os testes sem precisar declarar.

    Isso garante isolamento: cada teste começa com banco vazio.
    """
    async with test_engine.begin() as conn:
        # Cria todas as tabelas definidas nos models
        await conn.run_sync(Base.metadata.create_all)
    yield  # aqui o teste executa
    async with test_engine.begin() as conn:
        # Remove todas as tabelas após o teste
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Fornece uma sessão de banco de dados de teste.
    Usada internamente pela fixture `client`.
    """
    async with TestAsyncSession() as session:
        yield session


# =============================================================================
# Fixture principal: cliente HTTP de teste
# =============================================================================

@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Fornece um cliente HTTP assíncrono configurado para testar a API.

    O que faz:
      1. Substitui a dependência de banco (get_db) pela versão de teste
      2. Mocka as funções de cache (evita precisar do Redis)
      3. Mocka o Kafka (evita precisar do Kafka)
      4. Cria um AsyncClient que faz requisições diretas à app (sem HTTP real)

    Como usar nos testes:
      async def test_algo(client: AsyncClient):
          response = await client.get("/pokemons/")
          assert response.status_code == 200
    """

    # ── Substitui o banco de produção pelo de teste ───────────────────────
    async def override_get_db():
        """Versão de teste do get_db — usa SQLite em vez de PostgreSQL."""
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    # ── Desabilita cache (evita dependência do Redis nos testes) ──────────
    # patch substitui temporariamente as funções reais por mocks (fakes)
    with (
        patch("src.routes.cache_get",            new_callable=AsyncMock, return_value=None),
        patch("src.routes.cache_set",            new_callable=AsyncMock),
        patch("src.routes.cache_delete",         new_callable=AsyncMock),
        patch("src.routes.cache_delete_pattern", new_callable=AsyncMock),
        # Desabilita Kafka (evita tentativa de conexão)
        patch("src.routes.publish_pokemon_event", new_callable=AsyncMock),
    ):
        # ASGITransport permite fazer requisições HTTP sem precisar de servidor
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac

    # Limpa os overrides após o teste para não vazar entre testes
    app.dependency_overrides.clear()


# =============================================================================
# Fixtures de dados reutilizáveis
# =============================================================================

@pytest_asyncio.fixture
async def sample_pokemon(client: AsyncClient) -> dict:
    """
    Cria um Pokémon de exemplo (Pikachu) e retorna os dados da resposta.
    Usado como ponto de partida para testes de GET, PUT e DELETE.

    Qualquer teste que declare `sample_pokemon` como parâmetro recebe
    automaticamente um Pikachu já criado no banco de teste.
    """
    payload = {
        "name":    "pikachu",
        "height":  4,
        "weight":  60,
        "types":   ["electric"],
        "sprites": {
            "front_default": "https://sprites.example.com/25.png",
            "back_default":  "https://sprites.example.com/back/25.png",
        },
    }
    response = await client.post("/pokemons/", json=payload)
    assert response.status_code == 201, f"Falha ao criar fixture: {response.text}"
    return response.json()
