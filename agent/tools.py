from langchain_core.tools import tool
from config import DEFAULT_MANAGER_EMAIL

from db_queries import (
    get_employee,
    get_employee_by_email,
    get_employee_by_code,
    get_leave_balance,
    get_leave_history,
    get_pending_requests,
)
from services.leave_processor import process_leave_request, VALID_LEAVE_TYPES


@tool
def verify_employee(employee_id: int) -> dict:
    """Verify employee exists and return their profile details."""
    employee = get_employee(employee_id)
    if not employee:
        return {"found": False, "message": f"No employee with ID {employee_id}"}

    return {
        "found": True,
        "employee_id": employee[0],
        "employee_code": employee[1],
        "employee_name": employee[2],
        "email": employee[3],
        "department": employee[4],
        "manager_email": employee[5],
    }


@tool
def lookup_employee_by_email(email: str) -> dict:
    """Look up an employee by their email address."""
    employee = get_employee_by_email(email)
    if not employee:
        return {"found": False, "message": f"No employee with email {email}"}

    return {
        "found": True,
        "employee_id": employee[0],
        "employee_code": employee[1],
        "employee_name": employee[2],
        "email": employee[3],
        "department": employee[4],
        "manager_email": employee[5],
    }


@tool
def lookup_employee_by_code(employee_code: str) -> dict:
    """Look up an employee by their employee code (e.g. EMP001)."""
    employee = get_employee_by_code(employee_code)
    if not employee:
        return {"found": False, "message": f"No employee with code {employee_code}"}

    return {
        "found": True,
        "employee_id": employee[0],
        "employee_code": employee[1],
        "employee_name": employee[2],
        "email": employee[3],
        "department": employee[4],
        "manager_email": employee[5],
    }


@tool
def check_leave_balance(employee_id: int) -> dict:
    """Get available leave balances for an employee."""
    employee = get_employee(employee_id)
    if not employee:
        return {"error": f"Employee ID {employee_id} not found"}

    balance = get_leave_balance(employee_id)
    if not balance:
        return {"error": "Leave balance not found"}

    return {
        "employee_id": employee_id,
        "employee_name": employee[2],
        "annual_leave": balance[0],
        "personal_leave": balance[1],
        "special_leave": balance[2],
        "optional_holiday": balance[3],
    }


@tool
def view_leave_history(employee_id: int) -> dict:
    """View past leave requests for an employee."""
    employee = get_employee(employee_id)
    if not employee:
        return {"error": f"Employee ID {employee_id} not found"}

    history = get_leave_history(employee_id)
    records = []
    for row in history:
        records.append({
            "request_id": row[0],
            "leave_type": row[1],
            "start_date": str(row[2]),
            "end_date": str(row[3]),
            "total_days": row[4],
            "reason": row[5],
            "status": row[6],
            "applied_date": str(row[7]),
            "manager_comments": row[8] if len(row) > 8 and row[8] is not None else "",
        })

    return {
        "employee_id": employee_id,
        "employee_name": employee[2],
        "leave_history": records,
    }


@tool
def apply_leave(
    employee_id: int,
    leave_type: str,
    start_date: str,
    end_date: str,
    total_days: int,
    reason: str,
) -> dict:
    """
    Submit a leave request for processing.
    leave_type must be one of: Annual Leave, Personal Leave, Special Leave, Optional Holiday.
    Dates must be in YYYY-MM-DD format.
    """
    return process_leave_request(
        employee_id=employee_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        total_days=total_days,
        reason=reason,
    )


@tool
def list_pending_approvals(manager_email: str = DEFAULT_MANAGER_EMAIL) -> dict:
    """List all pending leave requests awaiting manager approval."""
    pending = get_pending_requests(manager_email)
    records = []
    for row in pending:
        records.append({
            "request_id": row[0],
            "employee_id": row[1],
            "employee_name": row[2],
            "email": row[3],
            "leave_type": row[4],
            "start_date": str(row[5]),
            "end_date": str(row[6]),
            "total_days": row[7],
            "reason": row[8],
            "status": row[9],
            "applied_date": str(row[10]),
        })

    return {"pending_requests": records, "count": len(records)}


LEAVE_TOOLS = [
    verify_employee,
    lookup_employee_by_email,
    lookup_employee_by_code,
    check_leave_balance,
    view_leave_history,
    apply_leave,
    list_pending_approvals,
]

LEAVE_TYPES_INFO = ", ".join(VALID_LEAVE_TYPES)
