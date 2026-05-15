import calendar
import datetime as _dt
import os
import re
import socket
import sys
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, jsonify, render_template, request, redirect, url_for, session, send_from_directory

from config import DASHBOARD_PORT, FIXED_COSTS, DASHBOARD_PASSWORD, DASHBOARD_USERNAME, SECRET_KEY, CATEGORY_ALIASES, EXPENSE_CATEGORIES, uae_now, uae_today
from database import Database

app = Flask(__name__)
app.secret_key = SECRET_KEY
db = Database()


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('authenticated'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('authenticated'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        if (request.form.get('username') == DASHBOARD_USERNAME and
                request.form.get('password') == DASHBOARD_PASSWORD):
            session['authenticated'] = True
            return redirect(url_for('index'))
        error = 'Invalid username or password.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))


# ── PWA assets ────────────────────────────────────────────────────────────────

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Expense Tracker",
        "short_name": "Expenses",
        "description": "Personal UAE expense tracker",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#F0F4F8",
        "theme_color": "#1E293B",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    })


@app.route('/sw.js')
def service_worker():
    resp = send_from_directory(app.static_folder, 'sw.js')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ── Helpers ───────────────────────────────────────────────────────────────────

def _month_payload(month_id: int) -> dict:
    data = db.get_month_details(month_id)
    if not data:
        return {}
    m = data["month"]
    balance = db.get_balance(month_id)
    fixed_total   = sum(f["amount"] for f in data["fixed_costs"])

    special_secs   = db.get_special_sections()
    special_names  = {s["name"] for s in special_secs}
    special_totals = {s["name"]: sum(e["amount"] for e in data["expenses"] if e["category"] == s["name"]) for s in special_secs}

    savings_total = sum(e["amount"] for e in data["expenses"] if e["category"] == "savings")
    var_total     = sum(e["amount"] for e in data["expenses"] if e["category"] not in special_names and e["category"] != "savings")

    expenses_by_cat = db.get_expenses_summary(month_id)
    expenses_by_cat.pop("savings", None)
    for _n in special_names:
        expenses_by_cat.pop(_n, None)

    return {
        "month": {
            "id": m["id"],
            "year": m["year"],
            "month": m["month"],
            "name": calendar.month_name[m["month"]],
            "salary": m["salary"],
            "status": m["status"],
        },
        "fixed_costs": data["fixed_costs"],
        "fixed_total": fixed_total,
        "expenses": data["expenses"],
        "expenses_by_category": expenses_by_cat,
        "var_total": var_total,
        "spending_total": var_total + sum(special_totals.values()),
        "savings_total": savings_total,
        "total_spent": fixed_total + var_total,
        "balance": balance,
        "balance_pct": round(balance / m["salary"] * 100, 1) if m["salary"] else 0,
        "special_sections": [dict(s) for s in special_secs],
        "special_totals": special_totals,
    }


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return "ok", 200



@app.route("/api/debug-write")
def debug_write():
    import traceback
    try:
        active = db.get_active_month()
        if not active:
            return jsonify({"step": "get_active_month", "result": None})
        eid = db.add_expense(active["id"], "debugtest", 0.01, "auto-debug", str(uae_today()))
        bal = db.get_balance(active["id"])
        return jsonify({"ok": True, "expense_id": eid, "balance": bal, "month_id": active["id"]})
    except Exception as e:
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route("/api/import-data", methods=["POST"])
def api_import_data():
    # One-time import endpoint — secured with SECRET_KEY as a bearer token
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {SECRET_KEY}":
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json()
    with db._conn() as conn:
        conn.execute("DELETE FROM expenses")
        conn.execute("DELETE FROM fixed_costs")
        conn.execute("DELETE FROM months")
        for m in data.get("months", []):
            conn.execute(
                "INSERT INTO months (id, year, month, salary, status, created_at, closed_at) VALUES (?,?,?,?,?,?,?)",
                (m["id"], m["year"], m["month"], m["salary"], m["status"], m["created_at"], m.get("closed_at"))
            )
        for f in data.get("fixed_costs", []):
            conn.execute(
                "INSERT INTO fixed_costs (id, month_id, name, amount) VALUES (?,?,?,?)",
                (f["id"], f["month_id"], f["name"], f["amount"])
            )
        for e in data.get("expenses", []):
            conn.execute(
                "INSERT INTO expenses (id, month_id, category, amount, description, expense_date, created_at) VALUES (?,?,?,?,?,?,?)",
                (e["id"], e["month_id"], e["category"], e["amount"], e["description"], e["expense_date"], e["created_at"])
            )
    return jsonify({"ok": True, "months": len(data.get("months", [])), "expenses": len(data.get("expenses", []))})


