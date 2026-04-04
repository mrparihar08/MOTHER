import re
from typing import Dict

TECH_THEMES = {
    "ai": {"bg": "F0F9FF", "accent": (37, 99, 235), "text": (30, 58, 138)},      # Blue/Brain
    "cyber": {"bg": "0F172A", "accent": (34, 197, 94), "text": (248, 250, 252)}, # Dark/Green
    "cloud": {"bg": "F8FAFC", "accent": (14, 165, 233), "text": (15, 23, 42)},   # Sky Blue
    "data": {"bg": "FDF2F8", "accent": (219, 39, 119), "text": (77, 12, 48)},    # Pink/Data
    "blockchain": {"bg": "F5F3FF", "accent": (124, 58, 237), "text": (46, 16, 101)}, # Purple
    "finance": {"bg": "F0FDF4", "accent": (21, 128, 61), "text": (20, 83, 45)},  # Emerald/Green
    "medical": {"bg": "FFF1F2", "accent": (225, 29, 72), "text": (76, 5, 25)},   # Rose/Red
    "education": {"bg": "FFFBEB", "accent": (217, 119, 6), "text": (69, 39, 0)}, # Amber/Yellow
    "marketing": {"bg": "F0FDFA", "accent": (13, 148, 136), "text": (19, 78, 74)}, # Teal
    "iot": {"bg": "ECFDF5", "accent": (5, 150, 105), "text": (6, 78, 59)},       # Emerald
    "gaming": {
        "bg": "111827",
        "accent": (168, 85, 247),
        "text": (243, 244, 246),
    },  # Neon Purple / Gaming

    "startup": {
        "bg": "FFF7ED",
        "accent": (249, 115, 22),
        "text": (124, 45, 18),
    },  # Orange / Startup

    "nature": {
        "bg": "F0FDF4",
        "accent": (34, 197, 94),
        "text": (22, 101, 52),
    },  # Green / Nature

    "travel": {
        "bg": "EFF6FF",
        "accent": (59, 130, 246),
        "text": (30, 64, 175),
    },  # Blue / Travel

    "music": {
        "bg": "F5F3FF",
        "accent": (236, 72, 153),
        "text": (107, 33, 168),
    },  # Pink / Music

    "food": {
        "bg": "FFFBEB",
        "accent": (245, 158, 11),
        "text": (120, 53, 15),
    },  # Warm Yellow / Food

    "sports": {
        "bg": "F8FAFC",
        "accent": (239, 68, 68),
        "text": (30, 41, 59),
    },  # Red / Sports

    "minimal": {
        "bg": "FFFFFF",
        "accent": (100, 116, 139),
        "text": (15, 23, 42),
    },  # Clean Gray

    "night": {
        "bg": "020617",
        "accent": (56, 189, 248),
        "text": (226, 232, 240),
    },  # Deep Dark

    "ecommerce": {
        "bg": "FFFDF7",
        "accent": (245, 158, 11),
        "text": (120, 53, 15),
    },  # Commerce / Buy

    "real_estate": {
        "bg": "F8FAFC",
        "accent": (14, 165, 233),
        "text": (30, 41, 59),
    },  # Property / Blue

    "legal": {
        "bg": "FEFCE8",
        "accent": (161, 98, 7),
        "text": (66, 32, 6),
    },  # Law / Gold

    "hr": {
        "bg": "FDF4FF",
        "accent": (168, 85, 247),
        "text": (88, 28, 135),
    },  # Human Resource / Violet

    "agriculture": {
        "bg": "F0FDF4",
        "accent": (22, 163, 74),
        "text": (21, 128, 61),
    },  # Farm / Green

    "automotive": {
        "bg": "F1F5F9",
        "accent": (71, 85, 105),
        "text": (15, 23, 42),
    },  # Car / Slate

    "retail": {
        "bg": "FFF1F2",
        "accent": (244, 63, 94),
        "text": (136, 19, 55),
    },  # Shop / Rose

    "energy": {
        "bg": "FEF9C3",
        "accent": (202, 138, 4),
        "text": (113, 63, 18),
    },  # Power / Yellow

    "media": {
        "bg": "FAF5FF",
        "accent": (147, 51, 234),
        "text": (88, 28, 135),
    },  # Media / Purple

    "logistics": {
        "bg": "F0F9FF",
        "accent": (2, 132, 199),
        "text": (12, 74, 110),
    },  # Delivery / Blue

    "manufacturing": {
        "bg": "F8FAFC",
        "accent": (100, 116, 139),
        "text": (30, 41, 59),
    },  # Factory / Neutral

    "government": {
        "bg": "EFF6FF",
        "accent": (37, 99, 235),
        "text": (30, 64, 175),
    },  # Public Sector / Blue

    "default": {"bg": "F8FAFC", "accent": (17, 24, 39), "text": (31, 41, 55)}
}

