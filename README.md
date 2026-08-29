# Trade Republic (for Home Assistant)

[![GitHub Release](https://img.shields.io/github/release/FaserF/ha-traderepublic.svg?style=flat-square)](https://github.com/FaserF/ha-traderepublic/releases)
[![Downloads (Current release)](https://img.shields.io/github/downloads/FaserF/ha-traderepublic/latest/traderepublic.zip?label=Downloads%20(Current%20release)&style=flat-square)](https://github.com/FaserF/ha-traderepublic/releases)
[![License](https://img.shields.io/github/license/FaserF/ha-traderepublic.svg?style=flat-square)](LICENSE)
[![hacs](https://img.shields.io/badge/HACS-custom-orange.svg?style=flat-square)](https://hacs.xyz)
[![Add to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=traderepublic)
[![CI Orchestrator](https://github.com/FaserF/ha-traderepublic/actions/workflows/ci-orchestrator.yml/badge.svg)](https://github.com/FaserF/ha-traderepublic/actions/workflows/ci-orchestrator.yml)

A **Home Assistant custom integration** for **Trade Republic**. It securely fetches your portfolio values, cash balance, profits/losses, and savings plan details.

> [!IMPORTANT]
> **Strictly Read-Only:** This integration does not have any execution, order placing, or funds transfer capabilities. Your credentials and sessions are handled strictly to retrieve portfolio metrics.

---

## 🧭 Quick Links

- [✨ Features](#-features)
- [📦 Installation](#-installation)
- [⚙️ Configuration](#️-configuration)
- [📡 Entities](#-entities)
- [🛡️ Anti-Ban / Rate-Limit Protection](#️-anti-ban--rate-limit-protection)

---

## ✨ Features

- 📊 **Portfolio Value** — Total value of your assets + cash.
- 🏦 **Cash Balance** — Available cash balance in your settlement account.
- 📈 **Return & Performance** — Total return/profit absolute (EUR) and percentage (%).
- 🏷️ **Exemption allowance** — Exemption order limit and current usage.
- 💼 **Active Savings Plans** — Active savings plans count.
- 🛡️ **Anti-ban protection** — Built-in random jitter (5–30s) before calls, domain-wide serialisation, and exponential backoff on HTTP 403/429 limits.

---

## 📦 Installation

### Via HACS (Recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `FaserF/ha-traderepublic` with category **Integration**
3. Search for **Trade Republic** and install
4. Restart Home Assistant

---

## ⚙️ Configuration

Adding the integration is done entirely via the UI.

1. Navigate to **Settings → Devices & Services** in Home Assistant.
2. Click **Add Integration** and search for **Trade Republic**.
3. **Step 1 — Select Connection Method:**
   - 🌟 **Trade Republic Home Assistant App (Recommended):** Automatically connects to your App instance. No manual token or phone/PIN needed if already logged in on the App.
   - 🔑 **Manual Credentials / Token (Classic Mode):** For standalone setups or additional secondary accounts.
4. **Step 2 — Authentication (if not using App or configuring secondary account):**
   - **Phone Number:** International E.164 format (e.g. `+491701234567`, `+33612345678`, `0170...`)
   - **PIN:** 4–6 digits (numeric only)
   - **Session Token (Optional):** Manual session token copied from browser

### Connection Methods

1. 🌟 **Trade Republic Home Assistant App (Recommended)**:
   - Uses the [Trade Republic App](https://github.com/FaserF/hassio-addons/tree/master/traderepublic) running on Home Assistant.
   - Solves AWS WAF Bot Challenges automatically in a headless browser.
   - **Zero-Touch In-HA Setup:** You can perform the full login (Credentials + In-App 2FA Confirmation / SMS) directly inside Home Assistant's configuration flow.
   - **Multi-Account & Discovery:** Discovered automatically by Home Assistant. If an account is already logged in on the App, it connects with a single click.
   - **Repairs & Self-Healing:** Creates Home Assistant Repair Issues if a session ever expires, allowing 1-click re-syncing or re-login directly within HA.
   - Keeps your session alive 24/7 without needing manual token copying.

2. 🔑 **Manual Session Token / Additional Account**:
   - Manually copy the `tr_session` cookie from your browser (instructions below) or log in with credentials and SMS/2FA.


---

## 💡 Why do I need the Trade Republic App?

Trade Republic protects its login and servers with an advanced security shield (**AWS Bot Control / Cloudflare Challenge**).

Think of this security shield like a digital gatekeeper: when you open Trade Republic on your computer or phone, your browser automatically solves invisible background checks to prove that you are a real human and not an automated robot.

- **Without the App (Manual Mode):** Normal Home Assistant integrations do not have a web browser. If Home Assistant tries to contact Trade Republic directly, the security shield blocks it (`HTTP 403 Forbidden` / `NUMBER_INVALID`). You would have to manually inspect your computer's browser, copy a hidden session token, and paste it into Home Assistant every few hours or days whenever it expires.
- **With the App (Automated & Recommended):** The [Trade Republic Home Assistant App](https://github.com/FaserF/hassio-addons/tree/master/traderepublic) provides a lightweight, dedicated browser that runs automatically in the background. It solves the invisible security challenges for you, logs in safely, confirms your phone approval, and keeps your login session active **24/7 without manual maintenance**.

### ⚖️ Comparison: App vs. Manual Mode

| Feature | 🌟 With Trade Republic App (Recommended) | 🔑 Without App (Manual Mode) |
|---|---|---|
| **Setup Effort** | 🟢 **1-Click / Guided:** Log in once via HA UI | 🔴 **Complex:** Must extract tokens via browser Developer Tools (F12) |
| **Session Lifetime** | 🟢 **Permanent (24/7 Auto-Renew)** | 🟠 **Temporary:** Expires after hours/days of inactivity |
| **Bot Challenge / WAF** | 🟢 **Solved automatically** in background browser | 🔴 **Not supported:** Can trigger account lockouts / blocks |
| **Re-Authentication** | 🟢 **Self-Healing:** 1-Click repair prompt in HA | 🔴 **Manual:** Must re-copy tokens from browser every time |
| **Smartphone In-App Approval** | 🟢 **Supported:** One-tap confirmation on phone | 🟠 **Limited:** Requires SMS code or pre-existing browser token |
| **Multi-Account Support** | 🟢 **Yes** | 🟢 **Yes** |

> [!NOTE]
> **ℹ️ Understanding Add-on Restarts & Session Expiration:**
> Trade Republic actively ties your session to the running live connection.
> - **During 24/7 normal operation:** The Add-on keeps your session continuously renewed and active.
> - **When the Add-on is restarted or updated:** Trade Republic's security servers terminate the session when the connection closes. When this happens, simply tap **"Reconfigure"** in Home Assistant or open the Add-on UI to confirm a fresh 1-tap approval in your Trade Republic mobile app.

---

### 🌐 Network Architecture: Ingress vs. Host Port Exposure

#### Why you normally **do NOT need to open or scan a host port**:
- **Home Assistant Ingress:** The Trade Republic App Web UI is accessed securely via Home Assistant Ingress. Ingress routes traffic directly through Home Assistant's authenticated web interface without exposing any port to your local network.
- **Internal Container Communication:** The integration communicates directly with the add-on through the internal Home Assistant Docker network (e.g. `http://a0d7b954-traderepublic:8095` or `http://127.0.0.1:8095`). Port 8095 is open **internally** between containers, which is why external port scanners on your Home Assistant host IP address will **not** (and do not need to) see port 8095.

#### When would a host port be needed?
- Only if you are running Home Assistant Core in a standalone container or on another server and running the Trade Republic Add-on on a completely separate machine across the physical network.

#### ⚠️ Security Recommendation:
- Exposing port 8095 on your host network is **not recommended**. Leaving financial session endpoints unauthenticated on the local network creates unnecessary security risks. Keep host port mapping disabled and let Home Assistant Ingress and the internal container network handle communication securely.

---

### 🔑 Manual Mode: How to copy your `sessionToken` (If not using the App)
1. Open your desktop web browser (e.g., Chrome, Firefox, Edge) and log in to [app.traderepublic.com](https://app.traderepublic.com).
2. Once logged in, press **F12** (or right-click anywhere and select **Inspect**) to open Developer Tools.
3. Navigate to the **Application** tab (Chrome/Edge) or **Storage** tab (Firefox).
4. In the left sidebar under **Storage**, expand **Cookies** and select `https://app.traderepublic.com`.
5. Find the cookie named **`tr_session`**. Its value is a long string starting with `eyJhbGci...`.
6. Copy the **entire** value of `tr_session` and paste it into the **Session Token** field in Home Assistant.

> [!WARNING]
> **Manual Session Lifetime Limitation:**
> Tokens copied manually will eventually expire when invalidated by Trade Republic. For a permanent, set-and-forget setup, install the [Trade Republic Home Assistant App](https://github.com/FaserF/hassio-addons/tree/master/traderepublic).





---

## 📡 Entities

The following sensors are created under the **Trade Republic** device:

| Sensor | Unit | Description | Default Status |
|---|---|---|---|
| `sensor.portfolio_value` | EUR | Total portfolio value (including cash) | **Enabled** |
| `sensor.cash_balance` | EUR | Available cash balance (Tagesgeld) | **Enabled** |
| `sensor.invested_capital` | EUR | Invested capital in securities | *Disabled* (available as attribute) |
| `sensor.total_return` | EUR | Profit or loss amount | *Disabled* (available as attribute) |
| `sensor.total_return_percent` | % | Return in percent | *Disabled* (available as attribute) |
| `sensor.exemption_limit` | EUR | Exemption order limit | *Disabled* (available as attribute) |
| `sensor.exemption_used` | EUR | Used exemption allowance | *Disabled* (available as attribute) |
| `sensor.active_savings_plans` | plans | Number of active savings plans | *Disabled* (available as attribute) |

> [!NOTE]
> To keep your Home Assistant clean, only the **Total Portfolio Value** and **Cash Balance** are enabled as entities by default. The values of the other metrics (along with your detailed asset holdings) are exposed directly as state attributes under the `sensor.portfolio_value` entity. You can always enable the individual sensors manually in the Home Assistant entity settings if needed.

---

## 🛡️ Anti-Ban / Rate-Limit Protection

To protect your account from WAF blocks or temporary bans, this integration implements several safeguards:
1. **Random Jitter:** A random sleep of 5–30 seconds is added before each request.
2. **Domain-wide Lock:** Serialises concurrent updates from multiple instances.
3. **Restart-Resistance:** Cached data is saved in HA storage. Upon restart, the integration serves cached data first instead of hammering the API.
4. **Exponential Backoff:** If the API returns a rate limit (HTTP 429/403), the integration backs off up to 24 hours.
