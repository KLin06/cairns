from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.trails import router as trails_router

app = FastAPI(title="Trail Conditions API")

# Local dev only - client (Vite, port 5173) and server (FastAPI, port 8000)
# run as separate processes with no reverse proxy in front yet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(trails_router)


@app.get("/health")
def health():
    return {"status": "ok"}
