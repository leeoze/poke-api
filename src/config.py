# =============================================================================
# src/config.py — Configurações centrais da aplicação
#
# O que faz este arquivo?
#   Define TODAS as variáveis de configuração da aplicação em um único lugar.
#   Usa a biblioteca pydantic-settings para ler valores do arquivo .env
#   automaticamente, com tipos e valores padrão definidos.
#
# Por que centralizar configurações?
#   • Evita "números mágicos" espalhados pelo código
#   • Facilita trocar ambiente (dev → prod) apenas mudando o .env
#   • Se uma variável obrigatória estiver faltando, a aplicação falha
#     na inicialização com mensagem clara — não no meio da execução
# =============================================================================

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Classe que representa todas as configurações da aplicação.

    O pydantic-settings lê automaticamente as variáveis do arquivo .env
    e faz a conversão de tipos (ex: "true" → True, "5432" → 5432).
    """

    # Instrui o pydantic a ler o arquivo .env na raiz do projeto
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignora variáveis do .env que não estão declaradas aqui
    )

    # ── Identificação da aplicação ─────────────────────────────────────────
    APP_NAME: str    = "PokéAPI"
    APP_VERSION: str = "2.0.0"
    # DEBUG=true ativa logs detalhados e SQL queries no console
    DEBUG: bool      = False

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    # asyncpg = driver assíncrono (usado pela API FastAPI)
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/pokedb"
    )
    # psycopg2 = driver síncrono (usado pelo Alembic para migrações)
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/pokedb"
    )

    # ── Redis ──────────────────────────────────────────────────────────────
    # Banco 0 → cache da API
    REDIS_URL: str  = "redis://localhost:6379/0"
    # Quanto tempo (em segundos) um dado fica em cache antes de expirar
    # 300 segundos = 5 minutos
    CACHE_TTL: int  = 300

    # ── Celery (fila de tarefas em background) ─────────────────────────────
    # Banco 1 → fila de mensagens do Celery (broker)
    CELERY_BROKER_URL: str      = "redis://localhost:6379/1"
    # Banco 2 → armazena o resultado das tarefas executadas
    CELERY_RESULT_BACKEND: str  = "redis://localhost:6379/2"

    # ── Apache Kafka (mensageria orientada a eventos) ──────────────────────
    # Endereço do servidor Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    # Nome do tópico onde os eventos de Pokémon são publicados
    KAFKA_TOPIC_POKEMON: str     = "pokemon-events"
    # Identificador do grupo de consumidores Kafka
    KAFKA_CONSUMER_GROUP: str    = "poke-api-group"

    # ── ELK Stack — Logstash ───────────────────────────────────────────────
    # Host e porta para onde os logs JSON são enviados
    LOGSTASH_HOST: str = "localhost"
    LOGSTASH_PORT: int = 5044


# Instância única (singleton) usada em todo o projeto
# Importar assim: from src.config import settings
settings = Settings()
