# X-ROM 512M support for FlashGBX

Everything needed to read and write an EasyBuy2000 **X-ROM 512M** (64 MiB, 2004) with a
**GBFlash** cart reader through **FlashGBX 5.1**. Not affiliated with FlashGBX. Reverse-engineered from the "XROM OS" helper
that USBCable/LittleWriter upload to the GBA, and verified on the cart on 2026-10-30
(full 64 MiB reads, sector writes, three full 64 MiB writes, buffered programming, verify).

## What is in here

| File | Purpose |
| --- | --- |
| `fc_AGB_XROM512M.txt` | The cart profile: chip IDs, 64 MiB in four 16 MiB banks, 128 KiB sectors, doubled AMD commands for the two parallel x8 chips, buffered writes. |
| `flashgbx-5.1-xrom.patch` | Unified diff of the two small FlashGBX source changes (for reading, or `git apply` on a source checkout). |
| `install_xrom_profile.py` | Installs the profile and applies the same two changes to an installed FlashGBX, with backups. Idempotent. |

The profile alone is **not** enough: FlashGBX has no bank-select type for the X-ROM register,
and its sector loop only rebases addresses into the bank window right after a bank switch.
Both are fixed by the patch.

## Install

```
"%LOCALAPPDATA%\Programs\FlashGBX\Python\python.exe" install_xrom_profile.py
```

Add `--check` to see what it would do. Originals are kept as `*.orig_xrom`. Updating FlashGBX
replaces the two source files, so run the installer again afterwards.

## Flash a ROM

GUI: connect the GBFlash, insert the cart, pick **X-ROM 512M (EasyBuy2000, 2x AMD/Spansion
x8 chips)** as the flash cart type (do not rely on auto-detect), then **Write ROM**.

Command line (the form the verified flashes used; `--device-port` is optional when only one reader is plugged in):

```
"%LOCALAPPDATA%\Programs\FlashGBX\Python\python.exe" -m FlashGBX --cli --mode agb --action flash-rom --device-port COM4 --flashcart-type "X-ROM 512M (EasyBuy2000, 2x AMD/Spansion x8 chips)" image.gba
```

```
"%LOCALAPPDATA%\Programs\FlashGBX\Python\python.exe" -m FlashGBX --cli --mode agb --action backup-rom --overwrite --device-port COM4 --flashcart-type "X-ROM 512M (EasyBuy2000, 2x AMD/Spansion x8 chips)" --agb-romsize 64mb cart_backup.gba
```

What to expect with GBFlash v1.3, firmware L15:

| Operation | Time |
| --- | --- |
| Full 64 MiB read | about 2 min |
| Full 64 MiB write, buffered, with verify | 18 to 23 min |
| Full 64 MiB write, per word (if `buffer_size` is removed) | 32 to 37 min |

## Things to know

- **Flash the whole cart image.** PogoShell images should be padded to 64 MiB. Sector compare
  (`--compare-sectors`, on by default in this build) then skips sectors that already match,
  so re-flashing a slightly changed image is quick.
- **ID read right after connecting** can show ROM bytes instead of `01 01 01 01 7E 7E 7E 7E`;
  reconnect or power-cycle the cart. The same applies if a read returns a repeating
  `46 46 46 46 06 06 06 06` pattern: the chip is still in command mode.
- **Save memory is banked.** The cart has 256 KiB of SRAM in four 64 KiB banks selected through
  the same register (`0x8000`, then `bank << 11` at cart offset `0x1000000`). FlashGBX's own
  save backup only sees bank 0. `XRomFront2026\xromfront\gbflash_sram.py` dumps and restores all
  four banks and understands PogoShell's save filesystem.
- **Real-time clock.** The X-ROM has a standard GBA GPIO RTC. FlashGBX detects it on a PogoShell
  image and can set it from its RTC dialog; `XRomFront2026\xromfront\gbflash_rtc.py set` does
  the same from the command line.
- **Buffered writes need `"double_die": true`** in the profile, which makes the firmware double
  the buffer word count for the two chips. A literal doubled count (`0x1F1F`) only programs one
  chip.

## Protocol reference

See [PROTOCOL.md](PROTOCOL.md) for the full register and command description, including the
helper disassembly it was derived from.

## Credits

This work stands on other people's projects:

- **[FlashGBX](https://github.com/lesserkuma/FlashGBX)** by Lesserkuma, the reader/writer this
  adds a cart to, and the **GBFlash** hardware it drives.
- **[PogoShell](https://github.com/NuVanDibe/Pogoshell-K)** by sasq (Jonas Minnberg, 2003-2004),
  with Kuwanger's later Pogoshell-K fork kept alive by NuVanDibe. Its `libfc_xrom` driver was the
  second source for the bank-register protocol and PogoShell images were the test material for
  every full-cart write here; the save-filesystem notes come from its `sramfile.c`.
- **[Revolution81's GBA-X-Rom-Windows-11](https://github.com/Revolution81/GBA-X-Rom-Windows-11)**,
  which brought the original X-Rom USB link cable back to life on Windows 11 with a WinUSB shim
  for the 2003 kernel drivers. The cable route is how the first full cart backup was taken and is
  the cross-check that the GBFlash writes were verified against.
- **EasyBuy2000** (2004), makers of the X-ROM 512M and of the USBCable/MRTool/LittleWriter
  helpers whose GBA-side "XROM OS" program is the primary source of the protocol.

## Licence

MIT, like FlashGBX itself. Material from the projects above stays under their own licences.

## AI disclosure

This project was built with Claude (Anthropic) working as a coding agent under the author's
direction: the helper disassembly, the FlashGBX patch, the installer, the hardware tests and
these documents were produced in that collaboration. Every write path described here was
verified on a real X-ROM 512M through a GBFlash v1.3 before being written up. Mistakes are
still possible; back up your cart before flashing.
