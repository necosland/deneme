# Trader ofisi 4 saatlik turu (sahte para). Elle calistirma girisi; is tur.py'de.
# Zamanlayici (TraderOfisTur) pencere hic acilmasin diye pythonw.exe ile tur.py'yi dogrudan cagirir:
# powershell -WindowStyle Hidden bile her calismada kisa bir konsol penceresi gosterir.
# Ornek: .\tur.ps1            .\tur.ps1 -Force       .\tur.ps1 -Only trader-turev -NoRisk -NoLedger
param([switch]$Force, [switch]$SkipData, [string]$Only, [switch]$NoRisk, [switch]$NoLedger)
$ErrorActionPreference = 'Stop'
$py = 'C:\Users\pc\AppData\Local\Programs\Python\Python313\python.exe'   # PATH'teki python numpy'siz
$a = @("$PSScriptRoot\tur.py")
if ($Force)    { $a += '--force' }
if ($SkipData) { $a += '--skip-data' }
if ($Only)     { $a += @('--only', $Only) }
if ($NoRisk)   { $a += '--no-risk' }
if ($NoLedger) { $a += '--no-ledger' }
& $py @a
exit $LASTEXITCODE
