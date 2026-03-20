# BimAtlas Style Guide

Use this file as the UI source of truth for agents implementing frontend work.

## Visual Direction

- Product tone: Professional, technical, architectural
- Brand keywords: Precision, structure, clarity, spatial
- Accessibility target: WCAG 2.1 AA compliance

## Design Tokens

```css
:root {
  /* --- Brand: Deep Slate & Architectural Bronze --- */
  --color-brand-500: #1e293b;
  --color-brand-400: #334155;
  --color-brand-gradient-start: #0f172a;
  --color-brand-gradient-end: #334155;

  /* --- Backgrounds: Warm Sand & Stone --- */
  --color-bg-canvas: #f8f8f2;
  --color-bg-surface: #ffffff;
  --color-bg-elevated: #f1f1eb;

  /* --- Typography: Technical Ink --- */
  --color-text-primary: #0f172a;
  --color-text-secondary: #64748b;
  --color-text-muted: #94a3b8;

  /* --- Borders & Geometry --- */
  --color-border-subtle: #e2e2da;
  --color-border-default: #cbd5e1;
  --color-border-strong: #1e293b;

  /* --- Functional --- */
  --color-action-primary: #334155;
  --color-warning: #b45309;
  --color-danger: #991b1b;
  --color-info: #475569;
  --color-success: #334155;

  /* --- IFC & Graph --- */
  --color-graph-node: #78350f;
  --color-graph-edge: #d4d4ce;
}
```

## Layout and Components

- Prefer semantic HTML before generic wrappers
- Use Flexbox for one-dimensional and Grid for two-dimensional layouts
- Use `gap` for spacing in flex/grid containers
- Keep selector specificity low and avoid `!important`

## Typography

- Primary font: System UI stack (fallback chain)
- Secondary font: Monospace for technical data
- Heading scale: 1.25 ratio
- Body scale: 1rem base

## Interaction Patterns

- Required states: `:hover`, `:focus-visible`, `:active`, `:disabled`
- Form behavior: Validate on blur, submit on enter
- Motion: Subtle transitions, 150-300ms duration

## Do Not

- Introduce visual styles outside this token system without updating this file
- Add inaccessible color contrast or remove keyboard focus visibility
- Use inline styles except for truly dynamic values
