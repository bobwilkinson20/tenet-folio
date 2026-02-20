# TenetFolio — Style Guide

> **Purpose:** This document defines the visual identity and UI conventions for TenetFolio.
> It is intended to be read by Claude Code (or any contributor) before implementing any
> frontend work. Follow these specifications exactly to maintain brand consistency.

---

## 1. Brand Identity

**Name:** TenetFolio (one word, camelCase in prose, `tenetfolio` in code/CLI)

**Tagline:** "Sovereign financial architecture."

**Positioning:** An engineer-first, self-hosted portfolio tracker built on the principles of data sovereignty, schema-driven design, and long-term financial clarity.

**Voice:** Technical but human. Precise but not cold. Think "senior engineer writing clear documentation," not "fintech marketing copy."

---

## 2. Logo — The Grid Mark

The logo is an **F letterform** that emerges from a dot grid, representing structured data where important nodes are highlighted. Every element maps to an architectural concept:

- **Top row (4 nodes, white→gray gradient):** The F's top bar. Represents the data schema — columns of structured information.
- **Left column (vertical nodes, gray):** The F's vertical stem. Represents the timeline — snapshots stacked over time.
- **Middle row (3 nodes, emerald gradient):** The F's crossbar. Represents the target allocation — the rule that cuts across all holdings.
- **Background grid dots:** The dormant data. Present but not active.

### 2.1 Grid Specifications

The icon is built on a **4-column × 5-row** dot grid with 16px spacing (scalable).

```
Grid positions (col, row):        Active nodes:
(0,0) (1,0) (2,0) (3,0)          ●  ●  ●  ●   ← Top bar (white gradient)
(0,1) (1,1) (2,1) (3,1)          ●  ·  ·  ·   ← Stem only
(0,2) (1,2) (2,2) (3,2)          ◆  ◆  ◆  ·   ← Crossbar (emerald)
(0,3) (1,3) (2,3) (3,3)          ●  ·  ·  ·   ← Stem only
(0,4) (1,4) (2,4) (3,4)          ●  ·  ·  ·   ← Stem end
```

### 2.2 Node Sizing

Nodes use variable radii to create hierarchy:

| Node | Radius | Color |
|---|---|---|
| (0,0) — anchor | 4.5 | `slate-100` `#f1f5f9` |
| (1,0) | 4.5 | `slate-200` `#e2e8f0` |
| (2,0) | 4.5 | `slate-300` `#cbd5e1` |
| (3,0) | 4.5 | `slate-400` `#94a3b8` |
| (0,1) — stem | 4.0 | `slate-400` `#94a3b8` |
| (0,2) — crossbar anchor | 5.0 | `emerald-500` `#10b981` |
| (1,2) — crossbar | 4.5 | `emerald-400` `#34d399` |
| (2,2) — crossbar end | 4.0 | `emerald-300` `#6ee7b7` at 70% opacity |
| (0,3) — stem | 4.0 | `slate-500` `#64748b` |
| (0,4) — stem end | 4.5 | `slate-400` `#94a3b8` |
| Inactive grid dots | 2.5 | `slate-700` `#334155` at 30% opacity |

### 2.3 Connection Lines (Optional)

Subtle lines connect active nodes. Use only in the full-size mark, omit at small sizes.

| Line | Stroke | Opacity |
|---|---|---|
| Top bar: (0,0) → (3,0) | `#f1f5f9` width 1.2 | 0.15 |
| Stem: (0,0) → (0,4) | `#94a3b8` width 1.2 | 0.12 |
| Crossbar: (0,2) → (2,2) | `#10b981` width 1.2 | 0.20 |

### 2.4 Light Background Variant

On light backgrounds, invert the slate values:

| Element | Dark BG | Light BG |
|---|---|---|
| Top bar nodes | `slate-100` → `slate-400` | `slate-900` → `slate-600` |
| Stem nodes | `slate-400` / `slate-500` | `slate-500` / `slate-600` |
| Crossbar nodes | `emerald-500/400/300` | `emerald-600/500/400` |
| Inactive dots | `slate-700` at 30% | `slate-300` at 35% |

### 2.5 Favicon / Small Size Simplification

At sizes ≤32px, reduce the grid:
- Remove inactive background dots
- Remove connection lines
- Increase node radii proportionally so they remain visible
- Minimum: 7 nodes (top bar 3 + stem 2 + crossbar 2)

