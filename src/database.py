# =============================================================================
# src/database.py — Conexão com o banco de dados PostgreSQL (assíncrona)
#
# O que é SQLAlchemy?
#   Um ORM (Object-Relational Mapper) — biblioteca que permite trabalhar
#   com bancos de dados usando classes Python, sem escrever SQL puro.
#
# O que é "assíncrono" aqui?
#   Operações de banco normalmente bloqueiam o servidor enquanto esperam
#   a resposta. O modo async permite que o servidor continue atendendo
#   outras requisições enquanto espera o banco — aumenta muito a performance.
#
# Componentes principais:
#   engine        → a "conexão mestre" com o banco, com pool de conexões
#   AsyncSession  → uma "sessão" de trabalho — onde você lê e escreve dados
#   Base          → classe base que todos os Models herdam
# =============================================================================

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


# =============================================================================
# ENGINE — a conexão com o banco de dados
# =============================================================================
engine = create_async_engine(
    settings.DATABASE_URL,

    # echo=True imprime todas as queries SQL no console — útil para debug
    echo=settings.DEBUG,

    # pool_pre_ping=True testa a conexão antes de usar (evita erro se o banco
    # reiniciou e a conexão "velha" ainda está no pool)
    pool_pre_ping=True,

    # Quantas conexões simultâneas manter abertas no pool
    pool_size=10,

    # Quantas conexões extras criar se o pool estiver cheio
    max_overflow=20,
)


# =============================================================================
# SESSION FACTORY — fábrica que cria sessões de banco de dados
# =============================================================================
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # expire_on_commit=False evita que os objetos fiquem "expirados"
    # após um commit, permitindo continuar usando-os sem nova consulta
    expire_on_commit=False,
)


# =============================================================================
# BASE — classe pai de todos os models (tabelas)
# =============================================================================
class Base(DeclarativeBase):
    """
    Todos os models (Pokemon, etc.) herdam desta classe.
    O SQLAlchemy usa ela para descobrir quais tabelas criar no banco.
    """
    pass


# =============================================================================
# DEPENDENCY INJECTION — fornece sessão para os endpoints
# =============================================================================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Função geradora assíncrona usada pelo FastAPI via Depends().

    Como funciona:
      1. Abre uma sessão de banco de dados
      2. Entrega a sessão para o endpoint via 'yield'
      3. Após o endpoint terminar, faz commit ou rollback automaticamente
      4. Fecha a sessão

    Uso no endpoint:
      async def meu_endpoint(db: AsyncSession = Depends(get_db)):
          ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session          # entrega a sessão para o endpoint
            await session.commit() # se tudo correu bem, salva as mudanças
        except Exception:
            await session.rollback()  # se deu erro, desfaz tudo
            raise                     # repassa o erro para o FastAPI tratar
        finally:
            await session.close()  # sempre fecha a sessão ao final


# =============================================================================
# CRIAÇÃO DAS TABELAS — executado na inicialização da aplicação
# =============================================================================
async def create_tables() -> None:
    """
    Cria todas as tabelas no banco de dados se ainda não existirem.

    ATENÇÃO: Em produção, prefira usar Alembic para migrações controladas.
    Este método é conveniente para desenvolvimento e testes.
    """
    async with engine.begin() as conn:
        # Importa os models para que o SQLAlchemy os conheça
        from src import models  # noqa: F401
        # Cria as tabelas baseando-se nos models importados
        await conn.run_sync(Base.metadata.create_all)
