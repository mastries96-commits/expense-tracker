# ─────────────────────────────────────────────────────────────────────────────
# Copy this file to config.py and fill in your own values.
# Never commit config.py — it contains secrets.
# ─────────────────────────────────────────────────────────────────────────────

# Get your token from @BotFather on Telegram
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

# Fixed monthly costs auto-deducted on each salary entry (amounts in AED)
FIXED_COSTS = {
    "Rent":      4200,
    "Etisalat":  420,
    "Auto Loan": 1980,
}

# Canonical expense categories and their display emoji
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

# Maps merchant names / keywords → canonical category
# Add your own UAE (or local) merchants here
CATEGORY_ALIASES = {
    # Savings
    "save": "savings", "saving": "savings",

    # Petrol / fuel
    "gas": "petrol", "fuel": "petrol", "patrol": "petrol",
    "adnoc": "petrol", "enoc": "petrol", "emarat": "petrol",

    # Groceries – supermarkets
    "grocery": "groceries",
    "spinneys": "groceries", "spinney": "groceries",
    "carrefour": "groceries", "lulu": "groceries",
    "waitrose": "groceries", "choithrams": "groceries",
    "nesto": "groceries", "geant": "groceries",
    "rawabi": "groceries", "grandiose": "groceries",
    "kibsons": "groceries", "hyperpanda": "groceries",
    "viva": "groceries", "almaya": "groceries",
    "unioncoop": "groceries", "westzone": "groceries",
    "priceline": "groceries",

    # Food – restaurants / cafes / delivery
    "eat": "food", "restaurant": "food", "cafe": "food",
    "coffee": "food", "lunch": "food", "dinner": "food",
    "breakfast": "food", "snack": "food",
    "takeaway": "food", "takeout": "food", "delivery": "food",
    "kfc": "food", "mcdonalds": "food", "mcdonald's": "food", "mcd": "food",
    "subway": "food", "starbucks": "food", "caribou": "food",
    "timhortons": "food", "hardees": "food",
    "pizzahut": "food", "dominos": "food", "domino's": "food",
    "nandos": "food", "nando's": "food", "pickl": "food",
    "chattime": "food", "zaatar": "food", "manoushe": "food",
    "jasmis": "food", "luqaimat": "food", "salt": "food",
    "layla": "food", "eataly": "food", "bosporus": "food",
    "kababji": "food", "burgerking": "food", "shawarma": "food",
    "biryani": "food", "hummus": "food",

    # Shopping / retail
    "shop": "shopping",
    "homebox": "shopping", "ikea": "shopping", "zara": "shopping",
    "h&m": "shopping", "hm": "shopping", "splash": "shopping",
    "centrepoint": "shopping", "lifestyle": "shopping",
    "namshi": "shopping", "noon": "shopping", "amazon": "shopping",
    "sephora": "shopping", "babyshop": "shopping",
    "mothercare": "shopping", "shoemart": "shopping",
    "max": "shopping", "ounass": "shopping", "faces": "shopping",
    "mumzworld": "shopping", "danube": "shopping", "acemart": "shopping",

    # Health / pharmacy
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

    # Utilities / bills
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

# SQLite database file path
DB_PATH = "expenses.db"

# Flask dashboard settings
DASHBOARD_PORT = 5000
DASHBOARD_PASSWORD = "change_me"          # password to access the dashboard
SECRET_KEY = "change-this-to-a-random-string"  # Flask session secret
