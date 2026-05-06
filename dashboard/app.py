import calendar
import os
import sys
from functools import wraps

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify, render_template, request, redirect, url_for, session

from config import DASHBOARD_PORT, FIXED_COSTS, DASHBOARD_PASSWORD, SECRET_KEY, CATEGORY_ALIASES, EXPENSE_CATEGORIES
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
        if request.form.get('password') == DASHBOARD_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        error = 'Incorrect password. Please try again.'
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _month_payload(month_id: int) -> dict:
    data = db.get_month_details(month_id)
    if not data:
        return {}
    m = data["month"]
    balance = db.get_balance(month_id)
    fixed_total   = sum(f["amount"] for f in data["fixed_costs"])
    savings_total = sum(e["amount"] for e in data["expenses"] if e["category"] == "savings")
    var_total     = sum(e["amount"] for e in data["expenses"] if e["category"] != "savings")

    expenses_by_cat = db.get_expenses_summary(month_id)
    expenses_by_cat.pop("savings", None)

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
        "savings_total": savings_total,
        "total_spent": fixed_total + var_total,
        "balance": balance,
        "balance_pct": round(balance / m["salary"] * 100, 1) if m["salary"] else 0,
    }


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html")


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


# ── Undo API ─────────────────────────────────────────────────────────────────

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

    # No expenses — undo the salary entry
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
    """Re-categorise all expenses using the full alias table."""
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
                # e.g. "food layla" → category "food", description "layla"
                first = words[0]
                resolved = CATEGORY_ALIASES.get(first, first)
                if resolved in EXPENSE_CATEGORIES or resolved != first:
                    new_cat = resolved
                    extra = " ".join(words[1:])
                    new_desc = " ".join(filter(None, [extra, desc]))

            if not new_cat:
                # single-word merchant alias  e.g. "spinneys" → "groceries"
                resolved = CATEGORY_ALIASES.get(original_cat)
                if resolved:
                    new_cat = resolved

            if new_cat and (new_cat != original_cat or new_desc != (e["description"] or "")):
                db.update_expense_category(e["id"], new_cat, new_desc)
                fixed_count += 1

    return jsonify({"ok": True, "fixed": fixed_count})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=True, use_reloader=False)
