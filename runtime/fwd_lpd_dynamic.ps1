# fwd_lpd_dynamic.ps1 - wait for guest LPD port report, add hostfwd via QEMU HMP monitor
# Usage: powershell -File runtime/fwd_lpd_dynamic.ps1 -LogFile runtime/qemu-boot-99.log
param(
    [string]$LogFile = "runtime/qemu-boot.log",
    [int]$MonitorPort = 14545
)
$root = Split-Path -Parent $PSScriptRoot
$logAbs = Join-Path $root $LogFile
$portRe = [regex]"SIMBOOT_LPD_PORT=(\d+)"

Write-Host "== waiting for LPD port report: $logAbs =="
$port = $null
for ($i = 0; $i -lt 300; $i++) {
    if (Test-Path $logAbs) {
        $tail = Get-Content $logAbs -Tail 40 -ErrorAction SilentlyContinue
        foreach ($line in $tail) {
            $m = $portRe.Match($line)
            if ($m.Success) { $port = [int]$m.Groups[1].Value; break }
        }
    }
    if ($port) { break }
    Start-Sleep -Seconds 2
}
if (-not $port) { Write-Host "FAIL: no SIMBOOT_LPD_PORT found"; exit 1 }
Write-Host "== LPD port = $port =="

# connect QEMU HMP monitor and send hostfwd_add (non-blocking read; monitor keeps conn open)
try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect('127.0.0.1', $MonitorPort)
    $s = $c.GetStream()
    $w = New-Object System.IO.StreamWriter($s)
    $w.AutoFlush = $true
    $w.Write("hostfwd_add tcp::14279-:$port`n")
    Start-Sleep -Milliseconds 600
    $resp = ""
    $buf = New-Object byte[] 4096
    while ($s.DataAvailable) {
        $n = $s.Read($buf, 0, 4096)
        $resp += [Text.Encoding]::ASCII.GetString($buf, 0, $n)
    }
    $c.Close()
    Write-Host "== hostfwd_add resp: '$resp' =="
    [IO.File]::AppendAllText("$root\runtime\fwd_hits.txt", "$(Get-Date -Format HH:mm:ss) port=$port resp=$resp`r`n")
} catch {
    Write-Host "FAIL monitor: $_"
    exit 1
}
Write-Host "DONE"
