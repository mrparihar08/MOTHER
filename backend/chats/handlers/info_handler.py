import random
import re
from typing import Any, Dict, Optional

# Triggers that should always bypass info_handler to specialized handlers or LLM
BYPASS_TRIGGERS = [
    # Health / Dora
    "fever", "headache", "cough", "cold", "pain", "doctor", "medicine", "health",
    "dora", "stomach", "symptom", "disease", "vomit", "dizzy", "infection",
    # Financial / Reports / Analytics
    "report", "analysis", "advice", "predict", "overspending", "waste", "anomaly",
    "budget", "trend", "monthly", "chart", "graph", "balance", "calc",
    # Weather
    "weather", "temperature", "mausam", "temp",
]


def handle_info_request(message: str) -> Optional[Dict[str, Any]]:
    """Handles static quick smalltalk & help queries without blocking intelligent routes."""
    text = (message or "").lower().strip()
    if not text:
        return None

    # Do not hijack specialized features
    if any(bt in text for bt in BYPASS_TRIGGERS):
        return None

    def has_exact(*words):
        return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)

    replies = {
        "help": [
            "💡 **Vitya AI Quick Guide:**\n\n"
            "• **Log Expense:** `spent 250 on pizza` or `kal 500 petrol bhara`\n"
            "• **Log Income:** `salary credited 50k` or `5000 cashback mila`\n"
            "• **Charts & Graphs:** `show pie chart for expenses` or `income vs expense trend`\n"
            "• **Quick Stats:** `my balance`, `total expense this month`, `budget status`\n"
            "• **Utilities:** `calc 1500 * 12`, `weather in Mumbai`, `/image futuristic city`\n"
            "• **Information:** `/wiki Elon Musk`, `/news tech updates`\n"
            "• **Health:** `/dora I have severe headache and nausea`",
        ],
        "category": [
            "🏷️ **Supported Categories:**\n"
            "• 🍔 **Food** (Restaurant, Swiggy, Zomato, Groceries)\n"
            "• 🚗 **Transport** (Uber, Ola, Petrol, Metro, Flight)\n"
            "• 🏠 **Housing** (Rent, Maintenance, Society)\n"
            "• 🎬 **Entertainment** (Netflix, Movies, Spotify)\n"
            "• 💡 **Utilities** (Electricity, Wifi, Mobile recharge, Water)\n"
            "• 💊 **Health** (Doctor, Pharmacy, Medicine)\n"
            "• 🛍️ **Shopping** (Amazon, Flipkart, Clothes, Shoes)\n"
            "• 💰 **Salary** (Payout, Bonus, Income, Stipend)\n"
            "• 📚 **Education** (Books, Course fees, Tuition)\n"
            "• 📈 **Finance** (SIP, Stocks, Mutual Funds, Insurance)",
        ],
        "about": [
            "🤖 **About Vitya:**\n\nVitya is your intelligent financial & lifestyle AI companion. "
            "Track spending in natural Hinglish, view smart analytics, generate charts, calculate budgets, "
            "get real-time news, weather, and AI assistance all in one unified chat!",
        ],
        "thanks": [
            "You're very welcome! Let me know if you want to log any other transaction or check your stats. 💳",
            "Always here to help! Keep your finances smart and organized. ✨",
            "Glad to be of help! Have a wonderful day ahead! 🚀",
        ],
        "greet": [
            "👋 Hello! Main hoon **Vitya**, aapka AI financial assistant. Aaj aapne kya kharch kiya ya kya jankari chahiye?",
            "Hey there! Ready to help you track your money and assist with anything you need. What's on your mind today?",
            "Namaste! Kaise madad kar sakta hoon aaj aapki?",
        ],
        "bye": [
            "Goodbye! Have a productive and financially smart day ahead! 👋",
            "Alvida! Jab bhi koi transaction note karna ho, bas ek message bhej dijiye. ✨",
        ],
        "joke": [
            "Why did the coin go to therapy? Because it had too many cents! 🪙😄",
            "Why don't accountants read novels? Because the only numbers in them are page numbers! 📚😂",
            "I told my budget a joke... it didn't laugh, it was too tight! 💸😆",
        ],
        "motivation": [
            "🌟 *'Do not save what is left after spending, but spend what is left after saving.'* — Warren Buffett",
            "🚀 *'Small daily improvements over time lead to stunning financial freedom.'*",
        ],
    }

    if has_exact("help", "guide", "kaise use kare", "/help", "commands"):
        return {"type": "text", "content": replies["help"][0]}

    if has_exact("category", "categories", "konsi category"):
        return {"type": "text", "content": replies["category"][0]}

    if has_exact("about", "who are you", "what is vitya", "vitya kya hai", "tum kaun ho"):
        return {"type": "text", "content": replies["about"][0]}

    if has_exact("thanks", "thank you", "dhanyawad", "shukriya", "thx"):
        return {"type": "text", "content": random.choice(replies["thanks"])}

    if text in ["hello", "hi", "hey", "namaste", "hola", "helo", "hi vitya", "hello vitya"]:
        return {"type": "text", "content": random.choice(replies["greet"])}

    if text in ["bye", "goodbye", "see you", "alvida", "tata", "cya"]:
        return {"type": "text", "content": random.choice(replies["bye"])}

    if has_exact("joke", "chutkula", "hasao"):
        return {"type": "text", "content": random.choice(replies["joke"])}

    if has_exact("motivation", "quote", "motivate"):
        return {"type": "text", "content": random.choice(replies["motivation"])}

    return None