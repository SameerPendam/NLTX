/**
 * NLTX API Client
 * Central module for all frontend → backend communication
 * All pages import this instead of hardcoding fetch calls
 */

const API_BASE = "http://localhost:8000";

// ============================================================
//  TOKEN MANAGEMENT
// ============================================================
const Auth = {
    setToken: (token) => localStorage.setItem("nltx_token", token),
    getToken: () => localStorage.getItem("nltx_token"),
    setUser: (user) => localStorage.setItem("nltx_user", JSON.stringify(user)),
    getUser: () => { try { return JSON.parse(localStorage.getItem("nltx_user")); } catch { return null; } },
    clear: () => { localStorage.removeItem("nltx_token"); localStorage.removeItem("nltx_user"); },
    isLoggedIn: () => !!localStorage.getItem("nltx_token"),
};

// ============================================================
//  BASE FETCH WRAPPER
// ============================================================
async function apiFetch(method, endpoint, body = null, requireAuth = true) {
    const headers = { "Content-Type": "application/json" };
    if (requireAuth) {
        const token = Auth.getToken();
        if (!token) {
            // Redirect to login if no token
            window.location.href = "login.html";
            return;
        }
        headers["Authorization"] = `Bearer ${token}`;
    }

    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);

    try {
        const res = await fetch(`${API_BASE}${endpoint}`, options);

        // Token expired or invalid → redirect to login
        if (res.status === 401) {
            Auth.clear();
            window.location.href = "login.html";
            return null;
        }

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            throw new Error(data.detail || data.error || `HTTP ${res.status}`);
        }
        return data;

    } catch (err) {
        if (err.message.includes("Failed to fetch") || err.message.includes("NetworkError")) {
            throw new Error("Cannot connect to NLTX server. Make sure backend is running on port 8000.");
        }
        throw err;
    }
}

// ============================================================
//  AUTH API
// ============================================================
const AuthAPI = {
    async register(payload) {
        return apiFetch("POST", "/api/auth/register", payload, false);
    },

    async login(username, password) {
        // OAuth2 form-encoded (required by FastAPI)
        const form = new URLSearchParams({ username, password });
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: "POST",
            body: form,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Login failed");
        return data;
    },

    async getMe() {
        return apiFetch("GET", "/api/auth/me");
    },

    async logout() {
        Auth.clear();
        window.location.href = "login.html";
    },
};

// ============================================================
//  NLP API
// ============================================================
const NLPAPI = {
    async parse(text, platform = "web", history = []) {
        return apiFetch("POST", "/api/nlp/parse", { text, platform, conversation_history: history });
    },

    async execute(text, platform = "web") {
        return apiFetch("POST", "/api/nlp/execute", { text, platform });
    },

    async getHistory(limit = 20) {
        return apiFetch("GET", `/api/nlp/history?limit=${limit}`);
    },

    async getStats() {
        return apiFetch("GET", "/api/nlp/stats");
    },
};

// ============================================================
//  WALLET API
// ============================================================
const WalletAPI = {
    async getBalances() {
        return apiFetch("GET", "/api/wallet/balances");
    },

    async getPrice(token) {
        return apiFetch("GET", `/api/wallet/price/${token}`);
    },

    async getGas(network = "polygon") {
        return apiFetch("GET", `/api/wallet/gas/${network}`);
    },

    async getNetworkStatus() {
        return apiFetch("GET", "/api/wallet/network-status", null, false);
    },

    async getSpendingLimits() {
        return apiFetch("GET", "/api/wallet/spending-limits");
    },

    async getAddresses() {
        return apiFetch("GET", "/api/wallet/address");
    },
};

// ============================================================
//  USER API
// ============================================================
const UserAPI = {
    async getMe() {
        return apiFetch("GET", "/api/users/me");
    },
    async updateMe(payload) {
        return apiFetch("PUT", "/api/users/me", payload);
    },
    async getProfile(username) {
        return apiFetch("GET", `/api/users/profile/${username}`);
    },
    async generateLinkCode() {
        return apiFetch("POST", "/api/users/platform/link-code");
    },
    async listUsers() {
        return apiFetch("GET", "/api/users/list");
    }
};

// ============================================================
//  TRANSACTIONS API
// ============================================================
const TxAPI = {
    async send(payload) {
        return apiFetch("POST", "/api/transactions/send", payload);
    },

    async swap(payload) {
        return apiFetch("POST", "/api/transactions/swap", payload);
    },

    async undo(txId) {
        return apiFetch("POST", `/api/transactions/undo/${txId}`);
    },

    async list(params = {}) {
        const q = new URLSearchParams(params).toString();
        return apiFetch("GET", `/api/transactions/?${q}`);
    },

    async getOne(id) {
        return apiFetch("GET", `/api/transactions/${id}`);
    },

    async getStats() {
        return apiFetch("GET", "/api/transactions/stats");
    },
};

// ============================================================
//  ANALYTICS API
// ============================================================
const AnalyticsAPI = {
    async getSummary() {
        return apiFetch("GET", "/api/analytics/summary");
    },
    async getPortfolioHistory(period = "7d") {
        return apiFetch("GET", `/api/analytics/portfolio?period=${period}`);
    },
};

