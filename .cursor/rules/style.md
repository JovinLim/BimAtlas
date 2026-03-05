---
description: HTML and CSS style guide for UI work
globs: **/*.{html,css,scss,svelte,ts,js,tsx,jsx}
alwaysApply: false
---

# HTML/CSS Style Guide (Reusable Template)

Use this guide when generating or editing UI markup and styles. This is designed to be reused in other projects by filling in the token template.

## HTML structure

- Prefer semantic elements (`header`, `main`, `section`, `nav`, `article`, `aside`, `footer`) before generic containers.
- Keep DOM shallow and meaningful; avoid unnecessary wrapper `div`s.
- Use classes for component intent, not element-only selectors for styling.
- Ensure accessibility basics: label form controls, preserve heading order, and add alt text for informative images.

## Layout preferences

- Default to Flexbox for one-dimensional layout (rows, columns, alignment, spacing).
- Use CSS Grid for two-dimensional layout (rows and columns together).
- Use `gap` for spacing in flex/grid containers (avoid margin-based spacing hacks).
- Avoid `position: absolute` for primary layout; use it only for overlays/popovers.

## Styling conventions

- Use design tokens (CSS variables) for color, spacing, typography, radius, and shadows.
- Use relative units (`rem`, `%`) by default; use px only when precision is required.
- Prefer mobile-first breakpoints with consistent naming and scale.
- Keep selector specificity low; avoid deep selector chains and `!important`.

Token usage preference:

- `background`: use `--color-bg-*`
- `color`: use `--color-text-*`
- `border-color`: use `--color-border-*`
- `interactive/focus/active`: use brand or state tokens

## Current app color scheme (BimAtlas)

Use these values for this repository unless a design update changes them:

```css
:root {
  /* Brand: Deep Slate & Bronze - Professional, precise, and timeless */
  --color-brand-500: #334155; /* Sophisticated Slate Blue-Gray */
  --color-brand-400: #64748b; /* Lighter Slate for secondary brand elements */
  --color-brand-gradient-start: #1e293b;
  --color-brand-gradient-end: #475569;

  /* Backgrounds: Warm Sand & Stone (The "Paper" layer) */
  --color-bg-canvas: #f7f7f2; /* Warm, high-end paper for the 3D viewport */
  --color-bg-surface: #ffffff; /* Clean white for panels */
  --color-bg-elevated: #efefe9; /* Soft warm gray for hover/active states */

  /* Typography: Architectural Ink */
  --color-text-primary: #0f172a; /* Near-black navy for sharp legibility */
  --color-text-secondary: #475569; /* Muted ink for secondary labels */
  --color-text-muted: #94a3b8; /* Light lead pencil for placeholders */

  /* Borders: Technical Graphite */
  --color-border-subtle: #e5e5e0;
  --color-border-default: #d4d4ce;
  --color-border-strong: #334155; /* Slate highlight for active selections */

  /* Functional: Muted Professional Tones */
  --color-warning: #b45309; /* Deep Amber/Bronze for warnings */
  --color-danger: #991b1b; /* Crimson Ink for errors */
  --color-danger-soft: #fee2e2;
  --color-info: #0369a1; /* Technical Blue for info */

  /* Graph/IFC Specifics */
  --color-success: #166534; /* Hunter Green (used only for "Pass" status) */
  --color-accent-bronze: #78350f; /* For specialized relationship lines */
}
```

## Component hygiene

- Co-locate styles with the component when practical.
- Favor reusable classes/patterns over copy-pasted one-off styles.
- Remove dead styles/classes when modifying components.
- Keep interaction states explicit (`:hover`, `:focus-visible`, `:disabled`, `:active`).

## Avoid

- Nested `div` stacks when one flex/grid parent solves layout.
- Inline styles except truly dynamic values that cannot be represented by classes/tokens.
- Magic numbers without a token or a brief comment for intent.
