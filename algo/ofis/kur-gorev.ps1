# Trader ofisi zamanlanmis gorevlerini kurar/gunceller (kullanici duzeyi, yonetici gerekmez). Tekrar calistirmak guvenli.
#  TraderOfisTur     : 03:20 07:20 11:20 15:20 19:20 23:20 TR (Binance 4h kapanisindan 20 dk sonra), tur.py
#  TraderOfisKontrol : 5 dakikada bir, kontrol.py --quiet (LLM yok)
# pythonw.exe konsolsuz calisir: pencere ve ses yok. Alt surecler CREATE_NO_WINDOW ile acilir.
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$pyw = 'C:\Users\pc\AppData\Local\Programs\Python\Python313\pythonw.exe'
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

$s1 = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 75)
# 75 dk (2026-11-21, tum evren 10 coin): tur.py T_TOTAL 40 dk + altyapi hatasinda 30 dk bekleme ve tekrar; eski 20 dk
$a1 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\tur.py`"" -WorkingDirectory $dir
$t1 = @('03:20','07:20','11:20','15:20','19:20','23:20') | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
Register-ScheduledTask -TaskName 'TraderOfisTur' -Action $a1 -Trigger $t1 -Settings $s1 -Principal $principal `
  -Description 'Trader ofisi 4 saatlik tur (sahte para): veri, uzmanlar, Riza, defter. algo\ofis\tur.py' -Force | Out-Null

$s2 = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
      -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
$a2 = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\kontrol.py`" --quiet" -WorkingDirectory $dir
$t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes([math]::Ceiling((Get-Date).TimeOfDay.TotalMinutes / 5) * 5) `
      -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName 'TraderOfisKontrol' -Action $a2 -Trigger $t2 -Settings $s2 -Principal $principal `
  -Description 'Trader ofisi izleyici (LLM yok): 1m mumlarla dolum/stop/hedef. algo\ofis\kontrol.py' -Force | Out-Null

Get-ScheduledTask -TaskName 'TraderOfis*' | ForEach-Object {
  $i = $_ | Get-ScheduledTaskInfo
  '{0}: {1}, next {2}' -f $_.TaskName, $_.State, $i.NextRunTime
}
