# X-ROM 512M write protocol

Source: disassembly of the "XROM OS" helper that `USBCable.exe` (X-Rom Testing Tools v2.1) and
LittleWriter upload to the GBA (`xromos_usbcable.mb`, 10,680 bytes, pure ARM, loads at
0x02000000). Extracted 2026-10-30. Cross-checked against PogoShell's `libfc_xrom` driver.

## Hardware picture

* Two 8-bit AMD/Spansion-compatible flash chips side by side form the 16-bit cart bus
  (low byte = chip A, high byte = chip B). Every command word is therefore doubled:
  `0xAAAA`, `0x5555`, `0x9090`, `0x8080`, `0x3030`, `0x2525`, `0x2929`, `0xF0F0`.
* Because each chip sees byte addresses, the AMD unlock addresses are the *byte-mode* ones:
  halfword index `0xAAA` (GBA byte offset `0x1554`) and halfword index `0x555` (byte `0xAAA`).
* Helper convention in the code: `WI(idx, v)` = `strh v, [0x08000000 + idx*2]`,
  `W16(addr, v)` = `strh v, [addr]`, `RI(idx)` = `ldrh [0x08000000 + idx*2]`.
* Chip identity expected for cart type 0x62 ("XROM 512M"): autoselect bytes
  `RI(0)=0x01` (manufacturer AMD/Spansion), `RI(2)=0x7E`, `RI(0x1C)=0x12`, `RI(0x1E)=0x01`
  (per chip; both bytes of each halfword should agree). 0x7E/0x12/0x01 matches the
  Spansion GL-M MirrorBit family, i.e. 2 x 256 Mbit = 64 MiB. Sector size used by the
  helper: 0x20000 bytes (two 64 KiB sectors in parallel). To be confirmed on hardware.

## Controller register at 0x09000000 (16-bit writes)

`W16(0x09000000, 0x8000)` arms the register, the next `W16(0x09000000, value)` sets it:

| value | effect |
| --- | --- |
| `0x8000 \| (offset >> 17)` | map the 64 MiB cart so that `offset` (128 KiB units, 0..511) appears at 0x08000000 (PogoShell uses this to start a ROM; the helper uses it to put the sector to erase at window offset 0, and masks to 16 MiB steps when programming) |
| `0x8000 \| (sram_offset >> 16) << 11` | SRAM bank select (from `libfc_xrom/main.c`) |
| single write `0` (no 0x8000 first) | reset to normal mapping (helper does this after erasing and before exit) |

## Start-up writes done once by the helper (purpose unknown, replicate for safety)

```
W16(0x0930ECA8, 0x5354)   ; WI(0x987654, 'ST')
W16(0x09E2468A, 0x9413)   ; WI(0xF12345, 0x9413)
```
Other cart types also get `WI(0x987654,0x5354)` + `WI(0xB5AC97, mode)`; not used for 0x62.

## Chip ID (helper function 0x02000408)

```
W16(0x09000000, 0x8000); W16(0x09000000, 0x8000)      ; bank register -> window at 0
WI(0xAAA, 0xAAAA); WI(0x555, 0x5555); WI(0xAAA, 0x9090) ; autoselect
mfr = RI(0) & 0xFF; dev = RI(2) & 0xFF; e1 = RI(0x1C) & 0xFF; e2 = RI(0x1E) & 0xFF
WI(0, 0xF0F0)                                          ; reset
ok = (mfr == 0x01 and dev == 0x7E and e1 == 0x12 and e2 == 0x01)
```

## Sector erase (helper function 0x020008D4, used by command 1 for type 0x62)

For each 128 KiB sector at cart offset `a` (count sectors, `a += 0x20000`):
```
WI(0x800000, 0x8000)                   ; = W16(0x09000000, 0x8000)
WI(0x800000, 0x8000 | (a >> 17))       ; window now starts at the sector
WI(0xAAA, 0xAAAA); WI(0x555, 0x5555); WI(0xAAA, 0x8080)
WI(0xAAA, 0xAAAA); WI(0x555, 0x5555); WI(0, 0x3030)   ; sector erase at window offset 0
loop: until (RI(0) & 0x8080) == 0x8080                  ; DQ7 on both chips
```
Afterwards: `WI(0x800000, 0)` (bank register reset).

## Program (helper function 0x02000F60, used by command 2 for type 0x62)

Write-to-buffer programming, 32 halfwords (64 bytes) per buffer, destination `d`
(cart offset, must stay inside one 128 KiB sector per buffer):
```
W16(0x09000000, 0x8000); W16(0x09000000, 0x8000 | ((d >> 17) & 0x180))  ; 16 MiB window
w = 0x08000000 + (d & 0xFFFFFF)          ; address inside the window
s = w & ~0x1FFFF                         ; sector base
W16(s + 0x1554, 0xAAAA); W16(s + 0xAAA, 0x5555)
W16(w, 0x2525)                           ; write to buffer
W16(w, 0x1F1F)                           ; word count - 1 = 31 (per chip)
W16(w + 2*i, data[i])  for i in 0..31
W16(w, 0x2929)                           ; program buffer to flash
poll R16(w + 0x3E): done when bit7 (and bit15 for chip B) equals the last data word's
      bit7/bit15; if DQ5 (0x22 / 0x2200) sets while mismatched -> error
```
The helper re-arms the bank register whenever `d` crosses into the next 16 MiB quarter.

