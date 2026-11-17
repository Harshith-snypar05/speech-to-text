"""Invoice email sent after a confirmed payment (Pro subscription or add-on).

The amounts come from the stored payment row (the provider-confirmed total, GST included) and are split back into the
catalogue price and the GST part, so the invoice always adds up to what was charged. Delivery goes through the same
provider layer as the verification mails and is logged to `email_deliveries`; a mail failure never fails the webhook.
"""
import datetime as dt
import html
import logging
import time
from dataclasses import dataclass

from . import email_providers as ep
from .config import get_settings
from .plans import ADDON_MINUTES, GST_RATE, PLANS, PRO

logger = logging.getLogger(__name__)

SELLER = "Snypar Tech"
SUPPORT = "info@scriptliv.com"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


@dataclass
class Invoice:
    number: str
    issued_at: float
    customer_name: str
    customer_email: str
    description: str
    detail: str
    net: float          # amount before GST, in rupees
    gst: float
    total: float
    currency: str
    method: str
    reference: str
    period: str | None
    sandbox: bool
    billing: dict


def inr(v: float) -> str:
    return f"₹{v:,.2f}"


def _fmt_date(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, IST).strftime("%d %b %Y")


def split_gst(total: float) -> tuple[float, float]:
    net = round(total / (1 + GST_RATE), 2)
    return net, round(total - net, 2)


def build(user: dict, payment: dict, sub: dict | None, billing: dict | None = None, seq: int = 1) -> Invoice:
    total = payment["amount_cents"] / 100
    net, gst = split_gst(total)
    addon = payment["description"].lower().startswith("add-on")
    issued = payment["created_at"]
    if addon:
        detail = f"{ADDON_MINUTES:,} extra transcription minutes. Valid until the end of your current plan period."
        period = None
    else:
        p = PLANS[PRO]
        detail = f"{p.included_minutes:,} minutes every month, up to {p.max_session_minutes // 60} hours per session."
        period = f"{_fmt_date(sub['period_start'])} to {_fmt_date(sub['period_end'])}" if sub else None
    return Invoice(
        number=f"SL-{dt.datetime.fromtimestamp(issued, IST).strftime('%Y%m')}-{seq:04d}", issued_at=issued,
        customer_name=(billing or {}).get("name") or user.get("name") or "there", customer_email=user["email"],
        description="ScriptLiv Pro, monthly" if not addon else f"Add-on, {ADDON_MINUTES:,} minutes", detail=detail,
        net=net, gst=gst, total=total, currency=payment.get("currency", "inr"),
        method="Cashfree (sandbox test payment)" if not get_settings().cashfree_live else "Cashfree",
        reference=str(payment.get("provider_ref") or ""), period=period, sandbox=not get_settings().cashfree_live,
        billing=billing or {})


def render_text(i: Invoice) -> str:
    lines = [f"ScriptLiv invoice {i.number}", f"Date: {_fmt_date(i.issued_at)}", "Status: PAID", "",
             f"Billed to: {i.customer_name} <{i.customer_email}>", "",
             f"{i.description}", f"  {i.detail}"]
    if i.period:
        lines.append(f"  Plan period: {i.period}")
    lines += ["", f"Subtotal: {inr(i.net)}", f"GST ({int(GST_RATE * 100)}%): {inr(i.gst)}", f"Total paid: {inr(i.total)}", "",
              f"Payment method: {i.method}", f"Reference: {i.reference}"]
    if i.sandbox:
        lines += ["", "This is a sandbox test payment. No money was charged."]
    lines += ["", f"Questions about this invoice? Write to {SUPPORT}.", f"{SELLER}"]
    return "\n".join(lines)


def render_html(i: Invoice) -> str:
    e = html.escape
    bill = i.billing or {}
    bill_lines = [x for x in (bill.get("company"), bill.get("address"), bill.get("country"),
                              f"Tax ID: {bill['tax_id']}" if bill.get("tax_id") else None) if x]
    bill_html = "".join(f'<div style="color:#6b6585;font-size:13px;line-height:1.5">{e(x)}</div>' for x in bill_lines)
    period = (f'<div style="color:#6b6585;font-size:13px;margin-top:2px">Plan period: {e(i.period)}</div>' if i.period else "")
    sandbox = ('<tr><td style="padding:0 40px 24px"><div style="background:#fff7e6;border:1px solid #f5d28a;border-radius:12px;'
               'padding:12px 16px;color:#8a5a00;font-size:13px;line-height:1.5"><strong>Sandbox test payment.</strong> '
               'This invoice was generated while testing ScriptLiv. No money was charged.</div></td></tr>') if i.sandbox else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice {e(i.number)}</title></head>
