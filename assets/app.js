const messagesEl = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const quickActions = document.getElementById('quick-actions');
const typingIndicator = document.getElementById('typing-indicator');
const liveBtn = document.getElementById('live-btn');
const consentModal = document.getElementById('consent-modal');

let isLive = false;
let currentAiMsgEl = null;

// Ensure we auto-scroll to bottom
function scrollToBottom() {
    setTimeout(() => {
        messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
    }, 10);
}

// Append a new message
function appendMessage(text, role, allowHtml = false) {
    const el = document.createElement('div');
    el.className = `msg ${role}`;
    if (allowHtml) {
        el.innerHTML = text;
    } else {
        el.textContent = text;
    }
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
}

// Called by python when yielding tokens
function updateCurrentMessage(text) {
    if (!currentAiMsgEl) {
        hideTyping();
        currentAiMsgEl = appendMessage(text, 'ai');
    } else {
        currentAiMsgEl.textContent = text;
        scrollToBottom();
    }
}

// Called by python when message ends
function endCurrentMessage() {
    currentAiMsgEl = null;
    hideTyping();
}

function showTyping() {
    typingIndicator.classList.remove('hidden');
    messagesEl.appendChild(typingIndicator); // move to bottom
    scrollToBottom();
}

function hideTyping() {
    typingIndicator.classList.add('hidden');
}

// Emulate backend python interaction
function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;
    
    appendMessage(text, 'user');
    userInput.value = '';
    userInput.style.height = 'auto'; // reset textarea
    showTyping();

    // Call python backend via pywebview exposed API
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.send_message(text).catch(err => {
            console.error("API Error: ", err);
            hideTyping();
            appendMessage("Runtime Error communicating with backend.", "dim");
        });
    }
}

// Show inline confirmation dialog for actions
function requireConfirmation(actionObj, msgId) {
    hideTyping();
    const actionStr = JSON.stringify(actionObj, null, 2);
    const box = document.createElement('div');
    box.className = 'confirm-box';
    box.innerHTML = `
        <strong>Humphi wants to execute an action:</strong>
        <pre><code>${actionStr}</code></pre>
        <div class="confirm-actions">
            <button class="btn btn-allow" onclick="confirmAction('${msgId}', true, this)">Allow</button>
            <button class="btn btn-deny" onclick="confirmAction('${msgId}', false, this)">Deny</button>
        </div>
    `;
    const aiMsg = appendMessage("", "ai", true);
    aiMsg.appendChild(box);
    scrollToBottom();
}

// User clicked allow/deny
window.confirmAction = (msgId, isAllow, btnElement) => {
    // Disable buttons
    const parent = btnElement.parentElement;
    parent.innerHTML = isAllow ? '<em>Action Allowed</em>' : '<em>Action Denied</em>';
    
    // Send back to python
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.resolve_confirmation(msgId, isAllow);
    }
}

// Quick Actions Setup
const popularChips = [
    "Fix slow PC", "Check WiFi", "Free disk space", 
    "Update Windows", "Sound issues", "Bluetooth help"
];

function renderChips() {
    quickActions.innerHTML = '';
    popularChips.forEach(chip => {
        const span = document.createElement('span');
        span.className = 'chip';
        span.textContent = chip;
        span.onclick = () => {
            userInput.value = chip;
            sendMessage();
        };
        quickActions.appendChild(span);
    });
}
renderChips();

// Event Listeners
sendBtn.onclick = sendMessage;
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-resize textarea
userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

// Live Mode Logic
liveBtn.onclick = () => {
    if (isLive) {
        stopLive();
    } else {
        // check if pywebview api says consent given
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.check_consent().then(hasConsent => {
                if (hasConsent) {
                    startLive();
                } else {
                    consentModal.classList.remove('hidden');
                }
            });
        }
    }
};

document.getElementById('consent-no').onclick = () => {
    consentModal.classList.add('hidden');
};

document.getElementById('consent-yes').onclick = () => {
    consentModal.classList.add('hidden');
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.give_consent().then(() => {
            startLive();
        });
    }
};

function startLive() {
    isLive = true;
    liveBtn.className = 'btn btn-live on';
    liveBtn.textContent = '■ End Live';
    appendMessage("🔴 Live session starting...", "msg dim");
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.toggle_live(true);
    }
}

function stopLive() {
    isLive = false;
    liveBtn.className = 'btn btn-live off';
    liveBtn.textContent = 'Go Live';
    appendMessage("Live session ended.", "msg dim");
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.toggle_live(false);
    }
}

// Wait for pywebview initialization
window.addEventListener('pywebviewready', function() {
    appendMessage("System Ready. How can I help you?", "ai");
});
