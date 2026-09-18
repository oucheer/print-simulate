# print-simulate · RK3588 打印机固件仿真验证

在 QEMU（aarch64）里启动**真实打印机固件**（真实 rootfs + 真实 `mfp.afx`），用虚拟外设逐步替代真实硬件，目标是构建一条**无硬件也能复现的完整打印闭环**（作业注入 → 解析 → 引擎 → 出图）。

模型：Pantum BM606ADN series（RK3588 主控 + 3700 副板 PCIe 架构）。

- 项目长期规划与已确认结论：[RK3588_Printer_Firmware_Simulation_Project_Summary.md](RK3588_Printer_Firmware_Simulation_Project_Summary.md)
- **下一步任务清单（换设备靠它继续）：[Task.md](Task.md)**
- 分阶段实施计划：[phase1-real-firmware-boot.md](.trae/documents/phase1-real-firmware-boot.md) · [phase2-print-closure-poc.md](.trae/documents/phase2-print-closure-poc.md)

---

## 1. 当前状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 固件结构分析（`update.img` → rootfs/内核/模块） | ✅ |
| Phase 1 | 真实 AArch64 固件在 QEMU 中启动，真实 `mfp.afx` 跑起来 | ✅ |
| Phase 2 Step 1 | Virtual HAL（`virtual_hal.so`）让 mfp 走完 HAL 层 | ✅ |
| Phase 2 Step 2 | 打印业务初始化到达 `print_info_status_init` 之后（POLL 解锁） | ✅ |
| Phase 2 Step 3 | PWG 打印作业经 LPD 进入真实 `mfp.afx` | ❌ **阻塞** |
| Phase 2 Step 4-6 | `engine-if.md` / `virtual_engine.py` / `virtual_printer.py` | ⏸ 待 Step 3 |

**Step 3 阻塞结论（已用运行时证据定案）**：真实固件的网络前端不是"宿主直连 LPD"，而是 **PCIe/IBC peer 代理**架构 —— 网络数据由副板经 PCIe 送进来。仿真下 peer 缺失，因此 `accept()` 能成功、但数据永远不会被投递到 LPD 处理函数。

---

## 2. 快速开始

### 2.1 恢复环境（换设备必读）

仓库只跟踪源码/脚本/日志/分析产物；**大体积二进制走 GitHub Release 资产包**（`.gitignore` 已排除），需先解压回位：

```
Release: v0.1-bundles
  print-sim-tools-qemu.7z      → tools/qemu-native/
  print-sim-tools-kernel.7z    → tools/kernel/
  print-sim-tools-toolchain.7z → tools/toolchain/
  print-sim-firmware.7z        → runtime/unpacked/  (+ 根目录 mfp.afx)
```

```powershell
git clone https://github.com/oucheer/print-simulate.git
cd print-simulate
gh release download v0.1-bundles     # 或网页下载
# 解压上面 4 个 7z 到对应目录后，确认以下文件存在：
#   tools/qemu-native/qemu-system-aarch64.exe
#   tools/qemu-native/share/edk2-aarch64-code.fd
#   tools/kernel/linux-virt-x/boot/vmlinuz-virt
#   runtime/unpacked/rkaf/rootfs.ext4
```

### 2.2 启动两个宿主服务（**必须先起**）

guest 启动过程要拉工具链、并回传证据，这两条不通会让 guest 卡在重试：

```powershell
# 8001：证据落盘服务（guest POST 上传 → runtime/collected/<时间戳>-<名字>）
python tools\upload_server.py

# 8000：静态文件服务（guest 从这里拉 musl 工具链 / virtual_hal.c / pwg-job-1page.pwg）
python -m http.server 8000 --directory tools\toolchain
```

### 2.3 启动仿真 + 自动注入

```powershell
# 终端 1：启动 QEMU（串口日志写入 runtime/qemu-boot-<自定义>.log）
powershell -ExecutionPolicy Bypass -File runtime\run_sim.ps1 -LogFile runtime/qemu-boot-s7.log

# 终端 2：看守串口日志，出现 READY FOR INJECT 后自动加 hostfwd 并投递 PWG 作业
powershell -ExecutionPolicy Bypass -File runtime\inject_on_ready.ps1 -LogFile runtime/qemu-boot-s7.log
```

LPD 端口由固件**动态分配**，所以不能写死在 `-netdev hostfwd` 里：payload 会把端口以 `SIMBOOT_LPD_PORTS=<hex 列表>` 打到串口，watcher 读出来后用 QEMU monitor（`127.0.0.1:14545`）执行 `hostfwd_add`。

### 2.4 一次成功运行应看到的关键信号

```
SIMBOOT_PREP_DONE
VHAL_WGET_TC_RC=0 / VHAL_GCC_RC=0 / VHAL: done
MFP_PID=<pid>
HOLD_ARMED wait=Nx3s / HOLD_OK=1
POLL <n>: passed print_info_status_init (N=102)   ← 业务初始化解锁
POLL_END N=102 tries=0
LPD_SOCK_READY k=1 / SIMBOOT_LPD_PORTS=<hex>
TRACE1_ARMED wait=Nx2s
READY FOR INJECT                                  ← 注入窗口打开
--- TRACE1 AFTER INJECT ---
TRACE1_HITS=<n>                                   ← >0 才算作业真进了 LPD
```

---

## 3. 目录结构

