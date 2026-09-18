#!/usr/bin/env python3
"""repack_tar.py — 把 gz 压缩 tar 解流为未压缩 tar（供 guest busybox tar 普通解压）

guest 的 busybox tar 不支持 gzip 解压（-z/-a 均无效），
在 host 侧剥离 gzip 层，保留全部原始成员（含符号链接）。
"""
import gzip, shutil, sys

src = r"tools\toolchain\musl-native.tgz"
dst = r"tools\toolchain\musl-native.tar"

with gzip.open(src, "rb") as fin, open(dst, "wb") as fout:
    shutil.copyfileobj(fin, fout, length=1 << 20)

print("repacked:", dst)
