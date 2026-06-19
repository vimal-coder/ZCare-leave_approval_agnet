# ZCare Leave AI Assistant

The **ZCare Leave AI Assistant** is an intelligent, automated leave management and approval platform designed for healthcare organizations. It features an interactive AI chatbot that allows employees to query leave balances, view leave history, and apply for leave in natural language, while enforcing complex corporate leave rules, manager escalations, Loss of Pay (LOP) routing, and automatic email notifications.

---

## 🌟 Key Features

*   **Natural Language Chatbot**: Powered by LangGraph and Groq, allowing employees to apply for leave and query balances conversationally.
*   **Automated Rules Engine**:
    *   **Auto-Approval**: Automatically approves requests of $\le 3$ days, requests with $\ge 28$ days notice, or **Emergency Leave** requests.
    *   **Manager Actions**: Routes short-notice requests, Loss of Pay (LOP) requests, or escalated cases for manager review.
    *   **Disciplinary Escalation**: Escalates requests if an employee has already used $\ge 2$ exceptional leave approvals in the same calendar year.
*   **Centralized Configuration**: Managed through `config.ini` for flexible deployments (Database, Email SMTP, LLM options).
*   **Professional Notification System**: Sends structured HTML emails to managers (with inline Approve/Reject action buttons) and status updates to employees.
*   **MCP Server Integration**: Exposes leave tools as Model Context Protocol (MCP) tools for external agent execution.

---

## 📁 Directory Structure

```text
ZCare_leave_approved/
├── agent/                  # Conversational AI Agent
│   ├── __init__.py
│   ├── leave_agent.py      # LangGraph state machine and System Prompt
│   └── tools.py            # LangChain tools mapping chat to services & DB
├── schemas/                # Data validation models
│   ├── __init__.py
│   └── leave_schema.py     # Pydantic schemas
├── services/               # Core business logic layer
│   ├── __init__.py
│   ├── leave_processor.py  # Leave rules validation and emergency handling
│   ├── manager_service.py  # Manager approval/rejection operations
│   ├── email_services.py   # Table-based HTML emails & SMTP manager
│   └── llm_service.py      # ChatGroq client provider
├── tools/                  # Auxiliary services & APIs
│   ├── __init__.py
│   ├── approval_tool.py
│   ├── leave_balance_tool.py
│   ├── leave_request_tool.py
│   ├── leave_tool.py
│   └── mcp_server.py       # Exposes FastMCP tools server
├── static/                 # Frontend assets (Chat Dashboard UI)
│   ├── index.html
│   ├── chat.js
│   ├── style.css
│   └── logo.svg
├── app.py                  # FastAPI server and HTTP API endpoints
├── database.py             # PostgreSQL ThreadedConnectionPool manager
├── db_queries.py           # Database CRUD queries and logging wrappers
├── config.py               # Python configuration module
├── config.ini              # Central config file (Database, SMTP, Groq)
├── requirements.txt        # Package dependencies
└── README.md               # Project documentation (this file)
```

---

## ⚙️ Configuration (`config.ini`)

All system settings are consolidated in `config.ini`. Copy and customize these settings for your local database and SMTP credentials:

```ini
[database]
DB_HOST = localhost
DB_PORT = 5432
DB_NAME = zcare_leave_db
DB_USER = postgres
DB_PASSWORD = your_db_password
DB_MIN_CONN = 1
DB_MAX_CONN = 15

[email]
EMAIL_SENDER = your_email@gmail.com
EMAIL_PASSWORD = your_app_password
SMTP_HOST = smtp.gmail.com
SMTP_PORT = 587

[app]
APP_BASE_URL = http://127.0.0.1:8000
GROQ_API_KEY = "your_groq_api_key"
GROQ_MODEL = llama-3.1-8b-instant
DEFAULT_MANAGER_EMAIL = manager@zcare.com
```

---

## 🛢️ Database Schema Details

The application communicates with a PostgreSQL database containing the following core tables:

### 1. `employees`
Stores employee profiles and manager associations.
*   `employee_id` (SERIAL PRIMARY KEY)
*   `employee_code` (VARCHAR, UNIQUE)
*   `employee_name` (VARCHAR)
*   `email` (VARCHAR, UNIQUE)
*   `department` (VARCHAR)
*   `manager_email` (VARCHAR)

### 2. `leave_balances`
Tracks active leave balances for each employee.
*   `employee_id` (INT REFERENCES employees)
*   `annual_leave` (INT)
*   `personal_leave` (INT)
*   `special_leave` (INT)
*   `optional_holiday` (INT)

### 3. `leave_requests`
Maintains records of submitted leave requests.
*   `request_id` (SERIAL PRIMARY KEY)
*   `employee_id` (INT REFERENCES employees)
*   `leave_type` (VARCHAR)
*   `start_date` (DATE)
*   `end_date` (DATE)
*   `total_days` (INT)
*   `reason` (TEXT)
*   `status` (VARCHAR: `AUTO_APPROVED`, `PENDING`, `APPROVED`, `REJECTED`, `LOP`, `ESCALATED`)
*   `applied_date` (TIMESTAMP)

### 4. `manager_approvals`
Tracks manager decisions and text comments.
*   `approval_id` (SERIAL PRIMARY KEY)
*   `request_id` (INT REFERENCES leave_requests)
*   `manager_email` (VARCHAR)
*   `decision` (VARCHAR)
*   `comments` (TEXT)
*   `approved_at` (TIMESTAMP)

### 5. `exceptional_cases`
Records exceptional approvals and emergency leave event tallies.
*   `exception_id` (SERIAL PRIMARY KEY)
*   `employee_id` (INT REFERENCES employees)
*   `request_id` (INT REFERENCES leave_requests)
*   `exception_year` (INT)
*   `created_at` (TIMESTAMP)

### 6. `email_logs`
Logs the status of all sent and failed email notifications.
*   `email_id` (SERIAL PRIMARY KEY)
*   `request_id` (INT REFERENCES leave_requests)
*   `recipient_email` (VARCHAR(100))
*   `subject` (VARCHAR(255))
*   `email_status` (VARCHAR(20) check: `SENT` or `FAILED`)
*   `sent_at` (TIMESTAMP)

---

## 🚀 How to Run

### 1. Set Up Environment
Create and activate a python virtual environment, and install dependencies:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the FastAPI Application
Start the FastAPI server locally:
```bash
uvicorn app:app --reload
```
Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser to access the Chat Dashboard.

### 3. Run the MCP Server
If you wish to expose the leave management tools to an MCP host:
```bash
python -m tools.mcp_server
```

---

## 📬 Email Notification Flows

*   **On Submission**:
    *   **Auto-Approved**: Employee gets an approval email. Manager receives an FYI.
    *   **LOP / Pending / Escalated**: Employee gets a submission confirmation. Manager receives an Action Required email with direct "Approve" and "Reject" buttons.
*   **On Manager Action**:
    *   Employee receives the manager's final approval/rejection details (including reason generated professionally by LLM).
    *   If it was the employee's **first exceptional case approval**, they also receive an **Exceptional Leave Warning** notifying them that a second exception will trigger future escalations.
