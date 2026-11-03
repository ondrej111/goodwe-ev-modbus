# GoodWe EV Charger — Home Assistant Integration

A local Modbus TCP integration for GoodWe AC EV chargers (HCA G2 series). No cloud, no app — direct communication over your local network.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dmacwalter&repository=goodwe-ev-modbus&category=integration)

## What's changed in this fork

This fork builds on [ondrej111/goodwe-ev-modbus](https://github.com/ondrej111/goodwe-ev-modbus) with:

- **Diagnostics** — a new binary sensor platform for per-link connectivity (inverter, EMS, etc.) plus fault/warning problem sensors, and new diagnostic sensors for fault state, power source, start mode, and charging strategy.
- **Adaptive polling** — the scan interval drops to 30s while a cable is connected/handshaking/charging and backs off to 60s when idle, instead of polling at a fixed rate regardless of charger state.
- **Options flow** — poll intervals and read delay are now tunable from the integration's Configure dialog, and apply live without reloading the integration.
- **Idle socket release** — the Modbus connection is closed between idle polls so the charger's own SEMS cloud uplink can use it, fixing chargers that showed as permanently offline in the GoodWe app. Retries back off automatically when the charger reports a fault instead of hammering it every 30 seconds.

## Requirements

- GoodWe AC EV charger reachable over Modbus TCP (default port 502)
- Charger firmware **V6 or newer** — energy consumption sensors do not work on earlier firmware
- Home Assistant 2024.1 or newer
- The charger's local IP address and Modbus Unit ID (default: **247**)

## Installation

### HACS (recommended)

Click the **Open in HACS** badge at the top of this page, or add manually:

1. Open HACS → Integrations → ⋮ menu → **Custom repositories**
2. Add `https://github.com/dmacwalter/goodwe-ev-modbus` — category: **Integration**
3. Search for **GoodWe EV Charger** and install it
4. Restart Home Assistant

### Manual

Copy the `custom_components/goodwe_ev` folder into your HA `config/custom_components/` directory and restart.

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **GoodWe EV Charger**.

| Field | Default | Description |
|---|---|---|
| IP Address | — | Local IP of the charger |
| Port | 502 | Modbus TCP port |
| Modbus Unit ID | 247 | Slave ID (check charger settings if unsure) |

## Entities

### Sensors (read-only)

| Entity | Unit | Description |
|---|---|---|
| Phase A/B/C Voltage | V | Per-phase AC voltage |
| Phase A/B/C Current | A | Per-phase charging current |
| Charging Power | kW | Total active charging power |
| Session Energy | kWh | Energy delivered in the current session |
| Total Energy | kWh | Cumulative energy delivered (all sessions) |
| Green Energy | kWh | Energy sourced from PV |
| Grid Energy | kWh | Energy sourced from the grid |
| Charger Status | — | idle, charging, fault, scheduled, … |
| Car Connection | — | disconnected / half connected / connected |
| CP State | — | Control pilot voltage level (A–E) |
| Charging Mode | — | Fast / PV only / PV + battery |
| Charger Type | — | Three-phase / Single-phase |
| Max Charging Power | kW | Currently configured power limit (readback) |
| Grid Power Limit | kW | Currently configured grid limit (readback) |

### Controls

| Entity | Type | Description |
|---|---|---|
| Charging | Switch | Start / stop a charging session |
| Plug & Charge | Switch | Enable automatic charging when cable is plugged in |
| EMS Dispatch (Reduce Power) | Switch | Reduce charger to minimum power on EMS command |
| Single/Three-Phase Switching | Switch | Toggle between single-phase and three-phase mode |
| Charging Mode | Select | Fast charging / PV only / PV + battery |
| Max Charging Power | Number | Set maximum charging power (1.4–22 kW) |
| Battery Discharge SOC Limit | Number | Minimum battery SOC before discharging to charger (0–100 %) |
| Grid Power Limit | Number | Maximum power draw from the grid (1.4–22 kW) |

## Notes

- Data is polled every **30 seconds** while a cable is connected/handshaking/charging, and every **60 seconds** when idle. Both intervals, and the read delay between Modbus block reads, are adjustable from the integration's Configure dialog.
- The integration communicates **locally only** — no GoodWe cloud account needed.
- Energy consumption sensors (Total/Session/Green/Grid Energy) require charger firmware **V6 or newer**. On earlier firmware these sensors do not report.
- Total Energy resets to 0 if the charger's internal counter is cleared (e.g. factory reset).
- The Charging switch reads its state from Charger Status (status = charging), not from the command register, so it accurately reflects whether charging is actually in progress.

## Supported Models

Tested on the **GoodWe HCA G2** series (7 kW / 11 kW / 22 kW, single- and three-phase). Other GoodWe AC chargers using the same Modbus protocol may work but are untested.

## Credits

- Original integration by [Ondrej Filip](https://github.com/ondrej111) — [ondrej111/goodwe-ev-modbus](https://github.com/ondrej111/goodwe-ev-modbus). This fork builds directly on that groundwork.
- [prezervos/goodwe-wallbox-sems-home-assistant](https://github.com/prezervos/goodwe-wallbox-sems-home-assistant) — a related integration that talks to GoodWe wallboxes over the SEMS cloud API rather than local Modbus. Worth a look if your charger isn't reachable on Modbus TCP or you'd rather not open it up on your local network.

## License

MIT
