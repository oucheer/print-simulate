"""gen_pwg_job.py - 生成最小 PWG Raster 作业: A4 单面黑白 1 页 (300dpi, 1bpp)
行式(line-based) PWG Raster 格式, 数据全白(0xFF)
输出: runtime/pwg-job-1page.pwg
"""
import struct

W, H = 2480, 3508          # A4 @300dpi
BYTES_PER_LINE = (W + 7) // 8  # 310

lines = []
lines.append(b"PWG RASTER\n")
lines.append(b"A4;Black_1;8;Chunky;None\n")   # Media;ColorSpace;BitsPerColor;ColorOrder;Compression
lines.append(b"1\n")                          # 页数
lines.append(b"P1\n")                         # 第 1 页
lines.append(b"%d %d 1 Black_1 300 300 0 0 %d %d\n" % (W, H, W, H))
lines.append(b"A4;plain;1side;LongEdge;Borderless=no\n")

# 图像数据: 每行前 4 字节小端行长度 + 行数据 (全白 0xFF)
row = b"\xff" * BYTES_PER_LINE
data = b"".join(struct.pack("<I", len(row)) + row for _ in range(H))

out = b"".join(lines) + data
path = r"d:\Apps\codex\files\simulate\runtime\pwg-job-1page.pwg"
with open(path, "wb") as f:
    f.write(out)
print("written", path, len(out), "bytes")
