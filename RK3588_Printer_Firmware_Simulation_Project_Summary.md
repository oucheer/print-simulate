# RK3588 激光打印机固件仿真验证项目：当前会话总结与后续规划

## 1. 项目背景

最初讨论激光打印机的拓展方向，包括：

- 打印机 Agent
- 智能故障诊断
- 自动化测试
- AI 打印质量检测
- 预测性维护
- 数字孪生
- 企业打印安全
- 耗材智能管理

随后确认：这些方向高度依赖具体业务场景、打印机内部架构、固件代码、测试方案、硬件设计、协议、代码仓库和验收标准。在这些信息未知时直接设计产品，很容易变成脱离实际的方案。

因此项目方向调整为：

> **建设一个基于真实 RK3588 打印机固件的仿真验证平台，以真实固件和真实 HAL 为核心，用 Virtual HAL / Virtual Device 替代真实硬件，在 PC 上进行快速验证。**

---

## 2. 最终目标

最终希望实现一个 Windows EXE：

```text
Printer Firmware Simulator.exe
│
├── Firmware Loader
├── ARM64 Runtime
├── Virtual HAL
├── Virtual Sensors
├── Virtual Device
├── Virtual Printer
├── Fault Injection
├── Test Engine
├── Trace / Log
└── PASS / FAIL
```

目标开发流程：

```text
修改固件代码
    ↓
内网直接编译
    ↓
生成真实固件
    ↓
导入 EXE
    ↓
启动仿真
    ↓
真实固件运行
    ↓
Virtual HAL / Virtual Device 提供硬件反馈
    ↓
执行测试
    ↓
自动输出结果
```

最终减少甚至避免：

```text
修改
→ 编译
→ 导出固件
→ 传输
→ 烧录 RK3588
→ 启动设备
→ 手工测试
→ 收集日志
→ 再修改
```

希望形成：

```text
Firmware
  ↓
Simulation
  ↓
Test
  ↓
Report
```

---

## 3. 核心工程原则

### 3.1 不猜真实业务

没有证据就不设计真实业务流程。

尤其不在未知硬件架构、未知 HAL、未知固件逻辑时，直接假设纸路、电机、传感器时序。

### 3.2 证据驱动

优先利用：

```text
真实固件
真实 rootfs
真实 ELF
真实 HAL
真实配置
真实符号
真实运行错误
真实设备行为
```

逐步建立模型。

### 3.3 先最小闭环，再逐层扩展

第一目标不是“完整模拟激光打印机”，而是：

> **让真实 `mfp.afx` 脱离真实 RK3588 硬件后仍然能够启动和运行。**

---

# 4. 当前已提供的真实固件

用户提供：

- `mfp.afx`
- 完整 RK3588 固件 `update.zip`

完整固件中包含 `update.img`。

已分析出类似：

```text
RKFW
  ↓
RKAF
  ├── MiniLoaderAll.bin
  ├── parameter.txt
  ├── uboot.img
  ├── misc.img
  ├── boot.img
  ├── pantum.ext4
  └── rootfs.ext4
```

`rootfs.ext4` 中包含：

```text
/usr/bin/mfp.afx
/usr/bin/ips.afx
/usr/bin/scan_app
/usr/bin/hal_daemon
/usr/bin/event_mgr_service
/usr/bin/service_manager
...
/usr/lib/libhal.so
/usr/lib/libcommon.so
/usr/lib/libevent_mgr.so
/usr/lib/libosal.so
...
```

---

# 5. 已确认 `mfp.afx` 是完整固件中的真实程序

之前单独上传的：

```text
mfp.afx
```

与：

```text
rootfs.ext4/usr/bin/mfp.afx
```

做过 SHA-256 比较：

> 完全一致。

因此关系已经确认：

```text
update.zip
  ↓
update.img
  ↓
rootfs.ext4
  ↓
/usr/bin/mfp.afx
```

---

# 6. `mfp.afx` 基本特征

已经确认：

- ELF64
- AArch64
- ARM 64 位
- Entry Point：`0x44c280`
- Linux 用户态程序特征
- 动态链接
- 未 stripped
- 带 DWARF debug 信息

因此它更符合：

```text
RK3588
  ↓
Linux
  ↓
mfp.afx
  ↓
打印机业务程序
```

而不是传统 MCU 裸机固件。

---

# 7. 已发现真实 HAL 架构

`mfp.afx` 依赖：

```text
libhal.so
```

并使用大量：

```text
pi_hal_*
```

接口。

已经发现包括：

