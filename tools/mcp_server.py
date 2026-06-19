"""
MCP server exposing ZCare leave management tools.
Run with: python -m tools.mcp_server
"""

from mcp.server.fastmcp import FastMCP
from config import DEFAULT_MANAGER_EMAIL

from db_queries import (
    get_employee,
    get_leave_balance,
    get_leave_history,
    get_pending_requests,
)
from services.leave_processor import process_leave_request
from services.manager_service import approve_leave, reject_leave

mcp = FastMCP("ZCare Leave Management")


@mcp.tool()
def verify_employee(employee_id: int) -> dict:
    """Verify employee exists and return profile details."""
    employee = get_employee(employee_id)
    if not employee:
        return {"found": False}

    return {
        "found": True,
        "employee_id": employee[0],
        "employee_code": employee[1],
        "employee_name": employee[2],
        "email": employee[3],
        "department": employee[4],
        "manager_email": employee[5],
    }


@mcp.tool()
def check_leave_balance(employee_id: int) -> dict:
    """Get leave balances for an employee."""
    balance = get_leave_balance(employee_id)
    if not balance:
        return {"error": "Balance not found"}

    return {
        "annual_leave": balance[0],
        "personal_leave": balance[1],
        "special_leave": balance[2],
        "optional_holiday": balance[3],
    }


@mcp.tool()
def view_leave_history(employee_id: int) -> list:
    """View leave request history for an employee."""
    rows = get_leave_history(employee_id)
    return [
        {
            "request_id": r[0],
            "leave_type": r[1],
            "start_date": str(r[2]),
            "end_date": str(r[3]),
            "total_days": r[4],
            "reason": r[5],
            "status": r[6],
            "manager_comments": r[8] if len(r) > 8 and r[8] is not None else "",
        }
        for r in rows
    ]


@mcp.tool()
def apply_leave(
    employee_id: int,
    leave_type: str,
    start_date: str,
    end_date: str,
    total_days: int,
    reason: str,
) -> dict:
    """Submit and process a leave request."""
    return process_leave_request(
        employee_id, leave_type, start_date, end_date, total_days, reason
    )


@mcp.tool()
def list_pending_approvals(manager_email: str = DEFAULT_MANAGER_EMAIL) -> list:
    """List pending leave requests for a manager."""
    rows = get_pending_requests(manager_email)
    return [
        {
            "request_id": r[0],
            "employee_name": r[2],
            "leave_type": r[4],
            "start_date": str(r[5]),
            "end_date": str(r[6]),
            "total_days": r[7],
            "reason": r[8],
        }
        for r in rows
    ]


@mcp.tool()
def manager_approve_leave(request_id: int, manager_email: str = DEFAULT_MANAGER_EMAIL) -> dict:
    """Manager approves a pending leave request."""
    return approve_leave(request_id, manager_email)


@mcp.tool()
def manager_reject_leave(request_id: int, manager_email: str = DEFAULT_MANAGER_EMAIL) -> dict:
    """Manager rejects a pending leave request."""
    return reject_leave(request_id, manager_email)


if __name__ == "__main__":
    mcp.run()
