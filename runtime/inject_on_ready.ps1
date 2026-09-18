# inject_on_ready.ps1 - watch QEMU serial log, add LPD hostfwd, inject PWG job on READY
# Usage: powershell -ExecutionPolicy Bypass -File runtime/inject_on_ready.ps1 -LogFile runtime/qemu-boot-s6i.log
# Why: guest OOM-kills mfp.afx ~30min after READY; manual polling misses the window.
# This watcher acts within seconds of "READY FOR INJECT" appearing in the serial log.
param(
    [string]$LogFile   = "runtime/qemu-boot-s6i.log",
    [int]$MonitorPort  = 14545,
    [string]$Pwg       = "runtime/pwg-job-1page.pwg",
    [string]$OutFile   = "runtime/inject_on_ready.txt",
    [int]$HostPort     = 14279,
    [int]$TimeoutSec   = 3600
)

$ErrorActionPreference = "Continue"
$root    = Split-Path -Parent $PSScriptRoot
$logAbs  = Join-Path $root $LogFile
$outAbs  = Join-Path $root $OutFile

"=== inject_on_ready start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') log=$LogFile monitor=$MonitorPort fwd=$HostPort ===" |
    Set-Content -Path $outAbs -Encoding UTF8

function Log([string]$m) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $m"
    Write-Host $line
    Add-Content -Path $outAbs -Value $line -Encoding UTF8
}

# QEMU holds the serial log open; ReadAllText throws "used by another process".
# Open with FileShare.ReadWrite so we can read while QEMU keeps writing.
function ReadLogSafe([string]$p) {
    for ($t = 0; $t -lt 6; $t++) {
        try {
            $fs = New-Object IO.FileStream($p, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            $sr = New-Object IO.StreamReader($fs)
            $txt = $sr.ReadToEnd()
            $sr.Close(); $fs.Close()
            return $txt
        } catch { Start-Sleep -Milliseconds 400 }
    }
    return $null
}

# QEMU monitor 单次命令（hostfwd_add 等）
function Send-Monitor([string]$cmd) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $c.Connect('127.0.0.1', $MonitorPort)
        $s = $c.GetStream()
        $w = New-Object System.IO.StreamWriter($s)
        $w.AutoFlush = $true
        $w.Write("$cmd`n")
        Start-Sleep -Milliseconds 800
        $buf = New-Object byte[] 4096
        $resp = ''
        while ($s.DataAvailable) {
            $n = $s.Read($buf, 0, 4096)
            $resp += [Text.Encoding]::ASCII.GetString($buf, 0, $n)
        }
        $c.Close()
        return ($resp -replace "`r`n", ' ')
    } catch {
        return "monitor error: $_"
    }
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ports = @(); $fwd = $false; $injected = $false

while ((Get-Date) -lt $deadline) {
    if (Test-Path $logAbs) {
        $txt = ReadLogSafe $logAbs

        if ($txt) {
            if ($ports.Count -eq 0) {
                # 优先解析全部 mfp 拥有的 LISTEN 端口（十六进制列表）
                $m = [regex]::Match($txt, 'SIMBOOT_LPD_PORTS= *((?:[0-9A-Fa-f]{1,4} ?)+)')
                if ($m.Success) {
                    $hexlist = $m.Groups[1].Value.Trim()
                    $ports = @($hexlist -split '\s+' | Where-Object { $_ } |
                        ForEach-Object { [Convert]::ToInt32($_, 16) } | Select-Object -Unique)
                    Log "LPD ports hex='$hexlist' dec=$($ports -join ',')"
                } elseif ($txt -match 'SIMBOOT_LPD_PORT=(\d+)') {
                    $ports = @([int]$Matches[1])
                    Log "LPD single port=$($ports[0])"
                }
            }

            if ($ports.Count -gt 0 -and -not $fwd) {
                for ($i = 0; $i -lt $ports.Count; $i++) {
                    $hp = $HostPort + $i
                    $resp = Send-Monitor "hostfwd_add tcp::$hp-:$($ports[$i])"
                    Log "hostfwd_add tcp::$hp-:$($ports[$i]) resp='$resp'"
                }
                $fwd = $true
            }

            if ($fwd -and -not $injected -and ($txt -match 'READY FOR INJECT')) {
                Log "READY FOR INJECT detected -> injecting PWG"
                Start-Sleep -Seconds 2
                $pwgAbs = Join-Path $root $Pwg
                $py = (Get-Command python).Source
                $send = Join-Path $root 'runtime\send_print_job.py'
                for ($i = 0; $i -lt $ports.Count -and -not $injected; $i++) {
                    $hp = $HostPort + $i
                    for ($a = 1; $a -le 3; $a++) {
                        Log "inject attempt port=$($ports[$i]) hostport=$hp try=$a"
                        $o = & $py $send 'lpd' '127.0.0.1' "$hp" $pwgAbs 2>&1 | Out-String
                        Log "attempt $a output:`n$($o.Trim())"
                        if ($o -match 'LPD job sent OK') { $injected = $true; break }
                        Start-Sleep -Seconds 4
                    }
                }
                break
            }
        }
    }
    Start-Sleep -Seconds 3
}

if ($injected) { Log "SUCCESS: job injected" }
else { Log "FAIL: ports=$($ports -join ',') fwd=$fwd injected=$injected" }
Log "done"
