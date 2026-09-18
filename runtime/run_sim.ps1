# run_sim.ps1 - RK3588 printer firmware simulator launcher
# Usage: powershell -File runtime/run_sim.ps1 [-LogFile runtime/qemu-boot.log]
# Starts QEMU AArch64, mounts real rootfs via custom initramfs (SIMBOOT), runs real mfp.afx
param(
    [string]$LogFile = "runtime/qemu-boot-$(Get-Date -Format yyyyMMdd-HHmmss).log",
    [switch]$NoSnapshot   # omit -snapshot (writes real rootfs, use carefully)
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$qemu = Join-Path $root "tools/qemu-native/qemu-system-aarch64.exe"
$bios = Join-Path $root "tools/qemu-native/share/edk2-aarch64-code.fd"
$kernel = Join-Path $root "tools/kernel/linux-virt-x/boot/vmlinuz-virt"
$initrd = Join-Path $root "tools/kernel/initramfs-new.gz"
$rootfs = Join-Path $root "runtime/unpacked/rkaf/rootfs.ext4"

foreach ($f in @($qemu, $bios, $kernel, $initrd, $rootfs)) {
    if (-not (Test-Path $f)) { throw "missing file: $f" }
}

$logAbs = Join-Path $root $LogFile
Write-Host "== RK3588 Printer Firmware Simulator =="
Write-Host "QEMU   : $qemu"
Write-Host "Kernel : $kernel"
Write-Host "RootFS : $rootfs"
Write-Host "Serial -> $logAbs"

$snap = if ($NoSnapshot) { @() } else { @("-snapshot") }

# LPD port is dynamically allocated by firmware (50999/60245 seen), so 14279 is not
# fixed here; runtime/fwd_lpd_dynamic.ps1 adds hostfwd via QEMU monitor at runtime.
$netdevArg = "user,id=n1" +
    ",hostfwd=tcp::515-:515,hostfwd=tcp::631-:631,hostfwd=tcp::9100-:9100" +
    ",hostfwd=tcp::9120-:9120,hostfwd=tcp::9130-:9130,hostfwd=tcp::9132-:9132"

# PowerShell 5.1 native-command arg passing mangles commas/spaces, so generate a
# .bat file and let cmd.exe interpret it (quotes keep every arg intact).
$snapArg = if ($NoSnapshot) { "" } else { "-snapshot" }
$batPath = Join-Path $PSScriptRoot "qemu_launch.bat"
$batLine = "@echo off`r`n" +
    "`"$qemu`" -M virt -cpu cortex-a76 -m 4G -smp 2 $snapArg" +
    " -bios `"$bios`"" +
    " -kernel `"$kernel`" -initrd `"$initrd`"" +
    " -drive `"file=$rootfs,format=raw,if=virtio,cache=unsafe`"" +
    " -device e1000,netdev=n1" +
    " -netdev `"$netdevArg`"" +
    " -append `"root=/dev/vda rw console=ttyAMA0`"" +
    " -serial `"file:$logAbs`" -display none -no-reboot" +
    " -monitor `"tcp:127.0.0.1:14545,server,nowait`""
[IO.File]::WriteAllText($batPath, $batLine, [Text.Encoding]::ASCII)
Write-Host "BAT: $batPath"
& $batPath
Write-Host "QEMU exited. serial log: $logAbs"
