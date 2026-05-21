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

Write-Host ""
Write-Host "Final check completed." -ForegroundColor Green
