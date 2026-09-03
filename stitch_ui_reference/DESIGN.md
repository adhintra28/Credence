# Obsidian — High-Contrast Dark

## North Star: "Precision in Darkness"
Developer-grade dark UI. Near-black surfaces, high-contrast text, and precise accent colors. Clean, fast-feeling, and functional.

## Colors
- **Primary (`#a78bfa`):** Soft violet — interactive elements, links, focus rings.
- **Background (`#09090b`):** True near-black.
- **Tertiary (`#34d399`):** Emerald green — success states, positive indicators, code highlights.
- **Surface scale:** Zinc-based grays (`#0c0c0f` → `#27272a`). Very subtle increments.
- Red (`#ef4444`) for errors only. No decorative color use.

## Typography
- **All fonts:** Geist — modern, clean, developer-friendly.
- Tight letter-spacing on headings (-0.02em). Standard on body.
- `#fafafa` for primary text, `#a1a1aa` for secondary. High contrast always.

## Elevation
- Minimal shadows. Use border-based separation: `1px solid #27272a`.
- Active/hover states: subtle background shifts to next surface tier.
- Focus rings: `2px solid #a78bfa` with `2px offset`.

## Components
- **Buttons:** Primary = solid violet fill. Secondary = transparent + border. Ghost = text only, visible on hover.
- **Cards:** `surface_container` background, thin `outline_variant` border, 8px radius.
- **Inputs:** `surface_container` fill, `outline_variant` border, violet focus ring.
- **Code blocks:** `surface_container_lowest` background, monospace font.

## Rules
- Never use light backgrounds. Maintain zinc gray consistency.
- Borders over shadows for separation. Keep the interface flat and precise.
- Accent colors for function, never decoration.