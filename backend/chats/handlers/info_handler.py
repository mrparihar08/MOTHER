import random
import re

def handle_info_request(message: str):
    text = (message or "").lower().strip()

    def has_any(*words):
        return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)

    replies = {
        "report": [
            "Report feature is coming soon!",
            "Reports are not available yet, but they are on the way.",
            "I am still learning to generate reports. Coming soon!",
            "Report section will be available in a future update.",
            "I cannot generate full reports right now, but it is planned.",
            "Reports are under development. Stay tuned!",
        ],
        "advice": [
            "Financial advice feature is coming soon!",
            "I will be able to give finance tips soon.",
            "Advice mode is not ready yet, but it is coming soon!",
            "I am still learning to give personalized financial advice.",
            "Advice support will be added in a future version.",
            "I cannot give full advice yet, but that feature is planned.",
        ],
        "help": [
            "You can tell me things like 'I spent 200 on food' or 'I earned 5000 salary'. You can also ask for totals like 'What is my total expense?'",
            "Try sending messages like 'paid 300 for groceries' or 'received 10000 salary'.",
            "You can chat naturally, for example: 'I bought lunch for 150' or 'I got freelance income 5000'.",
            "Send an expense or income message, and I will try to understand it.",
            "You can ask me to track spending, income, categories, totals, and summaries.",
            "Just type something like 'spent 120 on tea' or 'salary received 25000'.",
            "I can help with expenses, income, categories, and basic finance questions.",
        ],
        "category": [
            "I can categorize your transactions into Food, Transport, Entertainment, Utilities, Health, Salary, Shopping, and Housing based on keywords in your message.",
            "I detect categories like Food, Travel, Salary, Bills, Health, and Shopping from your text.",
            "Send me a transaction and I will try to classify it into the right expense or income category.",
            "I can map your spending to useful categories automatically.",
            "My category detection is keyword-based and works on simple transaction text.",
            "I can sort your entries into income and expense categories.",
        ],
        "feedback": [
            "We value your feedback! Please email us at feedback@vitya.com",
            "Your feedback matters. Write to feedback@vitya.com",
            "I would love to hear your suggestions at feedback@vitya.com",
            "Thanks for helping improve vitya. Send feedback to feedback@vitya.com",
            "You can share your ideas anytime at feedback@vitya.com",
        ],
        "contact": [
            "You can contact our support team at support@vitya.com",
            "Need help? Reach out to support@vitya.com",
            "For support, email support@vitya.com",
            "If something is not working, support@vitya.com is the right place.",
            "You can ask our support team at support@vitya.com",
        ],
        "about": [
            "vitya is your personal finance assistant. I can help you track your expenses and income just by chatting with me!",
            "vitya helps you manage money by understanding everyday messages about spending and earning.",
            "I am vitya, your personal money assistant for tracking income and expenses through chat.",
            "vitya is built to make expense tracking simple and conversational.",
            "I help turn normal chat messages into financial records.",
        ],
        "thanks": [
            "You're welcome! I'm here to help you manage your finances.",
            "Anytime! I am always here for your finance tasks.",
            "Glad to help. Keep tracking your money wisely!",
            "No problem at all. I am happy to help.",
            "You are welcome. Let us keep your finances organized.",
            "Always here to help.",
        ],
        "greet": [
            "Hello! I'm vitya, your personal finance assistant. How can I help you today?",
            "Hi there! I am vitya. Tell me your expense or income.",
            "Hey! Ready to track your money with you.",
            "Hello! Share your spending or earning details.",
            "Hi! I can help with expenses, income, and totals.",
            "Welcome back! What would you like to record today?",
        ],
        "bye": [
            "Goodbye! Have a great day managing your finances!",
            "See you soon! Keep your budget healthy.",
            "Bye! Stay financially smart.",
            "Take care! Keep saving and tracking.",
            "Goodbye! Come back anytime for finance help.",
            "See you later. Keep your money goals in mind.",
        ],
        "joke": [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the accountant break up with the calendar? Too many dates.",
            "I told my wallet a joke. Now it is still empty, but at least it smiled.",
            "Why was the budget so calm? Because it knew its limits.",
            "Why did the coin go to therapy? It had too many cents.",
            "I tried to save money, but my wallet kept making withdrawal arguments.",
        ],
        "quote": [
            "The best way to get started is to quit talking and begin doing. - Walt Disney",
            "Small steps every day lead to big results.",
            "Success is the sum of small efforts repeated daily.",
            "Do something today that your future self will thank you for.",
            "Discipline beats motivation when motivation disappears.",
            "A steady plan is better than a sudden rush.",
        ],
        "motivation": [
            "Don't watch the clock; do what it does. Keep going. - Sam Levenson",
            "Progress matters more than perfection. Keep moving.",
            "Save a little, earn a little, and grow steadily.",
            "Consistency is stronger than motivation.",
            "Tiny improvements every day become big wins.",
            "You do not need a perfect start, only a real one.",
        ],
        "weather": [
            "I can't check the weather yet, but I hope it's nice where you are!",
            "Weather lookup is not available right now, but I hope your day is pleasant.",
            "I cannot fetch weather yet, but I am hoping for clear skies for you!",
            "I am not connected to weather data yet.",
            "Weather updates are not available in this version.",
        ],
        "holiday": [
            "I hope you have a wonderful holiday! Remember to budget for it!",
            "Enjoy your holiday and keep an eye on spending too.",
            "Have a great holiday! Planning ahead helps a lot.",
            "Holiday time is fun — a little budget planning goes a long way.",
            "Enjoy your break and keep your finances balanced.",
        ],
        "goal": [
            "Setting financial goals is a great way to stay motivated! What are your goals?",
            "Goals make budgeting easier. What are you saving for?",
            "Tell me your money goal and I can help you stay on track.",
            "A clear goal makes money management much easier.",
            "What are you planning to save for this month?",
        ],
        "challenge": [
            "Here's a financial challenge for you: Try to save 10% of your income this month!",
            "Challenge: track every expense for 7 days straight.",
            "Challenge time: reduce one unnecessary expense this week.",
            "Try a no-spend day and see how it feels.",
            "Track all your spending today and review it tonight.",
        ],
        "random": [
            "Money management is a habit, not a one-time task.",
            "Small savings can become big results over time.",
            "Tracking expenses regularly gives you control.",
            "A simple budget can reduce stress a lot.",
            "Your future self will thank you for saving today.",
            "Spend with purpose, not by impulse.",
            "A clean budget is a powerful tool.",
            "Good financial habits start with awareness.",
            "One tracked expense is better than no tracking at all.",
            "You do not need to be perfect to make progress.",
            "Every rupee you track gives you more clarity.",
            "Budgeting is easier when you keep it simple.",
            "Saving a little now can help a lot later.",
            "Smart money habits start with small choices.",
            "Stay consistent and your finances will become clearer.",
            "A little discipline today can create a stronger tomorrow.",
            "Know where your money goes, and you will control it better.",
            "Even small income details matter when you track them well.",
            "Your budget works best when you review it often.",
            "Simple habits create strong financial results.",
        ],
        "fallback": [
            "I am here to help with your finance tracking.",
            "Tell me about a payment, expense, income, or ask for help.",
            "I can understand simple money-related messages.",
            "Try saying something like 'I spent 250 on food'.",
            "I am ready whenever you are.",
            "Send me a transaction and I will process it.",
            "You can ask me about expenses, income, categories, or totals.",
            "I can help organize your money information.",
            "Share your spending or earning details with me.",
            "I did not catch that, but I can still help with finance messages.",
            "I can understand simple finance commands and transaction messages.",
            "Try asking about help, category, report, advice, or totals.",
            "I am designed to track money conversations in a simple way.",
            "You can give me expense and income text directly.",
            "I am still learning, but I can help with basic finance tasks.",
        ],
    }

    if has_any("report"):
        return {"type": "text", "content": random.choice(replies["report"])}

    if has_any("advice"):
        return {"type": "text", "content": random.choice(replies["advice"])}

    if has_any("help"):
        return {"type": "text", "content": random.choice(replies["help"])}

    if has_any("category"):
        return {"type": "text", "content": random.choice(replies["category"])}

    if has_any("feedback"):
        return {"type": "text", "content": random.choice(replies["feedback"])}

    if has_any("contact"):
        return {"type": "text", "content": random.choice(replies["contact"])}

    if has_any("about"):
        return {"type": "text", "content": random.choice(replies["about"])}

    if has_any("thanks", "thank", "thank you"):
        return {"type": "text", "content": random.choice(replies["thanks"])}

    if has_any("hello", "hi", "hey", "greet"):
        return {"type": "text", "content": random.choice(replies["greet"])}

    if has_any("bye", "goodbye", "see you"):
        return {"type": "text", "content": random.choice(replies["bye"])}

    if has_any("joke", "funny"):
        return {"type": "text", "content": random.choice(replies["joke"])}

    if has_any("quote"):
        return {"type": "text", "content": random.choice(replies["quote"])}

    if has_any("motivation", "motivate", "motivational"):
        return {"type": "text", "content": random.choice(replies["motivation"])}

    if has_any("weather"):
        return {"type": "text", "content": random.choice(replies["weather"])}

    if has_any("holiday", "vacation"):
        return {"type": "text", "content": random.choice(replies["holiday"])}

    if has_any("goal", "goals"):
        return {"type": "text", "content": random.choice(replies["goal"])}

    if has_any("challenge"):
        return {"type": "text", "content": random.choice(replies["challenge"])}

    # Extra random fallback replies
    if random.random() < 0.25:
        return {"type": "text", "content": random.choice(replies["random"])}

    return {"type": "text", "content": random.choice(replies["fallback"])}