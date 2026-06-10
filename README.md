# 🎮 PokéAPI — FastAPI Production-Ready

> API RESTful assíncrona estilo PokéAPI — construída com as melhores práticas de engenharia backend.

[![CI/CD](https://github.com/seu-usuario/poke-api/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/seu-usuario/poke-api/actions)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![Poetry](https://img.shields.io/badge/Poetry-1.8-orange)](https://python-poetry.org)

---

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Stack Tecnológica](#stack-tecnológica)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Instalação e Execução](#instalação-e-execução)
- [Testes](#testes)
- [Endpoints da API](#endpoints-da-api)
- [Monitoramento ELK](#monitoramento-elk)
- [Kubernetes](#kubernetes)
- [CI/CD](#cicd)

---

## 🎯 Visão Geral

API de gerenciamento de Pokémons construída para demonstrar arquitetura backend moderna:

- **Assíncrona de ponta a ponta** — FastAPI + SQLAlchemy async + asyncpg
- **Cache em memória** — Redis reduz latência de consultas repetidas em ~95%
- **Processamento em background** — Celery processa tarefas pesadas sem bloquear a API
- **Mensageria de eventos** — Kafka desacopla a API do processamento assíncrono
- **Observabilidade completa** — Logs JSON estruturados indexados na ELK Stack
- **Containerizada** — Docker Compose para desenvolvimento, Kubernetes para produção
- **CI/CD automatizado** — GitHub Actions testa e deploya automaticamente

---

## 🛠️ Stack Tecnológica

| Camada | Tecnologia | Por que foi escolhida |
|---|---|---|
| **Framework** | FastAPI 0.111 | ASGI assíncrono, tipagem com Pydantic v2, docs automáticas |
| **ORM** | SQLAlchemy 2 async | Queries sem bloquear o event loop |
| **Banco de dados** | PostgreSQL 16 | Robusto, suporte nativo a JSON, amplamente usado |
| **Cache** | Redis 7 | < 1ms de latência, TTL configurável, eviction automático |
| **Fila de tarefas** | Celery 5 | Workers distribuídos para processamento em background |
| **Mensageria** | Apache Kafka (KRaft) | Eventos duráveis, replay, escalonamento sem Zookeeper |
| **Logs** | ELK Stack 8.13 | Indexação, busca e dashboards em tempo real |
| **Containers** | Docker + Compose | Ambiente reproduzível |
| **Orquestração** | Kubernetes | Escalabilidade, auto-healing, rolling updates |
| **Dependências** | Poetry 1.8 | Lock file preciso, separação dev/prod, virtual envs |
| **CI/CD** | GitHub Actions | Testes + deploy automáticos |

---

## 📁 Estrutura do Projeto

```
poke-api/
│
├── .github/
│   └── workflows/
│       └── ci-cd.yml          # Pipeline: CI (testes) → CD (deploy Render)
│
├── k8s/
│   ├── deployment.yml         # Pods, réplicas, health checks, recursos
│   └── service.yml            # Service ClusterIP + HPA + Ingress
│
├── src/                       # Código-fonte da aplicação
│   ├── __init__.py
│   ├── main.py                # App FastAPI, middleware, lifecycle hooks
│   ├── config.py              # Configurações via .env (pydantic-settings)
│   ├── database.py            # Engine async, sessão, criação de tabelas
│   ├── models.py              # Model SQLAlchemy: tabela 'pokemons'
│   ├── schemas.py             # Schemas Pydantic v2: request/response
│   ├── routes.py              # CRUD completo com cache Redis integrado
│   ├── cache.py               # Helpers Redis: get/set/delete/eviction
│   ├── logging_config.py      # Logging JSON estruturado para ELK
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── celery_app.py      # Instância e configuração do Celery
│   │   └── tasks.py           # Task: processa eventos Kafka em background
│   │
│   └── kafka/
│       ├── __init__.py
│       └── producer.py        # Publica eventos no tópico Kafka
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Fixtures: SQLite in-memory + mocks de cache
│   └── test_endpoints.py      # 13 testes: schema, paginação, CRUD, erros
│
├── elk-config/
│   └── logstash.conf          # Pipeline: coleta → filtra → Elasticsearch
│
├── Dockerfile                 # Multi-stage build: builder + runtime
├── docker-compose.yml         # Stack completa: API + PG + Redis + Kafka + ELK
├── pyproject.toml             # Dependências e configuração do projeto (Poetry)
├── .env.example               # Template de variáveis de ambiente
├── .gitignore
└── README.md
```

---

## 🚀 Instalação e Execução

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) ≥ 2.20

> Para desenvolvimento local sem Docker: Python 3.11+ e [Poetry](https://python-poetry.org/docs/#installation)

---

### ▶️ Opção 1 — Docker Compose (recomendado)

Sobe **toda a stack** com um único comando: API, PostgreSQL, Redis, Kafka e ELK.

```bash
# 1. Clone o repositório
git clone https://github.com/leeoze/poke-api.git
cd poke-api

# 2. Crie o arquivo de variáveis de ambiente
cp .env.example .env

# 3. Suba todos os containers em background
docker compose up --build -d

# 4. Verifique o status dos containers
docker compose ps
```

Aguarde cerca de 30 segundos para todos os serviços inicializarem. Após isso:

| Serviço | URL |
|---|---|
| **API — Swagger UI** | http://localhost:8000/docs |
| **API — ReDoc** | http://localhost:8000/redoc |
| **Health Check** | http://localhost:8000/health |
| **Kibana (logs)** | http://localhost:5601 |
| **Elasticsearch** | http://localhost:9200 |

```bash
# Ver logs da API em tempo real
docker compose logs -f api

# Ver logs do Celery worker
docker compose logs -f celery_worker

# Parar todos os containers (mantém volumes/dados)
docker compose down

# Parar e apagar todos os dados
docker compose down -v
```

---

### ▶️ Opção 2 — Desenvolvimento local com Poetry

```bash
# 1. Instale o Poetry (se ainda não tiver)
curl -sSL https://install.python-poetry.org | python3 -

# 2. Instale as dependências (cria o virtualenv automaticamente)
poetry install

# 3. Ative o shell do virtualenv
poetry shell

# 4. Copie e edite o .env com suas credenciais locais
cp .env.example .env

# 5. Suba apenas os serviços de infraestrutura (sem a API)
docker compose up postgres redis kafka -d

# 6. Rode a API com hot-reload
uvicorn src.main:app --reload --port 8000
```

---

## 🧪 Testes

Os testes usam **SQLite in-memory** — não precisam de PostgreSQL, Redis ou Kafka rodando.

```bash
# Executar todos os testes
poetry run pytest tests/ -v

# Com relatório de cobertura no terminal
poetry run pytest tests/ --cov=src --cov-report=term-missing

# Exige cobertura mínima de 80% (mesmo critério do CI)
poetry run pytest tests/ --cov=src --cov-fail-under=80

# Gerar relatório HTML de cobertura
poetry run pytest tests/ --cov=src --cov-report=html
# Abrir: htmlcov/index.html
```

### O que é testado

| Categoria | Testes |
|---|---|
| Schema/estrutura | Campos corretos, tipos corretos, normalização de nome |
| Paginação | next/previous/total calculados corretamente |
| Erros esperados | 404 (não encontrado), 409 (duplicado), 422 (dados inválidos) |
| CRUD | Criar, buscar, atualizar, deletar |
| Health check | Endpoint /health retorna 200 |

---

## 📡 Endpoints da API

### Criar Pokémon
```http
POST /pokemons/
Content-Type: application/json

{
  "name": "pikachu",
  "height": 4,
  "weight": 60,
  "types": ["electric"],
  "sprites": {
    "front_default": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/25.png",
    "back_default": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/back/25.png"
  }
}
```

**Resposta 201:**
```json
{
  "id": 1,
  "name": "pikachu",
  "height": 4,
  "weight": 60,
  "types": ["electric"],
  "sprites": {
    "front_default": "https://...",
    "back_default": "https://..."
  }
}
```

### Listar Pokémons (paginado)
```http
GET /pokemons/?limit=20&offset=0
```

**Resposta 200:**
```json
{
  "data": [...],
  "pagination": {
    "total": 151,
    "limit": 20,
    "offset": 0,
    "next": "/pokemons?limit=20&offset=20",
    "previous": null
  }
}
```

### Buscar por ID
```http
GET /pokemons/1
```

### Atualizar (parcial)
```http
PUT /pokemons/1
Content-Type: application/json

{ "weight": 65 }
```

### Deletar
```http
DELETE /pokemons/1
```
Resposta: `204 No Content`

### Pokémon não encontrado
```http
GET /pokemons/99999
```
**Resposta 404:**
```json
{ "detail": "Pokémon com id=99999 não encontrado." }
```

---

## 📊 Monitoramento ELK

### Acessando o Kibana

1. Abra http://localhost:5601
2. Vá em **Discover** → **Create data view**
3. Index pattern: `poke-api-logs-*`
4. Timestamp field: `@timestamp`

### Campos disponíveis para filtro

| Campo | Descrição | Exemplo |
|---|---|---|
| `level` | Nível do log | `INFO`, `ERROR` |
| `path` | Rota acessada | `/pokemons/` |
| `method` | Método HTTP | `GET`, `POST` |
| `status_code` | Status da resposta | `200`, `404` |
| `duration_ms` | Tempo de resposta | `42.5` |
| `request_id` | ID único da requisição | `abc-123...` |

### Exemplos de queries Kibana (KQL)

```
# Erros 500
status_code >= 500

# Requisições lentas (> 500ms)
duration_ms > 500

# Erros da aplicação
tags: "app_error"

# Requisições de um IP específico
client_ip: "192.168.1.1"
```

---

## ☸️ Kubernetes

```bash
# Criar os secrets (substitua pelos valores reais)
kubectl create secret generic poke-api-secrets \
  --from-literal=database-url='postgresql+asyncpg://...' \
  --from-literal=redis-url='redis://...'

# Aplicar todos os manifestos
kubectl apply -f k8s/

# Verificar status
kubectl get pods
kubectl get services
kubectl get ingress

# Ver logs de um pod
kubectl logs -f deployment/poke-api

# Escalar manualmente
kubectl scale deployment poke-api --replicas=5
```

---

## 🔄 CI/CD

### Configuração no GitHub

1. Vá em **Settings → Secrets → Actions**
2. Adicione o secret:
   ```
   RENDER_DEPLOY_HOOK_URL = https://api.render.com/deploy/srv-XXXX?key=YYYY
   ```
   _(O webhook é gerado em Render.com → Service → Settings → Deploy Hook)_

### Fluxo do pipeline

```
Push para main
     ↓
[CI] Instala dependências com Poetry
     ↓
[CI] pytest --cov-fail-under=80
     ↓ (se passou)
[CD] curl RENDER_DEPLOY_HOOK_URL
     ↓
Deploy automático no Render.com 🚀
```

---

## 🌐 Produção

> **API em produção:** https://poke-api-x360.onrender.com

---

## ⚙️ Comandos úteis de desenvolvimento

```bash
# Worker Celery local
poetry run celery -A src.workers.celery_app worker --loglevel=info

# Verificar tipos estáticos
poetry run mypy src/

# Lint e formatação
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/

# Abrir shell do banco de dados
docker compose exec postgres psql -U postgres -d pokedb

# Inspecionar filas do Redis
docker compose exec redis redis-cli
> KEYS *
> GET pokemon:25
```
