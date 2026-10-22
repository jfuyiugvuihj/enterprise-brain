param(
    [string]$ExtraArgs = ""
)

$ErrorActionPreference = "Stop"
$command = "pytest -q tests/test_upgrade_baseline.py tests/test_private_model_routing.py tests/test_retrieval_pipeline_concurrency.py $ExtraArgs"
& powershell -NoProfile -Command $command
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
