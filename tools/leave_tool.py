from services.leave_processor import process_leave_request


def apply_leave_tool(
    employee_id,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason
):

    result = process_leave_request(
        employee_id,
        leave_type,
        start_date,
        end_date,
        total_days,
        reason
    )

    return result