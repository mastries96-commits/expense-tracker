import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")

FIXED_COSTS = {
    "Rent":      float(os.environ.get("RENT",      4200)),
    "Etisalat":  float(os.environ.get("ETISALAT",  420)),
    "Auto Loan": float(os.environ.get("AUTO_LOAN", 1980)),
}

EXPENSE_CATEGORIES = {
    "food":          "🍔",
    "petrol":        "⛽",
    "shopping":      "🛍",
    "groceries":     "🛒",
    "entertainment": "🎬",
    "health":        "💊",
    "transport":     "🚌",
    "utilities":     "⚡",
    "education":     "📚",
    "savings":       "🐷",
    "other":         "💸",
}

CATEGORY_ALIASES = {
    # Savings
    "save": "savings", "saving": "savings",

    # Petrol / fuel
    "gas": "petrol", "fuel": "petrol", "patrol": "petrol",
    "adnoc": "petrol", "enoc": "petrol", "emarat": "petrol",

    # Groceries
    "grocery": "groceries",
    "spinneys": "groceries", "spinney": "groceries",
    "carrefour": "groceries", "lulu": "groceries",
    "waitrose": "groceries", "choithrams": "groceries", "choitram": "groceries",
    "nesto": "groceries", "geant": "groceries",
    "rawabi": "groceries", "grandiose": "groceries",
    "kibsons": "groceries", "hyperpanda": "groceries",
    "viva": "groceries", "almaya": "groceries",
    "unioncoop": "groceries", "westzone": "groceries",
    "priceline": "groceries",

    # Food
    "eat": "food", "restaurant": "food", "cafe": "food",
    "coffee": "food", "lunch": "food", "dinner": "food",
    "breakfast": "food", "snack": "food",
    "takeaway": "food", "takeout": "food", "delivery": "food",
    "shawarma": "food", "biryani": "food", "hummus": "food",
    "kfc": "food",
    "mcdonalds": "food", "mcdonald's": "food", "mcd": "food",
    "subway": "food", "starbucks": "food", "caribou": "food",
    "timhortons": "food", "hardees": "food",
    "pizzahut": "food", "dominos": "food", "domino's": "food",
    "nandos": "food", "nando's": "food", "pickl": "food",
    "chattime": "food", "zaatar": "food", "manoushe": "food",
    "jasmis": "food", "luqaimat": "food", "salt": "food",
    "layla": "food", "eataly": "food", "bosporus": "food",
    "kababji": "food", "burgerking": "food",

    # Shopping
    "shop": "shopping",
    "homebox": "shopping", "ikea": "shopping", "zara": "shopping",
    "h&m": "shopping", "hm": "shopping", "splash": "shopping",
    "centrepoint": "shopping", "lifestyle": "shopping",
    "namshi": "shopping", "noon": "shopping", "amazon": "shopping",
    "sephora": "shopping", "babyshop": "shopping",
    "mothercare": "shopping", "shoemart": "shopping",
    "max": "shopping", "ounass": "shopping", "faces": "shopping",
    "mumzworld": "shopping", "danube": "shopping", "acemart": "shopping",

    # Health
    "medical": "health", "medicine": "health",
    "pharmacy": "health", "clinic": "health",
    "doctor": "health", "hospital": "health",
    "boots": "health", "aster": "health",
    "lifepharmacy": "health", "mediclinic": "health",
    "nmc": "health", "thumbay": "health",

    # Transport
    "bus": "transport", "taxi": "transport",
    "uber": "transport", "careem": "transport",
    "metro": "transport", "tram": "transport",
    "rta": "transport", "salik": "transport", "nol": "transport",
    "bolt": "transport",

    # Utilities
    "electric": "utilities", "electricity": "utilities",
    "water": "utilities", "internet": "utilities", "bill": "utilities",
    "dewa": "utilities", "sewa": "utilities", "addc": "utilities",
    "du": "utilities",

    # Entertainment
    "cinema": "entertainment",
    "vox": "entertainment", "reel": "entertainment",
    "netflix": "entertainment", "spotify": "entertainment",
    "bowling": "entertainment", "ski": "entertainment",
    "yas": "entertainment", "playstation": "entertainment",
    "nintendo": "entertainment",

    # Education
    "school": "education", "tuition": "education",
    "nursery": "education", "books": "education",
}

DB_PATH            = os.environ.get("DB_PATH", "expenses.db")
DASHBOARD_PORT     = int(os.environ.get("PORT", 5000))
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "9693")
SECRET_KEY         = os.environ.get("SECRET_KEY", "expense-tracker-secret")
