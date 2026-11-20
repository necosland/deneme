# Trader ofisi kayitci gorevlerini kurar/gunceller (kullanici duzeyi, yonetici gerekmez). Tekrar calistirmak guvenli.
# kur-gorev.ps1'den ayri: o dosyayi yeniden calistirmak calisan tur/kontrol gorevlerine dokunur, bu dosya dokunmaz.
#  TraderOfisDerinlik : 5 dakikada bir, kayit_derinlik.py (emir defteri bantlari/duvarlari -> kayit\derinlik\)
#  TraderOfisTasfiye  : oturum acilisi + saatte bir, kayit_tasfiye.py (surekli websocket; calisiyorsa kilit yuzunden cikar)
# pythonw.exe konsolsuz calisir: pencere ve ses yok.
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$pyw = 'C:\Users\pc\AppData\Local\Programs\Python\Python313\pythonw.exe'
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$start = (Get-Date).Date.AddMinutes([math]::Ceiling((Get-Date).TimeOfDay.TotalMinutes / 5) * 5 + 2)

$s1 = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$a1 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\kayit_derinlik.py`"" -WorkingDirectory $dir
$t1 = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'TraderOfisDerinlik' -Action $a1 -Trigger $t1 -Settings $s1 -Principal $principal `
  -Description 'Trader ofisi kayitci (LLM yok): Binance emir defteri derinligi 5 dk. algo\ofis\kayit_derinlik.py' -Force | Out-Null

$s2 = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
$a2 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\kayit_tasfiye.py`"" -WorkingDirectory $dir
$t2a = New-ScheduledTaskTrigger -AtLogOn -User $user
$t2b = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName 'TraderOfisTasfiye' -Action $a2 -Trigger @($t2a, $t2b) -Settings $s2 -Principal $principal `
  -Description 'Trader ofisi kayitci (LLM yok): Binance tasfiye websocket, tek ornek. algo\ofis\kayit_tasfiye.py' -Force | Out-Null

Get-ScheduledTask -TaskName 'TraderOfis*' | ForEach-Object {
  $i = $_ | Get-ScheduledTaskInfo
  '{0}: {1}, next {2}, last result {3}' -f $_.TaskName, $_.State, $i.NextRunTime, $i.LastTaskResult
}