THEME_KEYWORDS = {
    "ai": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural", "llm", "genai", "generative ai", "prompt", "model", "nlp"
    ],
    "cyber": [
        "cyber", "security", "cybersecurity", "encryption", "malware",
        "firewall", "hacker", "hack", "threat", "vulnerability", "pentest"
    ],
    "cloud": [
        "cloud", "server", "aws", "azure", "gcp", "kubernetes", "docker",
        "devops", "deployment", "hosting", "saas", "microservice"
    ],
    "data": [
        "data", "analytics", "analyt", "bi ", "dashboard", "reporting",
        "etl", "warehouse", "sql", "pipeline", "visualization"
    ],
    "blockchain": [
        "blockchain", "web3", "crypto", "ledger", "smart contract",
        "defi", "token", "nft", "wallet", "coin"
    ],
    "finance": [
        "finance", "money", "budget", "expense", "income", "tax", "bank",
        "investment", "trading", "portfolio", "loan", "accounting", "audit"
    ],
    "medical": [
        "medical", "health", "doctor", "clinic", "hospital", "patient",
        "nurse", "pharma", "pharmacy", "diagnosis", "treatment", "medicine"
    ],
    "education": [
        "education", "school", "college", "student", "teacher", "classroom",
        "academic", "course", "e-learning", "elearning", "exam", "study", "syllabus"
    ],
    "marketing": [
        "marketing", "seo", "brand", "branding", "campaign", "ads",
        "advertising", "sales", "lead", "conversion", "crm", "growth", "promotion"
    ],
    "iot": [
        "iot", "internet of things", "smart device", "sensor", "embedded",
        "automation", "connected device", "wearable", "smart home"
    ],
    "gaming": [
        "game", "gaming", "esports", "vr", "ar", "metaverse", "controller",
        "multiplayer", "player", "console"
    ],
    "startup": [
        "startup", "mvp", "founder", "pitch", "venture", "funding",
        "seed round", "product launch", "scale", "entrepreneur"
    ],
    "nature": [
        "nature", "green", "eco", "environment", "sustainable", "forest",
        "agriculture", "farm", "organic", "climate"
    ],
    "travel": [
        "travel", "tour", "tourism", "trip", "hotel", "flight", "vacation",
        "journey", "booking", "destination"
    ],
    "music": [
        "music", "song", "audio", "podcast", "album", "dj", "beat",
        "melody", "studio", "recording"
    ],
    "food": [
        "food", "restaurant", "cafe", "kitchen", "recipe", "cooking",
        "meal", "dining", "chef", "bakery"
    ],
    "sports": [
        "sports", "fitness", "gym", "game", "match", "team", "player",
        "training", "workout", "athlete"
    ],
    "ecommerce": [
        "ecommerce", "e-commerce", "shop", "shopping", "store", "cart",
        "checkout", "marketplace", "product", "order"
    ],
    "real_estate": [
        "real estate", "property", "house", "home", "rent", "apartment",
        "villa", "land", "broker", "housing"
    ],
    "legal": [
        "legal", "law", "lawyer", "court", "contract", "compliance",
        "regulation", "case", "justice"
    ],
    "hr": [
        "hr", "human resource", "recruitment", "hire", "employee", "payroll",
        "talent", "onboarding", "performance review"
    ],
    "agriculture": [
        "agriculture", "agri", "farm", "farmer", "crop", "soil", "irrigation",
        "harvest", "rural"
    ],
    "automotive": [
        "automotive", "car", "vehicle", "ev", "electric vehicle", "engine",
        "garage", "fleet", "transport"
    ],
    "retail": [
        "retail", "store", "shop", "merchant", "sales counter", "inventory",
        "pos", "point of sale"
    ],
    "energy": [
        "energy", "power", "electricity", "solar", "wind", "battery",
        "renewable", "grid", "utility"
    ],
    "media": [
        "media", "news", "journalism", "broadcast", "content", "editorial",
        "publishing", "streaming", "video"
    ],
    "logistics": [
        "logistics", "delivery", "shipping", "supply chain", "warehouse",
        "tracking", "fleet", "shipment", "transport"
    ],
    "manufacturing": [
        "manufacturing", "factory", "production", "assembly", "industry",
        "quality control", "plant", "machinery", "operations"
    ],
    "government": [
        "government", "public sector", "municipal", "policy", "civic",
        "administration", "e-governance", "gov"
    ],
}

def detect_theme(text: str) -> Dict:
    raw = text.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", raw)
    padded = f" {normalized} "

    scores = {}
    for theme, keywords in THEME_KEYWORDS.items():
        score = 0
        for kw in keywords:
            kw_norm = kw.lower().strip()

            # Multi-word phrases get a stronger weight
            if " " in kw_norm:
                if f" {kw_norm} " in padded:
                    score += 3
            else:
                if re.search(rf"\b{re.escape(kw_norm)}\b", normalized):
                    score += 1

        scores[theme] = score

    best_theme = max(scores, key=scores.get)
    return TECH_THEMES[best_theme] if scores[best_theme] > 0 else TECH_THEMES["default"]