# ── Data API ──────────────────────────────────────────────────────────────────

@app.route("/api/current")
@login_required
def api_current():
    active = db.get_active_month()
    if not active:
        return jsonify({"error": "no_active_month"})
    return jsonify(_month_payload(active["id"]))


@app.route("/api/months")
@login_required
def api_months():
    months = db.get_all_months()
    result = []
    for m in months:
        data = db.get_month_details(m["id"])
        savings_total = sum(e["amount"] for e in data["expenses"] if e["category"] == "savings")
        var_total     = sum(e["amount"] for e in data["expenses"] if e["category"] != "savings")
        result.append({
            "id": m["id"],
            "year": m["year"],
            "month": m["month"],
            "name": calendar.month_name[m["month"]],
            "salary": m["salary"],
            "fixed_total": sum(f["amount"] for f in data["fixed_costs"]),
            "var_total": var_total,
            "savings_total": savings_total,
            "balance": db.get_balance(m["id"]),
            "status": m["status"],
        })
    return jsonify(result)


@app.route("/api/month/<int:month_id>")
@login_required
def api_month(month_id):
    payload = _month_payload(month_id)
    if not payload:
        return jsonify({"error": "not_found"}), 404
    return jsonify(payload)


@app.route("/api/network-info")
@login_required
def api_network_info():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return jsonify({"ip": ip, "port": DASHBOARD_PORT})


# ── Entry API (dashboard / mobile app) ───────────────────────────────────────

@app.route("/api/add-expense", methods=["POST"])
@login_required
def api_add_expense():
    data = request.get_json()
    raw_cat = (data.get("category") or "").strip().lower()
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_amount"}), 400
    description = (data.get("description") or "").strip()
    date_str = data.get("date") or str(uae_today())

    if not raw_cat or amount <= 0:
        return jsonify({"error": "invalid_input"}), 400

    first_word = raw_cat.split()[0]
    category = CATEGORY_ALIASES.get(first_word, first_word)

    active = db.get_active_month()
    if not active:
        return jsonify({"error": "no_active_month"}), 400

    db.add_expense(active["id"], category, amount, description, date_str)
    balance = db.get_balance(active["id"])
    return jsonify({"ok": True, "balance": balance, "category": category})


@app.route("/api/add-salary", methods=["POST"])
@login_required
def api_add_salary():
    data = request.get_json()
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_amount"}), 400

    if amount <= 0:
        return jsonify({"error": "invalid_amount"}), 400

    prev = db.get_active_month()
    if prev:
        db.close_month(prev["id"])
        if prev["month"] == 12:
            new_year, new_month = prev["year"] + 1, 1
        else:
            new_year, new_month = prev["year"], prev["month"] + 1
    else:
        now = uae_now()
        new_year, new_month = now.year, now.month

    month_id = db.create_or_get_month(new_year, new_month, amount)
    db.add_fixed_costs(month_id, FIXED_COSTS)
    balance = db.get_balance(month_id)

    return jsonify({
        "ok": True,
        "month": calendar.month_name[new_month],
        "year": new_year,
        "salary": amount,
        "balance": balance,
    })


# ── Undo API ──────────────────────────────────────────────────────────────────

@app.route("/api/undo", methods=["POST"])
@login_required
def api_undo():
    active = db.get_active_month()
    if not active:
        return jsonify({"ok": False, "message": "No active month to undo."})

    expense = db.get_last_expense(active["id"])
    if expense:
        db.delete_expense(expense["id"])
        balance = db.get_balance(active["id"])
        return jsonify({
            "ok": True,
            "type": "expense",
            "message": f"Deleted {expense['category'].capitalize()} — AED {expense['amount']:,.2f}",
            "balance": balance,
        })

    prev = db.get_last_closed_month()
    db.delete_month_cascade(active["id"])
    if prev:
        db.reopen_month(prev["id"])
        prev_name = f"{calendar.month_name[prev['month']]} {prev['year']}"
        return jsonify({
            "ok": True,
            "type": "salary",
            "message": f"Salary entry undone. {prev_name} is active again.",
        })
    return jsonify({
        "ok": True,
        "type": "salary",
        "message": "Salary entry undone. No previous month to restore.",
    })


