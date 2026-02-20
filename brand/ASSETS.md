# TenetFolio — Asset Inventory

## Directory Structure

Place all brand assets under a top-level `brand/` directory in your repo:

```
tenetfolio/
├── brand/
│   ├── STYLE_GUIDE.md          ← Claude Code reads this
│   ├── logo/
│   │   ├── gridmark-dark.svg   ← Primary mark, dark background
│   │   ├── gridmark-light.svg  ← Primary mark, light background
│   │   ├── icon-dark.svg       ← Standalone icon (no wordmark), dark bg
│   │   ├── icon-light.svg      ← Standalone icon (no wordmark), light bg
│   │   ├── icon-mono-white.svg ← Monochrome white (for colored backgrounds)
│   │   ├── lockup-h-dark.svg   ← Horizontal lockup, dark bg
│   │   ├── lockup-h-light.svg  ← Horizontal lockup, light bg
│   │   └── ascii.txt           ← ASCII art for CLI splash screen
│   └── favicon/
│       ├── favicon.svg         ← SVG favicon (modern browsers)
│       ├── favicon.ico         ← Fallback (generate from SVG, 16+32px)
│       ├── apple-touch-icon.png← 180×180 PNG
│       └── og-image.png        ← 1200×630 social preview for GitHub/Open Graph
├── docs/
│   └── assets/
│       ├── logo-dark.png       ← PNG export of dark-bg mark (GitHub dark mode)
│       └── logo-light.png      ← PNG export of light-bg mark (GitHub light mode)
```

---

## Asset Checklist

### Must-Have (Before First Commit)

| Asset | Format | Purpose | Notes |
|---|---|---|---|
| Primary mark (dark) | SVG | README header, docs | Full grid + wordmark on `#0f172a` |
| Primary mark (light) | SVG | Light-mode docs | Full grid + wordmark on `#f8fafc` |
| Standalone icon (dark) | SVG | Anywhere text isn't needed | Grid-F only, no wordmark |
| Favicon | SVG + ICO | Browser tab | Minimal grid-F, optimized for 16–32px |
| `og-image.png` | PNG 1200×630 | GitHub social preview, link previews | Dark bg, icon + wordmark centered |
| `logo.png` | PNG ~400px wide | README `<img>` tag | Transparent background |

### Nice-to-Have (Before Public Launch)

| Asset | Format | Purpose | Notes |
|---|---|---|---|
| Horizontal lockups | SVG | Nav bars, CLI headers | Compact single-line layout |
| Monochrome variants | SVG | On emerald bg, printed materials | Single-color white or single-color dark |
| Apple touch icon | PNG 180×180 | iOS home screen bookmark | Icon only, with bg fill in the PNG |
| ASCII logo | Text | CLI splash screen | Grid-F + wordmark, in `brand/logo/ascii.txt` |

---

## How to Export

Since the logos are defined as SVGs, export workflow is straightforward:

**SVGs** — These are your source-of-truth files. Copy the SVG code directly from the exploration HTML or recreate from the style guide spec.

**PNGs** — Generate from SVGs at 2× or 3× for retina. Preferred tool: **librsvg** (`brew install librsvg`) — handles SVG text and fonts reliably.
```bash
# Preferred: librsvg
rsvg-convert -w 800 gridmark-dark.svg > logo.png

# Alternative: Inkscape (CLI)
inkscape gridmark-dark.svg -w 800 -o logo.png

# Alternative: ImageMagick (may struggle with SVG text elements)
magick -background none -density 300 gridmark-dark.svg logo.png
```

**Favicon ICO** — Generate multi-resolution using ImageMagick (`brew install imagemagick`):
```bash
# First export SVG to a high-res PNG, then create the ICO
rsvg-convert -w 512 -h 512 favicon.svg > /tmp/favicon-512.png
magick /tmp/favicon-512.png -define icon:auto-resize=16,32,48 favicon.ico
```

**OG Image** — Create a 1200×630 canvas with `#0f172a` background, center the horizontal lockup:
```bash
rsvg-convert -w 600 lockup-h-dark.svg > /tmp/lockup-h-dark-600.png
magick -size 1200x630 xc:'#0f172a' \
  \( /tmp/lockup-h-dark-600.png -resize 600x \) \
  -gravity center -composite og-image.png
```

---

## README Usage

```markdown
<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-light.png">
    <img src="docs/assets/logo-light.png" alt="TenetFolio" width="360">
  </picture>
  <p><strong>Sovereign financial architecture.</strong></p>
  <p>Your data, your schema, your future.</p>
</div>
```

For GitHub's social preview, go to **Settings → Social preview** and upload `og-image.png`.