```text
pi_hal_gpio_request
pi_hal_gpio_set
pi_hal_gpio_get

pi_hal_led_request
pi_hal_led_ctrl

pi_hal_power_request
pi_hal_power_set

pi_hal_storage_*

pi_hal_rtc_*

pi_hal_boardinfo_*

pi_hal_virt_request
pi_hal_virt_free
pi_hal_virt_platform
pi_hal_virt_getinfo
```

说明架构大致是：

```text
mfp.afx
   ↓
libhal.so
   ↓
HAL
   ↓
硬件
```

---

# 8. 已发现 Virtual Platform

这是当前最重要的发现之一。

在真实固件配置和 `libhal.so` 中发现：

```text
virtual_platform
qemu_platform
pi_hal_virt_*
```

另外 PWM 配置还出现：

```text
"json_node": "virtual"
```

因此：

> **当前真实软件架构本身已经存在虚拟化相关接口和模块。**

这比从零设计 Virtual HAL 更有价值。

---

# 9. 已发现真实打印业务线索

`mfp.afx` 中存在大量打印业务相关符号/字符串，例如：

```text
paper_size
paper_type
paper_jam_flag
paper_media_speed
paper_size_with_tray
paper_type_with_tray
engine_configuration
engine_page_list_mgr
paper_remain
print_parser
print_image
print_ctl_config
maintenance_paper_type
```

以及：

```text
paper
tray
duplex
margin
image
600dpi
1200dpi
CMYK
```

因此没有必要先凭空重新设计完整打印流程。

真实业务代码本身就是后续行为模型的重要来源。

---

# 10. 已分析的真实启动链

目前已追到：

```text
main()
  ↓
hal_prolog()
  ↓
pi_hal_init()
  ↓
hal_core_shm_attach()
  ↓
hal_core_init()
  ↓
Wi-Fi / NVRAM / Event / Storage / Image / Print 等模块
```

因此当前真正的第一堵墙是：

> **HAL Runtime**

不是纸路、电机或者传感器。

---

# 11. 没有真实传感器是否可以

答案：

> **可以。**

真实环境：

```text
纸张
 ↓
真实传感器
 ↓
GPIO / I2C / ADC
 ↓
HAL
 ↓
mfp.afx
```

仿真环境：

```text
Virtual Event
 ↓
Virtual Sensor
 ↓
Virtual GPIO / I2C / ADC
 ↓
Virtual HAL
 ↓
mfp.afx
```

例如：

```text
Insert Paper
    ↓
VirtualPaperSensor = 1
    ↓
真实 mfp.afx 读取 GPIO
    ↓
进入下一阶段
```

因此第一阶段完全可以：

- 不需要真实传感器
- 不需要真实电机
- 不需要真实纸路
- 不需要真实加热器

---

# 12. Virtual Sensor 初期设计

第一阶段不需要做复杂物理模型，先使用事件：

```text
insert_paper(A4)
remove_paper()
paper_jam()
toner_low()
toner_empty()
heater_reach(180)
motor_stall()
sensor_fault()
```

然后映射到：

```text
Virtual Sensor State
```

例如：

```text
insert_paper(A4)

→ paper_sensor_1 = 1
→ paper_position = tray
→ paper_count = 1
```

目标是让真实固件得到和真实硬件一致的观察结果。

---

# 13. 推荐总体架构

```text
                Printer Firmware Simulator
                         EXE
                          │
              ┌───────────┴───────────┐
              │                       │
      Simulation Controller     Firmware Loader
              │                       │
              └───────────┬───────────┘
                          │
                    ARM64 Runtime
                          │
                  ┌───────┴───────┐
                  │               │
             Real Firmware    Virtual HAL
                  │               │
                  │        ┌──────┼──────┐
                  │        │      │      │
                  │      GPIO    PWM   Power
                  │        │      │      │
                  └────────┴──────┴──────┘
                           │
                    Virtual Printer
                           │
              ┌────────────┼────────────┐
              │            │            │
            Paper        Motor        Sensor
              │            │            │
              └────────────┼────────────┘
                           │
                         Trace
                           │
                      Test Engine
                           │
                        PASS / FAIL
```

---

# 14. QEMU 技术路线

## 14.1 `qemu-aarch64`

用于：

```text
Windows x86_64
    ↓
qemu-aarch64
    ↓
ARM64 Linux 用户态
```

目标：

> 先验证真实 `mfp.afx` 是否可以脱离 RK3588 进入用户态执行。

## 14.2 `qemu-system-aarch64`

