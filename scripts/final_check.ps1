$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Command
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Command
}

function Invoke-HttpCheck {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Uri
    )

    Invoke-Step $Name {
        $response = Invoke-WebRequest -Uri $Uri -Method Get -UseBasicParsing -TimeoutSec 10
        Write-Host "$Uri -> HTTP $($response.StatusCode)"
    }
}

Invoke-Step "Docker Compose services" {
    docker compose ps
}

Invoke-Step "Backend tests" {
    python -m pytest backend/tests -v
}

Invoke-Step "Frontend tests" {
    npm --prefix frontend run test
}

Invoke-Step "Frontend typecheck" {
    npm --prefix frontend run typecheck
}

Invoke-Step "Frontend build" {
    npm --prefix frontend run build
}

Invoke-Step "Celery smoke test" {
    docker compose exec -T backend python scripts/celery_smoke_test.py
}

Invoke-Step "Health endpoint" {
    Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get | ConvertTo-Json -Depth 5
}

Invoke-Step "Monitoring summary endpoint" {
    $login = Invoke-RestMethod `
        -Uri "http://localhost:8000/api/v1/auth/login" `
        -Method Post `
        -ContentType "application/json" `
        -Body '{"username":"admin_demo","password":"admin123"}'
    Invoke-RestMethod `
        -Uri "http://localhost:8000/api/v1/monitoring/summary" `
        -Method Get `
        -Headers @{ Authorization = "Bearer $($login.access_token)" } |
        ConvertTo-Json -Depth 8
}

Invoke-Step "Prometheus metrics endpoint" {
    curl.exe -s "http://localhost:8000/metrics" |
        Select-String -Pattern "analyze_requests_total"
}

Invoke-HttpCheck "Prometheus ready" "http://localhost:9090/-/ready"

Invoke-Step "Prometheus targets API" {
    Invoke-RestMethod -Uri "http://localhost:9090/api/v1/targets" -Method Get |
        ConvertTo-Json -Depth 8
}

Invoke-HttpCheck "Grafana health" "http://localhost:3000/api/health"
Invoke-HttpCheck "Loki ready" "http://localhost:3100/ready"
Invoke-HttpCheck "Flower UI" "http://localhost:5555"
Invoke-HttpCheck "RedisInsight UI" "http://localhost:5540"
Invoke-HttpCheck "cAdvisor UI" "http://localhost:8080"

Write-Host ""
Write-Host "Final check completed." -ForegroundColor Green
