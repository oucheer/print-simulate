# Task.md · 任务清单与进度

> 这份文件是**跨设备接力用的唯一进度源**：换电脑后先读 `README.md` 第 2 节恢复环境，再从这里挑 `[ ]` 继续。
> 每轮改动完成后：更新本文件 → `git commit` → `git push`。

---

## 工作流约定（每轮对话都遵守）

1. 改 `tools/build_initramfs.py` 后**必须重建并实跑**：`python tools\build_initramfs.py`，只改代码不取证不算完成。
2. 不得破坏既有已验证链路：`SIMBOOT_PREP_DONE` / `MFP_PID` / `HOLD_OK=1` / `POLL … passed print_info_status_init` / `LPD_SOCK_READY` / `READY FOR INJECT` 必须仍然出现。
3. 本轮做完 → 勾选/新增本文件的条目 → commit（信息写清"为什么"）→ push。
4. 有新规划也追加到本文件的对应 Phase 下，不要另开散落文档。

---

## 0. 环境恢复（换设备必做）

- [x] 仓库已建：`https://github.com/oucheer/print-simulate.git`（分支 `main`）
- [x] 大体积资产已发布 Release `v0.1-bundles`（qemu / kernel / toolchain / firmware / runtime-logs）
- [ ] 新设备：克隆 + `gh release download v0.1-bundles` + 解压 4 个 7z 到 `tools/qemu-native`、`tools/kernel`、`tools/toolchain`、`runtime/unpacked`
- [ ] 新设备：确认 `runtime/qemu-boot-*.log`、`runtime/collected/` 已就位（取证基线）
- [ ] 起宿主服务：`python tools\upload_server.py`（8001）、`python -m http.server 8000 --directory tools\toolchain`（8000）

---

## 1. Phase 0 · 固件结构分析 ✅

- [x] `update.img` 解包，定位 rootfs / 内核 / 内核模块
- [x] 确认 `mfp.afx` 是真实完整固件主程序（含 DWARF 行号，可 gdb 定位到 `net/lpd/lpd.c`）
- [x] PoC v0.1 / v0.2（`printer-sim-poc/`）与依赖分析产出

---

## 2. Phase 1 · 真实固件启动 ✅

- [x] Windows 原生 QEMU aarch64 + EDK2 启动 `vmlinuz-virt`
- [x] 自定义 initramfs（SIMBOOT）挂真实 `rootfs.ext4` 并 `chroot`
- [x] `LD_PRELOAD=libbinder_stub.so:virtual_hal.so` 拉起真实 `/usr/bin/mfp.afx`
- [x] 唯一 bake：`netdata_get_lpd_switch` → `mov w0,#1; ret`（既有链路，**不要动**）

---

## 3. Phase 2 · 真实打印闭环 POC

### Step 1 · Virtual HAL ✅
- [x] `tools/virtual_hal.c` 覆盖 `pi_hal_gpio/power/led/rtc/storage/wifi/boardinfo/virt`
- [x] guest 内 musl 交叉编译成 `/lib/virtual_hal.so` 并 `LD_PRELOAD`

### Step 2 · 业务初始化解锁 ✅
- [x] 定位 `print_info_status_init` 卡点，打 `0xa91370+0x5c/0x7c/0x80/0x82`
- [x] 处理"mfp 自身会写回 0"的问题：常驻 gdb 硬件 watchpoint 反复重置
- [x] 解锁后线程数 45 → 179/196，到达 `POLL … passed print_info_status_init (N=102)`

### Step 3 · PWG 作业经 LPD 进入真实 mfp.afx ❌ 进行中

**验收标准**：plog/stdout 出现 `job received` / parser / engine 命令，或注入脚本输出 `LPD job sent OK`。

已完成的取证（关键结论）：
- [x] 注入链路本身可用：`runtime/send_print_job.py`（RFC1179 receive-job）+ `inject_on_ready.ps1`（READY 看守 + monitor `hostfwd_add`）
- [x] 端口动态发现：payload 输出 `SIMBOOT_LPD_PORTS=<hex>`，watcher 解析后加转发（例：`84DB`=34011、`AE67`=44647）
- [x] **根因定案**：LPD 网络前端是 PCIe/IBC peer 代理，不是宿主直连
      `net_proxy_data_thread_handle → net_proxy_data_recv_from_pcie → ibc_read_sync → _wait_for_peer:747` 自旋；
      `lpd_dispatch_thread`(lpd.c:431) 等信号量 → 10 个 LPD 入口断点 `TRACE1_HITS=0`
- [x] TCP 层证据：`/proc/net/tcp` 中 LPD 端口仍 `0A`(LISTEN) 且 `rx_queue=2`，已 accept 的连接停在 `08`(CLOSE_WAIT) 且应用层从未 read
- [x] s7 试跑真实 `/usr/bin/pntp_service`：能起来并创建 `/tmp/.pntp_service`(unix socket)，但随后 `pntp_service process plog lib destory` 退出，**未解除门控**（注入仍失败，`TRACE1_HITS=0`）
- [x] 发现备用注入面：mfp 把打印子系统注册为文本命令，管道 `/tmp/cmd`（FIFO，s7 确认存在）
      例：`cmd register ok = print_parser - pwgfileprint`、`print - fileprint`，框架在 `libcommon.so`
