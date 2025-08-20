# Configurações do agente (edite conforme o PC/localidade)
$env:AGENT_SITE = $env:AGENT_SITE -or "galpao"
$env:AGENT_SERVER = $env:AGENT_SERVER -or "http://localhost:9000"
# Preencha o token se o servidor exigir (em dev, pode ficar vazio)
$env:AGENT_TOKEN = $env:AGENT_TOKEN -or ""
# Intervalo em segundos (apenas quando AGENT_LOOP=1)
$env:AGENT_INTERVAL_SEC = $env:AGENT_INTERVAL_SEC -or "60"
# 1 para rodar continuamente, 0 para executar uma vez
$env:AGENT_LOOP = $env:AGENT_LOOP -or "1"

# Descobrir Python do venv se existir
$agentDir = $PSScriptRoot
$repoRoot = Resolve-Path (Join-Path $agentDir "..")
$venvPython = Join-Path $repoRoot ".venv/Scripts/python.exe"

if (Test-Path $venvPython) {
  & $venvPython (Join-Path $agentDir "agent.py")
} else {
  python (Join-Path $agentDir "agent.py")
}
