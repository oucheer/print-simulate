# enumerate candidate cmd values with correct LE frame; matched cmd keeps conn (timeout) vs RST
$logf = "d:\Apps\codex\files\simulate\runtime\probe_cmd.txt"
$cands = @(0x578, 0x3e8, 0x0e, 0x0a, 0x00, 0x01, 0x02, 0x03, 0x05, 0x0b, 0x0c, 0x0d, 0x10, 0x11, 0x100, 0x200, 0x57800, 0x3e800, 0x0e0000, 0x0a0000)
function Make-Frame([int]$cmd) {
  $body = New-Object byte[] 17
  $b = [BitConverter]::GetBytes([int32]$cmd)
  $body[1]=$b[0]; $body[2]=$b[1]; $body[3]=$b[2]; $body[4]=$b[3]
  # w6 (sub) = 3
  $b = [BitConverter]::GetBytes([int32]3)
  $body[5]=$b[0]; $body[6]=$b[1]; $body[7]=$b[2]; $body[8]=$b[3]
  $head = [byte[]](0x0a, 0x00, 0x11)
  $out = New-Object byte[] 20
  [Array]::Copy($head,0,$out,0,3)
  [Array]::Copy($body,0,$out,3,17)
  return $out
}
[IO.File]::WriteAllText($logf, "probe_cmd start $(Get-Date -Format HH:mm:ss)`r`n")
foreach ($cmd in $cands) {
  try {
    $f = Make-Frame $cmd
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', 14279)
    $c.ReceiveTimeout = 5000
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
  } catch { $line = "$(Get-Date -Format HH:mm:ss) cmd=0x$($cmd.ToString('x')) connect-fail"; Write-Host $line; [IO.File]::AppendAllText($logf, "$line`r`n") }
  Start-Sleep -Milliseconds 500
}
echo "PROBE_CMD_DONE"
