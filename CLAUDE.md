# Stackbit 1248 Scanner - Krux Project

## Project Overview

This is a fork of the Krux firmware with a custom **Stackbit 1248 Scanner** feature for the **maixpy_embed_fire** device (Embed Fire / WonderK).

**Repository:** odudex/krux
**Branch:** embed_fire
**Device:** maixpy_embed_fire
**Working directory:** `/Users/valandro/Downloads/krux_odudex/`

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

## Supported Plates

| Plate | Dimensions | Aspect Ratio | Orientation | Grid | Words/scan |
|-------|-----------|--------------|-------------|------|------------|
| **1248** (Full) | 85mm × 54mm | 1.574 | Landscape | 16×12 | 12 |
| **1248mini** | 42.5mm × 54mm | 0.787 | Portrait | 8×12 | 6 |

The scanner auto-detects the plate type based on aspect ratio.

---

## Scanner Features

- **Camera-based detection** of Stackbit 1248 metal plates (Full and Mini)
- **Auto plate type detection** based on aspect ratio
- **Grid overlay** adapts to detected plate (16×12 for Full, 8×12 for Mini)
- **Multi-method punch detection:**
  - Adaptive threshold (luminance-based)
  - Circular blob detection (shape-based)
  - High contrast detection
- **Rounded corner filter** ignores plate corner cells (3mm radius causes false detections)
- **Real-time visualization** with black squares marking detected punches
- **Visual Stackbit 1248 display** (6 words per page with grid representation)
- **Word editing after scan** - touch any word to open 1248 editor, Go confirms, Esc cancels
- **Back/Next page navigation** in word display (touch footer or use buttons)
- **12 and 24 word support**
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
| `src/krux/pages/stack_1248_scanner.py` | Main scanner implementation |
| `src/krux/pages/stack_1248.py` | Manual entry implementation (existing) |
| `src/krux/pages/mnemonic_loader.py` | Menu integration |

---

## Version History

| Tag | Commit | Date | Changes |
|-----|--------|------|---------|
| `scanner-v0.1.0` | `6c0257b` | 01/02/2026 | Base working version - camera scanner, 12/24 word support |
| `scanner-v0.2.0` | `9f695ff` | 01/02/2026 | 1248mini plate support, improved blob detection (stride 5), centering score |
| `scanner-v0.3.0` | `bd6b6fe` | 06/02/2026 | ~~Fix grid alignment~~ **REVERTED** - piorou leitura |
| current | `57c2cb3` | 06/02/2026 | Revert para v0.2.0 (versão estável) |
| `scanner-v0.4.0` | `78bfd8a` | 01/03/2026 | Word editing after scan, rounded corner filter |

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

### Full Plate (1248)

| Property | Value |
|----------|-------|
| Dimensions | 85mm × 54mm |
| Aspect ratio | 1.574 (landscape) |
| Rounded corners | 2mm radius |
| Grid | 16 columns × 12 rows |
| Capacity | 12 words per side (24 total) |

### Mini Plate (1248mini)

| Property | Value |
|----------|-------|
| Dimensions | 42.5mm × 54mm |
| Aspect ratio | 0.787 (portrait) |
| Grid | 8 columns × 12 rows |
| Capacity | 6 words per side (12 total with front+back) |

---

## Technical Notes

### Grid Layout - Full Plate (16×12)

```
Col:  0   1   2-3   4-5   6-7  |  8   9   10-11  12-13  14-15
     idx mil  cen   dez   uni  | idx mil  cen    dez    uni
Row 0: Word 1 upper            | Word 7 upper
Row 1: Word 1 lower            | Word 7 lower
...
Row 10: Word 6 upper           | Word 12 upper
Row 11: Word 6 lower           | Word 12 lower
```

### Grid Layout - Mini Plate (8×12)

```
Col:  0   1   2-3   4-5   6-7
     idx mil  cen   dez   uni
Row 0: Word 1 upper
Row 1: Word 1 lower
...
Row 10: Word 6 upper
Row 11: Word 6 lower
```

