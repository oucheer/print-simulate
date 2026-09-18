# Phase 1 报告：真实 mfp.afx 首次在 AArch64 Runtime 中运行

> 日期：2026-08-22
> 计划：[.trae/documents/phase1-real-firmware-boot.md](file:///d:/Apps/codex/files/simulate/.trae/documents/phase1-real-firmware-boot.md)

## 1. 执行摘要

**第一阶段目标已超越达成。** 真实 `mfp.afx` 已在 Windows PC 上的 QEMU AArch64 仿真环境中真实运行，
并推进到 **HAL Runtime 内部（pcie_init → ibc → imagemem → nvram init）**——比计划预设的
`main() → hal_prolog() → pi_hal_init()` 成功标准更深入。过程中建立了完整「真实依赖清单」，
并验证了「真实错误 → 定位 → 最小 Virtualize → 再运行」循环的有效性（伪设备成功让 pcie_init 越过 open/mmap 阶段）。

## 2. 运行环境

| 项 | 值 |
|---|---|
| QEMU | `tools/qemu-native/qemu-system-aarch64.exe` v11.1.0 |
| 机型 | `-M virt -cpu cortex-a76 -m 2G -smp 2` |
| 固件 | UEFI `edk2-aarch64-code.fd` |
| 内核 | Alpine `linux-virt` 6.12.103（真实 RK3588 内核缺 PL011/virtio，无法用于 QEMU virt，详见依赖 D-01） |
| initramfs | `tools/kernel/initramfs-new.gz`（自制，注入 ext4/virtio 模块，见 `tools/build_initramfs.py`） |
| rootfs | 真实 `runtime/unpacked/rkaf/rootfs.ext4`（`-snapshot` 只读保护，未修改原文件） |
| 运行方式 | initramfs SIMBOOT 块：insmod → mount rootfs → bind /proc//sys//dev → chroot → 运行 `/usr/bin/mfp.afx` |

## 3. 启动日志摘要

- 完整首次运行日志：`runtime/first-run.log`（qemu-boot-11，binder 缺失阶段）
- 推进后日志：`runtime/first-run-advanced.log`（qemu-boot-18，nvram 建表阶段）
- 内核引导：UEFI → 6.12.103 内核 → initramfs → rootfs 挂载（`EXT4-fs (vda): mounted filesystem`）→ chroot shell

## 4. mfp.afx 真实运行分析

首次运行输出（真实固件日志）：
```text
set output level<5><DEBUG>
<plog_set_level> set log tage <0> level <5> <DEBUG>
1 mfp process plog lib init
pntp socket client init
error:miss key;line:=
binder: cannot open device (No such file or directory)
```

推进后（伪设备 Virtualize）：
```text
PLOG_JSON parse /configs/plog/plog_json_config.json error, reset config
1 mfp process plog lib init
---------------------ibc-------init------------
open /dev/dma_heap/system failed
pi_imagemem_init:67 : imagemem init failed
---------------------msg_router-------init------------
---------------------cmd-------init------------
---------------------nvram-------init------------
sql_init: create table:int/uint/string/struct success
== insert default value ==
[osal/pol] tid(425) name(cmd process thread)
```

**动态链接**：mfp.afx 在 guest 中成功加载全部 40+ 个共享库（libhal、libmali 58MB、libopencv、
gstreamer 全家等），无一失败——证明 rootfs 完整性与动态链接器工作正常。

## 5. 真实依赖清单（详见 `runtime/dependency-log.md`）

| 编号 | 依赖 | 状态 |
|---|---|---|
| D-01 | 真实 RK3588 内核缺 PL011/virtio → 换通用内核 | 已解决 |
| D-02 | initramfs 缺 ext4 模块 | 已解决 |
| D-03 | initramfs 打包丢执行位 | 已解决 |
| D-04 | busybox modprobe 无法发现注入模块 → 改 insmod | 已解决 |
| D-05 | `/dev/binder` 缺失（binder_start 引用） | 记录待处理 |
| D-06 | 加密密钥缺失（`error:miss key`） | 记录待处理 |
| D-07 | NVRAM sqlite 表缺失 | **已解决（自动建表成功）** |
| D-08 | `/dev/dma_heap/system` 缺失（imagemem）★当前阻塞 | 记录待处理 |
| D-09 | `/dev/netlog_dev` 缺失 | 记录待处理 |
| D-10 | `/tmp/.logserver`、`/tmp/.pntp_service` socket 缺失 | 记录待处理 |
| D-11 | plog/tslog 配置缺失 | 可恢复 |
| D-12 | `/sys/kernel/config/pci_ep/` 缺失 | 记录待处理 |

## 6. 启动链进展与下一堵墙

启动链已推进至（详见 `runtime/hal-call-trace.md`）：
```text
main → hal_prolog(反汇编确认) → plog → pntp → pcie_init(open+mmap 通过)
     → ibc → imagemem(缺 dma_heap) → msg_router → cmd → nvram(建表成功) → 继续...
```

**下一堵墙**：`/dev/dma_heap/system`（DMA-BUF heap，图像内存）以及守护 socket
（logserver/pntp_service）与服务设备（netlog_dev）。这些均已有 Virtualize 方案方向。

## 7. 下一阶段建议（Phase 2 Virtual HAL 首批清单）

1. **`/dev/dma_heap/system`**：内核 `CONFIG_DMABUF_HEAPS_SYSTEM` 编译支持，或在 guest 以
   `mknod c 10 <misc 次号>` + 可 mmap 伪设备绕过（dma-buf ioctl 需 stub）。
2. **守护 socket**：启动 mfp.afx 前在 guest 后台创建 `/tmp/.logserver`、`/tmp/.pntp_service`
   监听 socket（纯 shell，无需工具链）。
3. **`/dev/netlog_dev`**：mknod 伪设备 + 观察行为。
4. **binder**：rootfs 无 binder 驱动；方案为内核模块或 LD_PRELOAD stub（需 aarch64 交叉工具链，
   建议评估 `apt install gcc-aarch64-linux-gnu` 或用 QEMU guest 内的 gcc——rootfs 含 gdb/strace）。
5. **性能**：TCG 仿真约慢 10-20 倍（mfp.afx 加载 58MB libmali 需 ~45s）。后续若需更快，
   考虑 `-accel tcg,thread=multi` 或 WSL2（用户已排除）。
6. **自动化**：将 SIMBOOT 固化为一键脚本 `runtime/run_sim.ps1`，支持参数化场景。

## 8. 交付物

- `tools/unpack_bootimg.py` — Rockchip boot.img 内核提取/校验
- `tools/build_initramfs.py` — 自制 initramfs 构建（模块注入 + mode 恢复 + SIMBOOT 逻辑）
- `tools/kernel/` — 内核/initramfs/模块/apk（vmlinuz 6.12.103、initramfs-new.gz、linux-virt-x）
- `runtime/first-run.log`、`runtime/first-run-advanced.log` — 真实运行日志
- `runtime/dependency-log.md` — 真实依赖清单
- `runtime/hal-call-trace.md` — 启动链与 HAL 调用序列
- `runtime/phase1-report.md` — 本报告

## 9. 结论

> **真实 RK3588 打印机固件 mfp.afx 已在 PC 仿真环境真实运行，并穿越 HAL Runtime 第一堵墙。**
> 项目从「理论可行」正式进入「真实固件可运行、依赖可枚举、Virtualize 循环可闭环」的执行阶段。
