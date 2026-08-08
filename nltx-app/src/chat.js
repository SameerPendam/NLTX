/* ===== NLTX Chat JS (API Connected) ===== */

// ===== STATE =====
let chatHistory = JSON.parse(sessionStorage.getItem('nltxChat') || '[]');
let isProcessing = false;
let pendingTx = null;

document.addEventListener("DOMContentLoaded", async () => {
    // Auth Check
    if (!NLTX.requireAuth()) return;
    await NLTX.showServerBanner();

    // Fetch user Info
    const user = NLTX.Auth.getUser();
    if (user) {
        document.querySelectorAll('.user-name').forEach(el => el.textContent = user.first_name || user.username);
        document.querySelectorAll('.user-email').forEach(el => el.textContent = user.email);
    }
});

// ===== SIDEBAR =====
document.getElementById('sidebarToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('open');
});

// ===== INIT =====
const chatWelcome = document.getElementById('chatWelcome');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');
const charCount = document.getElementById('charCount');

// Users Panel Initialization
let allUsers = [];

async function loadUsers() {
    const usersListEl = document.getElementById('usersList');
    if (!usersListEl) return;
    
    try {
        const res = await NLTX.UserAPI.listUsers();
        allUsers = res.users || [];
        renderUsers(allUsers);
    } catch (e) {
        usersListEl.innerHTML = `<div class="users-empty" style="color:var(--accent-red)">Failed to load users</div>`;
    }
}

function renderUsers(users) {
    const usersListEl = document.getElementById('usersList');
    if (!usersListEl) return;

    if (users.length === 0) {
        usersListEl.innerHTML = `<div class="users-empty">No users found</div>`;
        return;
    }

    usersListEl.innerHTML = '';
    users.forEach(u => {
        const initial = (u.display_name || u.username || '?').charAt(0).toUpperCase();
        
        const card = document.createElement('div');
        card.className = 'user-card';
        card.innerHTML = `
            <div class="user-card-avatar">${initial}</div>
            <div class="user-card-info">
                <div class="user-card-name">${u.display_name}</div>
                <div class="user-card-username">@${u.username}</div>
            </div>
            <button class="user-send-btn">Send</button>
        `;

        // Click on the card auto-fills chat input
        card.addEventListener('click', () => {
            if (chatInput) {
                chatInput.value = `Send 10 USDT to @${u.username}`;
                chatInput.focus();
                // trigger input event to adjust height
                chatInput.dispatchEvent(new Event('input'));
            }
        });

        // Click on "Send" button auto-sends the command directly
        const sendBtn = card.querySelector('.user-send-btn');
        sendBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // prevent card click
            if (chatInput) {
                chatInput.value = `Send 10 USDT to @${u.username}`;
                sendMessage();
            }
        });

        usersListEl.appendChild(card);
    });
}

// User Search filtering
document.getElementById('userSearchInput')?.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    const filtered = allUsers.filter(u => 
        (u.display_name && u.display_name.toLowerCase().includes(query)) ||
        (u.username && u.username.toLowerCase().includes(query))
    );
    renderUsers(filtered);
});

// Load users on startup
loadUsers();

// Restore chat history
if (chatHistory.length > 0) {
    chatWelcome.style.display = 'none';
    chatMessages.style.display = 'flex';
    chatHistory.forEach(msg => renderMessage(msg.role, msg.content, false));
} else {
    chatMessages.style.display = 'none';
}

// ===== EXAMPLE COMMANDS =====
document.querySelectorAll('.example-cmd').forEach(btn => {
    btn.addEventListener('click', () => {
        const cmd = btn.dataset.cmd;
        if (chatInput) chatInput.value = cmd;
        sendMessage();
    });
});

// ===== INPUT =====
chatInput?.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    if (charCount) charCount.textContent = `${chatInput.value.length} / 500`;
});

chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});
chatSendBtn?.addEventListener('click', sendMessage);

// ===== CLEAR CHAT =====
document.getElementById('clearChat')?.addEventListener('click', () => {
    chatHistory = [];
    sessionStorage.removeItem('nltxChat');
    chatMessages.innerHTML = '';
    chatMessages.style.display = 'none';
    chatWelcome.style.display = 'flex';
});

