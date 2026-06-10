# =============================================================================
# src/models.py — Definição da tabela Pokémon no banco de dados
#
# O que é um Model?
#   Um Model é uma classe Python que representa uma tabela no banco.
#   Cada atributo da classe = uma coluna da tabela.
#   O SQLAlchemy traduz operações Python em queries SQL automaticamente.
#
# Tipos de colunas usados:
#   Integer → número inteiro
#   String  → texto com tamanho máximo
#   JSON    → dados estruturados (listas, dicionários) — suportado pelo PostgreSQL
# =============================================================================

from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class Pokemon(Base):
    """
    Representa a tabela 'pokemons' no banco de dados PostgreSQL.

    Exemplo de linha na tabela:
      id=25, name='pikachu', height=4, weight=60,
      types=['electric'], sprites={front_default: '...', back_default: '...'}
    """

    # Nome da tabela no banco de dados
    __tablename__ = "pokemons"

    # ── Colunas da tabela ──────────────────────────────────────────────────

    # Chave primária — identificador único, auto incrementado pelo banco
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,  # cria índice = buscas por id ficam muito mais rápidas
    )

    # Nome do Pokémon — obrigatório, único e indexado para busca rápida
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,  # não permite dois Pokémons com o mesmo nome
        index=True,   # índice para buscas por nome
        nullable=False,
    )

    # Altura em decímetros (conforme PokéAPI original)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    # Peso em hectogramas (conforme PokéAPI original)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)

    # Lista de tipos ex: ["electric"] ou ["grass", "poison"]
    # JSON é armazenado como texto no PostgreSQL e convertido automaticamente
    types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Dicionário com URLs das imagens do sprite
    # ex: {"front_default": "http://...", "back_default": "http://..."}
    sprites: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:
        """Representação textual — aparece em logs e no console Python."""
        return f"<Pokemon id={self.id} name={self.name}>"
