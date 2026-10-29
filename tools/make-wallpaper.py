#!/usr/bin/env python3
"""Render the Blueprint wallpapers into backgrounds/.

  thinkpad    a technical drawing of a ThinkPad T14s Gen 6: the open machine
              in plan view, front and side elevations, dimensions, numbered
              callouts, a parts list and a title block
  grid        engineering paper: a fine blue grid inside a zoned border, a
              north arrow, a scale bar and a title block
  isometric   a little city of blocks on an isometric grid, faces in three
              blue tints, a glyph on each roof
  contours    contour lines of an imaginary terrain in blueprint blue, one
              traced in violet, a summit marker and a legend

Blue ink (#104bff) on paper (#fbfbfe), as on blueprint.page; the TrackPoint is
the one red. Each picture keeps its subject inside the middle 3456 px so a
16:10 crop keeps it.

Usage: tools/make-wallpaper.py [name ...|all] [--width 3840 --height 2160] [--seed N]
"""

import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

THEME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Bold.ttf"


def theme_colors():
    with open(os.path.join(THEME_DIR, "colors.toml")) as f:
        return {k: "#" + v for k, v in re.findall(r'^(\w+)\s*=\s*"#([0-9a-fA-F]{6})"', f.read(), re.M)}


C = theme_colors()
PAPER = "#fbfbfe"          # blueprint.page's lightest surface
INK = C["blue"]            # #104bff
VIOLET = C["magenta"]      # #6a4cf5
TRACKPOINT = "#e3241a"     # the one red


def rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def tint(color, alpha, base=PAPER):
    """color laid over the paper at alpha, as an opaque RGB triple."""
    c, b = rgb(color), rgb(base)
    return tuple(round(b[i] + (c[i] - b[i]) * alpha) for i in range(3))


class Sheet:
    """A drawing surface at `ss` times the output size, so lines and curves
    come out antialiased when it's scaled down. Coordinates are output pixels."""

    def __init__(self, w, h, ss=2, paper=PAPER):
        self.w, self.h, self.ss = w, h, ss
        self.img = Image.new("RGB", (w * ss, h * ss), paper)
        self.d = ImageDraw.Draw(self.img)
        self.fonts = {}

    def P(self, *xy):
        return [v * self.ss for v in xy]

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(FONT_BOLD if bold else FONT, round(size * self.ss))
        return self.fonts[key]

    def line(self, pts, color, width=1.0, dash=None):
        pts = [(x * self.ss, y * self.ss) for x, y in pts]
        wd = max(1, round(width * self.ss))
        if not dash:
            self.d.line(pts, fill=color, width=wd, joint="curve")
            return
        # Dashed: walk each segment laying dashes from the pattern.
        pattern = [p * self.ss for p in dash]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            if length == 0:
                continue
            ux, uy = (x1 - x0) / length, (y1 - y0) / length
            t, k = 0.0, 0
            while t < length:
                seg = pattern[k % len(pattern)]
                if k % 2 == 0:
                    e = min(length, t + seg)
                    self.d.line([(x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e)], fill=color, width=wd)
                t += seg
                k += 1

    def rect(self, x0, y0, x1, y1, color, width=1.0, radius=0, fill=None, dash=None):
        if dash:
            self.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], color, width, dash)
            return
        self.d.rounded_rectangle(self.P(x0, y0, x1, y1), radius=radius * self.ss, outline=color,
                                 width=max(1, round(width * self.ss)), fill=fill)

    def circle(self, cx, cy, r, color, width=1.0, fill=None):
        self.d.ellipse(self.P(cx - r, cy - r, cx + r, cy + r), outline=color, width=max(1, round(width * self.ss)),
                       fill=fill)

    def polygon(self, pts, fill=None, outline=None, width=1.0):
        self.d.polygon([(x * self.ss, y * self.ss) for x, y in pts], fill=fill)
        if outline:
            self.line(list(pts) + [pts[0]], outline, width)

    def text(self, x, y, s, size, color, anchor="la", bold=False):
        self.d.text((x * self.ss, y * self.ss), s, font=self.font(size, bold), fill=color, anchor=anchor)

    def arrow(self, x, y, angle, size, color):
        a = math.radians(angle)
        pts = [(x, y), (x - size * math.cos(a - 0.3), y - size * math.sin(a - 0.3)),
               (x - size * math.cos(a + 0.3), y - size * math.sin(a + 0.3))]
        self.polygon(pts, fill=color)

    def image(self):
        return self.img.resize((self.w, self.h), Image.LANCZOS)


# --- the drawing sheet: grid, zoned border, title block ----------------------

