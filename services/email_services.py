import logging
import os
import smtplib
import socket
import concurrent.futures
from email.mime.text import MIMEText

from config import APP_BASE_URL, EMAIL_SENDER, EMAIL_PASSWORD, SMTP_HOST, SMTP_PORT

logger = logging.getLogger(__name__)

from db_queries import log_email
from services.llm_service import generate_rejection_email

# Initialize a thread pool executor for background email sending
_email_executor = concurrent.futures.ThreadPoolExecutor(max_workers=5, thread_name_prefix="email_worker")

# Statuses that require manager action — these get the Approve/Reject email
MANAGER_APPROVAL_STATUSES = {"PENDING", "ESCALATED", "LOP"}


_cached_base_url = None

def get_app_base_url():
    """Resolve and cache the application's base URL once to avoid repetitive blocking socket/DNS calls."""
    global _cached_base_url
    if _cached_base_url is None:
        # Try to read from environment variable BASE_URL first, then APP_BASE_URL
        base_url = APP_BASE_URL
        
        port = "8000"
        if base_url:
            base_url = base_url.rstrip("/")
            # Extract port if present (e.g., http://localhost:8000 -> 8000)
            parts = base_url.split(":")
            if len(parts) > 2:
                port = parts[-1].split("/")[0]
                
        # Check if we need to replace localhost, 127.0.0.1, or your-domain.com
        invalid_hosts = ["localhost", "127.0.0.1", "your-domain.com"]
        if not base_url or any(host in base_url for host in invalid_hosts):
            try:
                # Resolve actual machine hostname and local IP
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                base_url = f"http://{local_ip}:{port}"
            except Exception:
                # Fallback to local network hostname
                base_url = f"http://{socket.gethostname()}:{port}"
        _cached_base_url = base_url
    return _cached_base_url


def send_email(to_email, subject, body, is_html=False):
    if not to_email:
        logger.warning("Email not sent: recipient address is empty")
        return False

    sender   = EMAIL_SENDER
    password = EMAIL_PASSWORD

    if not password:
        logger.warning("Email not sent: EMAIL_PASSWORD not configured")
        return False

    msg = MIMEText(body, "html" if is_html else "plain")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = to_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Shared HTML builder — matches the professional table-based layout in the
# reference screenshot (EY-style: clean white, bordered table, footer text).
# ─────────────────────────────────────────────────────────────────────────────

_BASE_CSS = """
    body {
        font-family: Arial, Calibri, sans-serif;
        font-size: 13px;
        color: #222222;
        background-color: #ffffff;
        margin: 0;
        padding: 0;
    }
    .wrapper {
        max-width: 640px;
        margin: 24px auto;
        padding: 0 16px;
        background: #ffffff;
    }
    .subject-line {
        font-size: 15px;
        font-weight: bold;
        color: #1a1a1a;
        margin-bottom: 18px;
        padding-bottom: 8px;
        border-bottom: 2px solid #003366;
    }
    p {
        margin: 10px 0;
        line-height: 1.6;
    }
    table.details {
        border-collapse: collapse;
        width: 100%;
        margin: 16px 0 20px 0;
        font-size: 13px;
    }
    table.details th {
        background-color: #f0f0f0;
        border: 1px solid #999999;
        padding: 7px 10px;
        text-align: left;
        font-weight: bold;
        white-space: nowrap;
    }
    table.details td {
        border: 1px solid #999999;
        padding: 7px 10px;
        text-align: left;
        white-space: nowrap;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
        color: #ffffff;
    }
    .footer-note {
        font-size: 12px;
        color: #555555;
        margin-top: 8px;
        line-height: 1.7;
    }
    .brand {
        margin-top: 28px;
        padding-top: 14px;
        border-top: 1px solid #dddddd;
    }
    .brand-name {
        font-size: 22px;
        font-weight: bold;
        color: #003366;
        letter-spacing: 1px;
    }
    .brand-tag {
        font-size: 11px;
        color: #555555;
        margin-top: 2px;
    }
    .action-buttons {
        margin: 24px 0;
        text-align: center;
    }
    .btn {
        display: inline-block;
        padding: 11px 28px;
        font-size: 14px;
        font-weight: bold;
        border-radius: 4px;
        text-decoration: none;
        margin: 0 10px;
        color: #ffffff !important;
    }
    .btn-approve { background-color: #1a7a4a; }
    .btn-reject  { background-color: #c0392b; }
    .section-note {
        background: #fffbf0;
        border-left: 4px solid #e6a817;
        padding: 10px 14px;
        margin: 14px 0;
        font-size: 12.5px;
        color: #4a3800;
    }
"""


