"""
espresso API entry point.

Run with: python main.py   (or: uvicorn main:app --port 8000)
Docs at: http://localhost:8000/docs
"""

import logging
import os

from dotenv import load_dotenv

# Load environment variables BEFORE any local imports: the provider is resolved from them.
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from api.routes import router as api_router

app = FastAPI(
    title="espresso API",
    description="Turns an open-access medical paper into a verified scrollable explainer",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS.
#
# This runs on one machine for one reader, so the only callers that exist are local. The
# upstream project's public hosts are gone with the rest of its deployment; keeping them
# would allow a site nobody controls any more to read this API.
#
# The port has to be a wildcard rather than 3000. When something else already holds 3000,
# the launcher moves the web app to 3001, and a hardcoded origin then blocks every request
# the page makes: the app loads, looks fine, and lists nothing.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\[::1\]):\d{1,5}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
async def _seed() -> None:
    """A fresh install opens on a library, not an empty page."""
    import store

    try:
        store.seed_examples()
    except Exception:
        logging.getLogger(__name__).exception("Could not install the example explainers")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to API documentation."""
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))

    uvicorn.run("main:app", host=host, port=port)
