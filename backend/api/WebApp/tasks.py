from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.api.database import get_db
from backend.api.models.vitya import Task
from backend.api.schemas.vitya import TaskCreate, TaskUpdate, TaskResponse

router = APIRouter()


# ---------------------------
# GET ALL TASKS
# ---------------------------
@router.get("/", response_model=List[TaskResponse])
def get_tasks(db: Session = Depends(get_db)):
    tasks = db.query(Task).order_by(Task.id.desc()).all()
    return tasks


# ---------------------------
# CREATE TASK
# ---------------------------
@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    title = task.title.strip()

    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task title cannot be empty",
        )

    new_task = Task(title=title)

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return new_task


# ---------------------------
# UPDATE TASK (Partial Update Supported)
# ---------------------------
@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    task_data: TaskUpdate,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    update_data = task_data.model_dump(exclude_unset=True)

    if "title" in update_data:
        title = update_data["title"].strip()
        if not title:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Task title cannot be empty",
            )
        task.title = title

    db.commit()
    db.refresh(task)

    return task


# ---------------------------
# DELETE TASK
# ---------------------------
@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    db.delete(task)
    db.commit()

    return {"message": "Task deleted successfully"}