def frame_box(w, h):
    s = h / 2160
    return 268 * s, 104 * s, w - 268 * s, h - 104 * s


def draw_grid(sh, box, pitch, minor_alpha, major_alpha):
    x0, y0, x1, y1 = box
    minor, major = tint(INK, minor_alpha), tint(INK, major_alpha)
    i = 0
    x = x0
    while x <= x1 + 0.5:
        sh.line([(x, y0), (x, y1)], major if i % 5 == 0 else minor, 1.0)
        x += pitch
        i += 1
    i = 0
    y = y0
    while y <= y1 + 0.5:
        sh.line([(x0, y), (x1, y)], major if i % 5 == 0 else minor, 1.0)
        y += pitch
        i += 1


def draw_border(sh, w, h):
    """Outer and inner frame lines with drawing zones (1-8 across, A-D down)
    between them. Returns the inner box."""
    s = h / 2160
    ox0, oy0, ox1, oy1 = frame_box(w, h)
    gap = 34 * s
    ix0, iy0, ix1, iy1 = ox0 + gap, oy0 + gap, ox1 - gap, oy1 - gap
    sh.rect(ox0, oy0, ox1, oy1, INK, 1.4 * s)
    sh.rect(ix0, iy0, ix1, iy1, INK, 3.0 * s)
    cols, rows = 8, 4
    for i in range(cols):
        cx = ix0 + (i + 0.5) * (ix1 - ix0) / cols
        for y in ((oy0 + iy0) / 2, (oy1 + iy1) / 2):
            sh.text(cx, y, str(i + 1), 17 * s, INK, "mm")
        if i:
            x = ix0 + i * (ix1 - ix0) / cols
            sh.line([(x, oy0), (x, iy0)], INK, 1.2 * s)
            sh.line([(x, iy1), (x, oy1)], INK, 1.2 * s)
    for j in range(rows):
        cy = iy0 + (j + 0.5) * (iy1 - iy0) / rows
        for x in ((ox0 + ix0) / 2, (ox1 + ix1) / 2):
            sh.text(x, cy, "ABCD"[j], 17 * s, INK, "mm")
        if j:
            y = iy0 + j * (iy1 - iy0) / rows
            sh.line([(ox0, y), (ix0, y)], INK, 1.2 * s)
            sh.line([(ix1, y), (ox1, y)], INK, 1.2 * s)
    # Centring marks on each side, as on a printed sheet.
    for x, y, dx, dy in (((ox0 + ox1) / 2, oy0, 0, 1), ((ox0 + ox1) / 2, oy1, 0, -1),
                         (ox0, (oy0 + oy1) / 2, 1, 0), (ox1, (oy0 + oy1) / 2, -1, 0)):
        sh.line([(x, y), (x + dx * gap * 1.6, y + dy * gap * 1.6)], INK, 3.0 * s)
    return ix0, iy0, ix1, iy1


def draw_title_block(sh, inner, s, rows):
    """A title block in the inner frame's lower-right corner. rows: list of
    lists of (label, value, weight) cells; weights split the row width."""
    ix0, iy0, ix1, iy1 = inner
    bw, rh = 1060 * s, 76 * s
    x0, y1 = ix1 - bw, iy1
    y0 = y1 - rh * len(rows)
    sh.rect(x0, y0, ix1, iy1, INK, 2.4 * s, fill=PAPER)
    for r, cells in enumerate(rows):
        y = y0 + r * rh
        if r:
            sh.line([(x0, y), (ix1, y)], INK, 1.2 * s)
        total = sum(c[2] for c in cells)
        x = x0
        for k, (label, value, weight) in enumerate(cells):
            cw = bw * weight / total
            if k:
                sh.line([(x, y), (x, y + rh)], INK, 1.2 * s)
            sh.text(x + 12 * s, y + 8 * s, label, 13 * s, tint(INK, 0.7))
            sh.text(x + 12 * s, y + rh - 11 * s, value, (26 if r == 0 else 21) * s, INK, "ld", bold=(r == 0))
            x += cw
    return x0, y0


