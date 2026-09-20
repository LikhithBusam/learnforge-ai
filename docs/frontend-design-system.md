# Frontend Design System & Tokens Reference (Phase 12.1)

## 1. Design Principles
- **Restrained & Professional**: Minimalist, clean dark-theme palette inspired by modern developer productivity platforms (Linear, Cursor, Vercel).
- **Zero Distracting Elements**: No neon colors, no excessive glassmorphism, no childish illustrations, and no decorative fake metrics.
- **Visual Hierarchy**: High contrast for reading text, clear elevation boundaries with 1px subtle borders (`rgba(255, 255, 255, 0.07)` to `0.12`).

---

## 2. Spacing Scale

All margins, paddings, and gaps strictly use the standardized 4px/8px-based scale:

| Token | Value | Purpose |
| :--- | :--- | :--- |
| `--space-1` | `4px` | Fine adjustments, icon gaps |
| `--space-2` | `8px` | Tight inline element gaps |
| `--space-3` | `12px` | Standard input/card inner padding |
| `--space-4` | `16px` | Section gaps, standard padding |
| `--space-5` | `20px` | Metric card padding |
| `--space-6` | `24px` | Card padding, layout gutter |
| `--space-8` | `32px` | Page container padding |
| `--space-12` | `48px` | Large hero/section margin |

---

## 3. Surface & Color Palette

```css
:root {
  --bg-app: #090d16;             /* Deep neutral background */
  --bg-subtle: #0d1322;          /* Sidebar and topbar background */
  --surface-base: #111827;       /* Card and table surface */
  --surface-elevated: #162032;   /* Interactive / elevated surfaces */
  --surface-hover: #1e2b44;      /* Hover states */

  --text-primary: #f8fafc;       /* Highest contrast headers and body */
  --text-secondary: #94a3b8;     /* Supporting descriptive text */
  --text-muted: #64748b;         /* Labels, metadata, dates */

  --border-subtle: rgba(255, 255, 255, 0.07);
  --border-default: rgba(255, 255, 255, 0.12);
  --border-strong: rgba(255, 255, 255, 0.20);
  --border-focus: #6366f1;

  --accent-primary: #4f46e5;     /* Professional indigo brand accent */
  --accent-hover: #4338ca;
  --accent-subtle: rgba(79, 70, 229, 0.12);
  --accent-border: rgba(99, 102, 241, 0.35);
  --accent-text: #818cf8;
}
```

---

## 4. Typography Scale

- **Display**: Outfit, 28px (`1.75rem`), Bold (700)
- **Heading 1**: Outfit, 22px (`1.375rem`), Semi-bold (600)
- **Heading 2**: Outfit, 18px (`1.125rem`), Semi-bold (600)
- **Body Regular**: Inter, 14px (`0.875rem`), Regular (400), line-height 1.5
- **Metadata / Labels**: Inter, 11px–12px (`0.6875rem`–`0.75rem`), Medium (500)

---

## 5. Standard Component Guidelines

### Buttons (`.btn`)
- **Primary** (`.btn-primary`): Background `--accent-primary` (#4f46e5), white text. Used for main affirmative actions (Sign In, Create Project, Upload, Start Quiz).
- **Secondary** (`.btn-secondary`): Surface background with `--border-default`. Used for cancel, navigation, and secondary choices.
- **Sizes**: Default (38px height), Small `.btn-sm` (30px height), Large `.btn-lg` (44px height).

### Inputs (`.input`)
- Height 38px, background `--surface-base`, border `--border-default`.
- Focused state: Outline offset with 1px border ring `--border-focus` (#6366f1).
- Error state: `.input-error` with `--danger` (#ef4444).
