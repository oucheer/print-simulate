# RK3588 打印机固件仿真 PoC v0.1

这个 PoC 不是“完整打印机数字孪生”，而是验证最关键的第一条链路：

```text
真实 update.img
      ↓
RKFW / RKAF 解析
      ↓
rootfs.ext4
      ↓
真实 mfp.afx / libhal.so / HAL 配置
      ↓
识别 Virtual HAL 边界
      ↓
Virtual Printer / Sensor / Fault Model
      ↓
可重复测试与结果
```

## 已经实际验证的内容

基于用户提供的 `update.zip`：

- 外层：Rockchip RKFW
- 芯片字段：RK3588
- 内层：RKAF
- RKAF 分区：`MiniLoaderAll.bin`、`uboot.img`、`misc.img`、`boot.img`、`pantum.ext4`、`rootfs.ext4`
- `rootfs.ext4` 中存在真实 `/usr/bin/mfp.afx`
- `mfp.afx` 为 AArch64 ELF64
- `mfp.afx` 依赖 `libhal.so`
- `libhal.so` 暴露 `pi_hal_gpio_*`、`pi_hal_power_*`、`pi_hal_rtc_*`、`pi_hal_storage_*`、`pi_hal_virt_*`
- `hal_module_config.json` 中明确存在：
  - `virtual_platform`
  - `qemu_platform`
  - `pwm -> virtual`
  - `gpio`
  - `generic_power`
- PoC 已实现 Virtual Printer 正常打印、缺纸、卡纸与恢复场景

## 当前刻意没有做的事情

PoC 当前没有在 x86 主机上直接执行 AArch64 `mfp.afx`。这是下一阶段：需要接入 AArch64 用户态仿真器（如 `qemu-aarch64`）以及与该 rootfs 匹配的 ARM64 runtime。

所以现在的 PoC 证明的是：

1. 真实固件包可以被机器解析。
2. 真实 MFP 程序和 HAL 依赖可以被提取。
3. 真实固件已经暴露出 Virtual HAL / QEMU 相关边界。
4. 虚拟传感器/执行器可以用事件驱动方式形成闭环。

## 运行

```bash
python3 poc.py all /path/to/update.img -o poc-out
```

只做固件分析：

```bash
python3 poc.py inspect /path/to/update.img -o poc-out
```

只运行 Virtual Printer demo：

```bash
python3 poc.py demo -o poc-out
```

## 下一阶段

下一阶段不是继续扩大“假打印流程”，而是：

```text
AArch64 Linux Runtime
        ↓
真实 rootfs
        ↓
真实 mfp.afx
        ↓
真实 libhal
        ↓
Virtual HAL
        ↓
真实 mfp 代码开始运行
```

然后根据真实程序启动过程中首次访问的设备节点、HAL API 和系统调用，逐项补虚拟设备模型。
