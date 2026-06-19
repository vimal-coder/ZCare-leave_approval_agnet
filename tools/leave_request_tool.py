from database import get_connection


def create_leave_request(
    employee_id,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason,
    status
):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO leave_requests(
            employee_id,
            leave_type,
            start_date,
            end_date,
            total_days,
            reason,
            status
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s)
        RETURNING request_id
    """,
    (
        employee_id,
        leave_type,
        start_date,
        end_date,
        total_days,
        reason,
        status
    ))

    request_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return request_id