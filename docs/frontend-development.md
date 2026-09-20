# Frontend Development Guide (Phase 12)

## 1. Prerequisites
- Node.js 18+ (tested with Node.js 22.20.0)
- npm 10+ (tested with npm 10.9.3)

---

## 2. Local Setup & Execution

From the repository root or inside `packages/web`:

```powershell
# Navigate to web package
cd packages/web

# Install dependencies
npm.cmd install

# Start development server
npm.cmd run dev
```

The dev server runs on `http://localhost:3000` and automatically proxies `/api` calls to `http://127.0.0.1:8000`.

---

## 3. Production Build

To validate TypeScript compilation and create the optimized production bundle:

```powershell
npm.cmd run build
```

Bundle output is placed into `packages/web/dist/` ready for static deployment (Cloudflare Pages, Vercel, Netlify, or S3/CloudFront).
