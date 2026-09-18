$logf = "d:\Apps\codex\files\simulate\runtime\inject_hits.txt"
$m1 = [byte[]](0x0a,0x00,0x19,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x05,0x78,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x03,0x00,0x00,0x00,0x00)
$m2 = [byte[]](0x0a,0x00,0x11,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x03,0xe8,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00)
$m3 = [byte[]](0x0a,0x00,0x19,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x05,0x78,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00)
[IO.File]::WriteAllText($logf, "start $(Get-Date -Format HH:mm:ss)`r`n")
for ($i=0; $i -lt 400; $i++) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', 14279)
    $c.ReceiveTimeout = 10000
    $s = $c.GetStream()
    $wrote = 0
    foreach ($m in @($m1,$m2,$m3)) {
      $s.Write($m,0,$m.Length); $s.Flush(); $wrote += $m.Length
      Start-Sleep -Milliseconds 200
    }
    $buf = New-Object byte[] 64
    $readInfo = "noresp"
    try { $n = $s.Read($buf,0,64); if ($n -gt 0) { $readInfo = "resp=${n}:" + (($buf[0..($n-1)] | ForEach-Object { $_.ToString('X2') }) -join '') } } catch {
      if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { $readInfo = "read-timeout" } else { $readInfo = "read-aborted" }
    }
    $c.Close()
    [IO.File]::AppendAllText($logf, "hit $i at $(Get-Date -Format HH:mm:ss) wrote=$wrote $readInfo`r`n")
    Start-Sleep -Seconds 10
  } catch { Start-Sleep -Seconds 5 }
}
