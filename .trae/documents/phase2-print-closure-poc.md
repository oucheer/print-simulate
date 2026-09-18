# Phase 2 计划：真实打印闭环 PoC（合流方案）

> 依据：[RK3588_Printer_Firmware_Simulation_Project_Summary.md](file:///d:/Apps/codex/files/simulate/RK3588_Printer_Firmware_Simulation_Project_Summary.md) + 用户本次三层架构规划。
> 回答方向问题：**不做二选一，采用合流**——Phase 2 最小化是"真实打印闭环"的前置门槛，
> 但 Phase 2 以「mfp.afx 进入业务初始化 + 打印入口就绪」为边界，不无限扩展。

---

## 1. 摘要

目标：把三层串起来，让**真实 `mfp.afx` 驱动一个最小真实打印流程**：

```text
打印作业注入（PWG Raster）
  ↓
真实 mfp.afx（print_parser → [ENGINE] 引擎控制）
  ↓
Virtual Engine（模拟引擎固件 MCU，响应 pi_engfw_*）
  ↓
Virtual Printer（纸路/传感器/电机状态机）
  ↓
传感器反馈 → 真实 mfp.afx 读取 → 推进到下一步
```

验收：单页 A4 黑白作业，状态轨迹（IDLE → JOB → FEED → SENSOR → PRINT → OUTPUT → COMPLETE）**从真实固件日志提取**并对比。

---

## 2. 当前状态分析（已实证）

### 2.1 三层架构现状

| 层 | 内容 | 状态 |
|---|---|---|
| Layer 1 | QEMU / ARM64 Linux Runtime（CPU/RAM/Linux/ELF/动态库） | **已打通**：mfp.afx 真实运行，40+ 库全部加载 |
| Layer 2 | Virtual HAL / Device Model（GPIO/PWM/设备节点） | PoC 假模型 + 真实 HAL 边界（pi_hal_*）已识别；pcie 已伪设备穿越 |
| Layer 3 | Printer Behavior Simulation（纸路/电机/传感器/状态机） | 未建立（VirtualPrinter 是 Python 假模型，未接真实固件） |

### 2.2 启动链进展（Phase 1 成果）

```text
main → hal_prolog → plog → pntp → pcie_init(open+mmap 通过)
     → ibc → imagemem(缺 dma_heap) → msg_router → cmd → nvram(建表成功) → 继续(11线程)
```

### 2.3 本轮探索新发现（打印闭环可行性证据）

1. **mfp.afx 内置 PWG Raster 解析器**：`print_parser_pwg_*`（Read PWG Bitmap/band/header）
2. **打印入口**：`lpd_prolog`（LPD/515）、`netdata_set_ipp_switch`（IPP/631）、
   `pi_usbd_server_init_ippusb`（IPP over USB）、SNMP
3. **引擎控制接口**：`[ENGINE] engine_status_watcher_prolog, pi_engfw_get_print_report`、
   `Recv print start report page_index`、`Power Control Report`——mfp.afx 通过 `pi_engfw_*`
   与引擎固件（MCU）通信
4. **打印生命周期**：`MSG_PRINT_JOB_DONE`、`print_relay_print_job_done_process`、
   `print_job_pedk_set_paper_size/type`、`paper_size support tray_in`（纸盒匹配）
5. **进程家族**：rootfs 含独立 `pntp_service`（提供 `/tmp/.pntp_service`）、`hal_daemon`、
   `event_mgr_service`、`service_manager`、`ips.afx`、`scan_app`
6. **关键载体**：引擎通信通道疑为 `/dev/pantumpci-main`（PCIe，已伪设备穿越 open+mmap）

### 2.4 当前阻塞（Phase 2 最小 Virtualize 对象）

| 依赖 | 现状 | Virtualize 方案 |
|---|---|---|
| `/dev/dma_heap/system` | ENOENT，imagemem init failed | 内核 DMABUF_HEAPS 或 mknod 伪设备（观察 ioctl 需求） |
| `/tmp/.pntp_service` | ENOENT，线程轮询 | **直接运行真实 `pntp_service` 进程**（rootfs 自带） |
| `/tmp/.logserver` | ENOENT | 定位提供者（plog/event 服务），运行或伪造 |
| `/dev/netlog_dev` | ENOENT，线程轮询 | mknod 伪设备 |
| binder | ENOENT（第一轮出现，后续被淹没） | 观察是否阻塞业务初始化 |

---

## 3. 决策：回答"继续 Phase 2 还是直接做打印闭环"

**两者都需要，顺序为先 A 后 B：**

- **只做 Phase 2（无限虚拟化 HAL）** → 变成"让 mfp.afx 完整启动"，偏离打印仿真目标。
- **只做打印闭环（不先打通 Phase 2）** → 不可能：mfp.afx 业务层没起来，打印入口未监听，
  无法注入打印任务。

因此：**Phase 2 以最小集执行（Step 1），随后立即进入真实打印闭环（Step 2-6）**。
当 mfp.afx 出现打印端口监听（bind 515/631/9100）或 plog 出现 print/job 初始化日志，
即判定"业务初始化达成"，Phase 2 最小集收尾，不再扩展其他 HAL 设备。

---

## 4. 实施步骤

### Step 1：Phase 2 最小 Virtualize（前置门槛）

**目标**：mfp.afx 进入业务初始化，打印入口就绪。

- 修改 `tools/build_initramfs.py` 的 SIMBOOT 块（已验证的迭代循环）：
  - `/dev/dma_heap/system`：先 `mknod c 10 <次号>` + strace 观察 ioctl；若需内核支持，
    检查 `linux-virt` 内核 config 是否含 `CONFIG_DMABUF_HEAPS`；无则评估伪设备绕过
  - `/tmp/.pntp_service`：chroot 内**后台启动真实 `/usr/bin/pntp_service`**
  - `/tmp/.logserver`：grep mfp.afx/rootfs 定位提供者（plog 相关），启动或伪造监听
  - `/dev/netlog_dev`：mknod 伪设备（沿用 c 1 5 思路）
  - 保留 pantumpci 伪设备（c 1 5）
- 验证方式：mfp.afx 运行 120-180 秒后，strace/plog 确认：
  - 无 dma_heap 报错（或 imagemem init 成功）
  - **出现网络端口监听**（strace `bind`、`SO_REUSEADDR`）或 plog 出现 print/job 模块初始化
- 产出：`runtime/dependency-log.md` 更新；SIMBOOT 固化进 `runtime/run_sim.ps1`（一键脚本）

### Step 2：确认打印任务入口（探索，非臆想）

**目标**：确定打印作业如何注入。

- 从 Step 1 的 strace/plog 证据确认 mfp.afx 实际监听的端口与协议：
  - 网络：LPD(515)/IPP(631)/raw(9100)/PWG
  - 或 IPC：内部消息（msg_router）注入
- 若网络监听：QEMU 加 `-netdev user` + guest 内验证端口可达；
  从 Windows 侧用 curl/nc 发打印作业
- 产出：`runtime/print-entry.md`（入口协议/端口/报文格式，全部来自真实证据）

### Step 3：PWG 打印作业注入验证

**目标**：证明真实 mfp.afx 能接收作业并启动打印流程。

- 构造最小 PWG Raster 作业（A4 单面黑白 1 页，标准 PWG Raster 头 + 光栅数据）
- 注入 mfp.afx 打印入口（网络端口）
- 观察（plog/strace）：`print_parser` 处理、`print_relay_*` 调用、`[ENGINE]` 引擎命令出现
- 验收：plog 出现打印作业生命周期日志（job received / parser / engine 命令）
- 产出：`runtime/pwg-job-1page.pwg`（最小作业样本）+ 注入结果日志

### Step 4：引擎接口协议分析（pi_engfw_*）

**目标**：理解 mfp.afx ↔ 引擎固件（MCU）的通信协议，作为 Virtual Engine 的依据。

- 静态：`nm` 提取 mfp.afx 引用的 `pi_engfw_*`/`pi_eng*` 全集；capstone 定位调用点；
  分析引擎命令结构（打印开始/纸张/传感器/电机/定影/状态报告）
- 动态：strace 观察 mfp.afx 对 `/dev/pantumpci-main` 的 ioctl/读写（引擎通道）
- 产出：`runtime/engine-if.md`（接口清单 + 命令/响应结构，全部来自真实固件证据）

### Step 5：Virtual Engine + Virtual Printer 状态机

**目标**：实现引擎固件模拟器与打印机设备模型，接入真实 HAL。

- `runtime/` 下新增 `virtual_engine.py`（或复用现有 `poc.py` 扩展）：
  - 实现 `pi_engfw_*` 响应：打印报告（`Recv print start report page_index`、
    `Power Control Report` 等，结构来自 Step 4）
  - 引擎状态机：IDLE → FEED → PRINT → OUTPUT → DONE
- `virtual_printer.py`：纸路状态机（Paper/Sensor1/Sensor2/FeedMotor/Heater/Output），
  事件驱动（`insert_paper`、`paper advance`、`sensor on/off`、`motor on`），
  状态变化通过真实 HAL（pi_hal_gpio_*）呈现给 mfp.afx
- 关键：Virtual Engine/Printer 必须运行在 **guest 内**（作为独立进程/服务），
  与真实 mfp.afx 通过真实通道（pantumpci/共享内存/消息）通信——而不是 Python 假数据
- 产出：`runtime/virtual_engine.py`、`runtime/virtual_printer.py`

### Step 6：闭环与验收

**目标**：真实 mfp.afx 驱动完整最小打印流程。

- 流程：注入 PWG 作业 → mfp.afx 解析 → 发引擎命令 → Virtual Engine 响应 →
  Virtual Printer 纸路推进 → 传感器变化（经真实 HAL）→ mfp.afx 读取 → 继续推进 → 作业完成
- 状态轨迹：**从 mfp.afx 真实 plog 日志提取**（不臆想）：
  `IDLE → JOB_RECEIVED → PAPER_FEED → SENSOR_1 → PRINTING → OUTPUT → COMPLETE`
- 对比表：State / Sensor / Motor / Timing / Error / Job Result（与用户规划一致）
- 产出：`runtime/print-closure-report.md` + 轨迹日志

---

## 5. 假设与决策记录

| # | 假设/决策 | 依据 |
|---|---|---|
| 1 | 合流：Phase 2 最小集为前置，随后立即做打印闭环 | mfp.afx 须进入业务初始化才能接收打印任务 |
| 2 | Phase 2 边界 = 业务初始化 + 打印入口就绪 | 避免无限虚拟化偏离目标 |
| 3 | 打印任务入口以 PWG/网络为主候选（非臆想，探索确认） | rodata 证据：print_parser_pwg_*、lpd/ipp 入口 |
| 4 | 引擎通道为 `/dev/pantumpci-main`（候选） | Phase 1 证据：pcie_init 轮询此设备 |
| 5 | 状态轨迹从真实固件日志提取，不预先定义 | 文档原则：不猜真实业务 |
| 6 | Virtual Engine/Printer 运行于 guest 内，与真实固件通过真实通道通信 | 保证"真实固件闭环"而非假数据 |
| 7 | 若 Step 3 显示 mfp.afx 业务入口不在网络（如纯 IPC），则切换到 msg_router 注入 | 探索驱动 |

---

## 6. 验证方式

1. **Step 1**：mfp.afx 出现打印端口监听或 print/job 初始化日志 → Phase 2 最小集完成
2. **Step 3**：plog 出现打印作业生命周期日志（job received/parser/engine 命令）
3. **Step 4**：`engine-if.md` 含 pi_engfw_* 接口清单与命令结构（来自真实证据）
4. **Step 6 最终验收**：单页 A4 黑白 PWG 作业，真实 mfp.afx 驱动虚拟纸路，
   状态轨迹从真实 plog 提取并呈现（IDLE → ... → COMPLETE）
5. **回归**：现有 Phase 1 交付物与 `poc.py` 不受影响

---

## 7. 交付物清单

- `runtime/run_sim.ps1` — 一键仿真启动脚本（固化 SIMBOOT）
- `runtime/print-entry.md` — 打印入口探索结论（协议/端口/报文）
- `runtime/pwg-job-1page.pwg` — 最小 PWG 作业样本
- `runtime/engine-if.md` — pi_engfw_* 引擎接口协议分析
- `runtime/virtual_engine.py`、`runtime/virtual_printer.py` — 引擎/纸路模型（guest 内运行）
- `runtime/print-closure-report.md` — 闭环报告（状态轨迹对比）
- 更新：`runtime/dependency-log.md`、`tools/build_initramfs.py`
