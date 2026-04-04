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