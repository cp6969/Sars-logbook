import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth import NotAuthenticated
from app.routers import auth_routes, export_routes, import_routes, pages, trip_api

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="SARS Vehicle Logbook")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(pages.router)
app.include_router(trip_api.router)
app.include_router(export_routes.router)
app.include_router(import_routes.router)


@app.exception_handler(NotAuthenticated)
async def handle_not_authenticated(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse("app/static/manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        "app/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )
