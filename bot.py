import re
import logging
import calendar
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)

from config import BOT_TOKEN, FIXED_COSTS, DASHBOARD_PORT, EXPENSE_CATEGORIES, CATEGORY_ALIASES, uae_now
from database import Database

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database()


# ── Helpers ────────────────────────────────────────────────────────────────────

def fmt(amount: float) -> str:
    return f"AED {amount:,.2f}"


def month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def escape_md(text: str) -> str:
    """Escape Markdown v1 special characters in user-supplied text."""
    for ch in ['_', '*', '`', '[']:
        text = text.replace(ch, '\\' + ch)
    return text


def build_report(month_data: dict) -> str:
    m = month_data["month"]
    salary = m["salary"]
    fixed_costs = month_data["fixed_costs"]
    expenses = month_data["expenses"]

    fixed_total = sum(f["amount"] for f in fixed_costs)
    var_total = sum(e["amount"] for e in expenses)
    savings = salary - fixed_total - var_total
    savings_pct = (savings / salary * 100) if salary > 0 else 0

    by_cat: dict = {}
    for e in expenses:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]

    lines = [
        f"📊 *{month_label(m['year'], m['month'])} Report*",
        "",
        f"💰 Salary: {fmt(salary)}",
        "",
        "🏠 *Fixed Costs:*",
        *[f"  • {fc['name']}: {fmt(fc['amount'])}" for fc in fixed_costs],
        f"  ─ Total: *{fmt(fixed_total)}*",
        "",
        "🛒 *Variable Expenses:*",
    ]
    if by_cat:
        for cat, total in sorted(by_cat.items(), key=lambda x: -x[1]):
            lines.append(f"  • {cat.capitalize()}: {fmt(total)}")
        lines.append(f"  ─ Total: *{fmt(var_total)}*")
    else:
        lines.append("  No variable expenses recorded.")

    lines += [
        "",
        f"💸 *Total Spent:* {fmt(fixed_total + var_total)}",
        f"{'✅' if savings >= 0 else '⚠️'} *Savings:* {fmt(savings)} ({savings_pct:.1f}%)",
    ]
    return "\n".join(lines)


# ── Command handlers ───────────────────────────────────────────────────────────