---

## 3. Typography

**Primary font family:** `JetBrains Mono`

This is used for **everything** — the wordmark, headings, body text, data labels, and code. TenetFolio is an engineer's tool. The monospace font is a deliberate identity choice.

```css
font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', 'Cascadia Code', monospace;
```

### 3.1 Wordmark

| Element | Weight | Size (relative) | Letter-spacing | Color (dark bg) |
|---|---|---|---|---|
| `tenet` | 600 (SemiBold) | 1× | +1.5px | `slate-100` `#f1f5f9` |
| `folio` | 400 (Regular) | 0.65× | +4px | `slate-500` `#64748b` |

In horizontal lockups, the name renders as **one continuous word** (`tenetfolio`) with a color shift — no space, no separator. This matches the repo name, package name, and CLI command.

| Element | Weight | Size | Letter-spacing | Color (dark bg) |
|---|---|---|---|---|
| `tenet` | 500 (Medium) | 1× | +0.5px | `slate-100` `#f1f5f9` |
| `folio` | 500 (Medium) | 1× | +0.5px | `emerald-500` `#10b981` |

Implementation: use `<tspan>` elements in SVG or separate `<span>` elements in HTML — never a space character between them.

### 3.2 UI Typography Scale

Use this scale throughout the application:

| Token | Size | Weight | Line-height | Use |
|---|---|---|---|---|
| `display` | 32px | 600 | 1.2 | Page titles, net worth headline |
| `heading-1` | 24px | 600 | 1.2 | Section headers |
| `heading-2` | 18px | 500 | 1.3 | Card titles, table headers |
| `body` | 14px | 400 | 1.5 | General text, descriptions |
| `body-small` | 13px | 400 | 1.5 | Secondary text, timestamps |
| `caption` | 11px | 400 | 1.4 | Labels, helper text |
| `mono-data` | 14px | 500 | 1.6 | Financial figures, numbers |
| `mono-label` | 10px | 400 | 1.4 | Axis labels, legend items, uppercase w/ 2px tracking |

---

## 4. Color System

### 4.1 Core Palette

```css
:root {
  /* ── Background ── */
  --bg-primary:     #0f172a;  /* slate-900 — main app background */
  --bg-surface:     #1e293b;  /* slate-800 — cards, panels */
  --bg-elevated:    #334155;  /* slate-700 — hover states, active items */
  --bg-overlay:     #020617;  /* slate-950 — modals backdrop */

  /* ── Text ── */
  --text-primary:   #f1f5f9;  /* slate-100 — headings, primary content */
  --text-secondary: #94a3b8;  /* slate-400 — descriptions, labels */
  --text-tertiary:  #64748b;  /* slate-500 — placeholders, disabled */
  --text-muted:     #475569;  /* slate-600 — subtle hints */

  /* ── Border ── */
  --border-subtle:  rgba(148, 163, 184, 0.06);  /* card borders */
  --border-default: rgba(148, 163, 184, 0.12);  /* input borders */
  --border-strong:  rgba(148, 163, 184, 0.20);  /* focus rings */

  /* ── Accent: Emerald (primary action, growth, positive) ── */
  --accent-primary:   #10b981;  /* emerald-500 — buttons, links, positive values */
  --accent-hover:     #34d399;  /* emerald-400 — hover state */
  --accent-muted:     rgba(16, 185, 129, 0.08);  /* emerald tinted bg */
  --accent-border:    rgba(16, 185, 129, 0.15);  /* emerald tinted border */
  --accent-on-light:  #059669;  /* emerald-600 — accent on light backgrounds */

  /* ── Semantic ── */
  --positive:   #10b981;  /* emerald-500 — gains, success */
  --negative:   #ef4444;  /* red-500 — losses, errors */
  --warning:    #f59e0b;  /* amber-500 — warnings, caution */
  --info:       #3b82f6;  /* blue-500 — informational */
  --neutral:    #64748b;  /* slate-500 — unchanged, zero */
}
```

### 4.2 Usage Rules

