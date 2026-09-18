# single injection: cmd=0x0d (registered), type=0x0a, observe response + keep-alive
$logf = "d:\Apps\codex\files\simulate\runtime\inject_0d.txt"
function Make-Frame([int]$cmd) {
  $body = New-Object byte[] 17
  $b = [BitConverter]::GetBytes([int32]$cmd)
  $body[1]=$b[0]; $body[2]=$b[1]; $body[3]=$b[2]; $body[4]=$b[3]
  $b = [BitConverter]::GetBytes([int32]3)   # w6 = sub = 3
  $body[5]=$b[0]; $body[6]=$b[1]; $body[7]=$b[2]; $body[8]=$b[3]
  $head = [byte[]](0x0a, 0x00, 0x11)
  $out = New-Object byte[] 20
  [Array]::Copy($head,0,$out,0,3)
  [Array]::Copy($body,0,$out,3,17)
  return $out
}
foreach ($cmd in @(0x0d, 0x0d)) {
  $f = Make-Frame $cmd
  $c = New-Object System.Net.Sockets.TcpClient
  $c.Connect('127.0.0.1', 14279)
  $c.ReceiveTimeout = 7000
  $s = $c.GetStream()
  $s.Write($f,0,$f.Length); $s.Flush()
  $buf = New-Object byte[] 64
  $readInfo = "noresp"
  try { $n = $s.Read($buf,0,64); if ($n -gt 0) { $readInfo = "resp=${n}:" + (($buf[0..($n-1)] | ForEach-Object { $_.ToString('X2') }) -join '') } } catch {
    if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { $readInfo = "KEEP-TIMEOUT" } else { $readInfo = "read-aborted" }
  }
  $c.Close()
  $line = "$(Get-Date -Format HH:mm:ss) cmd=0x$($cmd.ToString('x')) $readInfo"
  Write-Host $line
  [IO.File]::AppendAllText($logf, "$line`r`n")
  Start-Sleep -Seconds 3
}
echo "INJECT_0D_DONE"
