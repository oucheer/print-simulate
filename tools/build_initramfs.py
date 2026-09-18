#!/usr/bin/env python3
"""build_initramfs.py — 构建含 ext4 模块的 Alpine initramfs（6.12.103 配套）

从解包好的 initramfs-x（6.12.81）出发：
1. 替换模块目录为 linux-virt apk 中的 6.12.103-0-virt（仅引导所需模块）
2. 手写 modules.dep 使 busybox modprobe 能解析依赖
3. 恢复解包时降级的 symlink（内容以 LINK-> 开头）
4. 重新打包为 cpio newc + gzip；文件 mode 从原始 cpio 恢复（避免丢失执行位）
"""
import gzip, os, shutil, struct

SRC = r"tools\kernel\initramfs-x"
DST = r"tools\kernel\initramfs-new"
MOD_VER_NEW = "6.12.103-0-virt"
MOD_VER_OLD = "6.12.81-0-virt"
MOD_SRC = r"tools\kernel\linux-virt-x\lib\modules" + "\\" + MOD_VER_NEW
ORIG_CPIO = r"tools\kernel\initramfs-virt.cpio"
OUT = r"tools\kernel\initramfs-new.gz"

NEEDED = {
    r"kernel\fs\ext4\ext4.ko.gz",
    r"kernel\fs\jbd2\jbd2.ko.gz",
    r"kernel\fs\mbcache.ko.gz",
    r"kernel\crypto\crc32c_generic.ko.gz",
    r"kernel\lib\crc16.ko.gz",
    r"kernel\drivers\block\virtio_blk.ko.gz",
    r"kernel\drivers\virtio\virtio_mmio.ko.gz",
    r"kernel\drivers\net\ethernet\intel\e1000\e1000.ko.gz",
}
MODULES_DEP = """\
kernel/fs/ext4/ext4.ko.gz: kernel/fs/jbd2/jbd2.ko.gz kernel/fs/mbcache.ko.gz kernel/crypto/crc32c_generic.ko.gz kernel/lib/crc16.ko.gz
kernel/fs/jbd2/jbd2.ko.gz: kernel/crypto/crc32c_generic.ko.gz
kernel/fs/mbcache.ko.gz:
kernel/crypto/crc32c_generic.ko.gz:
kernel/lib/crc16.ko.gz:
kernel/drivers/block/virtio_blk.ko.gz:
kernel/drivers/virtio/virtio_mmio.ko.gz:
kernel/drivers/net/ethernet/intel/e1000/e1000.ko.gz:
"""

ORIG_MODES = {}


def load_orig_modes(cpio_path):
    """读取原始 cpio 的 name->mode 映射（用于恢复文件权限）"""
    data = open(cpio_path, "rb").read()
    pos = 0
    FIELDS = ["ino", "mode", "uid", "gid", "nlink", "mtime", "filesize",
              "devmajor", "devminor", "rdevmajor", "rdevminor", "namesize", "check"]
    while pos + 110 <= len(data):
        if data[pos:pos+6] != b"070701":
            break
        vals = {}
        for i, fn in enumerate(FIELDS):
            vals[fn] = int(data[pos+6+i*8:pos+14+i*8], 16)
        name = data[pos+110:pos+110+vals["namesize"]].rstrip(b"\0").decode()
        pad = (4 - (110 + vals["namesize"]) % 4) % 4
        co = pos + 110 + vals["namesize"] + pad
        cpad = (4 - vals["filesize"] % 4) % 4
        pos = co + vals["filesize"] + cpad
        if name == "TRAILER!!!":
            break
        ORIG_MODES[name] = vals["mode"]
    print("orig modes loaded:", len(ORIG_MODES))