<body style="margin:0;padding:0;background:#f1edfb;font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#1f1a33">
<div style="display:none;max-height:0;overflow:hidden">Payment received: {e(inr(i.total))} for {e(i.description)}. Invoice {e(i.number)}.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1edfb;padding:32px 12px"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 8px 30px rgba(91,33,182,.12)">
  <tr><td style="background:#5b21b6;background-image:linear-gradient(135deg,#4c1d95 0%,#7c3aed 55%,#a78bfa 100%);padding:34px 40px 30px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="color:#ffffff;font-size:26px;font-weight:700;letter-spacing:-.3px">ScriptLiv</td>
      <td align="right"><span style="display:inline-block;background:#ffffff;color:#15803d;font-size:12px;font-weight:700;letter-spacing:.8px;padding:6px 14px;border-radius:999px">&#10003; PAID</span></td>
    </tr></table>
    <div style="color:#ede9fe;font-size:14px;margin-top:22px">Payment received</div>
    <div style="color:#ffffff;font-size:38px;font-weight:700;letter-spacing:-1px;margin-top:2px">{e(inr(i.total))}</div>
    <div style="color:#ddd6fe;font-size:14px;margin-top:6px">Thank you, {e(i.customer_name)}. Your receipt is below.</div>
  </td></tr>
  <tr><td style="padding:30px 40px 6px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td valign="top" width="50%"><div style="font-size:11px;letter-spacing:1px;color:#8b84a8;font-weight:700">INVOICE</div>
        <div style="font-size:16px;font-weight:700;margin-top:4px">{e(i.number)}</div>
        <div style="color:#6b6585;font-size:13px;margin-top:2px">Issued {e(_fmt_date(i.issued_at))}</div></td>
      <td valign="top" width="50%"><div style="font-size:11px;letter-spacing:1px;color:#8b84a8;font-weight:700">BILLED TO</div>
        <div style="font-size:16px;font-weight:700;margin-top:4px">{e(i.customer_name)}</div>
        <div style="color:#6b6585;font-size:13px;margin-top:2px">{e(i.customer_email)}</div>{bill_html}</td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:24px 40px 8px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e7e1f7;border-radius:14px;border-collapse:separate;overflow:hidden">
      <tr style="background:#f7f4ff"><td style="padding:12px 18px;font-size:11px;letter-spacing:1px;color:#8b84a8;font-weight:700">DESCRIPTION</td>
        <td align="right" style="padding:12px 18px;font-size:11px;letter-spacing:1px;color:#8b84a8;font-weight:700">AMOUNT</td></tr>
      <tr><td style="padding:18px"><div style="font-size:15px;font-weight:600">{e(i.description)}</div>
        <div style="color:#6b6585;font-size:13px;margin-top:4px;line-height:1.5">{e(i.detail)}</div>{period}</td>
        <td align="right" valign="top" style="padding:18px;font-size:15px;font-weight:600;white-space:nowrap">{e(inr(i.net))}</td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:8px 40px 26px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:6px 0;color:#6b6585;font-size:14px">Subtotal</td><td align="right" style="font-size:14px">{e(inr(i.net))}</td></tr>
      <tr><td style="padding:6px 0;color:#6b6585;font-size:14px">GST ({int(GST_RATE * 100)}%)</td><td align="right" style="font-size:14px">{e(inr(i.gst))}</td></tr>
      <tr><td colspan="2" style="padding-top:8px"><div style="border-top:2px solid #ede9fe"></div></td></tr>
      <tr><td style="padding:12px 0 0;font-size:17px;font-weight:700">Total paid</td>
          <td align="right" style="padding:12px 0 0;font-size:22px;font-weight:700;color:#5b21b6">{e(inr(i.total))}</td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:0 40px 24px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f4ff;border-radius:14px">
      <tr><td style="padding:16px 18px;font-size:13px;color:#6b6585;line-height:1.7">
        <strong style="color:#1f1a33">Payment method</strong><br>{e(i.method)}<br>
        <span style="display:block;margin-top:8px"><strong style="color:#1f1a33">Reference</strong><br>
        <span style="font-family:Consolas,Menlo,monospace;font-size:12px;word-break:break-all">{e(i.reference)}</span></span>
      </td></tr>
    </table>
  </td></tr>
  {sandbox}
  <tr><td align="center" style="padding:0 40px 34px">
    <a href="{e(get_settings().app_base_url.rstrip('/'))}/app/settings" style="display:inline-block;background:#6d28d9;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;padding:13px 28px;border-radius:999px">View your plan and payments</a>
  </td></tr>
  <tr><td style="background:#faf8ff;border-top:1px solid #ece6fb;padding:22px 40px;text-align:center;color:#8b84a8;font-size:12px;line-height:1.7">
    Questions about this invoice? Write to <a href="mailto:{SUPPORT}" style="color:#6d28d9;text-decoration:none">{SUPPORT}</a><br>
    {SELLER} &middot; ScriptLiv live speech-to-text
  </td></tr>
</table></td></tr></table></body></html>"""


def send(db, user: dict, payment: dict, sub: dict | None) -> dict:
    """Build and mail the invoice for a recorded, paid payment. Never raises."""
    try:
        uid = str(user["_id"])
        billing = (db.billing_details.find_one({"user_id": uid}) or {}).get("details", {})
        seq = db.payments.count_documents({"user_id": uid, "status": "paid", "created_at": {"$lte": payment["created_at"]}}) or 1
        inv = build(user, payment, sub, billing, seq)
        msg = ep.Message(to=user["email"], subject=f"Your ScriptLiv invoice {inv.number} ({inr(inv.total)})",
                         text=render_text(inv), html=render_html(inv))
        sent, attempts, err = ep.deliver(msg)
        status = "sent" if sent else ("no_provider" if err == "no_provider" else "failed")
        db.email_deliveries.insert_one({"user_id": uid, "kind": "invoice", "to_domain": user["email"].rsplit("@", 1)[-1].lower(),
                                        "provider": sent.provider if sent else None, "message_id": sent.message_id if sent else None,
                                        "status": status, "attempts": attempts, "error": err, "ts": time.time()})
        return {"delivery": status, "invoice": inv.number}
    except Exception:
        logger.exception("could not send invoice email")
        return {"delivery": "failed"}
