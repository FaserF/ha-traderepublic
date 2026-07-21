# Trade Republic (for Home Assistant)

[![GitHub Release](https://img.shields.io/github/release/FaserF/ha-traderepublic.svg?style=flat-square)](https://github.com/FaserF/ha-traderepublic/releases)
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
3. Follow the guided setup:
   - **Phone Number** (e.g., `+491701234567`)
   - **Session Token (sessionToken)** (Highly recommended)
   - **PIN** (Only needed if not using a Session Token)

### 💡 Why is the `sessionToken` required?
Other standalone Python libraries (like `pytr` or `tr-api` CLI clients) can automate the login process because they run on machines where they can spawn **Playwright** (a headless browser engine). Playwright automatically downloads a full web browser (Chromium) and executes the complex JavaScript code required to solve Trade Republic's **AWS WAF (Web Application Firewall) Bot Control** challenge.

Inside **Home Assistant**, running Playwright/Chromium is not feasible:
- Home Assistant Core runs in a restricted, containerized environment (often Docker on Home Assistant OS).
- Containerized environments lack the native graphical libraries and binary dependencies needed to run a headless browser.
- Automating browser solvers inside Home Assistant would make the integration highly unstable and prone to breaking on every Home Assistant OS update.

Therefore, manually importing your active browser `sessionToken` is the only stable, reliable, and secure method to connect.

### 🔑 How to retrieve your `sessionToken`
1. Open your desktop web browser (e.g., Chrome, Firefox, Edge) and log in to [app.traderepublic.com](https://app.traderepublic.com).
2. Once logged in, press **F12** (or right-click anywhere and select **Inspect**) to open the Developer Tools.
3. Navigate to the **Application** tab (Chrome/Edge) or **Storage** tab (Firefox).
4. In the left sidebar under the **Storage** section, expand **Local Storage** and select `https://app.traderepublic.com`.
5. Find the key named **`session`** and look at its value. It is a JSON object containing a property called `sessionToken` (e.g., `{"sessionToken":"3471b571-7730-4f85-bbaf-ca6d71322eec", ...}`).
6. Copy ONLY the UUID value of the `sessionToken` (e.g., `3471b571-7730-4f85-bbaf-ca6d71322eec`).
7. Paste this UUID into the **Session Token (sessionToken)** field during the Home Assistant integration setup. You can leave the **PIN** field blank.

> [!WARNING]
> **Session Expiry Limitation:** A `sessionToken` eventually expires. When the session expires or is terminated (e.g. by logging out on your web browser), Home Assistant will show a "Reauthentication required" notification, and you will need to copy and paste a new `sessionToken` UUID from a fresh browser session.

---

## 📡 Entities

The following sensors are created under the **Trade Republic** device:

| Sensor | Unit | Description |
|---|---|---|
| `sensor.portfolio_value` | EUR | Total portfolio value |
| `sensor.cash_balance` | EUR | Available cash balance |
| `sensor.invested_capital` | EUR | Invested capital |
| `sensor.total_return` | EUR | Profit or loss amount |
| `sensor.total_return_percent` | % | Return in percent |
| `sensor.exemption_limit` | EUR | Exemption order limit |
| `sensor.exemption_used` | EUR | Used exemption allowance |
| `sensor.active_savings_plans` | plans | Number of active savings plans |

---

## 🛡️ Anti-Ban / Rate-Limit Protection

To protect your account from WAF blocks or temporary bans, this integration implements several safeguards:
1. **Random Jitter:** A random sleep of 5–30 seconds is added before each request.
2. **Domain-wide Lock:** Serialises concurrent updates from multiple instances.
3. **Restart-Resistance:** Cached data is saved in HA storage. Upon restart, the integration serves cached data first instead of hammering the API.
4. **Exponential Backoff:** If the API returns a rate limit (HTTP 429/403), the integration backs off up to 24 hours.
