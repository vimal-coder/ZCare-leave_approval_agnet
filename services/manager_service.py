from pydantic import BaseModel

from config import DEFAULT_MANAGER_EMAIL
from db_queries import (
    get_leave_request,
    get_employee,
    get_exception_count,
    update_leave_status,
    create_manager_approval,
    record_exception,
)
from tools.leave_balance_tool import deduct_leave
from services.email_services import notify_leave_approved, notify_leave_rejected

# Statuses that a manager can act on (approve or reject)
ACTIONABLE_STATUSES = {"PENDING", "ESCALATED", "LOP"}

# PENDING and LOP requests are considered exceptional cases for recording in the database
EXCEPTIONAL_STATUSES = {"PENDING", "LOP"}


class ManagerDecision(BaseModel):
    manager_email: str = DEFAULT_MANAGER_EMAIL
    comments: str = ""


def approve_leave(request_id, manager_email=DEFAULT_MANAGER_EMAIL, comments=""):
    """
    Manager approves a leave request.

    Exceptional Case Rule:
    - PENDING:   This is a short-notice exceptional leave. Deduct balance,
                 record the exception event, mark APPROVED.
                 After approval, if exception_count reaches 1, the employee
                 is warned that the next short-notice request will be ESCALATED.
    - ESCALATED: Exception limit already exceeded. Deduct balance, mark APPROVED.
                 Do NOT record another exception (already counted on submission).
    - LOP:       Insufficient balance. Just mark APPROVED — no deduction,
                 but record the exception event in exceptional_cases table.
    """
    leave = get_leave_request(request_id)
    if not leave:
        return {"status": "Error", "message": "Leave request not found"}

    _, employee_id, leave_type, start_date, end_date, total_days, reason, status, _ = leave

    if status not in ACTIONABLE_STATUSES:
        return {
            "status": "Error",
            "message": f"Cannot approve request with status '{status}'. "
                       f"Only PENDING, ESCALATED, or LOP requests can be approved.",
        }

    employee = get_employee(employee_id)
    if not employee:
        return {"status": "Error", "message": "Employee not found"}

    _, employee_code, employee_name, employee_email, _, db_manager_email = employee
    notify_manager_email = db_manager_email or manager_email

    # ── Deduct balance ────────────────────────────────────────────────────────
    # LOP: balance is already 0, skip deduction.
    # PENDING / ESCALATED: balance is sufficient, deduct it.
    if status != "LOP":
        deduct_leave(employee_id, leave_type, total_days)

    # ── Update DB ─────────────────────────────────────────────────────────────
    update_leave_status(request_id, "APPROVED")
    create_manager_approval(request_id, notify_manager_email, "APPROVED", comments)

    # ── Record exception (PENDING only) ───────────────────────────────────────
    # PENDING = short-notice exceptional case. Each approval is an exception event.
    # ESCALATED = already triggered because exception limit was reached on submission.
    # LOP = insufficient balance, not a short-notice exception.
    exception_count_after = None
    if status in EXCEPTIONAL_STATUSES:
        record_exception(employee_id, request_id)
        # Fetch updated count so we can warn in the approval email
        exception_count_after = get_exception_count(employee_id)

    # ── Send emails ───────────────────────────────────────────────────────────
    email_status = notify_leave_approved(
        employee_email,
        employee_name,
        notify_manager_email,
        leave_type,
        str(start_date),
        str(end_date),
        total_days,
        reason=reason or "",
        request_id=request_id,
        employee_code=employee_code,
        exception_count_after=exception_count_after,  # triggers warning if count == 1
        was_exceptional=(status in EXCEPTIONAL_STATUSES),
    )

    return {
        "status":            "Approved",
        "message":           "Leave approved by manager",
        "request_id":        request_id,
        "was_exceptional":   status in EXCEPTIONAL_STATUSES,
        "exception_count":   exception_count_after,
        "email_sent":        email_status,
    }


def reject_leave(request_id, manager_email=DEFAULT_MANAGER_EMAIL, comments=""):
    """
    Manager rejects a leave request.
    Status → REJECTED. No balance deduction. No exception recorded.
    """
    leave = get_leave_request(request_id)
    if not leave:
        return {"status": "Error", "message": "Leave request not found"}

    _, employee_id, leave_type, start_date, end_date, total_days, reason, status, _ = leave

    if status not in ACTIONABLE_STATUSES:
        return {
            "status": "Error",
            "message": f"Cannot reject request with status '{status}'. "
                       f"Only PENDING, ESCALATED, or LOP requests can be rejected.",
        }

    employee = get_employee(employee_id)
    if not employee:
        return {"status": "Error", "message": "Employee not found"}

    _, employee_code, employee_name, employee_email, _, db_manager_email = employee
    notify_manager_email = db_manager_email or manager_email

    update_leave_status(request_id, "REJECTED")
    create_manager_approval(request_id, notify_manager_email, "REJECTED", comments)

    # No exception recorded on rejection — rejection is not an exceptional approval

    email_status = notify_leave_rejected(
        employee_email=employee_email,
        employee_name=employee_name,
        manager_email=notify_manager_email,
        leave_type=leave_type,
        start_date=str(start_date),
        end_date=str(end_date),
        total_days=total_days,
        request_id=request_id,
        reason=reason or "",
        comments=comments,
        employee_code=employee_code,
    )

    return {
        "status":      "Rejected",
        "message":     "Leave rejected by manager",
        "request_id":  request_id,
        "email_sent":  email_status,
    }
