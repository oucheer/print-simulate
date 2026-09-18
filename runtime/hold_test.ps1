# hold test: connect, send nothing, read repeatedly to find when firmware RSTs
$logf = "d:\Apps\codex\files\simulate\runtime\hold_test.txt"
$c = New-Object System.Net.Sockets.TcpClient
$c.Connect('127.0.0.1', 14279)
$c.ReceiveTimeout = 3000
$s = $c.GetStream()
$lines = @()
for ($t=0; $t -lt 10; $t++) {
  Start-Sleep -Milliseconds 1000
  $buf = New-Object byte[] 16
  $st = "t=$t"
  try { $n = $s.Read($buf,0,16); if ($n -gt 0) { $st += " data=${n}" } else { $st += " eof" } } catch {
    if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { $st += " timeout" } else { $st += " aborted:$($_.Exception.InnerException.SocketErrorCode)" }
  }
  $lines += $st
  Write-Host $st
  if ($st -match "aborted|eof") { break }
}
try { $c.Close() } catch {}
[IO.File]::WriteAllText($logf, "hold start $(Get-Date -Format HH:mm:ss)`r`n" + ($lines -join "`r`n") + "`r`n")
echo "HOLD_DONE"
