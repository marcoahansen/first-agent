# First Agent — ReAct (Reasoning + Action)

Notebook didático de um agente LLM no padrão **ReAct**: o agente alterna entre `Thought → Action → Observation → Answer` até resolver a pergunta.

Suporta dois providers de LLM, intercambiáveis via variável de ambiente:

- **Google Gemini** (free tier no [AI Studio](https://aistudio.google.com/app/apikey)) — default
- **OpenAI** (`gpt-4o-mini`)

## Estrutura

```
first-agent/
├── pyproject.toml        # uv + Python 3.11 + deps
├── .env.example          # template das chaves
├── .gitignore
├── react_agent.ipynb     # notebook principal
└── README.md
```

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

## Rodar o notebook

```bash
uv run jupyter notebook react_agent.ipynb
```

No Jupyter, selecione o kernel **Python (first-agent)** e execute as células em ordem.

## Conteúdo do notebook

1. **Setup** — carrega `.env`, escolhe provider.
2. **Classe `Agent`** — guarda histórico de mensagens, faz chamadas com `temperature=0`.
3. **Prompt ReAct** — instrui o modelo a alternar Thought/Action/PAUSE/Observation/Answer.
4. **Tools** — `calculate` (eval aritmético) e `preco_prato` (lookup em cardápio). Mapeadas em `known_actions`.
5. **Fluxo manual** — roda o ciclo passo a passo.
6. **`query()`** — automatiza o loop: detecta `Action:`, executa, devolve `Observation:`, repete até `Answer:`.
7. **Pergunta composta** — força encadeamento de ações (`"feijoada + picanha"` → dois lookups + soma).

## Modelos atuais

- Gemini: `gemini-2.5-flash` (default — bom equilíbrio de qualidade e cota grátis)
- OpenAI: `gpt-4o-mini`

Para trocar, edite `GEMINI_MODEL` ou `OPENAI_MODEL` na primeira célula.

## Trocar versão do Python

Edite `requires-python` em `pyproject.toml` e rode `uv sync` novamente.

## Segurança

- `.env` está no `.gitignore` — **nunca** suba sua chave.
- Use `.env.example` como template para outros desenvolvedores.
- A função `calculate` usa `eval()` — apenas didático, **não** exponha em produção sem sandbox.
