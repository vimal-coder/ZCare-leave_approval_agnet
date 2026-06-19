let chatHistory = [];
let isLoading = false;

const ICONS = {
    calendar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    note: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
    tag: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>`,
    check: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
    doubleCheck: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/><polyline points="24 6 13 17" transform="translate(-4,0)"/></svg>`,
    robot: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="9" cy="16" r="1.5" fill="currentColor" stroke="none"/><circle cx="15" cy="16" r="1.5" fill="currentColor" stroke="none"/><path d="M12 11V7"/><path d="M8 7h8"/><circle cx="12" cy="4" r="2"/></svg>`,
};

function getTimeString() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function detailRow(icon, label, value) {
    return `
        <div class="detail-row">
            <div class="detail-icon">${icon}</div>
            <span class="detail-label">${label}</span>
            <span class="detail-value">${escapeHtml(value)}</span>
        </div>`;
}

function parseLeaveDetails(text) {
    const message = normalizeReply(text);
    const fields = [
        { key: /leave\s*type[:\s]+([^\n]+)/i, label: 'Leave Type', icon: ICONS.tag },
        { key: /start\s*date[:\s]+([^\n]+)/i, label: 'Start Date', icon: ICONS.calendar },
        { key: /end\s*date[:\s]+([^\n]+)/i, label: 'End Date', icon: ICONS.calendar },
        { key: /total\s*days[:\s]+([^\n]+)/i, label: 'Total Days', icon: ICONS.clock },
        { key: /reason[:\s]+([^\n]+)/i, label: 'Reason', icon: ICONS.note },
    ];

    const rows = [];
    for (const f of fields) {
        const match = message.match(f.key);
        if (match) {
            rows.push(detailRow(f.icon, f.label, match[1].trim().replace(/\*\*/g, '')));
        }
    }
    return rows.length >= 2 ? rows.join('') : null;
}

function detectLeaveStatus(message) {
    const finalStatus = message.match(/final\s*status[:\s]+(\w+)/i);
    if (finalStatus) return finalStatus[1];

    const explicitStatus = message.match(/\bstatus[:\s]+(approved|pending|rejected|lop|disciplinary)\b/i);
    if (explicitStatus) return explicitStatus[1];

    if (/\b(pending\s*manager|forwarded\s*to\s*manager|awaiting\s*manager|pending\s*approval)\b/i.test(message)) {
        return 'Pending';
    }
    if (/\b(auto[- ]?approved|automatically\s*approved|has\s*been\s*approved)\b/i.test(message)) {
        return 'Approved';
    }
    if (/\b(rejected|declined)\b/i.test(message)) return 'Rejected';
    if (/\b(lop|loss\s*of\s*pay)\b/i.test(message)) return 'LOP';
    if (/\bdisciplinary\b/i.test(message)) return 'Disciplinary';

    return null;
}

function getStatusCardConfig(status) {
    const normalized = (status || '').toLowerCase();

    const configs = {
        approved: {
            title: 'Great News!',
            subtitle: 'Your leave has been <strong>Approved.</strong>',
            icon: '🎉',
            cardClass: 'status-card-approved',
            daysLabel: 'Approved Days',
        },
        pending: {
            title: 'Leave Submitted',
            subtitle: 'Your request is <strong>Pending Manager Approval.</strong>',
            icon: '⏳',
            cardClass: 'status-card-pending',
            daysLabel: 'Requested Days',
        },
        rejected: {
            title: 'Leave Update',
            subtitle: 'Your leave request has been <strong>Rejected.</strong>',
            icon: '❌',
            cardClass: 'status-card-rejected',
            daysLabel: 'Requested Days',
        },
        lop: {
            title: 'Leave Recorded',
            subtitle: 'Recorded as <strong>Loss of Pay</strong> due to insufficient balance.',
            icon: '⚠️',
            cardClass: 'status-card-lop',
            daysLabel: 'Requested Days',
        },
        disciplinary: {
            title: 'Action Required',
            subtitle: 'Flagged for <strong>Disciplinary Review.</strong>',
            icon: '⚠️',
            cardClass: 'status-card-disciplinary',
            daysLabel: 'Requested Days',
        },
    };

    return configs[normalized] || null;
}

function buildStatusCard(leaveResult, message) {
    const status = leaveResult?.status || detectLeaveStatus(message);
    const config = getStatusCardConfig(status);
    if (!config) return null;

    const daysMatch = message.match(/(\d+)\s*days?/i);
    const balanceMatch = message.match(/balance[:\s-]+([^\n.]+)/i);

    let rows = '';
    if (leaveResult?.request_id) {
        rows += detailRow(ICONS.tag, 'Reference ID', String(leaveResult.request_id));
    }
    if (daysMatch) {
        rows += detailRow(ICONS.clock, config.daysLabel, daysMatch[0]);
    }
    if (balanceMatch) {
        rows += detailRow(ICONS.note, 'Available Balance', balanceMatch[1].trim());
    }
    rows += detailRow(ICONS.check, 'Status', status);

    return `
        <div class="status-card ${config.cardClass}">
            <div class="success-header">
                <span class="success-icon">${config.icon}</span>
                <span class="success-title">${config.title}</span>
            </div>
            <p class="status-subtitle">${config.subtitle}</p>
            <div class="detail-card">${rows}</div>
        </div>`;
}

function parseApprovalCard(text, leaveResult = null) {
    if (leaveResult?.status) {
        return buildStatusCard(leaveResult, normalizeReply(text));
    }

    const message = normalizeReply(text);
    const status = detectLeaveStatus(message);
    if (!status) return null;

    return buildStatusCard({ status }, message);
}

function normalizeReply(content) {
    if (content == null) return '';
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
        return content
            .map((block) => {
                if (typeof block === 'string') return block;
                if (block && typeof block.text === 'string') return block.text;
                return '';
            })
            .filter(Boolean)
            .join('\n');
    }
    if (typeof content === 'object' && typeof content.text === 'string') {
        return content.text;
    }
    return String(content);
}

function formatBotMessage(text, leaveResult = null) {
    const message = normalizeReply(text);
    const approvalCard = parseApprovalCard(message, leaveResult);
    if (approvalCard) {
        return approvalCard;
    }

    const detailCard = parseLeaveDetails(message);
    if (detailCard) {
        const intro = message.split(/\n/)[0];
        const cleanIntro = intro.replace(/\*\*/g, '').trim();
        return `<p>${escapeHtml(cleanIntro)}</p><div class="detail-card">${detailCard}</div>`;
    }

    return escapeHtml(message)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n/g, '<br>');
}

function addUserMessage(content) {
    const container = document.getElementById('chat-messages');
    const time = getTimeString();

    const row = document.createElement('div');
    row.className = 'message-row user-row';
    row.innerHTML = `
        <div class="message-group">
            <div class="bubble user-bubble">${escapeHtml(content)}</div>
            <span class="timestamp read-status">
                ${time}
                <span title="Read">${ICONS.doubleCheck}</span>
            </span>
        </div>`;

    container.appendChild(row);
    scrollToBottom();
}

function addBotMessage(content, leaveResult = null) {
    const container = document.getElementById('chat-messages');
    const time = getTimeString();
    const formatted = formatBotMessage(content, leaveResult);

    const row = document.createElement('div');
    row.className = 'message-row bot-row';
    row.innerHTML = `
        <div class="avatar bot-avatar">${ICONS.robot}</div>
        <div class="message-group">
            <div class="bubble bot-bubble">${formatted}</div>
            <span class="timestamp">${time}</span>
        </div>`;

    container.appendChild(row);
    scrollToBottom();
}

function showTyping() {
    hideTyping();

    const container = document.getElementById('chat-messages');
    const row = document.createElement('div');
    row.id = 'typing-indicator';
    row.className = 'message-row bot-row typing-row';
    row.innerHTML = `
        <div class="avatar bot-avatar">${ICONS.robot}</div>
        <div class="bubble bot-bubble typing-bubble">
            <span class="dot"></span>
            <span class="dot"></span>
            <span class="dot"></span>
        </div>`;

    container.appendChild(row);
    scrollToBottom();
}

function hideTyping() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

function scrollToBottom() {
    const main = document.querySelector('.chat-main');
    main.scrollTop = main.scrollHeight;
}

async function sendMessage() {
    if (isLoading) return;

    const input = document.getElementById('user-input');
    const message = input.value.trim();
    if (!message) return;

    isLoading = true;
    input.value = '';
    addUserMessage(message);

    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    showTyping();

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history: chatHistory }),
        });

        if (!response.ok) throw new Error('Request failed');

        const data = await response.json();
        chatHistory = data.history || [];
        hideTyping();
        addBotMessage(
            data.reply || 'I could not generate a response. Please try again.',
            data.leave_result || null
        );
    } catch {
        hideTyping();
        addBotMessage('Sorry, something went wrong. Please try again.');
    } finally {
        hideTyping();
        isLoading = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

function resetChat() {
    chatHistory = [];
    hideTyping();
    const container = document.getElementById('chat-messages');
    container.innerHTML = `
        <div class="message-row bot-row">
            <div class="avatar bot-avatar">${ICONS.robot}</div>
            <div class="message-group">
                <div class="bubble bot-bubble">
                    <p>Hello! 👋 I'm your <strong>ZCare Leave Assistant</strong>.</p>
                    <p class="bubble-gap">I can help you apply for leave, check your balance, and view your leave history.</p>
                    <p class="bubble-gap">Tell me your employee ID and what you'd like to do — for example:</p>
                    <p class="example-text">"I want to apply for leave from 20 May to 22 May for personal work."</p>
                </div>
                <span class="timestamp">${getTimeString()}</span>
            </div>
        </div>`;
    document.getElementById('user-input').focus();
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('welcome-time').textContent = getTimeString();
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    document.getElementById('new-chat-btn').addEventListener('click', resetChat);
    document.getElementById('user-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
    document.getElementById('user-input').focus();
});
