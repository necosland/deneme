# Trader ofisi gundem zamanli gorevini kurar/gunceller (kullanici duzeyi, yonetici gerekmez). Tekrar calistirmak guvenli.
#  TraderOfisGundem : her gun 10:00 TR, gunluk.py = topla.py (yeni icerik) + ozetle.py (claude -p --agent trader-gundem)
# pythonw.exe konsolsuz calisir: pencere ve ses yok (video/ses indirilmez, yalniz altyazi ve metin).
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$pyw = 'C:\Users\pc\AppData\Local\Programs\Python\Python313\pythonw.exe'
$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries `
     -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
$a = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\gunluk.py`"" -WorkingDirectory $dir
$t = New-ScheduledTaskTrigger -Daily -At '10:00'
Register-ScheduledTask -TaskName 'TraderOfisGundem' -Action $a -Trigger $t -Settings $s -Principal $principal `
  -Description 'Trader ofisi gundem: kaynaklardan yeni yorum toplar, trader-gundem (Defne) ozetler. algo\ofis\gundem\gunluk.py' -Force | Out-Null
$i = Get-ScheduledTask -TaskName 'TraderOfisGundem' | Get-ScheduledTaskInfo
'TraderOfisGundem: next {0}' -f $i.NextRunTime
