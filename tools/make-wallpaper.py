#!/usr/bin/env python3
"""Render the Blueprint wallpapers into backgrounds/.

One drawing set of nine sheets, each the technical drawing of something
invented:

  gears      a train of three spur gears with true involute teeth, and a
             section through the big one
  hull       the lines plan of a boat: profile, half-breadth and body plan
  bridge     a suspension bridge in elevation, and a section of its deck
  linkage    a four-bar linkage and the curve its coupler point traces
  plan       the ground floor plan of a small pavilion
  wing       a tapered wing in plan, and its NACA 2412 ribs lofted
  lettering  the construction of a geometric capital B
  rocket     a two-stage launch vehicle, and two sections through it
  orbits     a transfer orbit between two circular orbits

Blue ink (#104bff) on paper (#fbfbfe), as on blueprint.page, and no other
color: each sheet picks out one feature with a heavier line and a pale wash
of the same ink. Every sheet has the same frame and title block (SHEET n / 9)
and keeps its drawing inside the middle 3456 px, so a 16:10 crop keeps it.

Usage: tools/make-wallpaper.py [name ...|all] [--width 3840 --height 2160] [--out DIR]
"""

import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

THEME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Bold.ttf"


def theme_colors():
    with open(os.path.join(THEME_DIR, "colors.toml")) as f:
        return {k: "#" + v for k, v in re.findall(r'^(\w+)\s*=\s*"#([0-9a-fA-F]{6})"', f.read(), re.M)}


C = theme_colors()
PAPER = "#fbfbfe"          # blueprint.page's lightest surface
INK = C["blue"]            # #104bff
SHEETS = 9
DATE = "2026-10-31"


def rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def tint(color, alpha, base=PAPER):
    """color laid over the paper at alpha, as an opaque RGB triple."""
    c, b = rgb(color), rgb(base)
    return tuple(round(b[i] + (c[i] - b[i]) * alpha) for i in range(3))


WASH = tint(INK, 0.08)         # the one picked-out feature
FAINT = tint(INK, 0.30)        # ghosted positions
CONSTRUCT = tint(INK, 0.55)    # construction lines

# Line weights in design pixels, after ISO 128: thin for dimensions and
# hatching, thick for visible outlines, heavy for the one picked-out feature.
THIN, MID, THICK, HEAVY = 1.0, 1.6, 2.4, 3.6
DASHDOT = (34, 8, 4, 8)        # centre lines
HIDDEN = (12, 7)               # hidden edges


def polar(cx, cy, r, a):
    """The point at radius r and angle a (radians, screen: y points down)."""
    return cx + r * math.cos(a), cy + r * math.sin(a)


