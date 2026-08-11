"""Crea Product + Price Stripe para CED Cierre ($20/mes).

Uso (con STRIPE_SECRET_KEY live o test en el entorno):

  cd apps/api
  python -m scripts.ensure_stripe_cierre

Imprime el price_id para copiar a STRIPE_PRICE_CIERRE en Railway.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.stripe_billing import ensure_stripe_plan_price  # noqa: E402


def main() -> int:
    price_id = ensure_stripe_plan_price("cierre")
    print(f"OK CED Cierre price_id={price_id}")
    print("Copia a Railway (API): STRIPE_PRICE_CIERRE=" + price_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
