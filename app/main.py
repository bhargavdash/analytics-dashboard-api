from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import stream, schema, conversations
from app.db.app_store import init_db

app = FastAPI(title="Analytics Dashboard ADK", version="0.1.0")

# Create the app-state tables (conversations/turns) on boot if they don't exist.
init_db()

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

app.include_router(stream.router, prefix="/api/v1")
app.include_router(schema.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")


