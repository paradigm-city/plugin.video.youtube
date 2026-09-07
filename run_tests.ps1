# PowerShell helper script for running the local test suite and stats runner
param (
    [switch]$Fast,
    [switch]$Live,
    [switch]$Verbose,
    [switch]$SkipLint,
    [string]$Suite = "all"
)

$argsList = @("run_tests.py")

if ($Fast) { $argsList += "-f" }
if ($Live) { $argsList += "--live" }
if ($Verbose) { $argsList += "-v" }
if ($SkipLint) { $argsList += "--skip-lint" }
if ($Suite -ne "all") { $argsList += "--suite", $Suite }

# Forward any additional remaining arguments
$argsList += $args

python @argsList
exit $LASTEXITCODE

