from pydantic import BaseModel


class LeaveRequest(BaseModel):
    employee_id: int
    leave_type: str
    start_date: str
    end_date: str
    total_days: int
    reason: str