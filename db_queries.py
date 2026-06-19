from datetime import date

from database import get_connection


def get_employee(employee_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT employee_id,
               employee_code,
               employee_name,
               email,
               department,
               manager_email
        FROM employees
        WHERE employee_id = %s
    """, (employee_id,))

    employee = cur.fetchone()

    cur.close()
    conn.close()

    return employee


def get_employee_by_email(email):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT employee_id,
               employee_code,
               employee_name,
               email,
               department,
               manager_email
        FROM employees
        WHERE email = %s
    """, (email,))

    employee = cur.fetchone()

    cur.close()
    conn.close()

    return employee


def get_employee_by_code(employee_code):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT employee_id,
               employee_code,
               employee_name,
               email,
               department,
               manager_email
        FROM employees
        WHERE employee_code = %s
    """, (employee_code,))

    employee = cur.fetchone()

    cur.close()
    conn.close()

    return employee


def get_leave_balance(employee_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT annual_leave,
               personal_leave,
               special_leave,
               optional_holiday
        FROM leave_balances
        WHERE employee_id = %s
    """, (employee_id,))

    balance = cur.fetchone()

    cur.close()
    conn.close()

    return balance


def get_exception_count(employee_id, year=None):
    """
    Count the number of exceptional approval events for this employee in the
    given calendar year. Each row in exceptional_cases = one exception event.
    """
    if year is None:
        year = date.today().year

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM exceptional_cases
        WHERE employee_id = %s AND exception_year = %s
    """, (employee_id, year))

    result = cur.fetchone()

    cur.close()
    conn.close()

    return result[0] if result else 0


def record_exception(employee_id, request_id, year=None):
    """
    Insert one row into exceptional_cases to record a single exception event.
    Called when a manager approves a PENDING/ESCALATED/LOP request.
    """
    if year is None:
        year = date.today().year

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO exceptional_cases (employee_id, request_id, exception_year)
        VALUES (%s, %s, %s)
    """, (employee_id, request_id, year))

    conn.commit()
    cur.close()
    conn.close()


# Keep this alias for backward-compat with any callers that used the old name
def increment_exception_count(employee_id, request_id=None, year=None):
    """
    Backward-compatible wrapper. Prefers record_exception when request_id is
    supplied; falls back to inserting with request_id=None (should only happen
    in legacy code paths).
    """
    record_exception(employee_id, request_id, year)


def get_leave_history(employee_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT lr.request_id,
               lr.leave_type,
               lr.start_date,
               lr.end_date,
               lr.total_days,
               lr.reason,
               lr.status,
               lr.applied_date,
               ma.comments
        FROM leave_requests lr
        LEFT JOIN manager_approvals ma ON lr.request_id = ma.request_id
        WHERE lr.employee_id = %s
        ORDER BY lr.request_id DESC
    """, (employee_id,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


def get_pending_requests(manager_email=None):
    """
    Return requests that still need manager action.
    Statuses: PENDING (normal), ESCALATED (2+ exceptions), LOP (insufficient balance).
    """
    conn = get_connection()
    cur = conn.cursor()

    if manager_email:
        cur.execute("""
            SELECT lr.request_id,
                   lr.employee_id,
                   e.employee_name,
                   e.email,
                   lr.leave_type,
                   lr.start_date,
                   lr.end_date,
                   lr.total_days,
                   lr.reason,
                   lr.status,
                   lr.applied_date
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.employee_id
            WHERE lr.status IN ('PENDING', 'ESCALATED', 'LOP')
              AND e.manager_email = %s
            ORDER BY lr.request_id DESC
        """, (manager_email,))
    else:
        cur.execute("""
            SELECT lr.request_id,
                   lr.employee_id,
                   e.employee_name,
                   e.email,
                   lr.leave_type,
                   lr.start_date,
                   lr.end_date,
                   lr.total_days,
                   lr.reason,
                   lr.status,
                   lr.applied_date
            FROM leave_requests lr
            JOIN employees e ON lr.employee_id = e.employee_id
            WHERE lr.status IN ('PENDING', 'ESCALATED', 'LOP')
            ORDER BY lr.request_id DESC
        """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows


def update_leave_status(request_id, status):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE leave_requests
        SET status = %s
        WHERE request_id = %s
    """, (status, request_id))

    conn.commit()

    cur.close()
    conn.close()


def get_leave_request(request_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT request_id,
               employee_id,
               leave_type,
               start_date,
               end_date,
               total_days,
               reason,
               status,
               applied_date
        FROM leave_requests
        WHERE request_id = %s
    """, (request_id,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    return row


def create_manager_approval(request_id, manager_email, decision, comments=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO manager_approvals (
            request_id,
            manager_email,
            decision,
            comments,
            approved_at
        )
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        RETURNING approval_id
    """, (request_id, manager_email, decision, comments))

    approval_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return approval_id


def log_email(request_id, recipient_email, subject, email_status):
    """Insert a row into email_logs after each send attempt."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO email_logs (request_id, recipient_email, subject, email_status)
        VALUES (%s, %s, %s, %s)
    """, (request_id, recipient_email, subject, "SENT" if email_status else "FAILED"))

    conn.commit()
    cur.close()
    conn.close()
