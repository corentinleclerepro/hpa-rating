param(
    [Parameter(Mandatory=$true)][string]$Configuration,
    [int]$Port = 8002,
    [switch]$PreparerPremierAcces
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$projectDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$encrypted = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Configuration).Path)
$clear = [Security.Cryptography.ProtectedData]::Unprotect($encrypted,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
try {
    $config = [Text.Encoding]::UTF8.GetString($clear) | ConvertFrom-Json
    if ($config.HPA_SUPABASE_ROLE -ne 'admin') { throw 'Configuration opérateur requise.' }
    foreach ($field in @('HPA_SUPABASE_ROLE','HPA_SUPABASE_PROJECT','HPA_DB_HOST','HPA_DB_PASSWORD','HPA_INVITATION_KEY','HPA_GUEST_ORIGIN','HPA_DATA_DIR')) {
        if (-not $config.$field) { throw "Champ absent dans la configuration : $field" }
        [Environment]::SetEnvironmentVariable($field, $config.$field, 'Process')
    }
} finally {
    [Array]::Clear($clear,0,$clear.Length)
}
$python = Join-Path $projectDir '.venv\Scripts\python.exe'
$entry = Join-Path $projectDir 'run_admin.py'
if ($PreparerPremierAcces) {
    $card = Join-Path $env:HPA_DATA_DIR 'premier-acces.txt'
    if (Test-Path -LiteralPath $card) { throw "Une fiche existe déjà dans $card." }
    & $python -X utf8 -B $entry --port $Port --setup-key $card
    if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $card)) { Write-Host "Fiche privée : $card" }
} else {
    & $python -X utf8 -B $entry --port $Port
}
exit $LASTEXITCODE