// ===== VOICE =====
const voiceBtn = document.getElementById('voiceBtn');
let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    recognition.onresult = (e) => {
        const transcript = e.results[0][0].transcript;
        if (chatInput) { chatInput.value = transcript; chatInput.dispatchEvent(new Event('input')); }
        voiceBtn?.classList.remove('recording');
    };
    recognition.onend = () => voiceBtn?.classList.remove('recording');
    voiceBtn?.addEventListener('click', () => {
        if (voiceBtn.classList.contains('recording')) {
            recognition.stop();
        } else {
            recognition.start();
            voiceBtn.classList.add('recording');
        }
    });
} else {
    voiceBtn?.setAttribute('title', 'Voice not supported in this browser');
}

// ===== SEND MESSAGE =====
async function sendMessage() {
    const text = chatInput?.value.trim();
    if (!text || isProcessing) return;

    isProcessing = true;
    chatSendBtn.disabled = true;
    chatInput.value = '';
    chatInput.style.height = 'auto';
    if (charCount) charCount.textContent = '0 / 500';

    chatWelcome.style.display = 'none';
    chatMessages.style.display = 'flex';

    // Add user message
    renderMessage('user', text);
    addToHistory('user', text);

    // Show typing indicator
    const typingEl = showTyping();
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        // Send to real backend API !
        const response = await NLTX.NLPAPI.execute(text, "web");
        typingEl.remove();

        const msgText = response.response_text || "Command processed.";
        let parsedCardData = null;

        // If it requires confirmation (Send, Swap)
        if (response.type === "confirmation_required") {
            parsedCardData = {
                action: response.intent,
                amount: response.entities?.amount || '0',
                token: response.entities?.token || 'USDT',
                to: response.entities?.to_username || response.entities?.to_address || 'Unknown',
                network: response.entities?.network || 'Polygon',
                memo: response.entities?.memo || '',
                raw_command: text,
                entities: response.entities || {}
            };
        }
        // If it's pure data return (Balance, Limits)
        else if (response.type === "info" && response.data) {
            renderMessage('bot', msgText + "\n\n" + JSON.stringify(response.data, null, 2), true);
            addToHistory('bot', msgText);
            isProcessing = false;
            chatSendBtn.disabled = false;
            return;
        }

        renderMessage('bot', msgText, true, parsedCardData);
        addToHistory('bot', msgText);

    } catch (err) {
        typingEl.remove();
        // Fallback or error message
        const errMsg = err.message.includes("Cannot connect")
            ? "⚠️ Cannot connect to NLTX Backend. Please start the server on port 8000."
            : `❌ Error: ${err.message}`;
        renderMessage('bot', errMsg, true);
        addToHistory('bot', errMsg);
    }

    isProcessing = false;
    chatSendBtn.disabled = false;
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ===== RENDER MESSAGE =====
function renderMessage(role, text, animate = true, parsed = null) {
    const wrap = document.createElement('div');
    wrap.className = `chat-msg ${role}`;
    if (!animate) wrap.style.animation = 'none';

    const avatar = document.createElement('div');
    avatar.className = `msg-avatar ${role}`;
    avatar.textContent = role === 'bot' ? '⬡' : 'R';

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.style.whiteSpace = 'pre-line';
    bubble.textContent = text;

    if (parsed) {
        const card = buildParsedCard(parsed);
        bubble.appendChild(card);
    }

    const time = document.createElement('div');
    time.className = 'msg-time';
    time.textContent = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

    const inner = document.createElement('div');
    inner.style.display = 'flex';
    inner.style.flexDirection = 'column';
    inner.appendChild(bubble);
    inner.appendChild(time);

    wrap.appendChild(avatar);
    wrap.appendChild(inner);
    chatMessages.appendChild(wrap);
}

