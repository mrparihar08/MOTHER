import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.api.models.vitya import Expense
from backend.chats.services.receipt_service import parse_receipt_image

logger = logging.getLogger(__name__)


def handle_receipt_scan(
    image_bytes: bytes,
    mime_type: str,
    db: Session,
    current_user: Any,
    auto_save: bool = True,
) -> Dict[str, Any]:
    """
    Scans a receipt image, parses financial metadata, and optionally logs it directly into Expenses.
    """
    data = parse_receipt_image(image_bytes, mime_type=mime_type)
    if not data.get("success"):
        return {
            "type": "text",
            "content": f"⚠️ Receipt scan failed: {data.get('error', 'Could not read text from receipt image.')}",
            "error": True,
        }

    merchant = data.get("merchant") or "Store Purchase"
    amount = float(data.get("amount", 0.0))
    category = data.get("category") or "Shopping"
    description = data.get("description") or f"Receipt purchase at {merchant}"
    items = data.get("items", [])
    raw_date = data.get("date")

    parsed_date = datetime.now(timezone.utc)
    if raw_date:
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            pass

    expense_id = None
    if auto_save and amount > 0:
        try:
            expense_record = Expense(
                amount=amount,
                category=category,
                description=description,
                date=parsed_date,
                user_id=current_user.id,
            )
            db.add(expense_record)
            db.commit()
            db.refresh(expense_record)
            expense_id = expense_record.id
        except Exception as e:
            db.rollback()
            logger.exception("Failed to auto-save receipt expense: %s", e)

    # Format structured message
    lines = [
        f"🧾 **Receipt Scanned & Logged:**\n",
        f"• **Merchant:** {merchant}",
        f"• **Total Amount:** ₹{amount:,.2f}",
        f"• **Category:** {category}",
        f"• **Date:** {parsed_date.strftime('%d %B %Y')}",
    ]

    if items:
        lines.append("\n**Detected Items:**")
        for itm in items[:6]:
            name = itm.get("name", "Item")
            price = itm.get("price")
            qty = itm.get("qty", 1)
            price_str = f" - ₹{float(price):,.2f}" if price else ""
            qty_str = f" (x{qty})" if qty and int(qty) > 1 else ""
            lines.append(f"• {name}{qty_str}{price_str}")

    if expense_id:
        lines.append(f"\n✅ *Expense record #{expense_id} created in your account.*")

    return {
        "type": "receipt",
        "content": "\n".join(lines),
        "data": {
            "expense_id": expense_id,
            "merchant": merchant,
            "amount": amount,
            "category": category,
            "date": parsed_date.isoformat(),
            "items": items,
        },
    }
