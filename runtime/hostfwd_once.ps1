# one-shot: send hostfwd_add to QEMU HMP monitor (non-blocking read)
param(
    [int]$GuestPort = 54049,
    [int]$HostPort = 14279,
    [int]$MonitorPort = 14545
)
try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $MonitorPort)
    $s = $c.GetStream()
    $w = New-Object System.IO.StreamWriter($s)
    $w.AutoFlush = $true
    $w.Write("hostfwd_add tcp::$HostPort-:$GuestPort`n")
    Start-Sleep -Milliseconds 600
    $resp = ""
    $buf = New-Object byte[] 4096
    while ($s.DataAvailable) {
        $n = $s.Read($buf, 0, 4096)
        $resp += [Text.Encoding]::ASCII.GetString($buf, 0, $n)
    }
    $c.Close()
    $line = "$(Get-Date -Format HH:mm:ss) guest=$GuestPort host=$HostPort resp='$resp'"
    Write-Host $line
    [IO.File]::AppendAllText("d:\Apps\codex\files\simulate\runtime\fwd_hits.txt", "$line`r`n")
} catch {
    Write-Host "FAIL: $_"
}
