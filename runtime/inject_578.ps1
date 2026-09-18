# inject PEDK IBC frame: cmd=0x0e + w6=0x578 + payload[0..4]=subcmd(3)
# 目标：0x74fb0c(0x578 checker) -> 0x74f95c(sub dispatch) -> 0x73b30c(panel event)
param([int]$Sub = 3, [int]$Rounds = 10, [int]$Port = 14279)
$logf = "d:\Apps\codex\files\simulate\runtime\inject_578_hits.txt"
function Make-Frame578([int]$sub) {
  $payload = New-Object byte[] 0x11  # 17 bytes
  $b = [BitConverter]::GetBytes([int32]$sub)
  for ($k=0; $k -lt 4; $k++) { $payload[$k] = $b[$k] }   # payload[0..4] = sub LE
  $lst = [System.Collections.Generic.List[byte]]::new()
  $lst.Add(0x00)
  $lst.AddRange([BitConverter]::GetBytes([int32]0x0e))    # cmd = 0x0e
  $lst.AddRange([BitConverter]::GetBytes([int32]0x578))   # w6 = 0x578
  $lst.AddRange([BitConverter]::GetBytes([int32]0))       # w1
  $lst.AddRange([BitConverter]::GetBytes([int32]0))       # w2
  $lst.AddRange($payload)
  $body = $lst.ToArray()
  $len = $body.Length
  $head = [byte[]](0x0a, (($len -shr 8) -band 0xff), ($len -band 0xff))
  $out = New-Object byte[] ($head.Length + $body.Length)
  [Array]::Copy($head, 0, $out, 0, $head.Length)
  [Array]::Copy($body, 0, $out, $head.Length, $body.Length)
  return $out
}
$f1 = Make-Frame578 $Sub
[IO.File]::WriteAllText($logf, "start $(Get-Date -Format HH:mm:ss) cmd=0xe w6=0x578 sub=$Sub frame_len=$($f1.Length)`r`n")
for ($i=0; $i -lt $Rounds; $i++) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $Port)
    $c.ReceiveTimeout = 4000
    $s = $c.GetStream()
    $s.Write($f1,0,$f1.Length); $s.Flush()
    $buf = New-Object byte[] 64
    $readInfo = "noresp"
    try { $n = $s.Read($buf,0,64); if ($n -gt 0) { $readInfo = "resp=${n}:" + (($buf[0..($n-1)] | ForEach-Object { $_.ToString('X2') }) -join '') } } catch {
      if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { $readInfo = "read-timeout" } else { $readInfo = "read-aborted" }
    }
    $c.Close()
    $line = "hit $i at $(Get-Date -Format HH:mm:ss) wrote=$($f1.Length) $readInfo"
    Write-Host $line
    [IO.File]::AppendAllText($logf, "$line`r`n")
    Start-Sleep -Seconds 6
  } catch { Start-Sleep -Seconds 5 }
}
