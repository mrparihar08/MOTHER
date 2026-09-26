from fastapi.concurrency import run_in_threadpool
import pandas as pd
import pickle
import os
from sklearn.linear_model import LinearRegression

models = {}
MODEL_FILE = "models.pkl"

def save_models():
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(models, f)

def load_models():
    global models
    if os.path.exists(MODEL_FILE):
        with open(MODEL_FILE, "rb") as f:
            models = pickle.load(f)

def train_model(df: pd.DataFrame):

    models.clear()

    df["date"] = pd.to_datetime(df["date"])

    df = df.groupby(
        ["category", pd.Grouper(key="date", freq="ME")]
    )["amount"].sum().reset_index()

    for category in df["category"].unique():

        cat_df = df[df["category"] == category]

        if len(cat_df) < 2:
            continue

        cat_df["month_index"] = range(len(cat_df))

        model = LinearRegression()
        model.fit(cat_df[["month_index"]], cat_df["amount"])

        models[category] = model

    save_models()

def predict(df: pd.DataFrame):

    df["date"] = pd.to_datetime(df["date"])

    df_month = df.groupby(
        ["category", pd.Grouper(key="date", freq="ME")]
    )["amount"].sum().reset_index()

    result = []

    for category in df_month["category"].unique():

        if category not in models:
            continue

        model = models[category]

        idx = len(df_month[df_month["category"] == category])

        predicted = model.predict([[idx]])[0]

        result.append({
            "category": category,
            "prediction": round(predicted,2)
        })

    return result

async def async_train_model(df: pd.DataFrame):
    return await run_in_threadpool(train_model, df)

async def async_predict(df: pd.DataFrame):
    return await run_in_threadpool(predict, df)


# -------------------------------------------------------------
# FINANCIAL HEALTH & EXECUTIVE SUMMARY SERVICES
# -------------------------------------------------------------
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.api.models.vitya import Expense, Income, Budget, SavingsGoal, RecurringSubscription, User
from backend.chats.services.gemini_service import generate_response


def compute_financial_health_score(current_user: User, db: Session) -> dict:
    total_income = db.query(func.sum(Income.amount)).filter(Income.user_id == current_user.id).scalar() or 0.0
    total_expense = db.query(func.sum(Expense.amount)).filter(Expense.user_id == current_user.id).scalar() or 0.0
    
    total_income = float(total_income)
    total_expense = float(total_expense)
    
    expense_ratio = (total_expense / total_income * 100.0) if total_income > 0 else (100.0 if total_expense > 0 else 0.0)
    net_savings = max(0.0, total_income - total_expense)
    savings_rate = (net_savings / total_income * 100.0) if total_income > 0 else 0.0
    
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()
    budget_adherence = 100.0
    if budgets:
        exceeded_count = 0
        for b in budgets:
            c_spend = db.query(func.sum(Expense.amount)).filter(
                Expense.user_id == current_user.id,
                Expense.category == b.category
            ).scalar() or 0.0
            if float(c_spend) > b.monthly_limit:
                exceeded_count += 1
        budget_adherence = max(0.0, 100.0 - (exceeded_count / len(budgets) * 50.0))

    subs = db.query(RecurringSubscription).filter(
        RecurringSubscription.user_id == current_user.id,
        RecurringSubscription.status == "active"
    ).all()
    monthly_subs = 0.0
    for s in subs:
        if s.billing_cycle == "yearly":
            monthly_subs += s.amount / 12.0
        elif s.billing_cycle == "weekly":
            monthly_subs += s.amount * 4.33
        else:
            monthly_subs += s.amount
            
    sub_ratio = (monthly_subs / total_income * 100.0) if total_income > 0 else (50.0 if monthly_subs > 0 else 0.0)
    
    score = 0
    score += min(35, int((savings_rate / 20.0) * 35))
    if expense_ratio <= 70:
        score += 30
    else:
        score += max(0, int(30 - ((expense_ratio - 70) * 1.0)))
    score += int((budget_adherence / 100.0) * 20)
    if sub_ratio <= 15:
        score += 15
    else:
        score += max(0, int(15 - ((sub_ratio - 15) * 0.75)))
        
    score = min(100, max(0, score))
    
    if score >= 85:
        grade = "Excellent"
    elif score >= 70:
        grade = "Good"
    elif score >= 50:
        grade = "Fair"
    else:
        grade = "Needs Attention"
        
    recs = []
    if savings_rate < 20:
        recs.append("Boost your savings rate to at least 20% of your total income.")
    if expense_ratio > 70:
        recs.append("Your total expenses exceed 70% of income. Consider reviewing high-spending categories.")
    if budget_adherence < 100:
        recs.append("You have exceeded limits in one or more budget categories. Adjust monthly caps.")
    if sub_ratio > 15:
        recs.append(f"Active subscriptions make up {round(sub_ratio, 1)}% of income. Audit unused recurring bills.")
    if not recs:
        recs.append("Great job maintaining healthy financial habits! Keep monitoring goals regularly.")
        
    return {
        "health_score": score,
        "grade": grade,
        "savings_rate_pct": round(savings_rate, 2),
        "expense_ratio_pct": round(expense_ratio, 2),
        "budget_adherence_pct": round(budget_adherence, 2),
        "subscription_ratio_pct": round(sub_ratio, 2),
        "recommendations": recs
    }


def generate_ai_financial_executive_summary(current_user: User, db: Session) -> dict:
    health = compute_financial_health_score(current_user, db)
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == current_user.id).all()
    
    prompt = (
        f"Generate an executive 2-paragraph financial summary for user {current_user.name}.\n"
        f"Financial Health Score: {health['health_score']}/100 ({health['grade']})\n"
        f"Savings Rate: {health['savings_rate_pct']}%, Expense Ratio: {health['expense_ratio_pct']}%\n"
        f"Subscription Ratio: {health['subscription_ratio_pct']}%\n"
        f"Active Goals Count: {len(goals)}\n"
        f"Key Recommendations: {', '.join(health['recommendations'])}\n\n"
        f"Keep the tone encouraging, executive, professional, and actionable."
    )
    
    ai_text = generate_response(prompt)
    if ai_text.startswith("Gemini error") or ai_text.startswith("Gemini API key"):
        ai_text = (
            f"Executive Financial Summary for {current_user.name}:\n\n"
            f"Your overall Financial Health Score is {health['health_score']}/100 ({health['grade']}). "
            f"Your current savings rate is {health['savings_rate_pct']}% with an expense-to-income ratio of {health['expense_ratio_pct']}%\n\n"
            f"Primary Focus: {health['recommendations'][0]}"
        )
        
    return {
        "summary_text": ai_text,
        "generated_at": datetime.now(timezone.utc)
    }