/* virtual_hal.c — LD_PRELOAD 虚拟 HAL，拦截 libhal.so 的 pi_hal_* 导出
 *
 * 目的：mfp.afx 经 .rela.plt 导入 libhal.so 的 pi_hal_gpio_* / power_* / led_* 等。
 *       本库在 mfp.afx 进程内拦截这些调用：
 *         1) gpio/power/led 等硬件操作虚拟化为共享内存状态
 *         2) 全部调用参数写入 /tmp/vhal.log（证据收集）
 *         3) 与 virtual_printer daemon 通过共享内存文件通信
 *
 * 编译：aarch64-linux-musl-gcc -nostdlib -fPIC -shared -o virtual_hal.so virtual_hal.c
 * 用法：LD_PRELOAD=/virtual_hal.so /usr/bin/mfp.afx
 * 依赖：纯 syscall（aarch64 内联），无 libc，可被 glibc 进程安全加载。
 *
 * 共享内存文件：/dev/shm/vhal.shm（不存在则 /tmp/vhal.shm）
 *   布局见 vhal_shm 结构（magic 0x5648414C 校验）
 */
#define _GNU_SOURCE

/* ---- aarch64 syscall numbers ---- */
#define SYS_openat 56
#define SYS_close 57
#define SYS_write 64
#define SYS_ftruncate 46
#define SYS_mmap 222
#define SYS_munmap 215
#define SYS_unlink 83

/* ---- constants ---- */
#define AT_FDCWD (-100)
#define O_RDWR 2
#define O_CREAT 0100
#define O_APPEND 02000
#define O_CLOEXEC 02000000

#define MAP_SHARED 0x01
#define MAP_ANONYMOUS 0x20
#define PROT_READ 0x1
#define PROT_WRITE 0x2

#define SHM_PATH "/dev/shm/vhal.shm"
#define SHM_PATH2 "/tmp/vhal.shm"
#define SHM_MAGIC 0x5648414Cu   /* "VHAL" */
#define SHM_SIZE  8192

/* ---- 极简 syscall wrapper ---- */
static long syscall6(long n, long a, long b, long c, long d, long e, long f)
{
    register long x8 __asm__("x8") = n;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    register long x5 __asm__("x5") = f;
    __asm__ volatile("svc 0"
                     : "+r"(x0)
                     : "r"(x8), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
                     : "memory");
    return x0;
}
static long syscall3(long n, long a, long b, long c)
{
    return syscall6(n, a, b, c, 0, 0, 0);
}
static long syscall2(long n, long a, long b)
{
    return syscall6(n, a, b, 0, 0, 0, 0);
}
static long syscall1(long n, long a)
{
    return syscall6(n, a, 0, 0, 0, 0, 0);
}
static long syscall4(long n, long a, long b, long c, long d)
{
    return syscall6(n, a, b, c, d, 0, 0);
}

/* ---- 日志（写 /tmp/vhal.log，无缓冲逐行） ---- */
static int log_fd = -1;
static void log_open(void)
{
    if (log_fd >= 0)
        return;
    log_fd = (int)syscall4(SYS_openat, AT_FDCWD, (long)"/tmp/vhal.log",
                           O_CREAT | O_APPEND | O_RDWR, 0644);
}
static void log_write(const char *s, long n)
{
    log_open();
    if (log_fd >= 0 && n > 0)
        syscall3(SYS_write, log_fd, (long)s, n);
}
static void log_str(const char *s)
{
    const char *p = s;
    long n = 0;
    while (*p) { p++; n++; }
    log_write(s, n);
}
static void log_hexlbl(const char *lbl, long v)
{
    char buf[64];
    long i = 0, j;
    static const char hx[] = "0123456789abcdef";
    while (lbl[i]) { buf[i] = lbl[i]; i++; }
    buf[i++] = ':';
    buf[i++] = ' ';
    buf[i++] = '0';
    buf[i++] = 'x';
    for (j = 56; j >= 0; j -= 8)
        buf[i++] = hx[((unsigned long)v >> j) & 0xf];
    buf[i++] = '\n';
    log_write(buf, i);
}
static void log_u32(const char *lbl, unsigned long v)
{
    char buf[64];
    long i = 0;
    static const char hx[] = "0123456789abcdef";
    while (lbl[i]) { buf[i] = lbl[i]; i++; }
    buf[i++] = ':';
    buf[i++] = ' ';
    buf[i++] = '0';
    buf[i++] = 'x';
    buf[i++] = hx[(v >> 28) & 0xf];
    buf[i++] = hx[(v >> 24) & 0xf];
    buf[i++] = hx[(v >> 20) & 0xf];
    buf[i++] = hx[(v >> 16) & 0xf];
    buf[i++] = hx[(v >> 12) & 0xf];
    buf[i++] = hx[(v >> 8) & 0xf];
    buf[i++] = hx[(v >> 4) & 0xf];
    buf[i++] = hx[v & 0xf];
    buf[i++] = '\n';
    log_write(buf, i);
}

