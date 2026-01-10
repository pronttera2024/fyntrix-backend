from fastapi import FastAPI

from .routers import me


app = FastAPI(title="Fyntrix Auth/Profile Service", version="0.1.0")


@app.get("/health")
async def health():
    return {"ok": True}


app.include_router(me.router, prefix="/v1")
