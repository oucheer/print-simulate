# probe PEDK IBC frame variants: one connection per variant, see which survive
$logf = "d:\Apps\codex\files\simulate\runtime\probe_var.txt"
$variants = @(
    @{name="A_cmd578_sub3_28B"; data=@(0x0a,0x00,0x19,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x05,0x78,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x03,0x00,0x00,0x00,0x00)},
    @{name="B_12B_head";           data=@(0x00,0x00,0x00,0x0e,0x00,0x00,0x05,0x78,0x00,0x00,0x00,0x03)},
    @{name="C_len16_sub3";         data=@(0x0a,0x00,0x10,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x05,0x78,0x00,0x00,0x00,0x03)},
    @{name="D_magic2B_len20";      data=@(0x0a,0x0a,0x14,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x05,0x78,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x03)},
    @{name="E_cmd3e8_20B";         data=@(0x0a,0x00,0x11,0x00,0x00,0x00,0x00,0x0e,0x00,0x00,0x03,0xe8,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00)},
    @{name="F_empty";              data=@()}
)
[IO.File]::WriteAllText($logf, "probe start $(Get-Date -Format HH:mm:ss)`r`n")
foreach ($v in $variants) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', 14279)
    $c.ReceiveTimeout = 6000
    $s = $c.GetStream()
    if ($v.data.Count -gt 0) { $s.Write([byte[]]$v.data,0,$v.data.Count); $s.Flush() }
    Start-Sleep -Milliseconds 400
    $buf = New-Object byte[] 64
    $readInfo = "noresp"
    try { $n = $s.Read($buf,0,64); if ($n -gt 0) { $readInfo = "resp=${n}:" + (($buf[0..($n-1)] | ForEach-Object { $_.ToString('X2') }) -join '') } } catch {
      if ($_.Exception.InnerException -and $_.Exception.InnerException.GetType().Name -eq 'SocketException' -and $_.Exception.InnerException.SocketErrorCode -eq 'TimedOut') { $readInfo = "read-timeout" } else { $readInfo = "read-aborted" }
    }
    $c.Close()
    $line = "$(Get-Date -Format HH:mm:ss) $($v.name) wrote=$($v.data.Count) $readInfo"
    Write-Host $line
    [IO.File]::AppendAllText($logf, "$line`r`n")
  } catch { $line = "$(Get-Date -Format HH:mm:ss) $($v.name) connect-fail"; Write-Host $line; [IO.File]::AppendAllText($logf, "$line`r`n") }
  Start-Sleep -Seconds 2
}
echo "PROBE_DONE"
