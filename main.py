import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Expense

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Expense Tracker API")


class ExpenseCreate(BaseModel):
    title: str
    amount: float = Field(gt=0)
    category: str
    date: datetime.date


class ExpenseOut(ExpenseCreate):
    id: int
    model_config = {"from_attributes": True}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health():
    return {"message": "Expense Tracker API is running"}


@app.post("/expenses", response_model=ExpenseOut)
def add_expense(data: ExpenseCreate, db: Session = Depends(get_db)):
    expense = Expense(**data.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@app.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    category: Optional[str] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Expense)
    if category:
        query = query.filter(func.lower(Expense.category) == category.lower())
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)
    return query.all()


@app.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense


@app.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, data: ExpenseCreate, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    for key, value in data.model_dump().items():
        setattr(expense, key, value)
    db.commit()
    db.refresh(expense)
    return expense


@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
    return {"message": "Expense deleted"}


@app.get("/summary/{year}/{month}")
def monthly_summary(year: int, month: int, db: Session = Depends(get_db)):
    rows = (
        db.query(Expense.category, func.sum(Expense.amount))
        .filter(extract("year", Expense.date) == year,
                extract("month", Expense.date) == month)
        .group_by(Expense.category)
        .all()
    )
    return {
        "year": year,
        "month": month,
        "total": sum(total for _, total in rows),
        "by_category": {category: total for category, total in rows},
    }