/* ---- 共享内存 ----
 * 布局（volatile u32 字段，偏移固定）：
 *   0x00 magic, 0x04 version, 0x08 engine_state,
 *   0x0c paper_state, 0x10 sensor1, 0x14 sensor2,
 *   0x18 feed_motor, 0x1c heater, 0x20 output,
 *   0x24 seq,
 *   0x28..0x128 gpio_val[64],
 *   0x128..0x228 gpio_dir[64]
 */
#define SHM_OFF_MAGIC      0x00
#define SHM_OFF_VERSION    0x04
#define SHM_OFF_ENGINE     0x08
#define SHM_OFF_PAPER      0x0c
#define SHM_OFF_SENSOR1    0x10
#define SHM_OFF_SENSOR2    0x14
#define SHM_OFF_MOTOR      0x18
#define SHM_OFF_HEATER     0x1c
#define SHM_OFF_OUTPUT     0x20
#define SHM_OFF_SEQ        0x24
#define SHM_OFF_GPIO_VAL   0x28   /* +4*i, i<64 */
#define SHM_OFF_GPIO_DIR   0x128  /* +4*i, i<64 */

static volatile unsigned char *shm = 0;   /* 映射基址 */
static int shm_fd = -1;

static void shm_u32(long off, unsigned long v)
{
    if (!shm) return;
    *(volatile unsigned long *)(shm + off) = v;
    __asm__ volatile("dmb sy" ::: "memory");
}
static unsigned long shm_r32(long off)
{
    if (!shm) return 0;
    return *(volatile unsigned long *)(shm + off);
}
static void shm_seq_inc(void)
{
    if (!shm) return;
    *(volatile unsigned long *)(shm + SHM_OFF_SEQ) += 1;
    __asm__ volatile("dmb sy" ::: "memory");
}

static void shm_init(void)
{
    long fd, r;
    long path = (long)SHM_PATH;
    if (shm) return;
    fd = syscall4(SYS_openat, AT_FDCWD, path, O_CREAT | O_RDWR, 0600);
    if (fd < 0) {
        path = (long)SHM_PATH2;
        fd = syscall4(SYS_openat, AT_FDCWD, path, O_CREAT | O_RDWR, 0600);
    }
    if (fd < 0)
        return;
    /* 确保足够大 */
    syscall2(SYS_ftruncate, fd, SHM_SIZE);
    shm = (volatile unsigned char *)syscall6(SYS_mmap, 0, SHM_SIZE,
                                             PROT_READ | PROT_WRITE,
                                             MAP_SHARED, fd, 0);
    if ((long)shm == -1) {
        shm = 0;
        syscall1(SYS_close, fd);
        return;
    }
    shm_fd = (int)fd;   /* 保持映射存活 */
    /* 首次初始化 */
    r = shm_r32(SHM_OFF_MAGIC);
    if (r != SHM_MAGIC) {
        shm_u32(SHM_OFF_MAGIC, SHM_MAGIC);
        shm_u32(SHM_OFF_VERSION, 1);
        /* 默认纸路：无纸、传感器低、电机停、加热关、出纸无 */
        shm_u32(SHM_OFF_PAPER, 0);     /* 0=NO_PAPER */
        shm_u32(SHM_OFF_SENSOR1, 0);
        shm_u32(SHM_OFF_SENSOR2, 0);
        shm_u32(SHM_OFF_MOTOR, 0);
        shm_u32(SHM_OFF_HEATER, 0);
        shm_u32(SHM_OFF_OUTPUT, 0);
        shm_u32(SHM_OFF_SEQ, 0);
    }
    shm_seq_inc();
}

/* ---- handle 结构（模仿 libhal：0=gpio_id u16, 8=flags, 16=内部指针）
 * 使用静态 .bss 池分配，避免 mmap 依赖（guest 内核下匿名 mmap 返回
 * -EINVAL 曾导致把错误码当指针写入而 SIGSEGV）。
 */
#define HANDLE_MAX 256
static unsigned long handle_pool[HANDLE_MAX * 4];  /* 每槽 32 字节，8 字节对齐 */
static long handle_next;

