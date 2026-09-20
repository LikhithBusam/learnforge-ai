# Frontend Architecture Documentation (Phase 12)

## 1. Overview
The frontend of the **AI Study Companion** is a production React + TypeScript application built on **Vite**, housed within the monorepo at `packages/web`. It functions strictly as an interactive consumer and client of the FastAPI modular monolith, visualizing domain state without replicating backend business logic.

---

## 2. Directory Structure

```text
packages/web/
├── src/
│   ├── components/       # Reusable navigation, auth modals, and UI primitives
│   │   ├── Navigation.tsx
│   │   └── AuthModal.tsx
│   ├── context/          # Client-side authentication and session state
│   │   └── AuthContext.tsx
│   ├── features/         # Domain workspace screens
│   │   ├── Dashboard.tsx
│   │   ├── ProjectWorkspace.tsx
│   │   └── AdminDashboard.tsx
│   ├── services/         # Centralized API client and SSE streaming
│   │   └── api.ts
│   ├── types/            # TypeScript definitions matching backend Pydantic DTOs
│   │   └── index.ts
│   ├── App.tsx           # Application root and view router
│   ├── main.tsx          # DOM mount entrypoint
│   ├── index.css         # Modern design system (glassmorphic dark theme)
│   └── vite-env.d.ts     # Vite environment types
├── index.html            # HTML template with Google Fonts (Inter & Outfit)
├── tsconfig.json         # Strict TypeScript compiler configuration
├── vite.config.ts        # Vite build & proxy settings
└── package.json          # Dependencies and build scripts
```

---

## 3. Key Architectural Decisions

- **Zero Duplicated Logic**: Bayesian Knowledge Tracing (BKT), growth trajectories, adaptive recommendation ranking, citation validation, and analytics rollups remain 100% backend-authoritative.
- **SSE Stream Handling**: The AI Tutor interface handles Server-Sent Events (`text/event-stream`), reading tokens progressively for real-time response rendering and surfacing structured citation chips.
- **Data Minimization & Privacy**: User listings, admin inspection, and error dialogues display sanitized DTOs without leaking password hashes, session tokens, or API credentials.
- **Design System**: A sleek, dark glassmorphism aesthetic built with custom CSS variables, accessible color contrasts, smooth micro-transitions, and responsive typography (Inter & Outfit).
