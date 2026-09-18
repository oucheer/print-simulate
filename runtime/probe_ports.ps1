# compare test: connect guest RAWPRINT 9100 vs LPD-mapped 14279, see behavior
$m = [byte[]](0x0a,0x00,0x11,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x03,0xe8,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00)
foreach ($port in @(9100, 14279)) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $port)
    $c.ReceiveTimeout = 8000
    $s = $c.GetStream()
    $s.Write($m,0,$m.Length); $s.Flush()
    $buf = New-Object byte[] 64
    try { $n = $s.Read($buf,0,64); if ($n -gt 0) { "port=$port resp=${n}:$((($buf[0..($n-1)]) | ForEach-Object {$_.ToString('X2')}) -join '')" } else { "port=$port noresp(0)" } } catch {
      if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { "port=$port read-timeout" } else { "port=$port read-aborted:$($_.Exception.Message.Substring(0,[Math]::Min(60,$_.Exception.Message.Length)))" }
    }
    $c.Close()
  } catch { "port=$port connect-fail:$($_.Exception.Message.Substring(0,[Math]::Min(60,$_.Exception.Message.Length)))" }
}
