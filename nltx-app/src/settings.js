/* ===== NLTX Settings JS (API Connected) ===== */

document.addEventListener("DOMContentLoaded", async () => {
    // 1. Auth check
    if (!NLTX.requireAuth()) return;
    await NLTX.showServerBanner();

    // 2. Load User Profile
    await loadUserProfile();

    // 3. Setup Listeners
    setupListeners();
});

async function loadUserProfile() {
    try {
        const user = await NLTX.UserAPI.getMe();

        // Update Sidebar (redundant but good to sync)
        document.querySelectorAll('.user-name').forEach(el => el.textContent = user.first_name || user.username);
        document.querySelectorAll('.user-email').forEach(el => el.textContent = user.email);

        // Update Form Fields
        const profilePanel = document.getElementById('panel-profile');
        if (profilePanel) {
            const inputs = profilePanel.querySelectorAll('input');
            const firstName = inputs[0], lastName = inputs[1], username = inputs[2], email = inputs[3];

            if (firstName) firstName.value = user.first_name || "";
            if (lastName) lastName.value = user.last_name || "";
            if (username) username.value = user.username ? `@${user.username}` : "";
            if (email) email.value = user.email || "";
        }

        // Update Toggles from settings
        if (user.settings) {
            updateToggle('toggle2fa', user.settings.two_factor);
            // More toggles can be synced here
        }

    } catch (err) {
        console.warn("Failed to load profile", err);
    }
}

function updateToggle(id, isOn) {
    const el = document.getElementById(id);
    if (!el) return;
    if (isOn) el.classList.add('on');
    else el.classList.remove('on');
}

function setupListeners() {
    // Sidebar toggle
    document.getElementById('sidebarToggle')?.addEventListener('click', () => {
        document.getElementById('sidebar')?.classList.toggle('open');
    });

    // Nav switch
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.addEventListener('click', function () {
            document.querySelectorAll('.settings-nav-item').forEach(n => n.classList.remove('active'));
            document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
            this.classList.add('active');
            const panelId = 'panel-' + this.dataset.panel;
            document.getElementById(panelId)?.classList.add('active');
        });
    });

    // Toggles
    document.querySelectorAll('.toggle').forEach(t => {
        if (t.id !== 'toggleMPC') {
            t.addEventListener('click', function () {
                this.classList.toggle('on');
            });
        }
    });

    // Save Button
    document.getElementById('saveSettings')?.addEventListener('click', async function () {
        const btn = this;
        btn.disabled = true;
        btn.textContent = 'Saving...';

        try {
            const profilePanel = document.getElementById('panel-profile');
            const inputs = profilePanel.querySelectorAll('input');
            const firstName = inputs[0].value, lastName = inputs[1].value, email = inputs[3].value;

            // Prepare settings payload
            const settings = {
                two_factor: document.getElementById('toggle2fa')?.classList.contains('on'),
                undo_window: 30, // example
                daily_limit: 5000 // example
            };

            await NLTX.UserAPI.updateMe({
                first_name: firstName,
                last_name: lastName,
                email: email,
                settings: settings
            });

            btn.textContent = '✅ Saved!';
            btn.style.background = 'var(--accent-green)';

            // Reload user data in memory
            await NLTX.Auth.getMe();

            setTimeout(() => {
                btn.textContent = 'Save Changes';
                btn.style.background = '';
                btn.disabled = false;
            }, 2000);

        } catch (err) {
            btn.textContent = '❌ Error';
            btn.style.background = 'var(--accent-red)';
            alert("Update failed: " + err.message);
            setTimeout(() => {
                btn.textContent = 'Save Changes';
                btn.style.background = '';
                btn.disabled = false;
            }, 2000);
        }
    });

    // Platforms Logic
    const connectModal = document.getElementById('connectModal');
    const closeConnectModal = document.getElementById('closeConnectModal');

    closeConnectModal?.addEventListener('click', () => connectModal.classList.add('hidden'));

    document.querySelectorAll('.platform-item button').forEach(btn => {
        if (btn.textContent === 'Connect') {
            btn.addEventListener('click', async function () {
                const platformItem = this.closest('.platform-item');
                const platformName = platformItem.querySelector('h4').textContent;

                document.getElementById('connectTitle').textContent = `Connect ${platformName}`;
                // Set icon
                const icon = platformName === 'Telegram' ? '🔹' : platformName === 'Discord' ? '🟣' : '🟢';
                document.getElementById('platformIcon').textContent = icon;

                try {
                    const res = await NLTX.UserAPI.generateLinkCode();
                    document.getElementById('linkCodeDisplay').textContent = res.code;

                    const botLink = document.getElementById('botLink');
                    botLink.textContent = 'Open instructions';
                    if (platformName === 'Telegram') {
                        let meta = null;
                        try {
                            meta = await NLTX.MetaAPI.messaging();
                        } catch (_) { /* offline */ }
                        const u = meta?.telegram?.bot_username;
                        botLink.href = u
                            ? `https://t.me/${u}?start=${encodeURIComponent(res.code)}`
                            : `https://t.me`;
                        botLink.textContent = u ? 'Open in Telegram' : 'Get Telegram';
                    } else if (platformName === 'Discord') {
                        botLink.href = 'https://discord.com/developers/applications';
                        botLink.textContent = 'Discord dev portal (optional)';
                    } else {
                        botLink.href = 'https://developers.facebook.com/docs/whatsapp';
                        botLink.textContent = 'WhatsApp Business API (optional)';
                    }

                    connectModal.classList.remove('hidden');
                } catch (err) {
                    alert("Failed to generate link code: " + err.message);
                }
            });
        }
    });
}
