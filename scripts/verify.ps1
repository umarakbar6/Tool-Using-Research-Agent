$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m unittest discover -s tests -v
    python -m compileall -q src tests
    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    python -m research_agent.demo --write_examples examples
}
finally {
    Pop-Location
}
