from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import vehicles
from app.auth import require_login
from app.timeline_import import extract_driving_segments, extract_raw_segments, import_segments

router = APIRouter(dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory="app/templates")


@router.get("/import/google-timeline")
def import_page(
    request: Request,
    imported: int | None = None,
    duplicates: int | None = None,
    skipped_non_driving: int | None = None,
    skipped_unparseable: int | None = None,
    error: str | None = None,
):
    result = None
    if imported is not None:
        result = {
            "imported": imported,
            "duplicates": duplicates or 0,
            "skipped_non_driving": skipped_non_driving or 0,
            "skipped_unparseable": skipped_unparseable or 0,
        }
    return templates.TemplateResponse("import_timeline.html", {"request": request, "result": result, "error": error})


@router.post("/import/google-timeline")
async def import_upload(file: UploadFile = File(...)):
    vehicle = vehicles.get_active_vehicle()
    if vehicle is None:
        return RedirectResponse(url="/settings?setup=1", status_code=303)

    raw_bytes = await file.read()
    try:
        raw_segments = extract_raw_segments(file.filename or "", raw_bytes)
    except Exception:
        return RedirectResponse(url="/import/google-timeline?error=parse", status_code=303)

    extracted = extract_driving_segments(raw_segments)
    result = import_segments(vehicle["id"], extracted["driving"])

    return RedirectResponse(
        url=(
            f"/import/google-timeline?imported={result['imported']}"
            f"&duplicates={result['duplicates']}"
            f"&skipped_non_driving={extracted['skipped_non_driving']}"
            f"&skipped_unparseable={extracted['skipped_unparseable']}"
        ),
        status_code=303,
    )
