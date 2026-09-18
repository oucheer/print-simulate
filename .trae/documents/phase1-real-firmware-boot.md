# Phase 1 计划：让真实 mfp.afx 首次真实运行（Windows 原生 QEMU 系统仿真）

> 依据：[RK3588_Printer_Firmware_Simulation_Project_Summary.md](file:///d:/Apps/codex/files/simulate/RK3588_Printer_Firmware_Simulation_Project_Summary.md) 第 14.2、19、20、25 节。
> 第一阶段成功标准：`mfp.afx → main() → hal_prolog() → pi_hal_init()`；即使第一次失败，也把失败点记录为「真实依赖清单」。
> 用户已明确决定：**不安装 WSL**。因此唯一执行路线为 Windows 原生 QEMU 系统仿真。

---

## 1. 摘要

使用已下载的 `tools/qemu-native/qemu-system-aarch64.exe`（system-mode，唯一可用）：

```text
Windows PC
  ↓
qemu-system-aarch64.exe（QEMU virt 机型）
  ↓
ARM64 Linux 内核（优先真实 kernel.img 解包，失败则通用内核）
  ↓
真实 rootfs.ext4（挂载为根文件系统）
  ↓
init=/bin/sh 直接进 shell（绕过 Buildroot init 干扰）
  ↓
真实 mfp.afx 运行 → 记录第一个真实错误 → 最小 Virtualize → 再运行
```

循环推进至 `pi_hal_init()`，产出首次真实运行报告与真实依赖清单。

---

## 2. 当前状态分析（已实证）

### 2.1 已具备

| 资产 | 位置 | 说明 |
|---|---|---|
| 真实 rootfs.ext4 | `runtime/unpacked/rkaf/rootfs.ext4`（722MB） | 完整 Buildroot，merged-usr |
| 真实 mfp.afx | rootfs 内 `/usr/bin/mfp.afx`（AArch64 ELF64，未 strip，带 DWARF） | 与根目录 `mfp.afx` SHA-256 一致 |
| 全部 19 个动态依赖 | rootfs 内 `usr/lib/`（`/lib`、`/bin` 为 symlink → `usr/`） | 已逐一确认：`ld-linux-aarch64.so.1`、`libc.so.6`、`libhal.so`、`libstdc++.so.6`、`libcommon.so`、`libevent_mgr.so`、`libosal.so`、`libsqlite3mc.so.0`、`libssl.so.3`、`libcrypto.so.3`、`libcjson.so.1`、`libparser_ips.so`、`libm.so.6`、`libz.so.1`、`libusb-1.0.so.0`、`libcurl.so.4`、`libnvram.so`、`libipm.so`、`libptencryption.so`、`libplog.so` |
| 真实内核（未解包） | `runtime/unpacked/rkaf/boot_extracted/kernel.img`（40MB，Rockchip boot 格式，首字节 `MZ@`） | 待剥离 boot 头提取真实 Image |
| initramfs（未解包） | `runtime/unpacked/rkaf/boot_extracted/ramdisk.img` | 备选 |
| Windows 原生 QEMU | `tools/qemu-native/qemu-system-aarch64.exe` + 依赖 DLL | 已确认可用，无 user-mode |
| PoC 解析代码 | `printer-sim-poc/ext4_read.py`、`poc.py` | 可复用 |
| HAL 虚拟化证据 | `libhal.so` 导出 `pi_hal_virt_*`；`hal_module_config.json` 有 `virtual_platform/qemu_platform`、`pwm→virtual`、`rtc→/dev/rtc0` | 真实固件自带虚拟化边界 |

### 2.2 阻碍（已实证 / 用户决定）

1. Windows 无 `qemu-aarch64.exe`（user-mode 不支持 Windows）→ 必须 system-mode。
2. **用户决定不安装 WSL** → 排除 WSL2 路线。
3. 真实 RK3588 厂商内核能否在 QEMU `virt` 机型启动未验证（可能需要 `virtio`/PCIe 驱动、`CONFIG_ARM64_GENERIC_DTB` 等）→ 计划内含回退：通用 ARM64 内核（需联网下载，用户授权）。
4. rootfs 的 `/lib`、`/bin` 是 symlink（merged-usr）→ 挂载时直接以 rootfs 为 `/`，天然保留语义，无需处理。

---

## 3. 实施步骤（唯一主路线：Windows 原生 QEMU 系统仿真）

### Step 0：QEMU 预检

```powershell
& "d:\Apps\codex\files\simulate\tools\qemu-native\qemu-system-aarch64.exe" --version
```
- 验收：输出 QEMU 版本号（确认 DLL 依赖完整、可运行）。

### Step 1：解包真实内核（Python 脚本，纯本地）

Rockchip boot.img 头格式（已确认 `kernel.img` 以 `MZ@` 起始）：
- offset 0：8 字节魔数 `MZ@` 头
- offset 8：4 字节 kernel 实际大小（小端）
- offset 12：4 字节 kernel 对齐大小
- offset 16：4 字节 kernel 加载地址
- offset 20：4 字节 kernel 入口地址
- offset 24：4 字节 resource 偏移
- offset 28：4 字节 resource 大小
- offset 32：4 字节 ramdisk 偏移
- offset 36：4 字节 ramdisk 大小
- offset 40~：kernel 数据

新建 `tools/unpack_bootimg.py`：
1. 解析头，切出 kernel 段、resource 段、ramdisk 段。
2. kernel 段用 ARM64 Image magic（offset 0x38 处小端 `0x644d5241` = `ARM\x64`）校验。
3. 若 kernel 为 gzip（`1F 8B`）或 LZ4（`02 21 4C 18`）压缩，解压还原。
4. 输出：`runtime/unpacked/rkaf/boot_extracted/kernel.Image`（纯内核）、`ramdisk.cpio.gz`、`resource.dtb`。

- 验收：`kernel.Image` 生成且通过 ARM64 magic 校验；脚本同时输出解包元数据 JSON。

### Step 2：内核能力预判（静态检查）

- 用 `strings`/Grep 检查 `kernel.Image` 中是否含 virtio 相关符号：`virtio_blk`、`virtio_net`、`virtio_console`、`CONFIG_ARM64` 等。
- 检查是否支持 QEMU 需要的设备驱动（`pl011` 串口 = `AMBA_PL011` / `8250`）。
- 注意：vendor 内核配置往往裁剪，静态检查仅作参考，最终以试跑为准。
- 验收：记录内核关键配置倾向（支持/不支持），不阻塞后续步骤。

### Step 3：第一次 QEMU 启动（真实内核）

```powershell
& "d:\Apps\codex\files\simulate\tools\qemu-native\qemu-system-aarch64.exe" `
  -M virt -cpu cortex-a76 -m 2G -smp 2 `
  -kernel "runtime\unpacked\rkaf\boot_extracted\kernel.Image" `
  -drive file="runtime\unpacked\rkaf\rootfs.ext4",format=raw,if=virtio `
  -append "root=/dev/vda rw init=/bin/sh console=ttyAMA0" `
  -nographic `
  -serial mon:stdio
```
- 说明：
  - `init=/bin/sh`：跳过 Buildroot init/rcS，避免卡在 RK 专用设备初始化，直接进 shell。
  - `-drive if=virtio` + `root=/dev/vda`：rootfs.ext4 直接作根盘。
  - `-nographic`：无窗口，串口走当前终端。
- 若 `-cpu cortex-a76` 不支持（老版本 QEMU），回退 `-cpu max` 或 `cortex-a72`。
- 验收：串口输出内核启动日志；若能进 `#` shell 即重大成功；若 panic/无输出，记录日志进 `runtime/qemu-boot-02.log` 并进入 Step 4 回退。
- 输出重定向：PowerShell 中先写日志文件再交互（用 `-serial file:runtime/qemu-serial-01.log` 与 `-nographic` 二选一策略，见实现时确定）。

### Step 4：真实内核启动失败 → 通用 ARM64 内核（需联网授权）

仅在 Step 3 无法进入 shell 时启用：
1. 下载发行版通用 ARM64 内核（如 Debian `linux-image-arm64` 的 vmlinuz 或 ArchLinuxARM），目标 `tools/kernel/`。
2. 使用相同 QEMU 命令，换 `-kernel <通用内核>`。
3. 若通用内核需要 initramfs 才能挂 root，用 ramdisk.img（Step 1 解包）或最小 busybox initramfs 引导，cmdline 加 `root=/dev/vda`。
- 验收：进入 shell 或产生明确的第一个失败证据。
- 记录：在报告中注明内核来源（真实 vs 通用）及其对结论的影响。

### Step 5：进 shell 后准备运行环境（guest 内）

```sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev    # 或手动 mknod 关键节点
echo /proc/cmdline                 # virtual_platform 模块读取项
ls /dev
```
- 验收：`/proc`、`/sys`、`/dev` 可访问；记录缺失的设备节点。

### Step 6：第一次真实运行 mfp.afx（预期失败，记录证据）

```sh
cd /
/usr/bin/mfp.afx 2>&1 | tee /first-run.log
echo "exit=$?"
```
- 若 rootfs 无 tee，用 `> /first-run.log 2>&1`。
- 无 strace 时改用下列手段定位：
  - QEMU 侧：`-d` 日志（过于底层，仅作最后手段）。
  - 需要 syscall 级证据时：从 Windows 侧拷贝静态编译的 aarch64 `strace` 进 rootfs（需联网下载，用户授权；rootfs 挂载为 rw 时直接写 `/`）。
- 验收：产出 `runtime/first-run.log`（含 mfp.afx 输出与退出码）。

### Step 7：建立真实依赖清单并逐项最小 Virtualize

按 Summary §20 循环：

```text
第一个真实错误 → 定位缺失依赖 → 最小 stub → 再次运行
```

第一波预期（来自已确认配置）：`/proc/cmdline`（virtual_platform）、`/dev/rtc0`（rtc 模块）、其他 `/dev` 字符设备、共享内存、daemon 缺失。
处理原则（最小化，不预建几十种硬件）：
- `/dev` 节点：`mknod` 按 libhal 期望的主次号创建（参考 rtc 主 254 等，具体以运行时报错为准）。
- `/proc`、`/sys` 缺失项：guest 内 `mkdir`/`echo` 伪造最小内容（如 `/proc/cmdline` 写入 `qemu_platform` 相关 cmdline）。
- 每个处理项记录：错误原文 → 缺失项 → 处理方式 → 验证结果，追加进 `runtime/dependency-log.md`。
- 验收：`pi_hal_init()` 前的失败全部有明确根因与处理记录。

### Step 8：推进到 pi_hal_init() 并采集 HAL 调用序列

- 对照 `libhal.so` 的 `pi_hal_*` 导出（Windows 侧 `nm -D` 或 WSL/工具链），确认 mfp.afx 实际调用链。
- 记录：启动链到达层（loader → main → hal_prolog → pi_hal_init → 后续）与下一个失败点。
- 验收：产出 `runtime/hal-call-trace.md`。

### Step 9：产出 Phase 1 报告

`runtime/phase1-report.md`，包含：
1. 运行环境（QEMU 版本、机型、内核来源：真实/通用）
2. QEMU 启动日志摘要（Step 3/4）
3. `first-run.log` 分析（mfp.afx 输出、退出码）
4. 真实依赖清单（Step 7 完整记录）
5. 启动链进展与下一堵墙
6. 下一阶段建议（Phase 2 Virtual HAL 首批接口清单：`pi_hal_virt_*`、`pi_hal_rtc_*` 等）

---

## 4. 假设与决策记录

| # | 假设/决策 | 依据 |
|---|---|---|
| 1 | 不安装 WSL，唯一路线为 Windows 原生 system-mode | 用户明确决定 |
| 2 | 优先尝试真实 kernel.img 解包内核 | Summary §14.2 优先真实资产 |
| 3 | 真实内核失败 → 通用 ARM64 内核（联网） | 需要用户授权下载 |
| 4 | 第一次运行必然失败，失败即成果 | Summary §20 |
| 5 | `init=/bin/sh` 绕过 Buildroot init | 避免 RK 专用 init 干扰，聚焦 mfp.afx |
| 6 | 不提前虚拟化几十种硬件，只解决当前错误 | Summary §25 第五步 |
| 7 | 不修改真实固件/rootfs 内容 | rootfs 以只读挂载优先；仅当确需写 stub 时以副本写入 |
| 8 | 静态编译 aarch64 strace 仅在需要 syscall 级证据时引入 | 需联网授权 |

---

## 5. 验证方式

1. **Step 1**：`kernel.Image` 通过 ARM64 magic 校验。
2. **Step 3/4**：串口日志证明内核启动到 shell，或产生明确的第一个失败证据。
3. **Step 6**：`runtime/first-run.log` 非空且可解释。
4. **Step 8**：`hal-call-trace.md` 标注启动链到达层与下一失败点。
5. **最终验收**：满足任一即完成：
   - 达成 `mfp.afx → main() → hal_prolog() → pi_hal_init()`（Summary §19）；
   - 或暴露第一个无法绕过的真实依赖且已有 Virtualize 方案（Summary §20）。
6. **回归**：现有 `printer-sim-poc/poc.py demo`（3 passed）不受影响；本次不改动 `printer-sim-poc/`。

---

## 6. 交付物清单

- `tools/unpack_bootimg.py` — Rockchip boot.img 解包脚本（含元数据 JSON 输出）
- `runtime/unpacked/rkaf/boot_extracted/kernel.Image`（及 `ramdisk`、`resource.dtb` 若有）
- `runtime/qemu-boot-02.log`、`runtime/qemu-serial-01.log` — QEMU 启动/串口日志
- `runtime/first-run.log` — mfp.afx 首次真实运行输出
- `runtime/dependency-log.md` — 真实依赖清单（错误→缺失→处理→验证）
- `runtime/hal-call-trace.md` — 启动链 + HAL 接口调用序列
- `runtime/phase1-report.md` — Phase 1 首次真实运行报告