用于：

```text
PC
 ↓
QEMU ARM64 System
 ↓
ARM64 Linux Kernel
 ↓
RootFS
 ↓
mfp.afx
```

目标：

> 后续做完整嵌入式 Linux Runtime。

---

# 15. 当前 QEMU 状态

用户已经安装 MSYS2 UCRT64，并尝试：

```bash
pacman -S mingw-w64-ucrt-x86_64-qemu
```

确认该包包含：

```text
/ucrt64/bin/qemu-system-aarch64.exe
```

但不包含：

```text
qemu-aarch64.exe
```

所以已经停止继续从 MSYS2 寻找 User Mode QEMU。

用户随后从：

```text
https://qemu.weilnetz.de/w64/
```

下载了 Windows 原生 QEMU。

当前下一步以 **Windows 原生 QEMU** 为准。

---

# 16. PoC v0.1

已经生成：

```text
rk3588-printer-sim-poc-v0.1.zip
```

主要包含：

```text
RKFW/RKAF 固件解析
rootfs.ext4 读取
mfp.afx 分析
libhal 分析
Virtual HAL
Virtual Sensor
Virtual Printer
正常打印场景
卡纸场景
卡纸恢复场景
自动化测试
```

测试结果：

```text
3 passed
```

但注意：

> v0.1 尚未真正执行 AArch64 `mfp.afx`。

---

# 17. PoC v0.2

已经生成：

```text
rk3588-printer-sim-poc-v0.2.zip
```

进一步加入：

```text
真实固件启动链分析
真实 HAL 依赖分析
ELF 动态依赖分析
QEMU AArch64 Runtime 准备
真实 mfp.afx 启动入口
Windows PowerShell 启动入口
真实 main() / hal_prolog() / pi_hal_init() 分析
```

v0.2 的核心结论：

> **真实执行的第一堵墙是 HAL Runtime。**

---

# 18. 当前真正的最小闭环

```text
真实 update.img
      ↓
真实 rootfs.ext4
      ↓
真实 mfp.afx
      ↓
AArch64 Linux Runtime
      ↓
真实 libhal.so
      ↓
Virtual HAL
      ↓
mfp.afx 真正运行
```

第一阶段不追求完整打印。

---

# 19. 第一阶段成功标准

只要达到：

```text
mfp.afx
  ↓
main()
  ↓
hal_prolog()
  ↓
pi_hal_init()
  ↓
进入后续业务初始化
```

就可以认为第一阶段获得重大突破。

---

# 20. 第一次失败也属于有效结果

第一次运行可能遇到：

```text
缺少动态库
缺少 /dev 节点
共享内存失败
IPC 失败
daemon 不存在
HAL 初始化失败
/sys 不完整
/proc 不完整
设备节点不存在
```

这些都应该被视为：

> **真实依赖清单，而不是无效结果。**

采用：

```text
真实错误
 ↓
定位依赖
 ↓
Virtualize
 ↓
再次运行
 ↓
获得下一个真实依赖
```

不断推进。

---

# 21. 后续路线图

## Phase 0：固件结构分析

状态：**已完成**

```text
update.zip
→ update.img
→ RKFW
→ RKAF
→ rootfs
→ mfp.afx
```

---

## Phase 1：真实 AArch64 固件启动

状态：**当前**

目标：

```text
QEMU
 ↓
真实 rootfs
 ↓
真实 mfp.afx
```

并获得第一个真实运行结果。

---

## Phase 2：Virtual HAL

目标：

```text
pi_hal_init()
GPIO
PWM
Power
RTC
Storage
Board Info
Virtual Platform
IPC / SHM
```

状态：**设计中**

---

## Phase 3：Virtual Device

逐步加入：

```text
Paper Sensor
Motor
Tray
Door
Heater
Temperature
Toner
```

状态：**未开始**

---

## Phase 4：Virtual Printer

建立：

```text
Idle
Receive Job
Paper Feed
Processing
Output
Complete
Jam
Recover
```

状态：**未开始**

---

## Phase 5：测试引擎

支持：

```text
测试用例
自动执行
故障注入
日志
Trace
断言
PASS / FAIL
```

状态：**未开始**

---

## Phase 6：真实设备差分验证

建立：

```text
Virtual Printer
        vs
Real Printer
```

比较：

```text
State
Sensor
Motor
Timing
Error
Result
```

状态：**后续**

---

## Phase 7：Windows EXE

最终封装：

```text
Printer Simulator.exe
```

主要功能：

