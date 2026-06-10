# =============================================================================
# src/schemas.py — Contratos de dados da API (validação e serialização)
#
# O que são Schemas (Pydantic)?
#   São classes que definem o "formato esperado" dos dados.
#   O FastAPI usa schemas para:
#     • Validar o JSON recebido nas requisições (body, query params)
#     • Definir o formato do JSON retornado nas respostas
#     • Gerar a documentação automática do Swagger UI (/docs)
#
# Diferença entre Model (SQLAlchemy) e Schema (Pydantic):
#   Model   → representa a TABELA no banco de dados
#   Schema  → representa o JSON que entra e sai da API
#   Eles são convertidos entre si nas rotas com model_validate()
#
# Schemas deste arquivo:
#   SpriteSchema           → formato das imagens do Pokémon
#   PokemonBase            → campos comuns (base para criar e responder)
#   PokemonCreate          → dados necessários para CRIAR um Pokémon (POST)
#   PokemonUpdate          → dados para ATUALIZAR (PUT) — todos opcionais
#   PokemonResponse        → formato de resposta (inclui o ID do banco)
#   PaginationMeta         → metadados de paginação
#   PaginatedPokemonResponse → resposta completa da listagem
# =============================================================================

from typing import Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Schema das imagens (sprites)
# =============================================================================
class SpriteSchema(BaseModel):
    """
    Representa as URLs das imagens do Pokémon.

    front_default → imagem da frente do Pokémon
    back_default  → imagem da costas do Pokémon
    """
    front_default: Optional[str] = None
    back_default:  Optional[str] = None


# =============================================================================
# Base compartilhada entre criação e resposta
# =============================================================================
class PokemonBase(BaseModel):
    """
    Campos comuns a todos os schemas de Pokémon.
    Outras classes herdam daqui para evitar repetição de código.
    """

    # Field(...) significa campo obrigatório (... = required em Pydantic)
    name:    str         = Field(..., min_length=1, max_length=100, description="Nome do Pokémon")
    height:  int         = Field(..., gt=0, description="Altura em decímetros")
    weight:  int         = Field(..., gt=0, description="Peso em hectogramas")
    types:   list[str]   = Field(..., min_length=1, description="Lista de tipos ex: ['electric']")
    sprites: SpriteSchema = Field(default_factory=SpriteSchema, description="URLs das imagens")

    # ── Validadores — executados automaticamente pelo Pydantic ────────────

    @field_validator("types")
    @classmethod
    def validar_types(cls, v: list[str]) -> list[str]:
        """
        Garante que a lista de tipos não está vazia e normaliza para minúsculas.
        ex: ["Electric", " FIRE "] → ["electric", "fire"]
        """
        if not v:
            raise ValueError("types deve conter pelo menos um elemento")
        return [t.lower().strip() for t in v]

    @field_validator("name")
    @classmethod
    def validar_name(cls, v: str) -> str:
        """
        Normaliza o nome para minúsculas e remove espaços extras.
        ex: "  Pikachu  " → "pikachu"
        """
        return v.lower().strip()


# =============================================================================
# Schema para criação (POST /pokemons)
# =============================================================================
class PokemonCreate(PokemonBase):
    """
    Dados necessários para criar um novo Pokémon.
    Herda todos os campos de PokemonBase sem modificações.

    Exemplo de body da requisição:
    {
        "name": "pikachu",
        "height": 4,
        "weight": 60,
        "types": ["electric"],
        "sprites": {"front_default": "http://..."}
    }
    """
    pass  # sem campos extras — herda tudo de PokemonBase


# =============================================================================
# Schema para atualização parcial (PUT /pokemons/{id})
# =============================================================================
class PokemonUpdate(BaseModel):
    """
    Dados para atualização parcial de um Pokémon.
    Todos os campos são opcionais — você pode atualizar apenas o peso,
    por exemplo, sem precisar reenviar todos os outros campos.

    Exemplo de body (atualiza só o peso):
    { "weight": 65 }
    """
    name:    Optional[str]         = Field(None, min_length=1, max_length=100)
    height:  Optional[int]         = Field(None, gt=0)
    weight:  Optional[int]         = Field(None, gt=0)
    types:   Optional[list[str]]   = None
    sprites: Optional[SpriteSchema] = None


# =============================================================================
# Schema de resposta (GET /pokemons e GET /pokemons/{id})
# =============================================================================
class PokemonResponse(PokemonBase):
    """
    Formato do JSON retornado pela API ao consultar um Pokémon.
    Inclui o id (gerado pelo banco) além dos campos da base.

    Exemplo de resposta:
    {
        "id": 25,
        "name": "pikachu",
        "height": 4,
        "weight": 60,
        "types": ["electric"],
        "sprites": {"front_default": "http://...", "back_default": "http://..."}
    }
    """
    id: int  # gerado automaticamente pelo banco — não enviado na criação

    # from_attributes=True permite criar o schema a partir de um objeto
    # SQLAlchemy (Model), não apenas de dicionários
    model_config = {"from_attributes": True}


# =============================================================================
# Schema de metadados de paginação
# =============================================================================
class PaginationMeta(BaseModel):
    """
    Informações sobre a página atual dos resultados.

    total    → quantos registros existem no total no banco
    limit    → quantos foram solicitados por página
    offset   → quantos foram pulados (posição de início)
    next     → link para a próxima página (None se for a última)
    previous → link para a página anterior (None se for a primeira)
    """
    total:    int
    limit:    int
    offset:   int
    next:     Optional[str]
    previous: Optional[str]


# =============================================================================
# Schema de resposta paginada (GET /pokemons)
# =============================================================================
class PaginatedPokemonResponse(BaseModel):
    """
    Resposta completa do endpoint de listagem.

    Exemplo:
    {
        "data": [{ "id": 25, "name": "pikachu", ... }],
        "pagination": {
            "total": 151,
            "limit": 20,
            "offset": 0,
            "next": "/pokemons?limit=20&offset=20",
            "previous": null
        }
    }
    """
    data:       list[PokemonResponse]
    pagination: PaginationMeta
