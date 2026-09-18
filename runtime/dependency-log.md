# Phase 1 真实依赖清单（dependency-log.md）

> 按「真实错误 → 定位缺失 → 最小 Virtualize → 再次运行」循环记录。
> 每项记录：错误原文 → 缺失项 → 处理方式 → 验证结果。

## 运行环境

- 仿真：`tools/qemu-native/qemu-system-aarch64.exe` v11.1.0
- 机型：`-M virt -cpu cortex-a76 -m 2G -smp 2`，UEFI 引导（edk2-aarch64-code.fd）
- 内核：Alpine `linux-virt-6.12.103-0-virt`（真实 RK3588 内核无 PL011/virtio 驱动，无法用于 QEMU virt）
- initramfs：`tools/kernel/initramfs-new.gz`（自制，注入 ext4/virtio 模块）
- rootfs：`runtime/unpacked/rkaf/rootfs.ext4`（真实 Buildroot，`-snapshot` 只读保护）
- 启动链：UEFI → 内核 → initramfs(SIMBOOT) → chroot 真实 rootfs → 运行真实 `/usr/bin/mfp.afx`

## 依赖项记录

### D-01：真实 RK3588 内核无法在 QEMU virt 启动

- **错误原文**：`qemu-boot-02.log` 0 字节；内核无 PL011 串口输出
- **缺失项**：真实 `kernel.img` 无 `virtio_*`、无 `pl011` 驱动（静态检查确认）；QEMU virt 机型依赖 virtio 磁盘 + PL011 串口
- **处理**：改用 Alpine `linux-virt` 通用 ARM64 内核（6.12.103），配套 initramfs 与模块
- **验证**：内核 6.12.103 正常启动至用户态 ✓

### D-02：initramfs 缺 ext4 模块（Alpine virt 内核 ext4=m）

- **错误原文**：`mount: mounting /dev/vda on /sysroot failed: Invalid argument`
- **缺失项**：`ext4.ko`（及依赖 jbd2/mbcache/crc32c/crc16），Alpine virt 内核 `CONFIG_EXT4_FS=m`
- **处理**：从 `linux-virt-6.12.103-r0.apk` 提取 7 个 `.ko.gz` 注入自制 initramfs，手写 `modules.dep`
- **验证**：ext4 加载成功，rootfs 挂载成功 ✓

### D-03：initramfs 打包丢失执行位

- **错误原文**：`Failed to execute /init (error -13)`（EACCES）
- **缺失项**：重打包 cpio 时文件 mode 全部变为 0644
- **处理**：`build_initramfs.py` 从原始 cpio 恢复每个文件的 mode
- **验证**：`/init` 0755，正常执行 ✓

### D-04：busybox modprobe 无法发现注入模块

- **错误原文**：`modprobe: FATAL: Module virtio_blk not found in directory /lib/modules/...`
- **缺失项**：busybox modprobe 的模块发现机制与预期不符（modules.dep 完整仍找不到）
- **处理**：SIMBOOT 改用 `insmod` 按依赖顺序显式加载（virtio_blk → crc16 → crc32c → mbcache → jbd2 → ext4）
- **验证**：模块全部加载，`/dev/vda` 出现 ✓

### D-05：`/dev/binder` 缺失（Android Binder IPC）★第一个真实固件依赖

- **错误原文**：`binder: cannot open device (No such file or directory)`（连续 2 次）
- **缺失项**：`/dev/binder` 字符设备（binder 驱动，Android IPC）
- **处理**：未处理（第一阶段记录）。rootfs 无 binder 驱动/模块；Virtualize 需内核 binder 驱动或 LD_PRELOAD stub
- **验证**：待处理

### D-06：加密密钥缺失

- **错误原文**：`error:miss key;line:=`
- **缺失项**：加密密钥（NVRAM / 加密模块所需）
- **处理**：未处理（记录，待分析 libnvram/加密逻辑）
- **验证**：待处理

### D-07：NVRAM 数据库表缺失 → **已解决（建表成功）**

