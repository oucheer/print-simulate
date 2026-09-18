# Phase 1 启动链与 HAL 调用序列（hal-call-trace.md）

> 证据来源：真实运行日志（`runtime/qemu-boot-11/15/16/18.log`）、plog 文件、strace 输出、main 反汇编。

## 1. 真实启动链（已实证推进到 nvram init）

```text
main()  [0x6a7dec, 反汇编确认]
  ├─ bl 0x6a0b34 = hal_prolog  [main 中 0x6a7f24 调用, 反汇编证据]
  │
  ├─ plog lib init
  │    └─ PLOG_JSON: parse /configs/plog/plog_json_config.json（缺失→reset config，可恢复）
  ├─ pntp socket client init（AF_UNIX /tmp/.pntp_service 缺失，线程轮询）
  │
  ├─ [HAL Runtime 内推进]
  │    ├─ pcie_init：open+mmap /dev/pantumpci-main(+video)
  │    │    （缺设备→ENOENT→轮询；伪设备 c1/5 后 open+mmap 通过）
  │    ├─ ibc init
  │    ├─ pi_imagemem_init：open /dev/dma_heap/system（缺失，imagemem init failed）
  │
  ├─ msg_router init
  ├─ cmd init（cmd process thread 已创建）
  ├─ nvram init
  │    ├─ sql_init：create table int/uint/string/struct success
  │    └─ insert default value
  └─ [继续推进中... 11 线程运行]
```

## 2. 外部符号引用（nm 证据）

mfp.afx 引用的 `pi_hal_*`（来自 libhal.so，未定义符号）：
`pi_hal_boardinfo_*`、`pi_hal_exit`、`pi_hal_gpio_get/request/set`、`pi_hal_init`、
`pi_hal_led_ctrl/request`、`pi_hal_power_request/set`、`pi_hal_rtc_*`、
`pi_hal_storage_*`（dirread/dirrelease/dirrequest/filerequest/fileread/...）

binder IPC 引用：`binder_add_target/binder_call/binder_done/binder_start`（来自 libcommon.so 等）

## 3. 动态链接（strace 证据，全部加载成功）

见 [dependency-log.md](file:///d:/Apps/codex/files/simulate/runtime/dependency-log.md) —— 40+ 个共享库
（含 libhal、libmali 58MB、libopencv、gstreamer 全家）全部 openat+mmap 成功。

## 4. 关键结论

1. **第一阶段目标已超越达成**：不只到 `pi_hal_init()`，真实 HAL 初始化已推进到
   `pcie_init → ibc → imagemem → nvram init`，即 HAL Runtime 第一堵墙已被实质性穿越。
2. **当前阻塞点**：`/dev/dma_heap/system`（DMA-BUF heap）缺失导致 imagemem init failed；
   以及多个守护 socket（logserver/pntp_service）与 `/dev/netlog_dev` 缺失导致的线程轮询。
3. **Virtualize 循环有效**：伪设备（/dev/null→/dev/zero 伪装）成功让 pcie_init 从
   `open ENOENT` 推进到 `mmap 通过`，证明「真实错误→定位→最小 Virtualize→再运行」方法论成立。
