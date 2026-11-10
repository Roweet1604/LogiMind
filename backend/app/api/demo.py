"""Local demo mode endpoint (decision 0029). 404 when demo mode is off; 403 for any request not from this machine."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.demo import DEMO_TENANT_ID, DEMO_TENANT_NAME, request_is_local

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/session", include_in_schema=False)
def demo_session(request: Request) -> dict:
    """The demo tenant's in-memory API key, so the local console can sign in without copying a key."""
    demo = request.app.state.demo
    if not demo.enabled:
        raise HTTPException(404, detail="demo mode is off")
    if not request_is_local(request):
        raise HTTPException(403, detail="demo mode answers only requests from this computer")
    return {"demo": True, "tenant_id": DEMO_TENANT_ID, "tenant_name": DEMO_TENANT_NAME, "api_key": demo.key,
            "note": "Synthetic demo data on a local development server."}
