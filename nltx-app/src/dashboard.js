/* ===== NLTX Dashboard JS (API Connected) ===== */

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Check Auth & Server Status
    if (!NLTX.requireAuth()) return;
    await NLTX.showServerBanner();

    // 2. Fetch fresh user data from API (not just localStorage)
    let user = NLTX.Auth.getUser();
    try {
        const freshUser = await NLTX.AuthAPI.getMe();
        if (freshUser) {
            user = freshUser;
            NLTX.Auth.setUser(freshUser);
        }
    } catch(e) { /* use cached user */ }

    if (user) {
        const displayName = user.first_name || user.username || 'User';
        document.querySelectorAll('.user-name').forEach(el => el.textContent = displayName);
        document.querySelectorAll('.user-email').forEach(el => el.textContent = user.email || '');
        // Update the greeting on the dashboard
        const greetEl = document.querySelector('.greeting-name');
        if (greetEl) greetEl.textContent = displayName;
    }

    // 3. Load Data
    await loadDashboardData();
    loadWalletAddress();
    drawMiniChart();
});

// ===== SIDEBAR TOGGLE =====
document.getElementById('sidebarToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('open');
});

// ===== DATA LOADING (Real + Fallback) =====
async function loadDashboardData() {
    let balances, stats, txs;
    try {
        // Try real API
        const balData = await NLTX.WalletAPI.getBalances();
        balances = balData.balances;
        const totalUsd = balData.total_usd;

        stats = await NLTX.TxAPI.getStats();
        const txData = await NLTX.TxAPI.list({ limit: 6 });
        txs = txData.transactions;

        animateCounter(document.getElementById('portfolioValue'), totalUsd);
        document.getElementById('statSent').textContent = `$${stats.total_sent_usd?.toLocaleString() || 0}`;
        document.getElementById('statGas').textContent = `$${stats.total_gas_usd?.toFixed(2) || 0}`;
    } catch (err) {
        // Fallback to demo data
        balances = NLTX.DemoData.balances;
        txs = NLTX.DemoData.transactions;
        animateCounter(document.getElementById('portfolioValue'), NLTX.DemoData.totalUsd);
        document.getElementById('statSent').textContent = `$24,830`;
        document.getElementById('statGas').textContent = `$183.40`;
    }

    renderBalances(balances);
    renderTransactions(txs);
}

// ===== RENDER BALANCES =====
function renderBalances(balances) {
    const list = document.getElementById('walletBalancesList');
    if (!list) return;
    list.innerHTML = '';
    balances.forEach(b => {
        const changeClass = b.change_24h >= 0 ? "text-success" : "text-danger";
        const sign = b.change_24h >= 0 ? "+" : "";
        list.innerHTML += `
        <div class="wallet-item">
            <div class="wallet-icon">${b.token.charAt(0)}</div>
            <div class="wallet-info">
                <h4>${b.token} <span style="font-size:0.7rem;color:var(--text-muted);font-weight:400">on ${b.network}</span></h4>
                <p>${b.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })} ≈ $${b.usd_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
            </div>
            <div class="wallet-change ${changeClass}">${sign}${b.change_24h}%</div>
        </div>`;
    });
}

