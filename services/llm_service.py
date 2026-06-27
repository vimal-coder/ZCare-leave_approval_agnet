from langchain_core.messages import HumanMessage, SystemMessage
from config import GROQ_MODEL, GROQ_API_KEY
from dotenv import load_dotenv
import os
load_dotenv()
_llm = None

def get_llm():
    """Lazily load and initialize the ChatGroq model instance on first use."""
    global _llm
    if _llm is None:
       from langchain_groq import ChatGroq
       _llm = ChatGroq(model=GROQ_MODEL,
        temperature=0,
        api_key=os.getenv("GROQ_API_KEY"))
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
    system_prompt = (
        "You are the ZCare AI Leave Approval Assistant. Your task is to write a polite, "
        "professional, and empathetic email body explaining why an employee's leave request has been rejected.\n\n"
        "Guidelines:\n"
        "1. Start directly with the explanation. Do NOT include a salutation or greeting (e.g., 'Dear Employee' or 'Dear Name'), "
        "as this is already handled by the email template.\n"
        "2. Do NOT include any subject lines, headers, preambles, or markdown wrappers (like backticks or 'Here is the email text').\n"
        "3. Maintain an empathetic, professional, and supportive tone.\n"
        "4. Clearly state the leave request details and the specific reason for rejection based on the manager's comments.\n"
        "5. Offer a polite concluding sentence wishing them well or offering guidance on next steps.\n"
        "6. Do NOT include a signature or sign-off line (such as 'Sincerely, ZCare' or 'Best regards'), as the template footer handles this.\n"
        "7. Return ONLY the body text of the explanation itself."
    )
    
    human_prompt = (
        "Please generate the rejection email body based on the following leave request details:\n\n"
        f"- Employee Name: {employee_name}\n"
        f"- Leave Type: {leave_type}\n"
        f"- Start Date: {start_date}\n"
        f"- End Date: {end_date}\n"
        f"- Total Days: {total_days}\n"
        f"- Employee's Reason for Leave: {reason or 'No reason provided'}\n"
        f"- Manager's Rejection Comments: {comments or 'No specific reason provided'}"
    )

    response = get_llm().invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ])
    return response.content.strip()
