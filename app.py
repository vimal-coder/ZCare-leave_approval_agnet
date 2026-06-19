from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from config import DEFAULT_MANAGER_EMAIL
from schemas.leave_schema import LeaveRequest
from services.leave_processor import process_leave_request
from services.manager_service import approve_leave, reject_leave, ManagerDecision
from db_queries import (
    get_leave_balance, get_leave_history, get_pending_requests,
    get_employee, get_leave_request,
)
from agent.leave_agent import leave_chat

BASE_DIR  = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="ZCare Leave AI Assistant",
    description="Intelligent leave approval automation for ZCare Healthcare",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    history: list = []


# ─────────────────────────────────────────────────────────────────────────────
# Core routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/health")
def health():
    return {"message": "ZCare Leave AI Assistant Running", "status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest):
    return leave_chat(request.message, request.history)


@app.post("/api/chat")
def api_chat(request: ChatRequest):
    return leave_chat(request.message, request.history)


@app.post("/apply-leave")
def apply_leave(data: LeaveRequest):
    return process_leave_request(
        employee_id=data.employee_id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        total_days=data.total_days,
        reason=data.reason,
    )


@app.get("/employees/{employee_id}")
def employee_info(employee_id: int):
    employee = get_employee(employee_id)
    if not employee:
        return {"error": "Employee not found"}
    return {
        "employee_id":   employee[0],
        "employee_code": employee[1],
        "employee_name": employee[2],
        "email":         employee[3],
        "department":    employee[4],
        "manager_email": employee[5],
    }

@app.get("/leave-balance/{employee_id}")
def leave_balance(employee_id: int):
    balance = get_leave_balance(employee_id)
    if not balance:
        return {"error": "Balance not found"}
    return {
        "annual_leave":    balance[0],
        "personal_leave":  balance[1],
        "special_leave":   balance[2],
        "optional_holiday": balance[3],
    }


@app.get("/leave-history/{employee_id}")
def leave_history(employee_id: int):
    history = get_leave_history(employee_id)
    return [
        {
            "request_id":      row[0],
            "leave_type":      row[1],
            "start_date":      str(row[2]),
            "end_date":        str(row[3]),
            "total_days":      row[4],
            "reason":          row[5],
            "status":          row[6],
            "applied_date":    str(row[7]),
            "manager_comments": row[8] if len(row) > 8 and row[8] is not None else "",
        }
        for row in history
    ]


@app.get("/pending-requests")
def pending_requests(manager_email: str = DEFAULT_MANAGER_EMAIL):
    pending = get_pending_requests(manager_email)
    return [
        {
            "request_id":   row[0],
            "employee_id":  row[1],
            "employee_name": row[2],
            "email":        row[3],
            "leave_type":   row[4],
            "start_date":   str(row[5]),
            "end_date":     str(row[6]),
            "total_days":   row[7],
            "reason":       row[8],
            "status":       row[9],
        }
        for row in pending
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Manager confirmation page builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_confirmation_page(
    action: str,              # "approved" | "rejected" | "error"
    request_id: int,
    leave_info: dict | None = None,
    error_message: str = "",
    was_exceptional: bool = False,    # True when original status was PENDING (exceptional)
    exception_count: int | None = None,  # count AFTER recording this exception
) -> HTMLResponse:
    """
    Render a rich HTML confirmation page after manager approves or rejects.
    Shows full leave details, exception counter (for exceptional cases), and next-steps.
    """
    timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")

    action_configs = {
        "approved": {
            "accent": "#1a7a4a",
            "icon": "✔",
            "heading": "Leave Request Approved",
            "badge_color": "#1a7a4a",
            "badge_text": "APPROVED",
            "sub_msg": "The leave has been approved and the employee's balance updated. A confirmation email has been sent to the employee.",
            "next_steps": [
                "Leave balance has been deducted for this period.",
                "The employee has been notified via email with an approval confirmation.",
            ]
        },
        "rejected": {
            "accent": "#c0392b",
            "icon": "✘",
            "heading": "Leave Request Rejected",
            "badge_color": "#c0392b",
            "badge_text": "REJECTED",
            "sub_msg": "The leave request has been rejected. The employee has been notified with your decision.",
            "next_steps": [
                "No leave balance has been deducted.",
                "The employee has been notified via email.",
                "No exception event has been recorded.",
                "The employee may reapply or contact HR for assistance.",
            ]
        },
        "error": {
            "accent": "#e67e22",
            "icon": "⚠",
            "heading": "Action Could Not Be Completed",
            "badge_color": "#e67e22",
            "badge_text": "ERROR",
            "sub_msg": error_message or "This request could not be processed.",
            "next_steps": [
                "The request may have already been actioned.",
                "Check the Manager Dashboard for current status.",
            ]
        }
    }

    cfg = action_configs.get(action, action_configs["error"])
    accent = cfg["accent"]
    icon = cfg["icon"]
    heading = cfg["heading"]
    badge_color = cfg["badge_color"]
    badge_text = cfg["badge_text"]
    sub_msg = error_message if (action == "error" and error_message) else cfg["sub_msg"]
    next_steps = list(cfg["next_steps"])

    if action == "approved" and was_exceptional:
        next_steps.append("This approval has been recorded as an exceptional case event.")
        if exception_count == 1:
            next_steps.append(
                "⚠ Employee has now used 1 of 2 allowed exceptions — "
                "a warning email has been sent to them."
            )
        elif exception_count is not None and exception_count >= 2:
            next_steps.append(
                "🚨 Employee has now used 2 of 2 exceptions — "
                "any further short-notice requests will be automatically ESCALATED."
            )

    # ── Exception status block (only for exceptional case approvals) ──────────
    exception_block = ""
    if action == "approved" and was_exceptional and exception_count is not None:
        used   = exception_count
        empty  = max(0, 2 - used)

        if used == 0:
            exc_color   = "#1a6fb5"
            exc_label   = "No exceptions recorded yet"
            exc_message = "Employee has no prior exceptional leave events this year."
        elif used == 1:
            exc_color   = "#e6a817"
            exc_label   = "1 of 2 Exceptions Used — Warning Issued"
            exc_message = (
                "A warning email has been automatically sent to the employee. "
                "If they submit one more short-notice request and it is approved, "
                "<strong>future requests will be ESCALATED</strong> for disciplinary review."
            )
        else:
            exc_color   = "#c0392b"
            exc_label   = f"{used} Exceptions Recorded — Escalation Threshold Reached"
            exc_message = (
                "The employee has reached the exception limit. Any further "
                "short-notice leave requests will be <strong>automatically ESCALATED</strong> "
                "for disciplinary review."
            )

        circles_html = (
            f'<span style="font-size:22px;color:{exc_color};letter-spacing:6px;">'
            + "&#11044; " * used
            + "&#9711; " * empty
            + "</span>"
        )

        exception_block = f"""
        <div class="section-label">Exceptional Case — Exception Tracker</div>
        <div class="exception-box" style="border-color:{exc_color};">
            <div class="exc-header" style="background:{exc_color};">
                <span class="exc-title">&#9888; {exc_label}</span>
            </div>
            <div class="exc-body">
                <div class="exc-circles">
                    {circles_html}
                    <span class="exc-count">{used} of 2 exceptions used this year</span>
                </div>
                <p class="exc-msg">{exc_message}</p>
            </div>
        </div>
        """

    # ── Leave details table ───────────────────────────────────────────────────
    details_table = ""
    if leave_info:
        emp_code  = leave_info.get("employee_code", "—")
        emp_name  = leave_info.get("employee_name", "—")
        emp_email = leave_info.get("employee_email", "—")
        l_type    = leave_info.get("leave_type", "—")
        s_date    = leave_info.get("start_date", "—")
        e_date    = leave_info.get("end_date", "—")
        t_days    = leave_info.get("total_days", "—")
        reason    = leave_info.get("reason", "No reason provided")

        details_table = f"""
        <div class="section-label">Leave Request Details</div>
        <table class="details-table">
            <tr><th>Leave Application ID</th><td>#{request_id}</td></tr>
            <tr><th>Employee Code</th><td>{emp_code}</td></tr>
            <tr><th>Employee Name</th><td><strong>{emp_name}</strong></td></tr>
            <tr><th>Employee Email</th><td>{emp_email}</td></tr>
            <tr><th>Leave Type</th><td>{l_type}</td></tr>
            <tr><th>From Date</th><td>{s_date}</td></tr>
            <tr><th>To Date</th><td>{e_date}</td></tr>
            <tr><th>Total Duration</th><td>{t_days} Day(s)</td></tr>
            <tr><th>Reason</th><td>{reason}</td></tr>
            <tr>
                <th>Decision</th>
                <td><span class="badge" style="background:{badge_color};">{badge_text}</span></td>
            </tr>
            <tr><th>Actioned At</th><td>{timestamp}</td></tr>
        </table>
        """

    # ── Next steps ────────────────────────────────────────────────────────────
    steps_html = "".join(f"<li>{s}</li>" for s in next_steps)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZCare — {heading}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            background: #f0f4f8;
            min-height: 100vh;
            padding: 32px 16px;
            color: #1a202c;
        }}
        .topbar {{
            max-width: 700px;
            margin: 0 auto 20px;
        }}
        .brand-name {{ font-size: 20px; font-weight: 700; color: #003366; }}
        .brand-sub  {{ font-size: 12px; color: #718096; margin-top: 2px; }}

        .card {{
            max-width: 700px;
            margin: 0 auto;
            background: #fff;
            border-radius: 16px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.08);
            overflow: hidden;
        }}
        .result-header {{
            background: {accent};
            padding: 28px 32px;
            display: flex;
            align-items: center;
            gap: 18px;
        }}
        .result-icon {{
            width: 58px; height: 58px;
            border-radius: 50%;
            background: rgba(255,255,255,0.25);
            display: flex; align-items: center; justify-content: center;
            font-size: 26px; color: #fff; font-weight: 700; flex-shrink: 0;
        }}
        .result-title {{ color: #fff; }}
        .result-title h1 {{ font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }}
        .result-title p  {{ font-size: 13.5px; opacity: 0.9; line-height: 1.5; }}

        .card-body {{ padding: 28px 32px; }}

        .section-label {{
            font-size: 11px; font-weight: 700;
            text-transform: uppercase; letter-spacing: 1px;
            color: #718096; margin-bottom: 10px; margin-top: 24px;
        }}
        .section-label:first-child {{ margin-top: 0; }}

        .details-table {{
            width: 100%; border-collapse: collapse;
            font-size: 13.5px; margin-bottom: 4px;
        }}
        .details-table th {{
            background: #f7fafc; border: 1px solid #e2e8f0;
            padding: 9px 14px; text-align: left;
            font-weight: 600; color: #4a5568; width: 38%; white-space: nowrap;
        }}
        .details-table td {{
            border: 1px solid #e2e8f0; padding: 9px 14px; color: #2d3748;
        }}
        .badge {{
            display: inline-block; padding: 3px 12px;
            border-radius: 100px; font-size: 11.5px;
            font-weight: 700; color: #fff; letter-spacing: 0.5px;
        }}

        /* ── Exception tracker box ── */
        .exception-box {{
            border: 1.5px solid #ccc;
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 4px;
        }}
        .exc-header {{
            padding: 10px 16px;
            color: #fff;
            font-weight: 700;
            font-size: 13px;
        }}
        .exc-body {{
            padding: 14px 16px;
            background: #fffdf5;
        }}
        .exc-circles {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }}
        .exc-count {{
            font-size: 12px;
            color: #555;
        }}
        .exc-msg {{
            font-size: 13px;
            color: #3a3a3a;
            line-height: 1.6;
        }}

        .next-steps {{
            background: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 16px 20px;
            margin-top: 8px;
        }}
        .next-steps ul {{ margin: 0; padding-left: 20px; }}
        .next-steps li {{
            font-size: 13.5px; color: #4a5568;
            margin-bottom: 6px; line-height: 1.5;
        }}
        .next-steps li:last-child {{ margin-bottom: 0; }}

        .footer-links {{
            display: flex; gap: 12px; flex-wrap: wrap;
            margin-top: 28px; padding-top: 20px;
            border-top: 1px solid #e2e8f0;
        }}
        .btn {{
            display: inline-block; padding: 10px 20px;
            border-radius: 8px; font-size: 13.5px; font-weight: 600;
            text-decoration: none; transition: opacity 0.15s;
        }}
        .btn:hover {{ opacity: 0.85; }}
        .btn-primary {{ background: {accent}; color: #fff; }}
        .btn-secondary {{ background: #edf2f7; color: #2d3748; }}
        .already-done {{
            text-align: center; padding: 20px 0 8px;
            color: #718096; font-size: 13.5px;
        }}
    </style>
</head>
<body>
    <div class="topbar">
        <div class="brand-name">ZCare</div>
        <div class="brand-sub">Healthcare Leave Management System</div>
    </div>

    <div class="card">
        <div class="result-header">
            <div class="result-icon">{icon}</div>
            <div class="result-title">
                <h1>{heading}</h1>
                <p>{sub_msg}</p>
            </div>
        </div>

        <div class="card-body">

            {details_table if details_table else f'<p class="already-done">{error_message}</p>'}

            {exception_block}

            <div class="section-label">What Happens Next</div>
            <div class="next-steps">
                <ul>{steps_html}</ul>
            </div>

            <div class="footer-links">
                <a href="/" class="btn btn-primary">Go to ZCare Dashboard</a>
                <a href="/pending-requests" class="btn btn-secondary">View Pending Requests</a>
            </div>

        </div>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html)


# ─────────────────────────────────────────────────────────────────────────────
# Manager action endpoints (GET — triggered from email links)
# ─────────────────────────────────────────────────────────────────────────────

def _get_leave_details(request_id: int) -> dict | None:
    """Helper to fetch and format employee and leave details for confirmation pages."""
    leave_row = get_leave_request(request_id)
    if not leave_row:
        return None
    _, employee_id, leave_type, start_date, end_date, total_days, reason, _, _ = leave_row
    employee = get_employee(employee_id)
    if not employee:
        return None
    return {
        "employee_code":  employee[1],
        "employee_name":  employee[2],
        "employee_email": employee[3],
        "leave_type":     leave_type,
        "start_date":     str(start_date),
        "end_date":       str(end_date),
        "total_days":     total_days,
        "reason":         reason or "No reason provided",
    }


@app.get("/manager/approve/{request_id}")
def manager_approve(request_id: int):
    leave_info = _get_leave_details(request_id)
    result = approve_leave(request_id)

    if result.get("status") in ("Approved", "APPROVED"):
        return _build_confirmation_page(
            action          = "approved",
            request_id      = request_id,
            leave_info      = leave_info,
            was_exceptional = result.get("was_exceptional", False),
            exception_count = result.get("exception_count"),
        )

    return _build_confirmation_page(
        action        = "error",
        request_id    = request_id,
        leave_info    = leave_info,
        error_message = result.get("message", "Unable to approve this request."),
    )


@app.get("/manager/reject/{request_id}")
def manager_reject(request_id: int):
    leave_info = _get_leave_details(request_id)
    result = reject_leave(request_id)

    if result.get("status") in ("Rejected", "REJECTED"):
        return _build_confirmation_page(
            action     = "rejected",
            request_id = request_id,
            leave_info = leave_info,
        )

    return _build_confirmation_page(
        action        = "error",
        request_id    = request_id,
        leave_info    = leave_info,
        error_message = result.get("message", "Unable to reject this request."),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Manager action endpoints (POST — for API / programmatic use)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/manager/approve/{request_id}")
def manager_approve_post(request_id: int, decision: ManagerDecision = ManagerDecision()):
    return approve_leave(request_id, decision.manager_email, decision.comments)


@app.post("/manager/reject/{request_id}")
def manager_reject_post(request_id: int, decision: ManagerDecision = ManagerDecision()):
    return reject_leave(request_id, decision.manager_email, decision.comments)


# ─────────────────────────────────────────────────────────────────────────────
# Email Action Route Aliases (GET — mapping /leave/* to /manager/*)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/leave/approve/{request_id}")
def leave_approve_alias(request_id: int):
    return manager_approve(request_id)


@app.get("/leave/reject/{request_id}")
def leave_reject_alias(request_id: int):
    return manager_reject(request_id)
