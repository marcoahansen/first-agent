# First Agent — Módulo 1 (Construção de Agentes com IA)

Repositório com os notebooks da **primeira etapa do curso** (Módulo 1): introdução a agentes LLM no padrão **ReAct** (Reasoning + Acting).

Cada notebook alterna entre `Thought/Pensamento → Action/Ação → Observation/Observação → Answer/Resposta` até resolver a pergunta. Suporta dois providers de LLM, intercambiáveis via variável de ambiente:

- **Google Gemini** (free tier no [AI Studio](https://aistudio.google.com/app/apikey)) — default
- **OpenAI** (`gpt-4o-mini`)

## Estrutura

```
first-agent/
├── pyproject.toml                       # uv + Python 3.11 + deps
├── .env.example                         # template das chaves
├── .gitignore
├── README.md
└── notebooks/
    ├── react_agent.ipynb                # base — tools calculate + preco_prato
    └── m1a3_react_agent.ipynb           # atividade M1A3 — + calcular_idade + converter_moeda
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

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (gerenciador de ambiente/Python)

Instalação rápida do `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

## Setup

```bash
git clone <este-repo>
cd first-agent

uv python install 3.11
uv sync                            # cria .venv e instala deps
cp .env.example .env               # edite e preencha sua chave
uv run python -m ipykernel install --user --name first-agent --display-name "Python (first-agent)"
```

No `.env`, preencha **apenas** o provider que você vai usar:

```env
LLM_PROVIDER=gemini                # ou "openai"
GOOGLE_API_KEY=...                 # se gemini
OPENAI_API_KEY=...                 # se openai
```

## Rodar os notebooks

```bash
uv run jupyter notebook notebooks/
```

No Jupyter, abra o notebook desejado, selecione o kernel **Python (first-agent)** e execute as células em ordem.

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
