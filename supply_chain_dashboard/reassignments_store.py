"""
In-memory store for order reassignment requests (weather reroute).
Approval flow: submit from alerts page -> email to approver -> approve/reject on reassignments page.
Data is lost on process restart.
"""
import logging
import os
import smtplib
import threading
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

APPROVAL_EMAIL_TO = "noel.hoxie@databricks.com"

_store: List[Dict[str, Any]] = []
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add(
    order_id: str,
    customer_name: str,
    origin_site_id: str,
    origin_name: str,
    reroute_site_id: str,
    reroute_site_name: str,
    delivery_city: str,
    delivery_state: str,
    delivery_due_date: str,
    reroute_plant_new_load: Optional[int] = None,
    reroute_plant_capacity: Optional[int] = None,
    reroute_plant_utilization_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Append a pending reassignment and return it (with id, status, requested_at)."""
    with _lock:
        entry = {
            "id": str(uuid.uuid4()),
            "order_id": order_id,
            "customer_name": customer_name,
            "origin_site_id": origin_site_id,
            "origin_name": origin_name,
            "reroute_site_id": reroute_site_id,
            "reroute_site_name": reroute_site_name,
            "delivery_city": delivery_city,
            "delivery_state": delivery_state,
            "delivery_due_date": delivery_due_date,
            "reroute_plant_new_load": reroute_plant_new_load,
            "reroute_plant_capacity": reroute_plant_capacity,
            "reroute_plant_utilization_pct": reroute_plant_utilization_pct,
            "status": "pending",
            "requested_at": _now_iso(),
            "approved_at": None,
            "email_sent": False,
        }
        _store.append(entry)
        return dict(entry)


def get_all() -> List[Dict[str, Any]]:
    """Return all reassignments (newest first)."""
    with _lock:
        return sorted([dict(e) for e in _store], key=lambda x: x["requested_at"], reverse=True)


def get_by_id(id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for e in _store:
            if e["id"] == id:
                return dict(e)
        return None


def mark_email_sent(ids: List[str]) -> None:
    with _lock:
        for e in _store:
            if e["id"] in ids:
                e["email_sent"] = True


def set_status(id: str, status: str) -> Optional[Dict[str, Any]]:
    """Set status to 'approved' or 'rejected'. Returns updated entry or None."""
    if status not in ("approved", "rejected"):
        return None
    with _lock:
        for e in _store:
            if e["id"] == id:
                if e["status"] != "pending":
                    return dict(e)
                e["status"] = status
                e["approved_at"] = _now_iso()
                return dict(e)
        return None


def send_approval_email(
    reassignments: List[Dict[str, Any]],
    base_url: str,
) -> bool:
    """Send one email to APPROVAL_EMAIL_TO with link to reassignments page. Returns True if sent."""
    if not reassignments:
        return False
    to_addr = APPROVAL_EMAIL_TO
    subject = "Reassignment approval requested: %d order(s)" % len(reassignments)
    review_url = (base_url.rstrip("/") + "/reassignments").replace("http://", "https://") if "localhost" not in base_url else base_url.rstrip("/") + "/reassignments"
    body_plain = (
        "You have %d pending order reassignment(s) for weather-related rerouting.\n\n"
        "Review and approve or reject at:\n%s\n\n"
        "Orders: %s"
    ) % (len(reassignments), review_url, ", ".join(r["order_id"] for r in reassignments))
    body_html = (
        "<p>You have <strong>%d</strong> pending order reassignment(s) for weather-related rerouting.</p>"
        "<p><a href=\"%s\">Review and approve or reject</a></p>"
        "<p>Orders: %s</p>"
    ) % (len(reassignments), review_url, ", ".join(r["order_id"] for r in reassignments))

    server = os.environ.get("MAIL_SERVER")
    port = int(os.environ.get("MAIL_PORT", "587"))
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
    user = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    from_addr = os.environ.get("MAIL_FROM", user or "noreply@localhost")

    if not server or not user or not password:
        log.warning(
            "Mail not configured (MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD). Would send to %s: %s",
            to_addr,
            review_url,
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(body_plain, "plain"))
        msg.attach(MIMEText(body_html, "html"))
        with smtplib.SMTP(server, port) as smtp:
            if use_tls:
                smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to_addr], msg.as_string())
        log.info("Approval email sent to %s for %d reassignment(s)", to_addr, len(reassignments))
        return True
    except Exception as e:
        log.exception("Failed to send approval email: %s", e)
        return False
