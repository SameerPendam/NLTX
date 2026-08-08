/**
 * NLTX Auth JS — Real API integration
 * Handles: Login, Register, Password Strength, OTP
 */

// ===== TOGGLE PASSWORD VISIBILITY =====
document.getElementById("togglePass")?.addEventListener("click", () => {
    const p = document.getElementById("password");
    p.type = p.type === "password" ? "text" : "password";
});
document.getElementById("toggleRegPass")?.addEventListener("click", () => {
    const p = document.getElementById("regPassword");
    p.type = p.type === "password" ? "text" : "password";
});

// ===== PASSWORD STRENGTH =====
document.getElementById("regPassword")?.addEventListener("input", function () {
    const val = this.value;
    const fill = document.getElementById("strengthFill");
    const text = document.getElementById("strengthText");
    if (!fill) return;
    let score = 0;
    if (val.length >= 8) score++;
    if (/[A-Z]/.test(val)) score++;
    if (/[0-9]/.test(val)) score++;
    if (/[^A-Za-z0-9]/.test(val)) score++;
    const pcts = ["0%", "25%", "50%", "75%", "100%"];
    const colors = ["", "#ef4444", "#f59e0b", "#3b82f6", "#10b981"];
    const labels = ["", "Weak", "Fair", "Good", "Strong"];
    fill.style.width = val.length ? pcts[score] : "0%";
    fill.style.background = colors[score] || "#ef4444";
    if (text) { text.textContent = val.length ? labels[score] : ""; text.style.color = colors[score]; }
});

// ===== HELPERS =====
function setLoading(btnTextEl, spinnerEl, isLoading, defaultText = "Submit") {
    if (btnTextEl) btnTextEl.textContent = isLoading ? "Please wait..." : defaultText;
    if (spinnerEl) spinnerEl.classList.toggle("hidden", !isLoading);
}
function showError(id, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 5000);
}
function showSuccess(id, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = msg;
    el.style.color = "var(--accent-green)";
    el.classList.remove("hidden");
}

// ===== LOGIN FORM =====
document.getElementById("loginForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const btnText = document.getElementById("loginBtnText");
    const spinner = document.getElementById("loginSpinner");
    const errEl = document.getElementById("loginError");

    if (!email || !password) { showError("loginError", "Please fill in all fields."); return; }

    setLoading(btnText, spinner, true, "Sign In");

    try {
        // Try real API first
        const data = await NLTX.AuthAPI.login(email, password);
        NLTX.Auth.setToken(data.access_token);
        NLTX.Auth.setUser({ id: data.user_id, username: data.username, email: data.email });

        setLoading(btnText, spinner, false, "Sign In");

        // Check if 2FA panel exists
        const twoFaPanel = document.getElementById("twoFaPanel");
        if (twoFaPanel) {
            document.getElementById("loginForm").classList.add("hidden");
            twoFaPanel.classList.remove("hidden");
            setupOTP();
        } else {
            window.location.href = "dashboard.html";
        }

    } catch (err) {
        setLoading(btnText, spinner, false, "Sign In");

        // Demo fallback — allow login with any credentials  
        if (err.message.includes("Cannot connect") || err.message.includes("NetworkError")) {
            showError("loginError", "⚠️ Backend offline — using demo mode.");
            NLTX.Auth.setToken("demo_token");
            NLTX.Auth.setUser({ id: "demo", username: "rahul", email });
            setTimeout(() => { window.location.href = "dashboard.html"; }, 1200);
        } else {
            showError("loginError", err.message || "Invalid credentials.");
        }
    }
});

// ===== OTP =====
function setupOTP() {
    const inputs = document.querySelectorAll(".otp-input");
    inputs.forEach((inp, i) => {
        inp.addEventListener("input", () => { if (inp.value && i < inputs.length - 1) inputs[i + 1].focus(); });
        inp.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !inp.value && i > 0) inputs[i - 1].focus(); });
    });
}
document.getElementById("verifyOtp")?.addEventListener("click", () => {
    window.location.href = "dashboard.html";
});

// ===== REGISTER FORM =====
document.getElementById("registerForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btnText = document.getElementById("registerBtnText");
    const spinner = document.getElementById("regSpinner");

    const payload = {
        first_name: document.getElementById("firstName")?.value.trim(),
        last_name: document.getElementById("lastName")?.value.trim(),
        email: document.getElementById("regEmail")?.value.trim(),
        username: document.getElementById("username")?.value.trim().replace("@", ""),
        password: document.getElementById("regPassword")?.value,
        account_type: document.getElementById("accountType")?.value || "personal",
    };

    if (!payload.email || !payload.password || !payload.username || !payload.first_name) {
        showError("regError", "Please fill in all required fields.");
        return;
    }
    if (payload.password.length < 6) {
        showError("regError", "Password must be at least 6 characters.");
        return;
    }

    setLoading(btnText, spinner, true, "Create Account");

    try {
        const data = await NLTX.AuthAPI.register(payload);
        NLTX.Auth.setToken(data.access_token);
        NLTX.Auth.setUser({ id: data.id, username: data.username, email: data.email });
        setLoading(btnText, spinner, false);
        window.location.href = "dashboard.html";

    } catch (err) {
        setLoading(btnText, spinner, false, "Create Account");

        if (err.message.includes("Cannot connect")) {
            // Demo mode
            NLTX.Auth.setToken("demo_token");
            NLTX.Auth.setUser({ id: "demo", username: payload.username, email: payload.email });
            setTimeout(() => { window.location.href = "dashboard.html"; }, 1000);
        } else {
            showError("regError", err.message || "Registration failed.");
        }
    }
});

// ===== OAUTH BUTTONS (Google / Telegram) =====
document.getElementById("googleLogin")?.addEventListener("click", () => {
    // In production: redirect to Google OAuth flow
    NLTX.Auth.setToken("demo_token");
    NLTX.Auth.setUser({ id: "demo", username: "demo_user", email: "demo@gmail.com" });
    window.location.href = "dashboard.html";
});
document.getElementById("telegramLogin")?.addEventListener("click", () => {
    NLTX.Auth.setToken("demo_token");
    NLTX.Auth.setUser({ id: "demo", username: "demo_user", email: "demo@telegram.org" });
    window.location.href = "dashboard.html";
});