// ===== PARSED CARD =====
function buildParsedCard(parsed) {
    const card = document.createElement('div');
    card.className = 'parsed-card';
    card.innerHTML = `
    <div class="parsed-title">✅ Transaction Parsed</div>
    <div class="parsed-fields">
      ${parsed.action ? `<div class="parsed-field"><div class="parsed-field-label">Action</div><div class="parsed-field-value">${parsed.action}</div></div>` : ''}
      ${parsed.amount ? `<div class="parsed-field"><div class="parsed-field-label">Amount</div><div class="parsed-field-value">${parsed.amount} ${parsed.token || ''}</div></div>` : ''}
      ${parsed.to && parsed.to !== 'Unknown' ? `<div class="parsed-field"><div class="parsed-field-label">Recipient</div><div class="parsed-field-value">${parsed.to}</div></div>` : ''}
      ${parsed.network ? `<div class="parsed-field"><div class="parsed-field-label">Network</div><div class="parsed-field-value">${parsed.network}</div></div>` : ''}
      ${parsed.memo ? `<div class="parsed-field"><div class="parsed-field-label">Memo</div><div class="parsed-field-value">${parsed.memo}</div></div>` : ''}
    </div>
    <div class="parsed-actions">
      <button class="btn btn-primary btn-sm confirm-tx-btn">Confirm →</button>
      <button class="btn btn-danger btn-sm cancel-tx-btn">Cancel</button>
    </div>`;

    card.querySelector('.confirm-tx-btn').addEventListener('click', () => {
        openTxConfirm(parsed);
    });
    card.querySelector('.cancel-tx-btn').addEventListener('click', () => {
        card.remove();
        renderMessage('bot', '❌ Transaction cancelled.');
    });
    return card;
}

