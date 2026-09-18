"""分段并行下载 musl.cc 工具链（服务器按连接限速，分段可提速）"""
import concurrent.futures, subprocess, pathlib, time

URL = "https://musl.cc/aarch64-linux-musl-native.tgz"
OUT = r"tools/toolchain/musl-native.tgz"
SEGS = 4

# 更健壮地解析 content-length
hdr = subprocess.run(["curl.exe", "-sIL", URL], capture_output=True, text=True).stdout
total = 0
for line in hdr.splitlines():
    low = line.lower().strip()
    if low.startswith("content-length"):
        total = int(line.split(":", 1)[1].strip())
print("total bytes:", total, flush=True)
assert total > 0, "no content-length"

size = total // SEGS
ranges = [(i * size, (i + 1) * size - 1 if i < SEGS - 1 else total - 1) for i in range(SEGS)]


def dl(i, r0, r1):
    part = f"tools/toolchain/np{i}.bin"
    subprocess.run(["curl.exe", "-s", "-L", "-r", f"{r0}-{r1}", "-o", part, URL], check=True)
    n = pathlib.Path(part).stat().st_size
    print(f"part{i}: {n} bytes ({r0}-{r1})", flush=True)
    return part, n


t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=SEGS) as ex:
    parts = [f.result() for f in [ex.submit(dl, i, r0, r1) for i, (r0, r1) in enumerate(ranges)]]

with open(OUT, "wb") as out:
    for part, _ in parts:
        with open(part, "rb") as p:
            out.write(p.read())

got = pathlib.Path(OUT).stat().st_size
print(f"merged: {got} / {total}  elapsed={time.time()-t0:.0f}s", flush=True)
print("OK" if got == total else "MISMATCH")
for i in range(SEGS):
    pathlib.Path(f"tools/toolchain/np{i}.bin").unlink(missing_ok=True)