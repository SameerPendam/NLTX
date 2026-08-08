/* ===== NLTX Analytics JS (API Connected) ===== */

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

    // 3. Load Analytics
    await loadAnalytics();
});

async function loadAnalytics() {
    try {
        const summary = await NLTX.AnalyticsAPI.getSummary();

        // Update Stats
        const netFlowEl = document.querySelector('.stat-card:nth-child(1) .stat-card-value');
        if (netFlowEl) netFlowEl.textContent = `+$${summary.performance_24h.usd.toLocaleString()}`;

        const changeEl = document.querySelector('.stat-card:nth-child(1) .stat-card-change');
        if (changeEl) changeEl.textContent = `↑ ${summary.performance_24h.percentage}% vs last month`;

        // Load Portfolio Chart
        await updatePortfolioChart('7d');

        // Draw category chart
        if (summary.category_breakdown) {
            drawCategoryChart(summary.category_breakdown);
        }

        // Draw secondary charts
        drawVolumeChart();
        drawNLPChart();

    } catch (err) {
        console.warn("Analytics API failed, using fallback data", err);
        await updatePortfolioChart('7d');
        drawVolumeChart();
        drawNLPChart();
    }
}

// Portfolio chart
async function updatePortfolioChart(period = '7d') {
    const c = document.getElementById('portfolioChart');
    if (!c) return;
    c.width = c.parentElement.offsetWidth;
    c.height = 200;
    const ctx = c.getContext('2d');

    let history;
    try {
        const data = await NLTX.AnalyticsAPI.getPortfolioHistory(period);
        history = data.history.map(p => p.value);
    } catch (e) {
        // Mock data fallback
        const datasets = {
            '7d': [10800, 11200, 10950, 11800, 12100, 11750, 12847],
            '30d': [8000, 8500, 9200, 8800, 9800, 10200, 10800, 11200, 10950, 11800, 12100, 11750, 12200, 12847],
            '90d': [6000, 6500, 7000, 7200, 7800, 8200, 8000, 8500, 9200, 8800, 9800, 10200, 10800, 11200, 10950, 11800, 12100, 11750, 12847],
            '1y': [4000, 5000, 6500, 7500, 9000, 10500, 11000, 9000, 11500, 12000, 11500, 12847]
        };
        history = datasets[period] || datasets['7d'];
    }

    const data = history;
    const w = c.width, h = c.height, pad = 30;
    const min = Math.min(...data) * 0.97, max = Math.max(...data) * 1.02;
    const xStep = (w - pad * 2) / (data.length - 1);
    const ys = v => pad + (1 - (v - min) / (max - min)) * (h - pad * 2);

    ctx.clearRect(0, 0, w, h);

    // Grid lines
    for (let i = 0; i <= 4; i++) {
        const y = pad + i * (h - pad * 2) / 4;
        ctx.strokeStyle = 'rgba(255,255,255,0.04)'; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
        const val = max - (i / 4) * (max - min);
        ctx.fillStyle = 'rgba(255,255,255,0.2)'; ctx.font = '10px Inter'; ctx.textAlign = 'right';
        ctx.fillText('$' + Math.round(val).toLocaleString(), pad - 4, y + 4);
    }

    // Gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, 'rgba(124,58,237,0.25)'); grad.addColorStop(1, 'rgba(124,58,237,0)');
    ctx.beginPath(); ctx.moveTo(pad, ys(data[0]));
    data.forEach((v, i) => ctx.lineTo(pad + i * xStep, ys(v)));
    ctx.lineTo(pad + (data.length - 1) * xStep, h - pad); ctx.lineTo(pad, h - pad); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();

    // Line
    ctx.beginPath(); ctx.moveTo(pad, ys(data[0]));
    data.forEach((v, i) => ctx.lineTo(pad + i * xStep, ys(v)));
    ctx.strokeStyle = '#7c3aed'; ctx.lineWidth = 2.5; ctx.stroke();
}

function drawCategoryChart(cats) {
    const c = document.getElementById('categoryChart'); if (!c) return;
    c.width = c.parentElement.offsetWidth; c.height = 180;
    const ctx = c.getContext('2d');

    const cx = c.width / 2, cy = c.height / 2, r = 70, inner = 45;
    let angle = -Math.PI / 2;
    cats.forEach(cat => {
        const slice = 2 * Math.PI * cat.value / 100;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, angle, angle + slice); ctx.closePath();
        ctx.fillStyle = cat.color; ctx.fill();
        angle += slice;
    });
    ctx.beginPath(); ctx.arc(cx, cy, inner, 0, Math.PI * 2); ctx.fillStyle = 'rgba(11,15,28,1)'; ctx.fill();

    // Legend
    const list = document.getElementById('catList'); if (!list) return; list.innerHTML = '';
    cats.forEach(cat => {
        list.innerHTML += `<div class="cat-item"><div class="cat-dot" style="background:${cat.color}"></div><div class="cat-info"><div class="cat-name">${cat.label}</div><div class="cat-bar-wrap"><div class="cat-bar" style="width:${cat.value}%;background:${cat.color}"></div></div></div><div class="cat-val">${cat.value}%</div></div>`;
    });
}

