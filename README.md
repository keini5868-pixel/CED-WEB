# Castillo Digital Web (CED SaaS)

Monorepo oficial de **CED Web** — migración desde desktop PyQt6 a SaaS en la nube.

> El proyecto legacy (`CED/`, `installer/`, `ced-backend/` en el repo anterior) **no se modifica** hasta el primer cobro Stripe en producción.

## Estructura

```
CED-WEB/
├── apps/
│   ├── web/          # Next.js 15 + Tailwind 4 + PWA
│   └── api/          # FastAPI + Stripe + Gemini proxy
├── packages/
│   ├── types/        # Tipos TS compartidos
│   ├── ui/           # Tokens diseño Tony Stark
│   └── config/       # TSConfig / ESLint base
├── docs/
├── MIGRATION_PLAN.md
└── PHASE0_REPORT.md
```

## Desarrollo local

### Requisitos

- Node.js 22+
- pnpm 9+
- Python 3.11+

### Instalación

```powershell
cd C:\Users\keini\OneDrive\Escritorio\CED-WEB
pnpm install
cd apps\api
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Variables de entorno

Copia `.env.example` → `apps/web/.env.local` y `apps/api/.env`.  
Guía detallada: `docs/ENV_SETUP.md`

### Ejecutar

```powershell
# Terminal 1 — API
pnpm dev:api

# Terminal 2 — Web
pnpm dev:web
```

- Web: http://localhost:3000  
- API: http://localhost:8000  
- Meta planes: http://localhost:8000/v1/meta  

## Roadmap

Ver `MIGRATION_PLAN.md` y `PHASE0_REPORT.md`.
