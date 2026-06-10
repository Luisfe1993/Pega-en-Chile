# Batch-prep this week's picks. Stops on first failure with traceback.
$env:PYTHONIOENCODING="utf-8"
$picks = @(
    @{label="Genesys";    id="ab3f5baea19d6cb0"},
    @{label="TechBiz";    id="225499c6cf8952fd"},
    @{label="Red Hat";    id="b859d09f7da605be"},
    @{label="Caterpillar";id="44d534794bcf01d6"},
    @{label="Le Creuset"; id="852a58cf705514a6"},
    @{label="FLSmidth";   id="f63932ceefc454a1"},
    @{label="Terrific";   id="4f81ee928becd03f"}
)
foreach ($p in $picks) {
    Write-Host ""
    Write-Host "=== $($p.label)  $($p.id) ===" -ForegroundColor Cyan
    .\.venv\Scripts\pega.exe tailor $p.id 2>&1 | Where-Object { $_ -notmatch "UserWarning|warnings.warn|class Network|class Outreach|DeprecationWarning|datetime.datetime.utcnow|duckduckgo_search|validated_self|with DDGS|RuntimeWarning|self.__pydantic" }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED on $($p.label)" -ForegroundColor Red
        break
    }
    .\.venv\Scripts\pega.exe show $p.id 2>&1 | Where-Object { $_ -notmatch "UserWarning|warnings.warn|class Network|class Outreach" }
}
Write-Host ""
Write-Host "=== Sync pipeline ===" -ForegroundColor Cyan
.\.venv\Scripts\pega.exe pipeline sync --limit 50 2>&1 | Where-Object { $_ -notmatch "UserWarning|warnings.warn|class Network|class Outreach" }
