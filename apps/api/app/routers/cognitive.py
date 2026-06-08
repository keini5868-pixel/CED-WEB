"""Router cognitivo — cerebro híbrido CED."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps.auth import require_user_id
from app.services.cognitive_router import route_message
from app.services.internal_knowledge import list_domains_public, search_internal_knowledge

router = APIRouter(prefix="/v1/cognitive", tags=["cognitive"])


class RouteBody(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    channel: str = Field(default="text", pattern="^(text|voice)$")
    confirm_pending: bool = False
    execute: bool = True


@router.post("/route")
def cognitive_route(
    body: RouteBody,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Clasifica intención y enriquece con cerebro interno, web o sistema avanzado."""
    result = route_message(
        user_id,
        body.text,
        channel=body.channel,  # type: ignore[arg-type]
        confirm_pending=body.confirm_pending,
        execute_side_effects=body.execute,
    )
    return result.to_dict()


@router.get("/domains")
def cognitive_domains(_user_id: str = Depends(require_user_id)) -> dict:
    """Catálogo de ramas del cerebro interno (premium)."""
    return {"domains": list_domains_public(), "total": len(list_domains_public())}


@router.get("/search")
def cognitive_search(
    q: str,
    limit: int = 5,
    user_id: str = Depends(require_user_id),
) -> dict:
    """Búsqueda directa en cerebro interno (debug/admin)."""
    hits = search_internal_knowledge(q, limit=min(limit, 10))
    return {
        "query": q,
        "hits": [
            {
                "domain_id": h.domain_id,
                "domain_label": h.domain_label,
                "title": h.title,
                "summary": h.summary,
                "confidence": h.confidence,
                "source": h.source,
            }
            for h in hits
        ],
    }
