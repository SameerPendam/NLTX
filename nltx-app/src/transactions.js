/* ===== NLTX Transactions JS (API Connected) ===== */

let ALL_TX = [];
let currentFilter = 'all';
let currentPage = 1;
const PER_PAGE = 10;

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Auth check
    if (!NLTX.requireAuth()) return;
    await NLTX.showServerBanner();

    // 2. Fetch User Info
    const user = NLTX.Auth.getUser();
    if (user) {
        document.querySelectorAll('.user-name').forEach(el => el.textContent = user.first_name || user.username);
        document.querySelectorAll('.user-email').forEach(el => el.textContent = user.email);
    }

    // 3. Load Stats
    loadStats();

    // 4. Load Transactions
    await fetchTransactions();
    renderTable();

    // 5. Setup Listeners
    setupListeners();
});

async function loadStats() {
    try {
        const stats = await NLTX.TxAPI.getStats();
        // Update summary cards
        document.querySelector('.stat-card:nth-child(1) .stat-card-value').textContent = `$${stats.total_sent_usd?.toLocaleString() || 0}`;
        document.querySelector('.stat-card:nth-child(2) .stat-card-value').textContent = `$${stats.total_received_usd?.toLocaleString() || 0}`;
        document.querySelector('.stat-card:nth-child(4) .stat-card-value').textContent = `$${stats.total_gas_usd?.toFixed(2) || 0}`;
    } catch (err) {
        console.warn("Stats API failed, using defaults", err);
    }
}

async function fetchTransactions() {
    try {
        const data = await NLTX.TxAPI.list({ limit: 100 });
        ALL_TX = data.transactions;
    } catch (err) {
        console.warn("Tx list API failed, using demo data", err);
        ALL_TX = NLTX.DemoData.transactions;
    }
}

function setupListeners() {
    document.querySelectorAll('.filter-pill').forEach(pill => {
        pill.addEventListener('click', function () {
            document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
            this.classList.add('active');
            currentFilter = this.dataset.filter;
            currentPage = 1;
            renderTable();
        });
    });

    document.getElementById('txSearch')?.addEventListener('input', () => {
        currentPage = 1;
        renderTable();
    });

    document.getElementById('exportCSV')?.addEventListener('click', () => {
        alert('Exporting transaction history as CSV...\n(In production, this connects to /api/transactions/export)');
    });

    document.getElementById('exportPDF')?.addEventListener('click', () => {
        alert('Generating PDF report...');
    });
}

function filterData() {
    const query = document.getElementById('txSearch')?.value?.toLowerCase() || '';
    return ALL_TX.filter(tx => {
        // Platform filter
        if (currentFilter !== 'all') {
            if (currentFilter === 'pending' && tx.status !== 'pending') return false;
            if (currentFilter === 'send' && tx.type !== 'send') return false;
            if (currentFilter === 'receive' && tx.type !== 'receive') return false;
            if (currentFilter === 'swap' && tx.type !== 'swap') return false;
        }

        // Search filter
        if (query) {
            const desc = (tx.memo || "").toLowerCase();
            const to = (tx.to_username || tx.to_address || "").toLowerCase();
            const from = (tx.from_address || "").toLowerCase();
            if (!desc.includes(query) && !to.includes(query) && !from.includes(query)) return false;
        }

        return true;
    });
}

function renderTable() {
    const data = filterData();
    const start = (currentPage - 1) * PER_PAGE;
    const end = start + PER_PAGE;
    const page = data.slice(start, end);
    const tbody = document.getElementById('txTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!page.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:40px">No transactions found</td></tr>';
        return;
    }

    page.forEach(tx => {
        const isReceive = tx.type === 'receive';
        const icon = isReceive ? '↓' : tx.type === 'swap' ? '⇄' : '↑';
        const badgeType = tx.type === 'send' ? 'badge-danger' : isReceive ? 'badge-success' : 'badge-info';

        const statusBadge = tx.status === 'confirmed' || tx.status === 'success'
            ? '<span class="badge badge-success">✓ Confirmed</span>'
            : tx.status === 'pending'
                ? '<span class="badge badge-warning">⏳ Pending</span>'
                : `<span class="badge badge-danger">✗ ${tx.status}</span>`;

        const amtClass = isReceive ? 'change-pos' : 'change-neg';
        const sign = isReceive ? '+' : '-';
        const hashDisplay = tx.tx_hash === 'Pending' || !tx.tx_hash
            ? '<span style="color:var(--text-muted)">Pending</span>'
            : `<a href="#" class="tx-hash-link" title="${tx.tx_hash}">${tx.tx_hash.slice(0, 10)}...</a>`;

        const desc = tx.memo || (isReceive ? `From ${tx.from_address?.slice(0, 8)}...` : `To ${tx.to_username || tx.to_address?.slice(0, 8)}...`);
        const dateStr = new Date(tx.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });

        const row = document.createElement('tr');
        row.className = 'tx-row';
        row.innerHTML = `
            <td><span class="badge ${badgeType}">${icon}</span></td>
            <td>
                <div style="font-weight:600;font-size:0.875rem">${desc}</div>
                <div style="font-size:0.75rem;color:var(--text-muted)">${tx.network || 'Polygon'}</div>
            </td>
            <td class="${amtClass}" style="font-weight:600">${sign}${tx.amount} ${tx.token}</td>
            <td>$${(tx.usd_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
            <td><span class="badge badge-purple" style="font-size:0.7rem">${tx.network || 'Polygon'}</span></td>
            <td>${statusBadge}</td>
            <td style="font-size:0.8rem;color:var(--text-secondary)">${dateStr}</td>
            <td class="tx-hash">${hashDisplay}</td>
        `;
        tbody.appendChild(row);
    });

    renderPagination(data.length);
}

function renderPagination(totalItems) {
    const totalPages = Math.ceil(totalItems / PER_PAGE);
    const pg = document.getElementById('pagination');
    if (!pg) return;
    pg.innerHTML = '';

    for (let i = 1; i <= totalPages; i++) {
        const b = document.createElement('div');
        b.className = `page-btn${i === currentPage ? ' active' : ''}`;
        b.textContent = i;
        b.onclick = () => {
            currentPage = i;
            renderTable();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        };
        pg.appendChild(b);
    }
}
