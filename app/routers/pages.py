from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import trips as trips_module
from app import vehicles
from app.auth import require_login
from app.config import settings as app_settings
from app.export_sars import current_odometer, tax_year_bounds

router = APIRouter(dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory="app/templates")


def _active_vehicle_or_none():
    return vehicles.get_active_vehicle()


@router.get("/")
def root():
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request):
    vehicle = _active_vehicle_or_none()
    if vehicle is None:
        return RedirectResponse(url="/settings?setup=1", status_code=303)

    open_trip = trips_module.get_open_trip(vehicle["id"])
    pending_count = trips_module.count_pending_review(vehicle["id"])

    tax_start, tax_end = tax_year_bounds(
        date.today(), app_settings.tax_year_start_month, app_settings.tax_year_start_day
    )
    odometer = current_odometer(vehicle, trips_module.list_trips(vehicle["id"], end_date=tax_end))
    recent_trips = trips_module.list_trips(vehicle["id"])[-10:][::-1]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "vehicle": vehicle,
            "open_trip": open_trip,
            "pending_count": pending_count,
            "current_odometer": odometer,
            "recent_trips": recent_trips,
        },
    )


@router.get("/trip/live")
def trip_live(request: Request, resume: str | None = None):
    vehicle = _active_vehicle_or_none()
    if vehicle is None:
        return RedirectResponse(url="/settings?setup=1", status_code=303)
    return templates.TemplateResponse(
        "trip_live.html", {"request": request, "vehicle": vehicle, "resume_trip_id": resume}
    )


@router.get("/trips")
def trip_list(request: Request, category: str | None = None):
    vehicle = _active_vehicle_or_none()
    if vehicle is None:
        return RedirectResponse(url="/settings?setup=1", status_code=303)
    all_trips = trips_module.list_trips(vehicle["id"], category=category)[::-1]
    return templates.TemplateResponse(
        "trip_list.html", {"request": request, "vehicle": vehicle, "trips": all_trips, "category": category}
    )


@router.get("/trips/{trip_id}")
def trip_detail(request: Request, trip_id: str):
    trip = trips_module.get_trip(trip_id)
    if trip is None:
        return RedirectResponse(url="/trips", status_code=303)
    return templates.TemplateResponse("trip_edit.html", {"request": request, "trip": trip})


@router.post("/trips/{trip_id}/update")
def trip_update(
    trip_id: str,
    category: str = Form(...),
    purpose: str = Form(""),
    odometer_open: str = Form(""),
    odometer_close: str = Form(""),
):
    trips_module.update_trip(
        trip_id,
        category=category,
        purpose=purpose or None,
        odometer_open=float(odometer_open) if odometer_open else None,
        odometer_close=float(odometer_close) if odometer_close else None,
        sync_status="synced",
    )
    return RedirectResponse(url=f"/trips/{trip_id}", status_code=303)


@router.post("/trips/{trip_id}/delete")
def trip_delete(trip_id: str):
    trips_module.delete_trip(trip_id)
    return RedirectResponse(url="/trips", status_code=303)


@router.get("/settings")
def settings_page(request: Request, setup: int = 0):
    vehicle = _active_vehicle_or_none()
    owner_settings = vehicles.get_settings()
    return templates.TemplateResponse(
        "settings.html", {"request": request, "vehicle": vehicle, "owner_settings": owner_settings, "setup": setup}
    )


@router.post("/settings/vehicle")
def settings_vehicle(
    registration: str = Form(...),
    make: str = Form(""),
    model: str = Form(""),
    engine_capacity_cc: str = Form(""),
    tax_year_opening_odometer: float = Form(...),
    tax_year_start_date: str = Form(...),
):
    vehicle = _active_vehicle_or_none()
    cc = int(engine_capacity_cc) if engine_capacity_cc else None
    if vehicle is None:
        vehicles.create_vehicle(
            registration, make or None, model or None, cc, tax_year_opening_odometer, tax_year_start_date
        )
    else:
        vehicles.update_vehicle(
            vehicle["id"],
            registration=registration,
            make=make or None,
            model=model or None,
            engine_capacity_cc=cc,
            tax_year_opening_odometer=tax_year_opening_odometer,
            tax_year_start_date=tax_year_start_date,
        )
    return RedirectResponse(url="/settings", status_code=303)


@router.post("/settings/owner")
def settings_owner(owner_display_name: str = Form(...)):
    vehicles.update_owner_name(owner_display_name)
    return RedirectResponse(url="/settings", status_code=303)