- **错误原文**：`_table_check:96L- sqlite3_step error:no more rows available`（重复多次）
- **缺失项**：nvram 初始化时查询的 sqlite 表不存在/无行
- **处理**：推进启动链（绕过 pcie 阻塞）后，sql_init 自动建表
- **验证**：`create table:int/uint/string/struct success` + `insert default value` ✓

### D-08：`/dev/dma_heap/system` 缺失（DMA-BUF heap）★当前阻塞点

- **错误原文**：`<init_fd:138>:open /dev/dma_heap/system failed: No such file or directory`
- **缺失项**：DMA-BUF heap 字符设备（内核 `CONFIG_DMABUF_HEAPS` 提供），用于图像内存
- **处理**：未处理（记录）。Virtualize 需内核 dma-heap 支持或伪设备（mknod c 10 x + 可 mmap）
- **验证**：待处理；`pi_imagemem_init:67` imagemem init failed 后 mfp.afx 继续推进（可恢复）

### D-09：`/dev/netlog_dev` 缺失（网络日志设备）

- **错误原文**：`faccessat /dev/netlog_dev = -1 ENOENT`（线程 412 高频轮询）
- **处理**：未处理（记录）
- **验证**：待处理

### D-10：守护进程 Unix socket 缺失 → **部分解决（真实服务启动）**

- **错误原文**：`connect AF_UNIX /tmp/.logserver = -1 ENOENT`、`faccessat /tmp/.pntp_service = -1 ENOENT`
- **缺失项**：`/tmp/.logserver`（libplog 日志服务，提供者 `/usr/bin/plog_daemon`）、
  `/tmp/.pntp_service`（pntp 服务，提供者 `/usr/bin/pntp_service`）
- **处理**：guest 内启动真实 `plog_daemon` → logserver 连接成功（=0）✓；
  `pntp_service` 启动但**启动后退出**（`pol log destruct`）→ pntp 连接 ECONNREFUSED（待查退出原因）
- **验证**：logserver ✓；pntp 待处理

### D-11：日志/配置文件缺失（可恢复）

- **错误原文**：`PLOG_JSON parse /configs/plog/plog_json_config.json error, reset config`
- **缺失项**：`/configs/plog/plog_json_config.json`、`/tslog/pol_log`
- **处理**：plog 自动 reset config，不阻塞
- **验证**：plog lib init 正常 ✓

### D-12：`/sys/kernel/config/pci_ep/` 缺失（PCI EP 配置）

- **错误原文**：`faccessat /sys/kernel/config/pci_ep/ = -1 ENOENT`
- **处理**：未处理（记录）。内核无 configfs pci_ep 支持
- **验证**：待处理

## 已确认的真实动态链接依赖（mfp.afx 实际加载成功，strace 证据）

以下库全部 `openat` 成功并 mmap，无一失败：
libhal.so、libcommon.so、libevent_mgr.so、libosal.so、libsqlite3mc.so.0、libssl.so.3、
libcrypto.so.3、libcjson.so.1、libparser_ips.so、libm.so.6、libz.so.1、libusb-1.0.so.0、
libcurl.so.4、libnvram.so、libipm.so、libptencryption.so、libplog.so、libc.so.6、
libgcc_s.so.1、libofd.so、libudev.so.1、libatomic.so.1、libopencv_{core,imgproc,imgcodecs,video,videoio}.so.409、
libimageproc.so、libgstreamer-1.0.so.0、libgst{base,app,riff,pbutils,video,audio,tag}-1.0.so.0、
libturbojpeg.so.0、libglib-2.0.so.0、libgobject-2.0.so.0、libgmodule-2.0.so.0、
libpcre2-8.so.0、libpthread.so.0、libdl.so.2、libffi.so.8、librga.so.2、libdrm.so.2、
libmali.so.1（58MB）

> 说明：`/lib64/...` 路径为 symlink 解析到 `usr/lib`，动态链接器 `ld-linux-aarch64.so.1` 工作正常。
