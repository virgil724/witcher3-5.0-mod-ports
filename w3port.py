#!/usr/bin/env python3
"""w3port - port 4.04-era Witcher 3 mods to game version 5.0 (remaster).

Subcommands
  apply   <game_dir>   apply the script patches in ./patches to the installed mods
  strings <game_dir>   convert old (v162/163, UTF-16) .w3strings in Mods/ to v164 (UTF-8)
  make    <orig_mods_dir> <ported_mods_dir>   (maintainer) regenerate ./patches

Standard library only. Originals are backed up to <game_dir>/Mods_w3port_backup.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH_DIR = HERE / "patches"
BACKUP_NAME = "Mods_w3port_backup"


# --------------------------------------------------------------------------- #
# script text helpers
# --------------------------------------------------------------------------- #

def read_ws(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    elif raw[:3] == b"\xef\xbb\xbf":
        text = raw[3:].decode("utf-8")
    else:
        text = raw.decode("utf-8")
    return text.replace("\r\n", "\n")


def write_ws(path: Path, text: str) -> None:
    data = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(b"\xff\xfe" + data.encode("utf-16-le"))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def backup(game: Path, target: Path) -> None:
    rel = target.relative_to(game / "Mods")
    dst = game / BACKUP_NAME / rel
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, dst)


# --------------------------------------------------------------------------- #
# patches: unified diff, strict apply
# --------------------------------------------------------------------------- #

def make(orig_mods: Path, ported_mods: Path) -> None:
    if PATCH_DIR.exists():
        shutil.rmtree(PATCH_DIR)
    manifest = []
    for new in sorted(ported_mods.rglob("*.ws")):
        rel = new.relative_to(ported_mods)
        old = orig_mods / rel
        if not old.exists():
            continue
        a, b = read_ws(old), read_ws(new)
        if a == b:
            continue
        diff = difflib.unified_diff(
            a.splitlines(keepends=True), b.splitlines(keepends=True),
            fromfile=f"a/{rel.as_posix()}", tofile=f"b/{rel.as_posix()}", n=3)
        out = PATCH_DIR / (rel.as_posix() + ".diff")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(diff), encoding="utf-8", newline="\n")
        manifest.append({"file": rel.as_posix(), "before": sha(a), "after": sha(b)})
    (PATCH_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"wrote {len(manifest)} patches")


def apply_diff(text: str, diff: str) -> str:
    src = text.splitlines(keepends=True)
    out: list[str] = []
    pos = 0
    lines = diff.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("@@"):
            i += 1
            continue
        old = line.split()[1][1:]  # "-start,count" without the "-"
        start, _, count = old.partition(",")
        start = int(start)
        start = start if count == "0" else start - 1
        out.extend(src[pos:start])
        pos = start
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            tag, body = lines[i][0], lines[i][1:]
            if tag in " -":
                if pos >= len(src) or src[pos].rstrip("\n") != body.rstrip("\n"):
                    raise ValueError(f"context mismatch near line {pos + 1}")
                if tag == " ":
                    out.append(src[pos])
                pos += 1
            elif tag == "+":
                out.append(body)
            i += 1
    out.extend(src[pos:])
    return "".join(out)


def apply(game: Path) -> int:
    manifest = json.loads((PATCH_DIR / "manifest.json").read_text(encoding="utf-8"))
    mods = game / "Mods"
    bad = 0
    for entry in manifest:
        target = mods / entry["file"]
        if not target.exists():
            print(f"[skip] not installed: {entry['file']}")
            continue
        text = read_ws(target)
        h = sha(text)
        if h == entry["after"]:
            print(f"[ok]   already patched: {entry['file']}")
            continue
        if h != entry["before"]:
            print(f"[FAIL] file differs from the expected mod version: {entry['file']}")
            bad += 1
            continue
        diff = (PATCH_DIR / (entry["file"] + ".diff")).read_text(encoding="utf-8")
        result = apply_diff(text, diff)
        if sha(result) != entry["after"]:
            print(f"[FAIL] patch result mismatch: {entry['file']}")
            bad += 1
            continue
        backup(game, target)
        write_ws(target, result)
        print(f"[ok]   patched: {entry['file']}")
    return bad


# --------------------------------------------------------------------------- #
# w3strings: v162/163 (UTF-16) -> v164 (UTF-8)
# --------------------------------------------------------------------------- #
# Layout (little endian): "RTSW", u32 version, u16 key_hi, count, count*(id^m, off, len),
# count, count*(hash, id^m), count(units), buffer, u16 key_lo.
# Text is XOR-obfuscated per string with a key derived from magic and the string length.

LANG_MAGIC = {  # 32-bit language key -> magic
    0x00000000: 0x00000000, 0x18632176: 0x16875467, 0x43975139: 0x79321793,
    0x54834893: 0x59825646, 0x63481486: 0x42386347, 0x83496237: 0x73946816,
    0x75886138: 0x42791159, 0x23863176: 0x75921975, 0x45931894: 0x12375973,
    0x18796651: 0x42387566, 0x24987354: 0x21793217, 0x42378932: 0x67823218,
}


def _read_count(d: bytes, p: int) -> tuple[int, int]:
    b = d[p]; p += 1
    v = b & 0x3F
    if not b & 0x40:
        return v, p
    shift = 6
    while True:
        b = d[p]; p += 1
        v |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return v, p


def _write_count(v: int) -> bytes:
    if v == 0:
        return b"\x00"
    out = bytearray([v & 0x3F]); v >>= 6
    while v:
        out.append((v & 0x7F) | 0x80); v >>= 7
    if len(out) > 1:
        out[0] |= 0x40; out[-1] &= 0x7F
    return bytes(out)


def _xor(raw: bytes, magic: int, unit: int) -> bytes:
    if magic == 0 or not raw:
        return raw
    n = len(raw) // unit
    key = (magic >> 8) & 0xFFFF
    out = bytearray(raw)
    for i in range(n):
        ck = ((n + 1) * key) & 0xFFFF
        out[i * unit] ^= ck & 0xFF
        if unit == 2:
            out[i * unit + 1] ^= ck >> 8
        key = ((key << 1) | (key >> 15)) & 0xFFFF
    return bytes(out)


def w3s_decode(d: bytes):
    if d[:4] != b"RTSW":
        raise ValueError("not a w3strings file")
    ver = struct.unpack_from("<I", d, 4)[0]
    lk = (struct.unpack_from("<H", d, 8)[0] << 16) | struct.unpack_from("<H", d, len(d) - 2)[0]
    magic = LANG_MAGIC[lk]
    p = 10
    n, p = _read_count(d, p)
    entries = [struct.unpack_from("<III", d, p + 12 * i) for i in range(n)]; p += 12 * n
    k, p = _read_count(d, p)
    keys = [struct.unpack_from("<II", d, p + 8 * i) for i in range(k)]; p += 8 * k
    units, p = _read_count(d, p)
    unit = 1 if ver >= 164 else 2
    if unit == 2 and p + units == len(d) - 2:
        unit = 1
    buf = d[p:p + units * unit]
    enc = "utf-8" if unit == 1 else "utf-16-le"
    strings = []
    for sid, off, ln in entries:
        strings.append((sid, _xor(buf[off * unit:(off + ln) * unit], magic, unit).decode(enc)))
    return ver, lk, magic, strings, keys


def w3s_encode(lk: int, magic: int, strings, keys) -> bytes:
    buf = bytearray(); ent = bytearray()
    for sid, text in sorted(strings, key=lambda s: s[0]):  # stored ids, already ^magic
        raw = text.encode("utf-8")
        ent += struct.pack("<III", sid, len(buf), len(raw))
        buf += _xor(raw, magic, 1) + b"\x00"
    kb = b"".join(struct.pack("<II", h, sid) for h, sid in sorted(set(keys)))
    return (b"RTSW" + struct.pack("<I", 164) + struct.pack("<H", lk >> 16)
            + _write_count(len(strings)) + ent + _write_count(len(set(keys))) + kb
            + _write_count(len(buf)) + bytes(buf) + struct.pack("<H", lk & 0xFFFF))


def strings(game: Path) -> int:
    bad = 0
    for f in sorted((game / "Mods").glob("*/content/*.w3strings")):
        d = f.read_bytes()
        ver = struct.unpack_from("<I", d, 4)[0]
        if ver >= 164:
            continue
        try:
            _, lk, magic, s, k = w3s_decode(d)
            new = w3s_encode(lk, magic, s, k)
            _, _, _, s2, k2 = w3s_decode(new)
            assert sorted(s) == sorted(s2) and sorted(set(k)) == sorted(k2)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {f.relative_to(game)}: {type(e).__name__} {e}")
            bad += 1
            continue
        backup(game, f)
        f.write_bytes(new)
        print(f"[ok]   {f.relative_to(game)}  v{ver} -> v164")
    return bad


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] in ("apply", "strings"):
        game = Path(argv[1])
        if not (game / "Mods").is_dir():
            print(f"no Mods folder in {game}")
            return 2
        return 1 if (apply(game) if argv[0] == "apply" else strings(game)) else 0
    if len(argv) == 3 and argv[0] == "make":
        make(Path(argv[1]), Path(argv[2]))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
