# Desafio Final da Trilha — Travel Planner + n8n + MCP

Estende o agente de viagens do **Módulo 1** (`notebooks/m1a7_travel_planner.ipynb`) com **duas ferramentas externas**, que o agente LangChain chama no ciclo normal de raciocínio/ação:

| Etapa | Ferramenta | Tecnologia | Fonte de dados |
|------|------------|-----------|----------------|
| **1** | `clima_e_checklist` | **n8n** (webhook) | Open-Meteo (sem chave) |
| **2** | `poi_find` | **Servidor MCP** (FastMCP) | Overpass/OpenStreetMap (sem chave) ou OpenTripMap |

```
Usuário: "Planeje 3 dias em Lisboa e diga o que levar."
        │
        ▼
   ┌─────────┐   rascunho de destinos/datas
   │  AGENTE │──────────────────────────────────────────────┐
   │(LangGraph)                                              │
   └────┬────┘                                               │
        │  bind_tools                                        │
        ├──► poi_find (MCP / FastMCP) ──► Overpass/OpenTripMap ─► atrações reais por dia
        ├──► clima_e_checklist (webhook) ─► n8n ─► Open-Meteo ──► previsão + checklist de mala
        ├──► preco_passagens (Tavily) ────────────────────────► preço de passagens
        └──► calcular_orcamento (Python) ─────────────────────► orçamento total
        │
        ▼
   plano final estruturado  (+ human-in-the-loop: revisa até 3x)
```

## Estrutura

```
desafio-final/
├── README.md                         # este arquivo
├── docker-compose.yml                # n8n local (Etapa 1)
├── n8n/
│   ├── weather_packing_workflow.json   # workflow RECOMENDADO (Webhook → Code → Respond) — robusto
│   └── weather_packing_canonical.json  # workflow CANÔNICO (Webhook → Split → HTTP → Code → Aggregate → Respond)
└── mcp_servers/
    └── poi_server.py                 # servidor MCP "POI Finder" (Etapa 2)

notebooks/
└── mf_travel_agent_plus.ipynb        # AGENTE final (Etapa 3) — orquestra tudo
```

## Setup

```bash
# na raiz do repo (llm-agents-fundamentals/)
uv sync                               # instala fastmcp + langchain-mcp-adapters (já no pyproject)
cp .env.example .env                  # se ainda não tiver; preencha as chaves
```

`.env` relevante:

```ini
LLM_PROVIDER=gemini                   # ou openai
GOOGLE_API_KEY=...                    # (ou OPENAI_API_KEY)
TAVILY_API_KEY=...                    # usado por preco_passagens e pelo nó de busca
N8N_WEBHOOK_URL=http://localhost:5678/webhook/weather-packing
OPENTRIPMAP_API_KEY=                  # OPCIONAL — vazio = POI server usa Overpass/OSM (sem chave)
```

---

## Etapa 1 — n8n "Weather & Packing Checklist" (webhook)

### 1. Subir o n8n

```bash
cd desafio-final
docker compose up -d                  # (ou: podman compose up -d)
# abra http://localhost:5678 e crie a conta local (fica offline)
```

### 2. Importar o workflow

No n8n: menu **⋮ → Import from File** → escolha `n8n/weather_packing_workflow.json`.

> **Qual importar?** Use o **`weather_packing_workflow.json`** (recomendado): 3 nós (`Webhook → Clima + Checklist (Code) → Respond to Webhook`). O nó *Code* faz, de forma transparente, o que o enunciado pede (geocoding + chamada Open-Meteo + montagem do checklist) e é robusto a diferenças de versão do n8n.
>
> O **`weather_packing_canonical.json`** traz a versão "didática" com os nós nativos do enunciado (`Split Out → HTTP Request (Open-Meteo) → Code → Aggregate`). Se algum nó reclamar de versão ao importar, ajuste no editor ou use o robusto. (Esse usa o path `weather-packing-canonical`.)

### 3. Ativar e pegar a URL

- Para uso normal: clique em **Active** (canto superior). A *Production URL* fica `http://localhost:5678/webhook/weather-packing`.
- Para depurar: deixe o workflow aberto, clique **Test workflow** e use a *Test URL* `http://localhost:5678/webhook-test/weather-packing` (dispara **uma** vez por clique). Nesse caso ajuste `N8N_WEBHOOK_URL` no `.env`.

### 4. Testar sem o agente

```bash
curl -s -X POST http://localhost:5678/webhook/weather-packing \
  -H 'Content-Type: application/json' \
  -d '{"itinerary":[{"city":"Lisboa","date":"2026-06-15"},
                    {"city":"Porto","lat":41.15,"lon":-8.61,"date":"2026-06-16"}]}'
```

Resposta (resumida):

```json
{
  "ok": true,
  "itinerary_weather": [
    {"city":"Lisboa","temp_min_c":16.5,"temp_max_c":28.1,"uv_index_max":8.05,"weather":"Nublado", ...}
  ],
  "checklists": [
    {"city":"Lisboa","items":["roupas leves","protetor solar FPS alto","óculos de sol"]}
  ]
}
```