HELP_TEXT = (
    "💰 *Expense Tracker*\n\n"
    "➕ *Record salary:*\n"
    "`+Salary 15000`\n\n"
    "💸 *Add an expense (with or without +):*\n"
    "`+food 150` or `food 150`\n"
    "`+petrol 200 filled tank`\n"
    "`+shopping 500 mall`\n"
    "`+groceries 300 Carrefour`\n"
    "`+entertainment 100 cinema`\n"
    "`+health 200 pharmacy`\n\n"
    "📌 *Fixed costs auto-deducted on salary entry:*\n"
    "  🏠 Rent: AED 4,200\n"
    "  📱 Etisalat: AED 420\n"
    "  🚗 Auto Loan: AED 1,980\n\n"
    "📊 *Commands:*\n"
    "/balance — remaining balance\n"
    "/summary — full month breakdown\n"
    "/history — past months overview\n"
    "/dashboard — dashboard URL\n"
    "/help — show this message\n\n"
    "🗑 *Delete / correct an entry:*\n"
    "`/delete food 50` — remove most recent match\n"
    "`/delete savings 2000`\n"
    "`/delete last` — remove very last entry\n"
    "`/undo` — same as /delete last"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = db.get_active_month()
    if not active:
        await update.message.reply_text(
            "⚠️ No active month. Record your salary first:\n`+Salary 15000`",
            parse_mode="Markdown",
        )
        return

    balance = db.get_balance(active["id"])
    summary = db.get_expenses_summary(active["id"])
    month_data = db.get_month_details(active["id"])
    fixed_total = sum(f["amount"] for f in month_data["fixed_costs"])
    var_total = sum(e["amount"] for e in month_data["expenses"])

    lines = [
        f"💰 *Balance — {month_label(active['year'], active['month'])}*",
        "",
        f"Salary:       {fmt(active['salary'])}",
        f"Fixed costs:  {fmt(fixed_total)}",
        f"Expenses:     {fmt(var_total)}",
        f"─────────────────────",
        f"Remaining:    *{fmt(balance)}*",
    ]
    if summary:
        lines += ["", "📋 *Expenses by category:*"]
        for cat, total in summary.items():
            lines.append(f"  • {cat.capitalize()}: {fmt(total)}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = db.get_active_month()
    if not active:
        await update.message.reply_text("No active month found.")
        return
    month_data = db.get_month_details(active["id"])
    await update.message.reply_text(build_report(month_data), parse_mode="Markdown")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    months = db.get_all_months()
    if not months:
        await update.message.reply_text("No history yet.")
        return

    lines = ["📅 *Monthly History*", ""]
    for m in months:
        icon = "🟢" if m["status"] == "active" else "⚪"
        balance = db.get_balance(m["id"])
        lines.append(f"{icon} *{month_label(m['year'], m['month'])}*")
        lines.append(f"   Salary: {fmt(m['salary'])}  |  Balance: {fmt(balance)}")
        lines.append("")

    await update.message.reply_text("\n".join(lines).strip(), parse_mode="Markdown")


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🖥️ Open your dashboard:\n`http://localhost:{DASHBOARD_PORT}`\n\n"
        "_Make sure the app is running._",
        parse_mode="Markdown",
    )


# ── Message handler ────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    now = uae_now()

    # ── +Salary ────────────────────────────────────────────────────────────────
    salary_match = re.match(r"^\+[Ss]alary\s+([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if salary_match:
        amount = float(salary_match.group(1).replace(",", ""))

        # Close the currently active month (if any) and send its report
        prev = db.get_active_month()
        if prev:
            month_data = db.get_month_details(prev["id"])
            db.close_month(prev["id"])
            report = build_report(month_data)
            await update.message.reply_text(
                f"📅 Closing *{month_label(prev['year'], prev['month'])}*…\n\n{report}\n\n"
                f"_Report saved. Starting new month now._",
                parse_mode="Markdown",
            )
            # Always advance to the NEXT month in sequence, regardless of calendar date
            if prev["month"] == 12:
                new_year, new_month = prev["year"] + 1, 1
            else:
                new_year, new_month = prev["year"], prev["month"] + 1
        else:
            # First ever salary — use today's calendar month
            new_year, new_month = now.year, now.month

        # Open new month
        month_id = db.create_or_get_month(new_year, new_month, amount)
        db.add_fixed_costs(month_id, FIXED_COSTS)

        fixed_total = sum(FIXED_COSTS.values())
        balance = amount - fixed_total

        lines = [
            f"✅ *Salary recorded: {fmt(amount)}*",
            "",
            f"📌 *Auto-deducted fixed costs:*",
            *[f"  • {name}: {fmt(cost)}" for name, cost in FIXED_COSTS.items()],
            f"  ─ Total: {fmt(fixed_total)}",
            "",
            f"💵 *Available balance: {fmt(balance)}*",
            "",
            f"📅 *{month_label(new_year, new_month)}* is now active.",
        ]
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── Expense: "food 150" / "spinneys 300 weekly" / "+kfc 80 zayed rd" ─────
    # First word = category; extra words before amount + words after = description
    exp_match = re.match(
        r"^\+?([a-zA-Z][a-zA-Z\s\-'&]*?)\s+([\d,]+(?:\.\d+)?)\s*(.*)?$", text
    )
    if exp_match and not text.startswith("/"):
        pre = exp_match.group(1).strip()
        amount = float(exp_match.group(2).replace(",", ""))
        post = (exp_match.group(3) or "").strip()

        pre_words = pre.split()
        raw_category = pre_words[0].lower()
        extra = " ".join(pre_words[1:])
        description = " ".join(filter(None, [extra, post]))

        # Normalise via aliases; keep user's word if no alias matches
        category = CATEGORY_ALIASES.get(raw_category, raw_category)

        active = db.get_active_month()
        if not active:
            await update.message.reply_text(
                "⚠️ No active month. Record your salary first:\n`+Salary 15000`",
                parse_mode="Markdown",
            )
            return

        db.add_expense(active["id"], category, amount, description, now.date())
        balance = db.get_balance(active["id"])

        emoji = EXPENSE_CATEGORIES.get(category, "💸")
        low_warning = "\n\n⚠️ *Balance is running low!*" if balance < 500 else ""
        desc_line = f"\n📝 _{escape_md(description)}_" if description else ""

        await update.message.reply_text(
            f"✅ {emoji} *{category.capitalize()}* — {fmt(amount)}{desc_line}\n"
            f"💰 Remaining: *{fmt(balance)}*{low_warning}",
            parse_mode="Markdown",
        )
        return

    # ── Fallback ───────────────────────────────────────────────────────────────
    await update.message.reply_text(
        "❓ Not sure what you mean. Try:\n"
        "• `+Salary 15000` — record salary\n"
        "• `food 150` — add expense\n"
        "• /help — all commands",
        parse_mode="Markdown",
    )


# ── Delete / undo ──────────────────────────────────────────────────────────────

async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = db.get_active_month()
    if not active:
        await update.message.reply_text("⚠️ No active month. Nothing to delete.")
        return

    args = context.args

    # /delete  or  /delete last  → remove the most recent expense
    if not args or (len(args) == 1 and args[0].lower() == "last"):
        expense = db.get_last_expense(active["id"])
        if not expense:
            await update.message.reply_text("No expenses logged yet.")
            return
        db.delete_expense(expense["id"])
        balance = db.get_balance(active["id"])
        emoji = EXPENSE_CATEGORIES.get(expense["category"], "💸")
        desc = f'\n📝 _{escape_md(expense["description"])}_' if expense["description"] else ""
        await update.message.reply_text(
            f"🗑 *Deleted — last entry:*\n"
            f"{emoji} {expense['category'].capitalize()} — {fmt(expense['amount'])}{desc}\n\n"
            f"💰 Balance restored to: *{fmt(balance)}*",
            parse_mode="Markdown",
        )
        return

    # /delete <category> <amount>
    if len(args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "• `/delete food 50` — remove most recent match\n"
            "• `/delete savings 2000`\n"
            "• `/delete last` — remove last entry\n"
            "• `/undo` — same as /delete last",
            parse_mode="Markdown",
        )
        return

    raw_cat = args[0].lower()
    try:
        amount = float(args[1].replace(",", ""))
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount. Example: `/delete food 50`",
            parse_mode="Markdown",
        )
        return

    category = CATEGORY_ALIASES.get(raw_cat, raw_cat)

    expense = db.find_expense(active["id"], category, amount)
    if not expense:
        await update.message.reply_text(
            f"❌ No *{category}* entry of {fmt(amount)} found in "
            f"{month_label(active['year'], active['month'])}.\n"
            f"Use /summary to see all logged expenses.",
            parse_mode="Markdown",
        )
        return

    db.delete_expense(expense["id"])
    balance = db.get_balance(active["id"])
    emoji = EXPENSE_CATEGORIES.get(category, "💸")
    desc = f'\n📝 _{expense["description"]}_' if expense["description"] else ""

    await update.message.reply_text(
        f"🗑 *Deleted:*\n"
        f"{emoji} {category.capitalize()} — {fmt(amount)}{desc}\n\n"
        f"💰 Balance restored to: *{fmt(balance)}*",
        parse_mode="Markdown",
    )


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = db.get_active_month()

    # ── Undo last expense if one exists ───────────────────────────────────────
    if active:
        expense = db.get_last_expense(active["id"])
        if expense:
            db.delete_expense(expense["id"])
            balance = db.get_balance(active["id"])
            emoji = EXPENSE_CATEGORIES.get(expense["category"], "💸")
            desc = f'\n📝 _{escape_md(expense["description"])}_' if expense["description"] else ""
            await update.message.reply_text(
                f"↩️ *Undone — last entry:*\n"
                f"{emoji} {expense['category'].capitalize()} — {fmt(expense['amount'])}{desc}\n\n"
                f"💰 Balance restored to: *{fmt(balance)}*",
                parse_mode="Markdown",
            )
            return

    # ── No expenses in active month → undo the salary (month transition) ──────
    if active:
        prev = db.get_last_closed_month()
        db.delete_month_cascade(active["id"])
        if prev:
            db.reopen_month(prev["id"])
            await update.message.reply_text(
                f"↩️ *Salary entry undone.*\n\n"
                f"📅 *{month_label(prev['year'], prev['month'])}* is active again.\n"
                f"💰 Balance: *{fmt(db.get_balance(prev['id']))}*",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "↩️ Salary entry undone. No previous month to restore.",
                parse_mode="Markdown",
            )
        return

    await update.message.reply_text("⚠️ Nothing to undo.")


# ── Entry point ────────────────────────────────────────────────────────────────

def build_application():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set. Add it to your .env file or Render environment variables.")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler(["start", "help"], cmd_start))
    application.add_handler(CommandHandler("balance", cmd_balance))
    application.add_handler(CommandHandler("summary", cmd_summary))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("dashboard", cmd_dashboard))
    application.add_handler(CommandHandler("delete", cmd_delete))
    application.add_handler(CommandHandler("undo", cmd_undo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application


def main():
    application = build_application()
    logger.info("Bot is polling…")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
