# Agente de Monitoramento de Câmeras (Windows)

Este diretório contém o agente Python que roda em cada computador local (Galpão, Rancho, Escritório) para pingar câmeras IP e testar a conectividade de rede, enviando relatórios periódicos para o servidor FastAPI central.

## Pré-requisitos
- Windows 10/11
- Python 3.10+
- Conectividade para alcançar o servidor (ex.: `http://SEU_SERVIDOR:9000`)

As dependências já estão no `requirements.txt` da raiz (FastAPI é para o servidor e `requests` para o agente). Se for usar um ambiente virtual:

```powershell
# na raiz do projeto (c:\monitoramento)
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

## Configuração do servidor (central)
No arquivo `.env` da raiz do projeto, configure (opcional em dev):

```
FAST_API_PORT=9000
# Mapa de tokens por site (pode usar ; ou , como separador)
# Exemplo para 3 localidades:
AGENT_TOKENS=galpao=token_galpao;rancho=token_rancho;escritorio=token_escritorio

# Intervalo sugerido para os agentes
AGENT_INTERVAL_SEC=60
# Tempo para considerar agente offline (sem report) em minutos
AGENT_OFFLINE_MINUTES=3
```

Inicie o servidor:

```powershell
# na raiz do projeto
python .\api_server.py
```

Endpoints relevantes do servidor:
- `GET /api/agents/{site}/config` (header opcional `X-Agent-Token`): retorna lista de câmeras do site e intervalos.
- `POST /api/agents/{site}/report` (header opcional `X-Agent-Token`): recebe o relatório do agente.
- `GET /api/status` e `GET /api/status/{site}`: resumo dos sites e detalhes do último relatório.

A UI (React) tem a aba "Localidades" que consome `GET /api/status`.

## Configuração das câmeras
Edite o arquivo `cameras.json` na raiz do projeto para incluir o campo `site` em cada câmera, por exemplo:

```json
[
  { "id": 1, "name": "Entrada Galpão", "ip": "192.168.10.80", "site": "galpao" },
  { "id": 2, "name": "Pátio Galpão", "ip": "192.168.10.81", "site": "galpao" },
  { "id": 3, "name": "Entrada Rancho", "ip": "192.168.20.80", "site": "rancho" },
  { "id": 4, "name": "Recepção Escritório", "ip": "192.168.30.80", "site": "escritorio" }
]
```

Se `site` não for informado, o backend assume `"default"`.

## Configuração do agente (em cada PC)
Você pode configurar via arquivo `agent.json` (já incluído como modelo) OU via variáveis de ambiente.

Arquivo `agent.json` (exemplo):
```json
{
  "site": "galpao",
  "server": "http://localhost:9000",
  "token": "token_galpao",
  "interval_sec": 60,
  "loop": true,
  "cameras": []
}
```

Variáveis de ambiente (alternativa):
- `AGENT_SITE` (ex.: `galpao`, `rancho`, `escritorio`)
- `AGENT_SERVER` (ex.: `http://SEU_SERVIDOR:9000`)
- `AGENT_TOKEN` (conforme configurado no servidor)
- `AGENT_INTERVAL_SEC` (opcional)
- `AGENT_LOOP=1` para rodar continuamente

## Executar o agente

Rodar uma vez:
```powershell
# no diretório c:\monitoramento\agent
python .\agent.py
```

Rodar continuamente (se não usar `agent.json` com `loop: true`):
```powershell
$env:AGENT_LOOP="1"
python .\agent.py
```

## Agendar no Windows Task Scheduler (a cada 1 minuto)
Crie uma tarefa que rode um script PowerShell. Exemplo de comando:

```powershell
schtasks /Create /TN "MonitoramentoAgente" /SC MINUTE /MO 1 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\monitoramento\agent\run_agent.ps1" /RL HIGHEST
```

O script `run_agent.ps1` (incluído aqui) chama o agente. Edite-o para definir `AGENT_SITE`, `AGENT_SERVER` e `AGENT_TOKEN` conforme o PC/localidade.

## Verificando no Dashboard
- Inicie o frontend (pasta `project`): `npm run dev`
- Acesse `http://localhost:5173` (ou porta configurada) e vá na aba "Localidades" para ver os sites, status (`OK`, `Degradado`, `Offline`), câmeras UP/TOTAL e última atualização.

## Observações
- Em ambiente de desenvolvimento, se nenhum token for configurado no servidor, as requisições do agente são aceitas (útil para testar rapidamente).
- O agente pinga as câmeras e testa rede (1.1.1.1 e 8.8.8.8), DNS e HTTP (google.com) e envia o resultado consolidado.
- Para distribuir sem Python instalado, é possível empacotar o agente com PyInstaller no futuro.
