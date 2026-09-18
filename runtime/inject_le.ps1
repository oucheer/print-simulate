# inject PEDK IBC frame in LE layout, cmd param
param([int]$Cmd = 0x578, [int]$Sub = 3, [int]$Rounds = 200)
$logf = "d:\Apps\codex\files\simulate\runtime\inject_hits.txt"
# frame: [type=0x0a][len(2 BE)] [0][cmd(4 LE)][w6=sub(4 LE)][w1=0(4)][w2=0(4)][payload 0x11 bytes]
function Make-Frame([int]$cmd, [int]$sub) {
  $payload = New-Object byte[] 0x11  # 17 zero bytes
  $body = New-Object byte[] 0  # build via list
  $lst = [System.Collections.Generic.List[byte]]::new()
  $lst.Add(0x00)
  $lst.AddRange([BitConverter]::GetBytes([int32]$cmd))     # cmd LE
  $lst.AddRange([BitConverter]::GetBytes([int32]$sub))     # w6 LE
  $lst.AddRange([BitConverter]::GetBytes([int32]0))        # w1
  $lst.AddRange([BitConverter]::GetBytes([int32]0))        # w2
  $lst.AddRange($payload)
  $body = $lst.ToArray()
  $len = $body.Length
  $head = [byte[]](0x0a, 0x00, ($len -shr 8) -band 0xff, $len -band 0xff)
  # head is 4 bytes? no: [type][len hi][len lo] = 3 bytes
  $head = [byte[]](0x0a, (($len -shr 8) -band 0xff), ($len -band 0xff))
  $out = New-Object byte[] ($head.Length + $body.Length)
  [Array]::Copy($head, 0, $out, 0, $head.Length)
  [Array]::Copy($body, 0, $out, $head.Length, $body.Length)
  return $out
}
$f1 = Make-Frame $Cmd $Sub
$f2 = Make-Frame 0x3e8 0
[IO.File]::WriteAllText($logf, "start $(Get-Date -Format HH:mm:ss) cmd=0x$($Cmd.ToString('x')) sub=$Sub frame_len=$($f1.Length)`r`n")
for ($i=0; $i -lt $Rounds; $i++) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', 14279)
    $c.ReceiveTimeout = 6000
    $s = $c.GetStream()
    $s.Write($f1,0,$f1.Length); $s.Flush()
    Start-Sleep -Milliseconds 300
    $s.Write($f2,0,$f2.Length); $s.Flush()
    $buf = New-Object byte[] 64
    $readInfo = "noresp"
    try { $n = $s.Read($buf,0,64); if ($n -gt 0) { $readInfo = "resp=${n}:" + (($buf[0..($n-1)] | ForEach-Object { $_.ToString('X2') }) -join '') } } catch {
      if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { $readInfo = "read-timeout" } else { $readInfo = "read-aborted" }
    }
    $c.Close()
    $line = "hit $i at $(Get-Date -Format HH:mm:ss) wrote=$($f1.Length+$f2.Length) $readInfo"
    Write-Host $line
    [IO.File]::AppendAllText($logf, "$line`r`n")
    Start-Sleep -Seconds 8
  } catch { Start-Sleep -Seconds 5 }
}
