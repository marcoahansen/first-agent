# Módulo 1 — Fundamentos práticos de agentes com LLMs

Repositório com **todas as atividades do Módulo 1** do curso: introdução a agentes LLM, do padrão **ReAct** (Reasoning + Acting) construído na mão até um agente de pesquisa com **LangGraph** + busca na web.

Os notebooks ReAct alternam entre `Thought/Pensamento → Action/Ação → Observation/Observação → Answer/Resposta` até resolver a pergunta. Suportam dois providers de LLM, intercambiáveis via variável de ambiente:

- **Google Gemini** (free tier no [AI Studio](https://aistudio.google.com/app/apikey)) — default
- **OpenAI** (`gpt-4o-mini`)

## Estrutura

```
llm-agents-fundamentals/
├── pyproject.toml                       # uv + Python 3.11 + deps
├── .env.example                         # template das chaves
├── .gitignore
├── README.md
└── notebooks/
    ├── react_agent.ipynb                # base — tools calculate + preco_prato
    ├── m1a3_react_agent.ipynb           # atividade M1A3 — + calcular_idade + converter_moeda
    └── m1a4_research_agent.ipynb        # atividade M1A4 — LangGraph + Tavily (agente de pesquisa)
```

## Notebooks

### `notebooks/react_agent.ipynb` — base
Implementação mínima do padrão ReAct:

1. Setup do provider (`.env` → `LLM_PROVIDER`).
2. Classe `Agent` com histórico e `temperature=0`.
3. Prompt ReAct.
4. Tools `calculate` (eval aritmético) e `preco_prato` (lookup em cardápio).
5. Fluxo manual passo a passo.
6. `query()` automatiza o loop até `Answer:`.
7. Pergunta composta (`feijoada + picanha` → 2 lookups + soma).

### `notebooks/m1a3_react_agent.ipynb` — atividade M1A3
Estende o notebook base com:

- Tools novas: `calcular_idade` e `converter_moeda` (taxa explícita ou tabela interna USD/BRL/EUR).
- `known_actions` atualizado com 4 ferramentas.
- Testes que forçam o ciclo ReAct:
  - "Quantos anos tem alguém que nasceu em 1995?"
  - "Quanto é 10 dólares em reais, considerando que 1 USD = 5,00 BRL?"
  - Pergunta composta (idade + conversão).

### `notebooks/m1a4_research_agent.ipynb` — atividade M1A4
Agente de pesquisa com **LangGraph** + **Tavily** (busca na web):

- Grafo com 2 nós (`llm` ↔ `action`) e aresta condicional baseada em `tool_calls`.
- SDK Tavily atual (`langchain-tavily`) — substitui o `TavilySearchResults` do `langchain-community` (deprecated).
- Dual provider: `ChatGoogleGenerativeAI` (Gemini) ou `ChatOpenAI` — ambos com tool calling nativo.
- Requer `TAVILY_API_KEY` no `.env` (free tier em https://tavily.com).
- Testes: clima do Rio, capital do Canadá, Copa do Mundo de 2014, pergunta composta (Copa 2022 + PIB).

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (gerenciador de ambiente/Python)

Instalação rápida do `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

## Setup

```bash
git clone https://github.com/marcoahansen/llm-agents-fundamentals.git
cd llm-agents-fundamentals

uv python install 3.11
uv sync                            # cria .venv e instala deps
cp .env.example .env               # edite e preencha sua chave
uv run python -m ipykernel install --user --name llm-agents-fundamentals --display-name "Python (llm-agents-fundamentals)"
```

No `.env`, preencha **apenas** o provider que você vai usar:

```env
LLM_PROVIDER=gemini                # ou "openai"
GOOGLE_API_KEY=...                 # se gemini
OPENAI_API_KEY=...                 # se openai
TAVILY_API_KEY=...                 # obrigatório para o notebook M1A4
```

## Rodar os notebooks

```bash
uv run jupyter notebook notebooks/
```

No Jupyter, abra o notebook desejado, selecione o kernel **Python (llm-agents-fundamentals)** e execute as células em ordem.

## Modelos atuais

- Gemini: `gemini-2.5-flash` (default — bom equilíbrio de qualidade e cota grátis)
- OpenAI: `gpt-4o-mini`

Para trocar, edite `GEMINI_MODEL` ou `OPENAI_MODEL` na célula de setup do notebook.

## Trocar versão do Python

Edite `requires-python` em `pyproject.toml` e rode `uv sync` novamente.

## Segurança

- `.env` está no `.gitignore` — **nunca** suba sua chave.
- Use `.env.example` como template para outros desenvolvedores.
- A função `calculate` usa `eval()` — apenas didático, **não** exponha em produção sem sandbox.