**Contrato de entrada:** `{ "itinerary": [ {"city","date?","lat?","lon?"} ] }`. Coordenadas são opcionais — o workflow **geocodifica** o nome da cidade (Open-Meteo Geocoding) quando faltam. **Regras do checklist:** frio (`temp_min`) → casaco; calor (`temp_max ≥ 25/30`) → roupas leves/hidratação; chuva (`precip_prob`/`mm`) → guarda-chuva; UV alto (`uv_index_max ≥ 3/6`) → protetor solar; neve/trovoada (`weather_code`) → itens próprios.

---

## Etapa 2 — Servidor MCP "POI Finder" (FastMCP)

`mcp_servers/poi_server.py` expõe a tool **`poi_find`** (conceitualmente `poi.find` — usei underscore porque os nomes de função do tool-calling do Gemini/OpenAI não aceitam ponto).

```python
poi_find(lat, lon, radius_m=1500, kinds="", limit=10) -> list[POI]
POI = {id, name, kind, lat, lon, dist_m, preview, wikidata, source}
```

**Provider agnóstico:** com `OPENTRIPMAP_API_KEY` vazio usa **Overpass/OpenStreetMap** (sem chave, garante a demo); com a chave preenchida usa **OpenTripMap** (radius → detalhe por `xid`). Tem cache em memória (TTL 10 min) e erros amigáveis (`ToolError`).

> O cadastro do OpenTripMap às vezes fica indisponível — por isso o default é Overpass. `kinds` aceita vocabulário amigável: `museums, cultural, restaurants, parks, viewpoints, historic, churches, hotels, shops, attractions...` (separados por vírgula).

Você **não precisa subir** o servidor manualmente: o notebook o **spawna** via stdio. Para inspecionar à parte:

```bash
# stdio (modo usado pelo agente)
uv run python desafio-final/mcp_servers/poi_server.py
# HTTP streamable (p/ MCP Inspector / testes manuais) → http://127.0.0.1:8000/mcp
uv run python desafio-final/mcp_servers/poi_server.py --http
```

---

## Etapa 3 — O agente (notebook)

Abra **`notebooks/mf_travel_agent_plus.ipynb`** e rode as células em ordem. Ele:

1. carrega as tools locais (`calcular_orcamento`, `preco_passagens`, `clima_e_checklist`);
2. **spawna** o servidor MCP e carrega `poi_find` como tool LangChain (`MultiServerMCPClient`, stdio);
3. faz `model.bind_tools([...])` e roda o grafo `query → search → agent ⇄ tools → feedback`.

Nos logs aparecem as chamadas `🔧 tool: poi_find(...)` e `🔧 tool: clima_e_checklist(...)` — a prova de que o agente está usando as duas ferramentas externas.

---

## Troubleshooting

- **n8n não loga via http / "secure cookie"**: o compose já seta `N8N_SECURE_COOKIE=false`. Se mudou, reinicie o container.
- **Webhook 404 / "not registered"**: o workflow precisa estar **Active** (Production URL) ou com **Test workflow** clicado (Test URL). Confira se `N8N_WEBHOOK_URL` aponta para a URL certa.
- **podman rootless no WSL2** (`/run/user/1000` não gravável): `export XDG_RUNTIME_DIR=/run/user/$(id -u)` e garanta a sessão de usuário (`loginctl enable-linger $USER`), ou use Docker Desktop.
- **MCP carrega mas `poi_find` dá erro de rede/SSL**: o transporte stdio do MCP usa um env mínimo; o notebook já passa `env=dict(os.environ)` para propagar `PATH`, certificados e chaves ao subprocesso. Em redes com proxy TLS-interceptador, garanta que a CA do proxy esteja no truststore do Python.
- **Gemini reclama do schema de `clima_e_checklist`** (lista de objetos): troque o argumento tipado por uma string JSON — `async def clima_e_checklist(itinerary_json: str)` e `json.loads(...)` — que é à prova de qualquer provider.

## Mapa enunciado → implementação

| Pedido do enunciado | Onde está |
|---|---|
| Webhook trigger (POST) + resposta síncrona | nós `Webhook` (responseMode) + `Respond to Webhook` |
| Open-Meteo sem chave / HTTP Request | nó Code (`weather_packing_workflow.json`) ou nó `HTTP Request` (canônico) |
| SplitInBatches / Item Lists por destino | nó `Split Out` (canônico); no robusto, loop dentro do Code |
| Function (gerar checklist) + Aggregate | `buildChecklist()` + nó `Aggregate` (canônico) |
| `FastMCP(name=...)` + `@mcp.tool` + docstring | `poi_server.py` |
| `poi.find(lat, lon, radius_m, kinds, limit)` | `poi_find(...)` |
| API pública (OpenTripMap) + alternativa sem chave | OpenTripMap **e** Overpass/OSM, selecionável por env |
| Agente chama ambas no ciclo de ação | `bind_tools` + grafo `agent ⇄ tools` no notebook |
