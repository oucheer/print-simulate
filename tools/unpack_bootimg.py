#!/usr/bin/env python3
"""unpack_bootimg.py — Rockchip boot 分区内核提取/校验脚本

输入：runtime/unpacked/rkaf/boot_extracted/kernel.img
行为：
1. 探测文件类型：
   - 直接为 ARM64 Image（offset 0x38 处小端 0x644d5241 = "ARM\\x64"）→ 原样复制
   - Rockchip 头 + gzip 压缩内核（"MZ@" + 1F 8B）→ 剥离头并解压
2. 输出 kernel.Image 与元数据 JSON
"""
import json, shutil, struct, sys
from pathlib import Path

ARM64_MAGIC = struct.pack("<I", 0x644D5241)  # "ARM\x64"
RK_BOOT_MAGIC = b"MZ@"
GZIP_MAGIC = b"\x1f\x8b"


def probe(path: Path):
    data = path.read_bytes()
    result = {"file": str(path), "size": len(data)}
    if data[0x38:0x3C] == ARM64_MAGIC:
        result["type"] = "arm64_image"
        result["arm64_magic_offset"] = 0x38
        result["text_offset"] = struct.unpack_from("<Q", data, 0x08)[0]
        result["image_size"] = struct.unpack_from("<Q", data, 0x0C)[0]
        result["flags"] = struct.unpack_from("<Q", data, 0x10)[0]
        return result, data
    if data[:3] == RK_BOOT_MAGIC and GZIP_MAGIC in data[0x100:0x400]:
        # Rockchip 头: magic(8) + kernel_size(4) + kernel_aligned(4) + load(4) + entry(4)
        ksz = struct.unpack_from("<I", data, 8)[0]
        candidate = data[0x100 : 0x100 + ksz]
        if candidate[:2] == GZIP_MAGIC:
            import gzip

            result["type"] = "rk_boot_gzip"
            result["kernel_offset"] = 0x100
            return result, gzip.decompress(candidate)
    result["type"] = "unknown"
    return result, data


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else r"runtime\unpacked\rkaf\boot_extracted\kernel.img")
    out_dir = src.parent
    info, payload = probe(src)
    if info["type"] == "arm64_image":
        dst = out_dir / "kernel.Image"
        dst.write_bytes(payload)
        info["action"] = "copied as-is (already ARM64 Image)"
    elif info["type"] == "rk_boot_gzip":
        dst = out_dir / "kernel.Image"
        dst.write_bytes(payload)
        info["action"] = "decompressed gzip kernel"
    else:
        dst = None
        info["action"] = "no extraction possible"
    meta = out_dir / "boot-extract.json"
    meta.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if dst:
        print(f"OUTPUT: {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
