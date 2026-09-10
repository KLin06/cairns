import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.trails import list_router as trail_list_router
from app.routers.trails import router as trails_router

app = FastAPI(title="Trail Conditions API")

# python -m uvicorn app.main:app --reload --port 8000
# Local dev (non-Docker) runs client (Vite, port 5173) and server (FastAPI,
# port 8000) as separate processes with no reverse proxy in front. The
# containerized client is served from its own origin (CLIENT_ORIGIN, e.g.
# the nginx container's published port) instead, so both are allowed.
_client_origins = ["http://localhost:5173"]
if os.environ.get("CLIENT_ORIGIN"):
    _client_origins.append(os.environ["CLIENT_ORIGIN"])

# Vercel gives every branch/PR its own preview URL (e.g.
# https://cairns-<hash>-<team>.vercel.app), which CLIENT_ORIGIN's single
# exact match can't cover - CLIENT_ORIGIN_REGEX is an optional second allow
# rule for that pattern, left unset (matches nothing) unless the deploy sets
# it. CLIENT_ORIGIN stays the production domain's exact match.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_client_origins,
    allow_origin_regex=os.environ.get("CLIENT_ORIGIN_REGEX"),
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(trail_list_router)
app.include_router(trails_router)


@app.get("/health")
def health():
    return {"status": "ok"}
