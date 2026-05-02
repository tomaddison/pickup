"""Write a list of markers as a Pro Tools `.ptx` session importable via Session Data.

Reverse-engineered from the ptformat reference and Pro Tools 12 sample sessions.
The bundled `template.dat` is a zlib-compressed PT12 session containing one
placeholder marker; we decrypt it, splice in a fresh marker container, fix up
offset pointers shifted by the size delta, then re-encrypt and write.

Public entry point: :func:`write_ptx`.
"""

from __future__ import annotations

import struct
import zlib
from importlib import resources
from pathlib import Path

from pickup.errors import PickupError

# Pro Tools internal tick unit (sample-rate independent).
_TICKS_PER_SECOND = 187.5
# First 20 bytes of a session are unencrypted; everything after is XOR-scrambled.
_HEADER_SIZE = 0x14
# Sentinel byte that begins every block in the decrypted stream.
_ZMARK = 0x5A

# Byte offsets within a single decrypted marker block.
_OFF_MARKER_NUM = 9  # uint16 LE
_OFF_NAME_LEN = 15  # uint32 LE
_OFF_NAME = 19  # variable-length UTF-8


Marker = tuple[str, float, str]  # (label, seconds, comments)


def write_ptx(markers: list[Marker], output_path: Path) -> int:
    """Write *markers* to *output_path* as a Pro Tools session.

    Returns the number of markers written. Raises :class:`PickupError` if the
    list is empty.
    """
    if not markers:
        raise PickupError("No markers to write.")

    template_raw = _load_template()
    xxor = _build_key_table(template_raw)

    decrypted = bytearray(template_raw[:_HEADER_SIZE]) + bytearray(
        _crypt(template_raw[_HEADER_SIZE:], xxor, _HEADER_SIZE)
    )

    block_offsets = _catalog_block_offsets(decrypted)
    container_start, container_end, record_size, _orig_count = _find_marker_container(decrypted)
    template_block = bytearray(decrypted[container_start + 13 : container_start + 13 + record_size])

    new_container = _build_container(template_block, markers)
    new_decrypted = bytearray(decrypted[:container_start] + new_container + decrypted[container_end:])

    # Splicing changes downstream block offsets; pointers in earlier blocks must follow.
    size_delta = len(new_container) - (container_end - container_start)
    if size_delta != 0:
        _fixup_pointers(new_decrypted, block_offsets, container_end, size_delta)

    output = bytes(new_decrypted[:_HEADER_SIZE]) + _crypt(
        bytes(new_decrypted[_HEADER_SIZE:]), xxor, _HEADER_SIZE
    )
    output_path.write_bytes(output)
    return len(markers)


def _load_template() -> bytes:
    """Decompress the bundled Pro Tools 12 session template."""
    data = resources.files("pickup").joinpath("template.dat").read_bytes()
    return zlib.decompress(data)


def _build_key_table(header: bytes) -> list[int]:
    """Derive the 256-entry XOR table from the session header's xor_type/xor_value."""
    xor_type = header[0x12]
    xor_value = header[0x13]
    if xor_type != 0x05:
        raise PickupError(
            f"Unsupported Pro Tools version (xor_type=0x{xor_type:02x}); expected 0x05 for PT10+."
        )
    xor_delta = 0
    for i in range(256):
        if (i * 11) & 0xFF == xor_value:
            xor_delta = (256 - i) & 0xFF
            break
    return [(i * xor_delta) & 0xFF for i in range(256)]


def _crypt(data: bytes, xxor: list[int], start_pos: int) -> bytes:
    """Symmetric XOR cipher used by Pro Tools — same routine encrypts and decrypts."""
    return bytes(b ^ xxor[((start_pos + i) >> 12) & 0xFF] for i, b in enumerate(data))


def _catalog_block_offsets(decrypted: bytes | bytearray) -> set[int]:
    """Return every offset where a valid block starts. Used as the pointer-fixup target set."""
    offsets: set[int] = set()
    pos = _HEADER_SIZE
    while pos < len(decrypted) - 7:
        if decrypted[pos] == _ZMARK:
            bt = struct.unpack_from("<H", decrypted, pos + 1)[0]
            bs = struct.unpack_from("<I", decrypted, pos + 3)[0]
            if not (bt & 0xFF00) and bs > 0 and pos + 7 + bs <= len(decrypted):
                offsets.add(pos)
        pos += 1
    return offsets


