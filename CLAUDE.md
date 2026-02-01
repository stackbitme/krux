# Stackbit 1248 Scanner - Krux Project

## Project Overview

This is a fork of the Krux firmware with a custom **Stackbit 1248 Scanner** feature for the **maixpy_embed_fire** device (Embed Fire / WonderK).

**Repository:** odudex/krux
**Branch:** embed_fire
**Device:** maixpy_embed_fire

---

## What is Stackbit 1248?

Stackbit 1248 is a metal backup plate for BIP39 seed phrases that uses binary-coded decimal (1-2-4-8) encoding. Each word is represented as a 4-digit number (0001-2048) with the following grid layout:

```
1  1  2  1  2  1  2   (upper row)
2  4  8  4  8  4  8   (lower row)
```

- **Milhar (thousands):** 1 or 2 (upper=1, lower=2)
- **Centenas/Dezenas/Unidades:** 1-2-4-8 encoding per digit pair

**Website:** https://stackbit.me
**Tutorial:** https://stackbit.me/tutorial-stackbit-1248/

---

## Scanner Features

- **Camera-based detection** of Stackbit 1248 metal plates
- **16x12 grid overlay** adapts to detected plate (85mm × 54mm)
- **Multi-method punch detection:**
  - Adaptive threshold (luminance-based)
  - Circular blob detection (shape-based)
  - High contrast detection
- **Real-time visualization** with black squares marking detected punches
- **Visual Stackbit 1248 display** (6 words per page with grid representation)
- **12 and 24 word support** (scan front, flip, scan back)
- **Auto wallet loading** - returns words directly to Krux load flow

---

## Menu Location

After installation, the scanner is available at:

```
Load Mnemonic → Via Camera → Stackbit 1248
```

Manual entry remains at:
```
Load Mnemonic → Via Manual Input → Stackbit 1248
```

---

## Key Files

| File | Description |
|------|-------------|
| `src/krux/pages/stack_1248_scanner.py` | Main scanner implementation (~1040 lines) |
| `src/krux/pages/stack_1248.py` | Manual entry implementation (existing) |
| `src/krux/pages/mnemonic_loader.py` | Menu integration |
| `STACKBIT_1248_SCANNER_CHANGELOG.md` | Detailed development changelog |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0.0 | 31/01/2026 | Initial release with consistent centered sampling (70%×60%) |
| v1.1.0 | 31/01/2026 | Fixed 1-2-4-8 bit mapping, improved plate detection (85×54mm), visual display |
| v1.2.0 | 31/01/2026 | Auto wallet loading, menu reorganization |
| v1.3.0 | 01/02/2026 | 24-word support, removed ASCII grid, improved row spacing |

---

## Build Commands

```bash
# Build firmware
./krux build maixpy_embed_fire

# Firmware output
build/kboot.kfpkg

# Flash to device (macOS example)
sudo ./build/ktool-mac -B dan -b 1500000 -p /dev/cu.usbserial-XXX build/kboot.kfpkg
```

---

## Plate Specifications

| Property | Value |
|----------|-------|
| Dimensions | 85mm × 54mm |
| Aspect ratio | 1.574 |
| Rounded corners | 2mm radius |
| Grid | 16 columns × 12 rows |
| Capacity | 12 words per side (24 total) |

---

## Technical Notes

### Grid Layout (16×12)

```
Col:  0   1   2-3   4-5   6-7  |  8   9   10-11  12-13  14-15
     idx mil  cen   dez   uni  | idx mil  cen    dez    uni
Row 0: Word 1 upper            | Word 7 upper
Row 1: Word 1 lower            | Word 7 lower
...
Row 10: Word 6 upper           | Word 12 upper
Row 11: Word 6 lower           | Word 12 lower
```

- Columns 0, 8: Indexers (word numbers - skipped)
- Columns 1, 9: Milhar digit (1 or 2)
- Columns 2-7, 10-15: Three pairs of 1-2-4-8 encoding

### 1-2-4-8 Bit Mapping

```python
# For each digit pair (cols 2-3, 4-5, 6-7):
# Left column: upper=1, lower=4
# Right column: upper=2, lower=8
val_1 = 1 if grid[row_upper][col_left] else 0
val_4 = 4 if grid[row_lower][col_left] else 0
val_2 = 2 if grid[row_upper][col_right] else 0
val_8 = 8 if grid[row_lower][col_right] else 0
digit = val_1 + val_2 + val_4 + val_8
```

### Centered Sampling

For consistent detection between live camera and final reading:
- Width: 70% of cell (15% offset from left)
- Height: 60% of cell (20% offset from top)

---

## Scanner Flow

### 12-Word Mode
1. Position plate under camera
2. Wait for grid alignment
3. Click/touch to capture
4. View visual Stackbit 1248 table (page 1: words 1-6, page 2: words 7-12)
5. If valid → returns words → Krux shows fingerprint → Load wallet

### 24-Word Mode
1. Position **front** of plate (words 1-12)
2. Click/touch to capture
3. View visual table (pages 1-2)
4. **"Flip plate / Words 13-24"** message
5. Position **back** of plate (words 13-24)
6. Click/touch to capture
7. View visual table (pages 1-2)
8. If valid → returns 24 words → Krux shows fingerprint → Load wallet

---

## Detection Methods

### 1. Adaptive Threshold
```python
relative_threshold = blob_otsu - 30
is_punched = cell_lum < relative_threshold
```

### 2. Circular Blob Detection
```python
blobs = img.find_blobs(threshold, roi=cell, ...)
is_punched = any(blob.roundness() > 0.3)
```

### 3. High Contrast Detection
```python
is_punched = cell_stats.l_stdev() > 25
```

**Combined Logic:** Punch detected if ANY method indicates presence (OR).

---

## Future Improvements

- [ ] Support for Stackbit 1248 Mini (half-width plate)
- [ ] Adjustable detection thresholds in settings
- [ ] Different lighting conditions presets
- [ ] Export scanned data before loading

---

## Development Tips

### Testing Changes
1. Modify `stack_1248_scanner.py`
2. Build with `./krux build maixpy_embed_fire`
3. Flash `build/kboot.kfpkg` to device
4. Test via: Load Mnemonic → Via Camera → Stackbit 1248

### Key Methods to Understand
- `_detect_plate()` - Blob detection for plate edges
- `_read_cell()` - Multi-method punch detection
- `_decode_numbers_from_grid()` - 1-2-4-8 to decimal conversion
- `_show_stackbit_words()` - Visual table rendering
- `scanner()` - Main loop with 12/24 word support

---

## Credits

- **Stackbit 1248 Format:** Created by stackbit.me
- **Scanner Implementation:** Developed for Krux firmware
- **Repository:** odudex/krux (fork with Embed Fire support)
