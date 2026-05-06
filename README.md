# 💰 Expense Tracker

A personal finance tracker built for the UAE market — log expenses via Telegram bot, visualise spending on a local web dashboard.

---

## Features

**Telegram Bot**
- Log expenses instantly: `food 150`, `kfc 80 dinner`, `spinneys 300`
- Record salary: `+Salary 15000` — auto-deducts fixed costs and opens a new month
- Smart category detection — 70+ UAE merchant aliases (Spinneys → groceries, KFC → food, ADNOC → petrol, etc.)
- Any free-text category accepted; unknown merchants kept as-is
- `/balance` — remaining balance + breakdown by category
- `/summary` — full monthly report
- `/history` — past months overview
- `/delete food 50` / `/delete last` / `/undo` — remove or undo entries including salary

**Web Dashboard** (`http://localhost:5000`)
- Password-protected login
- Live balance, stat cards, doughnut chart (variable expenses only)
- Click a pie slice or legend item to filter the transactions table by category
- Fixed costs shown as a separate amber strip (not mixed into the chart)
- Delete / edit description on any transaction inline
- **Undo** floating button — undoes the last expense or the last salary entry
- Fix Categories button — retroactively re-categorises all historical entries
- History tab — monthly cards with salary, fixed, variable, savings, balance
- Reports tab — monthly statements with pie chart + PDF download
- Dark / light theme toggle
- Monthly bar chart (salary vs. spent vs. balance)

---

## Stack

| Layer | Technology |
|-------|-----------|
| Bot | Python 3.12, [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) 20.7 |
| Dashboard | Flask 3.0.2, Chart.js 4.4, Bootstrap 5.3 |
| Database | SQLite (WAL mode) |
| PDF export | jsPDF 2.5.1 + html2canvas 1.4.1 |
| Fonts / Icons | Inter, Font Awesome 6.5 |

---

## Project Structure

```
expense-tracker/
├── bot.py               # Telegram bot — all command and message handlers
├── config.py            # Your secrets & settings (git-ignored)
├── config.example.py    # Copy this → config.py and fill in your values
├── database.py          # SQLite wrapper (months, fixed_costs, expenses)
├── run.py               # Starts both bot + dashboard together
├── run.bat              # Windows launcher (double-click)
├── requirements.txt
└── dashboard/
    ├── app.py           # Flask routes & REST API
    └── templates/
        ├── index.html   # Single-page dashboard
        └── login.html   # Login page
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/expense-tracker.git
cd expense-tracker
pip install -r requirements.txt
```

### 2. Create your config

```bash
cp config.example.py config.py
```

Edit `config.py`:

```python
BOT_TOKEN = "your-telegram-bot-token"   # from @BotFather

FIXED_COSTS = {
    "Rent":      4200,    # adjust to your actual fixed costs
    "Etisalat":  420,
    "Auto Loan": 1980,
}

DASHBOARD_PASSWORD = "your-password"
SECRET_KEY = "any-random-string"
```

### 3. Create a Telegram bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the token into `config.py`

### 4. Run

**Windows (double-click):**
```
run.bat
```

**Or manually:**
```bash
python run.py
```

Both the bot and dashboard start together.  
Dashboard → `http://localhost:5000`

---

## Bot Usage

### Record salary (starts a new month)
```
+Salary 15000
```
Auto-deducts your fixed costs and opens the new month.

### Log an expense
```
food 150
kfc 80 dinner with family
spinneys 300 weekly shop
petrol 200 filled up
savings 500
```
First word = category. Remaining text = description. No `+` needed.

### Commands
| Command | Description |
|---------|-------------|
| `/balance` | Remaining balance + category breakdown |
| `/summary` | Full month report |
| `/history` | All past months |
| `/delete food 50` | Remove most recent matching expense |
| `/delete last` | Remove the very last entry |
| `/undo` | Undo last expense, or undo salary entry |
| `/help` | Show all commands |

---

## Dashboard API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/current` | Active month full data |
| GET | `/api/months` | All months summary |
| GET | `/api/month/<id>` | Single month detail |
| DELETE | `/api/expense/<id>` | Delete an expense |
| PATCH | `/api/expense/<id>/description` | Update description |
| POST | `/api/undo` | Undo last expense or salary |
| POST | `/api/reclassify` | Re-categorise all historical expenses |

---

## Customising Categories

Add merchant aliases in `config.py` under `CATEGORY_ALIASES`:

```python
CATEGORY_ALIASES = {
    "mymall": "shopping",
    "myfavoritecafe": "food",
    ...
}
```

Then click **Fix Categories** on the dashboard to retroactively apply them to existing entries.

---

## License

MIT — use freely, modify as needed.