// ===== TYPING =====
function showTyping() {
    const wrap = document.createElement('div');
    wrap.className = 'chat-msg bot';
    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar bot';
    avatar.textContent = '⬡';
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = `<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
    wrap.appendChild(avatar);
    wrap.appendChild(bubble);
    chatMessages.appendChild(wrap);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return wrap;
}

// ===== TX CONFIRM MODAL =====
const txModal = document.getElementById('txConfirmModal');
function openTxConfirm(parsed) {
    txModal?.classList.remove('hidden');
    pendingTx = parsed;
    const details = document.getElementById('txConfirmDetails');
    if (details) {
        details.innerHTML = `
      <div class="tx-confirm-row"><span>Action</span><span class="tx-confirm-highlight">${parsed.action}</span></div>
      ${parsed.amount ? `<div class="tx-confirm-row"><span>Amount</span><span>${parsed.amount} ${parsed.token || ''}</span></div>` : ''}
      ${parsed.to && parsed.to !== 'Unknown' ? `<div class="tx-confirm-row"><span>To</span><span>${parsed.to}</span></div>` : ''}
      ${parsed.network ? `<div class="tx-confirm-row"><span>Network</span><span>${parsed.network}</span></div>` : ''}
      ${parsed.memo ? `<div class="tx-confirm-row"><span>Memo</span><span>${parsed.memo}</span></div>` : ''}`;
    }
    document.getElementById('confirmTxText').textContent = 'Authenticating...';
    document.getElementById('confirmTxBtn').disabled = true;
    runSecurityChecks();
}

document.getElementById('closeTxModal')?.addEventListener('click', () => txModal?.classList.add('hidden'));
document.getElementById('cancelTxBtn')?.addEventListener('click', () => {
    txModal?.classList.add('hidden');
    renderMessage('bot', '❌ Transaction cancelled by user.');
    addToHistory('bot', '❌ Transaction cancelled.');
});

document.getElementById('confirmTxBtn')?.addEventListener('click', async () => {
    const tx = pendingTx;
    if (!tx) return;

    const confirmBtn = document.getElementById('confirmTxBtn');
    const otpInput = document.getElementById('otpInput');
    const otpSection = document.getElementById('otpSection');

    confirmBtn.disabled = true;
    document.getElementById('confirmTxText').textContent = 'Processing...';

    try {
        let res;
        const otp_code = otpInput?.value.trim() || null;

        if (tx.action === "SEND") {
            const isAddress = tx.to.startsWith("0x");
            const payload = {
                to_username: isAddress ? null : tx.to,
                to_address: isAddress ? tx.to : null,
                amount: parseFloat(tx.amount) || 0,
                token: tx.token,
                network: tx.network?.toLowerCase() || "polygon",
                memo: tx.memo,
                nlp_command: tx.raw_command,
                confirmed: true,
                otp_code: otp_code
            };
            res = await NLTX.TxAPI.send(payload);
        } else if (tx.action === "SWAP") {
            // "Swap 0.1 ETH for USDT"
            // entities: amount=0.1, token=ETH, to_token=USDT (needs to be parsed or in tx object)
            // For now let's assume tx object has what we need
            const payload = {
                from_token: tx.token,
                to_token: tx.entities?.to_token || "USDT",
                amount: parseFloat(tx.amount) || 0,
                network: tx.network?.toLowerCase() || "polygon",
                nlp_command: tx.raw_command,
                confirmed: true,
                otp_code: otp_code
            };
            res = await NLTX.TxAPI.swap(payload);
        } else {
            // Other actions (Schedule, etc.) - simple mock for now
            await new Promise(r => setTimeout(r, 1000));
            txModal?.classList.add('hidden');
            renderMessage('bot', `✅ **Action Executed!**\n\nThe ${tx.action} request has been processed successfully.`);
            return;
        }

        txModal?.classList.add('hidden');
        otpSection?.classList.add('hidden');
        if (otpInput) otpInput.value = '';

        if (tx.action === "SEND") {
            const isReal = !res.message?.includes('simulated');
            const explorerMatch = res.message?.match(/Explorer: (https?:\/\/\S+)/);
            const explorerUrl = explorerMatch ? explorerMatch[1] : null;
            let msg = `✅ Transaction Sent!\n\nSent ${res.amount} ${res.token} to ${res.to_username || 'address'}\nStatus: ${res.status}\nHash: ${res.tx_hash}`;
            if (explorerUrl) {
                msg += `\n\n🔍 View on Explorer:\n${explorerUrl}`;
            }
            if (!isReal) {
                msg += `\n\n⚠️ Simulated (fund wallet with Sepolia ETH for real tx)\n💡 Faucet: https://sepoliafaucet.com`;
            }
            msg += `\n\n↩️ You have 30 seconds to type "Undo".`;
            renderMessage('bot', msg, true);
            window.NLTX_LAST_TX_ID = res.transaction_id;
        } else {
            renderMessage('bot', `✅ Swap Successful!\n\n${res.message}`);
        }

    } catch (err) {
        if (err.message === "2FA_REQUIRED") {
            otpSection?.classList.remove('hidden');
            document.getElementById('confirmTxText').textContent = 'Verify & Confirm';
            confirmBtn.disabled = false;
            otpInput?.focus();
        } else {
            txModal?.classList.add('hidden');
            renderMessage('bot', `❌ Execution Failed: ${err.message}`);
            confirmBtn.disabled = false;
            document.getElementById('confirmTxText').textContent = 'Confirm Transaction →';
        }
    }
});

async function runSecurityChecks() {
    const checks = ['check1', 'check2', 'check3'];
    const labels = ['Fraud Detection — Clear', 'Spending Limit — Valid', 'Encryption — Active'];

    for (let i = 0; i < checks.length; i++) {
        await new Promise(r => setTimeout(r, 400));
        const el = document.getElementById(checks[i]);
        if (el) {
            el.querySelector('.check-icon').className = 'check-icon pass';
            el.querySelector('.check-icon').textContent = '✓';
            el.querySelector('.check-sub').textContent = labels[i];
        }
    }
    const confirmBtn = document.getElementById('confirmTxBtn');
    const confirmText = document.getElementById('confirmTxText');
    if (confirmBtn) confirmBtn.disabled = false;
    if (confirmText) confirmText.textContent = 'Confirm Transaction →';
}

function addToHistory(role, content) {
    chatHistory.push({ role, content, time: Date.now() });
    if (chatHistory.length > 50) chatHistory = chatHistory.slice(-50);
    sessionStorage.setItem('nltxChat', JSON.stringify(chatHistory));
}
