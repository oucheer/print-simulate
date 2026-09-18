/* binder_stub.c — LD_PRELOAD 拦截，模拟 /dev/binder 设备
 *
 * 目的：让依赖 Android binder IPC 的进程（event_mgr_service / service_manager）
 *      在无 binder 内核驱动的仿真环境中不因 open("/dev/binder") 失败而退出。
 *
 * 编译：aarch64-linux-musl-gcc -nostdlib -fPIC -shared -o binder_stub.so binder_stub.c
 * 用法：LD_PRELOAD=/binder_stub.so <进程>
 *
 * 纯 syscall 实现（aarch64 内联），无 libc 依赖，可被 glibc 进程安全加载。
 */
#define _GNU_SOURCE

/* ---- aarch64 syscall numbers ---- */
#define SYS_openat 56
#define SYS_ioctl 29
#define SYS_mmap 222
#define SYS_close 57
#define SYS_fcntl 25
#define SYS_poll 7

/* ---- constants ---- */
#define AT_FDCWD (-100)
#define O_RDONLY 0
#define O_RDWR 2
#define O_CLOEXEC 02000000
#define O_NONBLOCK 00004000

#define MAP_SHARED 0x01
#define MAP_PRIVATE 0x02
#define MAP_ANONYMOUS 0x20
#define MAP_FAILED ((void *)-1)

#define PROT_READ 0x1
#define PROT_WRITE 0x2

#define POLLIN 0x001

#define FAKE_FD 0x777

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

/* ---- 判断路径是否为 binder 设备 ---- */
static int path_is_binder(const char *p)
{
    const char *t = "/dev/binder";
    while (*t != 0) {
        if (*p != *t) return 0;
        p++;
        t++;
    }
    /* 匹配 "/dev/binder" 完全相等 或 前缀（如 /dev/binderfs） */
    return 1;
}

/* ================= 导出的拦截函数 ================= */

/* open() 在 glibc 中经 openat(AT_FDCWD, ...) 实现，只需拦截 openat */
int openat(int dirfd, const char *path, int flags, ...)
{
    if (path_is_binder(path)) {
        return FAKE_FD;
    }
    return (int)syscall6(SYS_openat, dirfd, (long)path, flags, 0, 0, 0);
}

/* 也拦截旧式 open（若调用方直接用 syscall 或旧 glibc） */
int open(const char *path, int flags, ...)
{
    if (path_is_binder(path)) {
        return FAKE_FD;
    }
    return (int)syscall6(SYS_openat, AT_FDCWD, (long)path, flags, 0, 0, 0);
}

int ioctl(int fd, unsigned long request, ...)
{
    if (fd == FAKE_FD) {
        return 0; /* binder ioctl 全部视为成功 */
    }
    return (int)syscall6(SYS_ioctl, fd, (long)request, 0, 0, 0, 0);
}

void *mmap(void *addr, unsigned long length, int prot, int flags, int fd,
           long offset)
{
    if (fd == FAKE_FD) {
        /* 用匿名映射替代 binder 内存映射 */
        flags |= MAP_ANONYMOUS;
        fd = -1;
        return (void *)syscall6(SYS_mmap, (long)addr, length, prot, flags, fd, offset);
    }
    return (void *)syscall6(SYS_mmap, (long)addr, length, prot, flags, fd, offset);
}

int close(int fd)
{
    if (fd == FAKE_FD) {
        return 0;
    }
    return (int)syscall6(SYS_close, fd, 0, 0, 0, 0, 0);
}

int fcntl(int fd, int cmd, ...)
{
    if (fd == FAKE_FD) {
        return 0; /* F_SETFL / F_GETFL 等均视为成功 */
    }
    return (int)syscall6(SYS_fcntl, fd, cmd, 0, 0, 0, 0);
}

/* poll() 结构体定义（与内核 ABI 一致） */
struct pollfd {
    int fd;
    short events;
    short revents;
};

int poll(struct pollfd *fds, unsigned long nfds, int timeout)
{
    unsigned long i;
    int fake_seen = 0;
    for (i = 0; i < nfds; i++) {
        if (fds[i].fd == FAKE_FD) {
            fds[i].revents = POLLIN; /* 声称有事件，避免客户端阻塞 */
            fake_seen = 1;
        } else {
            fds[i].revents = 0;
        }
    }
    if (fake_seen) {
        return (int)nfds;
    }
    /* 没有 fake fd 时不做真 poll（简化：返回 0 立即超时） */
    return 0;
}
