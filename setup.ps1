$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $args"
    }
}

function Test-Docker {
    param([string[]]$Command)
    # A probe can fail while a service starts or a model is not installed yet.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    & docker @Command 2>&1 | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Wait-Docker {
    param([string]$Step, [string[]]$Command)
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-Docker $Command) { return }
        Start-Sleep -Seconds 2
    }
    & docker @Command
    throw "$Step did not become ready."
}

function Ensure-Model {
    param([string]$Service, [string]$Setting)
    $model = (Invoke-Docker compose exec -T api python -c (
        "from app.configs import settings; print(settings.$Setting.model_name)"
    )).Trim()
    $server = @('compose', '-f', "docker-compose.$Service.yml", 'exec', '-T', $Service)
    Wait-Docker "Ollama ($Service)" ($server + @('ollama', 'list'))
    if (!(Test-Docker ($server + @('ollama', 'show', $model)))) {
        Invoke-Docker @server ollama pull $model
    }
}

Push-Location $PSScriptRoot
try {
    Invoke-Docker info --format '{{.ServerVersion}}'
    if (!(Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    if ((Test-Path -LiteralPath 'security_events.jsonl' -PathType Leaf) -and
        !(Test-Path -LiteralPath 'audit/security_events.jsonl')) {
        New-Item -ItemType Directory -Path 'audit' -Force | Out-Null
        Copy-Item -LiteralPath 'security_events.jsonl' -Destination 'audit/security_events.jsonl'
    }

    Invoke-Docker compose -f docker-compose.embedder.yml up -d embedder
    Invoke-Docker compose -f docker-compose.llm.yml up -d llm
    Invoke-Docker compose up -d --build
    Wait-Docker 'API' @(
        'compose', 'exec', '-T', 'api', 'curl', '-fsS', '--max-time', '5',
        'http://127.0.0.1:8000/health'
    )
    Ensure-Model embedder embedding
    Ensure-Model llm llm
    $probe = "import os; from urllib.parse import urljoin; from urllib.request import urlopen; " +
        "[urlopen(urljoin(os.environ[name], '/api/tags'), timeout=5).close() " +
        "for name in ('EMBEDDING_URL', 'LLM_URL')]"
    Wait-Docker 'API connection to Ollama' @('compose', 'exec', '-T', 'api', 'python', '-c', $probe)
    Invoke-Docker compose exec -T api python -m scripts.seed_data
    Write-Host 'Ready. Swagger: http://localhost:8000/docs'
}
finally {
    Pop-Location
}