// ===== RENDER TRANSACTIONS =====
function renderTransactions(txs) {
    const list = document.getElementById('txList');
    if (!list) return;
    list.innerHTML = '';

    txs.forEach(tx => {
        const isReceive = tx.type === 'receive';
        const iconClasses = { send: 'tx-type-send', receive: 'tx-type-receive', swap: 'tx-type-swap', schedule: 'tx-type-schedule' };
        const icons = { send: '↑', receive: '↓', swap: '⇄', schedule: '⏰' };

        const descMatch = tx.memo || (isReceive ? `Received from ${tx.from_address || 'External'}` : `Sent to ${tx.to_username || tx.to_address}`);
        const dateStr = new Date(tx.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const metaStr = `${dateStr} · ${tx.network || 'unknown'}`;

        const amountSign = isReceive ? '+' : '-';
        const amountClass = isReceive ? 'in' : 'out';
        const statusColors = { confirmed: 'badge-success', pending: 'badge-warning', failed: 'badge-danger', undone: 'badge-danger' };

        list.innerHTML += `
        <div class="tx-item">
            <div class="tx-type-icon ${iconClasses[tx.type] || 'tx-type-send'}">${icons[tx.type] || '→'}</div>
            <div class="tx-info">
                <div class="tx-desc">${descMatch}</div>
                <div class="tx-meta">${metaStr}</div>
            </div>
            <div class="tx-amount-col">
                <div class="tx-amount ${amountClass}">${amountSign}${tx.amount} ${tx.token}</div>
                <div class="tx-status-badge"><span class="badge ${statusColors[tx.status] || 'badge-info'}" style="font-size:0.65rem">${tx.status}</span></div>
            </div>
        </div>`;
    });
}

// ===== ANIMATE COUNTER =====
function animateCounter(el, target, prefix = '$') {
    if (!el) return;
    const start = 0; const duration = 1500; const startTime = performance.now();
    function update(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = start + (target - start) * eased;
        el.textContent = prefix + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ===== MINI CHART =====
function drawMiniChart() {
    const canvas = document.getElementById('miniChart');
    if (!canvas) return;
    canvas.width = canvas.parentElement.offsetWidth;
    canvas.height = 80;
    const ctx = canvas.getContext('2d');
    const data = [10800, 11200, 10950, 11800, 12100, 11750, 12847];
    const w = canvas.width, h = canvas.height;
    const min = Math.min(...data) * 0.98, max = Math.max(...data) * 1.01;
    const xStep = w / (data.length - 1);
    const yScale = (v) => h - ((v - min) / (max - min)) * h;

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(124,58,237,0.3)');
    grad.addColorStop(1, 'rgba(124,58,237,0)');

    ctx.beginPath(); ctx.moveTo(0, yScale(data[0]));
    data.forEach((v, i) => ctx.lineTo(i * xStep, yScale(v)));
    ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();

    ctx.beginPath(); ctx.moveTo(0, yScale(data[0]));
    data.forEach((v, i) => ctx.lineTo(i * xStep, yScale(v)));
    ctx.strokeStyle = '#7c3aed'; ctx.lineWidth = 2; ctx.stroke();
}
window.addEventListener('resize', drawMiniChart);

// ===== NOTIFICATION HELPER =====
window.showNotification = function (msg, type = 'info') {
    const notif = document.createElement('div');
    notif.style.cssText = `position:fixed;top:20px;right:20px;z-index:9999;
    background:var(--bg-secondary);border:1px solid ${type === 'success' ? 'rgba(16,185,129,0.3)' : type === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(37,99,235,0.3)'};
    border-radius:12px;padding:14px 20px;font-size:0.875rem;
    color:${type === 'success' ? '#34d399' : type === 'error' ? '#ef4444' : '#60a5fa'};
    box-shadow:0 8px 32px rgba(0,0,0,0.4); animation:slideIn 0.3s ease;`;
    notif.textContent = (type === 'success' ? '✅ ' : type === 'error' ? '❌ ' : 'ℹ️ ') + msg;
    document.body.appendChild(notif);
    setTimeout(() => notif.remove(), 4000);
}

// ===== NLP PARSE & SEND =====
let currentParsedIntent = null;

// Parse button in Send modal
document.getElementById('nlpParseBtn')?.addEventListener('click', async () => {
    const input = document.getElementById('nlpParseInput')?.value;
    if (!input) return;

    document.getElementById('nlpParseBtn').textContent = "...";
    try {
        const res = await NLTX.NLPAPI.parse(input);
        currentParsedIntent = res;
        const e = res.entities || {};

        if (document.getElementById('sendTo')) document.getElementById('sendTo').value = e.to_username || e.to_address || '';
        if (document.getElementById('sendAmount')) document.getElementById('sendAmount').value = e.amount || '';
        if (document.getElementById('sendToken')) {
            const tokInput = document.getElementById('sendToken');
            Array.from(tokInput.options).forEach(opt => { if (opt.value === e.token) opt.selected = true; });
        }
        if (document.getElementById('sendMemo')) document.getElementById('sendMemo').value = e.memo || '';

        updatePreview();
        showNotification("📝 " + res.response_text, "success");
    } catch (err) {
        showNotification(err.message, "error");
    } finally {
        document.getElementById('nlpParseBtn').textContent = "Parse Command";
    }
});

function updatePreview() {
    const amount = parseFloat(document.getElementById('sendAmount')?.value || 0);
    const token = document.getElementById('sendToken')?.value || 'USDT';
    const preview = document.getElementById('txPreview');
    if (preview) {
        const totalEl = preview.querySelector('.preview-total');
        if (totalEl) totalEl.textContent = `${amount} ${token} ≈ Checking...`;

        // Fetch real price
        NLTX.WalletAPI.getPrice(token).then(data => {
            const usd = amount * (data.price_usd || 1);
            if (totalEl) totalEl.textContent = `${amount} ${token} ≈ $${usd.toFixed(2)}`;
        }).catch(e => {
            if (totalEl) totalEl.textContent = `${amount} ${token}`;
        });
    }
}
document.getElementById('sendAmount')?.addEventListener('input', updatePreview);
document.getElementById('sendToken')?.addEventListener('change', updatePreview);

// Send Confirm Logic
const sendModal = document.getElementById('sendModal');
document.getElementById('sendBtn')?.addEventListener('click', () => { sendModal?.classList.remove('hidden'); });
document.getElementById('closeSendModal')?.addEventListener('click', () => sendModal?.classList.add('hidden'));

let currentTxId = null;
let undoInterval;

document.getElementById('confirmSendBtn')?.addEventListener('click', async () => {
    const to = document.getElementById('sendTo').value;
    const amount = parseFloat(document.getElementById('sendAmount').value);
    const token = document.getElementById('sendToken').value;
    const memo = document.getElementById('sendMemo').value;

    if (!to || !amount) { showNotification("Please fill amount and recipient", "error"); return; }

    const isAddress = to.startsWith("0x");
    const payload = {
        to_username: isAddress ? null : to,
        to_address: isAddress ? to : null,
        amount: amount,
        token: token,
        network: token === 'ETH' ? 'ethereum' : 'polygon',
        memo: memo,
        confirmed: true
    };

    const btn = document.getElementById('confirmSendBtn');
    const otpInput = document.getElementById('otpInput');
    const otpSection = document.getElementById('otpSection');

    if (otpSection && !otpSection.classList.contains('hidden')) {
        payload.otp_code = otpInput.value;
    }

    btn.textContent = "Processing...";
    btn.disabled = true;

    try {
        const res = await NLTX.TxAPI.send(payload);

        if (res.status === "2FA_REQUIRED") {
            showNotification("Security check required", "info");
            otpSection?.classList.remove('hidden');
            otpInput?.focus();
            btn.textContent = "Verify & Execute";
            btn.disabled = false;
            return;
        }

        sendModal.classList.add('hidden');
        otpSection?.classList.add('hidden');
        if (otpInput) otpInput.value = '';

        showUndoToast(res.transaction_id);
        setTimeout(loadDashboardData, 1000); // Reload balances
    } catch (err) {
        showNotification(err.message, "error");
    } finally {
        if (btn.textContent === "Processing...") {
            btn.textContent = "Confirm & Send";
            btn.disabled = false;
            document.getElementById('sendTo').value = '';
            document.getElementById('sendAmount').value = '';
            document.getElementById('nlpParseInput').value = '';
        }
    }
});

// QUICK SEND
const quickSendBtn = document.getElementById('quickSendBtn');
if (quickSendBtn) {
    quickSendBtn.addEventListener('click', () => {
        const val = document.getElementById('quickSend').value;
        sendModal?.classList.remove('hidden');
        const nlpInp = document.getElementById('nlpParseInput');
        if (nlpInp) {
            nlpInp.value = val;
            document.getElementById('nlpParseBtn').click();
        }
    });
}

function showUndoToast(txId) {
    currentTxId = txId;
    const toast = document.getElementById('undoToast');
    if (!toast) return;
    toast.classList.remove('hidden');
    let count = 30;
    const countEl = document.getElementById('undoCountdown');
    if (undoInterval) clearInterval(undoInterval);
    undoInterval = setInterval(() => {
        count--;
        if (countEl) countEl.textContent = count;
        if (count <= 0) {
            clearInterval(undoInterval);
            toast.classList.add('hidden');
        }
    }, 1000);
}

document.getElementById('undoBtn')?.addEventListener('click', async () => {
    if (!currentTxId) return;
    try {
        await NLTX.TxAPI.undo(currentTxId);
        clearInterval(undoInterval);
        document.getElementById('undoToast')?.classList.add('hidden');
        showNotification('Transaction undone successfully', 'success');
        setTimeout(loadDashboardData, 1000);
    } catch (err) {
        showNotification(err.message, "error");
    }
});

// REFRESH BUTTON
document.getElementById('refreshBalances')?.addEventListener('click', async function () {
    this.style.opacity = '0.5';
    this.textContent = '↻ Loading...';
    await loadDashboardData();
    this.style.opacity = '1';
    this.textContent = '↻ Refresh';
    showNotification('Balances updated', 'success');
});

// OTHER MODALS
const receiveModal = document.getElementById('receiveModal');
document.getElementById('receiveBtn')?.addEventListener('click', () => receiveModal?.classList.remove('hidden'));
document.getElementById('closeReceiveModal')?.addEventListener('click', () => receiveModal?.classList.add('hidden'));
document.getElementById('copyAddressBtn')?.addEventListener('click', () => {
    const addrEl = document.getElementById('receiveAddress');
    const addr = addrEl?.textContent?.trim() || '';
    if (addr && addr !== 'Loading...' && addr !== 'N/A') {
        navigator.clipboard.writeText(addr);
        showNotification("Address copied to clipboard!", "success");
    }
});

async function loadWalletAddress() {
    const addrEl = document.getElementById('receiveAddress');
    const explorerEl = document.getElementById('receiveExplorerLink');
    const faucetEl = document.getElementById('receiveFaucetLink');
    try {
        const data = await NLTX.WalletAPI.getAddresses();
        const ethWallet = data.addresses?.find(a => a.network === 'ethereum');
        if (ethWallet && addrEl) {
            addrEl.textContent = ethWallet.address;
            if (explorerEl) {
                explorerEl.href = ethWallet.explorer;
                explorerEl.style.display = 'inline';
            }
            if (faucetEl) {
                faucetEl.href = ethWallet.faucet;
                faucetEl.style.display = 'inline';
            }
        }
    } catch(e) { if (addrEl) addrEl.textContent = 'N/A'; }
}

// LOGOUT
document.getElementById('logoutBtn')?.addEventListener('click', () => {
    NLTX.AuthAPI.logout();
});
