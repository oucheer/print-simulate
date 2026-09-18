import struct
import sys
from pathlib import Path


ENTRY_SIZE = 512
FIELD_SIZE_OFFSET = 0x108
TABLE_OFFSET = 0x200


def main() -> None:
    resource_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    data = resource_path.read_bytes()
    if data[:4] != b"RSCE":
        sys.exit(f"not a Rockchip resource image: {data[:4]!r}")

    count = struct.unpack_from("<I", data, 12)[0]
    print(f"resource entries: {count}")

    data_offset = TABLE_OFFSET + count * ENTRY_SIZE
    entries = []
    for index in range(count):
        base = TABLE_OFFSET + index * ENTRY_SIZE
        tag = data[base : base + 4]
        name = data[base + 4 : base + 20].rstrip(b"\x00").decode("ascii", "replace")
        size = struct.unpack_from("<I", data, base + FIELD_SIZE_OFFSET)[0]
        offset = data_offset
        data_offset += size
        entries.append((name, offset, size))
        print(f"  {tag!r} {name!r:24} offset=0x{offset:x} size=0x{size:x}")

    for name, offset, size in entries:
        if size == 0 or offset + size > len(data):
            print(f"skip {name}: invalid range")
            continue
        out_path = out_dir / name
        out_path.write_bytes(data[offset : offset + size])
        print(f"wrote {out_path.name}: {size} bytes")


if __name__ == "__main__":
    main()
