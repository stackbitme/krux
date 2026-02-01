11# The MIT License (MIT)
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
import image
import sensor
import time
from embit.wordlists.bip39 import WORDLIST
from . import Page, FLASH_MSG_TIME
from ..krux_settings import t
from ..themes import theme
from ..display import DEFAULT_PADDING, MINIMAL_PADDING, FONT_HEIGHT, FONT_WIDTH
from ..camera import BINARY_GRID_MODE
from ..wdt import wdt
from ..kboard import kboard


class StackbitScanner(Page):
    """Uses camera sensor to detect punch pattern on Stackbit 1248 metal plate"""

    def __init__(self, ctx):
        super().__init__(ctx, None)
        self.ctx = ctx
        self.x_regions = []
        self.y_regions = []
        self.blob_otsu = 0x80
        self.detection_start_time = None
        self.last_rect = None
        self.debug_mode = True  # Show visual markers for detected punches

    def _detect_plate(self, img):
        """Detect the Stackbit 1248 plate as a bright blob

        Plate dimensions: 85mm x 54mm (aspect ratio = 1.574)
        Corners are rounded with 2mm radius
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

            # Allow plate to be partially outside the frame (for easier positioning)
            margin = 5
            if (rect[0] >= -margin and rect[1] >= -margin and
                (rect[0] + rect[2]) < img.width() + margin and
                (rect[1] + rect[3]) < img.height() + margin):

                # Check aspect ratio with tolerance
                if abs(aspect - TARGET_ASPECT) < ASPECT_TOLERANCE:
                    # Score based on how close to ideal aspect ratio
                    aspect_diff = abs(aspect - TARGET_ASPECT)
                    # Also consider blob area (larger is better)
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
            # Make indexador columns (0 and 8) thicker
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
        """Read a single cell and return True if punched, False if not

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

            # Method 1: Adaptive threshold based on image histogram
            # blob_otsu represents the image's brightness baseline
            # Detect cells that are 30+ points darker than this baseline
            relative_threshold = self.blob_otsu - 30
            if cell_lum < relative_threshold:
                is_punched = True

            # Method 2: Circular blob detection for rounded marker dots
            # Look for dark circular blobs within the cell
            if not is_punched:
                try:
                    # Create threshold for dark blobs (black marker dots)
                    dark_threshold = max(20, cell_lum - 40)  # At least 40 points darker than cell average
                    blob_threshold = [(0, dark_threshold)]

                    # Find dark blobs in this cell ROI
                    blobs = img.find_blobs(
                        blob_threshold,
                        roi=(x, y, w, h),
                        pixels_threshold=int(w * h * 0.1),  # At least 10% of cell area
                        area_threshold=int(w * h * 0.08),   # Minimum blob area
                        merge=True
                    )

                    # Check if any blob is reasonably circular (roundness > 0.4)
                    for blob in blobs:
                        roundness = blob.roundness()
                        # Roundness ranges from 0 (line) to 1 (perfect circle)
                        # Marker dots should be reasonably round (> 0.3)
                        if roundness > 0.3:
                            is_punched = True
                            break
                except:
                    pass  # If blob detection fails, rely on threshold method

            # Method 3: High contrast detection
            # Check if there's significant contrast within the cell
            if not is_punched:
                try:
                    # Check standard deviation - high std means high contrast (dark dot present)
                    std = stats.l_stdev()
                    # If standard deviation is high, there's a dark spot in the cell
                    if std > 25:  # High contrast threshold
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
        """Create a 16×12 grid over the detected plate for visualization

        Args:
            rect: (x, y, w, h) of detected plate

        Returns:
            (x_regions, y_regions) - lists of x and y coordinates for 16×12 grid
        """
        x_regions = []
        y_regions = []

        # 16 columns
        x_step = rect[2] / 16
        for i in range(17):  # 17 points for 16 columns
            x_regions.append(int(rect[0] + i * x_step))

        # 12 rows
        y_step = rect[3] / 12
        for i in range(13):  # 13 points for 12 rows
            y_regions.append(int(rect[1] + i * y_step))

        return x_regions, y_regions

    def _read_all_grid_cells(self, img, rect):
        """Read all 16×12 grid cells and return a 2D boolean array

        Args:
            img: Camera image
            rect: (x, y, w, h) of detected plate

        Returns:
            2D list [row][col] where True = punched, False = not punched
        """
        # Create 16×12 grid over the detected plate
        x_regions, y_regions = self._create_16x12_grid_regions(rect)

        grid = []

        # Read all 12 rows
        for row_idx in range(12):
            row = []
            y = y_regions[row_idx]
            h = y_regions[row_idx + 1] - y

            # Use centered sampling (same as live camera detection)
            # 60% height, 20% offset from top
            sample_h = int(h * 0.6)
            sample_y = y + int(h * 0.2)

            # Read all 16 columns
            for col_idx in range(16):
                x = x_regions[col_idx]
                w = x_regions[col_idx + 1] - x

                # Use centered sampling (same as live camera detection)
                # 70% width, 15% offset from left
                sample_w = int(w * 0.7)
                sample_x = x + int(w * 0.15)

                # Read cell using the multi-method detection with centered sample
                is_punched = self._read_cell(img, sample_x, sample_y, sample_w, sample_h, draw_debug=False)
                row.append(is_punched)

            grid.append(row)

        return grid, x_regions, y_regions

    def _decode_word_from_row_pair(self, img, word_idx, col_offset):
        """Decode one word from a pair of rows

        Args:
            word_idx: Word index (0-5)
            col_offset: Column offset (0 for left group, 8 for right group)

        Grid layout for one word (2 rows):
        - Col 0/8: Indexador (skip)
        - Col 1/9: Milhar - upper=1, lower=2
        - Col 2-3/10-11: Centenas - 8/2, 4/1
        - Col 4-5/12-13: Dezenas - 8/2, 4/1
        - Col 6-7/14-15: Unidades - 8/2, 4/1
        """
        row_upper = word_idx * 2
        row_lower = word_idx * 2 + 1

        if row_lower >= len(self.y_regions) - 1:
            return None

        y_upper = self.y_regions[row_upper]
        y_lower = self.y_regions[row_lower]
        row_h = self.y_regions[row_upper + 1] - y_upper

        # Sample positions - use 60% of cell height, centered vertically
        sample_h = int(row_h * 0.6)
        sample_y_upper = y_upper + int(row_h * 0.2)
        sample_y_lower = y_lower + int(row_h * 0.2)

        digits = []

        # Column 1/9: Milhar (skip col 0/8 indexador)
        col = col_offset + 1
        if col >= len(self.x_regions) - 1:
            return None

        x = self.x_regions[col]
        w = self.x_regions[col + 1] - x
        # Use 70% of cell width, centered horizontally
        sample_w = int(w * 0.7)
        sample_x = x + int(w * 0.15)

        upper = self._read_cell(img, sample_x, sample_y_upper, sample_w, sample_h, self.debug_mode)
        lower = self._read_cell(img, sample_x, sample_y_lower, sample_w, sample_h, self.debug_mode)

        milhar = 0
        if upper:
            milhar = 1
        elif lower:
            milhar = 2
        digits.append(milhar)

        # Columns 2-7 or 10-15: Three pairs of 1-2-4-8 encoding
        for pair_idx in range(3):
            col_left = col_offset + 2 + pair_idx * 2
            col_right = col_offset + 3 + pair_idx * 2

            if col_right >= len(self.x_regions) - 1:
                return None

            # Left column: 8 (upper), 2 (lower)
            x = self.x_regions[col_left]
            w = self.x_regions[col_left + 1] - x
            # Use 70% of cell width, centered horizontally
            sample_w_left = int(w * 0.7)
            sample_x_left = x + int(w * 0.15)

            val_8 = 8 if self._read_cell(img, sample_x_left, sample_y_upper, sample_w_left, sample_h, self.debug_mode) else 0
            val_2 = 2 if self._read_cell(img, sample_x_left, sample_y_lower, sample_w_left, sample_h, self.debug_mode) else 0

            # Right column: 4 (upper), 1 (lower)
            x = self.x_regions[col_right]
            w = self.x_regions[col_right + 1] - x
            # Use 70% of cell width, centered horizontally
            sample_w_right = int(w * 0.7)
            sample_x_right = x + int(w * 0.15)

            val_4 = 4 if self._read_cell(img, sample_x_right, sample_y_upper, sample_w_right, sample_h, self.debug_mode) else 0
            val_1 = 1 if self._read_cell(img, sample_x_right, sample_y_lower, sample_w_right, sample_h, self.debug_mode) else 0

            digit = val_8 + val_4 + val_2 + val_1
            digits.append(digit)

        if len(digits) == 4:
            number = digits[0] * 1000 + digits[1] * 100 + digits[2] * 10 + digits[3]
            return number
        return None

    def _decode_all_words(self, img):
        """Decode all 12 words from the grid"""
        words = []

        # Decode left group (words 1-6, columns 0-7)
        for word_idx in range(6):
            number = self._decode_word_from_row_pair(img, word_idx, 0)
            if number is not None and 1 <= number <= 2048:
                word = WORDLIST[number - 1]
                words.append(word)
            else:
                words.append("????")

        # Decode right group (words 7-12, columns 8-15)
        for word_idx in range(6):
            number = self._decode_word_from_row_pair(img, word_idx, 8)
            if number is not None and 1 <= number <= 2048:
                word = WORDLIST[number - 1]
                words.append(word)
            else:
                words.append("????")

        return words

    def _show_ascii_grid(self, grid):
        """Show ASCII representation of the 16×12 grid with detected points

        Compact format (1 space between groups):
        1.[x] [x][x] [x][x] [x][x]
          [ ] [ ][ ] [ ][x] [x][ ]

        Shows in two pages - left group (cols 0-7) and right group (cols 8-15)
        """
        # Page 1: Left group (columns 0-7, words 1-6)
        self.ctx.display.clear()

        y_pos = 5
        for word_idx in range(6):  # 6 words
            row_upper = word_idx * 2
            row_lower = word_idx * 2 + 1

            # Get cell values for columns 1-7 (skip col 0 indexer)
            cells_upper = []
            cells_lower = []
            for col in range(1, 8):  # Skip column 0 (indexer)
                if row_upper < len(grid) and col < len(grid[row_upper]):
                    cells_upper.append("x" if grid[row_upper][col] else " ")
                else:
                    cells_upper.append(" ")
                if row_lower < len(grid) and col < len(grid[row_lower]):
                    cells_lower.append("x" if grid[row_lower][col] else " ")
                else:
                    cells_lower.append(" ")

            # Compact format: 1.[m] [c][c] [d][d] [u][u]
            line_upper = "{}.[{}] [{}][{}] [{}][{}] [{}][{}]".format(
                word_idx + 1,
                cells_upper[0],
                cells_upper[1], cells_upper[2],
                cells_upper[3], cells_upper[4],
                cells_upper[5], cells_upper[6]
            )
            line_lower = "  [{}] [{}][{}] [{}][{}] [{}][{}]".format(
                cells_lower[0],
                cells_lower[1], cells_lower[2],
                cells_lower[3], cells_lower[4],
                cells_lower[5], cells_lower[6]
            )

            self.ctx.display.draw_string(5, y_pos, line_upper)
            y_pos += 16
            self.ctx.display.draw_string(5, y_pos, line_lower)
            y_pos += 20  # Extra space between words

        self.ctx.input.wait_for_button()

        # Page 2: Right group (columns 8-15, words 7-12)
        self.ctx.display.clear()

        y_pos = 5
        for word_idx in range(6):  # 6 words (7-12)
            row_upper = word_idx * 2
            row_lower = word_idx * 2 + 1

            # Get cell values for columns 9-15 (skip col 8 indexer)
            cells_upper = []
            cells_lower = []
            for col in range(9, 16):  # Skip column 8 (indexer)
                if row_upper < len(grid) and col < len(grid[row_upper]):
                    cells_upper.append("x" if grid[row_upper][col] else " ")
                else:
                    cells_upper.append(" ")
                if row_lower < len(grid) and col < len(grid[row_lower]):
                    cells_lower.append("x" if grid[row_lower][col] else " ")
                else:
                    cells_lower.append(" ")

            # Compact format with dot for all numbers
            word_num = word_idx + 7
            if word_num < 10:
                line_upper = "{}.[{}] [{}][{}] [{}][{}] [{}][{}]".format(
                    word_num,
                    cells_upper[0],
                    cells_upper[1], cells_upper[2],
                    cells_upper[3], cells_upper[4],
                    cells_upper[5], cells_upper[6]
                )
                line_lower = "  [{}] [{}][{}] [{}][{}] [{}][{}]".format(
                    cells_lower[0],
                    cells_lower[1], cells_lower[2],
                    cells_lower[3], cells_lower[4],
                    cells_lower[5], cells_lower[6]
                )
            else:
                # For 10, 11, 12 - include dot after number
                line_upper = "{}.[{}] [{}][{}] [{}][{}] [{}][{}]".format(
                    word_num,
                    cells_upper[0],
                    cells_upper[1], cells_upper[2],
                    cells_upper[3], cells_upper[4],
                    cells_upper[5], cells_upper[6]
                )
                line_lower = "   [{}] [{}][{}] [{}][{}] [{}][{}]".format(
                    cells_lower[0],
                    cells_lower[1], cells_lower[2],
                    cells_lower[3], cells_lower[4],
                    cells_lower[5], cells_lower[6]
                )

            self.ctx.display.draw_string(5, y_pos, line_upper)
            y_pos += 16
            self.ctx.display.draw_string(5, y_pos, line_lower)
            y_pos += 20  # Extra space between words

        self.ctx.input.wait_for_button()

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
            # Layout: upper=1,2 lower=4,8 for each pair
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
            # Layout: upper=1,2 lower=4,8 for each pair
            digits = [milhar]
            for pair_idx in range(3):
                col_left = 10 + pair_idx * 2
                col_right = 11 + pair_idx * 2

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

        return numbers

    def _show_stackbit_words(self, grid):
        """Show decoded words in Stackbit 1248 visual format

        Similar to backup mnemonic > other formats > stackbit 1248
        Shows 6 words per page with visual grid representation
        """
        # Decode all word numbers from the grid
        numbers = self._decode_numbers_from_grid(grid)

        # Setup display parameters
        x_offset = DEFAULT_PADDING if not kboard.is_m5stickv else MINIMAL_PADDING
        x_pad = 2 * FONT_WIDTH
        y_pad = FONT_HEIGHT

        def draw_word_row(word_idx, number, y_offset):
            """Draw one word row with Stackbit 1248 visual representation"""
            # Convert number to 4 digits
            digits = [
                (number // 1000) % 10,
                (number // 100) % 10,
                (number // 10) % 10,
                number % 10
            ]
            digits_str = "{:04d}".format(number)

            # Get BIP39 word
            if 1 <= number <= 2048:
                word = WORDLIST[number - 1]
            else:
                word = "????"

            # Draw word index background
            grid_x_offset = x_offset - FONT_WIDTH // 2
            index_x_offset = x_offset + x_pad // 2 - 1
            if len(str(word_idx)) > 1:
                index_x_offset -= FONT_WIDTH

            # Draw word_num background
            self.ctx.display.fill_rectangle(
                grid_x_offset,
                y_offset - 2,
                x_pad + FONT_WIDTH // 2,
                2 * y_pad + 2,
                theme.disabled_color,
            )

            # Draw word index number
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

            # Top line
            self.ctx.display.draw_line(
                grid_x_offset, y_offset - 2,
                grid_x_offset + width, y_offset - 2,
                theme.frame_color,
            )
            # Bottom line
            self.ctx.display.draw_line(
                grid_x_offset, y_offset - 2 + height,
                grid_x_offset + width, y_offset - 2 + height,
                theme.frame_color,
            )
            # Vertical lines
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

            # Draw punched marks (highlighted boxes)
            outline_width = x_pad - 6
            outline_height = y_pad - 4
            outline_x = x_offset + x_pad + 3

            # Milhar digit (0, 1, or 2)
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

            # Other 3 digits (1-2-4-8 encoding)
            outline_x += x_pad
            for d in range(3):
                digit = digits[d + 1]
                # 8 bit (upper right)
                if (digit >> 3) & 1:
                    self.ctx.display.outline(
                        outline_x + x_pad, y_offset + y_pad + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                # 4 bit (lower right)
                if (digit >> 2) & 1:
                    self.ctx.display.outline(
                        outline_x, y_offset + y_pad + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                # 2 bit (upper left)
                if (digit >> 1) & 1:
                    self.ctx.display.outline(
                        outline_x + x_pad, y_offset + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                # 1 bit (lower left)
                if digit & 1:
                    self.ctx.display.outline(
                        outline_x, y_offset + 1,
                        outline_width, outline_height,
                        theme.highlight_color,
                    )
                outline_x += 2 * x_pad

            # Draw number and word on the right
            if not kboard.is_m5stickv:
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

        # Row spacing (extra space between each word row)
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

    def _show_grid_visualization(self, grid, img):
        """Show visual representation of the grid with detected punches

        Displays the same grid overlay used during camera capture,
        but with red dots marking the detected punches.

        Args:
            grid: 2D list [row][col] where True = punched, False = not punched
            img: Camera image to use as base
        """
        # Count detected punches
        total_punches = sum(sum(1 for cell in row if cell) for row in grid)

        # Create a copy of the image to draw on
        display_img = img.copy()

        # Draw the grid lines (same as _draw_grid)
        # Get the rectangle bounds from x_regions and y_regions
        if len(self.x_regions) >= 2 and len(self.y_regions) >= 2:
            rect_x = self.x_regions[0]
            rect_y = self.y_regions[0]
            rect_w = self.x_regions[-1] - self.x_regions[0]
            rect_h = self.y_regions[-1] - self.y_regions[0]
            rect = (rect_x, rect_y, rect_w, rect_h)

            # Draw rectangle outline
            display_img.draw_rectangle(rect, lcd.WHITE, thickness=2)

            # Draw vertical lines (16 columns)
            for i, x in enumerate(self.x_regions):
                thickness = 2 if i in (0, 8) else 1
                display_img.draw_line(
                    x, rect[1],
                    x, rect[1] + rect[3],
                    lcd.WHITE, thickness=thickness
                )

            # Draw horizontal lines (12 rows)
            for y in self.y_regions:
                display_img.draw_line(
                    rect[0], y,
                    rect[0] + rect[2], y,
                    lcd.WHITE, thickness=1
                )

            # Draw red dots for detected punches (skip indexador columns 0 and 8)
            for row_idx in range(12):
                if row_idx >= len(grid):
                    break
                y = self.y_regions[row_idx]
                h = self.y_regions[row_idx + 1] - y if row_idx + 1 < len(self.y_regions) else 10

                for col_idx in range(16):
                    if col_idx >= len(grid[row_idx]):
                        break
                    # Skip indexador columns
                    if col_idx == 0 or col_idx == 8:
                        continue

                    if grid[row_idx][col_idx]:  # If punched
                        x = self.x_regions[col_idx]
                        w = self.x_regions[col_idx + 1] - x if col_idx + 1 < len(self.x_regions) else 10

                        # Draw red filled circle in center of cell
                        center_x = x + w // 2
                        center_y = y + h // 2
                        radius = min(w, h) // 3

                        # Draw filled red circle (approximated with rectangle)
                        display_img.draw_circle(center_x, center_y, radius, lcd.RED, thickness=-1)

        # Display the image
        if kboard.is_m5stickv:
            display_img.lens_corr(strength=1.0, zoom=0.56)
        if kboard.is_amigo:
            lcd.display(display_img, oft=(80, 40))
        else:
            lcd.display(display_img)

        # Show summary text overlay
        time.sleep(1)

        # Wait for user to press button
        self.ctx.input.wait_for_button()

    def _show_words_for_confirmation(self, words):
        """Show the 12 words to user for review and confirmation

        Returns the confirmed words list, or None if user cancels
        """
        self.ctx.display.clear()

        # Show all 12 words in a scrollable list
        lines_per_page = 6
        current_line = 0

        while True:
            self.ctx.display.clear()
            self.ctx.display.draw_hcentered_text(
                t("Review 12 words") + "\n"
            )

            # Show 6 words at a time
            y_offset = 40
            for i in range(lines_per_page):
                word_idx = current_line + i
                if word_idx < len(words):
                    line = str(word_idx + 1) + ". " + words[word_idx]
                    self.ctx.display.draw_string(
                        10, y_offset, line
                    )
                    y_offset += 20

            # Show navigation hint
            if len(words) > lines_per_page:
                nav_text = t("UP/DOWN scroll") + " | " + t("ENTER confirm")
            else:
                nav_text = t("ENTER to confirm") + " | " + t("PAGE to cancel")

            self.ctx.display.draw_hcentered_text(
                nav_text,
                info_box=True
            )

            btn = self.ctx.input.wait_for_button()

            if btn == self.ctx.input.BUTTON_ENTER or btn == self.ctx.input.BUTTON_TOUCH:
                # Confirm - return the words
                return words
            elif btn == self.ctx.input.BUTTON_PAGE or btn == self.ctx.input.BUTTON_PAGE_PREV:
                # Cancel
                return None
            elif btn == self.ctx.input.BUTTON_PAGE:
                # Scroll down
                if current_line + lines_per_page < len(words):
                    current_line += 1
            elif btn == self.ctx.input.BUTTON_PAGE_PREV:
                # Scroll up
                if current_line > 0:
                    current_line -= 1

    def _validate_and_get_words(self, grid):
        """Decode and validate words from grid

        Returns:
            List of 12 BIP39 words if all valid, None otherwise
        """
        numbers = self._decode_numbers_from_grid(grid)
        words = []

        for number in numbers:
            if 1 <= number <= 2048:
                words.append(WORDLIST[number - 1])
            else:
                return None  # Invalid number found

        return words

    def scanner(self, w24=False):
        """Scans the Stackbit 1248 plate with manual trigger

        Detects the plate, adjusts 16x12 grid, marks detected punches,
        and reads when user clicks on screen

        Args:
            w24: If True, scans for 24 words (front + back of plate)

        Returns:
            List of 12 or 24 BIP39 words if successfully read, None otherwise
        """
        page = 0  # 0 = first 12 words, 1 = second 12 words (for 24-word mode)
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

            # Detect plate
            rect = self._detect_plate(img)

            if rect:
                # Create grid over detected rectangle
                self._create_grid_over_rect(rect)

                # Draw grid
                self._draw_grid(img, rect)

                # Continuously mark detected punches with black squares
                # This will show user what's being detected in real-time
                for row_idx in range(12):
                    y = self.y_regions[row_idx]
                    h = self.y_regions[row_idx + 1] - y
                    sample_h = int(h * 0.6)
                    sample_y = y + int(h * 0.2)

                    for col_idx in range(16):
                        # Skip indexador columns (0 and 8)
                        if col_idx == 0 or col_idx == 8:
                            continue

                        x = self.x_regions[col_idx]
                        w = self.x_regions[col_idx + 1] - x
                        sample_w = int(w * 0.7)
                        sample_x = x + int(w * 0.15)

                        # Read and mark if punched
                        self._read_cell(img, sample_x, sample_y, sample_w, sample_h, True)

            if kboard.is_m5stickv:
                img.lens_corr(strength=1.0, zoom=0.56)
            if kboard.is_amigo:
                lcd.display(img, oft=(80, 40))
            else:
                lcd.display(img)

            # Check for click/touch to perform final reading
            if self.ctx.input.enter_event() or self.ctx.input.touch_event(validate_position=False):
                if rect:
                    # Stop camera and switch to portrait
                    sensor.run(0)
                    self.ctx.display.to_portrait()

                    # Read all grid cells with 16×12 grid
                    grid, x_regions_viz, y_regions_viz = self._read_all_grid_cells(img, rect)

                    # Show visual Stackbit 1248 representation with words
                    self._show_stackbit_words(grid)

                    # Validate and get words
                    words = self._validate_and_get_words(grid)

                    if words:
                        if w24:
                            # 24-word mode
                            if page == 0:
                                # First 12 words done - save and prompt to flip
                                all_words = words[:]
                                page = 1

                                # Prompt to flip plate
                                self.ctx.display.clear()
                                self.flash_text(
                                    t("Flip plate") + "\n" +
                                    t("Words 13-24") + "\n\n" +
                                    t("Click to read")
                                )

                                # Restart camera for second side
                                self.ctx.camera.initialize_run(mode=BINARY_GRID_MODE)
                                self.ctx.camera.zoom_mode()
                                self.ctx.display.to_landscape()
                                self.ctx.display.clear()
                                continue
                            else:
                                # Second 12 words done - combine and return
                                all_words.extend(words)
                                return all_words
                        else:
                            # 12-word mode - return directly
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
