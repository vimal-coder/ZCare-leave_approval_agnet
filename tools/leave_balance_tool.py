from database import get_connection


def deduct_leave(employee_id, leave_type, days):

    conn = get_connection()
    cur = conn.cursor()

    column_map = {
        "Annual Leave": "annual_leave",
        "Personal Leave": "personal_leave",
        "Special Leave": "special_leave",
        "Optional Holiday": "optional_holiday"
    }

    column = column_map[leave_type]

    query = f"""
        UPDATE leave_balances
        SET {column} = {column} - %s
        WHERE employee_id = %s
    """

    cur.execute(query, (days, employee_id))

    conn.commit()

    cur.close()
    conn.close()