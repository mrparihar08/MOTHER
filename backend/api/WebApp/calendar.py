from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.api.database import get_db
from backend.api.models.vitya import CalendarEvent, User
from backend.api.schemas.vitya import (
    CalendarEventCreate,
    CalendarEventUpdate,
    CalendarEventResponse,
)
from backend.api.auth import token_required

router = APIRouter()


# ---------------------------
# GET ALL CALENDAR EVENTS
# ---------------------------
@router.get("", response_model=List[CalendarEventResponse])
@router.get("/", response_model=List[CalendarEventResponse])
def get_calendar_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.user_id == current_user.id)
        .order_by(CalendarEvent.date.asc(), CalendarEvent.id.asc())
        .all()
    )
    return events


# ---------------------------
# CREATE CALENDAR EVENT
# ---------------------------
@router.post("", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=CalendarEventResponse, status_code=status.HTTP_201_CREATED)
def create_calendar_event(
    event: CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    title = event.title.strip()
    date = event.date.strip()

    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event title cannot be empty",
        )
    if not date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event date cannot be empty",
        )

    new_event = CalendarEvent(
        title=title,
        date=date,
        time=event.time.strip() if event.time else None,
        description=event.description.strip() if event.description else None,
        user_id=current_user.id,
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return new_event


# ---------------------------
# UPDATE CALENDAR EVENT
# ---------------------------
@router.put("/{event_id}", response_model=CalendarEventResponse)
def update_calendar_event(
    event_id: int,
    event_data: CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    event = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found",
        )

    update_data = event_data.model_dump(exclude_unset=True)

    if "title" in update_data:
        title = update_data["title"].strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event title cannot be empty",
            )
        event.title = title

    if "date" in update_data:
        date = update_data["date"].strip()
        if not date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event date cannot be empty",
            )
        event.date = date

    if "time" in update_data:
        event.time = update_data["time"].strip() if update_data["time"] else None

    if "description" in update_data:
        event.description = update_data["description"].strip() if update_data["description"] else None

    db.commit()
    db.refresh(event)

    return event


# ---------------------------
# DELETE CALENDAR EVENT
# ---------------------------
@router.delete("/{event_id}", status_code=status.HTTP_200_OK)
def delete_calendar_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(token_required),
):
    event = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found",
        )

    db.delete(event)
    db.commit()

    return {"message": "Calendar event deleted successfully"}
