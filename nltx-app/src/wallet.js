/* ===== NLTX Wallet JS (API Connected) ===== */

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Auth check
    if (!NLTX.requireAuth()) return;
    await NLTX.showServerBanner();

    // 2. User info
    const user = NLTX.Auth.getUser();
    if (user) {
        document.querySelectorAll('.user-name').forEach(el => el.textContent = user.first_name || user.username);
        document.querySelectorAll('.user-email').forEach(el => el.textContent = user.email);
    }

    // 3. Load wallets & tokens
    await loadWalletData();
});

async function loadWalletData() {
    try {
        const data = await NLTX.WalletAPI.getBalances();
        const balances = data.balances || [];

        // Update network wallet cards
        updateNetworkCards(balances);

        // Update token grid
        updateTokenGrid(balances);

    } catch (err) {
        console.warn("Wallet API failed, using demo data", err);
        updateNetworkCards(NLTX.DemoData.balances);
        updateTokenGrid(NLTX.DemoData.balances);
    }
}

function updateNetworkCards(balances) {
    // Map of token symbol -> card class suffix
    const cardMap = {
        'ETH': '.wc-eth',
        'MATIC': '.wc-matic',
        'SOL': '.wc-sol'
    };

    balances.forEach(b => {
        const selector = cardMap[b.token.toUpperCase()];
        if (!selector) return;
        const card = document.querySelector(selector);
        if (!card) return;

        const balEl = card.querySelector('.wallet-card-balance');
        const usdEl = card.querySelector('.wallet-card-usd');
        const addrEl = card.querySelector('.wallet-card-addr');

        if (balEl) balEl.textContent = `${b.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${b.token}`;
        if (usdEl) usdEl.textContent = `≈ $${(b.usd_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })} USD`;
        // In real app, we'd fetch address per network. Using demo ones for now.
    });
}

function updateTokenGrid(balances) {
    const grid = document.querySelector('.token-grid');
    if (!grid) return;

    // Keep the "Add Token" dashed card
    const addTokenCard = grid.querySelector('[onclick*="Add custom token"]');
    grid.innerHTML = '';

    balances.forEach(b => {
        const sign = b.change_24h >= 0 ? "+" : "";
        const changeClass = b.change_24h >= 0 ? "change-pos" : "change-neg";
        const iconColor = b.token === 'ETH' ? '#627EEA' : b.token === 'USDT' ? '#26A17B' : b.token === 'MATIC' ? '#8247E5' : '#9945FF';
        const iconChar = b.token === 'ETH' ? 'Ξ' : b.token === 'USDT' ? '₮' : b.token === 'SOL' ? '●' : '⬡';

        const card = document.createElement('div');
        card.className = 'token-card';
        card.innerHTML = `
            <div class="token-card-icon" style="color:${iconColor}">${iconChar}</div>
            <div class="token-card-name">${b.token === 'MATIC' ? 'Polygon' : b.token === 'SOL' ? 'Solana' : b.token}</div>
            <div class="token-card-sym">${b.token} · ${b.network}</div>
            <div class="token-card-balance">${b.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })}</div>
            <div class="token-card-usd">$${(b.usd_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            <div class="token-card-change ${changeClass}">${sign}${b.change_24h}%</div>
        `;
        grid.appendChild(card);
    });

    if (addTokenCard) grid.appendChild(addTokenCard);
}
