[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$templatePath = Join-Path $projectRoot '.env.example'
$envPath = Join-Path $projectRoot '.env'

if (Test-Path -LiteralPath $envPath) {
    Write-Output 'Docker environment already exists; leaving it unchanged.'
    exit 0
}

if (-not (Test-Path -LiteralPath $templatePath)) {
    throw "Missing environment template: $templatePath"
}

function New-UrlSafeSecret {
    param([int]$Bytes = 32)

    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    }
    finally {
        $rng.Dispose()
    }

    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Set-EnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $pattern = '(?m)^' + [Regex]::Escape($Name) + '=.*$'
    if (-not [Regex]::IsMatch($Content, $pattern)) {
        throw "Environment template is missing $Name"
    }
    return [Regex]::Replace($Content, $pattern, "$Name=$Value", 1)
}

$content = [IO.File]::ReadAllText($templatePath)
$rabbitPassword = New-UrlSafeSecret 36
$secrets = [ordered]@{
    VLLM_API_KEY = New-UrlSafeSecret 36
    QDRANT_API_KEY = New-UrlSafeSecret 36
    RABBITMQ_PASSWORD = $rabbitPassword
    INTERNAL_AUTH_SECRET = New-UrlSafeSecret 48
    PASSWORD_PEPPER = New-UrlSafeSecret 48
    SESSION_PEPPER = New-UrlSafeSecret 48
    MONGO_ROOT_PASSWORD = New-UrlSafeSecret 36
    MONGO_GATEWAY_PASSWORD = New-UrlSafeSecret 36
    MONGO_FILES_PASSWORD = New-UrlSafeSecret 36
    MONGO_MEMORY_PASSWORD = New-UrlSafeSecret 36
    MONGO_RAG_PASSWORD = New-UrlSafeSecret 36
}

foreach ($entry in $secrets.GetEnumerator()) {
    $content = Set-EnvironmentValue -Content $content -Name $entry.Key -Value $entry.Value
}
$content = Set-EnvironmentValue -Content $content -Name 'RABBITMQ_URL' -Value "amqp://ragapp:$rabbitPassword@rabbitmq:5672/"

[IO.File]::WriteAllText($envPath, $content, (New-Object Text.UTF8Encoding($false)))

# Keep the workspace ACL inheritance so Docker Desktop, the IDE, and the
# launching user can all read the file.  Git ignores the file and the script
# never prints any generated value.
Write-Output 'Generated a local .env with independent random secrets.'
Write-Output 'Create the first administrator in the browser on first run (http://localhost:3000).'