def _status_badge(status):
    colors = {
        "AUTO_APPROVED": "#1a7a4a",
        "APPROVED":      "#1a7a4a",
        "PENDING":       "#1a6fb5",
        "LOP":           "#c07d00",
        "ESCALATED":     "#c0392b",
        "REJECTED":      "#c0392b",
    }
    color = colors.get(status, "#666666")
    return f'<span class="status-badge" style="background-color:{color};">{status}</span>'


def _leave_table(
    employee_code,
    employee_name,
    request_id,
    leave_type,
    start_date,
    end_date,
    total_days,
    status=None,
):
    """Build the bordered leave-details table matching the reference screenshot."""
    status_cell = _status_badge(status) if status else ""
    return f"""
    <table class="details">
        <tr>
            <th>Employee Code</th>
            <th>Employee Name</th>
            <th>Leave Application ID</th>
            <th>Leave Type</th>
            <th>From Date</th>
            <th>To Date</th>
            <th>Total Duration</th>
            {"<th>Status</th>" if status else ""}
        </tr>
        <tr>
            <td>{employee_code}</td>
            <td>{employee_name}</td>
            <td>{request_id}</td>
            <td>{leave_type}</td>
            <td>{start_date}</td>
            <td>{end_date}</td>
            <td>{total_days} Day(s)</td>
            {"<td>" + status_cell + "</td>" if status else ""}
        </tr>
    </table>
    """


def _brand_footer():
    return """
    <div class="brand">
        <div class="brand-name">ZCare</div>
        <div class="brand-tag">Healthcare Leave Management System</div>
    </div>
    """