- **Never use pure white (`#ffffff`) or pure black (`#000000`)** as background or text colors. Always use the slate scale.
- **Emerald is for positive/growth/action only.** Don't use it decoratively. When something is emerald, it means "this is good" or "interact with this."
- **Red is for losses and errors only.** Don't use it for decoration or emphasis.
- **Financial values:** Positive = `--positive`, Negative = `--negative`, Zero/unchanged = `--neutral`.
- **Percentage changes:** Always show sign: `+4.2%` in emerald, `-1.8%` in red, `0.0%` in neutral.

### 4.3 Light Mode (If Implemented)

Swap the background and text scales:

```css
[data-theme="light"] {
  --bg-primary:     #f8fafc;  /* slate-50 */
  --bg-surface:     #ffffff;
  --bg-elevated:    #f1f5f9;  /* slate-100 */
  --text-primary:   #0f172a;  /* slate-900 */
  --text-secondary: #475569;  /* slate-600 */
  --text-tertiary:  #94a3b8;  /* slate-400 */
  --accent-primary: #059669;  /* emerald-600 — darker for contrast */
  --border-subtle:  rgba(15, 23, 42, 0.06);
  --border-default: rgba(15, 23, 42, 0.12);
}
```

---

## 5. Layout & Spacing

### 5.1 Spacing Scale

Use a **4px base unit** system:

| Token | Value | Use |
|---|---|---|
| `space-1` | 4px | Tight gaps (inline elements, icon padding) |
| `space-2` | 8px | Small gaps (between related items) |
| `space-3` | 12px | Default gap (list items, form fields) |
| `space-4` | 16px | Section padding within cards |
| `space-5` | 20px | Card internal padding |
| `space-6` | 24px | Between cards/sections |
| `space-8` | 32px | Major section breaks |
| `space-10` | 40px | Page-level padding |
| `space-16` | 64px | Hero/header spacing |

### 5.2 Border Radius

| Token | Value | Use |
|---|---|---|
| `radius-sm` | 4px | Tags, badges, small chips |
| `radius-md` | 8px | Buttons, inputs, small cards |
| `radius-lg` | 12px | Cards, panels, dropdowns |
| `radius-xl` | 16px | Large cards, modals |
| `radius-2xl` | 20px | Hero sections |

### 5.3 Container Widths

| Context | Max Width |
|---|---|
| Main dashboard content | 1200px |
| Narrow content (settings, forms) | 640px |
| Wide content (tables, charts) | 100% with 40px padding |

---

## 6. Component Patterns

### 6.1 Cards

Cards are the primary UI container.

```css
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);  /* 12px */
  padding: var(--space-5);           /* 20px */
}

/* Card with header */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-4);     /* 16px */
}

.card-title {
  font-size: 18px;
  font-weight: 500;
  color: var(--text-primary);
}
```

### 6.2 Data Tables

Financial data is displayed in tables. Keep them clean and scannable.

```css
.data-table th {
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--text-tertiary);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border-default);
  text-align: left;
}

.data-table td {
  font-size: 14px;
  font-weight: 500;  /* numbers should feel solid */
  color: var(--text-primary);
  padding: var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
}

/* Right-align all numeric columns */
.data-table td.numeric,
.data-table th.numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
```

### 6.3 Buttons

```css
/* Primary action */
.btn-primary {
  background: var(--accent-primary);
  color: var(--text-primary);  /* #f1f5f9 — never use pure #ffffff */
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 500;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  transition: background 150ms ease;
}
.btn-primary:hover {
  background: var(--accent-hover);
}
.btn-primary:focus-visible {
  outline: 2px solid var(--accent-hover);
  outline-offset: 2px;
}

/* Secondary / ghost action */
.btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 400;
  padding: 8px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 150ms ease;
}
.btn-secondary:hover {
  color: var(--text-primary);
  border-color: var(--border-strong);
  background: var(--bg-elevated);
}
.btn-secondary:focus-visible {
  outline: 2px solid var(--border-strong);
  outline-offset: 2px;
}
```

### 6.3.1 Focus States

All interactive elements must have visible focus indicators for keyboard navigation and accessibility.

```css
/* Default focus ring for inputs and interactive elements */
:focus-visible {
  outline: 2px solid var(--border-strong);
  outline-offset: 2px;
}

/* Accent focus ring for primary actions */
.btn-primary:focus-visible,
a:focus-visible {
  outline-color: var(--accent-hover);
}

/* Remove default outline only when focus-visible handles it */
:focus:not(:focus-visible) {
  outline: none;
}
```