- [ ] **`/tmp/cmd` 尚未打通**：s7 里 `echo > /tmp/cmd` 全部 `RC=124`（写入阻塞 5s 超时）→ 当前**没有 reader**

**下一步实验（按性价比排序）**：
- [ ] **A. 打通 `/tmp/cmd`（首选）**
      先自己持读写句柄再写，避免 open-for-write 阻塞：`exec 3<>/tmp/cmd; echo "print_parser" >&3`
      同时用——静态确认谁读它：`libcommon.so` 的 `cmd_process_thread`/`cmd_prolog` 打开模式（`Create cmd pipe failed:%s` / `Open cmd pipe:%s failed`）
      验证：mfp 日志出现 `"print_parser" supports subcmds below:` 或 `invalid cmd!`
- [ ] **A2. 打通后直接投作业**：`echo "print_parser - pwgfileprint /tmp/job.pwg" >&3`（PWG 从 `http://10.0.2.2:8000/pwg-job-1page.pwg` 拉）
      验证：出现 parser/engine 相关日志 → Step 3 达成，直接进 Step 4
- [ ] **B. 查清 pntp 客户端路径**：mfp 启动日志有 `pntp socket client init`；确认它是否连接 `/tmp/.pntp_service`、以及 `pntp_service` 为什么 `destory`（是否等 `/dev/pantumpci-*` 真设备）
- [ ] **C. 兜底：伪造 PCIe/IBC peer**：需要先逆向 IBC 帧格式与 `/dev/pantumpci-main` 读写语义，成本最高，只在 A/B 均失败时启动
- [ ] **D. 修抓栈**：s7 的 `thread apply all bt 5` 只产出 1 行（attach 未成功/进程已 OOM），改为先确认 attach 成功再 `bt 3`，并把结果落文件后回传

### Step 4 · `engine-if.md`（引擎接口文档）⏸
- [ ] 从 `print_parser` / `print` 下发到引擎的命令序列中提炼接口（命令码、参数、时序）
- [ ] 覆盖最小打印所需：引擎配置（color/speed/density/tray）、页数据下发、状态回报、错误回报

### Step 5 · `virtual_engine.py` + `virtual_printer.py` ⏸
- [ ] 必须**跑在 guest 内**，与真实固件通过真实通道（`pantumpci` / 共享内存 / 消息）通信，不得用宿主侧旁路
- [ ] `virtual_engine.py`：实现 Step 4 定义的引擎侧状态机（就绪/走纸/成像/出错）
- [ ] `virtual_printer.py`：把引擎输出的页数据渲染成可校验图像，作为"出图"证据

### Step 6 · 闭环验收 ⏸
- [ ] 一条 PWG 作业 → 解析 → 引擎命令 → 虚拟引擎出图 → 落盘比对
- [ ] 产出可复现脚本（一条命令跑完整闭环）与验收报告

---

## 4. 后续 Phase（源自项目总结文档，暂列）

- [ ] Phase 3 · Virtual Device（传感器/执行器虚拟化）
- [ ] Phase 4 · Virtual Printer（完整虚拟打印引擎）
- [ ] Phase 5 · 测试引擎（自动化用例）
- [ ] Phase 6 · 真实设备差分验证（仿真 vs 真机行为对齐）
- [ ] Phase 7 · 打包 Windows EXE 一键运行

---

## 5. 每轮运行记录（接力时照着往前读）

| 轮次 | 目的 | 结果 |
|---|---|---|
| s6x | 注入窗口 + trace | 链接从不被 accept（首次暴露） |
| s6y | 加 guest 侧关键字 grep | ❌ 卡死：8MB 快照多分支 `-i` grep 在 TCG 下数分钟 |
| s6z | 去掉 guest 侧 grep，改宿主侧分析 | ✅ 流程恢复秒级；`TRACE1_HITS=0`；`allbt.txt` 定案 peer 门控 |
| s7 | 起真实 `pntp_service` + `/tmp/cmd` 探测 | ✅ pntp 起来但自退；`/tmp/cmd` 是 FIFO 但无 reader（`RC=124`）；注入仍失败 |

---

## 6. 硬约束（每轮都要守住）

- Guest 4G 内存，READY 后约 28 分钟 `mfp.afx` 被 OOM 杀 → 取证一律"有界快照 + 立刻回传"
- 宿主 2 物理核，`-smp` 保持 2
- guest 侧禁止对大文件做多分支 `-i` 正则 grep（s6y 事故）
- 读 gdb 输出前先 kill gdb；`/proc/<tid>/syscall` 只能在 gdb 释放后读
- 不 patch `ibc_read_sync` 自旋、不修 plog stdout 重定向