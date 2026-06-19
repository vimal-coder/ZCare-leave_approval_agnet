from tools.leave_balance_tool import deduct_leave


def auto_approve(
    employee_id,
    leave_type,
    total_days
):

    deduct_leave(
        employee_id,
        leave_type,
        total_days
    )

    return "APPROVED"