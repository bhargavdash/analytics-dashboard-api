from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Analytics Dashboard ADK", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "adk"}


# Import and include routers here later 
# from app.api import stream, history 
# app.include_router(stream.router, prefix="/api/v1")
# app.include_router(history.router, prefix="/api/v1")

