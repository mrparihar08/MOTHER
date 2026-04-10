from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import SessionLocal
from models.vitya import Note
from schemas.vitya import NoteCreate, NoteUpdate, NoteResponse

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=List[NoteResponse])
def get_notes(db: Session = Depends(get_db)):
    return db.query(Note).order_by(Note.id.desc()).all()


@router.post("/", response_model=NoteResponse)
def create_note(note: NoteCreate, db: Session = Depends(get_db)):
    content = note.content.strip()

    if not content:
        raise HTTPException(status_code=400, detail="Note content cannot be empty")

    new_note = Note(content=content)
    db.add(new_note)
    db.commit()
    db.refresh(new_note)
    return new_note


@router.put("/{note_id}", response_model=NoteResponse)
def update_note(note_id: int, note_data: NoteUpdate, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    content = note_data.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Note content cannot be empty")

    note.content = content
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(note)
    db.commit()
    return {"message": "Note deleted successfully"}