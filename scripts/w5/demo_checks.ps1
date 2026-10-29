param(
    [string]$Python = ".private/w5/tokenizer-runtime/Scripts/python.exe",
    [string]$Candidate = "",
    [string]$Payload = ""
)
$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw "Python runtime missing; see scripts/w5/README.md" }
    function Run-Step([string[]]$Arguments, [int]$Expected = 0) {
        & $Python @Arguments
        if ($LASTEXITCODE -ne $Expected) { throw "Expected exit $Expected; received $LASTEXITCODE" }
    }
    Run-Step -Arguments @("-B", "-m", "unittest", "discover", "-s", "scripts/w5/tests")
    Run-Step -Arguments @("-B", "scripts/w5/validate_instruction_dataset.py", "--input", "data/fixtures/w5-instruction-contract.jsonl", "--fixture-mode", "--report", ".private/w5/demo/fixture-validation.json")
    Run-Step -Arguments @("-B", "scripts/w5/check_training_format.py", "--input", "data/fixtures/w5-instruction-contract.jsonl", "--payload", "data/fixtures/w5-sft-contract-preview.jsonl", "--fixture-mode", "--report", ".private/w5/demo/fixture-tokenization.json")
    Run-Step -Expected 1 -Arguments @("-B", "scripts/w5/validate_instruction_dataset.py", "--input", "data/fixtures/w5-instruction-contract.jsonl", "--fixture-mode", "--stage", "release", "--report", ".private/w5/demo/fixture-release-rejected.json")
    if ($Candidate -or $Payload) {
        if (-not $Candidate -or -not $Payload) { throw "Provide both -Candidate and -Payload" }
        Run-Step -Arguments @("-B", "scripts/w5/validate_instruction_dataset.py", "--input", $Candidate, "--report", ".private/w5/demo/member-validation.json")
        Run-Step -Arguments @("-B", "scripts/w5/check_training_format.py", "--input", $Candidate, "--payload", $Payload, "--draft-mode", "--report", ".private/w5/demo/member-tokenization.json")
        # Reviewed full releases use the explicit commands in README instead.
        Run-Step -Expected 1 -Arguments @("-B", "scripts/w5/create_split_plan.py", "--input", $Candidate, "--report", ".private/w5/demo/unreviewed-release-rejected.json")
    }
    Write-Output "Demo completed. Read each report's stage/eligible_ids; passing draft checks is not release approval."
}
finally { Pop-Location }
