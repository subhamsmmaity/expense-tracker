import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Expense

# Create database tables
Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Spendly - Expense Tracker API")


# -------------------------------
# Pydantic Models
# -------------------------------

class ExpenseCreate(BaseModel):
    title: str
    amount: float = Field(gt=0)
    category: str
    date: datetime.date


class ExpenseOut(ExpenseCreate):
    id: int

    model_config = {"from_attributes": True}


# -------------------------------
# Home Page
# -------------------------------

@app.get("/", include_in_schema=False)
def home():
    index_file = BASE_DIR / "index.html"

    if not index_file.exists():
        raise HTTPException(
            status_code=404,
            detail="index.html was not found in the root folder"
        )

    return FileResponse(index_file)


# -------------------------------
# Health Check
# -------------------------------

@app.get("/health")
def health():
    return {
        "message": "Expense Tracker API is running"
    }


# -------------------------------
# Add Expense
# -------------------------------

@app.post("/expenses", response_model=ExpenseOut)
def add_expense(
    data: ExpenseCreate,
    db: Session = Depends(get_db)
):
    try:
        expense = Expense(**data.model_dump())

        db.add(expense)
        db.commit()
        db.refresh(expense)

        return expense

    except Exception as e:
        db.rollback()
        print(f"Add expense error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Could not add expense"
        )


# -------------------------------
# List and Filter Expenses
# -------------------------------

@app.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(
    category: Optional[str] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Expense)

    if category:
        query = query.filter(
            func.lower(Expense.category) == category.lower()
        )

    if start_date:
        query = query.filter(
            Expense.date >= start_date
        )

    if end_date:
        query = query.filter(
            Expense.date <= end_date
        )

    return query.order_by(Expense.date.desc()).all()


# -------------------------------
# Get Single Expense
# -------------------------------

@app.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db)
):
    expense = db.get(Expense, expense_id)

    if not expense:
        raise HTTPException(
            status_code=404,
            detail="Expense not found"
        )

    return expense


# -------------------------------
# Update Expense
# -------------------------------

@app.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(
    expense_id: int,
    data: ExpenseCreate,
    db: Session = Depends(get_db)
):
    expense = db.get(Expense, expense_id)

    if not expense:
        raise HTTPException(
            status_code=404,
            detail="Expense not found"
        )

    try:
        for key, value in data.model_dump().items():
            setattr(expense, key, value)

        db.commit()
        db.refresh(expense)

        return expense

    except Exception as e:
        db.rollback()
        print(f"Update expense error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Could not update expense"
        )


# -------------------------------
# Delete Expense
# -------------------------------

@app.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db)
):
    expense = db.get(Expense, expense_id)

    if not expense:
        raise HTTPException(
            status_code=404,
            detail="Expense not found"
        )

    try:
        db.delete(expense)
        db.commit()

        return {
            "message": "Expense deleted successfully"
        }

    except Exception as e:
        db.rollback()
        print(f"Delete expense error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Could not delete expense"
        )


# -------------------------------
# Monthly Summary
# -------------------------------

@app.get("/summary/{year}/{month}")
def monthly_summary(
    year: int,
    month: int,
    db: Session = Depends(get_db)
):
    # Validate month
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=400,
            detail="Month must be between 1 and 12"
        )

    try:
        # First day of selected month
        start_date = datetime.date(
            year,
            month,
            1
        )

        # First day of the next month
        if month == 12:
            end_date = datetime.date(
                year + 1,
                1,
                1
            )
        else:
            end_date = datetime.date(
                year,
                month + 1,
                1
            )

        # Calculate total for each category
        rows = (
            db.query(
                Expense.category,
                func.sum(Expense.amount).label("total")
            )
            .filter(
                Expense.date >= start_date,
                Expense.date < end_date
            )
            .group_by(Expense.category)
            .all()
        )

        # Convert results to a dictionary
        by_category = {
            category: float(total or 0)
            for category, total in rows
        }

        # Calculate monthly total
        total_amount = sum(
            by_category.values()
        )

        return {
            "year": year,
            "month": month,
            "total": total_amount,
            "by_category": by_category
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"Monthly summary error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Failed to generate monthly summary"
        )
