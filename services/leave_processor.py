from datetime import datetime

from db_queries import (
    get_employee,
    get_leave_balance,
    get_exception_count,
    record_exception,
)
from tools.leave_request_tool import create_leave_request
from tools.leave_balance_tool import deduct_leave
from services.email_services import notify_leave_confirmed

VALID_LEAVE_TYPES = [
    "Annual Leave",
    "Personal Leave",
    "Special Leave",
    "Optional Holiday",
]


def _send_confirmation_emails(
    employee_email,
    employee_name,
    employee_code,
    manager_email,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason,
    status,
    request_id,
    exception_count=0,
):
    return notify_leave_confirmed(
        employee_email=employee_email,
        employee_name=employee_name,
        manager_email=manager_email,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        total_days=total_days,
        reason=reason,
        status=status,
        request_id=request_id,
        employee_code=employee_code,
        exception_count=exception_count,
    )


def process_leave_request(
    employee_id,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason,
):
    # ── 1. Validate employee ──────────────────────────────────────────────────
    employee = get_employee(employee_id)
    if not employee:
        return {
            "status": "Error",
            "message": f"Employee ID {employee_id} not found",
        }

    _, employee_code, employee_name, employee_email, _, manager_email = employee

    # ── 2. Validate leave type ────────────────────────────────────────────────
    if leave_type not in VALID_LEAVE_TYPES:
        return {
            "status": "Error",
            "message": f"Invalid leave type. Choose from: {', '.join(VALID_LEAVE_TYPES)}",
        }

    # ── 3. Check leave balance ────────────────────────────────────────────────
    balances = get_leave_balance(employee_id)
    if not balances:
        return {
            "status": "Error",
            "message": "Leave balance record not found for employee",
        }

    leave_map = {
        "Annual Leave": balances[0],
        "Personal Leave": balances[1],
        "Special Leave": balances[2],
        "Optional Holiday": balances[3],
    }
    available_balance = leave_map[leave_type]

    # ── 4. Determine Status & Balance Deduction ──────────────────────────────
    status = None
    message = ""
    exception_count = 0
    is_emergency = reason and "emergency" in str(reason).lower()

    if is_emergency:
        status = "AUTO_APPROVED"
        message = "Emergency leave automatically approved and recorded as an exception."
        deduct_leave(employee_id, leave_type, total_days)
    elif available_balance < total_days:
        status = "LOP"
        message = (
            "Insufficient leave balance. Recorded as Loss of Pay (LOP). "
            "Your manager has been notified and will review the request."
        )
    elif total_days <= 3:
        status = "AUTO_APPROVED"
        message = "Leave auto-approved (3 days or less)."
        deduct_leave(employee_id, leave_type, total_days)
    else:
        # Check advance notice
        start = datetime.strptime(start_date, "%Y-%m-%d")
        today = datetime.today()
        notice_days = (start - today).days

        if notice_days >= 28:
            status = "AUTO_APPROVED"
            message = f"Leave auto-approved ({notice_days} days advance notice provided)."
            deduct_leave(employee_id, leave_type, total_days)
        else:
            exception_count = get_exception_count(employee_id)
            if exception_count < 2:
                status = "PENDING"
                message = "Leave request forwarded to manager for approval."
            else:
                status = "ESCALATED"
                message = (
                    "Exception limit exceeded (2+ short-notice requests this year). "
                    "Request escalated for disciplinary review."
                )

    # ── 5. Save and Notify ────────────────────────────────────────────────────
    request_id = create_leave_request(
        employee_id,
        leave_type,
        start_date,
        end_date,
        total_days,
        reason,
        status,
    )

    if is_emergency:
        record_exception(employee_id, request_id)

    email_status = _send_confirmation_emails(
        employee_email,
        employee_name,
        employee_code,
        manager_email,
        leave_type,
        start_date,
        end_date,
        total_days,
        reason,
        status,
        request_id,
        exception_count=exception_count,
    )

    response = {
        "request_id": request_id,
        "status": status,
        "message": message,
        "employee_name": employee_name,
        "email_sent": email_status,
    }
    if status == "LOP":
        response["available_balance"] = available_balance
    elif status in ("PENDING", "ESCALATED"):
        response["exception_count"] = exception_count

    return response