def arc_points(cx, cy, r, a0, a1, step=4.0):
    """Points along an arc from a0 to a1 (degrees, screen)."""
    n = max(8, int(abs(math.radians(a1 - a0)) * r / step))
    return [polar(cx, cy, r, math.radians(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def hull(points):
    """Convex hull, counterclockwise on paper."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def rounded(points, r):
    """The outline of a convex plate around the points, corners of radius r."""
    return hull([polar(x, y, r, math.radians(a)) for x, y in points for a in range(0, 360, 5)])


def shape_box(shape):
    if isinstance(shape[0], str):
        if shape[0] == "circle":
            _, cx, cy, r = shape
            return cx - r, cy - r, cx + r, cy + r
        return shape[1:]
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    return min(xs), min(ys), max(xs), max(ys)


class Sheet:
    """A drawing surface. Coordinates, sizes and line widths are in design
    pixels on a 3840 x 2160 sheet; the surface is `scale` times that, and
    `ss` times more again so lines come out antialiased when it's scaled
    down."""

    W, H = 3840, 2160

    def __init__(self, scale=1.0, ss=2):
        self.scale, self.ss, self.k = scale, ss, scale * ss
        self.img = Image.new("RGB", (round(self.W * self.k), round(self.H * self.k)), PAPER)
        self.d = ImageDraw.Draw(self.img)
        self.fonts = {}

    def P(self, *xy):
        return [v * self.k for v in xy]

    def px(self, width):
        return max(1, round(width * self.k))

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(FONT_BOLD if bold else FONT, max(1, round(size * self.k)))
        return self.fonts[key]

    def line(self, pts, color=INK, width=1.0, dash=None):
        pts = [(x * self.k, y * self.k) for x, y in pts]
        wd = self.px(width)
        if not dash:
            self.d.line(pts, fill=color, width=wd, joint="curve")
            return
        # Lay the pattern along the whole polyline, so a curve made of many
        # short segments keeps its rhythm, and draw each dash in one stroke.
        pattern = [p * self.k for p in dash]
        k, left, run = 0, pattern[0], [pts[0]]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            t = 0.0
            while length - t > 1e-9:
                step = min(left, length - t)
                t += step
                left -= step
                p = (x0 + (x1 - x0) * t / length, y0 + (y1 - y0) * t / length)
                if k % 2 == 0:
                    run.append(p)
                if left <= 1e-9:
                    if k % 2 == 0 and len(run) > 1:
                        self.d.line(run, fill=color, width=wd, joint="curve")
                    k += 1
                    left = pattern[k % len(pattern)]
                    run = [p]
        if k % 2 == 0 and len(run) > 1:
            self.d.line(run, fill=color, width=wd, joint="curve")

    def rect(self, x0, y0, x1, y1, color=INK, width=1.0, radius=0, fill=None, dash=None):
        if dash:
            if fill:
                self.d.rectangle(self.P(x0, y0, x1, y1), fill=fill)
            self.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], color, width, dash)
            return
        self.d.rounded_rectangle(self.P(x0, y0, x1, y1), radius=radius * self.k, outline=color,
                                 width=self.px(width), fill=fill)

    def fill_rect(self, x0, y0, x1, y1, color):
        self.d.rectangle(self.P(x0, y0, x1, y1), fill=color)

    def circle(self, cx, cy, r, color=INK, width=1.0, fill=None, dash=None):
        if dash:
            if fill:
                self.d.ellipse(self.P(cx - r, cy - r, cx + r, cy + r), fill=fill)
            self.line(arc_points(cx, cy, r, 0, 360), color, width, dash)
            return
        self.d.ellipse(self.P(cx - r, cy - r, cx + r, cy + r), outline=color, width=self.px(width), fill=fill)

    def arc(self, cx, cy, r, a0, a1, color=INK, width=1.0, dash=None):
        self.line(arc_points(cx, cy, r, a0, a1), color, width, dash)

    def polygon(self, pts, fill=None, outline=None, width=1.0, dash=None):
        if fill:
            self.d.polygon([(x * self.k, y * self.k) for x, y in pts], fill=fill)
        if outline:
            self.line(list(pts) + [pts[0], pts[1]], outline, width, dash)

    def text(self, x, y, s, size, color=INK, anchor="la", bold=False):
        self.d.text((x * self.k, y * self.k), s, font=self.font(size, bold), fill=color, anchor=anchor)

    def label(self, x, y, s, size, anchor="mm", bold=False, color=INK):
        """Text on a patch of clean paper, for labels that sit over lines."""
        f = self.font(size, bold)
        b = self.d.textbbox((x * self.k, y * self.k), s, font=f, anchor=anchor)
        p = 0.3 * size * self.k
        self.d.rectangle([b[0] - p, b[1] - p, b[2] + p, b[3] + p], fill=PAPER)
        self.d.text((x * self.k, y * self.k), s, font=f, fill=color, anchor=anchor)

    def rtext(self, x, y, s, size, angle=0.0, color=INK, bold=False, halo=True):
        """Text centred on (x, y) running along `angle` (degrees, screen),
        kept upright, on a patch of clean paper."""
        while angle > 90.5:
            angle -= 180
        while angle <= -89.5:
            angle += 180
        f = self.font(size, bold)
        b = f.getbbox(s)
        pad = round(0.3 * size * self.k)
        tile = Image.new("RGBA", (b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        if halo:
            td.rectangle([0, 0, tile.width, tile.height], fill=rgb(PAPER) + (255,))
        td.text((tile.width / 2, tile.height / 2), s, font=f, fill=color, anchor="mm")
        if abs(angle) > 0.01:
            tile = tile.rotate(-angle, resample=Image.BILINEAR, expand=True)
        self.img.paste(tile, (round(x * self.k - tile.width / 2), round(y * self.k - tile.height / 2)), tile)

    def arrow(self, x, y, angle, size=16, color=INK):
        """A filled arrowhead with its tip at (x, y), pointing along angle (degrees)."""
        a = math.radians(angle)
        pts = [(x, y), (x - size * math.cos(a - 0.28), y - size * math.sin(a - 0.28)),
               (x - size * math.cos(a + 0.28), y - size * math.sin(a + 0.28))]
        self.d.polygon([(px * self.k, py * self.k) for px, py in pts], fill=color)

    def _mask(self, shapes, holes=()):
        """An L mask over the shapes' bounding box on the surface: shapes
        filled, holes cut out. A shape is a list of points, ("circle", cx, cy,
        r) or ("rect", x0, y0, x1, y1)."""
        boxes = [shape_box(s) for s in shapes]
        x0 = math.floor(min(b[0] for b in boxes) * self.k) - 2
        y0 = math.floor(min(b[1] for b in boxes) * self.k) - 2
        x1 = math.ceil(max(b[2] for b in boxes) * self.k) + 2
        y1 = math.ceil(max(b[3] for b in boxes) * self.k) + 2
        mask = Image.new("L", (x1 - x0, y1 - y0), 0)
        md = ImageDraw.Draw(mask)
        for shape, value in [(s, 255) for s in shapes] + [(s, 0) for s in holes]:
            if isinstance(shape[0], str):
                if shape[0] == "circle":
                    _, cx, cy, r = shape
                    md.ellipse([(cx - r) * self.k - x0, (cy - r) * self.k - y0,
                                (cx + r) * self.k - x0, (cy + r) * self.k - y0], fill=value)
                else:
                    _, a, b, c, d = shape
                    md.rectangle([a * self.k - x0, b * self.k - y0, c * self.k - x0, d * self.k - y0], fill=value)
            else:
                md.polygon([(px * self.k - x0, py * self.k - y0) for px, py in shape], fill=value)
        return mask, (x0, y0, x1, y1)

    def wash(self, shapes, holes=(), color=WASH):
        mask, box = self._mask(shapes, holes)
        self.img.paste(color, box, mask)

    def hatch(self, shapes, holes=(), spacing=12, angle=45, color=INK, width=THIN):
        """Section lining: parallel lines at `angle` clipped to the shapes.
        The lines are laid on the sheet, not the shape, so two touching
        hatched parts line up."""
        mask, box = self._mask(shapes, holes)
        lines = Image.new("L", mask.size, 0)
        ld = ImageDraw.Draw(lines)
        a = math.radians(angle)
        d, n = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
        w, h = mask.size
        reach = math.hypot(w, h)
        off = n[0] * box[0] + n[1] * box[1]
        proj = [cx * n[0] + cy * n[1] + off for cx, cy in ((0, 0), (w, 0), (0, h), (w, h))]
        step = spacing * self.k
        t = math.floor(min(proj) / step) * step
        while t <= max(proj):
            c = t - off
            bx, by = c * n[0], c * n[1]
            ld.line([(bx - reach * d[0], by - reach * d[1]), (bx + reach * d[0], by + reach * d[1])],
                    fill=255, width=self.px(width))
            t += step
        self.img.paste(color, box, ImageChops.multiply(mask, lines))

    def image(self):
        # A box filter averages the supersampled pixels without ringing, so
        # every pixel stays a mix of paper and ink.
        return self.img.resize((round(self.W * self.scale), round(self.H * self.scale)), Image.BOX)


# --- the drawing sheet: grid, zoned border, title block ----------------------

FRAME = (268, 104, 3840 - 268, 2160 - 104)


def draw_grid(sh, box, pitch, minor_alpha, major_alpha):
    x0, y0, x1, y1 = box
    minor, major = tint(INK, minor_alpha), tint(INK, major_alpha)
    i, x = 0, x0
    while x <= x1 + 0.5:
        sh.line([(x, y0), (x, y1)], major if i % 5 == 0 else minor, 1.0)
        x += pitch
        i += 1
    i, y = 0, y0
    while y <= y1 + 0.5:
        sh.line([(x0, y), (x1, y)], major if i % 5 == 0 else minor, 1.0)
        y += pitch
        i += 1


def draw_border(sh):
    """Outer and inner frame lines with drawing zones (1-8 across, A-D down)
    between them. Returns the inner box."""
    ox0, oy0, ox1, oy1 = FRAME
    gap = 34
    ix0, iy0, ix1, iy1 = ox0 + gap, oy0 + gap, ox1 - gap, oy1 - gap
    sh.rect(ox0, oy0, ox1, oy1, INK, 1.2)
    sh.rect(ix0, iy0, ix1, iy1, INK, 2.4)
    cols, rows = 8, 4
    for i in range(cols):
        cx = ix0 + (i + 0.5) * (ix1 - ix0) / cols
        for y in ((oy0 + iy0) / 2, (oy1 + iy1) / 2):
            sh.text(cx, y, str(i + 1), 17, INK, "mm")
        if i:
            x = ix0 + i * (ix1 - ix0) / cols
            sh.line([(x, oy0), (x, iy0)], INK, 1.2)
            sh.line([(x, iy1), (x, oy1)], INK, 1.2)
    for j in range(rows):
        cy = iy0 + (j + 0.5) * (iy1 - iy0) / rows
        for x in ((ox0 + ix0) / 2, (ox1 + ix1) / 2):
            sh.text(x, cy, "ABCD"[j], 17, INK, "mm")
        if j:
            y = iy0 + j * (iy1 - iy0) / rows
            sh.line([(ox0, y), (ix0, y)], INK, 1.2)
            sh.line([(ix1, y), (ox1, y)], INK, 1.2)
    # Centring marks on each side, as on a printed sheet.
    for x, y, dx, dy in (((ox0 + ox1) / 2, oy0, 0, 1), ((ox0 + ox1) / 2, oy1, 0, -1),
                         (ox0, (oy0 + oy1) / 2, 1, 0), (ox1, (oy0 + oy1) / 2, -1, 0)):
        sh.line([(x, y), (x + dx * gap * 1.6, y + dy * gap * 1.6)], INK, 2.4)
    return ix0, iy0, ix1, iy1


INNER = (FRAME[0] + 34, FRAME[1] + 34, FRAME[2] - 34, FRAME[3] - 34)


def draw_title_block(sh, rows):
    """A title block in the inner frame's lower-right corner. rows: lists of
    (label, value, weight) cells; the weights split the row's width."""
    ix0, iy0, ix1, iy1 = INNER
    bw, rh = 880, 62
    x0, y1 = ix1 - bw, iy1
    y0 = y1 - rh * len(rows)
    sh.rect(x0, y0, ix1, iy1, INK, 2.4, fill=PAPER)
    for r, cells in enumerate(rows):
        y = y0 + r * rh
        if r:
            sh.line([(x0, y), (ix1, y)], INK, 1.2)
        total = sum(c[2] for c in cells)
        x = x0
        for k, (label, value, weight) in enumerate(cells):
            if k:
                sh.line([(x, y), (x, y + rh)], INK, 1.2)
            sh.text(x + 11, y + 7, label, 12, tint(INK, 0.7))
            sh.text(x + 11, y + rh - 10, value, 22 if r == 0 else 18, INK, "ld", bold=(r == 0))
            x += bw * weight / total


def new_sheet(scale):
    sh = Sheet(scale)
    draw_border(sh)
    draw_grid(sh, INNER, 30, 0.03, 0.055)
    return sh


def finish(sh, n, title, scale="1:1", units="mm"):
    draw_title_block(sh, [
        [("TITLE", title, 1)],
        [("PROJECT", "BLUEPRINT", 1.2), ("DRAWN", "ShadowOne", 1), ("SHEET", f"{n} / {SHEETS}", 0.75)],
        [("SCALE", scale, 0.9), ("UNITS", units, 0.7), ("DATE", DATE, 1), ("REV", "A", 0.5)],
    ])
    return sh.image()


# --- drafting conventions ----------------------------------------------------

def dim_line(sh, a, b, text, size=19):
    sh.line([a, b], INK, THIN)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    sh.arrow(*a, ang + 180)
    sh.arrow(*b, ang)
    if text:
        sh.rtext((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, text, size, ang)


def hdim(sh, a, b, y, text, size=19, gap=8):
    """A horizontal dimension of a.x .. b.x with its line at height y and
    extension lines down or up from the points."""
    for px, py in (a, b):
        sgn = 1 if y > py else -1
        if abs(y - py) > gap:
            sh.line([(px, py + sgn * gap), (px, y + sgn * 10)], INK, THIN)
    dim_line(sh, (a[0], y), (b[0], y), text, size)


def vdim(sh, a, b, x, text, size=19, gap=8):
    """A vertical dimension of a.y .. b.y with its line at x."""
    for px, py in (a, b):
        sgn = 1 if x > px else -1
        if abs(x - px) > gap:
            sh.line([(px + sgn * gap, py), (x + sgn * 10, py)], INK, THIN)
    dim_line(sh, (x, a[1]), (x, b[1]), text, size)


def leader(sh, target, at, text, size=18, bold=False, head="arrow"):
    """A leader from the note at `at` to `target`, with a short shoulder."""
    (tx, ty), (x, y) = target, at
    right = x >= tx
    shoulder = 26 if right else -26
    sh.line([(tx, ty), (x, y), (x + shoulder, y)], INK, THIN)
    if head == "arrow":
        sh.arrow(tx, ty, math.degrees(math.atan2(ty - y, tx - x)), 15)
    else:
        sh.circle(tx, ty, 4, INK, 1, fill=INK)
    sh.text(x + shoulder + (8 if right else -8), y, text, size, INK, "lm" if right else "rm", bold)


def centre_lines(sh, x, y, r, ext=24):
    sh.line([(x - r - ext, y), (x + r + ext, y)], INK, THIN, dash=DASHDOT)
    sh.line([(x, y - r - ext), (x, y + r + ext)], INK, THIN, dash=DASHDOT)


def centre_cross(sh, x, y, size=12, color=INK):
    sh.line([(x - size, y), (x + size, y)], color, THIN)
    sh.line([(x, y - size), (x, y + size)], color, THIN)


def balloon(sh, n, x, y, tx, ty):
    """A numbered callout: a circle at (x, y) with a leader to (tx, ty)."""
    r = 22
    a = math.atan2(ty - y, tx - x)
    sh.line([(x + r * math.cos(a), y + r * math.sin(a)), (tx, ty)], INK, THIN)
    sh.circle(tx, ty, 4, INK, 1, fill=INK)
    sh.circle(x, y, r, INK, MID, fill=PAPER)
    sh.text(x, y, str(n), 21, INK, "mm", bold=True)


def view_title(sh, x, y, title, sub=None):
    """A view's name, underlined, with its scale or a note below."""
    sh.text(x, y, title, 22, INK, "ms", bold=True)
    w = sh.font(22, True).getlength(title) / sh.k
    sh.line([(x - w / 2, y + 9), (x + w / 2, y + 9)], INK, MID)
    if sub:
        sh.text(x, y + 36, sub, 15, INK, "ms")


def table(sh, x, y, rows, widths, rh=40, size=16):
    """A ruled table from its top-left corner; the first row is the header."""
    w, h = sum(widths), rh * len(rows)
    sh.rect(x, y, x + w, y + h, INK, MID, fill=PAPER)
    for i in range(1, len(rows)):
        sh.line([(x, y + i * rh), (x + w, y + i * rh)], INK, 1.3 if i == 1 else 0.9)
    cx = x
    for wd in widths[:-1]:
        cx += wd
        sh.line([(cx, y), (cx, y + h)], INK, 0.9)
    for i, row in enumerate(rows):
        cx = x
        for wd, cell in zip(widths, row):
            sh.text(cx + 13 * size / 16, y + i * rh + rh / 2, cell, size, INK, "lm", bold=(i == 0))
            cx += wd
    return y + h


def cutting_plane(sh, p, q, letter, view):
    """The ends of a cutting plane p..q: heavy strokes, arrows looking along
    `view` (a unit vector) and the section's letter."""
    (px, py), (qx, qy) = p, q
    length = math.hypot(qx - px, qy - py)
    ux, uy = (qx - px) / length, (qy - py) / length
    sh.line([p, (px + ux * 44, py + uy * 44)], INK, HEAVY)
    sh.line([q, (qx - ux * 44, qy - uy * 44)], INK, HEAVY)
    ang = math.degrees(math.atan2(view[1], view[0]))
    for ex, ey in (p, q):
        tx, ty = ex + view[0] * 54, ey + view[1] * 54
        sh.line([(ex, ey), (tx, ty)], INK, MID)
        sh.arrow(tx, ty, ang, 18)
        sh.text(tx + view[0] * 26, ty + view[1] * 26, letter, 26, INK, "mm", bold=True)


def level_mark(sh, x, y, text):
    """A level: a small triangle standing on the line at (x, y), the value beside it."""
    sh.polygon([(x - 10, y - 17), (x + 10, y - 17), (x, y)], fill=PAPER, outline=INK, width=THIN)
    sh.line([(x - 10, y - 17), (x + 120, y - 17)], INK, THIN)
    sh.text(x + 16, y - 24, text, 16, INK, "ls")


def ground_line(sh, x0, x1, y):
    sh.line([(x0, y), (x1, y)], INK, THICK)
    x = x0 + 8
    while x < x1:
        sh.line([(x, y), (x - 12, y + 12)], INK, THIN)
        x += 12


def pin(sh, x, y, r=11):
    sh.circle(x, y, r, INK, MID, fill=PAPER)
    sh.circle(x, y, 2.6, INK, 1, fill=INK)


def support(sh, x, y):
    """A fixed pivot: a pin on a triangle on hatched ground."""
    sh.polygon([(x, y), (x + 38, y + 58), (x - 38, y + 58)], fill=PAPER, outline=INK, width=THICK)
    ground_line(sh, x - 62, x + 62, y + 58)
    pin(sh, x, y)


def fmt(v, decimals=0):
    """A number with thin spaces between thousands, as on drawings."""
    return f"{v:,.{decimals}f}".replace(",", " ")


# --- 1 gears -----------------------------------------------------------------

def involute_gear(cx, cy, z, m, rot, alpha=20.0, backlash=0.05):
    """The outline of a spur gear with involute teeth, tooth 0 centred on the
    angle rot (radians)."""
    r = m * z / 2
    a = math.radians(alpha)
    rb, ra, rf = r * math.cos(a), r + m, r - 1.25 * m

    def inv(phi):
        return math.tan(phi) - phi

    beta = math.pi / (2 * z) * (1 - backlash)        # half a tooth at the pitch circle

    def half(rho):
        return beta + inv(a) - inv(math.acos(min(1.0, rb / max(rho, rb))))

    low = max(rf, rb)
    radii = np.linspace(low, ra, 16)
    pts = []
    for k in range(z):
        c = rot + 2 * math.pi * k / z
        if rf < rb:
            pts.append(polar(cx, cy, rf, c - half(rb)))
        pts += [polar(cx, cy, rho, c - half(rho)) for rho in radii]
        ht = half(ra)
        pts += [polar(cx, cy, ra, c + t) for t in np.linspace(-ht, ht, 7)[1:-1]]
        pts += [polar(cx, cy, rho, c + half(rho)) for rho in radii[::-1]]
        if rf < rb:
            pts.append(polar(cx, cy, rf, c + half(rb)))
        a0, a1 = c + half(low), c + 2 * math.pi / z - half(low)
        pts += [polar(cx, cy, rf, t) for t in np.linspace(a0, a1, 9)[1:-1]]
    return pts


def keyed_bore(cx, cy, r, kw, kd, rot=-90.0):
    """A shaft bore of radius r with a keyway kw wide and kd deep at angle rot."""
    half = math.degrees(math.asin(kw / 2 / r))
    a = math.radians(rot)
    u, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
    pts = arc_points(cx, cy, r, rot + half, rot + 360 - half)
    pts.append((cx + u[0] * (r + kd) - n[0] * kw / 2, cy + u[1] * (r + kd) - n[1] * kw / 2))
    pts.append((cx + u[0] * (r + kd) + n[0] * kw / 2, cy + u[1] * (r + kd) + n[1] * kw / 2))
    return pts


def render_gears(scale):
    sh = new_sheet(scale)
    m = 26.0                                        # module: 4 mm at 6.5 px/mm
    mm = m / 4
    z1, z2, z3 = 40, 24, 16
    r1, r2, r3 = m * z1 / 2, m * z2 / 2, m * z3 / 2
    c1 = (1250.0, 1060.0)
    t12, t23 = math.radians(-20), math.radians(35)
    c2 = polar(*c1, r1 + r2, t12)
    c3 = polar(*c2, r2 + r3, t23)
    # Mesh the teeth: a tooth of one gear meets a gap of the next on the line
    # of centres, offset by however far the driving tooth is from that line.
    rot1 = t12
    rot2 = t12 + math.pi + math.pi / z2
    p2 = 2 * math.pi / z2
    d2 = (t23 - rot2 + p2 / 2) % p2 - p2 / 2
    rot3 = t23 + math.pi + d2 * z2 / z3 + math.pi / z3

    # Centre lines, the line of centres and the pitch circles go underneath.
    for (cx, cy), r in ((c1, r1), (c2, r2), (c3, r3)):
        centre_lines(sh, cx, cy, r + m, 34)
        sh.circle(cx, cy, r, INK, THIN, dash=DASHDOT)
    sh.line([c1, c2, c3], INK, THIN, dash=DASHDOT)

    # Gear 1, picked out: wash, heavy outline, rim, hub, six lightening holes.
    out1 = involute_gear(*c1, z1, m, rot1)
    bore1 = keyed_bore(*c1, 65, 36, 22)
    holes1 = [polar(*c1, 272, math.radians(60 * i)) for i in range(6)]
    sh.wash([out1], [bore1] + [("circle", hx, hy, 70) for hx, hy in holes1])
    sh.polygon(out1, outline=INK, width=HEAVY)
    sh.circle(*c1, 400, INK, MID)
    sh.circle(*c1, 150, INK, MID)
    for hx, hy in holes1:
        sh.circle(hx, hy, 70, INK, THICK)
        centre_cross(sh, hx, hy, 16)
    sh.polygon(bore1, outline=INK, width=THICK)

    # Gears 2 and 3.
    out2 = involute_gear(*c2, z2, m, rot2)
    sh.polygon(out2, outline=INK, width=THICK)
    sh.circle(*c2, 105, INK, MID)
    for i in range(4):
        hx, hy = polar(*c2, 200, math.radians(45 + 90 * i))
        sh.circle(hx, hy, 40, INK, THICK)
        centre_cross(sh, hx, hy, 12)
    sh.polygon(keyed_bore(*c2, 44, 26, 16), outline=INK, width=THICK)
    out3 = involute_gear(*c3, z3, m, rot3)
    sh.polygon(out3, outline=INK, width=THICK)
    sh.circle(*c3, 85, INK, MID)
    sh.polygon(keyed_bore(*c3, 36, 22, 13), outline=INK, width=THICK)

    # Cutting plane A-A through gear 1, looking right.
    ra1 = r1 + m
    cutting_plane(sh, (c1[0], c1[1] - ra1 - 46), (c1[0], c1[1] + ra1 + 46), "A", (1, 0))

    # SECTION A-A at 1:2: rim, web and hub of gear 1 cut through its axis.
    # The teeth are left unhatched, as drawings show them.
    sx, sy, k = 3070.0, 1150.0, 0.5
    tip, root, rim, hub, bore, kd = ra1, r1 - 1.25 * m, 400.0, 150.0, 65.0, 22.0
    b, length, web = 32 * mm, 40 * mm, 10 * mm

    def S(x, y):
        return sx + x * k, sy - y * k

    def half_section(top, inner, sign):
        prof = [(-length / 2, inner), (-length / 2, hub), (-web / 2, hub), (-web / 2, rim), (-b / 2, rim),
                (-b / 2, top), (b / 2, top), (b / 2, rim), (web / 2, rim), (web / 2, hub), (length / 2, hub),
                (length / 2, inner)]
        return [S(x, sign * y) for x, y in prof]

    sh.line([S(-length / 2 - 70, 0), S(length / 2 + 70, 0)], INK, THIN, dash=DASHDOT)
    for sign, inner in ((1, bore + kd), (-1, bore)):
        sh.hatch([half_section(root, inner, sign)], spacing=11)
        sh.polygon(half_section(tip, inner, sign), outline=INK, width=THICK)
        sh.line([S(-b / 2, sign * root), S(b / 2, sign * root)], INK, MID)
        sh.line([S(-b / 2 - 16, sign * r1), S(b / 2 + 16, sign * r1)], INK, THIN, dash=DASHDOT)
    hdim(sh, S(-b / 2, tip), S(b / 2, tip), S(0, tip)[1] - 46, "32")
    vdim(sh, S(-b / 2, tip), S(-b / 2, -tip), S(-length / 2, 0)[0] - 60, "Ø168")
    leader(sh, S(length / 2 - 8, -bore), (S(0, 0)[0] + 150, S(0, -bore)[1] + 120), "Ø20 H7")
    view_title(sh, sx, S(0, -tip)[1] + 92, "SECTION A-A", "SCALE 1:2")

    # Gear data, callouts and pitch circle notes.
    y = table(sh, 2830, 290, [["GEAR", "z", "m", "Ø PCD"], ["1", "40", "4", "160"], ["2", "24", "4", "96"],
                               ["3", "16", "4", "64"]], [120, 90, 90, 150])
    sh.text(2843, y + 34, "α 20°  ·  INVOLUTE  ·  a₁₂ 128  ·  a₂₃ 80", 16, INK, "lm")
    balloon(sh, 1, 760, 560, *polar(*c1, 330, math.radians(210)))
    balloon(sh, 2, 1760, 330, *polar(*c2, 245, math.radians(-90)))
    balloon(sh, 3, 2560, 1500, *polar(*c3, 130, math.radians(60)))
    leader(sh, polar(*c1, r1, math.radians(130)), (640, 1640), "Ø160 PCD")
    leader(sh, polar(*c2, r2, math.radians(-25)), (2470, 480), "Ø96 PCD")
    leader(sh, polar(*c3, r3, math.radians(100)), (2200, 1540), "Ø64 PCD")
    return finish(sh, 1, "GEAR TRAIN", "1:1", "mm")


# --- 2 hull ------------------------------------------------------------------

def render_hull(scale):
    sh = new_sheet(scale)
    X0, X1 = 560.0, 2600.0          # transom and stem in profile and half-breadth
    BASE, D = 860.0, 340.0          # baseline and moulded depth
    CL, B2 = 1130.0, 300.0          # half-breadth centreline and half beam
    BX = 3080.0                     # body plan centreline
    MMPX = 6.0                      # millimetres per design pixel

    def sheer(x):                   # lowest just aft of amidships, springing up to the bow
        if x < 0.55:
            return D * (1.0 + 0.10 * ((0.55 - x) / 0.55) ** 2)
        return D * (1.0 + 0.24 * ((x - 0.55) / 0.45) ** 2)

    def keel(x):                    # a little rocker, rising into the stem and the transom
        rise = 0.05 * D * ((x - 0.45) / 0.55) ** 2
        if x > 0.8:
            rise += 0.9 * D * ((x - 0.8) / 0.2) ** 2.2
        if x < 0.18:
            rise += 0.28 * D * ((0.18 - x) / 0.18) ** 2
        return rise

    def plan(x):                    # waterplane fullness, stern to bow
        if x <= 0.42:
            return 1 - 0.22 * ((0.42 - x) / 0.42) ** 2
        return max(0.0, 1 - ((x - 0.42) / 0.58) ** 1.9) ** 1.05

    def q(x):                       # section shape: full amidships, a V forward
        if x <= 0.45:
            return 4.5 - 1.5 * ((0.45 - x) / 0.45) ** 2
        return 1.6 + 2.9 * math.exp(-((x - 0.45) / 0.38) ** 2)

    def half(x, z):
        k, top = keel(x), sheer(x)
        if z < k:
            return None
        zn = min(1.0, (z - k) / (top - k))
        return B2 * plan(x) * (1 - (1 - zn) ** q(x))

    def PX(x):
        return X0 + x * (X1 - X0)

    def PZ(z):
        return BASE - z

    xs = np.linspace(0, 1, 500)
    WLS = [0.14, 0.28, 0.42, 0.56, 0.70, 0.84]
    DWL = 0.56 * D
    BUTTOCKS = [0.25 * B2, 0.5 * B2, 0.75 * B2]
    names = ["WL1", "WL2", "WL3", "DWL", "WL5", "WL6"]

    # --- profile: stations, waterlines, buttocks, outline, underwater wash.
    keel_pts = [(PX(x), PZ(keel(x))) for x in xs]
    sheer_pts = [(PX(x), PZ(sheer(x))) for x in xs[::-1]]
    outline = keel_pts + [(PX(1), PZ(sheer(1)))] + sheer_pts + [(PX(0), PZ(keel(0)))]
    under = [(PX(x), PZ(min(DWL, keel(x)))) for x in xs if keel(x) <= DWL]
    sh.wash([under + [(under[-1][0], PZ(DWL)), (under[0][0], PZ(DWL))]])
    for i in range(11):
        x = PX(i / 10)
        sh.line([(x, BASE + 16), (x, PZ(1.3 * D))], INK, THIN)
    for f, name in zip(WLS, names):
        z = f * D
        sh.line([(X0 - 40, PZ(z)), (X1 + 40, PZ(z))], INK, HEAVY if name == "DWL" else THIN)
        sh.text(X0 - 50, PZ(z), name, 15, INK, "rm", bold=(name == "DWL"))
    sh.line([(X0 - 40, BASE), (X1 + 40, BASE)], INK, MID)
    sh.text(X0 - 50, BASE, "BL", 15, INK, "rm")
    for b in BUTTOCKS:
        pts = []
        for x in xs:
            u = b / max(1e-6, B2 * plan(x))
            if u < 1:
                zn = 1 - (1 - u) ** (1 / q(x))
                pts.append((PX(x), PZ(keel(x) + zn * (sheer(x) - keel(x)))))
            elif len(pts) > 1:
                break
        sh.line(pts, INK, THIN)
    sh.polygon(outline, outline=INK, width=THICK)
    view_title(sh, PX(0.5), BASE + 74, "PROFILE")

    # --- half-breadth plan: deck line, waterlines, buttocks, stations.
    sh.line([(X0 - 40, CL), (X1 + 40, CL)], INK, THIN, dash=DASHDOT)
    sh.text(X0 - 50, CL, "CL", 15, INK, "rm")
    for i in range(11):
        x = PX(i / 10)
        sh.line([(x, CL), (x, CL + B2 + 18)], INK, THIN)
        sh.text(x, CL + B2 + 44, str(i), 16, INK, "mm")
    for j, b in enumerate(BUTTOCKS, 1):
        sh.line([(X0 - 40, CL + b), (X1 + 40, CL + b)], INK, THIN)
        sh.text(X0 - 50, CL + b, f"B{j}", 15, INK, "rm")
    for f, name in zip(WLS, names):
        pts = [(PX(x), CL + half(x, f * D)) for x in xs if half(x, f * D) is not None]
        sh.line(pts, INK, HEAVY if name == "DWL" else MID)
    deck = [(PX(0), CL)] + [(PX(x), CL + B2 * plan(x)) for x in xs]
    sh.line(deck, INK, THICK)
    view_title(sh, PX(0.5), CL + B2 + 112, "HALF-BREADTH PLAN")
    hdim(sh, (PX(0), CL + B2 * plan(0)), (PX(1), CL), CL + B2 + 190, f"LOA {fmt((X1 - X0) * MMPX)}")

    # --- body plan: sections aft on the left, forward on the right.
    sh.line([(BX, BASE + 30), (BX, PZ(1.34 * D))], INK, THIN, dash=DASHDOT)
    sh.line([(BX - B2 - 40, BASE), (BX + B2 + 40, BASE)], INK, MID)
    for f, name in zip(WLS, names):
        z = PZ(f * D)
        sh.line([(BX - B2 - 40, z), (BX + B2 + 40, z)], INK, HEAVY if name == "DWL" else THIN)
        sh.text(BX + B2 + 52, z, name, 15, INK, "lm", bold=(name == "DWL"))
    for b in BUTTOCKS:
        for sgn in (-1, 1):
            sh.line([(BX + sgn * b, BASE), (BX + sgn * b, PZ(1.3 * D))], INK, THIN)
    for i in range(10):
        x = i / 10
        zs = np.linspace(keel(x), sheer(x), 60)
        for sgn in ([-1] if i < 5 else [1] if i > 5 else [-1, 1]):
            sh.line([(BX + sgn * half(x, z), PZ(z)) for z in zs], INK, MID)
    sh.text(BX - 160, BASE + 40, "AFT", 15, INK, "mm")
    sh.text(BX + 160, BASE + 40, "FWD", 15, INK, "mm")
    view_title(sh, BX, BASE + 112, "BODY PLAN")
    hdim(sh, (BX - B2, PZ(D)), (BX + B2, PZ(D)), PZ(1.42 * D), f"BOA {fmt(2 * B2 * MMPX)}")

    # Table of offsets: half-breadths at each station, as the builder reads them.
    rows = [["HALF-BR."] + [str(i) for i in range(11)]]
    for f, name in zip(WLS, names):
        cells = [half(i / 10, f * D) for i in range(11)]
        rows.append([name] + ["—" if v is None or v < 1 else fmt(v * MMPX) for v in cells])
    rows.append(["SHEER"] + [fmt(B2 * plan(i / 10) * MMPX) if i < 10 else "0" for i in range(11)])
    rows.append(["SHEER H"] + [fmt(sheer(i / 10) * MMPX) for i in range(11)])
    sh.text(2700, 1078, "TABLE OF OFFSETS", 18, INK, "ls", bold=True)
    sh.text(3500, 1078, "mm", 15, INK, "rs")
    table(sh, 2700, 1096, rows, [104] + [63.3] * 11, 34, 14)
    return finish(sh, 2, "LINES PLAN", "1:25", "mm")


# --- 3 bridge ----------------------------------------------------------------

def render_bridge(scale):
    sh = new_sheet(scale)
    MPX = 600 / 1480                 # metres per design pixel, horizontally
    VPX = MPX / 3                    # vertically: the elevation is exaggerated 3x
    XT1, XT2 = 1180.0, 2660.0        # towers
    XM = (XT1 + XT2) / 2
    TOP, SADDLE = 400.0, 388.0       # tower top, cable over the saddle
    SLAB, CHORD, BOT = 990.0, 1000.0, 1056.0
    LOW = 910.0                      # cable at midspan
    HWL = 1426.0
    BED0, BED1 = 960.0, 2880.0

    def bed(x):
        return HWL + 148 * math.sin(math.pi * (x - BED0) / (BED1 - BED0)) ** 0.5

    def cable_main(x):
        return LOW - (LOW - SADDLE) * ((x - XM) / (XM - XT1)) ** 2

    anchor_l = [(330, 980), (550, 980), (622, 1250), (330, 1250)]
    anchor_r = [(3840 - x, y) for x, y in anchor_l]
    entry_l = (550 + 72 * 70 / 270, 1050.0)
    entry_r = (3840 - entry_l[0], 1050.0)

    def cable_side(x, xt, entry):
        u = (x - xt) / (entry[0] - xt)
        return SADDLE + (entry[1] - SADDLE) * u + 160 * u * (1 - u)

    # Ground and river bed, with a band of earth hatching under the line.
    bank = [(302, 1092), (520, 1094), (700, 1110), (860, 1250), (930, 1380), (BED0, HWL)]
    ground = bank + [(x, bed(x)) for x in np.linspace(BED0, BED1, 120)[1:-1]] + \
        [(3840 - x, y) for x, y in reversed(bank)]
    sh.hatch([ground + [(x, y + 30) for x, y in reversed(ground)]], spacing=11, color=tint(INK, 0.6))
    sh.line(ground, INK, THICK)
    sh.line([(BED0, HWL), (BED1, HWL)], INK, MID)
    for x in range(1030, 2840, 150):
        if min(abs(x - XT1), abs(x - XT2)) > 130:
            sh.line([(x, HWL + 16), (x + 52, HWL + 16)], tint(INK, 0.6), THIN)
            sh.line([(x + 76, HWL + 31), (x + 108, HWL + 31)], tint(INK, 0.6), THIN)

    # Anchorages: concrete, cut where the ground cuts them.
    for poly in (anchor_l, anchor_r):
        sh.polygon(poly, fill=PAPER)
        sh.hatch([poly], spacing=14, color=tint(INK, 0.6))
        sh.polygon(poly, outline=INK, width=THICK)

    # The deck: slab over a Warren truss, end to end.
    x0, x1 = 550.0, 3290.0
    sh.fill_rect(x0, SLAB, x1, BOT, PAPER)
    n = 74
    xs = np.linspace(x0, x1, n + 1)
    sh.line([(x, CHORD if i % 2 == 0 else BOT) for i, x in enumerate(xs)], INK, THIN)
    sh.line([(x0, SLAB), (x1, SLAB)], INK, THICK)
    sh.line([(x0, CHORD), (x1, CHORD)], INK, MID)
    sh.line([(x0, BOT), (x1, BOT)], INK, MID)

    # Hangers every 37 px (15 m), then the towers in front of the deck.
    for k in range(1, 40):
        x = XT1 + 37 * k
        sh.line([(x, cable_main(x)), (x, SLAB)], INK, THIN)
    for xt, entry, sgn in ((XT1, entry_l, -1), (XT2, entry_r, 1)):
        x = xt + sgn * 37
        while cable_side(x, xt, entry) < SLAB - 30:
            sh.line([(x, cable_side(x, xt, entry)), (x, SLAB)], INK, THIN)
            x += sgn * 37
        b = bed(xt)
        foot = [(xt - 95, b - 6), (xt + 95, b - 6), (xt + 95, b + 34), (xt - 95, b + 34)]
        sh.polygon(foot, fill=PAPER)
        sh.hatch([foot], spacing=9)
        sh.polygon(foot, outline=INK, width=THICK)
        sh.polygon([(xt - 52, 1380), (xt + 52, 1380), (xt + 64, b - 6), (xt - 64, b - 6)],
                   fill=PAPER, outline=INK, width=THICK)
        sh.polygon([(xt - 28, TOP), (xt + 28, TOP), (xt + 40, 1380), (xt - 40, 1380)],
                   fill=PAPER, outline=INK, width=THICK)
        for yb in (560, 930):           # the portal beams, seen end on
            sh.line([(xt - 30, yb), (xt + 30, yb)], INK, THIN)
            sh.line([(xt - 31, yb + 34), (xt + 31, yb + 34)], INK, THIN)
        sh.rect(xt - 38, TOP - 24, xt + 38, TOP + 4, INK, THICK, fill=PAPER)

    # The main cable, picked out, over both saddles into the anchorages.
    left = [(x, cable_side(x, XT1, entry_l)) for x in np.linspace(entry_l[0], XT1, 90)]
    main = [(x, cable_main(x)) for x in np.linspace(XT1, XT2, 240)]
    right = [(x, cable_side(x, XT2, entry_r)) for x in np.linspace(XT2, entry_r[0], 90)]
    sh.line(left + main[1:] + right[1:], INK, HEAVY)
    sh.line([(XT1, SADDLE), (XT2, SADDLE)], INK, THIN, dash=DASHDOT)

    # Levels, sag and clearance.
    level_mark(sh, 1030, HWL, "HWL ±0.0")
    level_mark(sh, XT1 + 120, SLAB, f"+{(HWL - SLAB) * VPX:.1f}")
    level_mark(sh, XT2 + 70, TOP - 24, f"+{(HWL - TOP + 24) * VPX:.1f}")
    vdim(sh, (XM + 18, SADDLE), (XM + 18, LOW), XM + 18, f"f {(LOW - SADDLE) * VPX:.1f}")
    vdim(sh, (XM + 166, BOT), (XM + 166, HWL), XM + 166, f"{(HWL - BOT) * VPX:.1f}")

    # Spans.
    yd = 1690
    el, er = (entry_l[0], 1262), (entry_r[0], 1262)
    t1, t2 = (XT1, bed(XT1) + 40), (XT2, bed(XT2) + 40)
    hdim(sh, el, t1, yd, fmt((XT1 - entry_l[0]) * MPX, 1))
    hdim(sh, t1, t2, yd, fmt((XT2 - XT1) * MPX, 1))
    hdim(sh, t2, er, yd, fmt((entry_r[0] - XT2) * MPX, 1))
    hdim(sh, el, er, yd + 70, fmt((entry_r[0] - entry_l[0]) * MPX, 1))
    cutting_plane(sh, (1660, SLAB - 70), (1660, BOT + 70), "A", (-1, 0))
    view_title(sh, XM, 1880 - 40, "ELEVATION", "VERTICAL SCALE ×3")

    # SECTION A-A of the deck, up in the sky on the left.
    ox, oy = 660.0, 300.0
    slab = [(ox - 262, oy), (ox + 262, oy), (ox + 262, oy + 14), (ox - 262, oy + 14)]
    sh.hatch([slab], spacing=8)
    sh.polygon(slab, outline=INK, width=THICK)
    for sgn in (-1, 1):
        x = ox + sgn * 240
        chord = [(x - 9, oy + 14), (x + 9, oy + 14), (x + 9, oy + 112), (x - 9, oy + 112)]
        sh.wash([chord], color=tint(INK, 0.5))
        sh.polygon(chord, outline=INK, width=MID)
        hx = ox + sgn * 252
        sh.line([(hx, oy), (hx, oy - 118)], INK, MID)
        sh.circle(hx, oy - 130, 12, INK, THICK, fill=WASH)
        sh.line([(ox + sgn * 262, oy), (ox + sgn * 262, oy - 26)], INK, THIN)
    sh.line([(ox - 270, oy - 26), (ox - 236, oy - 26)], INK, THIN)
    sh.line([(ox + 236, oy - 26), (ox + 270, oy - 26)], INK, THIN)
    sh.line([(ox - 231, oy + 112), (ox + 231, oy + 112)], INK, THICK)
    sh.line([(ox - 231, oy + 14), (ox + 231, oy + 112)], INK, THIN)
    sh.line([(ox - 231, oy + 112), (ox + 231, oy + 14)], INK, THIN)
    sh.line([(ox, oy - 150), (ox, oy + 140)], INK, THIN, dash=DASHDOT)
    hdim(sh, (ox - 262, oy + 14), (ox + 262, oy + 14), oy + 170, "28.0")
    view_title(sh, ox, oy + 250, "SECTION A-A", "SCALE 1:400")

    table(sh, 2880, 240, [["SPAN", "m"], ["MAIN", fmt((XT2 - XT1) * MPX, 1)],
                          ["SIDE", fmt((XT1 - entry_l[0]) * MPX, 1)], ["SAG f", f"{(LOW - SADDLE) * VPX:.1f}"],
                          ["f / l", f"1 : {(XT2 - XT1) * MPX / ((LOW - SADDLE) * VPX):.1f}"],
                          ["HANGERS", "@ 15.0"]], [200, 180])
    return finish(sh, 3, "SUSPENSION BRIDGE — ELEVATION", "1:2500", "m")


# --- 4 linkage ---------------------------------------------------------------

def fourbar(theta, a, b, c, d):
    """Joints B and C of a crank-rocker with ground pivots A = (0, 0) and
    D = (d, 0), y up, at crank angle theta; C on the open branch."""
    B = (a * math.cos(theta), a * math.sin(theta))
    dx, dy = d - B[0], -B[1]
    L = math.hypot(dx, dy)
    x = (b * b - c * c + L * L) / (2 * L)
    h = math.sqrt(max(0.0, b * b - x * x))
    ux, uy = dx / L, dy / L
    return B, (B[0] + ux * x - uy * h, B[1] + uy * x + ux * h)


def render_linkage(scale):
    sh = new_sheet(scale)
    # Chebyshev's lambda: crank 1, coupler and rocker 2.5, ground 2, and the
    # coupler point twice as far out as C, so P runs nearly straight for
    # part of each turn.
    a, b, c, d = 0.5, 1.25, 1.25, 1.0
    e, f = 2.0, 0.0

    def pose(t):
        B, C = fourbar(t, a, b, c, d)
        ux, uy = (C[0] - B[0]) / b, (C[1] - B[1]) / b
        P = (B[0] + (e * ux - f * uy) * b, B[1] + (e * uy + f * ux) * b)
        return B, C, P

    ts = np.linspace(0, 2 * math.pi, 721)
    poses = [pose(t) for t in ts]
    pts = [p for B, C, P in poses for p in (B, C, P)] + [(0, 0), (d, 0), (0, -0.2), (d, -0.2)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    k = min(2000 / (max(xs) - min(xs)), 1320 / (max(ys) - min(ys)))
    ox = 1720 - k * (max(xs) + min(xs)) / 2
    oy = 1010 + k * (max(ys) + min(ys)) / 2

    def T(p):
        return ox + k * p[0], oy - k * p[1]

    A, Dp = T((0, 0)), T((d, 0))
    sh.circle(*A, a * k, INK, THIN, dash=HIDDEN)
    rock = [math.degrees(math.atan2(T(C)[1] - Dp[1], T(C)[0] - Dp[0])) for _, C, _ in poses]
    sh.arc(*Dp, c * k, min(rock), max(rock), INK, THIN, dash=HIDDEN)
    sh.line([A, Dp], INK, THIN, dash=DASHDOT)

    # Ghosts: the linkage at nine more crank angles.
    t0 = 1.0
    for i in range(1, 10):
        B, C, P = (T(p) for p in pose(t0 + 2 * math.pi * i / 10))
        sh.line([A, B, C, Dp], FAINT, THIN)
        sh.polygon([B, C, P], outline=FAINT, width=THIN)
        for p in (B, C, P):
            sh.circle(*p, 5, FAINT, THIN, fill=PAPER)

    # The coupler curve, picked out, with arrows showing which way it runs.
    curve = [T(P) for _, _, P in poses]
    sh.line(curve, INK, HEAVY)
    for i in (90, 330, 560):
        (x0, y0), (x1, y1) = curve[i], curve[i + 4]
        sh.arrow(x1, y1, math.degrees(math.atan2(y1 - y0, x1 - x0)), 24)

    # The linkage itself at t0: bars, the coupler plate, pins and supports.
    B, C, P = (T(p) for p in pose(t0))
    for p, q, wd in ((A, B, 17), (C, Dp, 17), (B, P, 20)):
        sh.polygon(rounded([p, q], wd), fill=PAPER, outline=INK, width=THICK)
    support(sh, *A)
    support(sh, *Dp)
    for p in (B, C):
        pin(sh, *p)
    sh.circle(*P, 13, INK, MID, fill=WASH)
    centre_cross(sh, *P, 20)

    # The stretch where P runs straight, measured.
    ymin = min(p[2][1] for p in poses)
    ys_span = max(p[2][1] for p in poses) - ymin
    flat = [p[2][0] for p in poses if p[2][1] - ymin < 0.004 * ys_span]
    f0, f1 = T((min(flat), ymin)), T((max(flat), ymin))
    sh.line([(f0[0] - 90, f0[1]), (f1[0] + 90, f1[1])], INK, THIN, dash=DASHDOT)
    hdim(sh, f0, f1, f0[1] + 74, fmt((max(flat) - min(flat)) * 200 / d))
    # Crank angle and its direction of turn.
    ang = math.degrees(math.atan2(B[1] - A[1], B[0] - A[0]))
    sh.arc(*A, 92, ang, 0, INK, THIN)
    sh.arrow(*polar(*A, 92, math.radians(ang)), ang - 90, 14)
    sh.text(*polar(*A, 122, math.radians(ang / 2)), "θ₂", 22, INK, "mm")
    sh.arc(*A, a * k + 42, ang - 70, ang - 25, INK, MID)
    sh.arrow(*polar(*A, a * k + 42, math.radians(ang - 70)), ang - 160, 16)
    sh.text(*polar(*A, a * k + 74, math.radians(ang - 48)), "ω₂", 22, INK, "mm")

    for p, name, (dx, dy) in ((A, "A", (-44, -10)), (B, "B", (-38, -30)), (C, "C", (56, 16)),
                              (Dp, "D", (44, -10)), (P, "P", (0, -50))):
        sh.label(p[0] + dx, p[1] + dy, name, 28, bold=True)

    mm = 200 / d                                     # ground link is 200 mm
    y = table(sh, 2840, 300, [["LINK", "", "mm"], ["AB", "CRANK", fmt(a * mm)], ["BC", "COUPLER", fmt(b * mm)],
                              ["CD", "ROCKER", fmt(c * mm)], ["DA", "GROUND", fmt(d * mm)],
                              ["BP", "", fmt(math.hypot(e, f) * b * mm)]], [100, 200, 110])
    sh.text(2853, y + 34, "CHEBYSHEV'S LAMBDA", 16, INK, "lm", bold=True)
    sh.text(2853, y + 64, "CRANK-ROCKER  ·  s + l < p + q", 16, INK, "lm")
    sh.text(2853, y + 94, "P: A NEAR-STRAIGHT RUN", 16, INK, "lm")
    return finish(sh, 4, "FOUR-BAR LINKAGE", "1:1", "mm")


# --- 5 floor plan ------------------------------------------------------------

def span_segments(lo, hi, gaps):
    segs, cur = [], lo
    for g0, g1 in sorted(gaps):
        if g0 > cur:
            segs.append((cur, g0))
        cur = max(cur, g1)
    if hi > cur:
        segs.append((cur, hi))
    return segs


def render_plan(scale):
    sh = new_sheet(scale)
    GX = [980.0 + 470 * i for i in range(5)]       # grid 1-5, 6 000 apart
    GY = [480.0 + 390 * j for j in range(4)]       # grid A-D, 5 000 apart
    TE, TI = 36.0, 20.0                            # exterior and interior walls
    walls, windows = [], []

    def wall_h(y, xa, xb, t, gaps=(), glass=()):
        for s0, s1 in span_segments(xa - t / 2, xb + t / 2, list(gaps) + list(glass)):
            walls.append(("rect", s0, y - t / 2, s1, y + t / 2))
        windows.extend(("h", y, g0, g1, t) for g0, g1 in glass)

    def wall_v(x, ya, yb, t, gaps=(), glass=()):
        for s0, s1 in span_segments(ya - t / 2, yb + t / 2, list(gaps) + list(glass)):
            walls.append(("rect", x - t / 2, s0, x + t / 2, s1))
        windows.extend(("v", x, g0, g1, t) for g0, g1 in glass)

    def mid(p, q, w):
        c = (p + q) / 2
        return c - w / 2, c + w / 2

    WC = GX[3] + 235
    wall_h(GY[0], GX[0], GX[4], TE, glass=[mid(GX[i], GX[i + 1], 220) for i in range(3)] + [mid(GX[3], GX[4], 180)])
    wall_h(GY[3], GX[0], GX[4], TE, gaps=[mid(GX[0], GX[1], 140)],
           glass=[mid(GX[1], GX[2], 160), mid(GX[2], GX[3], 220), mid(GX[3], GX[4], 220)])
    wall_v(GX[0], GY[0], GY[3], TE, glass=[mid(GY[0], GY[1], 200), mid(GY[1], GY[2], 200)])
    wall_v(GX[4], GY[0], GY[3], TE, glass=[mid(GY[0], GY[1], 180), mid(GY[2], GY[3], 180)])
    wall_h(GY[2], GX[0], GX[4], TI, gaps=[mid(GX[0], GX[1], 180), mid(GX[2], GX[3], 220), mid(WC, GX[4], 80)])
    wall_h(GY[1], GX[3], GX[4], TI)
    wall_v(GX[3], GY[0], GY[2], TI, gaps=[(GY[0] + 30, GY[0] + 110), mid(GY[1], GY[2], 80)])
    wall_v(WC, GY[1], GY[2], TI)
    wall_v(GX[1], GY[2], GY[3], TI, gaps=[mid(GY[2], GY[3], 140)])
    wall_v(GX[2], GY[2], GY[3], TI)

    # Grid lines and bubbles go under everything.
    for i, x in enumerate(GX):
        sh.line([(x, GY[0] - 272), (x, GY[3] + 70)], CONSTRUCT, THIN, dash=DASHDOT)
        sh.circle(x, GY[0] - 300, 28, INK, MID, fill=PAPER)
        sh.text(x, GY[0] - 300, str(i + 1), 22, INK, "mm", bold=True)
    for j, y in enumerate(GY):
        sh.line([(GX[0] - 272, y), (GX[4] + 70, y)], CONSTRUCT, THIN, dash=DASHDOT)
        sh.circle(GX[0] - 300, y, 28, INK, MID, fill=PAPER)
        sh.text(GX[0] - 300, y, "ABCD"[j], 22, INK, "mm", bold=True)

    # Cut walls, picked out: an ink edge, the wash and a fine hatch.
    lw = 2.6
    for _, x0, y0, x1, y1 in walls:
        sh.fill_rect(x0 - lw, y0 - lw, x1 + lw, y1 + lw, INK)
    for _, x0, y0, x1, y1 in walls:
        sh.fill_rect(x0, y0, x1, y1, tint(INK, 0.10))
    sh.hatch(walls, spacing=9, color=tint(INK, 0.45), width=0.8)
    for kind, at, g0, g1, t in windows:
        for o in (-t / 2, -3, 3, t / 2):
            if kind == "h":
                sh.line([(g0, at + o), (g1, at + o)], INK, THIN)
            else:
                sh.line([(at + o, g0), (at + o, g1)], INK, THIN)

    # Doors: leaves and their swings.
    def door(hx, hy, r, leaf, a0, a1):
        sh.line([(hx, hy), polar(hx, hy, r, math.radians(leaf))], INK, MID)
        sh.arc(hx, hy, r, a0, a1, INK, THIN)

    ce = (GX[0] + GX[1]) / 2
    yi = GY[3] - TE / 2
    door(ce - 70, yi, 70, -90, -90, 0)
    door(ce + 70, yi, 70, -90, 180, 270)
    door(GX[3] + TI / 2, GY[0] + 30, 80, 0, 0, 90)
    door(GX[3] + TI / 2, (GY[1] + GY[2]) / 2 - 40, 80, 0, 0, 90)
    door((WC + GX[4]) / 2 - 40, GY[2] - TI / 2, 80, -90, -90, 0)

    # Free-standing columns in the studio.
    for x in (GX[1], GX[2]):
        sh.fill_rect(x - 14, GY[1] - 14, x + 14, GY[1] + 14, INK)

    # Stair: ten treads, the walking line and a break line.
    sx0, sx1, sy0, sy1 = GX[1] + 50, GX[2] - 50, GY[2] + 42, GY[2] + 192
    sh.rect(sx0, sy0, sx1, sy1, INK, MID)
    for i in range(1, 10):
        x = sx0 + (sx1 - sx0) * i / 10
        sh.line([(x, sy0), (x, sy1)], INK, THIN, dash=HIDDEN if i > 6 else None)
    bx = sx0 + (sx1 - sx0) * 0.64
    sh.line([(bx - 26, sy1), (bx - 4, (sy0 + sy1) / 2 + 12), (bx + 6, (sy0 + sy1) / 2 - 12), (bx + 26, sy0)], INK, MID)
    my = (sy0 + sy1) / 2
    sh.line([(sx0 + 18, my), (sx1 - 20, my)], INK, THIN)
    sh.circle(sx0 + 18, my, 5, INK, THIN, fill=PAPER)
    sh.arrow(sx1 - 20, my, 0, 16)
    sh.label(sx0 + 90, my, "UP", 16, bold=True)

    # Fittings, in thin line.
    k0, k1 = GY[3] - TE / 2, GX[4] - TE / 2
    sh.polygon([(GX[2] + TI / 2, k0), (GX[2] + TI / 2, k0 - 62), (k1 - 62, k0 - 62), (k1 - 62, GY[2] + TI / 2 + 30),
                (k1, GY[2] + TI / 2 + 30), (k1, k0)], outline=INK, width=THIN)
    sh.rect(GX[2] + 160, k0 - 54, GX[2] + 250, k0 - 8, INK, THIN, radius=8)
    sh.circle(GX[2] + 205, k0 - 31, 6, INK, THIN)
    for dx, dy in ((0, 0), (40, 0), (0, 32), (40, 32)):
        sh.circle(GX[3] + 70 + dx, k0 - 46 + dy, 12, INK, THIN)
    sh.rect(GX[4] - 170, GY[0] + 60, GX[4] - 40, GY[0] + 150, INK, THIN)
    sh.circle(GX[4] - 105, GY[0] + 180, 22, INK, THIN)
    tx0, ty0, tx1, ty1 = GX[0] + 200, GY[1] + 40, GX[1] + 250, GY[1] + 150
    sh.rect(tx0, ty0, tx1, ty1, INK, THIN)
    for i in range(4):
        x = tx0 + 50 + i * (tx1 - tx0 - 100) / 3
        for y in (ty0 - 34, ty1 + 10):
            sh.rect(x - 22, y, x + 22, y + 24, INK, THIN, radius=5)
    sh.rect(WC + 30, GY[1] + TI / 2 + 20, WC + 80, GY[1] + TI / 2 + 50, INK, THIN)
    sh.d.ellipse(sh.P(WC - 90, GY[1] + 60, WC - 40, GY[1] + 130), outline=INK, width=sh.px(THIN))
    sh.rect(WC - 100, GY[1] + TI / 2 + 4, WC - 30, GY[1] + TI / 2 + 26, INK, THIN)

    # Rooms.
    for name, area, x, y in (("STUDIO", "172.4", (GX[0] + GX[3]) / 2, GY[0] + 150),
                             ("OFFICE", "27.4", (GX[3] + GX[4]) / 2 - 40, (GY[0] + GY[1]) / 2 + 30),
                             ("WC", "12.6", (GX[3] + WC) / 2, (GY[1] + GY[2]) / 2 + 60),
                             ("STORE", "12.6", (WC + GX[4]) / 2, (GY[1] + GY[2]) / 2),
                             ("ENTRY", "27.4", (GX[0] + GX[1]) / 2, (GY[2] + GY[3]) / 2),
                             ("STAIR", "27.4", (GX[1] + GX[2]) / 2, GY[3] - 90),
                             ("KITCHEN", "57.2", (GX[2] + GX[4]) / 2 - 40, (GY[2] + GY[3]) / 2 - 20)):
        sh.text(x, y - 14, name, 24, INK, "mm", bold=True)
        sh.text(x, y + 18, f"{area} m²", 17, INK, "mm")

    # Dimensions, section A-A, north arrow, scale bar.
    for i in range(4):
        hdim(sh, (GX[i], GY[0] - TE / 2), (GX[i + 1], GY[0] - TE / 2), GY[0] - 150, "6 000")
    hdim(sh, (GX[0], GY[0] - 150), (GX[4], GY[0] - 150), GY[0] - 214, "24 000")
    for j in range(3):
        vdim(sh, (GX[0] - TE / 2, GY[j]), (GX[0] - TE / 2, GY[j + 1]), GX[0] - 150, "5 000")
    vdim(sh, (GX[0] - 150, GY[0]), (GX[0] - 150, GY[3]), GX[0] - 214, "15 000")
    xa = (GX[1] + GX[2]) / 2 + 80
    cutting_plane(sh, (xa, GY[0] - 80), (xa, GY[3] + 80), "A", (-1, 0))
    nx, ny = 3250.0, 470.0
    sh.circle(nx, ny, 50, INK, MID)
    sh.polygon([(nx, ny - 46), (nx + 15, ny + 4), (nx, ny - 8)], fill=INK)
    sh.polygon([(nx, ny - 46), (nx - 15, ny + 4), (nx, ny - 8)], outline=INK, width=MID)
    sh.text(nx, ny - 76, "N", 24, INK, "mm", bold=True)
    for i in range(5):
        x = 3050 + i * 78
        sh.rect(x, 700, x + 78, 714, INK, 1.2, fill=INK if i % 2 == 0 else PAPER)
        sh.text(x, 736, str(i), 15, INK, "mm")
    sh.text(3050 + 5 * 78, 736, "5 m", 15, INK, "mm")
    view_title(sh, (GX[0] + GX[4]) / 2, GY[3] + 170, "GROUND FLOOR PLAN", "SCALE 1:75")
    return finish(sh, 5, "FLOOR PLAN — PAVILION", "1:75", "mm")


# --- 6 wing ------------------------------------------------------------------

def naca4(code, n=90):
    """Upper and lower surface and camber line of a NACA 4-digit section,
    chord 0..1, y up."""
    m, p, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    x = (1 - np.cos(np.linspace(0, math.pi, n))) / 2
    yt = 5 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3 - 0.1036 * x ** 4)
    yc = np.where(x < p, m / p ** 2 * (2 * p * x - x ** 2), m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x ** 2))
    dyc = np.where(x < p, 2 * m / p ** 2 * (p - x), 2 * m / (1 - p) ** 2 * (p - x))
    th = np.arctan(dyc)
    upper = list(zip(x - yt * np.sin(th), yc + yt * np.cos(th)))
    lower = list(zip(x + yt * np.sin(th), yc - yt * np.cos(th)))
    return upper, lower, list(zip(x, yc))


def render_wing(scale):
    sh = new_sheet(scale)
    RX, TX = 600.0, 2200.0              # root and tip stations in plan
    MMPX = 3.5

    def mm(px):                         # millimetres, to the nearest 5
        return fmt(round(px * MMPX / 5) * 5)

    def le(f):
        return 300 + 200 * f

    def te(f):
        return 740 - 50 * f

    def sx(f):
        return RX + f * (TX - RX)

    ribs = [i / 8 for i in range(9)]

    # --- plan view.
    for frac in (0.25, 0.68):
        sh.line([(sx(0), le(0) + frac * (te(0) - le(0))), (sx(0.97), le(0.97) + frac * (te(0.97) - le(0.97)))],
                INK, THIN, dash=HIDDEN)
    for f0, f1, frac in ((0.05, 0.52, 0.75), (0.56, 0.92, 0.78)):
        hinge = [(sx(f), le(f) + frac * (te(f) - le(f))) for f in (f0, f1)]
        sh.line(hinge, INK, THIN)
        for f, (hx, hy) in zip((f0, f1), hinge):
            sh.line([(hx, hy), (hx, te(f))], INK, THIN)
    for i, f in enumerate(ribs):
        sh.line([(sx(f), le(f)), (sx(f), te(f))], INK, HEAVY if i == 0 else THIN)
        sh.text(sx(f), le(f) - 22, f"R{i + 1}", 15, INK, "ms")
    cap = [(TX + 26 * math.sin(math.pi * u), le(1) + u * (te(1) - le(1))) for u in np.linspace(0, 1, 30)]
    sh.line([(RX, le(0)), (TX, le(1))] + cap + [(RX, te(0))], INK, THICK)
    sh.line([(RX, 250), (RX, 790)], INK, THIN, dash=DASHDOT)
    hdim(sh, (RX, le(0)), (TX, le(1)), 250, f"SPAN {mm(TX - RX)}")
    vdim(sh, (RX, le(0)), (RX, te(0)), RX - 80, mm(te(0) - le(0)))
    vdim(sh, (TX + 26, le(1)), (TX + 26, te(1)), TX + 110, mm(te(1) - le(1)))
    view_title(sh, (RX + TX) / 2, 830, "PLAN", "SCALE 1:25")

    # --- the ribs lofted: an oblique view, tip at the back, root in front.
    upper, lower, camber = naca4("2412")
    outline = upper[::-1] + lower[1:]
    O, V, sweep = (940.0, 1660.0), (1000.0, -500.0), 320.0

    def frame(f):
        c = 1.6 * (te(f) - le(f))
        lx, ly = O[0] + f * (V[0] + sweep), O[1] + f * V[1]
        return lambda x, y: (lx + x * c, ly - y * c), c

    def surface_y(x, surf):
        xs_, ys_ = zip(*sorted(surf))
        return float(np.interp(x, xs_, ys_))

    lines = [[], [], [], [], [], []]
    for f in ribs:
        R, c = frame(f)
        lines[0].append(R(0, 0))
        lines[1].append(R(1, 0))
        for j, x in enumerate((0.25, 0.68)):
            lines[2 + 2 * j].append(R(x, surface_y(x, upper)))
            lines[3 + 2 * j].append(R(x, surface_y(x, lower)))
    for ln in lines:
        sh.line(ln, INK, THIN)
    for i in reversed(range(len(ribs))):
        R, c = frame(ribs[i])
        pts = [R(x, y) for x, y in outline]
        root = i == 0
        sh.polygon(pts, fill=WASH if root else PAPER, outline=INK, width=HEAVY if root else MID)
        sh.line([R(0, 0), R(1, 0)], INK, THIN)
        sh.line([R(x, y) for x, y in camber], INK, THIN, dash=HIDDEN)
        for x in (0.40, 0.53):
            hx, hy = R(x, surface_y(x, camber))
            sh.circle(hx, hy, 0.034 * c, INK, THIN)
        tx, ty = R(1, 0)
        sh.text(tx + 12, ty + 6, f"R{i + 1}", 15, INK, "lm", bold=root)
    view_title(sh, 1400, 1800, "RIB LOFT", "NACA 2412 · OBLIQUE")

    rows = [["RIB", "STA", "CHORD"]] + [[f"R{i + 1}", mm(f * (TX - RX)), mm(te(f) - le(f))]
                                        for i, f in enumerate(ribs)]
    y = table(sh, 2860, 330, rows, [100, 150, 150], 38)
    sh.text(2873, y + 34, "NACA 2412 · t/c 12 %", 16, INK, "lm")
    return finish(sh, 6, "WING — RIB STATIONS", "1:25", "mm")


# --- 7 lettering -------------------------------------------------------------

def render_lettering(scale):
    sh = new_sheet(scale)
    K, X0, YB = 1.6, 1300.0, 1560.0     # px per font unit, origin, baseline

    def U(x, y):
        return X0 + K * x, YB - K * y

    CAP, XH, STEM, BAR, MBAR = 700, 500, 110, 64, 380
    # Bowls: (centre x, centre y, outer radius) and the counters inside them.
    up_o, up_i = (264, 524, 176), (228, 524, 112)
    lo_o, lo_i = (298, 206, 206), (256, 206, 142)
    width, lsb, rsb = lo_o[0] + lo_o[2], 50, 40

    def arc_u(cx, cy, r, a0, a1, n=80):     # font units, angles in degrees, y up
        return [U(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                for a in np.linspace(a0, a1, n)]

    # Where the two outer bowls meet on the right.
    (x1, y1, r1), (x2, y2, r2) = up_o, lo_o
    dd = math.hypot(x2 - x1, y2 - y1)
    along = (r1 * r1 - r2 * r2 + dd * dd) / (2 * dd)
    hh = math.sqrt(r1 * r1 - along * along)
    mx, my = x1 + along * (x2 - x1) / dd, y1 + along * (y2 - y1) / dd
    ix, iy = max(((mx + hh * (y2 - y1) / dd, my - hh * (x2 - x1) / dd),
                  (mx - hh * (y2 - y1) / dd, my + hh * (x2 - x1) / dd)))
    a_up = math.degrees(math.atan2(iy - y1, ix - x1))
    a_lo = math.degrees(math.atan2(iy - y2, ix - x2))
    outer = [U(0, CAP), U(up_o[0], CAP)] + arc_u(x1, y1, r1, 90, a_up) + arc_u(x2, y2, r2, a_lo, -90) + \
        [U(0, 0)]

    def counter(c, top, bottom):
        cx, cy, r = c
        return [U(STEM, top), U(cx, top)] + arc_u(cx, cy, r, 90, -90) + [U(cx, bottom), U(STEM, bottom)]

    c_up = counter(up_i, CAP - BAR, MBAR + BAR / 2)
    c_lo = counter(lo_i, MBAR - BAR / 2, BAR)

    # Guides first, faint, across the whole drawing.
    gx0, gx1 = 560.0, 2520.0
    for yv, name, style in ((CAP, "CAP 700", None), (XH, "x 500", HIDDEN), (MBAR, "BAR 380", DASHDOT),
                            (0, "BASE 0", None)):
        y = U(0, yv)[1]
        sh.line([(gx0, y), (gx1, y)], INK, MID if yv in (0, CAP) else THIN, dash=style)
        sh.text(gx0, y - 12, name, 15, INK, "ls")

    # The glyph, picked out.
    sh.wash([outer], [c_up, c_lo])
    sh.polygon(outer, outline=INK, width=HEAVY)
    sh.polygon(c_up, outline=INK, width=HEAVY)
    sh.polygon(c_lo, outline=INK, width=HEAVY)

    # Construction over it: the four circles, their centres, axes.
    for cx, cy, r in (up_o, up_i, lo_o, lo_i):
        sh.circle(*U(cx, cy), r * K, CONSTRUCT, THIN)
        centre_cross(sh, *U(cx, cy), 14, CONSTRUCT)
    for cy in (up_o[1], lo_o[1]):
        sh.line([U(-80, cy), U(width + 90, cy)], CONSTRUCT, THIN, dash=DASHDOT)
    for cx in (up_o[0], lo_o[0]):
        sh.line([U(cx, -50), U(cx, CAP + 60)], CONSTRUCT, THIN, dash=DASHDOT)
    for x in (-lsb, width + rsb):
        sh.line([U(x, -40), U(x, CAP + 40)], INK, THIN, dash=HIDDEN)

    # Radii.
    for (cx, cy, r), deg, outside in ((up_o, 40, True), (lo_o, -40, True), (up_i, 140, False),
                                      (lo_i, 220, False)):
        c = U(cx, cy)
        p = U(cx + r * math.cos(math.radians(deg)), cy + r * math.sin(math.radians(deg)))
        ang = math.atan2(p[1] - c[1], p[0] - c[0])
        end = polar(*p, 70, ang) if outside else p
        sh.line([c, end], INK, THIN)
        sh.arrow(*p, math.degrees(ang), 15)
        if outside:
            sh.text(end[0] + 10, end[1], f"R{r}", 18, INK, "lm")
        else:
            sh.label((c[0] + p[0]) / 2, (c[1] + p[1]) / 2, f"R{r}", 16)

    # Dimensions.
    hdim(sh, U(0, CAP), U(STEM, CAP), U(0, CAP)[1] - 70, str(STEM))
    vdim(sh, U(-lsb, 0), U(-lsb, CAP), U(-lsb, 0)[0] - 110, str(CAP))
    vdim(sh, U(150, CAP), U(150, CAP - BAR), U(150, 0)[0], str(BAR))
    hdim(sh, U(lo_i[0] + lo_i[2], lo_o[1]), U(width, lo_o[1]), U(0, lo_o[1])[1],
         str(width - lo_i[0] - lo_i[2]))
    yd = YB + 90
    hdim(sh, U(-lsb, -40), U(0, -40), yd, str(lsb))
    hdim(sh, U(0, 0), U(width, 0), yd, str(width))
    hdim(sh, U(width, -40), U(width + rsb, -40), yd, str(rsb))
    hdim(sh, U(-lsb, -40), U(width + rsb, -40), yd + 70, str(lsb + width + rsb))
    view_title(sh, U(width / 2, 0)[0], YB + 250, "LATIN CAPITAL LETTER B", "U+0042 · 1 000 UNITS / EM")

    table(sh, 2700, 330, [["METRIC", "UNITS"], ["CAP HEIGHT", str(CAP)], ["x-HEIGHT", str(XH)],
                          ["STEM", str(STEM)], ["BARS", str(BAR)], ["BOWLS R", f"{up_o[2]} / {lo_o[2]}"],
                          ["COUNTERS R", f"{up_i[2]} / {lo_i[2]}"], ["ADVANCE", str(lsb + width + rsb)]],
          [230, 190])
    return finish(sh, 7, "LETTER B — CONSTRUCTION", "1.6 : 1", "units")


# --- 8 rocket ----------------------------------------------------------------

def render_rocket(scale):
    sh = new_sheet(scale)
    YC, R = 700.0, 100.0
    XN, XA, XI, XS, XF, XO, XT = 580.0, 720.0, 1840.0, 2000.0, 2600.0, 2800.0, 3200.0

    def sta(x):
        return fmt((XT - x) * 10)

    rho = (R * R + (XT - XO) ** 2) / (2 * R)          # tangent ogive

    def ogive(x):
        return math.sqrt(max(0.0, rho * rho - (x - XO) ** 2)) + R - rho

    def dome(x0, sgn, rd=88):
        """A 2:1 elliptical tank dome from x0, bulging toward sgn, dashed."""
        ys = np.linspace(-rd, rd, 40)
        sh.line([(x0 + sgn * rd / 2 * math.sqrt(max(0.0, 1 - (y / rd) ** 2)), YC + y) for y in ys],
                INK, THIN, dash=HIDDEN)

    # Station lines up top.
    for x in (XT, XO, XF, XS, XI, XA, XN):
        sh.line([(x, YC - R - 12), (x, 380)], INK, THIN, dash=DASHDOT)
        sh.text(x, 362, f"STA {sta(x)}", 15, INK, "ms")

    # Fins: two in profile, one edge on.
    fin = [(XA, YC - R), (XA + 60, YC - R - 150), (XA + 170, YC - R - 150), (XA + 240, YC - R)]
    for pts in (fin, [(x, 2 * YC - y) for x, y in fin]):
        sh.polygon(pts, fill=PAPER, outline=INK, width=THICK)
    # Fairing, picked out.
    fairing = [(XF, YC - R), (XO, YC - R)] + [(x, YC - ogive(x)) for x in np.linspace(XO, XT, 60)] + \
        [(x, YC + ogive(x)) for x in np.linspace(XT, XO, 60)] + [(XF, YC + R)]
    sh.wash([fairing])
    # Body.
    sh.line([(XA, YC - R), (XF, YC - R)], INK, THICK)
    sh.line([(XA, YC + R), (XF, YC + R)], INK, THICK)
    sh.line([(XA, YC - R), (XA, YC + R)], INK, THICK)
    for x in (XI, XS):
        sh.line([(x, YC - R), (x, YC + R)], INK, MID)
    sh.polygon(fairing, outline=INK, width=HEAVY)
    sh.line([(XF + 10, YC), (XT - 30, YC)], INK, THIN, dash=DASHDOT)
    sh.rect(XA, YC - 5, XA + 240, YC + 5, INK, THIN, fill=PAPER)
    sh.line([(XA + 300, YC - R - 8), (XF - 30, YC - R - 8)], INK, THIN)
    sh.line([(XA + 300, YC - R), (XA + 300, YC - R - 8)], INK, THIN)
    sh.line([(XF - 30, YC - R), (XF - 30, YC - R - 8)], INK, THIN)
    # Nozzle, outside.
    throat = XA - 34
    nz = [(XA, 40.0), (XA - 18, 40.0), (throat, 26.0)] + \
        [(x, 26 + 46 * ((throat - x) / (throat - XN)) ** 0.55) for x in np.linspace(throat, XN, 30)[1:]]
    sh.line([(x, YC - r) for x, r in nz], INK, THICK)
    sh.line([(x, YC + r) for x, r in nz], INK, THICK)
    sh.line([(XN, YC - nz[-1][1]), (XN, YC + nz[-1][1])], INK, THICK)
    sh.line([(XA - 18, YC - 40), (XA - 18, YC + 40)], INK, THIN)

    # Hidden: tank domes, the feed line, the upper stage engine, the payload.
    dome(800, -1)
    dome(1200, 1)
    dome(1270, -1)
    dome(1760, 1)
    sh.line([(1226, YC - 10), (XA, YC - 10)], INK, THIN, dash=HIDDEN)
    sh.line([(1226, YC + 10), (XA, YC + 10)], INK, THIN, dash=HIDDEN)
    dome(2060, -1)
    dome(2300, -1)
    dome(2520, 1)
    bell = [(x, 30 + 40 * ((XS - x) / (XS - 1870)) ** 0.6) for x in np.linspace(XS, 1870, 20)]
    sh.line([(x, YC - r) for x, r in bell], INK, THIN, dash=HIDDEN)
    sh.line([(x, YC + r) for x, r in bell], INK, THIN, dash=HIDDEN)
    sh.line([(1870, YC - 70), (1870, YC + 70)], INK, THIN, dash=HIDDEN)
    pay = [(2650, YC - 76), (2930, YC - 76), (3060, YC - 30), (3060, YC + 30), (2930, YC + 76), (2650, YC + 76)]
    sh.polygon(pay, outline=INK, width=THIN, dash=HIDDEN)
    sh.line([(XF + 20, YC - 92), (2650, YC - 50), (2650, YC + 50), (XF + 20, YC + 92)], INK, THIN, dash=HIDDEN)

    # Lengths and the diameter.
    yd = YC + R + 220
    pts = [(XN, YC + nz[-1][1]), (XI, YC + R), (XS, YC + R), (XF, YC + R), (XT, YC)]
    for p, q in zip(pts, pts[1:]):
        hdim(sh, p, q, yd, fmt((q[0] - p[0]) * 10))
    hdim(sh, pts[0], pts[-1], yd + 70, fmt((XT - XN) * 10))
    vdim(sh, (XO, YC - R), (XO, YC + R), XT + 110, "Ø2 000")
    cutting_plane(sh, (1480, YC - R - 36), (1480, YC + R + 36), "B", (-1, 0))
    cutting_plane(sh, (2700, YC - R - 36), (2700, YC + R + 36), "C", (-1, 0))

    # SECTION B-B through the oxidiser tank, and C-C through the fairing.
    for cx, name in ((1300.0, "B"), (2060.0, "C")):
        cy, ro = 1560.0, 170.0
        ri = 160.0 if name == "B" else 154.0
        centre_lines(sh, cx, cy, ro, 30)
        ring = [("circle", cx, cy, ro)]
        sh.hatch(ring, [("circle", cx, cy, ri)], spacing=7)
        sh.circle(cx, cy, ro, INK, THICK)
        sh.circle(cx, cy, ri, INK, THICK)
        if name == "B":
            for i in range(24):
                a = math.radians(i * 15 + 7.5)
                u, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
                pts = [(cx + u[0] * rr + n[0] * w, cy + u[1] * rr + n[1] * w)
                       for rr, w in ((ri, -4), (ri - 16, -4), (ri - 16, 4), (ri, 4))]
                sh.polygon(pts, fill=INK)
            sh.circle(cx, cy, 22, INK, THICK, fill=PAPER)
            sh.circle(cx, cy, 17, INK, THIN)
        else:
            for a in (0, 180):
                for off in (-1.6, 1.6):
                    p0 = polar(cx, cy, ri, math.radians(a + off))
                    p1 = polar(cx, cy, ro, math.radians(a + off))
                    sh.line([p0, p1], INK, THIN)
            hexagon = [polar(cx, cy, 98, math.radians(30 + 60 * i)) for i in range(6)]
            sh.polygon(hexagon, fill=PAPER, outline=INK, width=THICK)
            sh.circle(cx, cy, 136, INK, THIN, dash=HIDDEN)
        view_title(sh, cx, cy + ro + 76, f"SECTION {name}-{name}", "SCALE 1:12")

    notes = ["NOTES", "1. DIMENSIONS IN mm.", "2. STATIONS FROM THE NOSE TIP.",
             "3. HIDDEN LINES: TANK DOMES, FEED LINE,", "   UPPER STAGE NOZZLE, PAYLOAD ENVELOPE."]
    for i, line in enumerate(notes):
        sh.text(2660, 1440 + i * 34, line, 16, INK, "ls", bold=(i == 0))
    return finish(sh, 8, "LAUNCH VEHICLE — GENERAL ARRANGEMENT", "1:100", "mm")


# --- 9 orbits ----------------------------------------------------------------

def render_orbits(scale):
    sh = new_sheet(scale)
    F = (1700.0, 1080.0)
    AU = 480.0                                       # px per astronomical unit
    r1, r2 = 1.000 * AU, 1.524 * AU
    a = (r1 + r2) / 2
    c = a - r1
    b = math.sqrt(r1 * r2)
    tp = math.radians(195)                            # periapsis direction
    u = (math.cos(tp + math.pi), math.sin(tp + math.pi))
    v = (u[1], -u[0])
    Ce = (F[0] + c * u[0], F[1] + c * u[1])

    def ell(E):
        return (Ce[0] + a * math.cos(E) * u[0] + b * math.sin(E) * v[0],
                Ce[1] + a * math.cos(E) * u[1] + b * math.sin(E) * v[1])

    peri, apo = polar(*F, r1, tp), polar(*F, r2, tp + math.pi)
    transfer = [ell(E) for E in np.linspace(math.pi, 2 * math.pi, 300)]
    other = [ell(E) for E in np.linspace(0, math.pi, 300)]
    lead = math.pi * (1 - ((r1 + r2) / (2 * r2)) ** 1.5)
    inner_move = math.pi * (a / r1) ** 1.5

    # Orbits, apsis line, the dashed half of the ellipse.
    sh.line([polar(*F, r1 + 90, tp), polar(*F, r2 + 90, tp + math.pi)], INK, THIN, dash=DASHDOT)
    sh.circle(*F, r1, INK, MID)
    sh.circle(*F, r2, INK, MID)
    sh.line(other, INK, THIN, dash=HIDDEN)
    for r, degs in ((r1, (60, 300)), (r2, (100, 250))):
        for dg in degs:
            p, q = polar(*F, r, math.radians(dg)), polar(*F, r, math.radians(dg - 1))
            sh.arrow(*q, math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])), 18)

    # Phase angle at departure.
    target0 = tp - lead
    sh.line([F, polar(*F, r2, target0)], INK, THIN)
    sh.line([F, peri], INK, THIN)
    sh.arc(*F, 210, math.degrees(target0), math.degrees(tp), INK, THIN)
    sh.label(*polar(*F, 250, (target0 + tp) / 2), f"φ {math.degrees(lead):.1f}°", 18)

    # The transfer, picked out, and the two burns.
    sh.line(transfer, INK, HEAVY)
    for p, ang, name in ((peri, tp, "Δv₁"), (apo, tp + math.pi, "Δv₂")):
        d = (math.sin(ang), -math.cos(ang))
        q = (p[0] + d[0] * 150, p[1] + d[1] * 150)
        sh.line([p, q], INK, THICK)
        sh.arrow(*q, math.degrees(math.atan2(d[1], d[0])), 22)
        sh.label(q[0] + 44 * (1 if d[0] >= 0 else -1), q[1], name, 22, bold=True)

    # Bodies: the centre, both planets at departure and at arrival.
    sh.circle(*F, 46, INK, THICK, fill=WASH)
    sh.circle(*F, 5, INK, 1, fill=INK)
    for p, r, ghost in ((peri, 16, False), (polar(*F, r2, target0), 20, True), (apo, 20, False),
                        (polar(*F, r1, tp - inner_move), 16, True)):
        if ghost:
            sh.circle(*p, r, INK, MID, fill=PAPER, dash=(6, 5))
        else:
            sh.circle(*p, r, INK, THICK, fill=WASH)

    # Radii and names.
    for r, deg, name in ((r1, 250, "r₁"), (r2, 326, "r₂")):
        p = polar(*F, r, math.radians(deg))
        sh.line([F, p], INK, THIN)
        sh.arrow(*p, deg, 16)
        sh.label(*polar(*F, (r + (r1 if r > r1 else 0)) * 0.5, math.radians(deg)), name, 20, bold=True)

    # Days since departure along the transfer (Kepler's equation, from periapsis).
    ecc = c / a
    for days in (50, 100, 150, 200):
        M = math.pi * days / 259
        E = M
        for _ in range(30):
            E -= (E - ecc * math.sin(E) - M) / (1 - ecc * math.cos(E))
        p = ell(E + math.pi)
        ang = math.atan2(p[1] - F[1], p[0] - F[0])
        sh.line([polar(*p, -12, ang), polar(*p, 12, ang)], INK, MID)
        sh.text(*polar(*p, 44, ang), f"{days} d", 15, INK, "mm")
    leader(sh, peri, (peri[0] - 120, peri[1] - 150), "PERIAPSIS", 18, bold=True, head="dot")
    leader(sh, apo, (apo[0] + 110, apo[1] + 150), "APOAPSIS", 18, bold=True, head="dot")
    leader(sh, polar(*F, r1, math.radians(345)), (2600, 780), "ORBIT 1", 17, head="dot")
    leader(sh, polar(*F, r2, math.radians(235)), (820, 380), "ORBIT 2", 17, head="dot")
    leader(sh, ell(1.42 * math.pi), (1250, 1830), "TRANSFER ELLIPSE", 17, head="dot")
    sh.label(F[0] + 40, F[1] + 64, "F", 22, bold=True)

    table(sh, 2780, 330, [["ELEMENT", "VALUE"], ["r₁", "1.000 AU"], ["r₂", "1.524 AU"],
                          ["a", f"{a / AU:.3f} AU"], ["e", f"{c / a:.3f}"], ["t", "259 d"],
                          ["φ", f"{math.degrees(lead):.1f}°"], ["Δv₁", "2.94 km/s"], ["Δv₂", "2.65 km/s"]],
          [200, 220])
    return finish(sh, 9, "TRANSFER ORBIT", "NTS", "AU")


# --- main --------------------------------------------------------------------

RENDERERS = {
    "gears": ("1-gears.png", render_gears),
    "hull": ("2-hull.png", render_hull),
    "bridge": ("3-bridge.png", render_bridge),
    "linkage": ("4-linkage.png", render_linkage),
    "plan": ("5-plan.png", render_plan),
    "wing": ("6-wing.png", render_wing),
    "lettering": ("7-lettering.png", render_lettering),
    "rocket": ("8-rocket.png", render_rocket),
    "orbits": ("9-orbits.png", render_orbits),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", default=["all"], help="which to render: " + ", ".join(RENDERERS) + ", or all")
    ap.add_argument("--width", type=int, default=3840)
    ap.add_argument("--height", type=int, default=2160)
    ap.add_argument("--out", default=os.path.join(THEME_DIR, "backgrounds"))
    args = ap.parse_args()

    names = list(RENDERERS) if "all" in args.names else args.names
    os.makedirs(args.out, exist_ok=True)
    for name in names:
        filename, render = RENDERERS[name]
        img = render(args.height / Sheet.H)
        if img.width != args.width:
            # The sheets are laid out 16:9; other shapes get them centred on paper.
            canvas = Image.new("RGB", (args.width, args.height), PAPER)
            canvas.paste(img, ((args.width - img.width) // 2, 0))
            img = canvas
        path = os.path.join(args.out, filename)
        img.save(path, optimize=True)
        print(f"Wrote {path} ({args.width}x{args.height}, {os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
