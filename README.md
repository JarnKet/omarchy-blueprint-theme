# Blueprint — an Omarchy theme

A light theme for coding in daylight, even out in the sun: white panels,
near-black text, and one blueprint blue, in the colors of
[blueprint.page](https://blueprint.page)'s design system.

![Blueprint theme preview](preview.png)

## Install

```bash
omarchy theme install https://github.com/JarnKet/omarchy-blueprint-theme
```

Omarchy switches GTK apps, browsers and VS Code to their light mode with it,
and generates VS Code, Neovim, terminal and btop colors from the palette.

## Built for sunlight

Body text is 17.7:1 against the white background, and every terminal color
is at least 5.2:1, so nothing washes out in bright light. Disabled text,
which is meant to recede, is lighter.

| Role                | Hex       | From blueprint.page |
|---------------------|-----------|---------------------|
| background          | `#FFFFFF` | panel               |
| dark background     | `#F7F7F8` | page background     |
| darker background   | `#EEEFF1` | shell               |
| foreground          | `#18181B` | text                |
| light foreground    | `#3F3F46` | secondary text      |
| muted               | `#5F5F68` | muted text          |
| accent, blue        | `#104BFF` | brand blue          |
| magenta             | `#6A4CF5` | AI violet           |
| red                 | `#C2372B` | danger              |
| green               | `#16794A` | success text        |
| yellow              | `#8A5D00` | warning, darkened to read on white |
| cyan, orange, brown | `#0E7490`, `#C2410C`, `#7C4A1E` | added in the same weight |

## Files

- `colors.toml`: the palette (`mode = "light"`).
- `shell.toml`: bar, popups, menus and notifications on white with
  blueprint.page's neutral `#E4E4E7` lines; blue is kept for selection and
  focus.
- `btop.theme`: neutral boxes; only the graphs carry color.
- `neovim.lua`: the generated aether palette, marked as a light theme
  (`background = "light"`) so Neovim and its plugins pick light variants.
  Omarchy uses it from a linked checkout; an installed copy falls back to the
  generated one.
- `icons.theme`: `Yaru-blue`.
- `backgrounds/`: four wallpapers drawn in blueprint ink by
  `tools/make-wallpaper.py` (`make-wallpaper.py all`, or name the ones to
  redo):
  1. **thinkpad**: a technical drawing of a ThinkPad T14s Gen 6. Plan view
     open flat, front and left elevations, dimensions (313.6 × 219.4 × 16.9 mm,
     the published footprint), numbered callouts, a parts list, a 4:1 detail
     of the TrackPoint and a title block.
  2. **grid**: engineering paper in a zoned border with a datum, a north arrow,
     a scale bar and a title block.
  3. **isometric**: a little city of blocks on an isometric grid.
  4. **contours**: contour lines of an imaginary terrain, one in violet.

  Cycle them with `omarchy theme bg next`.
- `preview.png`: the theme switcher thumbnail, from `tools/make-preview.sh`
  (takes over an empty workspace for about 10 seconds).
  `tools/palette.sh` prints the terminal palette.

## Developing

Link a checkout instead of installing, so edits apply on the next
`omarchy theme set blueprint`:

```bash
ln -s ~/Projects/blueprint-theme ~/.config/omarchy/themes/blueprint
```

## How this was made

The idea and the choices are mine: a bright theme I can read outdoors,
blueprint.page's colors, and the technical-drawing wallpapers. The files were
written by Claude (Anthropic's AI) in Claude Code from what I asked for. I
tried the theme on my own machine and take responsibility for what's here.

## Credits

The palette follows the design tokens of [blueprint.page](https://blueprint.page).
Not affiliated with Blueprint. ThinkPad and TrackPoint are trademarks of
Lenovo; the drawing is an illustration, not an official one.

## License

MIT; see [LICENSE](LICENSE).
