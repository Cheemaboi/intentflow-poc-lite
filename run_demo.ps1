$ErrorActionPreference = 'Stop'
$pocRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCommand = Get-Command python -ErrorAction Stop

& $pythonCommand.Source "$pocRoot\src\analyzer.py" --output "$pocRoot\evidence"
if ($LASTEXITCODE -ne 0) { throw "PoC analyzer returned exit code $LASTEXITCODE" }

& $pythonCommand.Source -m unittest discover -s "$pocRoot\tests" -p 'test_*.py' -v
if ($LASTEXITCODE -ne 0) { throw "PoC tests returned exit code $LASTEXITCODE" }
