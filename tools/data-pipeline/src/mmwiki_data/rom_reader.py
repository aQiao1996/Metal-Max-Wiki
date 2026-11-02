"""只读解析本机 MM2R 的文件表、PAK 名称树和物品名称表。"""

import struct
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class RomFile:
    data: bytes
    offset: int


@dataclass(frozen=True)
class RomItemName:
    item_id: int
    kind: int
    name: str
    record_offset: int
    name_offset: int
    name_bytes: int


def _bounded(data: bytes, offset: int, size: int) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError(f"ROM 数据范围越界：offset={offset} size={size}")


def _u16(data: bytes, offset: int) -> int:
    _bounded(data, offset, 2)
    return int(struct.unpack_from("<H", data, offset)[0])


def _u32(data: bytes, offset: int) -> int:
    _bounded(data, offset, 4)
    return int(struct.unpack_from("<I", data, offset)[0])


def read_rom(path: Path, *, expected_hash: str, expected_size: int) -> bytes:
    """校验用户登记的文件指纹，拒绝同名但不同内容的 ROM。"""
    if path.stat().st_size != expected_size or not 512 <= expected_size <= 268435456:
        raise ValueError("ROM 大小与登记记录不一致")
    data = path.read_bytes()
    if "sha256:" + sha256(data).hexdigest() != expected_hash:
        raise ValueError("ROM SHA-256 与登记记录不一致")
    if data[:12].rstrip(b"\0") != b"METALMAX2R" or data[12:16] != b"TMXJ":
        raise ValueError("ROM 内部标题或游戏代码不匹配")
    return data


def read_nds_file(data: bytes, filename: str) -> RomFile:
    """按 NDS 文件名表定位文件，同时校验目录和 FAT 边界。"""
    fnt_offset, fnt_size = _u32(data, 64), _u32(data, 68)
    fat_offset, fat_size = _u32(data, 72), _u32(data, 76)
    _bounded(data, fnt_offset, fnt_size)
    _bounded(data, fat_offset, fat_size)
    if fat_size % 8:
        raise ValueError("ROM FAT 长度不是完整条目")
    fnt = data[fnt_offset : fnt_offset + fnt_size]
    directories = _u16(fnt, 6)
    _bounded(fnt, 0, directories * 8)
    visited: set[int] = set()
    files: dict[str, int] = {}

    def walk(directory: int, prefix: str) -> None:
        if directory >= directories or directory in visited:
            raise ValueError("ROM 目录树包含越界或重复节点")
        visited.add(directory)
        at = _u32(fnt, directory * 8)
        file_id = _u16(fnt, directory * 8 + 4)
        if at < directories * 8:
            raise ValueError("ROM 目录内容覆盖目录索引")
        while True:
            _bounded(fnt, at, 1)
            marker = fnt[at]
            at += 1
            if marker == 0:
                break
            length = marker & 127
            _bounded(fnt, at, length)
            name = fnt[at : at + length].decode("ascii")
            at += length
            if not name or any(char in name for char in "/\\\0") or name in {".", ".."}:
                raise ValueError("ROM 文件名无效")
            full_name = prefix + name
            if marker & 128:
                nested = _u16(fnt, at)
                at += 2
                if nested & 0xF000 != 0xF000:
                    raise ValueError("ROM 目录 ID 无效")
                walk(nested & 0xFFF, full_name + "/")
            else:
                if full_name in files or file_id * 8 + 8 > fat_size:
                    raise ValueError("ROM 文件名重复或 FAT ID 越界")
                files[full_name] = file_id
                file_id += 1

    walk(0, "")
    if filename not in files:
        raise ValueError(f"ROM 缺少文件：{filename}")
    entry = fat_offset + files[filename] * 8
    start, end = _u32(data, entry), _u32(data, entry + 4)
    _bounded(data, start, end - start)
    return RomFile(data[start:end], start)


def read_pak_files(archive: RomFile) -> dict[str, RomFile]:
    """解析本份 MM2R PAK 的前缀名称树及长度／位置索引。"""
    data = archive.data
    count, table, trie = _u16(data, 0), _u32(data, 2), _u16(data, 6)
    if not count or not 8 <= trie < table:
        raise ValueError("MM2R PAK 头无效")
    _bounded(data, table, count * 8)
    names: dict[int, str] = {}
    visited: set[int] = set()

    def walk(at: int, prefix: str) -> None:
        if not trie <= at < table or at in visited:
            raise ValueError("MM2R PAK 名称树包含越界或重复节点")
        visited.add(at)
        entries = _u16(data, at)
        if at + 2 + entries * 4 > table:
            raise ValueError("MM2R PAK 名称树覆盖文件索引")
        for index in range(entries):
            text_at = _u16(data, at + 2 + index * 4)
            value = _u16(data, at + 4 + index * 4)
            if not 8 <= text_at < trie:
                raise ValueError("MM2R PAK 字符串位置越界")
            end = data.find(b"\0", text_at, trie)
            if end < 0:
                raise ValueError("MM2R PAK 字符串未结束")
            name = prefix + data[text_at:end].decode("ascii")
            if value & 1:
                file_id = value >> 1
                if file_id >= count or file_id in names or not name:
                    raise ValueError("MM2R PAK 文件 ID 或名称无效")
                names[file_id] = name
            else:
                walk(value >> 1, name)

    walk(trie, "")
    if len(names) != count or len(set(names.values())) != count:
        raise ValueError("MM2R PAK 文件数量或名称不一致")
    files: dict[str, RomFile] = {}
    for index in range(count):
        size, offset = _u32(data, table + index * 8), _u32(data, table + index * 8 + 4)
        if offset < table + count * 8:
            raise ValueError("MM2R PAK 文件覆盖索引")
        _bounded(data, offset, size)
        files[names[index]] = RomFile(data[offset : offset + size], archive.offset + offset)
    return files


def read_item_names(data: bytes) -> tuple[RomItemName, ...]:
    """仅提取物品名称和分类定位，不解释数值、掉率或运行效果。"""
    files = read_pak_files(read_nds_file(data, "xls/data/pack_data.pak"))
    records, strings = files["ITEMLIST.ARR"], files["ITEMLIST.NAM"]
    if len(records.data) % 12 or len(strings.data) % 2:
        raise ValueError("MM2R 物品表长度或 UTF-16 对齐无效")
    result: list[RomItemName] = []
    for item_id in range(len(records.data) // 12):
        at = item_id * 12
        start = _u16(records.data, at)
        if start % 2:
            raise ValueError(f"MM2R 物品名称未按 UTF-16 对齐：{item_id}")
        end = start
        while True:
            _bounded(strings.data, end, 2)
            if strings.data[end : end + 2] == b"\0\0":
                break
            end += 2
        name = strings.data[start:end].decode("utf-16le")
        if any(ord(char) < 32 for char in name):
            raise ValueError(f"MM2R 物品名称包含控制字符：{item_id}")
        result.append(
            RomItemName(
                item_id,
                _u16(records.data, at + 2),
                name,
                records.offset + at,
                strings.offset + start,
                end - start,
            )
        )
    return tuple(result)
