from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agent.tools import LEAVE_TOOLS, LEAVE_TYPES_INFO

SYSTEM_PROMPT = f"""You are the ZCare AI Leave Approval Assistant for hospital employees.

Your responsibilities:
1. Help employees apply for leave through natural conversation
2. Verify employee identity before processing requests
3. Check leave balances and leave history when asked
4. Explain leave policies clearly
5. When checking leave history, if any request has status 'REJECTED', explicitly inform
   the employee and state the manager's comments/rejection reason (returned as
   `manager_comments` in the record).
6. When displaying leave balances or history, do NOT write any conversational paragraphs, filler sentences, or extra introductory/concluding text. Only output the structured list or Markdown table directly.

Supported leave types: {LEAVE_TYPES_INFO}

Leave Approval Rules:
━━━━━━━━━━━━━━━━━━━━
Auto-Approval Rules (no manager action needed):
  • The request is for an emergency (reason contains 'emergency') → AUTO_APPROVED immediately and recorded as an exception
  • Balance is sufficient AND total_days ≤ 3  →  AUTO_APPROVED immediately
  • Balance is sufficient AND notice ≥ 28 days →  AUTO_APPROVED immediately

Manager Review Required:
  • Insufficient balance (any days)            →  LOP (Loss of Pay) — manager notified
  • Balance OK, >3 days, <28 days notice,
    employee has < 2 short-notice exceptions
    this year                                  →  PENDING — manager must approve/reject
  • Same as above but ≥ 2 exceptions this year →  ESCALATED — disciplinary review

Exceptional Case Rule:
  • Each time a PENDING/ESCALATED/LOP request is approved by the manager, it is
    recorded as an exception event.
  • An emergency leave auto-approval is also recorded as an exception event.
  • When an employee accumulates 2 or more exceptions in the same calendar year,
    the next non-auto-approvable request gets status ESCALATED.

Loss of Pay (LOP) Policy:
  • Triggered when leave balance < days requested.
  • Manager may still approve (no balance deducted, but recorded as an exception) or reject the LOP request.
  • If rejected, the employee must reconsider or use unpaid leave.

Status values used in the system:
  AUTO_APPROVED, PENDING, APPROVED, REJECTED, LOP, ESCALATED

When applying leave, you MUST collect:
- employee_id (or look up by email/employee code)
- leave_type
- start_date (YYYY-MM-DD)
- end_date (YYYY-MM-DD)
- total_days
- reason

If any information is missing, ask the user politely before calling apply_leave.
Always use tools to fetch real data — never invent balances or statuses.
After processing, summarize the result clearly for the employee, including the
status, what it means, and what happens next.
"""

# Cache the SystemMessage to avoid re-creation on every message
SYSTEM_MESSAGE_CACHE = SystemMessage(content=SYSTEM_PROMPT)

_leave_graph = None

def _get_leave_graph():
    """Lazily load and compile the LangGraph compilation chain on first request."""
    global _leave_graph
    if _leave_graph is None:
        from langgraph.graph import StateGraph, MessagesState, START
        from langgraph.prebuilt import ToolNode, tools_condition
        from services.llm_service import llm

        llm_with_tools = llm.bind_tools(LEAVE_TOOLS)
        tool_node = ToolNode(LEAVE_TOOLS)

        def agent_node(state: MessagesState):
            response = llm_with_tools.invoke(state["messages"])
            return {"messages": [response]}

        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("agent", agent_node)
        graph_builder.add_node("tools", tool_node)
        graph_builder.add_edge(START, "agent")
        graph_builder.add_conditional_edges("agent", tools_condition)
        graph_builder.add_edge("tools", "agent")

        _leave_graph = graph_builder.compile()
    return _leave_graph


def extract_text_content(content) -> str:
    """Normalize Gemini/LangChain message content to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p).strip()
    return str(content)


def get_final_reply(messages) -> str:
    """Get the last AI text response from graph messages."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            text = extract_text_content(message.content)
            if text:
                return text
    return "I'm sorry, I couldn't generate a response. Please try again."


def leave_chat(user_message: str, history: list | None = None) -> dict:
    messages = [SYSTEM_MESSAGE_CACHE]

    if history:
        for item in history:
            role = item.get("role", "user")
            content = extract_text_content(item.get("content", ""))
            if not content:
                continue
            if role == "assistant":
                messages.append(AIMessage(content=content))
            else:
                messages.append(HumanMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    try:
        result = _get_leave_graph().invoke({"messages": messages})
        reply = get_final_reply(result["messages"])
    except Exception as exc:
        return {
            "reply": (
                "I'm having trouble connecting to the AI service right now. "
                f"Please try again in a moment. ({type(exc).__name__})"
            ),
            "history": history or [],
            "error": True,
        }

    updated_history = []
    if history:
        updated_history.extend(history)
    updated_history.append({"role": "user", "content": user_message})
    updated_history.append({"role": "assistant", "content": reply})

    return {
        "reply": reply,
        "history": updated_history,
    }
