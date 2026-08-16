from datetime import date, datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from app import vehicles
from app.auth import require_login
from app.config import settings as app_settings
from app.export_sars import build_excel_report, build_report_data, tax_year_bounds

router = APIRouter(dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory="app/templates")


def _resolve_range(start: str | None, end: str | None):
    if start and end:
        return (
            datetime.strptime(start, "%Y-%m-%d").date(),
            datetime.strptime(end, "%Y-%m-%d").date(),
        )
    return tax_year_bounds(date.today(), app_settings.tax_year_start_month, app_settings.tax_year_start_day)


@router.get("/export")
def export_select(request: Request):
    vehicle = vehicles.get_active_vehicle()
    tax_start, tax_end = tax_year_bounds(
        date.today(), app_settings.tax_year_start_month, app_settings.tax_year_start_day
    )
    return templates.TemplateResponse(
        "export_select.html", {"request": request, "vehicle": vehicle, "tax_start": tax_start, "tax_end": tax_end}
    )


@router.get("/export/html")
def export_html(request: Request, start: str | None = None, end: str | None = None):
    vehicle = vehicles.get_active_vehicle()
    start_date, end_date = _resolve_range(start, end)
    data = build_report_data(vehicle, start_date, end_date)
    return templates.TemplateResponse("export_report.html", {"request": request, **data})


@router.get("/export/xlsx")
def export_xlsx(start: str | None = None, end: str | None = None):
    vehicle = vehicles.get_active_vehicle()
    start_date, end_date = _resolve_range(start, end)
    data = build_report_data(vehicle, start_date, end_date)
    content = build_excel_report(data)
    filename = f"sars-logbook-{start_date.isoformat()}-to-{end_date.isoformat()}.xlsx"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
