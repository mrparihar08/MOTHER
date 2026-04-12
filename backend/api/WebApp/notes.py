from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.api.database import get_db
from backend.api.models.vitya import Note
from backend.api.schemas.vitya import NoteCreate, NoteUpdate, NoteResponse

router = APIRouter()


# ---------------------------
# GET ALL NOTES
# ---------------------------
@router.get("/", response_model=List[NoteResponse])
def get_notes(db: Session = Depends(get_db)):
    notes = db.query(Note).order_by(Note.id.desc()).all()
    return notes


# ---------------------------
# CREATE_NOTE
# ---------------------------
@router.post("/", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(note: NoteCreate, db: Session = Depends(get_db)):
    content = note.content.strip()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Note content cannot be empty",
        )

    new_note = Note(content=content)

    db.add(new_note)
    db.commit()
    db.refresh(new_note)

    return new_note


# ---------------------------
# UPDATE_NOTE
# ---------------------------
@router.put("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: int,
    note_data: NoteUpdate,
    db: Session = Depends(get_db),
):
    note = db.query(Note).filter(Note.id == note_id).first()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    update_data = note_data.model_dump(exclude_unset=True)

    if "content" in update_data:
        content = update_data["content"].strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Note content cannot be empty",
            )
        note.content = content

    db.commit()
    db.refresh(note)

    return note


# ---------------------------
# DELETE_NOTE
# ---------------------------
@router.delete("/{note_id}", status_code=status.HTTP_200_OK)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    db.delete(note)
    db.commit()

    return {"message": "Note deleted successfully"}