def _fixup_pointers(buf: bytearray, block_offsets: set[int], splice_point: int, delta: int) -> int:
    """Shift any 32-bit LE pointer that referenced a block at or beyond *splice_point*."""
    targets = {o for o in block_offsets if o >= splice_point}
    if not targets:
        return 0
    count = 0
    for i in range(len(buf) - 3):
        val = struct.unpack_from("<I", buf, i)[0]
        if val in targets:
            struct.pack_into("<I", buf, i, val + delta)
            count += 1
    return count


def _find_marker_container(decrypted: bytes | bytearray) -> tuple[int, int, int, int]:
    """Locate the marker container block. Returns (start, end, record_size, count)."""
    i = 0
    while i < len(decrypted) - 13:
        if decrypted[i : i + 3] == b"\x5a\x05\x00":
            size = struct.unpack("<I", decrypted[i + 3 : i + 7])[0]
            const = decrypted[i + 7 : i + 9]
            count = struct.unpack("<I", decrypted[i + 9 : i + 13])[0]
            if const == b"\x30\x20" and 1 <= count <= 999:
                child_start = i + 13
                if decrypted[child_start : child_start + 3] == b"\x5a\x12\x00":
                    child_size = struct.unpack("<I", decrypted[child_start + 3 : child_start + 7])[0]
                    return i, i + 7 + size, 7 + child_size, count
        i += 1
    raise PickupError("Could not find marker container in Pro Tools template.")


def _patch_marker_block(
    template_block: bytes | bytearray, number: int, label: str, seconds: float, comments: str
) -> bytes:
    """Clone the template block; patch in marker number, name, ticks, and Comments field.

    The Comments string appears twice in a marker block (at tail+74 and again
    after a 50-byte fixed metadata segment). Both copies are rewritten.
    """
    blk = bytearray(template_block)

    orig_name_len = struct.unpack("<I", blk[_OFF_NAME_LEN : _OFF_NAME_LEN + 4])[0]
    name_bytes = label.encode("utf-8")
    new_name_len = len(name_bytes)

    tail_start = _OFF_NAME + orig_name_len + 1  # +1 for null terminator after the name
    tail = blk[tail_start:]

    # Layout of `tail`:
    #   [0:74]   ticks (16) + fixed metadata (58)
    #   [74:78]  comments_1 length (uint32 LE)
    #   [78:78+c1_len] comments_1 utf-8
    #   then 50 bytes fixed
    #   then comments_2 length + utf-8
    #   then UUID + sub-blocks
    pre_comments = tail[0:74]
    orig_c1_len = struct.unpack("<I", tail[74:78])[0]
    mid_start = 78 + orig_c1_len
    mid_fixed = tail[mid_start : mid_start + 50]
    c2_offset = mid_start + 50
    orig_c2_len = struct.unpack("<I", tail[c2_offset : c2_offset + 4])[0]
    post_tail = tail[c2_offset + 4 + orig_c2_len :]

    comments_bytes = comments.encode("utf-8")
    c_len = len(comments_bytes)

    new_tail = bytearray()
    new_tail += pre_comments
    new_tail += struct.pack("<I", c_len) + comments_bytes
    new_tail += mid_fixed
    new_tail += struct.pack("<I", c_len) + comments_bytes
    new_tail += post_tail

    new_blk = bytearray(blk[:_OFF_NAME_LEN])
    new_blk += struct.pack("<I", new_name_len)
    new_blk += name_bytes
    new_blk += b"\x00"
    new_blk += new_tail

    new_blk[3:7] = struct.pack("<I", len(new_blk) - 7)
    new_blk[_OFF_MARKER_NUM : _OFF_MARKER_NUM + 2] = struct.pack("<H", number)

    ticks = int(seconds * _TICKS_PER_SECOND)
    tick_pos = _OFF_NAME + new_name_len + 1
    new_blk[tick_pos : tick_pos + 8] = struct.pack("<Q", ticks)
    new_blk[tick_pos + 8 : tick_pos + 16] = struct.pack("<Q", ticks)

    return bytes(new_blk)


def _build_container(template_block: bytes | bytearray, markers: list[Marker]) -> bytes:
    """Assemble a fresh marker container block from patched marker records."""
    marker_data = bytearray()
    for i, (label, seconds, comments) in enumerate(markers, start=1):
        marker_data += _patch_marker_block(template_block, i, label, seconds, comments)

    container_size = 6 + len(marker_data) + 8
    block = bytearray()
    block += b"\x5a\x05\x00"
    block += struct.pack("<I", container_size)
    block += b"\x30\x20"
    block += struct.pack("<I", len(markers))
    block += marker_data
    block += b"\x00" * 8
    return bytes(block)