static long handle_alloc(long gpio_id, long flags)
{
    long p;
    if (handle_next >= HANDLE_MAX)
        return 0;
    p = (long)(handle_pool + handle_next * 4);
    handle_next++;
    *(volatile unsigned short *)(p + 0) = (unsigned short)gpio_id;
    *(volatile unsigned long *)(p + 8) = (unsigned long)flags;
    *(volatile unsigned long *)(p + 16) = 0;
    return p;
}

/* ================= 拦截函数（pi_hal_*） ================= */

/* pi_hal_init — 初始化 HAL */
int pi_hal_init(void *a)
{
    shm_init();
    log_str("[vhal] pi_hal_init\n");
    return 0;
}

void pi_hal_exit(void)
{
    log_str("[vhal] pi_hal_exit\n");
    if (shm) {
        shm_u32(SHM_OFF_PAPER, 0);
        syscall3(SYS_munmap, (long)shm, SHM_SIZE, 0);
        shm = 0;
    }
    if (shm_fd >= 0) {
        syscall1(SYS_close, shm_fd);
        shm_fd = -1;
    }
}

/* pi_hal_gpio_request(gpio_id, **handle, flags) -> int */
int pi_hal_gpio_request(int gpio_id, void **handle, int flags)
{
    long h;
    log_str("[vhal] gpio_request id=");
    log_u32("", (unsigned long)(unsigned short)gpio_id);
    if (!handle) return -1;
    h = handle_alloc(gpio_id, flags);
    if (!h) return -12;   /* ENOMEM */
    *handle = (void *)h;
    /* 方向登记：默认输入；马达/加热用输出会在 set 时登记 */
    if (shm) {
        shm_u32(SHM_OFF_GPIO_DIR + ((gpio_id & 0x3f) * 4), 0);
        shm_seq_inc();
    }
    return 0;
}

/* pi_hal_gpio_set(handle, value) -> int */
int pi_hal_gpio_set(void *handle, int value)
{
    long id;
    if (!handle) return -1;
    id = *(volatile unsigned short *)((long)handle + 0);
    log_str("[vhal] gpio_set id=");
    log_u32("", (unsigned long)id);
    log_str(" val=");
    log_u32("", (unsigned long)value);
    if (shm) {
        /* 方向登记为输出 */
        shm_u32(SHM_OFF_GPIO_DIR + ((id & 0x3f) * 4), 1);
        shm_u32(SHM_OFF_GPIO_VAL + ((id & 0x3f) * 4), (unsigned long)value & 1);
        /* 事件可视化（供 virtual_printer 轮询） */
        if (shm_r32(SHM_OFF_MOTOR) != ((unsigned long)value & 1) && shm_r32(SHM_OFF_MOTOR) == 0xfffffffful)
            ;
        shm_seq_inc();
    }
    return 0;
}

/* pi_hal_gpio_get(handle, *out) -> int */
int pi_hal_gpio_get(void *handle, int *out)
{
    long id;
    unsigned long v = 0;
    if (!handle || !out) return -1;
    id = *(volatile unsigned short *)((long)handle + 0);
    if (shm) {
        /* 输入口：从共享状态读（virtual_printer 驱动）；默认 0 */
        v = shm_r32(SHM_OFF_GPIO_VAL + ((id & 0x3f) * 4));
        if (shm_r32(SHM_OFF_GPIO_DIR + ((id & 0x3f) * 4)) == 0)
            v = 0;   /* 未登记的输出 → 输入默认低电平 */
    }
    *out = (int)v;
    log_str("[vhal] gpio_get id=");
    log_u32("", (unsigned long)id);
    log_str(" -> ");
    log_u32("", v);
    return 0;
}

/* pi_hal_gpio_free(handle) — 池分配，无需真正释放 */
int pi_hal_gpio_free(void *handle)
{
    log_str("[vhal] gpio_free\n");
    return 0;
}

/* ---- power ---- */
int pi_hal_power_request(void *a, void *b, int c)
{
    log_str("[vhal] power_request\n");
    return 0;
}
int pi_hal_power_set(void *handle, int value)
{
    log_str("[vhal] power_set val=");
    log_u32("", (unsigned long)value);
    return 0;
}
int pi_hal_power_get(void *handle, int *out)
{
    log_str("[vhal] power_get\n");
    if (out) *out = 1;   /* 电源始终"开启" */
    return 0;
}
int pi_hal_power_free(void *handle)
{
    log_str("[vhal] power_free\n");
    return 0;
}

