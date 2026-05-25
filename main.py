
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import requests
from fastapi.middleware.cors import CORSMiddleware
import json
from dotenv import  load_dotenv
import os

load_dotenv()


app = FastAPI()

# 🔓 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 KEYS
AI_API_KEY = os.getenv("AI_API_KEY")

API_KEY = os.getenv("API_KEY")
print("AI_API_KEY",AI_API_KEY)
print("API_KEY",API_KEY)

# 📦 MODELS
class StockDay(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class AIAnalysis(BaseModel):
    summary: str
    risk: str
    confidence: str


class StockResponse(BaseModel):
    symbol: str
    data: List[StockDay]
    trend: str
    percent_change: float
    recommendation: str
    ai_analysis: AIAnalysis


#  AI FUNCTION
def get_ai_analysis(symbol, trend, percent_change, prices):
    ai_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={AI_API_KEY}"

    oldest_price = prices[0]
    latest_price = prices[-1]
    highest = max(prices)
    lowest = min(prices)

    prompt = f"""
You are a financial assistant for beginners.

Analyze stock: {symbol}

Data:
- Last 10 days closing prices: {prices}
- Oldest price: {oldest_price}
- Latest price: {latest_price}
- Highest price: {highest}
- Lowest price: {lowest}
- Trend: {trend}
- Percentage change: {percent_change:.2f}%

Tasks:
1. Briefly explain what the company does (include industry and founder if known).
2. Explain the price movement using the actual numbers (oldest → latest).
3. Say whether this movement looks normal or unusual.
4. Give a simple beginner-friendly explanation (not financial advice).

Return ONLY valid JSON:
{{
  "summary": "clear explanation including company background and price movement",
  "risk": "low/medium/high",
  "confidence": "low/medium/high"
}}

No markdown. No backticks. No extra text.
"""

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    data = None
    try:
        response = requests.post(ai_url, json=payload, timeout=10)
        data = response.json()

        ai_text = data["candidates"][0]["content"]["parts"][0]["text"]

        # 🔥 CLEAN TEXT
        ai_text = ai_text.strip()
        ai_text = ai_text.replace("```json", "").replace("```", "")

        # 🔥 EXTRACT ONLY JSON PART
        start = ai_text.find("{")
        end = ai_text.rfind("}") + 1

        if start == -1 or end == -1:
            raise ValueError("No JSON found in AI response")

        ai_text = ai_text[start:end]

        parsed = json.loads(ai_text)

        # 🔥 SAFETY CHECK (keys exist)
        return {
            "summary": parsed.get("summary", "No summary"),
            "risk": parsed.get("risk", "unknown"),
            "confidence": parsed.get("confidence", "unknown")
        }

    except Exception as e:
        print("AI ERROR:", e)
        print("RAW AI RESPONSE:", data)

        return {
            "summary": "AI analysis not available",
            "risk": "unknown",
            "confidence": "unknown"
        }

#  MAIN ENDPOINT
@app.get("/stock/{symbol}", response_model=StockResponse)
def get_stock(symbol: str):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={API_KEY}"

    try:
        response = requests.get(url, timeout=10)
        data = response.json()
    except:
        raise HTTPException(status_code=500, detail="Failed to fetch stock data")

    #  API error
    if "Time Series (Daily)" not in data:
        print("API ERROR:", data)
        raise HTTPException(
            status_code=400,
            detail=data.get("Note") or data.get("Error Message") or "API error"
        )

    time_series = data["Time Series (Daily)"]

    stock_data = []

    for i, (date, value) in enumerate(time_series.items()):
        stock_data.append(StockDay(
            date=date,
            open=float(value["1. open"]),
            high=float(value["2. high"]),
            low=float(value["3. low"]),
            close=float(value["4. close"]),
            volume=int(value["5. volume"])
        ))

        if i == 9:
            break

    #  FIX ORDER → oldest → newest
    stock_data.reverse()

    prices = [day.close for day in stock_data]

    oldest_price = prices[0]
    latest_price = prices[-1]

    percent_change = ((latest_price - oldest_price) / oldest_price) * 100

    #  TREND
    if percent_change > 2:
        trend = "up"
    elif percent_change < -2:
        trend = "down"
    else:
        trend = "sideways"

    # 💡 RECOMMENDATION
    if trend == "up":
        recommendation = "buy"
    elif trend == "down":
        recommendation = "sell"
    else:
        recommendation = "hold"


    ai_analysis = get_ai_analysis(symbol, trend, percent_change, prices)

    #  RESPONSE
    return StockResponse(
        symbol=symbol,
        data=stock_data,
        trend=trend,
        percent_change=percent_change,
        recommendation=recommendation,
        ai_analysis=ai_analysis
    )