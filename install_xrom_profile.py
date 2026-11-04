"""Install X-ROM 512M support into a FlashGBX installation.

    <FlashGBX>\\Python\\python.exe install_xrom_profile.py [--flashgbx DIR] [--config DIR] [--check]

1. copies fc_AGB_XROM512M.txt into FlashGBX's config directory (%LOCALAPPDATA%\\FlashGBX)
2. patches FlashGBX/Flashcart.py  : adds flash_bank_select_type 3 (the X-ROM bank register)
3. patches FlashGBX/LK_Device.py  : makes sector addresses bank-window relative for every
   sector past the first bank, not only right after a bank switch

Originals are saved next to the patched files as *.orig_xrom. Re-running is safe (idempotent).
Written against FlashGBX 5.1 (installed 2026-09-16); the edits are pattern based so they may apply to nearby versions.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROFILE = "fc_AGB_XROM512M.txt"

FLASHCART_ANCHOR = """\t\t\tself.CartWrite([[0xF12345*2, 0x9413]], fast_write=False)
\t\t\treturn True

\t\treturn False
"""
FLASHCART_INSERT = """\t\t\tself.CartWrite([[0xF12345*2, 0x9413]], fast_write=False)
\t\t\treturn True
\t\telif self.CONFIG["flash_bank_select_type"] == 3: # X-ROM 512M (EasyBuy2000)
\t\t\t# 16-bit register at 0x09000000: write 0x8000 to arm it, then
\t\t\t# 0x8000 | (cart offset >> 17); the helper program that USBCable
\t\t\t# uploads to the GBA maps 16 MiB windows (bits 7-8 of that value).
\t\t\tbank_size = self.CONFIG.get("flash_bank_size", 0x1000000)
\t\t\tvalue = 0x8000 | ((index * bank_size) >> 17)
\t\t\tself.CartWrite([[0x1000000, 0x8000]], fast_write=False)
\t\t\tself.CartWrite([[0x1000000, value]], fast_write=False)
\t\t\treturn True

\t\treturn False
"""
FLASHCART_MARK = 'flash_bank_select_type"] == 3'

# LK_Device.py: three copies of this block (erase, write, verify) with different indentation.
LK_OLD = """if bank != current_bank:
{i}\tflashcart.Reset(full_reset=True)
{i}\tflashcart.SelectBankROM(bank)
{i}\ttemp = end_address - start_address
{i}\tstart_address %= cart_type["flash_bank_size"]
{i}\tend_address = min(cart_type["flash_bank_size"], start_address + temp)
{i}\tcurrent_bank = bank
"""
LK_NEW = """if bank != current_bank:
{i}\tflashcart.Reset(full_reset=True)
{i}\tflashcart.SelectBankROM(bank)
{i}\tcurrent_bank = bank
{i}# X-ROM fix: addresses must always be bank-window relative, not only on a bank change
{i}if start_address >= cart_type["flash_bank_size"]:
{i}\ttemp = end_address - start_address
{i}\tstart_address %= cart_type["flash_bank_size"]
{i}\tend_address = min(cart_type["flash_bank_size"], start_address + temp)
"""
LK_MARK = "# X-ROM fix: addresses must always be bank-window relative"


def patch_flashcart(path: Path, check: bool) -> str:
    s = path.read_text("utf-8")
    if FLASHCART_MARK in s:
        return "already patched"
    if s.count(FLASHCART_ANCHOR) != 1:
        return "ANCHOR NOT FOUND (different FlashGBX version?), left untouched"
    if check:
        return "would patch"
    shutil.copy2(path, path.with_suffix(".py.orig_xrom"))
    path.write_text(s.replace(FLASHCART_ANCHOR, FLASHCART_INSERT, 1), "utf-8")
    return "patched"


def patch_lk_device(path: Path, check: bool) -> str:
    s = path.read_text("utf-8")
    if LK_MARK in s:
        return "already patched"
    n = 0
    for indent in ("\t" * k for k in range(4, 12)):
        old = LK_OLD.format(i=indent)
        if old in s:
            n += s.count(old)
            s = s.replace(old, LK_NEW.format(i=indent))
    if n != 3:
        return f"found {n} bank-switch blocks instead of 3 (different FlashGBX version?), left untouched"
    if check:
        return "would patch 3 blocks"
    shutil.copy2(path, path.with_suffix(".py.orig_xrom"))
    path.write_text(s, "utf-8")
    return "patched 3 blocks"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--flashgbx", default=None, help="FlashGBX install dir (default: the one this python.exe belongs to)")
    ap.add_argument("--config", default=None, help="FlashGBX config dir (default: %%LOCALAPPDATA%%\\FlashGBX)")
    ap.add_argument("--check", action="store_true", help="only report what would be done")
    a = ap.parse_args()

    fg = Path(a.flashgbx) if a.flashgbx else Path(sys.executable).resolve().parent.parent
    pkg = fg / "FlashGBX"
    if not (pkg / "Flashcart.py").is_file():
        print(f"FlashGBX package not found under {fg}; pass --flashgbx")
        return 1
    cfg = Path(a.config) if a.config else Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "FlashGBX"

    src = HERE / PROFILE
    dst = cfg / PROFILE
    if a.check:
        print(f"profile  : {'present' if dst.is_file() and dst.read_bytes() == src.read_bytes() else 'would copy'} -> {dst}")
    else:
        cfg.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"profile  : copied -> {dst}")
    print(f"Flashcart: {patch_flashcart(pkg / 'Flashcart.py', a.check)}")
    print(f"LK_Device: {patch_lk_device(pkg / 'LK_Device.py', a.check)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