def dimension(sh, a, b, offset, text, s, horizontal=True):
    """A dimension line between points a and b, offset from them, with
    extension lines, arrowheads and the value written along it."""
    (ax, ay), (bx, by) = a, b
    ext = 8 * s
    if horizontal:
        y = ay + offset
        sign = 1 if offset > 0 else -1
        sh.line([(ax, ay + sign * ext), (ax, y + sign * ext)], INK, 1.0 * s)
        sh.line([(bx, by + sign * ext), (bx, y + sign * ext)], INK, 1.0 * s)
        sh.line([(ax, y), (bx, y)], INK, 1.2 * s)
        sh.arrow(ax, y, 180, 18 * s, INK)
        sh.arrow(bx, y, 0, 18 * s, INK)
        tw = len(text) * 13 * s
        mx = (ax + bx) / 2
        sh.rect(mx - tw / 2 - 8 * s, y - 16 * s, mx + tw / 2 + 8 * s, y + 16 * s, PAPER, 1, fill=PAPER)
        sh.text(mx, y, text, 22 * s, INK, "mm")
    else:
        x = ax + offset
        sign = 1 if offset > 0 else -1
        sh.line([(ax + sign * ext, ay), (x + sign * ext, ay)], INK, 1.0 * s)
        sh.line([(bx + sign * ext, by), (x + sign * ext, by)], INK, 1.0 * s)
        sh.line([(x, ay), (x, by)], INK, 1.2 * s)
        sh.arrow(x, ay, 270, 18 * s, INK)
        sh.arrow(x, by, 90, 18 * s, INK)
        my = (ay + by) / 2
        sh.rect(x - 16 * s, my - 52 * s, x + 16 * s, my + 52 * s, PAPER, 1, fill=PAPER)
        # Vertical text: draw on a small tile and rotate it in.
        tile = Image.new("RGBA", (round(130 * s * sh.ss), round(36 * s * sh.ss)), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((tile.width / 2, tile.height / 2), text, font=sh.font(22 * s), fill=INK, anchor="mm")
        tile = tile.rotate(90, expand=True)
        sh.img.paste(tile, (round(x * sh.ss - tile.width / 2), round(my * sh.ss - tile.height / 2)), tile)


def balloon(sh, n, x, y, tx, ty, s):
    """A numbered callout: a circle at (x, y) with a leader to (tx, ty)."""
    r = 22 * s
    a = math.atan2(ty - y, tx - x)
    sh.line([(x + r * math.cos(a), y + r * math.sin(a)), (tx, ty)], INK, 1.2 * s)
    sh.circle(tx, ty, 4 * s, INK, 1, fill=INK)
    sh.circle(x, y, r, INK, 2.0 * s, fill=PAPER)
    sh.text(x, y, str(n), 22 * s, INK, "mm", bold=True)


# --- thinkpad ----------------------------------------------------------------

# ThinkPad T14s Gen 6 (AMD), published footprint: 313.6 x 219.4 x 16.9 mm.
W_MM, D_MM, H_MM = 313.6, 219.4, 16.9


def keyboard_rows():
    """(label, width in key units) per row, top row first; each row is 15 units."""
    fn = [("Esc", 1)] + [(f"F{i}", 1) for i in range(1, 13)] + [("Home", 1), ("End", 1)]
    return [
        fn,
        [("`", 1)] + [(k, 1) for k in "1234567890-="] + [("⌫", 2)],
        [("Tab", 1.5)] + [(k, 1) for k in "QWERTYUIOP[]"] + [("\\", 1.5)],
        [("Caps", 1.75)] + [(k, 1) for k in "ASDFGHJKL;'"] + [("Enter", 2.25)],
        [("Shift", 2.25)] + [(k, 1) for k in "ZXCVBNM,./"] + [("Shift", 2.75)],
        [("Fn", 1), ("Ctrl", 1), ("⊞", 1), ("Alt", 1), ("", 5), ("Alt", 1), ("PrtSc", 1), ("Ctrl", 1),
         ("◀", 1), ("▲▼", 1), ("▶", 1)],
    ]


def render_thinkpad(w, h, seed):
    s = h / 2160
    sh = Sheet(w, h)
    inner = draw_border(sh, w, h)
    ix0, iy0, ix1, iy1 = inner
    draw_grid(sh, inner, 30 * s, 0.035, 0.07)
    mm = 3.55 * s                                   # drawing scale, pixels per mm
    X0 = ix0 + 170 * s                              # left edge of the machine
    HINGE = iy0 + 70 * s + D_MM * mm                # hinge line: lid above, deck below

    def P(x, y):
        return X0 + x * mm, HINGE + y * mm

    thick, thin, faint = 2.6 * s, 1.3 * s, tint(INK, 0.55)
    # Centre line (dash-dot) through the machine, and the hinge axis.
    cx = X0 + W_MM / 2 * mm
    sh.line([(cx, HINGE - D_MM * mm - 40 * s), (cx, HINGE + D_MM * mm + 40 * s)], faint, 1.0 * s, dash=(34 * s, 8 * s, 4 * s, 8 * s))
    sh.line([(X0 - 40 * s, HINGE), (X0 + W_MM * mm + 40 * s, HINGE)], faint, 1.0 * s, dash=(34 * s, 8 * s, 4 * s, 8 * s))

    # The lid, opened flat: shell, display, webcam.
    sh.rect(*P(0, -D_MM), *P(W_MM, 0), INK, thick, radius=7 * mm)
    dw, dh = 301.5, 188.5                           # 14.0" 16:10 panel
    dx0, dy0 = (W_MM - dw) / 2, -D_MM + 9.5
    sh.rect(*P(dx0, dy0), *P(dx0 + dw, dy0 + dh), INK, thin, radius=1.2 * mm)
    for i in range(1, 8):                           # a faint hatch across the glass
        t = i / 8
        sh.line([P(dx0 + dw * t, dy0 + dh), P(dx0 + dw * t + dh * 0.18, dy0 + dh * 0.82)], tint(INK, 0.18), 1.0 * s)
    wx, wy = P(W_MM / 2, -D_MM + 4.6)
    sh.circle(wx, wy, 1.6 * mm, INK, thin)

    # The deck: shell, keyboard, TrackPoint, buttons, touchpad, logo.
    sh.rect(*P(0, 0), *P(W_MM, D_MM), INK, thick, radius=7 * mm)
    rows = keyboard_rows()
    kx0, kx1, ky = 17.0, W_MM - 17.0, 12.0
    unit = (kx1 - kx0) / 15
    heights = [9.5] + [16.5] * 5
    keys, key_rects = {}, []
    for r, (row, kh) in enumerate(zip(rows, heights)):
        x = kx0
        for label, units in row:
            x_end = x + units * unit
            sh.rect(*P(x + 0.8, ky + 0.8), *P(x_end - 0.8, ky + kh - 0.8), INK, 1.2 * s, radius=1.4 * mm)
            if label:
                sh.text(*P((x + x_end) / 2, ky + kh / 2), label, (11 if r == 0 else 15) * s, INK, "mm")
            keys.setdefault(label, (x, ky, x_end, ky + kh))
            key_rects.append((label, x, ky, x_end, ky + kh, r))
            x = x_end
        ky += kh + 1.2
    gx = keys["G"][2]
    tp_x, tp_y = gx, (keys["G"][3] + keys["B"][1]) / 2
    tpx, tpy = P(tp_x, tp_y)
    sh.circle(tpx, tpy, 3.2 * mm, TRACKPOINT, 2.0 * s, fill=TRACKPOINT)
    by0, by1 = ky + 2.5, ky + 11.0
    bx0, bx1 = W_MM / 2 - 52, W_MM / 2 + 52
    third = (bx1 - bx0) / 3
    for i in range(3):
        sh.rect(*P(bx0 + i * third + 0.8, by0), *P(bx0 + (i + 1) * third - 0.8, by1), INK, thin, radius=1.6 * mm)
    for x in (bx0 + third + 3.5, bx0 + 2 * third - 3.5):
        sh.line([P(x, by0 + 1.5), P(x, by1 - 1.5)], TRACKPOINT, 2.2 * s)
    pad = (W_MM / 2 - 56, by1 + 3.0, W_MM / 2 + 56, D_MM - 14.0)
    sh.rect(*P(pad[0], pad[1]), *P(pad[2], pad[3]), INK, thin, radius=4 * mm)
    lx, ly = P(W_MM - 44, D_MM - 8.5)
    sh.text(lx, ly, "ThinkPad", 26 * s, INK, "lm", bold=True)
    ib = sh.font(26 * s, True).getbbox("Th")
    sh.circle(lx + (ib[2] - ib[0]) / sh.ss + 7.5 * s, ly - 13.5 * s, 3.2 * s, TRACKPOINT, 1, fill=TRACKPOINT)

    # Dimensions of the plan view.
    dimension(sh, P(0, D_MM), P(W_MM, D_MM), 64 * s, "313.6", s)
    dimension(sh, P(0, 0), P(0, D_MM), -70 * s, "219.4", s, horizontal=False)
    dimension(sh, P(0, -D_MM), P(0, 0), -70 * s, "219.4", s, horizontal=False)
    sh.text(*P(W_MM / 2, -D_MM / 2 + 14), '14.0"  16:10  1920×1200', 24 * s, tint(INK, 0.6), "mm")
    sh.text(X0, HINGE - D_MM * mm - 46 * s, "PLAN VIEW · OPEN 180°", 22 * s, INK, "ls", bold=True)

    # Elevations on the right, same scale.
    ex0 = X0 + W_MM * mm + 330 * s
    fy = iy0 + 150 * s
    sh.text(ex0, fy - 40 * s, "FRONT ELEVATION", 22 * s, INK, "ls", bold=True)
    sh.rect(ex0, fy, ex0 + W_MM * mm, fy + H_MM * mm, INK, thick, radius=4 * mm)
    sh.line([(ex0 + 10 * s, fy + 6.0 * mm), (ex0 + W_MM * mm - 10 * s, fy + 6.0 * mm)], INK, thin)
    sh.rect(ex0 + W_MM * mm / 2 - 14 * mm, fy - 1.0 * s, ex0 + W_MM * mm / 2 + 14 * mm, fy + 3.0 * mm, INK, thin, radius=1.5 * mm, dash=(10 * s, 6 * s))
    dimension(sh, (ex0 + W_MM * mm, fy), (ex0 + W_MM * mm, fy + H_MM * mm), 46 * s, "16.9", s, horizontal=False)

    sy = fy + 260 * s
    sh.text(ex0, sy - 40 * s, "LEFT ELEVATION", 22 * s, INK, "ls", bold=True)
    sw = D_MM * mm
    sh.rect(ex0, sy, ex0 + sw, sy + H_MM * mm, INK, thick, radius=4 * mm)
    sh.line([(ex0 + 10 * s, sy + 6.0 * mm), (ex0 + sw - 10 * s, sy + 6.0 * mm)], INK, thin)
    port_y = sy + 9.0 * mm
    x = ex0 + 22 * mm
    for kind in ("usbc", "usbc", "hdmi", "usba"):
        if kind == "usbc":
            sh.rect(x, port_y, x + 9 * mm, port_y + 3.2 * mm, INK, thin, radius=1.6 * mm)
            x += 15 * mm
        elif kind == "hdmi":
            sh.polygon([(x, port_y), (x + 15 * mm, port_y), (x + 13.5 * mm, port_y + 4.2 * mm), (x + 1.5 * mm, port_y + 4.2 * mm)], outline=INK, width=thin)
            x += 22 * mm
        else:
            sh.rect(x, port_y - 0.6 * mm, x + 12.5 * mm, port_y + 4.4 * mm, INK, thin, radius=0.6 * mm)
            x += 20 * mm
    dimension(sh, (ex0, sy + H_MM * mm), (ex0 + sw, sy + H_MM * mm), 56 * s, "219.4", s)

    # Parts list and callouts.
    parts = [("1", "TRACKPOINT, RED CAP"), ("2", 'DISPLAY 14.0" WUXGA'), ("3", "TOUCHPAD, GLASS"),
             ("4", "HINGE, 180°"), ("5", "CAMERA, SHUTTER"), ("6", "TRACKPOINT BUTTONS")]
    tx0, ty0 = ex0, sy + 300 * s
    rh = 46 * s
    sh.rect(tx0, ty0, tx0 + 900 * s, ty0 + rh * (len(parts) + 1), INK, 2.0 * s)
    sh.text(tx0 + 16 * s, ty0 + rh / 2, "ITEM", 16 * s, INK, "lm", bold=True)
    sh.text(tx0 + 110 * s, ty0 + rh / 2, "DESCRIPTION", 16 * s, INK, "lm", bold=True)
    sh.line([(tx0 + 90 * s, ty0), (tx0 + 90 * s, ty0 + rh * (len(parts) + 1))], INK, 1.2 * s)
    for i, (n, text) in enumerate(parts, 1):
        y = ty0 + i * rh
        sh.line([(tx0, y), (tx0 + 900 * s, y)], INK, 1.0 * s)
        sh.text(tx0 + 45 * s, y + rh / 2, n, 18 * s, INK, "mm")
        sh.text(tx0 + 110 * s, y + rh / 2, text, 18 * s, INK, "lm")
    edge = X0 + W_MM * mm
    balloon(sh, 1, edge + 120 * s, tpy - 40 * s, tpx + 14 * s, tpy, s)
    balloon(sh, 2, edge + 120 * s, HINGE - D_MM * mm * 0.62, *P(W_MM - 40, -D_MM * 0.55), s)
    balloon(sh, 3, edge + 120 * s, HINGE + D_MM * mm * 0.80, *P(pad[2] - 8, (pad[1] + pad[3]) / 2), s)
    balloon(sh, 4, edge + 120 * s, HINGE + 16 * s, *P(W_MM - 22, 0), s)
    balloon(sh, 5, edge + 120 * s, HINGE - D_MM * mm + 30 * s, wx + 8 * s, wy, s)
    balloon(sh, 6, edge + 120 * s, HINGE + D_MM * mm * 0.58, *P(bx1 - 6, (by0 + by1) / 2), s)

    # DETAIL A: the TrackPoint and the keys around it, 4:1.
    reach = 13.0                                    # mm around the TrackPoint shown
    sh.circle(tpx, tpy, reach * mm, INK, 1.4 * s)
    sh.text(tpx - reach * mm * 1.05, tpy + reach * mm * 1.05, "A", 24 * s, INK, "mm", bold=True)
    R = 250 * s
    dcx, dcy = tx0 + 900 * s - R, ty0 + rh * (len(parts) + 1) + 80 * s + R
    k4 = R / reach                                  # detail scale, pixels per mm
    ss = sh.ss
    layer = Image.new("RGBA", (round(2 * R * ss), round(2 * R * ss)), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    def L(x, y):
        return ((x - tp_x) * k4 + R) * ss, ((y - tp_y) * k4 + R) * ss

    for label, x0k, y0k, x1k, y1k, r in key_rects:
        if x1k < tp_x - reach - 20 or x0k > tp_x + reach + 20 or y1k < tp_y - reach - 20 or y0k > tp_y + reach + 20:
            continue
        ld.rounded_rectangle([*L(x0k + 0.8, y0k + 0.8), *L(x1k - 0.8, y1k - 0.8)], radius=1.4 * k4 * ss,
                             outline=INK, width=round(2.2 * s * ss), fill=PAPER)
        if label:
            ld.text(L((x0k + x1k) / 2, (y0k + y1k) / 2), label, font=sh.font(46 * s), fill=INK, anchor="mm")
    cxl, cyl = L(tp_x, tp_y)
    rr = 3.2 * k4 * ss
    ld.ellipse([cxl - rr, cyl - rr, cxl + rr, cyl + rr], fill=TRACKPOINT)
    for ring in (0.72, 0.45):                       # the cap's texture
        q = rr * ring
        ld.ellipse([cxl - q, cyl - q, cxl + q, cyl + q], outline=tint("#ffffff", 0.35, TRACKPOINT), width=round(2 * s * ss))
    mask = Image.new("L", layer.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, layer.width - 1, layer.height - 1], fill=255)
    layer.putalpha(Image.fromarray(np.minimum(np.asarray(layer.getchannel("A")), np.asarray(mask))))
    sh.circle(dcx, dcy, R, PAPER, 1, fill=PAPER)
    sh.img.paste(layer, (round((dcx - R) * ss), round((dcy - R) * ss)), layer)
    sh.circle(dcx, dcy, R, INK, 2.6 * s)
    sh.text(dcx - R, dcy - R - 18 * s, "DETAIL A · 4:1", 22 * s, INK, "ls", bold=True)

    draw_title_block(sh, inner, s, [
        [("TITLE", "THINKPAD T14s GEN 6 — GENERAL ARRANGEMENT", 1)],
        [("PROJECT", "OMARCHY · BLUEPRINT", 1.3), ("DRAWN", "ShadowOne", 1), ("DATE", "2026-10-29", 0.9)],
        [("SCALE", "1:2", 0.7), ("UNITS", "mm", 0.7), ("SHEET", "1 / 1", 0.7), ("REV", "A", 0.5)],
    ])
    return sh.image()


# --- grid --------------------------------------------------------------------

def north_arrow(sh, x, y, r, s):
    sh.circle(x, y, r, INK, 1.6 * s)
    sh.polygon([(x, y - r * 0.9), (x + r * 0.28, y), (x, y - r * 0.18)], fill=INK)
    sh.polygon([(x, y - r * 0.9), (x - r * 0.28, y), (x, y - r * 0.18)], outline=INK, width=1.4 * s)
    sh.text(x, y - r - 22 * s, "N", 24 * s, INK, "mm", bold=True)


def scale_bar(sh, x, y, unit_px, s, label="mm"):
    for i in range(5):
        sh.rect(x + i * unit_px, y, x + (i + 1) * unit_px, y + 14 * s, INK, 1.4 * s, fill=INK if i % 2 == 0 else PAPER)
        sh.text(x + i * unit_px, y + 34 * s, str(i * 10), 15 * s, INK, "mm")
    sh.text(x + 5 * unit_px, y + 34 * s, f"50 {label}", 15 * s, INK, "mm")


def render_grid(w, h, seed):
    s = h / 2160
    sh = Sheet(w, h)
    inner = draw_border(sh, w, h)
    draw_grid(sh, inner, 24 * s, 0.07, 0.15)
    ix0, iy0, ix1, iy1 = inner
    # A datum: a circle and cross where the sheet's centre lines meet.
    cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    sh.circle(cx, cy, 60 * s, INK, 2.0 * s)
    sh.line([(cx - 110 * s, cy), (cx + 110 * s, cy)], INK, 1.4 * s)
    sh.line([(cx, cy - 110 * s), (cx, cy + 110 * s)], INK, 1.4 * s)
    sh.text(cx + 76 * s, cy - 76 * s, "DATUM A", 16 * s, INK, "lm", bold=True)
    tx0, ty0 = draw_title_block(sh, inner, s, [
        [("TITLE", "BLUEPRINT", 1)],
        [("PROJECT", "OMARCHY", 1.3), ("DRAWN", "ShadowOne", 1), ("DATE", "2026-10-29", 0.9)],
        [("SCALE", "1:1", 0.7), ("UNITS", "mm", 0.7), ("SHEET", "1 / 1", 0.7), ("REV", "A", 0.5)],
    ])
    north_arrow(sh, tx0 - 120 * s, iy1 - 170 * s, 46 * s, s)
    scale_bar(sh, tx0 - 360 * s, iy1 - 60 * s, 48 * s, s)
    return sh.image()


# --- isometric ---------------------------------------------------------------

def render_isometric(w, h, seed):
    rng = np.random.default_rng(seed)
    s = h / 2160
    sh = Sheet(w, h)
    u = 78 * s                                   # one grid step along an iso axis
    c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    ox, oy = w / 2, h * 0.50 + 1.2 * u          # the cluster's middle lands mid-screen

    def iso(i, j, k=0.0):
        return ox + (i - j) * c30 * u, oy + (i + j) * s30 * u - k * u

    # The iso grid itself.
    grid = tint(INK, 0.08)
    n = 60
    for t in range(-n, n + 1):
        sh.line([iso(t, -n), iso(t, n)], grid, 1.0)
        sh.line([iso(-n, t), iso(n, t)], grid, 1.0)
    for t in range(-n * 2, n * 2 + 1):
        x = ox + t * c30 * u
        sh.line([(x, 0), (x, h)], tint(INK, 0.04), 1.0)

    # A little city: blocks on the grid, tall in the middle, drawn back to front.
    blocks = []
    for i in range(-5, 6):
        for j in range(-5, 6):
            if rng.random() < 0.42:
                continue
            d = math.hypot(i, j)
            height = max(0.4, (6.5 - d) * rng.uniform(0.35, 1.0))
            blocks.append((i, j, height))
    top_c, left_c, right_c = tint(INK, 0.06, "#ffffff"), tint(INK, 0.16, "#ffffff"), tint(INK, 0.30, "#ffffff")
    glyphs = ["{}", "fn", "</>", "=>", "[]", "λ", "#", "&&", "::", "0x"]
    for i, j, k in sorted(blocks, key=lambda b: (b[0] + b[1], b[0])):
        a, b = 0.86, 0.86                         # footprint, leaving a street between blocks
        x0, y0 = i + (1 - a) / 2, j + (1 - b) / 2
        # Soft shadow to the lower right.
        shadow = [iso(x0 + a, y0), iso(x0 + a + k * 0.55, y0 + k * 0.10), iso(x0 + a + k * 0.55, y0 + b + k * 0.10), iso(x0 + a, y0 + b)]
        sh.polygon(shadow, fill=tint(INK, 0.06, PAPER))
        top = [iso(x0, y0, k), iso(x0 + a, y0, k), iso(x0 + a, y0 + b, k), iso(x0, y0 + b, k)]
        left = [iso(x0, y0 + b, 0), iso(x0 + a, y0 + b, 0), iso(x0 + a, y0 + b, k), iso(x0, y0 + b, k)]
        right = [iso(x0 + a, y0, 0), iso(x0 + a, y0 + b, 0), iso(x0 + a, y0 + b, k), iso(x0 + a, y0, k)]
        for face, color in ((left, left_c), (right, right_c), (top, top_c)):
            sh.polygon(face, fill=color, outline=INK, width=1.8 * s)
        if k > 2.2:
            cxp, cyp = iso(x0 + a / 2, y0 + b / 2, k)
            sh.text(cxp, cyp, glyphs[(i * 7 + j * 3) % len(glyphs)], 30 * s, INK, "mm", bold=True)
        if k > 3.0:
            # Windows: a column of ticks on the right face.
            for f in np.arange(0.6, k - 0.3, 0.55):
                p0, p1 = iso(x0 + a, y0 + 0.25, f), iso(x0 + a, y0 + b - 0.25, f)
                sh.line([p0, p1], tint(INK, 0.55, "#ffffff"), 1.4 * s)
    sh.text(w / 2, h - 150 * s, "isometric · 30°", 20 * s, tint(INK, 0.55), "mm")
    return sh.image()


# --- contours ----------------------------------------------------------------

def noise(w, h, rng, cell, octaves=5, persistence=0.5):
    """Smooth value noise in 0..1: random grids, bicubic-upscaled, summed."""
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        size = max(2.0, cell / 2 ** o)
        grid = rng.random((max(2, int(h / size) + 2), max(2, int(w / size) + 2))).astype(np.float32)
        out += np.asarray(Image.fromarray(grid, "F").resize((w, h), Image.BICUBIC), np.float32) * amp
        total += amp
        amp *= persistence
    out /= total
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


def render_contours(w, h, seed):
    rng = np.random.default_rng(seed)
    s = h / 2160
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    height = noise(w, h, rng, 0.55 * h, 5, 0.48)
    for cx, cy, sg, amp in ((0.58, 0.42, 0.15, 0.50), (0.33, 0.62, 0.11, 0.28)):
        height += amp * np.exp(-(((xx / w - cx) * w / h) ** 2 + (yy / h - cy) ** 2) / (2 * sg * sg))
    height = (height - height.min()) / (height.max() - height.min())
    gy, gx = np.gradient(height)
    levels = 36
    v = height * levels
    level = np.round(v)
    dist = np.abs(v - level) / (np.hypot(gx, gy) * levels + 1e-6)
    index = level % 5 == 0
    width = np.where(index, 1.6, 1.0) * s
    line = np.clip(width + 0.5 - dist, 0, 1)
    special = level == int(levels * 0.6)
    alpha = np.where(special, 0.95, np.where(index, 0.55, 0.26)) * line
    paper = np.array(rgb(PAPER), np.float32)
    ink = np.where(special[..., None], np.array(rgb(VIOLET), np.float32), np.array(rgb(INK), np.float32))
    arr = paper + (ink - paper) * alpha[..., None]
    img = Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8))

    sh = Sheet(w, h, ss=1)
    sh.img = img
    sh.d = ImageDraw.Draw(img)
    sy, sx = np.unravel_index(np.argmax(height), height.shape)
    r = 9 * s
    sh.polygon([(sx, sy - r), (sx - r, sy + r * 0.8), (sx + r, sy + r * 0.8)], fill=INK)
    sh.text(sx + 18 * s, sy, "1 842", 22 * s, INK, "lm", bold=True)
    # Graticule ticks along the edges, inside the 16:10-safe area.
    x0, x1, y0, y1 = 300 * s, w - 300 * s, 90 * s, h - 90 * s
    for t in range(0, 11):
        x = x0 + (x1 - x0) * t / 10
        for y, d in ((y0, 1), (y1, -1)):
            sh.line([(x, y), (x, y + d * 18 * s)], INK, 1.6 * s)
        sh.text(x, y0 + 36 * s, f"{t:02d}", 15 * s, tint(INK, 0.7), "mm")
    for t in range(0, 7):
        y = y0 + (y1 - y0) * t / 6
        for x, d in ((x0, 1), (x1, -1)):
            sh.line([(x, y), (x + d * 18 * s, y)], INK, 1.6 * s)
    # Legend.
    lx, ly = x0 + 30 * s, y1 - 190 * s
    sh.rect(lx, ly, lx + 560 * s, ly + 150 * s, INK, 1.6 * s, fill=PAPER)
    sh.text(lx + 22 * s, ly + 34 * s, "BLUEPRINT", 22 * s, INK, "lm", bold=True)
    sh.text(lx + 22 * s, ly + 72 * s, "CONTOUR INTERVAL 20 m", 16 * s, INK, "lm")
    sh.line([(lx + 22 * s, ly + 110 * s), (lx + 92 * s, ly + 110 * s)], VIOLET, 3 * s)
    sh.text(lx + 108 * s, ly + 110 * s, "1 200 m", 16 * s, INK, "lm")
    scale_bar(sh, lx + 300 * s, ly + 96 * s, 42 * s, s, label="km")
    return img


# --- main --------------------------------------------------------------------

RENDERERS = {
    "thinkpad": ("1-thinkpad-drawing.png", render_thinkpad),
    "grid": ("2-grid.png", render_grid),
    "isometric": ("3-isometric.png", render_isometric),
    "contours": ("4-contours.png", render_contours),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", default=["all"], help="which to render: " + ", ".join(RENDERERS) + ", or all")
    ap.add_argument("--width", type=int, default=3840)
    ap.add_argument("--height", type=int, default=2160)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(THEME_DIR, "backgrounds"))
    args = ap.parse_args()

    names = list(RENDERERS) if "all" in args.names else args.names
    os.makedirs(args.out, exist_ok=True)
    for name in names:
        filename, render = RENDERERS[name]
        img = render(args.width, args.height, args.seed)
        path = os.path.join(args.out, filename)
        img.save(path, optimize=True)
        print(f"Wrote {path} ({args.width}x{args.height}, {os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