```text
固件选择
模型选择
启动
暂停
重启
单步
日志
寄存器
HAL Trace
Sensor 控制
故障注入
测试用例
报告
```

状态：**后续**

---

# 22. 最终理想开发闭环

```text
代码修改
   ↓
内网编译
   ↓
生成 AFX / ELF
   ↓
自动加载到 Simulator
   ↓
启动 ARM64 Runtime
   ↓
加载 Virtual HAL
   ↓
自动测试
   ↓
故障注入
   ↓
Trace
   ↓
PASS / FAIL
```

目标是把开发从：

```text
编译 → 烧录 → 实机测试
```

转变成：

```text
编译 → 仿真 → 自动验证
```

真实机器只负责最终差分验证。

---

# 23. 当前最重要的技术判断

当前已经确认：

1. 固件为 AArch64 ELF64
2. 运行环境为 Linux / Buildroot
3. RK3588 为真实目标平台
4. `mfp.afx` 存在于真实 rootfs
5. `mfp.afx` 依赖 `libhal.so`
6. HAL 存在大量 `pi_hal_*`
7. 存在 `virtual_platform`
8. 存在 `qemu_platform`
9. 存在 `pi_hal_virt_*`
10. PWM 存在 `virtual` 配置
11. `mfp.afx` 未 strip
12. 存在 DWARF debug 信息
13. 可以继续直接追踪真实函数、符号和 HAL 调用

因此当前项目已经从：

> “理论上可能”

进入：

> **“有真实固件、真实 HAL 和 Virtual Platform 证据支撑，可以进入真实执行验证。”**

---

# 24. 当前最大未知量

当前最重要的未知量不是：

```text
CPU
Linux
固件位置
HAL
Virtual Platform
```

而是：

```text
真实 mfp.afx 能否通过当前 Virtual HAL / QEMU Runtime 初始化并进入业务运行？
```

以及：

```text
启动过程中到底依赖哪些：
- daemon
- IPC
- SHM
- /dev
- /sys
- /proc
- HAL module
- 外部服务
```

这些问题必须通过真实运行逐步暴露。

---

# 25. 下一步具体行动

### 第一步：确认 Windows 原生 QEMU

PowerShell：

```powershell
where.exe qemu-aarch64.exe
qemu-aarch64.exe --version

where.exe qemu-system-aarch64.exe
qemu-system-aarch64.exe --version
```

### 第二步：准备真实 `update.img`

使用 `afptool-rs` 等工具解析：

```text
update.img
 ↓
RKAF
 ↓
rootfs.ext4
boot.img
uboot.img
```

### 第三步：准备 ARM64 RootFS

确认至少存在：

```text
/lib/ld-linux-aarch64.so.1
/usr/bin/mfp.afx
/usr/lib/libhal.so
```

### 第四步：第一次真实运行

优先尝试：

```text
qemu-aarch64 + rootfs + mfp.afx
```

如果 `mfp.afx` 依赖大量 Linux 内核资源，则切换：

```text
qemu-system-aarch64
+
ARM64 Linux kernel
+
rootfs.ext4
```

### 第五步：记录第一个真实失败点

不要提前模拟几十种硬件。

只解决：

```text
第一个真实错误
 ↓
真实依赖
 ↓
最小 Virtual Device / Runtime
 ↓
再次启动
```

重复执行。

---

# 26. 项目最终定位

项目名称建议：

> **RK3588 Printer Firmware Simulation & Validation Platform**

中文：

> **RK3588 打印机固件仿真验证平台**

核心技术：

```text
真实固件
+
ARM64 Runtime
+
Virtual HAL
+
Virtual Device
+
Virtual Printer
+
Test Engine
+
Trace
+
Differential Validation
```

而不是单纯的：

> “打印机模拟器”。

---

# 27. 一句话定义

> **让真实 RK3588 打印机固件在 Windows PC 上通过 ARM64 Runtime + Virtual HAL + Virtual Device 运行，从而把“编译→烧录→测试”逐渐转化成“编译→仿真→自动验证”。**

---

# 28. 当前会话形成的关键共识

- 不凭空猜打印机内部流程。
- 不先做完整数字孪生。
- 不先做复杂 AI。
- 不先做漂亮 GUI。
- 先运行真实固件。
- 先定位真实 HAL 和系统依赖。
- 再逐步建立 Virtual Device。
- 再建立 Virtual Printer。
- 再加入自动测试。
- 最终再包装成 EXE。
- 真实硬件用于最终一致性验证，而不是日常开发验证。
