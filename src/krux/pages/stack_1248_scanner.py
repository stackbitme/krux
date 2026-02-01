# The MIT License (MIT)
#
# Copyright (c) 2021-2024 Krux contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import lcd
import sensor
import time
from embit.wordlists.bip39 import WORDLIST
from . import Page
from ..krux_settings import t
from ..themes import theme
from ..display import DEFAULT_PADDING, MINIMAL_PADDING, FONT_HEIGHT, FONT_WIDTH
from ..camera import BINARY_GRID_MODE
from ..wdt import wdt
from ..input import BUTTON_ENTER, BUTTON_PAGE, BUTTON_PAGE_PREV, BUTTON_TOUCH


class StackbitScanner(Page):
    """Uses camera sensor to detect punch pattern on Stackbit 1248 metal plate

    Stackbit 1248 is a metal backup plate for BIP39 seed phrases using
    binary-coded decimal (1-2-4-8) encoding. Each word is represented as
    a 4-digit number (0001-2048).

    Plate specifications:
    - Dimensions: 85mm x 54mm (aspect ratio = 1.574)
    - Grid: 16 columns x 12 rows
    - Capacity: 12 words per side (24 total with front+back)

    Grid layout:
    - Columns 0, 8: Word index numbers (skipped during reading)
    - Columns 1, 9: Milhar digit (1 or 2)
    - Columns 2-7, 10-15: Three pairs of 1-2-4-8 encoding
    """

    def __init__(self, ctx):
        super().__init__(ctx, None)
        self.ctx = ctx
        self.x_regions = []
        self.y_regions = []
        self.blob_otsu = 0x80
        self.debug_mode = True  # Show visual markers for detected punches

    def _detect_plate(self, img):
        """Detect the Stackbit 1248 plate as a bright blob

        Returns the detected plate rectangle (x, y, w, h) or None
        """
        try:
            self.blob_otsu = img.get_histogram().get_threshold().value()
        except:
            pass

        # Use a slightly lower threshold to better detect plate edges
        blob_threshold = [(max(self.blob_otsu - 10, 60), 255)]
        blobs = img.find_blobs(
            blob_threshold, x_stride=20, y_stride=20, area_threshold=3000
        )

        best_rect = None
        best_score = 0

        # Target aspect ratio: 85 / 54 = 1.574
        TARGET_ASPECT = 1.574
        ASPECT_TOLERANCE = 0.25  # Allow 1.324 to 1.824

        for blob in blobs:
            rect = blob.rect()
            if rect[3] == 0:
                continue

            aspect = rect[2] / rect[3]

            # Allow plate to be partially outside the frame
            margin = 5
            if (rect[0] >= -margin and rect[1] >= -margin and
                (rect[0] + rect[2]) < img.width() + margin and
                (rect[1] + rect[3]) < img.height() + margin):

                # Check aspect ratio with tolerance
                if abs(aspect - TARGET_ASPECT) < ASPECT_TOLERANCE:
                    aspect_diff = abs(aspect - TARGET_ASPECT)
                    area_score = min(1.0, blob.area() / 10000)
                    score = (1.0 / (1.0 + aspect_diff * 2)) + area_score * 0.3

                    if score > best_score:
                        best_score = score
                        best_rect = rect

        return best_rect

    def _create_grid_over_rect(self, rect):
        """Create 16x12 grid regions over detected rectangle"""
        self.x_regions = []
        self.y_regions = []

        x, y, w, h = rect

        # 16 columns
        col_width = w / 16
        for i in range(17):
            self.x_regions.append(int(x + i * col_width))

        # 12 rows
        row_height = h / 12
        for i in range(13):
            self.y_regions.append(int(y + i * row_height))

    def _draw_grid(self, img, rect):
        """Draw grid overlay on detected rectangle"""
        # Draw rectangle outline
        img.draw_rectangle(rect, lcd.WHITE, thickness=2)

        # Draw vertical lines (16 columns)
        for i, x in enumerate(self.x_regions):
            thickness = 2 if i in (0, 8) else 1
            img.draw_line(
                x, rect[1],
                x, rect[1] + rect[3],
                lcd.WHITE, thickness=thickness
            )

        # Draw horizontal lines (12 rows)
        for y in self.y_regions:
            img.draw_line(
                rect[0], y,
                rect[0] + rect[2], y,
                lcd.WHITE, thickness=1
            )

    def _read_cell(self, img, x, y, w, h, draw_debug=False):
        """Read a single cell and return True if punched

        Uses multiple detection methods:
        1. Adaptive threshold (luminance-based)
        2. Circular blob detection (shape-based)
        3. Contrast detection (dark vs light)
        """
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return False
        if x + w > img.width() or y + h > img.height():
            return False

        try:
            stats = img.get_statistics(roi=(x, y, w, h))
            cell_lum = stats.l_mean()

            is_punched = False

            # Method 1: Adaptive threshold
            relative_threshold = self.blob_otsu - 30
            if cell_lum < relative_threshold:
                is_punched = True

            # Method 2: Circular blob detection
            if not is_punched:
                try:
                    dark_threshold = max(20, cell_lum - 40)
                    blob_threshold = [(0, dark_threshold)]
                    blobs = img.find_blobs(
                        blob_threshold,
                        roi=(x, y, w, h),
                        pixels_threshold=int(w * h * 0.1),
                        area_threshold=int(w * h * 0.08),
                        merge=True
                    )
                    for blob in blobs:
                        if blob.roundness() > 0.3:
                            is_punched = True
                            break
                except:
                    pass

            # Method 3: High contrast detection
            if not is_punched:
                try:
                    std = stats.l_stdev()
                    if std > 25:
                        is_punched = True
                except:
                    pass

            # Draw debug marker if requested
            if draw_debug and is_punched:
                img.draw_rectangle((x, y, w, h), lcd.BLACK, thickness=2)

            return is_punched
        except:
            return False

    def _create_16x12_grid_regions(self, rect):
        """Create a 16x12 grid over the detected plate"""
        x_regions = []
        y_regions = []

        x_step = rect[2] / 16
        for i in range(17):
            x_regions.append(int(rect[0] + i * x_step))

        y_step = rect[3] / 12
        for i in range(13):
            y_regions.append(int(rect[1] + i * y_step))

        return x_regions, y_regions

    def _read_all_grid_cells(self, img, rect):
        """Read all 16x12 grid cells and return a 2D boolean array"""
        x_regions, y_regions = self._create_16x12_grid_regions(rect)
        grid = []

        for row_idx in range(12):
            row = []
            y = y_regions[row_idx]
            h = y_regions[row_idx + 1] - y

            # Use centered sampling (70% width, 60% height)
            sample_h = int(h * 0.6)
            sample_y = y + int(h * 0.2)

            for col_idx in range(16):
                x = x_regions[col_idx]
                w = x_regions[col_idx + 1] - x
                sample_w = int(w * 0.7)
                sample_x = x + int(w * 0.15)

                is_punched = self._read_cell(
                    img, sample_x, sample_y, sample_w, sample_h, draw_debug=False
                )
                row.append(is_punched)

            grid.append(row)

        return grid, x_regions, y_regions

    def _decode_numbers_from_grid(self, grid):
        """Decode all 12 word numbers from the grid

        Returns list of 12 integers (word numbers 1-2048)
        """
        numbers = []

        # Process left group (words 1-6, columns 0-7)
        for word_idx in range(6):
            row_upper = word_idx * 2
            row_lower = word_idx * 2 + 1

            # Column 1: Milhar (skip col 0 indexer)
            milhar = 0
            if grid[row_upper][1]:
                milhar = 1
            elif grid[row_lower][1]:
                milhar = 2

            # Columns 2-7: Three pairs of 1-2-4-8 encoding
            digits = [milhar]
            for pair_idx in range(3):
                col_left = 2 + pair_idx * 2
                col_right = 3 + pair_idx * 2

                # Left column: upper=1, lower=4
                # Right column: upper=2, lower=8
                val_1 = 1 if grid[row_upper][col_left] else 0
                val_4 = 4 if grid[row_lower][col_left] else 0
                val_2 = 2 if grid[row_upper][col_right] else 0
                val_8 = 8 if grid[row_lower][col_right] else 0

                digit = val_1 + val_2 + val_4 + val_8
                digits.append(digit)

            number = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
            numbers.append(number)

        # Process right group (words 7-12, columns 8-15)
        for word_idx in range(6):
            row_upper = word_idx * 2
            row_lower = word_idx * 2 + 1

            # Column 9: Milhar (skip col 8 indexer)
            milhar = 0
            if grid[row_upper][9]:
                milhar = 1
            elif grid[row_lower][9]:
                milhar = 2

            # Columns 10-15: Three pairs of 1-2-4-8 encoding
            digits = [milhar]
            for pair_idx in range(3):
                col_left = 10 + pair_idx * 2
                col_right = 11 + pair_idx * 2

                val_1 = 1 if grid[row_upper][col_left] else 0
                val_4 = 4 if grid[row_lower][col_left] else 0
                val_2 = 2 if grid[row_upper][col_right] else 0
                val_8 = 8 if grid[row_lower][col_right] else 0

                digit = val_1 + val_2 + val_4 + val_8
                digits.append(digit)

            number = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
            numbers.append(number)

        return numbers

    def _show_stackbit_words(self, grid):
        """Show decoded words in Stackbit 1248 visual format

        Shows 6 words per page with visual grid representation
        """
        numbers = self._decode_numbers_from_grid(grid)

        x_offset = DEFAULT_PADDING
        x_pad = 2 * FONT_WIDTH
        y_pad = FONT_HEIGHT

        def draw_word_row(word_idx, number, y_offset):
            """Draw one word row with Stackbit 1248 visual representation"""
            digits = [
                (number // 1000) % 10,
                (number // 100) % 10,
                (number // 10) % 10,
                number % 10
            ]
            digits_str = "{:04d}".format(number)

            if 1 <= number <= 2048:
                word = WORDLIST[number - 1]
            else:
                word = "????"

            # Draw word index background
            grid_x_offset = x_offset - FONT_WIDTH // 2
            index_x_offset = x_offset + x_pad // 2 - 1
            if len(str(word_idx)) > 1:
                index_x_offset -= FONT_WIDTH

            self.ctx.display.fill_rectangle(
                grid_x_offset,
                y_offset - 2,
                x_pad + FONT_WIDTH // 2,
                2 * y_pad + 2,
                theme.disabled_color,
            )

            self.ctx.display.draw_string(
                index_x_offset,
                y_offset + y_pad // 2,
                str(word_idx),
                theme.fg_color,
                theme.disabled_color,
            )

            # Draw 1-2-4-8 labels
            numbers_offset = x_offset + x_pad
            numbers_offset += (x_pad - FONT_WIDTH) // 2
            upper_numbers = [1, 1, 2, 1, 2, 1, 2]
            lower_numbers = [2, 4, 8, 4, 8, 4, 8]
            label_y_offset = y_offset + (y_pad - FONT_HEIGHT) // 2

            for i in range(len(upper_numbers)):
                self.ctx.display.draw_string(
                    numbers_offset,
                    label_y_offset,
                    str(upper_numbers[i]),
                    theme.fg_color,
                )
                self.ctx.display.draw_string(
                    numbers_offset,
                    label_y_offset + y_pad,
                    str(lower_numbers[i]),
                    theme.fg_color,
                )
                numbers_offset += x_pad

            # Draw grid lines
            width = 8 * x_pad + FONT_WIDTH // 2
            height = 2 * y_pad + 2

            self.ctx.display.draw_line(
                grid_x_offset, y_offset - 2,
                grid_x_offset + width, y_offset - 2,
                theme.frame_color,
            )
            self.ctx.display.draw_line(
                grid_x_offset, y_offset - 2 + height,
                grid_x_offset + width, y_offset - 2 + height,
                theme.frame_color,
            )

            x_bar = x_offset
            self.ctx.display.draw_line(
                grid_x_offset, y_offset - 2,
                grid_x_offset, y_offset - 2 + height,
                theme.frame_color,
            )
            x_bar += x_pad
            self.ctx.display.draw_line(
                x_bar, y_offset - 2,
                x_bar, y_offset - 2 + height,
                theme.frame_color,
            )
            x_bar += x_pad
            for _ in range(4):
                self.ctx.display.draw_line(
                    x_bar, y_offset - 2,
                    x_bar, y_offset - 2 + height,
                    theme.frame_color,
                )
                x_bar += 2 * x_pad

            # Draw punched marks
            outline_width = x_pad - 6
            outline_height = y_pad - 4
            outline_x = x_offset + x_pad + 3

            if digits[0] == 2:
                self.ctx.display.outline(
                    outline_x, y_offset + y_pad + 1,
                    outline_width, outline_height,
                    theme.highlight_color,
                )
            elif digits[0] == 1:
                self.ctx.display.outline(
                    outline_x, y_offset + 1,
                    outline_width, outline_height,
                    theme.highlight_color,
                )

            outline_x += x_pad
            for d in range(3):
                digit = digits[d + 1]
                if (digit >> 3) & 1:
                    self.ctx.display.outline(
                        outline_x + x_pad, y_offset + y_pad + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                if (digit >> 2) & 1:
                    self.ctx.display.outline(
                        outline_x, y_offset + y_pad + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                if (digit >> 1) & 1:
                    self.ctx.display.outline(
                        outline_x + x_pad, y_offset + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                if digit & 1:
                    self.ctx.display.outline(
                        outline_x, y_offset + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                outline_x += 2 * x_pad

            # Draw number and word on the right
            self.ctx.display.draw_string(
                x_offset + 17 * FONT_WIDTH,
                y_offset,
                digits_str,
                theme.highlight_color,
            )
            self.ctx.display.draw_string(
                x_offset + 17 * FONT_WIDTH,
                y_offset + y_pad,
                word,
                theme.disabled_color,
            )

        row_spacing = 6

        # Page 1: Words 1-6
        self.ctx.display.clear()
        self.ctx.display.draw_hcentered_text("Stackbit 1248")
        y_pos = 2 * FONT_HEIGHT
        for i in range(6):
            draw_word_row(i + 1, numbers[i], y_pos)
            y_pos += 2 * y_pad + row_spacing

        self.ctx.input.wait_for_button()

        # Page 2: Words 7-12
        self.ctx.display.clear()
        self.ctx.display.draw_hcentered_text("Stackbit 1248")
        y_pos = 2 * FONT_HEIGHT
        for i in range(6):
            draw_word_row(i + 7, numbers[i + 6], y_pos)
            y_pos += 2 * y_pad + row_spacing

        self.ctx.input.wait_for_button()

    def _validate_and_get_words(self, grid):
        """Decode and validate words from grid

        Returns list of 12 BIP39 words if all valid, None otherwise
        """
        numbers = self._decode_numbers_from_grid(grid)
        words = []

        for number in numbers:
            if 1 <= number <= 2048:
                words.append(WORDLIST[number - 1])
            else:
                return None

        return words

    def scanner(self, w24=False):
        """Scans the Stackbit 1248 plate with manual trigger

        Args:
            w24: If True, scans for 24 words (front + back of plate)

        Returns:
            List of 12 or 24 BIP39 words if successfully read, None otherwise
        """
        page = 0  # 0 = first 12 words, 1 = second 12 words
        all_words = []

        self.ctx.display.clear()
        if w24:
            message = t("Position plate") + "\n" + t("Words 1-12") + "\n" + t("Click to read")
        else:
            message = t("Position plate") + "\n" + t("Click to read")
        self.ctx.display.draw_centered_text(message)
        time.sleep(2)

        self.ctx.camera.initialize_run(mode=BINARY_GRID_MODE)
        self.ctx.camera.zoom_mode()
        self.ctx.display.to_landscape()
        self.ctx.display.clear()

        while True:
            wdt.feed()
            img = self.ctx.camera.snapshot()

            rect = self._detect_plate(img)

            if rect:
                self._create_grid_over_rect(rect)
                self._draw_grid(img, rect)

                # Mark detected punches in real-time
                for row_idx in range(12):
                    y = self.y_regions[row_idx]
                    h = self.y_regions[row_idx + 1] - y
                    sample_h = int(h * 0.6)
                    sample_y = y + int(h * 0.2)

                    for col_idx in range(16):
                        if col_idx == 0 or col_idx == 8:
                            continue

                        x = self.x_regions[col_idx]
                        w = self.x_regions[col_idx + 1] - x
                        sample_w = int(w * 0.7)
                        sample_x = x + int(w * 0.15)

                        self._read_cell(img, sample_x, sample_y, sample_w, sample_h, True)

            # Display image
            lcd.display(img)

            # Check for click/touch to perform final reading
            if self.ctx.input.enter_event() or self.ctx.input.touch_event(validate_position=False):
                if rect:
                    sensor.run(0)
                    self.ctx.display.to_portrait()

                    grid, x_regions_viz, y_regions_viz = self._read_all_grid_cells(img, rect)
                    self._show_stackbit_words(grid)

                    words = self._validate_and_get_words(grid)

                    if words:
                        if w24:
                            if page == 0:
                                all_words = words[:]
                                page = 1

                                self.ctx.display.clear()
                                self.flash_text(
                                    t("Flip plate") + "\n" +
                                    t("Words 13-24") + "\n\n" +
                                    t("Click to read")
                                )

                                self.ctx.camera.initialize_run(mode=BINARY_GRID_MODE)
                                self.ctx.camera.zoom_mode()
                                self.ctx.display.to_landscape()
                                self.ctx.display.clear()
                                continue
                            else:
                                all_words.extend(words)
                                return all_words
                        else:
                            return words

                    # Invalid words - return to scanning
                    self.ctx.display.to_landscape()
                    self.ctx.camera.initialize_run(mode=BINARY_GRID_MODE)
                    self.ctx.camera.zoom_mode()
                    continue

            # Check for exit
            if self.ctx.input.page_event() or self.ctx.input.page_prev_event():
                break

        sensor.run(0)
        self.ctx.display.to_portrait()
        return None