- Columns 0 (and 8 on Full): Indexers (word numbers - skipped)
- Columns 1 (and 9 on Full): Milhar digit (1 or 2)
- Columns 2-7 (and 10-15 on Full): Three pairs of 1-2-4-8 encoding

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

### 12-Word Mode - Full Plate (1248)
1. Position plate under camera
2. Wait for grid alignment (16×12 grid appears)
3. Click/touch to capture
4. View visual Stackbit 1248 table (page 1: words 1-6, page 2: words 7-12)
5. Touch any word to edit it (opens 1248 editor, Go confirms, Esc cancels)
6. Navigate pages with Back/Next footer buttons
7. If valid → returns words → Krux shows fingerprint → Load wallet

### 12-Word Mode - Mini Plate (1248mini)
1. Position **front** of mini plate (words 1-6)
2. Wait for grid alignment (8×12 grid appears)
3. Click/touch to capture
4. View visual table (words 1-6)
5. **"Flip plate / Words 7-12"** message
6. Position **back** of mini plate (words 7-12)
7. Click/touch to capture
8. View visual table (words 7-12)
9. If valid → returns 12 words → Krux shows fingerprint → Load wallet

### 24-Word Mode (Full Plate only)
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

### Plate Detection (`_detect_plate`)
- Uses `find_blobs()` with `merge=True` and stride 5 for accurate edges
- Scores by: aspect ratio (50%) + area (35%) + centering (15%)
- Auto-detects Full vs Mini based on aspect ratio

### Important: Do NOT change punch detection logic
Changes to `_read_cell()` or blob detection parameters have historically
degraded reading quality. The current v0.2.0 parameters are stable.
Any improvements should be tested very carefully before committing.

### Punch Detection (`_read_cell`)

#### 1. Adaptive Threshold
```python
relative_threshold = blob_otsu - 30
is_punched = cell_lum < relative_threshold
```

#### 2. Circular Blob Detection
```python
blobs = img.find_blobs(threshold, roi=cell, ...)
is_punched = any(blob.roundness() > 0.3)
```

#### 3. High Contrast Detection
```python
is_punched = cell_stats.l_stdev() > 25
```

**Combined Logic:** Punch detected if ANY method indicates presence (OR).

---

## Future Improvements

- [ ] Adjustable detection thresholds in settings
- [ ] Different lighting conditions presets
- [ ] Export scanned data before loading
- [ ] Snap effect (grid locks when stable for several frames)

---

## Development Tips

### Testing Changes
1. Modify `stack_1248_scanner.py`
2. Build with `./krux build maixpy_embed_fire`
3. Flash `build/kboot.kfpkg` to device
4. Test via: Load Mnemonic → Via Camera → Stackbit 1248

### Git Versioning
```bash
# After each change, commit and tag
git add src/krux/pages/stack_1248_scanner.py
git commit -m "feat: description of change"
git tag scanner-vX.Y.Z -m "description"

# To revert to a specific version
git checkout scanner-vX.Y.Z -- src/krux/pages/stack_1248_scanner.py
```

### Key Methods to Understand
- `_detect_plate()` - Blob detection for plate edges (Full + Mini)
- `_read_cell()` - Multi-method punch detection
- `_decode_6_words_from_half()` - 1-2-4-8 to decimal for 6 words
- `_decode_numbers_from_grid()` - Full decoder (6 or 12 words)
- `_edit_single_word()` - Opens Stackbit 1248 editor for a single word (reuses `Stackbit` class)
- `_show_stackbit_words()` - Interactive word display with editing, returns edited numbers
- `_numbers_to_words()` - Convert word numbers to BIP39 words
- `scanner()` - Main loop with Full/Mini auto-detect, 12/24 word support

---

## Credits

- **Stackbit 1248 Format:** Created by stackbit.me
- **Scanner Implementation:** Developed for Krux firmware
- **Repository:** odudex/krux (fork with Embed Fire support)
