# Routing Extension: web-dev

## Reviewers

### the Front-End Reviewer (senior-front-end)
- **Signals:** Front-end, CSS, UI components, design tokens, component library, styling, responsive design, web accessibility
- **Model:** opus
- **Effort:** Medium (escalates to High when combined with architecture)
- **Backstop:** the UX Reviewer (same plugin)
- **Agent file:** `agents/senior-front-end.md`

### the UX Reviewer (staff-ux)
- **Signals:** UX flow, user-facing feature, trust/clarity assessment, onboarding, user interaction, form design, error states
- **Model:** opus
- **Effort:** Low (escalates to Medium for full flow reviews)
- **Backstop:** the Staff Engineer (coordinator plugin — universal reviewer)
- **Agent file:** `agents/staff-ux.md`

## Project-Local Pairings
- `<web-app>`: the Front-End Reviewer primary, the UX Reviewer for UX flows, the Staff Engineer for architecture
- `<dashboard-app>`: the Front-End Reviewer primary, the UX Reviewer for UX, the Data Science Reviewer when data-science plugin enabled

(Replace the placeholders above with your actual project names; this file is the routing table consumed by `/review` and `/review-code` for reviewer routing.)