function drawVolumeChart() {
    const c = document.getElementById('volumeChart'); if (!c) return;
    c.width = c.parentElement.offsetWidth; c.height = 180;
    const ctx = c.getContext('2d');
    const data = [120, 340, 180, 520, 290, 410, 680, 230, 570, 440, 300, 610, 380, 490];
    const labels = ['Feb 20', '21', '22', '23', '24', '25', '26', '27', '28', 'Mar 1', '2', '3', '4', '5'];
    const w = c.width, h = c.height, pad = 30;
    const max = Math.max(...data) * 1.1;
    const barW = (w - pad * 2) / data.length - 4;
    ctx.clearRect(0, 0, w, h);
    data.forEach((v, i) => {
        const bh = (v / max) * (h - pad);
        const x = pad + i * ((w - pad * 2) / data.length) + 2;
        const grad = ctx.createLinearGradient(0, h - pad - bh, 0, h - pad);
        grad.addColorStop(0, 'rgba(124,58,237,0.8)'); grad.addColorStop(1, 'rgba(37,99,235,0.4)');
        ctx.fillStyle = grad;
        const r = 4; const bx = x, by = h - pad - bh, bw = barW;
        ctx.beginPath(); ctx.moveTo(bx + r, by); ctx.lineTo(bx + bw - r, by); ctx.quadraticCurveTo(bx + bw, by, bx + bw, by + r); ctx.lineTo(bx + bw, by + bh); ctx.lineTo(bx, by + bh); ctx.lineTo(bx, by + r); ctx.quadraticCurveTo(bx, by, bx + r, by); ctx.closePath();
        ctx.fill();
        if (i % 2 === 0) { ctx.fillStyle = 'rgba(255,255,255,0.2)'; ctx.font = '8px Inter'; ctx.textAlign = 'center'; ctx.fillText(labels[i].slice(-2), x + barW / 2, h - pad + 12); }
    });
}

function drawNLPChart() {
    const c = document.getElementById('nlpChart'); if (!c) return;
    c.width = c.parentElement.offsetWidth; c.height = 180;
    const ctx = c.getContext('2d');
    const types = [
        { name: 'Send/Pay', val: 57, color: '#7c3aed' },
        { name: 'Balance/Info', val: 22, color: '#2563eb' },
        { name: 'Swap', val: 12, color: '#06b6d4' },
        { name: 'Schedule', val: 6, color: '#10b981' },
        { name: 'Settings', val: 3, color: '#f59e0b' },
    ];
    const cx = 90, cy = c.height / 2, r = 65, inner = 42;
    let angle = -Math.PI / 2;
    types.forEach(t => {
        const slice = 2 * Math.PI * t.val / 100;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.arc(cx, cy, r, angle, angle + slice); ctx.closePath();
        ctx.fillStyle = t.color; ctx.fill(); angle += slice;
    });
    ctx.beginPath(); ctx.arc(cx, cy, inner, 0, Math.PI * 2); ctx.fillStyle = 'rgba(11,15,28,1)'; ctx.fill();
    ctx.fillStyle = '#fff'; ctx.font = 'bold 14px Space Grotesk'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('127', cx, cy - 8); ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.font = '9px Inter'; ctx.fillText('Commands', cx, cy + 8);
    const legend = document.getElementById('nlpLegend'); if (!legend) return; legend.innerHTML = '';
    types.forEach(t => { legend.innerHTML += `<div style="display:flex;align-items:center;gap:8px;font-size:0.78rem"><span style="width:10px;height:10px;border-radius:50%;background:${t.color};display:inline-block;flex-shrink:0"></span><span style="flex:1;color:var(--text-secondary)">${t.name}</span><span style="font-weight:600">${t.val}%</span></div>`; });
}

// Time buttons
document.querySelectorAll('.time-btn').forEach(btn => {
    btn.addEventListener('click', async function () {
        document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        await updatePortfolioChart(this.dataset.period);
    });
});

window.addEventListener('resize', () => {
    updatePortfolioChart(document.querySelector('.time-btn.active')?.dataset.period || '7d');
});
