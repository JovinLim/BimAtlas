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
  /* --- Brand: Deep Slate & Architectural Bronze --- */
  /* Used for the Sidebar (like the reference) and primary navigation */
  --color-brand-500: #1e293b; /* Deep Navy Slate - The "Anchor" color */
  --color-brand-400: #334155; /* Mid-tone Slate for secondary nav elements */
  --color-brand-gradient-start: #0f172a;
  --color-brand-gradient-end: #334155;

  /* --- Backgrounds: Warm Sand & Stone --- */
  /* Mimics the reference's clean feel without being "cold" */
  --color-bg-canvas: #f8f8f2; /* Warm Sand - The base background layer */
  --color-bg-surface: #ffffff; /* Pure White - For the rounded cards/panels */
  --color-bg-elevated: #f1f1eb; /* Soft Stone - For hover states and secondary tabs */

  /* --- Typography: Technical Ink --- */
  /* High contrast for headers, softer for metadata */
  --color-text-primary: #0f172a; /* Near-Black - Sharp legibility for data */
  --color-text-secondary: #64748b; /* Muted Slate - For labels like "Current MRR" */
  --color-text-muted: #94a3b8; /* Light Lead - For timestamps and placeholders */

  /* --- Borders & Geometry: Technical Graphite --- */
  /* Crucial for the "Friendly" feel - Use border-radius: 12px to 16px */
  --color-border-subtle: #e2e2da; /* Very light stone for card outlines */
  --color-border-default: #cbd5e1; /* For input fields and dividers */
  --color-border-strong: #1e293b; /* For active focus states */

  /* --- Functional: Muted Professional Tones --- */
  /* Replaces the bright blue/orange with your custom palette */
  --color-action-primary: #334155;
  --color-warning: #b45309; /* Deep Amber - For structural warnings */
  --color-danger: #991b1b; /* Crimson Ink - For critical errors */
  --color-info: #475569; /* Slate - For neutral technical info */

  /* --- IFC & Graph Specifics --- */
  /* Avoiding green to prevent the "Sustainability Project" look */
  --color-success: #334155; /* Slate - Used for "Verified" or "Pass" (Minimalist) */
  --color-graph-node: #78350f; /* Bronze - For selected IFC elements */
  --color-graph-edge: #d4d4ce; /* Light Stone - For relationship lines */
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