def _wrap_html(title, body_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{_BASE_CSS}</style>
</head>
<body>
    <div class="wrapper">
        {body_html}
    </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Employee-facing email templates
# ─────────────────────────────────────────────────────────────────────────────

def _build_employee_email(
    subject_line,
    employee_code,
    employee_name,
    request_id,
    leave_type,
    start_date,
    end_date,
    total_days,
    status,
    intro_paragraph,
    extra_notes="",
):
    table = _leave_table(
        employee_code, employee_name, request_id,
        leave_type, start_date, end_date, total_days, status,
    )
    body = f"""
    <div class="subject-line">Information: {subject_line}</div>

    <p>Dear {employee_name},</p>

    <p>{intro_paragraph}</p>

    {table}

    {extra_notes}

    <p class="footer-note">
        You will be notified once an action is taken on this request.
        For any queries, please contact your HR representative or your manager.
    </p>
    <p class="footer-note">
        This is a system-generated notification. Please do not reply to this email.
    </p>

    {_brand_footer()}
    """
    return _wrap_html(subject_line, body)


def _employee_email_auto_approved(
    employee_code, employee_name, request_id,
    leave_type, start_date, end_date, total_days,
):
    intro = (
        "Your leave request has been <strong>automatically approved</strong>. "
        "No further action is required."
    )
    return _build_employee_email(
        subject_line   = "Your leave request has been auto-approved",
        employee_code  = employee_code,
        employee_name  = employee_name,
        request_id     = request_id,
        leave_type     = leave_type,
        start_date     = start_date,
        end_date       = end_date,
        total_days     = total_days,
        status         = "AUTO_APPROVED",
        intro_paragraph= intro,
    )


def _employee_email_pending(
    employee_code, employee_name, request_id,
    leave_type, start_date, end_date, total_days,
):
    intro = (
        "Your leave request has been submitted and sent for manager approval. "
        "You will be notified once your manager takes action."
    )
    return _build_employee_email(
        subject_line   = "Your leave request has been submitted",
        employee_code  = employee_code,
        employee_name  = employee_name,
        request_id     = request_id,
        leave_type     = leave_type,
        start_date     = start_date,
        end_date       = end_date,
        total_days     = total_days,
        status         = "PENDING",
        intro_paragraph= intro,
    )


def _employee_email_lop(
    employee_code, employee_name, request_id,
    leave_type, start_date, end_date, total_days,
):
    intro = (
        "Your leave request has been submitted. However, your leave balance is "
        "insufficient to cover this request. It has been recorded as "
        "<strong>Loss of Pay (LOP)</strong> and forwarded to your manager for review."
    )
    extra = """
    <div class="section-note">
        ⚠ Please note: LOP will result in a salary deduction for the leave period
        unless your manager takes alternative action.
    </div>
    """
    return _build_employee_email(
        subject_line   = "Your leave request has been submitted — Loss of Pay (LOP)",
        employee_code  = employee_code,
        employee_name  = employee_name,
        request_id     = request_id,
        leave_type     = leave_type,
        start_date     = start_date,
        end_date       = end_date,
        total_days     = total_days,
        status         = "LOP",
        intro_paragraph= intro,
        extra_notes    = extra,
    )


def _employee_email_escalated(
    employee_code, employee_name, request_id,
    leave_type, start_date, end_date, total_days,
):
    intro = (
        "Your leave request has been submitted. This request has been "
        "<strong>escalated for disciplinary review</strong> because you have exceeded "
        "the allowed number of short-notice exceptional leave requests for this year. "
        "Your manager will be notified and will review this case."
    )
    extra = """
    <div class="section-note">
        ⚠ Please contact your manager or HR department at the earliest to discuss
        this leave request and avoid any disciplinary action.
    </div>
    """
    return _build_employee_email(
        subject_line   = "Your leave request has been escalated for disciplinary review",
        employee_code  = employee_code,
        employee_name  = employee_name,
        request_id     = request_id,
        leave_type     = leave_type,
        start_date     = start_date,
        end_date       = end_date,
        total_days     = total_days,
        status         = "ESCALATED",
        intro_paragraph= intro,
        extra_notes    = extra,
    )


def _employee_email_approved(
    employee_code, employee_name, request_id,
    leave_type, start_date, end_date, total_days,
):
    intro = (
        "Your leave request has been <strong>approved by your manager</strong>. "
        "Enjoy your time off!"
    )
    return _build_employee_email(
        subject_line   = "Your leave request has been approved",
        employee_code  = employee_code,
        employee_name  = employee_name,
        request_id     = request_id,
        leave_type     = leave_type,
        start_date     = start_date,
        end_date       = end_date,
        total_days     = total_days,
        status         = "APPROVED",
        intro_paragraph= intro,
    )


def _employee_email_rejected(
    employee_code, employee_name, request_id,
    leave_type, start_date, end_date, total_days,
    llm_body="", comments="",
):
    table = _leave_table(
        employee_code, employee_name, request_id,
        leave_type, start_date, end_date, total_days, "REJECTED",
    )

    if llm_body:
        # LLM gave us a full email body — embed it after the table
        body_content = f"""
        <div class="subject-line">Information: Your leave request has been rejected</div>
        <p>Dear {employee_name},</p>
        {table}
        <p>{llm_body.replace(chr(10), '<br>')}</p>
        <p class="footer-note">This is a system-generated notification. Please do not reply to this email.</p>
        {_brand_footer()}
        """
    else:
        body_content = f"""
        <div class="subject-line">Information: Your leave request has been rejected</div>
        <p>Dear {employee_name},</p>
        <p>We regret to inform you that your leave request has been <strong>rejected</strong> by your manager.</p>
        {table}
        <p><strong>Manager's Comments:</strong> {comments or "No specific reason provided."}</p>
        <p>Please reach out to your manager for further clarification if needed.</p>
        <p class="footer-note">This is a system-generated notification. Please do not reply to this email.</p>
        {_brand_footer()}
        """

    return _wrap_html("Your leave request has been rejected", body_content)


# ─────────────────────────────────────────────────────────────────────────────
# Manager-facing email template (with Approve / Reject action buttons)
# ─────────────────────────────────────────────────────────────────────────────

def notify_manager_approval_required(
    manager_email,
    employee_name,
    employee_email,
    employee_code,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason,
    request_id,
    status="PENDING",
    exception_count=0,
):
    """Send manager an HTML email with the dark modern layout + Approve/Reject buttons."""
    base_url    = get_app_base_url()
    approve_url = f"{base_url}/leave/approve/{request_id}"
    reject_url  = f"{base_url}/leave/reject/{request_id}"

    if status == "ESCALATED":
        subject_line = f"Action Required: Escalated Leave Request — {employee_name}"
        status_color = "#c62828"
    elif status == "LOP":
        subject_line = f"Action Required: Loss of Pay Leave — {employee_name}"
        status_color = "#ff5353"
    else:
        subject_line = f"Action Required: Exceptional Leave Approval — {employee_name}"
        status_color = "#ffb300"

    lop_warning_box = ""
    if status == "LOP":
        lop_warning_box = f"""
        <!-- Loss of Pay Warning Box -->
        <tr>
            <td align="left" style="padding: 0 0 24px 0;">
                <div style="padding: 16px; background-color: #2a1b1b; border: 1px solid #5a2b2b; border-left: 4px solid #ff5353; border-radius: 4px;">
                    <div style="font-size: 13px; font-weight: 700; color: #ff5353; margin-bottom: 6px;">⚠️ Loss of Pay (LOP) Warning</div>
                    <div style="font-size: 13px; line-height: 1.5; color: #e0d0d0;">
                        This request is marked as Loss of Pay because the employee does not have sufficient leave balance. Approving this leave will result in a salary deduction for the leave period.
                    </div>
                </div>
            </td>
        </tr>
        """

    exceptional_warning_box = ""
    if status in ("PENDING", "ESCALATED"):
        exceptional_warning_box = f"""
        <!-- Exceptional Case Section -->
        <tr>
            <td align="left" style="padding: 0 0 32px 0;">
                <div style="padding: 16px; background-color: #2c2215; border: 1px solid #5c4325; border-left: 4px solid #ffb300; border-radius: 4px;">
                    <div style="font-size: 13px; font-weight: 700; color: #ffb300; margin-bottom: 6px;">🚨 Exceptional Case Approval Required</div>
                    <div style="font-size: 13px; line-height: 1.5; color: #e6dac8;">
                        This request is an Exceptional Case because:
                        <ul style="margin: 6px 0 0 0; padding-left: 20px;">
                            <li>Leave duration exceeds 3 days.</li>
                            <li>Notice period is less than 28 days.</li>
                        </ul>
                        The request requires manager approval.
                    </div>
                </div>
            </td>
        </tr>
        """

    reason_content = reason or "No reason provided"
    reason_box = f"""
    <!-- Reason Box -->
    <div style="margin-bottom: 24px; padding: 16px; background-color: #1e1e24; border-left: 4px solid #3b82f6; border-radius: 4px;">
        <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: #3b82f6; margin-bottom: 8px;">Employee Reason</div>
        <div style="font-size: 14px; line-height: 1.5; color: #e0e0e0; font-style: italic;">"{reason_content}"</div>
    </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ZCare — {subject_line}</title>
    <style>
        body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; }}
        img {{ border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        table {{ border-collapse: collapse !important; }}
        body {{ height: 100% !important; margin: 0 !important; padding: 0 !important; width: 100% !important; background-color: #121212; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e0e0e0; }}
        a {{ text-decoration: none; }}
    </style>
</head>
<body style="margin: 0 !important; padding: 0 !important; background-color: #121212; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e0e0e0; -webkit-font-smoothing: antialiased;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #121212;">
        <tr>
            <td align="center" style="padding: 40px 10px 40px 10px;">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #1a1a1f; border-radius: 12px; border: 1px solid #2e2e38; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                    <!-- Header -->
                    <tr>
                        <td align="left" style="background: linear-gradient(135deg, #1f2937, #111827); padding: 30px 40px; border-bottom: 1px solid #2e2e38;">
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td>
                                        <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #a0a0b0; margin-bottom: 6px;">ZCare Leave Approval</div>
                                        <h1 style="margin: 0; font-size: 24px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">Leave Approval Request</h1>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td align="left" style="padding: 40px;">
                            <p style="margin-top: 0; margin-bottom: 24px; font-size: 15px; line-height: 1.6; color: #cccccc;">
                                Dear Manager,
                            </p>
                            <p style="margin-top: 0; margin-bottom: 24px; font-size: 15px; line-height: 1.6; color: #cccccc;">
                                A leave request from <strong>{employee_name}</strong> requires your review. Below are the details of the request:
                            </p>

                            <!-- Employee Details Table -->
                            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px; border: 1px solid #2e2e38; border-radius: 8px; overflow: hidden;">
                                <tr>
                                    <td width="40%" style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">Employee Code</td>
                                    <td width="60%" style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; color: #ffffff;">{employee_code}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">Employee Name</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #ffffff;">{employee_name}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">Leave Application ID</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; color: #ffffff;">#{request_id}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">Leave Type</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; color: #ffffff;">{leave_type}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">From Date</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; color: #ffffff;">{start_date}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">To Date</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; color: #ffffff;">{end_date}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; border-bottom: 1px solid #2e2e38; font-size: 13px; font-weight: 600; color: #a0a0b0;">Total Duration</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; border-bottom: 1px solid #2e2e38; font-size: 13px; color: #ffffff;">{total_days} {"Day" if total_days == 1 else "Days"}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 12px 16px; background-color: #25252b; font-size: 13px; font-weight: 600; color: #a0a0b0;">Status</td>
                                    <td style="padding: 12px 16px; background-color: #1e1e24; font-size: 13px; font-weight: bold; color: {status_color};">{status}</td>
                                </tr>
                            </table>

                            {reason_box}

                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                {lop_warning_box}
                                {exceptional_warning_box}
                            </table>

                            <!-- Action Buttons -->
                            <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                <tr>
                                    <td align="center" style="padding-bottom: 10px;">
                                        <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                            <tr>
                                                <td width="48%" align="center">
                                                    <a href="{approve_url}" style="display: block; width: 100%; max-width: 240px; background-color: #1a7a4a; color: #ffffff; font-size: 15px; font-weight: bold; text-align: center; padding: 16px 0; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.2); border: 1px solid #145a32;">
                                                        ✔ Approve Leave
                                                    </a>
                                                </td>
                                                <td width="4%"></td>
                                                <td width="48%" align="center">
                                                    <a href="{reject_url}" style="display: block; width: 100%; max-width: 240px; background-color: #c62828; color: #ffffff; font-size: 15px; font-weight: bold; text-align: center; padding: 16px 0; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.2); border: 1px solid #921b1b;">
                                                        ✘ Reject Leave
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td align="center" style="padding: 30px 40px; background-color: #111827; border-top: 1px solid #2e2e38;">
                            <p style="margin: 0 0 10px 0; font-size: 12px; color: #718096; line-height: 1.5;">
                                This is a system-generated notification.
                            </p>
                            <p style="margin: 0; font-size: 11px; color: #4a5568;">
                                ZCare Healthcare Services &copy; 2026. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    status_sent = send_email(manager_email, f"ZCare — {subject_line}", html, is_html=True)
    log_email(request_id, manager_email, f"ZCare — {subject_line}", status_sent)
    return status_sent


# ─────────────────────────────────────────────────────────────────────────────
# Manager confirmation email (after they approve/reject)
# ─────────────────────────────────────────────────────────────────────────────

def _manager_confirmation_email(
    manager_email,
    employee_code,
    employee_name,
    request_id,
    leave_type,
    start_date,
    end_date,
    total_days,
    final_status,
    comments="",
):
    action_word = "approved" if final_status == "APPROVED" else "rejected"
    table = _leave_table(
        employee_code, employee_name, request_id,
        leave_type, start_date, end_date, total_days, final_status,
    )
    comments_row = ""
    if comments:
        comments_row = f"<p><strong>Your Comments:</strong> {comments}</p>"

    body = f"""
    <div class="subject-line">Information: Leave request {action_word} — {employee_name}</div>

    <p>Dear Manager,</p>

    <p>You have <strong>{action_word}</strong> the following leave request.</p>

    {table}

    {comments_row}

    <p class="footer-note">
        The employee has been notified of your decision by email.
    </p>
    <p class="footer-note">
        This is a system-generated notification. Please do not reply to this email.
    </p>

    {_brand_footer()}
    """
    html = _wrap_html(f"Leave {action_word} — {employee_name}", body)
    subj = f"ZCare — Leave {action_word.capitalize()} Confirmation — {employee_name}"
    status_sent = send_email(manager_email, subj, html, is_html=True)
    log_email(request_id, manager_email, subj, status_sent)
    return status_sent


def notify_leave_confirmed(
    employee_email,
    employee_name,
    manager_email,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason,
    status,
    request_id,
    employee_code="—",
    exception_count=0,
):
    """
    Master dispatcher: send the right employee email based on status, and also
    send the manager their notification (approval request or FYI) asynchronously.
    """
    def _send_task():
        # Define a dictionary mapping for employee emails
        email_map = {
            "AUTO_APPROVED": (
                _employee_email_auto_approved,
                "ZCare — Your leave request has been auto-approved"
            ),
            "PENDING": (
                _employee_email_pending,
                "ZCare — Your leave request has been submitted"
            ),
            "LOP": (
                _employee_email_lop,
                "ZCare — Your leave request has been submitted (Loss of Pay)"
            ),
            "ESCALATED": (
                _employee_email_escalated,
                "ZCare — Your leave request has been escalated"
            ),
        }

        builder, emp_subject = email_map.get(
            status,
            (_employee_email_auto_approved, "ZCare — Your leave request update")
        )
        emp_html = builder(
            employee_code, employee_name, request_id,
            leave_type, start_date, end_date, total_days,
        )

        employee_sent = send_email(employee_email, emp_subject, emp_html, is_html=True)
        log_email(request_id, employee_email, emp_subject, employee_sent)

        # ── Manager email ─────────────────────────────────────────────────────────
        manager_sent          = False
        manager_approval_sent = False

        if status in MANAGER_APPROVAL_STATUSES:
            # Fetch employee_code from DB if not passed — use "—" as fallback
            manager_approval_sent = notify_manager_approval_required(
                manager_email  = manager_email,
                employee_name  = employee_name,
                employee_email = employee_email,
                employee_code  = employee_code,
                leave_type     = leave_type,
                start_date     = start_date,
                end_date       = end_date,
                total_days     = total_days,
                reason         = reason,
                request_id     = request_id,
                status         = status,
                exception_count= exception_count,  # show exception counter in manager email
            )
            manager_sent = manager_approval_sent
        else:
            # AUTO_APPROVED — send a simple FYI to the manager
            mgr_table = _leave_table(
                employee_code, employee_name, request_id,
                leave_type, start_date, end_date, total_days, status,
            )
            mgr_body = f"""
            <div class="subject-line">Information: Leave auto-approved for {employee_name}</div>
            <p>Dear Manager,</p>
            <p>A leave request for your team member has been <strong>automatically approved</strong>.
            No action is required from your end.</p>
            {mgr_table}
            <p class="footer-note">This is a system-generated notification. Please do not reply to this email.</p>
            {_brand_footer()}
            """
            mgr_html = _wrap_html(f"Leave Auto-Approved — {employee_name}", mgr_body)
            manager_sent = send_email(
                manager_email,
                f"ZCare — Leave Auto-Approved — {employee_name}",
                mgr_html,
                is_html=True,
            )
            log_email(request_id, manager_email, f"ZCare — Leave Auto-Approved — {employee_name}", manager_sent)

    _email_executor.submit(_send_task)

    return {
        "employee_email_sent":        True,
        "manager_email_sent":         True,
        "manager_approval_email_sent": True,
    }


def notify_leave_approved(
    employee_email,
    employee_name,
    manager_email,
    leave_type,
    start_date,
    end_date,
    total_days,
    reason="",
    request_id=None,
    employee_code="—",
    exception_count_after=None,   # set when this was an exceptional (PENDING) approval
    was_exceptional=False,         # True when the approved request was PENDING
):
    """Called by manager_service after manual approval — notify both parties asynchronously.

    If was_exceptional is True and exception_count_after == 1, also sends a
    warning email to the employee: 'One more short-notice request → ESCALATED'.
    """
    def _send_task():
        # ── Standard approval email to employee ───────────────────────────────────
        emp_html = _employee_email_approved(
            employee_code, employee_name, request_id,
            leave_type, start_date, end_date, total_days,
        )
        employee_sent = send_email(
            employee_email,
            "ZCare — Your leave request has been approved ✔",
            emp_html,
            is_html=True,
        )
        log_email(request_id, employee_email, "ZCare — Your leave request has been approved ✔", employee_sent)

        # ── Exception warning email (only when 1st exception was just approved) ──
        warning_sent = False
        if was_exceptional and exception_count_after == 1:
            warning_body = f"""
            <div class="subject-line">
                Information: Exceptional Leave Warning — Action Required
            </div>

            <p>Dear {employee_name},</p>

            <p>
                Your leave request (Application ID: <strong>#{request_id}</strong>) has been
                <strong>approved</strong> by your manager. However, this request has been recorded
                as your <strong>first exceptional leave approval</strong> for this calendar year.
            </p>

            <div class="section-note" style="border-left-color:#e6a817; background:#fff9f0;">
                <strong>⚠ Exceptional Leave Warning</strong><br><br>
                <span style="font-size:18px; letter-spacing:4px; color:#e6a817;">&#11044; &#9711;</span><br>
                <span style="font-size:12px; color:#555;">1 of 2 exceptions used this year</span><br><br>
                You have used <strong>1 out of 2</strong> allowed exceptional leave approvals
                for this year. If you submit another short-notice leave request
                (more than 3 days, less than 28 days notice) and it is approved again,
                <strong>future short-notice requests will be automatically ESCALATED</strong>
                for disciplinary review.
            </div>

            <p>
                To avoid escalation, please plan your leave in advance and ensure you provide
                at least <strong>28 days notice</strong> for longer leave requests.
            </p>

            <p class="footer-note">
                For any queries, please contact your manager or HR department.
            </p>
            <p class="footer-note">
                This is a system-generated notification. Please do not reply to this email.
            </p>

            {_brand_footer()}
            """
            warning_html = _wrap_html("Exceptional Leave Warning", warning_body)
            warning_sent = send_email(
                employee_email,
                "ZCare — ⚠ Exceptional Leave Warning: 1 of 2 exceptions used",
                warning_html,
                is_html=True,
            )
            log_email(request_id, employee_email, "ZCare — ⚠ Exceptional Leave Warning: 1 of 2 exceptions used", warning_sent)

        # ── Confirmation email to manager ─────────────────────────────────────────
        mgr_sent = _manager_confirmation_email(
            manager_email = manager_email,
            employee_code = employee_code,
            employee_name = employee_name,
            request_id    = request_id,
            leave_type    = leave_type,
            start_date    = start_date,
            end_date      = end_date,
            total_days    = total_days,
            final_status  = "APPROVED",
        )

    _email_executor.submit(_send_task)

    return {
        "employee_email_sent":  True,
        "manager_email_sent":   True,
        "exception_warning_sent": True,
    }


def notify_leave_rejected(
    employee_email,
    employee_name,
    manager_email,
    leave_type,
    start_date,
    end_date,
    total_days=0,
    request_id=None,
    reason="",
    comments="",
    employee_code="—",
):
    """Called by manager_service after rejection — LLM generates empathetic body asynchronously."""
    def _send_task():
        try:
            llm_body = generate_rejection_email(
                employee_name=employee_name,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                total_days=total_days,
                reason=reason,
                comments=comments,
            )
        except Exception as exc:
            logger.error("LLM rejection email failed: %s. Using fallback.", exc)
            llm_body = ""

        emp_html = _employee_email_rejected(
            employee_code, employee_name, request_id,
            leave_type, start_date, end_date, total_days,
            llm_body=llm_body,
            comments=comments,
        )
        employee_sent = send_email(
            employee_email,
            "ZCare — Your leave request has been rejected",
            emp_html,
            is_html=True,
        )
        log_email(request_id, employee_email, "ZCare — Your leave request has been rejected", employee_sent)

        mgr_sent = _manager_confirmation_email(
            manager_email  = manager_email,
            employee_code  = employee_code,
            employee_name  = employee_name,
            request_id     = request_id,
            leave_type     = leave_type,
            start_date     = start_date,
            end_date       = end_date,
            total_days     = total_days,
            final_status   = "REJECTED",
            comments       = comments,
        )

    _email_executor.submit(_send_task)

    return {
        "employee_email_sent": True,
        "manager_email_sent":  True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Convenience wrappers (kept for backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def notify_leave_pending(
    employee_email, employee_name, manager_email,
    leave_type, start_date, end_date, total_days,
    request_id, reason="", employee_code="—",
):
    return notify_leave_confirmed(
        employee_email, employee_name, manager_email,
        leave_type, start_date, end_date, total_days,
        reason, "PENDING", request_id, employee_code,
    )


def notify_leave_lop(
    employee_email, employee_name, manager_email,
    leave_type, start_date, end_date, total_days,
    reason="", request_id=None, employee_code="—",
):
    return notify_leave_confirmed(
        employee_email, employee_name, manager_email,
        leave_type, start_date, end_date, total_days,
        reason, "LOP", request_id, employee_code,
    )


def notify_escalated(
    employee_email, employee_name, manager_email,
    leave_type, start_date, end_date, request_id,
    reason="", total_days=0, employee_code="—",
):
    return notify_leave_confirmed(
        employee_email, employee_name, manager_email,
        leave_type, start_date, end_date, total_days,
        reason, "ESCALATED", request_id, employee_code,
    )