```
tools/
  build_initramfs.py      ★ 唯一构建入口：把 SIMBOOT payload 注入 initramfs（每次改动都要重建）
  kernel/initramfs-new.gz   构建产物（QEMU -initrd 用它）
  virtual_hal.c             Virtual HAL（musl 编译成 /lib/virtual_hal.so，guest 内 LD_PRELOAD）
  binder_stub.so            binder 打桩（mfp 依赖 libbinder）
  upload_server.py          8001 上传落盘服务
  elf_scan.py / disasm_*.py / find_*.py   逆向分析工具集（aarch64 静态分析）
  gen_pwg_job.py            生成 runtime/pwg-job-1page.pwg
runtime/
  run_sim.ps1               QEMU 启动器
  inject_on_ready.ps1       READY 看守 + hostfwd + 作业注入
  send_print_job.py         RFC1179 receive-job 客户端（LPD 注入）
  virtual_engine.py / virtual_printer.py   Phase 2 Step 5-6 预留
  unpacked/rkaf/rootfs.ext4 真实固件 rootfs（Release 资产）
  collected/                guest 回传的证据文件
  qemu-boot-*.log           历轮串口日志（每轮一个，全是取证记录）
.trae/documents/            phase1 / phase2 分阶段计划
printer-sim-poc/            PoC v0.1/v0.2（固件抽取 + 依赖分析）
```

---

## 4. 关键架构发现（已验证）

**启动链**：EDK2 → `vmlinuz-virt` → 自定义 initramfs（SIMBOOT）→ 挂真实 `rootfs.ext4` → `chroot` 跑 payload → `LD_PRELOAD=libbinder_stub.so:virtual_hal.so` 启动真实 `/usr/bin/mfp.afx`。

**唯一一处二进制 bake**（在 initramfs 阶段打，不在源码里）：
`netdata_get_lpd_switch` 改成 `mov w0,#1; ret`，让 LPD 开关恒开 —— 这是既有已验证链路，**不要动**。

**网络前端 = PCIe/IBC peer 代理**（Step 3 阻塞根因，`thread apply all bt` 直接读到）：

```
net_proxy_data_thread_handle   (net/netproxy/netproxy.c:797)
  └─ net_proxy_data_recv_from_pcie  (netproxy.c)
       └─ ibc_read_sync()           (libcommon.so)
            └─ _wait_for_peer:747   (ibc.c)   ← 自旋刷屏，占日志 99.4%
lpd_dispatch_thread            (net/lpd/lpd.c:431) → pi_sem_wait_ent  ← 等 netproxy 投递
protocol_thread_handle         (netproxy.c:162) × N  → 等信号量
```

即：作业数据来自 PCIe peer（3700 副板），仿真下 peer 不存在 → `_wait_for_peer` 自旋、LPD 分发线程永久阻塞。

**内部文本命令通道**（Step 3 的备用注入面，已确认存在但尚无 reader）：
mfp 启动时把整个打印子系统注册成文本命令，打印到 stdout：

```
print parser register success, io_via [10],type = [0]
cmd register ok = print_parser - pwgfileprint / urffileprint / pwgsaveoriginal
cmd register ok = print - fileprint / sendctlcmd
```

命令框架在 `libcommon.so`（`cmd_prolog` / `cmd_process_thread` / `cmd_register`），管道路径 `/tmp/cmd`，形式 `<main> - <sub> <params>`；非法命令会回 `invalid cmd!` 或列出可用子命令。

---

## 5. 已知约束与坑（换设备同样适用）

- **Guest 内存 4G，READY 后约 28 分钟 `mfp.afx` 会被 OOM 杀** → 所有取证必须在窗口内完成，脚本一律用"有界快照 + 立刻回传"。
- **宿主是 2 物理核**，`-smp` 保持 2；增大只会让 TCG 线程互相抢占变慢。
- **guest 侧禁止对大文件做多分支 `-i` 正则 grep**：TCG 下要数分钟，会让 `READY FOR INJECT` 永不出现（s6y 事故）。文本分析一律搬到宿主侧。
- **读 gdb 输出文件前必须先 kill gdb**，否则文件在增长、`wc/grep` 追不到 EOF。
- **`/proc/<tid>/syscall` 与 ptrace 冲突**：被 trace 的线程读它返回 EBUSY，只能在 gdb 释放后再读。
- **刷屏**：`_wait_for_peer:747 IBC WARN` 从启动第 6 行就开始，实测 3ms 内 33 行。它只饿死 guest 侧 grep，不影响注入本身。
- 别 patch `ibc_read_sync` 自旋、别修 plog stdout 重定向（无 daemon 时会让 mfp 写阻塞）——语义风险大于收益。

---

## 6. 证据与文档索引

| 想看什么 | 去哪 |
|---|---|
| 每轮运行的完整串口记录 | `runtime/qemu-boot-*.log`（`s6x`/`s6z`/`s7` 是最近三轮） |
| guest 回传的原始证据 | `runtime/collected/` |
| LPD/网络前端调用栈 | `runtime/collected/*-allbt.txt` |
| 分阶段计划 | `.trae/documents/phase1-*.md`、`phase2-print-closure-poc.md` |
| 长期结论与路线图 | `RK3588_Printer_Firmware_Simulation_Project_Summary.md` |

---

## 7. 改动约定

1. 改 `tools/build_initramfs.py` 后**必须重建**：`python tools\build_initramfs.py`，然后实跑取证，不能只看代码。
2. 任何改动都不得破坏既有已验证链路（bake 点、启动链、`POLL`/`LPD_SOCK_READY`/`READY FOR INJECT` 这些信号必须仍然出现）。
3. **每轮改动后更新 [Task.md](Task.md) 并提交推送**（见 Task.md 的"工作流约定"）。