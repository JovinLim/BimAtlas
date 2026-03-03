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

## Color scheme template (fill for new projects)

Use semantic tokens first, then point those tokens to actual palette values:

```css
:root {
  /* Brand */
  --color-brand-500: <fill>;
  --color-brand-400: <fill>;

  /* Surfaces */
  --color-bg-canvas: <fill>;
  --color-bg-surface: <fill>;
  --color-bg-elevated: <fill>;

  /* Text */
  --color-text-primary: <fill>;
  --color-text-secondary: <fill>;
  --color-text-muted: <fill>;

  /* Borders */
  --color-border-subtle: <fill>;
  --color-border-default: <fill>;
  --color-border-strong: <fill>;

  /* States */
  --color-success: <fill>;
  --color-warning: <fill>;
  --color-danger: <fill>;
  --color-info: <fill>;
}
```

Token usage preference:
- `background`: use `--color-bg-*`
- `color`: use `--color-text-*`
- `border-color`: use `--color-border-*`
- `interactive/focus/active`: use brand or state tokens

## Current app color scheme (BimAtlas)

Use these values for this repository unless a design update changes them:

```css
:root {
  --color-brand-500: #ff8866;
  --color-brand-400: #ffaa88;
  --color-brand-gradient-start: #ff6644;
  --color-brand-gradient-end: #ff9966;

  --color-bg-canvas: #12121e;
  --color-bg-surface: #1a1a2e;
  --color-bg-elevated: #1e1e30;

  --color-text-primary: #e0e0e0;
  --color-text-secondary: #ccc;
  --color-text-muted: #888;

  --color-border-subtle: rgba(255, 255, 255, 0.06);
  --color-border-default: rgba(255, 255, 255, 0.1);
  --color-border-strong: rgba(255, 136, 102, 0.3);

  --color-warning: #c9a227;
  --color-danger: #ff6b6b;
  --color-danger-soft: #ee8888;
  --color-info: #87ceeb;
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
