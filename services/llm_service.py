from langchain_core.messages import HumanMessage
from config import GROQ_API_KEY, GROQ_MODEL

_llm = None

def get_llm():
    """Lazily load and initialize the ChatGroq model instance on first use."""
    global _llm
    if _llm is None:
        from langchain_groq import ChatGroq
        _llm = ChatGroq(
            model=GROQ_MODEL,
            temperature=0,
            api_key=GROQ_API_KEY
        )
    return _llm

def __getattr__(name: str):
    """Support lazy importing/initialization of module attributes."""
    if name == "llm":
        return get_llm()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def generate_rejection_email(
    employee_name: str,
    leave_type: str,
    start_date: str,
    end_date: str,
    total_days: int,
    reason: str,
    comments: str
) -> str:
    """Generate a professional rejection email using the LLM."""
    prompt = (
        "You are the ZCare AI Leave Approval Assistant. A manager has rejected a leave request from an employee.\n"
        "Please write a polite, professional, and empathetic email to the employee notifying them that their leave request has been rejected.\n\n"
        "Leave Request Details:\n"
        f"- Employee Name: {employee_name}\n"
        f"- Leave Type: {leave_type}\n"
        f"- Start Date: {start_date}\n"
        f"- End Date: {end_date}\n"
        f"- Total Days: {total_days}\n"
        f"- Employee's Reason for Leave: {reason or 'No reason provided'}\n"
        f"- Manager's Rejection Comments: {comments or 'No specific reason provided'}\n\n"
        "The email should be written from the ZCare Leave Management System. It must clearly state the reason for rejection (manager's comments) and offer a polite concluding sentence.\n"
        "Return ONLY the email body text. Do not include any subject lines or other text."
    )
    response = get_llm().invoke([HumanMessage(content=prompt)])
    return response.content.strip()