Never remove focus indicators entirely. Use `focus-visible` (not `focus`) so mouse users aren't distracted while keyboard users retain navigation cues.

### 6.4 Tags / Badges

```css
.tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 400;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  background: var(--accent-muted);
  color: var(--accent-hover);
  border: 1px solid var(--accent-border);
}

/* Variant: neutral */
.tag-neutral {
  background: rgba(148, 163, 184, 0.06);
  color: var(--text-secondary);
  border-color: var(--border-default);
}
```

### 6.5 Financial Value Display

```css
/* Large headline number (e.g. total net worth) */
.value-headline {
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

/* Inline value with change indicator */
.value-change {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
.value-change.positive { color: var(--positive); }
.value-change.negative { color: var(--negative); }
.value-change.neutral  { color: var(--neutral); }
```

### 6.6 Charts

When implementing charts (Recharts, Chart.js, D3, etc.):

- **Background:** Transparent (inherits card bg)
- **Grid lines:** `var(--border-subtle)` — barely visible
- **Axis labels:** `mono-label` style (10px, 400, `--text-tertiary`)
- **Primary data line/area:** `var(--accent-primary)` with 8% opacity fill
- **Tooltip background:** `var(--bg-elevated)` with `var(--border-default)` border
- **Allocation pie/donut:** Use the emerald scale for equity-heavy, slate scale for bonds/cash, blue for alternatives:
  - Equities: `#10b981`, `#34d399`, `#6ee7b7`
  - Bonds: `#64748b`, `#94a3b8`, `#cbd5e1`
  - Cash: `#475569`
  - Alternatives: `#3b82f6`, `#60a5fa`

---

## 7. Iconography

Use **Lucide icons** (`lucide-react` or SVG sprites). They are consistent with the monospace, clean aesthetic.

Preferred icon mappings:

| Concept | Icon | Notes |
|---|---|---|
| Accounts | `landmark` | Bank building |
| Holdings | `layers` | Stacked layers |
| Allocation | `pie-chart` | Target vs actual |
| Sync | `refresh-cw` | Data refresh |
| Snapshot | `camera` | Point-in-time capture |
| Settings | `sliders-horizontal` | Prefer over gear |
| Growth / Gain | `trending-up` | With emerald color |
| Loss | `trending-down` | With red color |
| Add | `plus` | In a circle for primary actions |
| Dashboard | `layout-dashboard` | Overview page |

Icon size: `16px` inline with text, `20px` in buttons, `24px` in navigation.

---

## 8. Motion & Transitions

Keep animations minimal and functional. This is a data tool, not a marketing site.

```css
/* Standard transition for interactive elements */
transition: all 150ms ease;

/* Page/panel entrance (use sparingly) */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}
.animate-in {
  animation: fadeIn 200ms ease-out;
}
```

- **No bouncing, no spring physics, no parallax.**
- **Hover states:** Subtle color shifts only. No scale transforms on cards.
- **Loading states:** Use a simple pulse or skeleton with `var(--bg-elevated)`.
- **Number transitions:** If animating values (e.g. net worth counter), use `150ms` duration with easing.

---

## 9. Dark Mode First

TenetFolio is **dark mode by default.** The palette, contrast ratios, and brand colors are all optimized for dark backgrounds.

If light mode is added later, treat it as a theme override using `[data-theme="light"]` CSS selectors and the light palette defined in section 4.3.

---

## 10. Do's and Don'ts

### Do

- Use `font-variant-numeric: tabular-nums` for all financial data so columns align
- Right-align all numeric columns in tables
- Always show currency signs and +/- on changes
- Use the grid mark icon at sizes where it reads clearly (≥16px)
- Keep card borders at `1px solid var(--border-subtle)` — almost invisible
- Use `JetBrains Mono` everywhere — consistency over variety

### Don't

- Don't use gradients on backgrounds (flat colors only)
- Don't use box-shadow for elevation — use border opacity differences instead (e.g. `--border-subtle` for default, `--border-default` for raised)
- Don't use more than 2 colors from the emerald scale in a single view
- Don't round financial numbers — always show full precision (or 2 decimal places for currency)
- Don't use icons without labels on primary navigation items
- Don't introduce a second font family
- Don't use opacity below 0.5 for any text the user needs to read