# ── Expense mutation API ──────────────────────────────────────────────────────

@app.route("/api/expense/<int:expense_id>", methods=["DELETE"])
@login_required
def api_delete_expense(expense_id):
    db.delete_expense(expense_id)
    return jsonify({"ok": True})


@app.route("/api/expense/<int:expense_id>", methods=["PATCH"])
@login_required
def api_update_expense(expense_id):
    data = request.get_json()
    raw_cat = (data.get("category") or "").strip().lower()
    category = CATEGORY_ALIASES.get(raw_cat, raw_cat)
    if not category:
        return jsonify({"error": "missing category"}), 400
    try:
        amount = float(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid amount"}), 400
    if amount <= 0:
        return jsonify({"error": "invalid amount"}), 400
    description  = (data.get("description") or "").strip()
    expense_date = (data.get("expense_date") or "").strip()
    if not expense_date:
        return jsonify({"error": "missing date"}), 400
    db.update_expense_full(expense_id, category, amount, description, expense_date)
    return jsonify({"ok": True, "category": category})


@app.route("/api/expense/<int:expense_id>/description", methods=["PATCH"])
@login_required
def api_update_description(expense_id):
    data = request.get_json()
    description = (data.get("description") or "").strip()
    db.update_expense_description(expense_id, description)
    return jsonify({"ok": True})


@app.route("/api/reclassify", methods=["POST"])
@login_required
def api_reclassify():
    months = db.get_all_months()
    fixed_count = 0
    for m in months:
        data = db.get_month_details(m["id"])
        for e in data["expenses"]:
            original_cat = e["category"].lower()
            desc = e["description"] or ""
            new_cat = None
            new_desc = desc

            words = original_cat.split()
            if len(words) > 1:
                first = words[0]
                resolved = CATEGORY_ALIASES.get(first, first)
                if resolved in EXPENSE_CATEGORIES or resolved != first:
                    new_cat = resolved
                    extra = " ".join(words[1:])
                    new_desc = " ".join(filter(None, [extra, desc]))

            if not new_cat:
                resolved = CATEGORY_ALIASES.get(original_cat)
                if resolved:
                    new_cat = resolved

            if new_cat and (new_cat != original_cat or new_desc != (e["description"] or "")):
                db.update_expense_category(e["id"], new_cat, new_desc)
                fixed_count += 1

    return jsonify({"ok": True, "fixed": fixed_count})


# ── Special sections API ──────────────────────────────────────────────────────

@app.route("/api/special-sections", methods=["GET"])
@login_required
def api_get_special_sections():
    return jsonify([dict(s) for s in db.get_special_sections()])


@app.route("/api/special-sections", methods=["POST"])
@login_required
def api_add_special_section():
    data = request.get_json()
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": "label required"}), 400
    name  = re.sub(r'[^a-z0-9]+', '_', label.lower().strip()).strip('_')
    icon  = (data.get("icon") or "credit-card").strip()
    color = (data.get("color") or "#8B5CF6").strip()
    try:
        sid = db.add_special_section(name, label, icon, color)
        return jsonify({"ok": True, "id": sid, "name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/special-sections/<int:section_id>", methods=["DELETE"])
@login_required
def api_delete_special_section(section_id):
    db.delete_special_section(section_id)
    return jsonify({"ok": True})


# ── Chat API (Telegram-style natural language entry) ──────────────────────────

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "message": "Empty message."})

    now = uae_now()
    cmd = text.lower().lstrip("/")

    # ── balance ───────────────────────────────────────────────────────────────
    if cmd in ("balance", "b"):
        active = db.get_active_month()
        if not active:
            return jsonify({"ok": True, "refresh": False,
                "message": "⚠️ No active month. Record your salary first."})
        data   = db.get_month_details(active["id"])
        fixed  = sum(f["amount"] for f in data["fixed_costs"])
        spent  = sum(e["amount"] for e in data["expenses"])
        bal    = db.get_balance(active["id"])
        by_cat = db.get_expenses_summary(active["id"])
        lines  = [
            f"💰 {calendar.month_name[active['month']]} {active['year']}",
            f"Salary:    AED {active['salary']:>10,.2f}",
            f"Fixed:     AED {fixed:>10,.2f}",
            f"Expenses:  AED {spent:>10,.2f}",
            f"─────────────────────",
            f"Remaining: AED {bal:>10,.2f}",
        ]
        if by_cat:
            lines.append("")
            for cat, total in sorted(by_cat.items(), key=lambda x: -x[1]):
                emoji = EXPENSE_CATEGORIES.get(cat, "💸")
                lines.append(f"{emoji} {cat.capitalize()}: AED {total:,.2f}")
        return jsonify({"ok": True, "refresh": False, "message": "\n".join(lines)})

    # ── summary ───────────────────────────────────────────────────────────────
    if cmd in ("summary", "s"):
        active = db.get_active_month()
        if not active:
            return jsonify({"ok": True, "refresh": False, "message": "⚠️ No active month."})
        data      = db.get_month_details(active["id"])
        fixed_tot = sum(f["amount"] for f in data["fixed_costs"])
        var_tot   = sum(e["amount"] for e in data["expenses"])
        bal       = db.get_balance(active["id"])
        sav_pct   = (bal / active["salary"] * 100) if active["salary"] else 0
        return jsonify({"ok": True, "refresh": False,
            "message": (
                f"📊 {calendar.month_name[active['month']]} {active['year']}\n"
                f"Salary:   AED {active['salary']:,.2f}\n"
                f"Fixed:    AED {fixed_tot:,.2f}\n"
                f"Variable: AED {var_tot:,.2f}\n"
                f"Balance:  AED {bal:,.2f} ({sav_pct:.1f}%)"
            )})

    # ── undo ──────────────────────────────────────────────────────────────────
    if cmd in ("undo", "u"):
        active = db.get_active_month()
        if not active:
            return jsonify({"ok": True, "refresh": False, "message": "Nothing to undo."})
        expense = db.get_last_expense(active["id"])
        if expense:
            db.delete_expense(expense["id"])
            bal = db.get_balance(active["id"])
            return jsonify({"ok": True, "refresh": True,
                "message": (f"↩️ Deleted: {expense['category'].capitalize()} — AED {expense['amount']:,.2f}\n"
                            f"💰 Balance: AED {bal:,.2f}")})
        prev = db.get_last_closed_month()
        db.delete_month_cascade(active["id"])
        if prev:
            db.reopen_month(prev["id"])
            return jsonify({"ok": True, "refresh": True,
                "message": f"↩️ Salary undone. {calendar.month_name[prev['month']]} {prev['year']} restored."})
        return jsonify({"ok": True, "refresh": True, "message": "↩️ Salary entry undone."})

    # ── help ──────────────────────────────────────────────────────────────────
    if cmd in ("help", "h", "?"):
        return jsonify({"ok": True, "refresh": False, "message": (
            "💡 What you can type:\n\n"
            "food 150\n"
            "kfc 80 dinner\n"
            "spinneys 300 weekly\n"
            "petrol 200 filled up\n"
            "savings 500\n"
            "salary 15000\n"
            "balance  →  check balance\n"
            "undo     →  remove last entry"
        )})

    # ── +Salary / salary <amount> ─────────────────────────────────────────────
    sal_match = re.match(r"^\+?salary\s+([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if sal_match:
        amount = float(sal_match.group(1).replace(",", ""))
        prev   = db.get_active_month()
        if prev:
            db.close_month(prev["id"])
            new_year  = prev["year"] + 1 if prev["month"] == 12 else prev["year"]
            new_month = 1 if prev["month"] == 12 else prev["month"] + 1
        else:
            new_year, new_month = now.year, now.month
        month_id  = db.create_or_get_month(new_year, new_month, amount)
        db.add_fixed_costs(month_id, FIXED_COSTS)
        fixed_tot = sum(FIXED_COSTS.values())
        balance   = amount - fixed_tot
        deductions = "\n".join(f"  • {n}: AED {v:,.2f}" for n, v in FIXED_COSTS.items())
        return jsonify({"ok": True, "refresh": True, "message": (
            f"✅ Salary AED {amount:,.2f} recorded\n\n"
            f"📌 Fixed costs deducted:\n{deductions}\n\n"
            f"📅 {calendar.month_name[new_month]} {new_year} is now active\n"
            f"💵 Available: AED {balance:,.2f}"
        )})

    # ── Expense: "food 150", "kfc 80 dinner", "+petrol 200" ──────────────────
    exp_match = re.match(
        r"^\+?([a-zA-Z][a-zA-Z\s\-'&]*?)\s+([\d,]+(?:\.\d+)?)\s*(.*)?$", text
    )
    if exp_match and not text.startswith("/"):
        pre          = exp_match.group(1).strip()
        amount       = float(exp_match.group(2).replace(",", ""))
        post         = (exp_match.group(3) or "").strip()
        pre_words    = pre.split()
        raw_category = pre_words[0].lower()
        extra        = " ".join(pre_words[1:])
        description  = " ".join(filter(None, [extra, post]))
        category     = CATEGORY_ALIASES.get(raw_category, raw_category)

        active = db.get_active_month()
        if not active:
            return jsonify({"ok": False, "refresh": False,
                "message": "⚠️ No active month. Record your salary first."})

        db.add_expense(active["id"], category, amount, description, str(now.date()))
        balance = db.get_balance(active["id"])
        emoji   = EXPENSE_CATEGORIES.get(category, "💸")
        warning = "\n⚠️ Balance running low!" if balance < 500 else ""
        desc_ln = f"\n📝 {description}" if description else ""
        return jsonify({"ok": True, "refresh": True, "message": (
            f"{emoji} {category.capitalize()} — AED {amount:,.2f}{desc_ln}\n"
            f"💰 Remaining: AED {balance:,.2f}{warning}"
        )})

    return jsonify({"ok": False, "refresh": False,
        "message": "❓ Didn't get that. Try: food 150, kfc 80, salary 15000, balance, undo, help"})


# ── Telegram webhook setup ────────────────────────────────────────────────────

@app.route("/setup-webhook")
@login_required
def setup_webhook():
    import urllib.request, json as _json
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        return jsonify({"error": "BOT_TOKEN is not set in Render environment variables. Add it in the Render dashboard under Environment."}), 500
    host = request.host_url.rstrip("/")
    webhook_url = f"{host}/webhook/{token}"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"
    with urllib.request.urlopen(api_url) as r:
        result = _json.loads(r.read())
    return jsonify({"webhook_url": webhook_url, "telegram_response": result})


# ── Telegram webhook (used when deployed on Render/cloud) ────────────────────

_BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


def _process_tg_text(text: str) -> str:
    """Run the same logic as /api/chat and return a plain-text reply."""
    import calendar as _cal
    now = uae_now()
    cmd = text.strip().lower().lstrip("/")

    if cmd in ("balance", "b"):
        active = db.get_active_month()
        if not active:
            return "⚠️ No active month. Record your salary first: +Salary 15000"
        data  = db.get_month_details(active["id"])
        fixed = sum(f["amount"] for f in data["fixed_costs"])
        spent = sum(e["amount"] for e in data["expenses"])
        bal   = db.get_balance(active["id"])
        lines = [
            f"💰 *{_cal.month_name[active['month']]} {active['year']}*",
            f"Salary:    AED {active['salary']:>10,.2f}",
            f"Fixed:     AED {fixed:>10,.2f}",
            f"Expenses:  AED {spent:>10,.2f}",
            f"─────────────────────",
            f"Remaining: *AED {bal:>10,.2f}*",
        ]
        by_cat = db.get_expenses_summary(active["id"])
        if by_cat:
            lines.append("")
            for cat, total in sorted(by_cat.items(), key=lambda x: -x[1]):
                emoji = EXPENSE_CATEGORIES.get(cat, "💸")
                lines.append(f"{emoji} {cat.capitalize()}: AED {total:,.2f}")
        return "\n".join(lines)

    if cmd in ("summary", "s"):
        active = db.get_active_month()
        if not active:
            return "⚠️ No active month."
        data      = db.get_month_details(active["id"])
        fixed_tot = sum(f["amount"] for f in data["fixed_costs"])
        var_tot   = sum(e["amount"] for e in data["expenses"])
        bal       = db.get_balance(active["id"])
        pct       = (bal / active["salary"] * 100) if active["salary"] else 0
        return (f"📊 *{_cal.month_name[active['month']]} {active['year']}*\n"
                f"Salary:   AED {active['salary']:,.2f}\n"
                f"Fixed:    AED {fixed_tot:,.2f}\n"
                f"Variable: AED {var_tot:,.2f}\n"
                f"Balance:  *AED {bal:,.2f}* ({pct:.1f}%)")

    if cmd in ("undo", "u"):
        active = db.get_active_month()
        if not active:
            return "Nothing to undo."
        expense = db.get_last_expense(active["id"])
        if expense:
            db.delete_expense(expense["id"])
            bal = db.get_balance(active["id"])
            return (f"↩️ *Undone:* {expense['category'].capitalize()} — AED {expense['amount']:,.2f}\n"
                    f"💰 Balance: AED {bal:,.2f}")
        prev = db.get_last_closed_month()
        db.delete_month_cascade(active["id"])
        if prev:
            db.reopen_month(prev["id"])
            return f"↩️ Salary undone. *{_cal.month_name[prev['month']]} {prev['year']}* restored."
        return "↩️ Salary entry undone."

    if cmd in ("help", "h", "?", "start"):
        return (
            "💰 *Expense Tracker*\n\n"
            "➕ *Add expense:*\n`food 150`, `kfc 80 dinner`, `petrol 200`\n\n"
            "💼 *Add salary:*\n`+Salary 15000`\n\n"
            "📊 *Commands:*\n"
            "/balance — remaining balance\n"
            "/summary — full breakdown\n"
            "/undo — remove last entry\n"
            "/help — this message"
        )

    sal_match = re.match(r"^\+?salary\s+([\d,]+(?:\.\d+)?)", text.strip(), re.IGNORECASE)
    if sal_match:
        amount = float(sal_match.group(1).replace(",", ""))
        prev   = db.get_active_month()
        if prev:
            db.close_month(prev["id"])
            new_year  = prev["year"] + 1 if prev["month"] == 12 else prev["year"]
            new_month = 1 if prev["month"] == 12 else prev["month"] + 1
        else:
            new_year, new_month = now.year, now.month
        month_id  = db.create_or_get_month(new_year, new_month, amount)
        db.add_fixed_costs(month_id, FIXED_COSTS)
        fixed_tot = sum(FIXED_COSTS.values())
        balance   = amount - fixed_tot
        lines = [f"  • {n}: AED {v:,.2f}" for n, v in FIXED_COSTS.items()]
        return (f"✅ *Salary AED {amount:,.2f} recorded*\n\n"
                f"📌 Fixed costs deducted:\n" + "\n".join(lines) + "\n\n"
                f"📅 *{_cal.month_name[new_month]} {new_year}* is now active\n"
                f"💵 Available: *AED {balance:,.2f}*")

    exp_match = re.match(
        r"^\+?([a-zA-Z][a-zA-Z\s\-'&]*?)\s+([\d,]+(?:\.\d+)?)\s*(.*)?$", text.strip()
    )
    if exp_match and not text.strip().startswith("/"):
        pre          = exp_match.group(1).strip()
        amount       = float(exp_match.group(2).replace(",", ""))
        post         = (exp_match.group(3) or "").strip()
        raw_category = pre.split()[0].lower()
        extra        = " ".join(pre.split()[1:])
        description  = " ".join(filter(None, [extra, post]))
        category     = CATEGORY_ALIASES.get(raw_category, raw_category)
        active = db.get_active_month()
        if not active:
            return "⚠️ No active month. Record your salary first: +Salary 15000"
        db.add_expense(active["id"], category, amount, description, str(now.date()))
        balance = db.get_balance(active["id"])
        emoji   = EXPENSE_CATEGORIES.get(category, "💸")
        warn    = "\n\n⚠️ *Balance running low!*" if balance < 500 else ""
        desc_ln = f"\n📝 _{description}_" if description else ""
        return (f"✅ {emoji} *{category.capitalize()}* — AED {amount:,.2f}{desc_ln}\n"
                f"💰 Remaining: *AED {balance:,.2f}*{warn}")

    return "❓ Didn't get that. Try: `food 150`, `+Salary 15000`, /balance, /help"


def _tg_send(chat_id, text):
    import urllib.request as _ur
    import json as _json
    url  = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
    body = _json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req  = _ur.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with _ur.urlopen(req, timeout=10) as r:
        return _json.loads(r.read())


@app.route("/webhook/<token>", methods=["POST"])
def telegram_webhook(token):
    if not _BOT_TOKEN or token != _BOT_TOKEN:
        return "forbidden", 403

    payload  = request.get_json(force=True) or {}
    message  = payload.get("message", {})
    text     = (message.get("text") or "").strip()
    chat_id  = (message.get("chat") or {}).get("id")

    if not text or not chat_id:
        return "ok"

    try:
        reply = _process_tg_text(text)
    except Exception as e:
        app.logger.error(f"Webhook process error: {e}", exc_info=True)
        reply = "⚠️ Something went wrong. Please try again."

    try:
        _tg_send(chat_id, reply)
    except Exception as e:
        app.logger.error(f"Webhook send error: {e}", exc_info=True)

    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=True, use_reloader=False)