## Confirmed on hardware (GBFlash v1.3, FlashGBX 5.1, 2026-10-30)

* Autoselect through the GBFlash returns, in GBA byte offsets:
  `0000: 01 01 01 01 7E 7E 7E 7E 00 00 00 00 08 08 08 08 / 0010: 03 03 03 03 ... / 0038: 12 12 12 12 01 01 01 01`
  i.e. manufacturer 01, device 7E, extended 12 01 on both chips: Spansion GL-M family,
  two 256 Mbit parts in byte mode. Each chip address occupies 4 GBA bytes here because the
  chips ignore their lowest address line in autoselect mode.
* CFI query (0x98 at chip address 0x55 or 0xAA) returns no "QRY" through this path.
* Bank register works exactly as decoded: arming write 0x8000 then `0x8000 | (offset >> 17)`
  at 0x09000000 maps any 16 MiB window; all four windows read correctly.
* A full 64 MiB read through FlashGBX with the profile below was byte-identical to the
  image that USBCable had written and verified (2 minutes vs 9 over the link cable).

## Write tests through the GBFlash (2026-10-30)

* `xrom_sector_test.py`: last 128 KiB sector (blank padding) erased in 0.7 s, 1 KiB
  programmed word by word and read back correctly, erased again; cart restored.
* FlashGBX `--action flash-rom --compare-sectors` with an image that differs only in that
  sector: "The ROM was written and verified successfully!" (42 s including the compare).
  This needed one fix in `LK_Device.py`: in the three bank-switching blocks of the write and
  verify loops, addresses were made window-relative only on a bank change, so the second
  and later sectors of a bank were addressed absolutely. With 32 MiB banks the GBA address
  space wraps and nobody noticed; with 16 MiB windows the sector-erase write went to
  0x09xxxxxx (the controller) and timed out. Patched to reduce the address whenever it is
  past the bank size (see `flashgbx-5.1-xrom.patch`).
* Note: in this FlashGBX build `--compare-sectors` defaults to on (argparse default=True,
  and `CompareSectors = enabled` in settings.ini), so flashing an image identical to the
  cart writes nothing and ends with "ROM writing complete!" (no verify ran). A genuine
  full-write test therefore needs an image that differs from the cart.
* Cosmetic: the CLI's own flash-ID check right after connecting sometimes reads ROM bytes
  instead of the ID (first command after a reconnect); a cart power cycle or a second
  attempt fixes it. It is only a warning in the CLI.

## Full-cart writes through the GBFlash (2026-10-30 evening)

| Step | Image | Result | Time |
| --- | --- | --- | --- |
| A | original backup (Kirby + Pokémon Emerald, 64 MiB, differs from cart nearly everywhere) | written and verified | 37 min |
| B | PogoShell image (64 MiB padded) back on top | written and verified | 32.5 min |

An independent full read afterwards matched the PogoShell image byte for byte. Per-word
programming is the bottleneck (~30 KB/s end to end, including 512 sector erases at 0.7 s
each). Incremental updates with compare-sectors take under a minute per changed sector;
whole-cart rewrites are faster over the link cable with USBCable (15 min) until a buffered
write mode that doubles the word count for the two chips exists in the GBFlash firmware.

## Buffered programming through FlashGBX (2026-10-30, 20:30)

* Variant A (profile with the doubled count `0x1F1F` as a literal): FAILED. Only the
  low-byte chip programmed; the firmware substitutes its own computed count (0x001F) at that
  position, so chip B received a count of 0.
* Variant B (`"double_die": true` + the normal `"BS"` placeholder): WORKS. FlashGBX's
  double-die support makes the firmware double the buffer word count, exactly what two
  parallel byte-wide chips need. Sector test written and verified.
* Full write of a new 8-game PogoShell image (57.5 MiB of content, ~440 differing sectors)
  with the buffered profile: written and verified in 18.5 min (20:34 -> 20:52), about half
  the per-word time. Roughly 6 min of that is sector erasing; `--prefer-chip-erase` (the
  profile now has `chip_erase`) should trim a few more minutes on full rewrites.
* The main profile `fc_AGB_XROM512M.txt` now carries `buffer_size: 64`, `double_die: true`,
  `buffer_write` and `chip_erase`; `single_write` remains as the fallback.

## FlashGBX integration

* Profile: `fc_AGB_XROM512M.txt` (AMD command set, doubled values, byte-mode unlock
  addresses 0x1554 / 0xAAA, `flash_ids` = the 8 bytes above, 64 MiB in four 16 MiB banks,
  128 KiB sectors, buffered programming through `double_die`, per-word `single_write` as
  the fallback).
* `Flashcart.py`: new `flash_bank_select_type` 3 that performs the two register writes.
* `LK_Device.py`: window-relative addresses for every sector past the first bank.
* Both source changes are in `flashgbx-5.1-xrom.patch`; `install_xrom_profile.py` applies
  them to an installed FlashGBX.
