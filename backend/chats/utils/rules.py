import re

rules = {
    "greeting": {
        "type": "text",
        "keywords": ["hi", "hello", "hey", "hii", "namaste"],
        "response": "Hello! How can I help you?"
    },

    "farewell": {
        "type": "text",
        "keywords": ["bye", "goodbye", "see you"],
        "response": "Thank you! Have a great day 😊"
    },

    "thanks": {
        "type": "text",
        "keywords": ["thanks", "thank you", "thx"],
        "response": "You're welcome! 😊"
    },

    "timing": {
        "type": "text",
        "keywords": ["time", "open", "closing", "hours"],
        "response": "We are open from 9 AM to 8 PM (Monday to Saturday)."
    },

    "location": {
        "type": "text",
        "keywords": ["location", "address", "where", "map"],
        "response": "We are located in Betul, Madhya Pradesh."
    },

    "contact": {
        "type": "text",
        "keywords": ["phone", "contact", "number", "call"],
        "response": "You can call us at +91-9876543210."
    },

    "email": {
        "type": "text",
        "keywords": ["email", "mail", "support email"],
        "response": "You can email us at support@example.com."
    },

    "price": {
        "type": "text",
        "keywords": ["price", "cost", "fee", "charges"],
        "response": "Prices vary depending on the service. Please contact us for details."
    },

    "services": {
        "type": "text",
        "keywords": ["services", "what do you offer", "offer"],
        "response": "We offer multiple services. Please specify what you're looking for."
    },

    "booking": {
        "type": "text",
        "keywords": ["book", "appointment", "reserve"],
        "response": "To book an appointment, please call us or visit our office."
    },

    "availability": {
        "type": "text",
        "keywords": ["available", "availability"],
        "response": "Yes, we are available during working hours."
    },

    "payment": {
        "type": "text",
        "keywords": ["payment", "pay", "upi", "cash"],
        "response": "We accept UPI, cash, and bank transfer."
    },

    "refund": {
        "type": "text",
        "keywords": ["refund", "return money"],
        "response": "Refunds depend on the service. Please contact support."
    },

    "complaint": {
        "type": "text",
        "keywords": ["complaint", "problem", "issue"],
        "response": "Sorry for the inconvenience. Please contact support at +91-9876543210."
    },

    "offers": {
        "type": "text",
        "keywords": ["offer", "discount", "deal"],
        "response": "We occasionally provide discounts. Contact us for current offers."
    },

    "owner": {
        "type": "text",
        "keywords": ["owner", "who is owner"],
        "response": "Please contact us directly for owner details."
    },

    "website": {
        "type": "text",
        "keywords": ["website", "site"],
        "response": "You are already on our official website 😊"
    },

    "job": {
        "type": "text",
        "keywords": ["job", "vacancy", "career"],
        "response": "Currently no openings. Please check later."
    },

    "feedback": {
        "type": "text",
        "keywords": ["feedback", "review"],
        "response": "We value your feedback! Please share your thoughts."
    },

    "support": {
        "type": "text",
        "keywords": ["help", "support", "assist"],
        "response": "Sure! Please tell me your issue."
    },

    "delivery": {
        "type": "text",
        "keywords": ["delivery", "deliver"],
        "response": "Delivery options depend on your location. Contact us for details."
    },

    "order": {
        "type": "text",
        "keywords": ["order", "buy", "purchase"],
        "response": "To place an order, please contact us directly."
    },

    "cancel": {
        "type": "text",
        "keywords": ["cancel", "cancel order"],
        "response": "Please contact support to cancel your order."
    },

    "login": {
        "type": "text",
        "keywords": ["login", "sign in"],
        "response": "Please use the login button on the website."
    },

    "signup": {
        "type": "text",
        "keywords": ["signup", "register", "create account"],
        "response": "You can register using the signup option on our website."
    },

    "password": {
        "type": "text",
        "keywords": ["password", "forgot password"],
        "response": "Click on 'Forgot Password' to reset your password."
    },

    "security": {
        "type": "text",
        "keywords": ["secure", "safety", "safe"],
        "response": "Yes, our platform is secure and your data is protected."
    },

    "language": {
        "type": "text",
        "keywords": ["hindi", "english", "language"],
        "response": "We support both Hindi and English."
    },

    "about": {
        "type": "text",
        "keywords": ["about", "company", "who are you"],
        "response": "We are a local service provider dedicated to customer satisfaction."
    },

    "experience": {
        "type": "text",
        "keywords": ["experience", "since when"],
        "response": "We have several years of experience in our field."
    },

    "team": {
        "type": "text",
        "keywords": ["team", "staff"],
        "response": "Our team consists of skilled professionals."
    },

    "holiday": {
        "type": "text",
        "keywords": ["holiday", "closed", "off day"],
        "response": "We are closed on Sundays and public holidays."
    },

    "emergency": {
        "type": "text",
        "keywords": ["urgent", "emergency"],
        "response": "For urgent help, please call us immediately at +91-9876543210."
    }
}


def normalize_message(message: str) -> str:
    message = (message or "").lower().strip()
    message = re.sub(r"[^\w\s]", " ", message)   # punctuation हटाओ
    message = re.sub(r"\s+", " ", message)       # extra spaces हटाओ
    return message


def keyword_matches(message: str, keyword: str) -> bool:
    """
    Single word keywords -> word boundary match
    Multi-word keywords -> normalized phrase search
    """
    keyword = keyword.lower().strip()

    if " " in keyword:
        return keyword in message

    return bool(re.search(rf"\b{re.escape(keyword)}\b", message))


def get_reply(message: str):
    msg = normalize_message(message)

    for intent in rules.values():
        for keyword in intent["keywords"]:
            if keyword_matches(msg, keyword):
                return intent["response"]

    return "Sorry, I didn't understand. Please contact support."