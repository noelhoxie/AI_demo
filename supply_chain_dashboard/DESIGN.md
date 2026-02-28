# Design guide — professional, minimal dashboard

This app follows a **text-only, minimal** UI: no icons, clear hierarchy, limited palette, and consistent spacing. Use these patterns when adding or editing pages so the app stays professional and easy to scan.

---

## Design principles

1. **No icons** — Labels, headings, and text only. No icon fonts, SVGs, or emoji in the UI.
2. **Limited palette** — Use CSS variables from `style.css` (`--color-primary`, `--color-bg`, `--color-card`, `--color-text-muted`, etc.). Avoid new colors.
3. **Consistent spacing** — Use the scale: `--space-8`, `--space-12`, `--space-16`, `--space-24`, `--space-32` (4px base).
4. **Single font** — `var(--font-sans)` everywhere; one weight for body (400/500), 600 for headings and KPI values.

---

## Page templates (patterns)

### 1. Standard content page (extends `dashboard_base.html`)

- **Block `content`**: One `<section class="panel active">` with `<div class="panel-content">`.
- **Intro**: Optional `<p class="sim-intro">` — one short sentence, muted color.
- **KPIs**: `<div class="kpi-row">` with `<div class="kpi-card">` per metric. Each card: `<div class="label">`, `<div class="value">`, optional `<div class="target">`.
- **Charts**: `<div class="charts-row">` with `<div class="chart-card">`, `<h3>`, `<div class="chart-container">`, `<canvas>`.
- **Comments**: Reuse the `comments-section` pattern from existing pages.

### 2. Filters bar

- Wrap in `<div class="filters-bar">`.
- Each control: `<div class="filter-group">` with `<label>` and `<select>` or `<input>`.
- Use `<span class="filter-count">` for “Showing X of Y”.
- Buttons: `btn btn-secondary btn-refresh` for Refresh; `btn btn-primary` for primary actions. Text only (e.g. “Refresh”, “Apply”).

### 3. Data table

- `<table class="data-table">` with `<thead>` and `<tbody>`.
- Headers: `<th data-sort data-sort-key="...">Label <span class="sort-indicator"></span></th>` if sortable.
- No icons in headers or cells; use text (“A–Z”, “High–Low”) or a single character for sort if needed.

### 4. Empty and loading states

- **Empty**: `<p class="empty-state">No items match the current filters.</p>` (or similar short sentence).
- **Loading**: `<div class="loading">Loading…</div>` or use `panel-content is-loading` on the panel. No spinners; text only.

### 5. Modals

- Overlay: `modal-overlay` with `modal-dialog`.
- Title: `<h3>`. Form: `form-group`, `form-row` where needed. Actions: `modal-actions` with `btn btn-secondary` (Cancel) and `btn btn-primary` (Save/Submit).
- Message: `modal-message` with optional `.error` or `.success`. No icons.

### 6. Buttons and links

- Primary action: `btn btn-primary` — solid background, white text.
- Secondary: `btn btn-secondary` — border, muted text.
- All buttons must have visible text (e.g. “Save”, “Cancel”, “Refresh”). No icon-only buttons.

### 7. Alerts and notices

- Short text plus background color (e.g. light red for errors, light green for success). Use existing classes like `sim-message`, `modal-message.error`, or a small inline notice. No icons.

---

## File and structure checklist

- [ ] New pages extend `dashboard_base.html` and use `section="..."` for nav.
- [ ] No Font Awesome, Material Icons, or inline SVG.
- [ ] Colors and spacing use `style.css` variables.
- [ ] KPI cards use `.kpi-card` with `.label`, `.value`, and optional `.target`.
- [ ] Chart titles are `<h3>` text above the chart; no icons in titles.
- [ ] Buttons and nav items are text-only and have clear labels.
- [ ] Empty and loading states are text-only.

---

## Customizing per brand

- **Primary color**: Overridden in templates with `--color-primary: {{ company.primary_color }}` (from `company.py`). Keep a single primary for nav active state and primary buttons.
- **Font**: Change `--font-sans` in `:root` if needed; keep one family for the whole app.
- **Shadows**: `--shadow` and `--shadow-card` are kept light for a minimal look; avoid adding heavier shadows.

Keeping to these templates and the checklist will keep the app professional, minimal, and consistent.
