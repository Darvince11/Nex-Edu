# 02 · Design system

The design system is defined once, in [web/src/app/globals.css](../../web/src/app/globals.css), as Tailwind 4
`@theme` tokens. Every page and module uses the tokens and the components in
[web/src/components/ui.tsx](../../web/src/components/ui.tsx) and [brand.tsx](../../web/src/components/brand.tsx).
A module that introduces its own colours, button styles or card styles fails review.

## 1. Colour

All brand values were sampled from the supplied logo (`web/public/brand/nex-edu-logo.png`), not invented.

| Token | Value | Source in logo | Use |
|---|---|---|---|
| `brand` | `#0C63D9` | Body of the N | Primary buttons, links, active nav, focus ring, selected states. White text on it is 5.5:1 (WCAG AA). |
| `brand-strong` | `#043DCC` | Foot of the N, the x | Hover and pressed states, active nav text in light mode |
| `brand-bright` | `#0794F7` | "Edu", divider bar | Accent text and icons on dark surfaces |
| `brand-sky` | `#03B8FD` | Top of the N gradient | Badge text on dark surfaces, chart highlight. Never body text on white (fails contrast). |
| `brand-navy` | `#042159` | Cap, "Nex" | Headings and info-alert text, dark-mode browser chrome, PDF table headers |
| `neutral-50 … 950` | Tailwind scale re-tinted to hue 260 | Navy | Text, borders, surfaces, dark-mode background. Greys are never pure grey. |

**Surfaces.** Page background is white. Cards are white with a `neutral-200` border. Tinted surfaces
(unread rows, selected rows, info alerts) use `brand/5`–`brand/10`. Dark mode uses `neutral-950` (deep navy)
for the page and `neutral-900` for cards.

**Status colours are semantic and stay off-brand on purpose.** Success is emerald, warning amber, error red.
Blue already means "in progress / under review" (`Badge tone="blue"`), so success can't also be blue without
users confusing "paid" with "pending". Status is never shown by colour alone: badges always carry a word.

**Gradients** appear only inside the logo image. No gradient backgrounds, buttons or headers.

### Tokens still to add (Phase 2)

| Token | Proposed | Why |
|---|---|---|
| `brand-50` | `#EEF5FE` | "Very light blue" content surface the brief asks for, without relying on alpha blending |
| `--radius-control` / `--radius-card` | `0.375rem` / `0.75rem` | Today's values (`rounded-md`, `rounded-xl`) are repeated by hand in components |
| `--shadow-card` | Tailwind `shadow-sm` | One elevation for cards; modals use `shadow-xl`. No other shadows. |
| Chart palette | Sequential: navy → brand → bright → sky. Categorical: brand, amber-600, emerald-600, neutral-500, red-600 | Charts must read as part of the same system and pass contrast in both themes |

## 2. Typography

- **Font:** the system UI stack (Tailwind default `font-sans`). This is deliberate: no web-font download on
  slow mobile connections, and the CSP allows `font-src 'self'` only. Revisit only if the owner supplies a brand
  typeface with a licence for self-hosting.
- **Scale:** page title `text-2xl font-semibold tracking-tight`; card title `font-medium`; body `text-sm`/`text-base`;
  hints `text-xs text-neutral-500`. Numbers in tables and stats use `tabular-nums`.

## 3. Layout and components

| Element | Rule |
|---|---|
| App shell | White sidebar (15rem) with the full logo, school name below it, then the nav. Top bar with school, roles, inbox, switch-school, sign out. On phones: the logo mark plus a Menu disclosure. |
| Sidebar choice | **White**, not dark blue. A dark sidebar would need the dark logo variant in light mode and makes the brand blue active state lower contrast. |
| Platform vs school identity | The Nex Edu logo always sits in the sidebar and on sign-in screens. A school's own logo appears in the top bar, on its public admission page and on its report cards and receipts. A school never replaces the Nex Edu mark or the app colours. |
| School-level branding (permitted) | Logo upload (PNG/JPEG/SVG, max 1 MB, re-encoded server-side), optional document accent colour used **only** on PDFs and the public admission page, motto, report-card footer. |
| Buttons | `Button` variants: primary (brand), secondary (outline), danger (red), ghost. One primary button per view. |
| Forms | `Field` + `Input`/`Select`/`Textarea`. Labels always visible; errors in an `Alert tone="error"` with `role="alert"`. |
| States | Every data view handles loading (`Loading`), empty (`Empty`), error (`ErrorText`) and **permission denied** (new `Forbidden` component, Phase 2). |
| Modals | Native `<dialog>` (`Modal`), which gives focus trapping and Escape for free. |

## 4. Accessibility and responsiveness

- WCAG 2.2 AA contrast for text and controls in both themes. Focus is always visible (`ring-brand/30` plus border).
- Everything is reachable by keyboard; no click-only `div`s.
- Layouts work from 360 px wide. Tables scroll horizontally inside their card, never the page.
- Dark mode follows the OS (`prefers-color-scheme`). The logo swaps to a white-navy variant.

## 5. Verification (each phase)

1. `grep` the web source for raw colour classes outside the token set (`emerald`, `green`, `sky`, hex values).
   Allowed: semantic status tones in `ui.tsx` and `attendance/page.tsx`.
2. Screenshot review of the shell, a form, a table and a modal in light and dark mode at 360 px and 1280 px.
3. Automated accessibility check (axe via Playwright) on each new page, from Phase 2.