// ============================================================
//  HEALTH CHECK
// ============================================================
async function checkServerHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`, { signal: AbortSignal.timeout(3000) });
        return res.ok;
    } catch {
        return false;
    }
}

// ============================================================
//  SHOW SERVER STATUS BANNER
// ============================================================
async function showServerBanner() {
    const isUp = await checkServerHealth();
    const existing = document.getElementById("server-banner");
    if (existing) existing.remove();

    if (!isUp) {
        const banner = document.createElement("div");
        banner.id = "server-banner";
        banner.style.cssText = `
      position:fixed; bottom:20px; left:50%; transform:translateX(-50%);
      background:#450a0a; border:1px solid #ef4444; border-radius:12px;
      padding:12px 20px; color:#fca5a5; font-size:0.85rem; font-weight:600;
      z-index:9999; display:flex; align-items:center; gap:10px;
      box-shadow:0 8px 32px rgba(0,0,0,0.5); white-space:nowrap;
    `;
        banner.innerHTML = `
      ⚠️ Backend offline — showing demo data.
      <span style="opacity:0.7;font-weight:400">Run: cd nltx-backend && python run.py</span>
      <button onclick="this.parentElement.remove()" style="background:none;border:none;color:#fca5a5;cursor:pointer;font-size:1rem">✕</button>
    `;
        document.body.appendChild(banner);
    } else {
        const banner = document.createElement("div");
        banner.id = "server-banner";
        banner.style.cssText = `
      position:fixed; bottom:20px; right:20px;
      background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3);
      border-radius:10px; padding:8px 14px; color:#34d399; font-size:0.78rem;
      z-index:9999; display:flex; align-items:center; gap:8px;
    `;
        banner.innerHTML = `<span style="width:7px;height:7px;border-radius:50%;background:#34d399;display:inline-block"></span>API Connected`;
        document.body.appendChild(banner);
        setTimeout(() => banner.remove(), 3000);
    }
}

// ============================================================
//  PUBLIC META (no auth)
// ============================================================
const MetaAPI = {
    async messaging() {
        const res = await fetch(`${API_BASE}/api/meta/messaging`);
        if (!res.ok) throw new Error("Could not load messaging config");
        return res.json();
    },
};

// ============================================================
//  GUARD: redirect to login if not authenticated
// ============================================================
function requireAuth() {
    if (!Auth.isLoggedIn()) {
        window.location.href = "login.html";
        return false;
    }
    return true;
}

// ============================================================
//  DEMO DATA (fallback when API is offline)
// ============================================================
const DemoData = {
    balances: [
        { network: "ethereum", token: "ETH", balance: 2.4831, usd_value: 6183.40, change_24h: 2.4 },
        { network: "ethereum", token: "USDT", balance: 1766.50, usd_value: 1766.50, change_24h: 0.0 },
        { network: "polygon", token: "MATIC", balance: 12500, usd_value: 2987.50, change_24h: 1.1 },
        { network: "solana", token: "SOL", balance: 18.92, usd_value: 1909.92, change_24h: -0.8 },
    ],
    totalUsd: 12847.32,
    transactions: [
        { id: "tx1", type: "send", status: "confirmed", amount: 50, token: "USDT", usd_value: 50, to_username: "@alice", memo: "Coffee", network: "polygon", created_at: "2026-03-05T09:02:00Z", tx_hash: "0x1a2b3c", can_undo: false },
        { id: "tx2", type: "receive", status: "confirmed", amount: 0.25, token: "ETH", usd_value: 622.3, to_username: "@priya", memo: "", network: "ethereum", created_at: "2026-03-05T05:40:00Z", tx_hash: "0x5e6f7a", can_undo: false },
        { id: "tx3", type: "swap", status: "confirmed", amount: 0.1, token: "ETH", usd_value: 248.9, to_username: null, memo: "Uniswap", network: "ethereum", created_at: "2026-03-04T13:15:00Z", tx_hash: "0x9c0d1e", can_undo: false },
        { id: "tx4", type: "send", status: "confirmed", amount: 500, token: "USDT", usd_value: 500, to_username: "@landlord", memo: "Rent", network: "ethereum", created_at: "2026-02-28T03:30:00Z", tx_hash: "0x3a4b5c", can_undo: false },
        { id: "tx5", type: "receive", status: "confirmed", amount: 2000, token: "USDT", usd_value: 2000, to_username: "Company", memo: "Salary", network: "polygon", created_at: "2026-02-25T04:30:00Z", tx_hash: "0x7e8f9a", can_undo: false },
    ],
    nlpStats: { total_commands: 127, successful: 124, accuracy_pct: 97.6, avg_response_ms: 320 },
    txStats: { total_sent_usd: 24830, total_received_usd: 31420, net_flow_usd: 6590, total_gas_usd: 183.4, transaction_count: 254 },
};

// Export everything
window.NLTX = {
    Auth, AuthAPI, NLPAPI, WalletAPI, TxAPI, UserAPI, AnalyticsAPI, MetaAPI,
    checkServerHealth, showServerBanner, requireAuth, DemoData,
};