def build():
    if os.path.exists(DST):
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    old_mod = os.path.join(DST, "lib", "modules", MOD_VER_OLD)
    new_mod = os.path.join(DST, "lib", "modules", MOD_VER_NEW)
    if os.path.exists(old_mod):
        shutil.rmtree(old_mod)
    os.makedirs(new_mod, exist_ok=True)
    for rel in NEEDED:
        src = os.path.join(MOD_SRC, rel)
        dst = os.path.join(new_mod, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    with open(os.path.join(new_mod, "modules.dep"), "w", newline="\n") as f:
        f.write(MODULES_DEP)
    with open(os.path.join(new_mod, "modules.alias"), "w", newline="\n") as f:
        f.write("")
    # 注入 binder 拦截库（LD_PRELOAD，拦截 /dev/binder 的 openat/ioctl/mmap 等）
    binder_src = os.path.join("tools", "binder_stub.so")
    if os.path.exists(binder_src):
        shutil.copy2(binder_src, os.path.join(DST, "lib", "binder_stub.so"))
        print("binder stub injected:", binder_src)
    # 生成 XOR 加密的机器配置（固件 platform_decode_ini_file 用 'xxxaaabbbcccxxx' 逐字节 XOR 解出明文）
    xor_key = b"xxxaaabbbcccxxx"
    ini_plain = b"[DeviceInfo]\nmachine_tag=0x1\nmfg_name=PANTUM\nseries_name=CM806ADN\nproduct_name=CM806ADN\nspeed=30\ncountry_code=0\n"
    ini_enc = bytes(b ^ xor_key[i % len(xor_key)] for i, b in enumerate(ini_plain))
    os.makedirs(os.path.join(DST, "root"), exist_ok=True)
    with open(os.path.join(DST, "root", "en_machine_config.ini"), "wb") as f:
        f.write(ini_enc)
    print("encrypted machine config injected")
    # 注入调试块：在 Mounting root 前输出模块加载诊断
    init_path = os.path.join(DST, "init")
    txt = open(init_path, encoding="utf-8", errors="replace").read()
    dbg = r'''# ==== SIM BOOT ====
echo "SIMBOOT: kernel=$(uname -r)"
M=/lib/modules/$(uname -r)
insmod $M/kernel/drivers/block/virtio_blk.ko.gz 2>&1
insmod $M/kernel/lib/crc16.ko.gz 2>&1
insmod $M/kernel/crypto/crc32c_generic.ko.gz 2>&1
insmod $M/kernel/fs/mbcache.ko.gz 2>&1
insmod $M/kernel/fs/jbd2/jbd2.ko.gz 2>&1
insmod $M/kernel/fs/ext4/ext4.ko.gz 2>&1
insmod $M/kernel/drivers/net/ethernet/intel/e1000/e1000.ko.gz 2>&1
lsmod 2>&1 | head -20
sleep 1
mkdir -p /sysroot
mount -t ext4 -o rw /dev/vda /sysroot 2>&1
mount -o bind /dev /sysroot/dev 2>&1
mount -t proc proc /sysroot/proc 2>&1
mount -t sysfs sysfs /sysroot/sys 2>&1
mount -t tmpfs tmpfs /sysroot/tmp 2>&1
mount -t tmpfs tmpfs /sysroot/tslog 2>&1
cp /lib/binder_stub.so /sysroot/lib/libbinder_stub.so
cp /root/en_machine_config.ini /sysroot/root/en_machine_config.ini
printf '\x20\x00\x80\x52\xc0\x03\x5f\xd6' | dd of=/sysroot/usr/bin/mfp.afx bs=1 seek=2087624 conv=notrunc 2>/dev/null; echo "SIMBOOT: baked netdata_get_lpd_switch->mov w0,#1;ret"
# gdb 脚本与 chroot payload 用 heredoc 写入 /sysroot/tmp（chroot 内即 /tmp），
# 避免嵌套引号转义；payload 独立成文件便于后续迭代
cat > /sysroot/tmp/gdbtrace.txt << 'SIMBOOT_GDBTRACE'
set pagination off
set print thread-events off
set height 0
handle SIGSTOP nostop noprint pass
handle SIGCONT nostop noprint pass
b *0x683e0c
commands
silent
printf "T1 lpd_netproxy_handler\n"
continue
end
b *0x6831e8
commands
silent
printf "T1 lpd_list_add\n"
continue
end
b *0x6830a4
commands
silent
printf "T1 lpd_start_job\n"
continue
end
b *0x68236c
commands
silent
printf "T1 lpd_task_read\n"
continue
end
b *0x68365c
commands
silent
printf "T1 lpd_dispatch_thread\n"
continue
end
b *0x683510
commands
silent
printf "T1 lpd_list_take\n"
continue
end
b *0x66c12c
commands
silent
printf "T1 net_socket_accept_connection\n"
continue
end
b *0x6838f4
commands
silent
printf "T1 lpd_task_create\n"
continue
end
b *0x683f84
commands
silent
printf "T1 lpd_netproxy_error_handler\n"
continue
end
b *0x684050
commands
silent
printf "T1 lpd_update_callback\n"
continue
end
# s6z：显式武装标记，替代靠 "Breakpoint N at" 编号判断（编号会随断点增删漂移，
# s6y 就是靠 ^Breakpoint 8 at 判断的，一旦断点数量变化判定即失效）
printf "TRACE1 armed\n"
continue
SIMBOOT_GDBTRACE
cat > /sysroot/tmp/gdbtrace2.txt << 'SIMBOOT_GDBTRACE2'
set pagination off
set print thread-events off
set height 0
handle SIGSTOP nostop noprint pass
handle SIGCONT nostop noprint pass
b *0x6838f4
commands
silent
printf "T2 lpd_task_create\n"
continue
end
b *0x676ec4
commands
silent
printf "T2 pcie_send_mod2pcie\n"
continue
end
b *0x61fbf8
commands
silent
printf "T2 setter_internal_event\n"
continue
end
b *0x74c960
commands
silent
printf "T2 ibc_type0a\n"
continue
end
b *0x74c38c
commands
silent
printf "T2 pedk_disp\n"
continue
end
b *0x6b7570
commands
silent
printf "T2 job_disp_6b7570\n"
continue
end
b *0x6b6adc
commands
silent
printf "T2 sub514_6b6adc\n"
continue
end
b *0x6b6b64
commands
silent
printf "T2 sub516_6b6b64\n"
continue
end
b *0x6b7060
commands
silent
printf "T2 sub518_6b7060\n"
continue
end
b *0x6b740c
commands
silent
printf "T2 sub519_6b740c\n"
continue
end
b *0x6b7500
commands
silent
printf "T2 sub51a_6b7500\n"
continue
end
b *0x6b7158
commands
silent
printf "T2 sub51c_6b7158\n"
continue
end
continue
SIMBOOT_GDBTRACE2
cat > /sysroot/tmp/gdbpatch.txt << 'SIMBOOT_GDBPATCH'
set pagination off
set print thread-events off
printf "B4: 5c=%d 7c=%d 80=%d 82=%d\n", *(unsigned char*)(0xa91370+0x5c), *(unsigned int*)(0xa91370+0x7c), *(unsigned short*)(0xa91370+0x80), *(unsigned char*)(0xa91370+0x82)
set *(unsigned char*)(0xa91370+0x5c)=1
set *(unsigned int*)(0xa91370+0x7c)=1
set *(unsigned short*)(0xa91370+0x80)=1
set *(unsigned char*)(0xa91370+0x82)=1
printf "AF: 5c=%d 7c=%d 80=%d 82=%d\n", *(unsigned char*)(0xa91370+0x5c), *(unsigned int*)(0xa91370+0x7c), *(unsigned short*)(0xa91370+0x80), *(unsigned char*)(0xa91370+0x82)
detach
SIMBOOT_GDBPATCH
cat > /sysroot/tmp/gdbhold.txt << 'SIMBOOT_GDBHOLD'
set pagination off
set print thread-events off
set height 0
set confirm off
handle SIGSTOP nostop noprint pass
handle SIGCONT nostop noprint pass
set *(unsigned char*)(0xa91370+0x5c)=1
set *(unsigned int*)(0xa91370+0x7c)=1
set *(unsigned short*)(0xa91370+0x80)=1
set *(unsigned char*)(0xa91370+0x82)=1
printf "HOLD armed\n"
watch *(unsigned int*)(0xa91370+0x7c)
commands
silent
set *(unsigned char*)(0xa91370+0x5c)=1
set *(unsigned int*)(0xa91370+0x7c)=1
set *(unsigned short*)(0xa91370+0x80)=1
set *(unsigned char*)(0xa91370+0x82)=1
continue
end
continue
SIMBOOT_GDBHOLD
cat > /sysroot/tmp/gdbcmd.txt << 'SIMBOOT_GDBCMD'
set pagination off
set print thread-events off
set $h = *(long*)0x910e20
set $i = 0
while $h != 0 && $i < 60
printf "node=%p cmd=%#x cb=%p arg=%p\n", $h, *(int*)($h+0x10), *(long*)($h+0x18), *(long*)($h+0x20)
set $h = *(long*)$h
set $i = $i + 1
end
detach
SIMBOOT_GDBCMD
cat > /sysroot/tmp/simboot_payload.sh << 'SIMBOOT_PAYLOAD'
#!/bin/sh
# SIMBOOT payload（s6m）：真实 rootfs 内启动真实 mfp.afx，并在业务初始化后立刻开放注入窗口
mknod /dev/pantumpci-main c 1 5 2>&1
mknod /dev/pantumpci-main-video c 1 5 2>&1
mknod /dev/pantumpci-plog c 1 5 2>&1
mknod /dev/pantumpci-upgrade c 1 5 2>&1
mknod /dev/pantumpci-scan c 1 5 2>&1
mknod /dev/pantumpci-transfer-video c 1 5 2>&1
mknod /dev/pantumpci-transfer-cis c 1 5 2>&1
mknod /dev/board_desc c 1 5 2>&1
mknod /dev/netlog_dev c 1 5 2>&1
mkdir -p /tmp/.plog /tslog /configs/plog /tmp
touch /tslog/pol_log
# 关闭 THP/khugepaged：s6o 观测到 khugepaged 在内存压力下软锁死（uptime 1070s）
for f in /sys/kernel/mm/transparent_hugepage/enabled /sys/kernel/mm/transparent_hugepage/defrag; do
  [ -w "$f" ] && echo never > "$f" 2>/dev/null
done
[ -w /sys/kernel/mm/transparent_hugepage/khugepaged/defrag ] && echo 0 > /sys/kernel/mm/transparent_hugepage/khugepaged/defrag 2>/dev/null
[ -w /sys/kernel/mm/transparent_hugepage/khugepaged/scan_sleep_millisecs ] && echo 120000 > /sys/kernel/mm/transparent_hugepage/khugepaged/scan_sleep_millisecs 2>/dev/null
echo "THP_ENABLED=$(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null)"
echo "THP_DEFRAG=$(cat /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null)"
cat > /etc/plog_json_config.json << 'PLOGJSON'
{"log_state":1,"log_level":2,"log_path":"/tslog","log_size":5120,"machine_name":"RK3588","machine_id":0,"dev_id":0,"root_node":"root","default_topic":"PLOG_PUB","tcp_server_state":0,"upgrade_log_state":0,"ui_connect":0,"debug_mode":0,"slave_config":{"slave_dev_id":0},"slave_dev_id":0,"topic_config":[{"topic_name":"PLOG_PUB","topic_id":0,"console":0,"log_level":2,"subscription":0,"cache_size":512,"auto_register":1,"abort_flag":0,"local_dump":0,"debug_mode":0,"state":1}]}
PLOGJSON
for d in /var /data /configs /settings; do
  mkdir -p /tmp/r$d
  cp -a $d/. /tmp/r$d/ 2>/dev/null
  mount -t tmpfs -o size=512M tmpfs $d
  cp -a /tmp/r$d/. $d/ 2>/dev/null
done
(/usr/bin/plog_daemon > /plogd.log 2>&1 &)
sleep 5
(/usr/bin/hal_daemon > /hald.log 2>&1 &)
sleep 3
# s7（计划 §2.4）：mfp 会轮询 /tmp/.pntp_service，缺失时 peer/netproxy 数据路径不通
# （s6z 证据：LPD 端口 accept 成功 1 条连接，但 lpd_netproxy_handler 等 10 个入口断点零命中，
#   且 net_proxy_data_thread_handle 线程在 IBC _wait_for_peer 自旋）。
# 这里直接运行与本 rootfs 同源的真实 pntp_service，看能否补齐 mfp 依赖的本地服务端。
(/usr/bin/pntp_service > /pntp.log 2>&1 &)
PNTP=$!
sleep 5
echo "PNTP_PID=$PNTP"
if kill -0 $PNTP 2>/dev/null; then echo "PNTP_ALIVE=1"; else echo "PNTP_ALIVE=0"; fi
ls -la /tmp/.pntp_service 2>&1
tail -20 /pntp.log 2>&1
ip link set eth0 up 2>&1
ip addr add 10.0.2.15/24 dev eth0 2>&1
ip route add default via 10.0.2.2 2>&1
ip link set lo up 2>&1
echo "=== VHAL: fetch toolchain ==="
rc=1
for t in 1 2 3 4 5; do
  wget -q -O /tmp/musl-native.tar http://10.0.2.2:8000/musl-native.tar 2>&1
  rc=$?
  if [ $rc -eq 0 ] && [ -s /tmp/musl-native.tar ]; then break; fi
  echo "VHAL_WGET_TC_RETRY t=$t rc=$rc"
  sleep 6
done
echo "VHAL_WGET_TC_RC=$rc"
ls -la /tmp/musl-native.tar 2>&1
rc=1
for t in 1 2 3 4 5; do
  wget -q -O /tmp/virtual_hal.c http://10.0.2.2:8000/virtual_hal.c 2>&1
  rc=$?
  if [ $rc -eq 0 ] && [ -s /tmp/virtual_hal.c ]; then break; fi
  echo "VHAL_WGET_SRC_RETRY t=$t rc=$rc"
  sleep 6
done
echo "VHAL_WGET_SRC_RC=$rc"
ls -la /tmp/virtual_hal.c 2>&1
echo "=== VHAL: extract ==="
cd /tmp && tar -xf /tmp/musl-native.tar 2>&1
echo "VHAL_TAR_RC=$?"
ls -la /tmp/aarch64-linux-musl-native/bin/aarch64-linux-musl-gcc 2>&1
echo "=== VHAL: compile ==="
/tmp/aarch64-linux-musl-native/bin/aarch64-linux-musl-gcc -nostdlib -fPIC -shared -o /lib/virtual_hal.so /tmp/virtual_hal.c 2>&1
echo "VHAL_GCC_RC=$?"
ls -la /lib/virtual_hal.so 2>&1
if [ ! -s /lib/virtual_hal.so ]; then echo "VHAL_MISSING_TOOLCHAIN_DOWN"; fi
echo "=== VHAL: done ==="
# 释放 /tmp(tmpfs) 中的 toolchain：s6p 证据显示内存压力下 fork/exec 会慢到数分钟
rm -rf /tmp/aarch64-linux-musl-native /tmp/musl-native.tar /tmp/virtual_hal.c 2>/dev/null
sync
# 不 drop_caches：s6r 观测到清空 page cache 后每次 fork/exec 变冷读（约 1s/次），
# 会把 find_lpd/诊断循环拖死。改为预热后续循环要用的二进制。
for b in ls awk sort uniq wc sleep grep readlink gdb; do
  $b --help > /dev/null 2>&1
done
echo "CACHE_WARMED"
head -4 /proc/meminfo 2>&1
cd /
export LD_PRELOAD=/lib/libbinder_stub.so:/lib/virtual_hal.so
export LD_BIND_NOW=1
ulimit -n 4096 2>/dev/null
echo "SIMBOOT_PREP_DONE"
# mfp stdout 是启动进度与报错的唯一来源（main 里每个 prolog 前后都有 "----xxx----init/end----" 标记）。
# s6k 教训：直接重定向到文件会涨到 GB 并把脚本拖死。这里用 FIFO + head -c 只保留前 40MB，
# 之后由 cat 继续排空管道 —— 既不落盘增长，也不会对 mfp 产生 SIGPIPE/写阻塞。
mkfifo /tmp/mfp.fifo 2>/dev/null
# mfp stdout 进度/报错摘要（启动进度标记 + 关键字报错 + 尾部）
mfp_log_progress() {
  TAG=$1
  if [ ! -s /tslog/mfp.out ]; then echo "--- $TAG: MFP LOG EMPTY/ABSENT ---"; return; fi
  echo "--- $TAG: MFP LOG size=$(wc -c < /tslog/mfp.out 2>/dev/null) ---"
  # s6w/s6y 事故：mfp 启动后 IBC _wait_for_peer:747 报错死循环持续刷屏（实测该快照 102214 行中
  # 101631 行是刷屏，占 99.4%，且从第 6 行就开始），guest 侧对 8MB 快照做 grep -i 多分支匹配在 TCG
  # 下要数分钟甚至更久，期间 READY FOR INJECT 永不出现，注入窗口整轮作废。
  # 结论（s6z 起）：guest 只做【有界 dd 快照 + 原样回传】，所有文本分析一律移到宿主侧完成。
  dd if=/tslog/mfp.out of=/tmp/mfp.snap bs=1048576 count=4 2>/dev/null
  echo "--- $TAG: SNAP size=$(wc -c < /tmp/mfp.snap 2>/dev/null) ---"
  echo "--- $TAG: MFP LOG TAIL ---"
  tail -12 /tmp/mfp.snap 2>/dev/null
}
( head -c 41943040 > /tslog/mfp.out; cat > /dev/null ) < /tmp/mfp.fifo &
echo "MFP_LOG_READER_PID=$!"
/usr/bin/mfp.afx > /tmp/mfp.fifo 2>&1 &
MFP=$!
echo "MFP_PID=$MFP"
unset LD_PRELOAD
# 查找 mfp 拥有的 LISTEN socket（LPD 用临时端口，非 515）
find_lpd() {
  IN=""
  ALL=""
  # 单次 awk 关联 fd -> socket inode -> LISTEN 端口（避免每个 fd 一次 fork：s6r 冷读下 ~1s/次）
  ROWS=$(ls -l /proc/$MFP/fd/ 2>/dev/null | awk '
    /-> *socket:\[/ { fd=$9; ino=$NF; gsub(/socket:\[/,"",ino); gsub(/\]/,"",ino); fds[ino]=fd }
    END {
      while ((getline line < "/proc/net/tcp") > 0) {
        n=split(line, f, " ")
        if (n < 10) continue
        if (f[4] != "0A") continue
        if (!(f[10] in fds)) continue
        split(f[2], a, ":"); printf "%s %s %s\n", fds[f[10]], f[10], a[2]
      }
    }' 2>/dev/null)
  while read -r FDD INO P; do
    [ -z "$P" ] && continue
    echo "LPD_OWNED fd=$FDD ino=$INO decport=$((16#$P))"
    ALL="$ALL $P"
    [ -z "$IN" ] && IN=$P
  done <<EOF
$ROWS
EOF
}
# 快速等待业务初始化：N>=44 时打 print-ready 标志（0xa91370+0x5c/0x7c/0x80/0x82），
# 该 patch 是 print_info_status_init 解锁的关键（打上后线程数 45 -> 179）
GDBTRIES=0
# 常驻 watch 会话：0xa91370+0x5c/0x7c/0x80/0x82 会被 mfp 自身状态刷新重置（s6s POLL24
# 实测 B4 从 1 变回 0），一次性 patch 只靠运气；这里用硬件 watchpoint 在每次写回后立刻重置 1
sleep 10
nohup gdb -p $MFP -batch -x /tmp/gdbhold.txt > /tmp/gdbhold.out 2>&1 &
HOLDPID=$!
echo "GDBHOLD STARTED pid=$HOLDPID"
# s6v 教训：gdb attach 一个上百线程的进程要几十秒（期间输出全是 [New LWP ...]），
# 固定 sleep 8 会把还在 attach 的会话误判为失败。这里轮询等 "HOLD armed"，最多 60s。
HOLD_OK=0
for w in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if grep -a -q "HOLD armed" /tmp/gdbhold.out 2>/dev/null; then HOLD_OK=1; echo "HOLD_ARMED wait=${w}x3s"; break; fi
  if ! kill -0 $HOLDPID 2>/dev/null; then echo "GDBHOLD_EXITED wait=${w}x3s"; break; fi
  sleep 3
done
if [ "$HOLD_OK" = "0" ]; then
  # hold 会话没能武装（脚本报错或超时）：收掉它并解除 group-stop，让下面的 gdbpatch 兜底
  kill $HOLDPID 2>/dev/null
  sleep 5
  kill -CONT $MFP 2>/dev/null
  echo "GDBHOLD DISARMED"
fi
echo "HOLD_OK=$HOLD_OK"
head -6 /tmp/gdbhold.out 2>&1
for i in $(seq 1 400); do
  N=$(awk 'END{print NR}' /proc/$MFP/task/*/comm 2>/dev/null)
  N=${N:-0}
  if [ "$N" -gt 100 ]; then
    echo "POLL $i: passed print_info_status_init (N=$N)"
    break
  fi
  if [ "$N" -ge 20 ] && [ "$HOLD_OK" = "0" ] && [ "$GDBTRIES" -lt 8 ]; then
    echo "--- GDBPATCH @POLL$i (N=$N) try=$((GDBTRIES+1)) ---"
    timeout 40 gdb -p $MFP -batch -x /tmp/gdbpatch.txt 2>&1 | tail -4
    GDBTRIES=$((GDBTRIES+1))
  fi
  if [ $((i % 10)) -eq 0 ]; then echo "POLL $i: N=$N"; fi
  sleep 1
done
echo "POLL_END N=$N tries=$GDBTRIES"
# 解锁后结束常驻 watch 会话，避免与后续 trace1/BT 的 gdb 抢占 ptrace
kill $HOLDPID 2>/dev/null
sleep 3
kill -CONT $MFP 2>/dev/null
sleep 2
echo "GDBHOLD STOPPED N=$(awk 'END{print NR}' /proc/$MFP/task/*/comm 2>/dev/null)"
tail -8 /tmp/gdbhold.out 2>&1
LPDHEX=""
LPD_ALL=""
for k in $(seq 1 40); do
  find_lpd
  LPDHEX=$IN
  LPD_ALL=$ALL
  if [ -n "$LPDHEX" ]; then echo "LPD_SOCK_READY k=$k"; break; fi
  echo "WAIT_LPD_SOCK k=$k N=$(ls /proc/$MFP/task 2>/dev/null | wc -l)"
  sleep 3
done
if [ -n "$LPDHEX" ]; then
  echo "SIMBOOT_LPD_PORT=$((16#$LPDHEX))"
  echo "SIMBOOT_LPD_PORTS=${LPD_ALL# }"
else
  echo "SIMBOOT_LPD_PORT=NONE"
  echo "SIMBOOT_LPD_PORTS="
fi
# 注入前的线程级证据：单进程 awk 一次性读取（避免 196×N 次 fork 在内存压力下龟速）
# s6p 教训：所有线程 comm 都是 mfp.afx（无区分度），必须靠 wchan/栈定位
thread_dump() {
  TAG=$1
  echo "--- $TAG: THREADS (tid comm wchan) ---"
  awk '
    FILENAME ~ /\/wchan$/ { w[FILENAME]=$0; next }
    FILENAME ~ /\/comm$/  { c[FILENAME]=$0; next }
    END {
      for (f in w) {
        d=f; sub(/\/wchan$/,"",d); split(d,a,"/"); tid=a[5]
        printf "%s %s %s\n", tid, (c[d "/comm"]==""?"?":c[d "/comm"]), w[f]
      }
    }' /proc/$MFP/task/*/wchan /proc/$MFP/task/*/comm 2>/dev/null | sort -n
  echo "--- $TAG: WCHAN HIST ---"
  awk 'FILENAME ~ /\/wchan$/ { print $0 }' /proc/$MFP/task/*/wchan 2>/dev/null | sort | uniq -c | sort -rn | head -25
  # s6z 新增：/proc/<tid>/syscall 直接给出"该线程停在哪个系统调用 + 第一个参数（通常是 fd）"，
  # 用于判定是否有线程在 accept/recv 哪个 fd 上（LPD 监听 socket 的 fd 可从 SOCKET FDS 段拿到）。
  # 注意：必须在 gdb 已释放 ptrace 之后调用，否则被 ptrace 的线程读该文件会返回 EBUSY。
  echo "--- $TAG: THREAD SYSCALLS (path: nr arg0..arg5 sp pc) ---"
  awk '{ print FILENAME": "$0 }' /proc/$MFP/task/*/syscall 2>/dev/null
}
echo "--- THREAD COUNT PRE-INJECT ---"
awk 'END{print NR}' /proc/$MFP/task/*/comm 2>/dev/null
echo "--- THREAD NAMES (top30) ---"
awk '{ c[$0]++ } END { for (k in c) printf "%d %s\n", c[k], k }' /proc/$MFP/task/*/comm 2>/dev/null | sort -rn | head -30
thread_dump PRE
echo "--- SOCKET FDS ---"
ls -l /proc/$MFP/fd/ 2>/dev/null | grep -a socket
# 注入前 trace：只挂 LPD 入口断点（低频，避免拖慢 179 线程进程）
# 有界快照 + 立即回传：mfp 会持续刷屏，run 后期随时可能 OOM，先把启动证据送回宿主
dd if=/tslog/mfp.out of=/tmp/mfp.pre bs=1048576 count=12 2>/dev/null
echo "MFP_PRE_SNAP=$(wc -c < /tmp/mfp.pre 2>/dev/null)"
wget -q -O /dev/null --post-file=/tmp/mfp.pre http://10.0.2.2:8001/upload/mfp-pre.out 2>&1
echo "MFP_PRE_UPLOAD_RC=$? size=$(wc -c < /tmp/mfp.pre 2>/dev/null)"
# 注入窗口内挂 LPD 入口 trace：s6t 的“连接从不被 accept”出现在常驻 watch 会话与被 trace 抢 ptrace 时；
# 本轮 hold 会话已在上面收掉，这里只挂入口级低频断点。s6w 事故：此处原为 GPID=$! 残留，trace 从未启动，
# 导致注入期间没有任何断点证据。改为真正启动 + 轮询等 attach/断点装载完成（attach 上百线程要几十秒），
# 否则 mfp 在 attach 期间是 stop 状态，watcher 恰好此时注入必然失败。
: > /tmp/gdbtrace.out
nohup gdb -p $MFP -batch -x /tmp/gdbtrace.txt > /tmp/gdbtrace.out 2>&1 &
GPID=$!
TRACE_OK=0
for w in $(seq 1 30); do
  if grep -a -qE 'TRACE1 armed' /tmp/gdbtrace.out 2>/dev/null; then TRACE_OK=1; echo "TRACE1_ARMED wait=${w}x2s"; break; fi
  if ! kill -0 $GPID 2>/dev/null; then echo "TRACE1_EXITED wait=${w}x2s"; break; fi
  sleep 2
done
echo "TRACE1 GDB STARTED pid=$GPID armed=$TRACE_OK"
tail -4 /tmp/gdbtrace.out 2>&1
mfp_log_progress PREREADY
echo "READY FOR INJECT"
# 注入窗口：宿主 watcher 数秒内 hostfwd + 发送 PWG 作业
sleep 180
echo "--- TRACE1 AFTER INJECT ---"
# s6z：必须先收掉 trace 再读 gdbtrace.out —— gdb 仍在运行时该文件会被持续追加，
# wc/grep 会像对活文件一样追不到 EOF（与 s6w 卡死同类风险）。
kill $GPID 2>/dev/null
sleep 2
kill -CONT $MFP 2>/dev/null
sleep 2
echo "TRACE1_STOPPED threads=$(ls /proc/$MFP/task 2>/dev/null | wc -l)"
wc -l /tmp/gdbtrace.out 2>&1
echo "TRACE1_HITS=$(grep -a -c 'T1 ' /tmp/gdbtrace.out 2>/dev/null)"
grep -a 'T1 ' /tmp/gdbtrace.out 2>/dev/null | head -20
tail -20 /tmp/gdbtrace.out 2>&1
echo "--- ALIVE ---"
ls /proc/$MFP/task 2>/dev/null | wc -l
echo "--- PORTS POST (full /proc/net/tcp) ---"
# 不截断：LPD 监听/已建立连接条目可能排在中后部，head -20 会截掉关键证据。
# 关键判据：注入后 LPD 端口若仍为 01(ESTABLISHED) 且 rx_queue 非 0，说明应用层从未 read。
cat /proc/net/tcp 2>&1
echo "--- PORTS POST tcp6 ---"
cat /proc/net/tcp6 2>&1 | head -10
echo "--- LPD OWNED POST ---"
find_lpd
echo "--- THREADS POST-INJECT ---"
thread_dump POST
mfp_log_progress POST
echo "--- MFP LOG UPLOAD (filtered tail) ---"
# s7：不再整份回传（40MB 里 99.4% 是 _wait_for_peer 刷屏，slirp 上传会把整轮拖死）。
# 取尾部 20MB（覆盖注入窗口时间段），guest 侧只做一次【固定串 -F】过滤
# （单模式固定串，不是 s6y 那种多分支 -i 正则，40MB 内秒级完成），回传过滤后的小文件。
tail -c 20971520 /tslog/mfp.out > /tmp/mfp.tail 2>/dev/null
echo "MFP_TAIL_SIZE=$(wc -c < /tmp/mfp.tail 2>/dev/null)"
grep -v -a -F '_wait_for_peer' /tmp/mfp.tail > /tmp/mfp.filt 2>/dev/null
echo "MFP_FILT_SIZE=$(wc -c < /tmp/mfp.filt 2>/dev/null)"
wget -q -O /dev/null --post-file=/tmp/mfp.filt http://10.0.2.2:8001/upload/mfp_post_filt.out 2>&1
echo "MFP_FILT_UPLOAD_RC=$? size=$(wc -c < /tmp/mfp.filt 2>/dev/null)"
echo "--- PLOG DIR ---"
ls -la /tslog 2>&1
for f in /tslog/*; do
  if [ -f "$f" ]; then echo "PLOG_FILE $f size=$(wc -c < "$f" 2>/dev/null)"; fi
done
# s6z：删除 guest 侧 PLOG JOB GREP（同为多分支 -i 匹配，一旦 plog 文件变大就会重演 s6y 卡死）。
# plog 文件一律原样回传，关键字检索在宿主侧做。
echo "--- TMP DIR + CMD PIPE PROBE ---"
# s7 新线索（8MB mfp.out 宿主侧分析）：mfp 已把整个打印子系统注册成文本命令
# （cmd register ok = print_parser - pwgfileprint / print - fileprint / print_parser - urffileprint ...），
# 命令框架在 libcommon.so（cmd_prolog/cmd_process_thread/cmd_register），管道路径 /tmp/cmd。
# 若网络前端被 peer 门控，这条内部通道是计划「决策 #7」的逃生路径，先做无副作用探测：
# 空/非法命令只会让框架打印 "invalid cmd!" 或列出可用子命令，不会启动打印。
ls -la /tmp 2>&1
if [ -e /tmp/cmd ]; then
  echo "CMD_PIPE_PRESENT $(ls -l /tmp/cmd 2>&1)"
  # 探测 1：非法主命令 -> 期望框架回 "invalid cmd!"
  timeout 5 sh -c 'echo "cmd_probe_invalid" > /tmp/cmd' 2>&1; echo "CMD_PROBE1_RC=$?"
  # 探测 2：只给主命令 -> 期望回 '"print_parser" supports subcmds below:' + 可用子命令清单（用来确定输入语法）
  timeout 5 sh -c 'echo "print_parser" > /tmp/cmd' 2>&1; echo "CMD_PROBE2_RC=$?"
  sleep 3
  # 探测 3：真正投一个 PWG 作业给真实 print_parser（绕过 LPD/peer 网络前端）
  wget -q -O /tmp/job.pwg http://10.0.2.2:8000/pwg-job-1page.pwg 2>&1
  echo "JOB_PWG_SIZE=$(wc -c < /tmp/job.pwg 2>/dev/null)"
  timeout 5 sh -c 'echo "print_parser - pwgfileprint /tmp/job.pwg" > /tmp/cmd' 2>&1; echo "CMD_PROBE3_RC=$?"
  sleep 5
  timeout 5 sh -c 'echo "print - fileprint /tmp/job.pwg" > /tmp/cmd' 2>&1; echo "CMD_PROBE4_RC=$?"
  sleep 5
else
  echo "CMD_PIPE_ABSENT"
fi
echo "--- PLOG UPLOAD ---"
for f in /tslog/*; do
  [ "$f" = "/tslog/mfp.out" ] && continue
  if [ -f "$f" ]; then
    wget -q -O /dev/null --post-file="$f" "http://10.0.2.2:8001/upload/plog_$(basename $f)" 2>&1
    echo "PLOG_UP $(basename $f) rc=$?"
  fi
done
echo "--- VHAL LOG ---"
tail -120 /tmp/vhal.log 2>&1
wget -q -O /dev/null --post-file=/tmp/vhal.log http://10.0.2.2:8001/upload/vhal.log 2>&1
echo "VHAL_UPLOAD_RC=$?"
# 注入后复核：trace1 已在注入窗口内挂载并回收（见 TRACE1 AFTER INJECT），此处只读静态文件复核
echo "TRACE1_POST_HITS=$(grep -a -c 'T1 ' /tmp/gdbtrace.out 2>/dev/null)"
grep -a 'T1 ' /tmp/gdbtrace.out 2>/dev/null | head -30
tail -6 /tmp/gdbtrace.out 2>&1
echo "--- AFTER TRACE1 KILL threads=$(ls /proc/$MFP/task 2>/dev/null | wc -l) ---"
# trace1 已结束，gdb 空闲：抓全部线程栈，定位 LPD accept/dispatch 线程卡在哪
# s6z：150s 在 179 线程 + TCG + 刷屏线程占 CPU 的情况下不够，放宽到 420s（超时会丢整轮证据）
echo "--- ALL BT (filtered) ---"
timeout 420 gdb -p $MFP -batch -ex "thread apply all bt 5" > /tmp/allbt.txt 2>&1
echo "ALLBT_RC=$? lines=$(wc -l < /tmp/allbt.txt 2>/dev/null)"
grep -a -n -E "^Thread|accept|lpd|net_|proxy|dispatch|sem_|nanosleep|recv|epoll|poll|read|pthread_cond|pi_mutex|pi_list" /tmp/allbt.txt 2>/dev/null | head -200
wget -q -O /dev/null --post-file=/tmp/allbt.txt http://10.0.2.2:8001/upload/allbt.txt 2>&1
echo "ALLBT_UP_RC=$?"
kill -CONT $MFP 2>/dev/null
sleep 2
thread_dump POSTBT
# 注入后 trace2：作业/引擎分发断点（低频）
nohup gdb -p $MFP -batch -x /tmp/gdbtrace2.txt > /tmp/gdbtrace2.out 2>&1 &
GPID2=$!
sleep 25
echo "--- TRACE2 ---"
wc -l /tmp/gdbtrace2.out 2>&1
tail -60 /tmp/gdbtrace2.out 2>&1
kill $GPID2 2>/dev/null
sleep 2
kill -CONT $MFP 2>/dev/null
sleep 2
echo "--- CMD REG TABLE (post) ---"
timeout 60 gdb -p $MFP -batch -x /tmp/gdbcmd.txt 2>&1 | tail -90
echo "--- HALD LOG ---"
tail -15 /hald.log 2>&1
echo "--- PLOGD LOG ---"
tail -15 /plogd.log 2>&1
echo "--- PNTP LOG (post) ---"
tail -30 /pntp.log 2>&1
ls -la /tmp/.pntp_service 2>&1
# s6z：同样删除 guest 侧 PLOG FINAL GREP（多分支 -i 匹配在 TCG 下有卡死风险，改为直接回传）
for f in /tslog/*; do
  [ "$f" = "/tslog/mfp.out" ] && continue
  if [ -f "$f" ]; then
    wget -q -O /dev/null --post-file="$f" "http://10.0.2.2:8001/upload/plog_final_$(basename $f)" 2>&1
  fi
done
wget -q -O /dev/null --post-file=/tmp/vhal.log http://10.0.2.2:8001/upload/vhal_final.log 2>&1
echo "--- POST PORTS ---"
cat /proc/net/tcp 2>&1
sleep 240
echo "SIMBOOT: mfp pid $MFP threads=$(ls /proc/$MFP/task 2>/dev/null | wc -l)"
echo "KEEPING MFP ALIVE"
SIMBOOT_PAYLOAD
chmod +x /sysroot/tmp/simboot_payload.sh
echo "SIMBOOT: root mounted rw, running real mfp.afx with binder stub"
chroot /sysroot /bin/sh /tmp/simboot_payload.sh 2>&1
echo "SIMBOOT: mfp run finished, keeping shell"
exec /bin/sh
# ==== SIM BOOT END ====
'''
    anchor = '\tebegin "Mounting root"'
    if dbg.strip() not in txt:
        txt = txt.replace(anchor, dbg + anchor, 1)
        open(init_path, "w", encoding="utf-8", newline="\n").write(txt)
    print("modules injected:", len(NEEDED))
    return DST


def cpio_add(out, name, data, mode, is_dir=False, is_link=False, link_target=""):
    fields = [0o100644 if is_dir else mode & 0o7777]
    ino = 1
    nlink = 2 if is_dir else 1
    mtime = 0
    if is_link:
        ftype = 0o120000
        payload = link_target.encode()
    elif is_dir:
        ftype = 0o040000
        payload = b""
    else:
        ftype = 0o100000
        payload = data
    namesize = len(name) + 1
    filesize = len(payload)
    hdr = [ino, ftype | (fields[0] & 0o7777), 0, 0, nlink, mtime, filesize,
           0, 0, 0, 0, namesize, 0]
    line = b"070701" + b"".join(b"%08x" % x for x in hdr)
    line += name.encode() + b"\0"
    line += b"\0" * ((4 - len(line) % 4) % 4)
    out.append(line)
    out.append(payload)
    out.append(b"\0" * ((4 - filesize % 4) % 4))


def pack(root, outpath):
    chunks = []
    entries = []
    for dirpath, dirs, files in os.walk(root):
        for d in sorted(dirs):
            full = os.path.join(dirpath, d)
            rel = os.path.relpath(full, root).replace("\\", "/")
            entries.append(("d", rel, full))
        for f in sorted(files):
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, root).replace("\\", "/")
            entries.append(("f", rel, full))
    all_dirs = set(r for k, r, _ in entries if k == "d")
    for kind, rel, full in entries:
        if kind == "d":
            continue
        parent = os.path.dirname(rel)
        while parent and parent not in all_dirs:
            cpio_add(chunks, parent, b"", 0o040755, is_dir=True)
            all_dirs.add(parent)
            parent = os.path.dirname(parent)
    for kind, rel, full in entries:
        if kind == "d":
            cpio_add(chunks, rel, b"", 0o040755, is_dir=True)
            continue
        data = open(full, "rb").read()
        if rel in ORIG_MODES:
            mode = ORIG_MODES[rel]
        else:
            mode = 0o100644
        if data.startswith(b"LINK->"):
            target = data[6:].decode(errors="replace").rstrip("\n")
            cpio_add(chunks, rel, b"", mode, is_link=True, link_target=target)
        else:
            cpio_add(chunks, rel, data, mode)
    cpio_add(chunks, "TRAILER!!!", b"", 0, is_dir=True)
    blob = b"".join(chunks)
    with open(outpath, "wb") as f:
        f.write(gzip.compress(blob, mtime=0))
    print("packed:", outpath, "cpio", len(blob), "gz", os.path.getsize(outpath))


if __name__ == "__main__":
    load_orig_modes(ORIG_CPIO)
    d = build()
    pack(d, OUT)