/* ---- led ---- */
int pi_hal_led_request(void *a, void *b, int c)
{
    log_str("[vhal] led_request\n");
    return 0;
}
int pi_hal_led_ctrl(void *handle, int v)
{
    log_str("[vhal] led_ctrl val=");
    log_u32("", (unsigned long)v);
    return 0;
}

/* ---- rtc ---- */
int pi_hal_rtc_request(void *a, void *b, int c)
{
    log_str("[vhal] rtc_request\n");
    return 0;
}
int pi_hal_rtc_free(void *handle)
{
    log_str("[vhal] rtc_free\n");
    return 0;
}
int pi_hal_rtc_time_read(void *handle, void *out)
{
    log_str("[vhal] rtc_time_read\n");
    if (out) {
        /* 填充 2026-08-31 12:00:00 简单时间戳（tm 结构简化） */
        *(volatile long *)(out + 0) = 0;
    }
    return 0;
}

/* ---- storage（最小 stub：返回失败避免误写真实文件系统） ---- */
long pi_hal_storage_filerequest(void *a, void *b, void *c, void *d)
{
    log_str("[vhal] storage_filerequest (stub -> -1)\n");
    return -1;
}
long pi_hal_storage_filerelease(void *a)
{
    return 0;
}
long pi_hal_storage_fileread(void *a, void *b, void *c)
{
    return -1;
}
long pi_hal_storage_filewrite(void *a, void *b, void *c)
{
    return -1;
}
long pi_hal_storage_filelseek(void *a, void *b, void *c)
{
    return -1;
}
long pi_hal_storage_dirrequest(void *a, void *b, void *c)
{
    return 0;
}
long pi_hal_storage_dirrelease(void *a)
{
    return 0;
}
long pi_hal_storage_dirread(void *a, void *b)
{
    return -1;
}
long pi_hal_storage_mkdir(void *a, void *b)
{
    return -1;
}
long pi_hal_storage_file_dir_remove(void *a)
{
    return -1;
}
long pi_hal_storage_file_dir_rename(void *a, void *b)
{
    return -1;
}
long pi_hal_storage_file_dir_access(void *a, void *b)
{
    return -1;
}
long pi_hal_storage_media_emmc_get_nominal_size(void *a)
{
    return 0;
}
long pi_hal_storage_media_ssd_get_size(void *a)
{
    return 0;
}
long pi_hal_storage_media_udisk_get_size(void *a)
{
    return 0;
}
long pi_hal_storage_media_ssd_power_ctl(void *a, void *b)
{
    return 0;
}
long pi_hal_storage_partition_get_size(void *a)
{
    return 0;
}

/* ---- storage_mgr（外部符号：mfp 经 .rela.plt 从 libhal.so 导入）
 * 真实实现内部调用 hal_shm_mutex_lock -> hal_mutex_lock，依赖 pi_hal_init
 * 建立的共享内存 mutex；被我们拦截 pi_hal_init 后该状态未初始化，
 * 直接放行会 SIGSEGV(si_addr=0x2)。这里全部 stub 返回 0，避开真实路径。
 */
int storage_mgr_ctl(void *a0, int a1, void *a2)
{
    log_str("[vhal] storage_mgr_ctl cmd=");
    log_u32("", (unsigned long)a1);
    return 0;
}
int storage_mgr_get(void *a0)
{
    log_str("[vhal] storage_mgr_get\n");
    return 0;
}
int storage_mgr_put(void *a0)
{
    log_str("[vhal] storage_mgr_put\n");
    return 0;
}

/* ---- virt / wifi / boardinfo（最小 stub） ---- */
int pi_hal_virt_request(void *a, void *b, int c)
{
    log_str("[vhal] virt_request\n");
    return 0;
}
int pi_hal_virt_free(void *a)
{
    log_str("[vhal] virt_free\n");
    return 0;
}
int pi_hal_virt_platform(void *a, void *b)
{
    log_str("[vhal] virt_platform\n");
    return 0;
}
int pi_hal_wifi_request(void *a, void *b, int c)
{
    return 0;
}
int pi_hal_wifi_free(void *a)
{
    return 0;
}
int pi_hal_wifi_load(void *a)
{
    return 0;
}
int pi_hal_boardinfo_request(void *a, void *b, int c)
{
    log_str("[vhal] boardinfo_request\n");
    return 0;
}
int pi_hal_boardinfo_free(void *a)
{
    return 0;
}
int pi_hal_boardinfo_getinfo(void *a, void *b)
{
    log_str("[vhal] boardinfo_getinfo\n");
    return 0;
}