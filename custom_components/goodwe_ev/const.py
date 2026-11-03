DOMAIN = "goodwe_ev"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"

# Option keys — tunable from the integration's Configure dialog.
CONF_SCAN_INTERVAL_IDLE = "scan_interval_idle"
CONF_SCAN_INTERVAL_ACTIVE = "scan_interval_active"
CONF_READ_DELAY = "read_delay"
CONF_RELEASE_WHEN_IDLE = "release_when_idle"
CONF_ACTIVE_BACKOFF = "active_backoff"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 247
# ── Polling ─────────────────────────────────────────────────────────────────
# The charger is polled faster whenever a session could plausibly change state
# (cable connected, handshaking, or charging) and slower when nothing is
# plugged in at all. Idle here means "no car present", not "car present but
# not drawing" — a plugged-in vehicle still polls at the fast rate so plug-in
# and handshake transitions are picked up promptly.
# These are defaults only; the effective values come from the config entry
# options and are editable under Settings -> Devices & services -> Configure.
SCAN_INTERVAL_IDLE = 60      # seconds, nothing connected
SCAN_INTERVAL_ACTIVE = 30    # seconds, cable connected / handshaking / charging
SCAN_INTERVAL = SCAN_INTERVAL_IDLE  # startup value, adjusted after first read

READ_DELAY = 0.2  # seconds to pause between Modbus block reads (paces bursts)

# Guard rails for the options form. The lower interval bound keeps a mistyped
# value from hammering a charger that only tolerates a couple of connections;
# the read-delay ceiling keeps a single poll cycle from outlasting its own
# schedule.
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600
MIN_READ_DELAY = 0.0
MAX_READ_DELAY = 5.0

# The charger serves a single Modbus connection, and that connection competes
# with its own outbound cloud uplink. Holding the socket open between polls
# therefore keeps the charger permanently offline in the SEMS app, no matter
# how infrequently it is actually read. When idle we close the socket after
# each poll so the uplink has the whole interval to establish.
RELEASE_WHEN_IDLE = True

# While idle the socket is contended by design, so a failed connect is an
# expected outcome rather than a fault. Ride out this many consecutive idle
# failures on the last known data before surfacing the entities as
# unavailable, retrying at the active cadence rather than the long idle one.
IDLE_FAILURE_GRACE = 3

# Backing off while a cable is connected. Retrying a faulted charger every 30
# seconds achieves nothing. On either a failed read or a charger-reported
# fault, wait this long before the next attempt. The connection itself is
# retained throughout: a cable is connected, so the slot stays ours.
ACTIVE_BACKOFF = 210

# Charger statuses treated as a fault for backoff purposes. 8 (start_failed) is
# included deliberately: a session that will not start is the case this exists
# for. Remove it here if you would rather only hard faults trigger a backoff.
FAULT_STATUSES = {5, 8}

# Charger statuses that count as "active" for polling-rate purposes.
ACTIVE_STATUSES = {2, 3}  # handshaking, charging
# Car connection states that count as "active" (1 = half connected, 2 = connected)
ACTIVE_CAR_STATES = {1, 2}

# ── Register addresses ──────────────────────────────────────────────────────

REG_EMS_DISPATCH        = 10000  # RW  0=normal, 1=reduce to min power

REG_FAULT_01            = 10001  # RO  bitmask — AC faults
REG_FAULT_02            = 10002  # RO  bitmask — AC faults
REG_FAULT_03            = 10003  # RO  bitmask — AC faults
REG_FAULT_04            = 10004  # RO  reserved
REG_FAULT_05            = 10005  # RO  bitmask — AC alarms
REG_FAULT_06            = 10006  # RO  bitmask — AC alarms
REG_FAULT_07            = 10007  # RO  bitmask — HW faults
REG_FAULT_08            = 10008  # RO  reserved

REG_VOLT_A              = 10009  # RO  U16 ÷10 V
REG_VOLT_B              = 10010  # RO  U16 ÷10 V
REG_VOLT_C              = 10011  # RO  U16 ÷10 V
REG_CURR_A              = 10012  # RO  U16 ÷10 A
REG_CURR_B              = 10013  # RO  U16 ÷10 A
REG_CURR_C              = 10014  # RO  U16 ÷10 A
REG_POWER               = 10015  # RO  U16 ÷10 kW
REG_SESSION_ENERGY      = 10016  # RO  U16 ÷10 kWh
REG_STATUS              = 10017  # RO  enum (see CHARGER_STATUS)
REG_COMMS_STATUS        = 10018  # RO  bitmask

REG_PLUG_CHARGE         = 10019  # RW  0=off 1=on
REG_RESERVATION         = 10020  # RW  0=none 1=once 2=permanent

REG_SINGLE_3PH          = 10023  # RW  0=off 1=on
REG_MAINTAIN_MIN_PWR    = 10024  # RW  0=off 1=on
REG_DYN_LOAD_MGMT       = 10025  # RW  0=off 1=on
REG_BREAKER_CURRENT     = 10026  # RW  U16 A  [0,2000] household breaker rating

REG_MAX_CAPACITY        = 10027  # RW  U16 ÷10 kWh
REG_MIN_CAPACITY        = 10028  # RW  U16 ÷10 kWh
REG_MAX_POWER           = 10029  # RW  U16 ÷10 kW  [14,220]
REG_BATTERY_SOC         = 10030  # RW  U16 %  [0,100]
REG_CHARGING_MODE       = 10032  # RW  0=fast 1=PV 2=PV+bat
REG_GRID_LIMIT          = 10039  # RW  U16 ÷10 kW

REG_SN                  = 10040  # RO  STR 8 regs (16 bytes ASCII)
REG_SW_VERSION          = 10048  # RO  STR 2 regs
REG_SVN_VERSION         = 10050  # RO  U16
REG_HW_VERSION          = 10056  # RO  STR 2 regs
REG_POWER_SPEC          = 10058  # RO  0=7kW 1=11kW 2=22kW
REG_CHARGER_TYPE        = 10059  # RO  0=3-phase 1=single-phase

REG_CHARGE_CONTROL      = 10060  # RW  1=stop 2=start

REG_CHARGE_DURATION     = 10063  # RO  U32 (2 regs) seconds, valid while charging
REG_ACCUM_ENERGY        = 10065  # RO  U32 (2 regs) ÷10 kWh

REG_TIME_YM             = 10067  # RO  hi=year lo=month
REG_TIME_DH             = 10068  # RO  hi=day  lo=hour
REG_TIME_MS             = 10069  # RO  hi=min  lo=sec

REG_CAR_STATUS          = 10075  # RO  0=disconnected 1=half 2=connected
REG_START_MODE          = 10076  # RO  enum
REG_CHARGE_STRATEGY     = 10077  # RO  enum
REG_STRATEGY_PARAM      = 10078  # RO  U16, meaning depends on 10077
REG_APPOINTMENT         = 10079  # RO  0=none 1=reservation valid
REG_CP_STATE            = 10084  # RO  0-4 CP voltage level

REG_GREEN_ENERGY        = 10103  # RO  U32 (2 regs) ÷10 kWh
REG_GRID_ENERGY         = 10105  # RO  U32 (2 regs) ÷10 kWh
REG_PROJECT_TYPE        = 10107  # RO  0,1=DC 2=AC
REG_POWER_SOURCE        = 10108  # RO  bitmask: bit0=grid bit1=PV bit2=bat
REG_TRANSPARENT_MODE    = 10157  # RW  0=direct IoT cloud 1=via GoodWe gateway

# ── Value maps ──────────────────────────────────────────────────────────────

CHARGER_STATUS = {
    0:  "idle_no_cable",
    1:  "idle_cable_connected",
    2:  "handshaking",
    3:  "charging",
    4:  "charge_complete",
    5:  "fault",
    6:  "scheduled",
    7:  "maintenance",
    8:  "start_failed",
    9:  "upgrading",
    10: "charging_interrupted",
}

CAR_STATUS = {
    0: "disconnected",
    1: "half_connected",
    2: "connected",
}

CP_STATE = {
    0: "no_voltage",
    1: "12v",
    2: "9v",
    3: "6v",
    4: "3v",
}

CHARGING_MODE = {
    0: "fast",
    1: "pv",
    2: "pv_battery",
}

# Register 10157. Per GoodWe's Gen2 protocol (V1.0.15), 1 routes the charger's
# traffic through a GoodWe gateway instead of its own IoT cloud link. Exposed so
# the SEMS-offline-under-Modbus behaviour can be tested; not a known fix.
TRANSPARENT_MODE = {
    0: "direct_iot",
    1: "via_gateway",
}

POWER_SPEC = {0: "7kW", 1: "11kW", 2: "22kW"}
CHARGER_TYPE = {0: "three_phase", 1: "single_phase"}

START_MODE = {
    0: "auth_card",
    1: "backend",
    2: "local_admin",
    3: "vin",
    4: "wallet_card",
    5: "plug_and_charge",
    6: "scheduled",
    7: "bluetooth_app",
}

CHARGE_STRATEGY = {
    0: "auto_full",
    1: "fill_by_time",
    2: "fixed_amount",
    3: "by_energy",
}

APPOINTMENT = {
    0: "none",
    1: "active",
}

PROJECT_TYPE = {
    0: "dc",
    1: "dc",
    2: "ac",
}

# Register 10108 is a bitmask (bit0=grid, bit1=PV, bit2=battery) and more than
# one bit can be set at once. Enumerating all eight combinations keeps the
# sensor a proper ENUM with a fixed option list rather than a free-text state.
POWER_SOURCE = {
    0: "none",
    1: "grid",
    2: "pv",
    3: "grid_pv",
    4: "battery",
    5: "grid_battery",
    6: "pv_battery",
    7: "grid_pv_battery",
}

POWER_SOURCE_BITS = {0: "grid", 1: "pv", 2: "battery"}

# ── Communication link bits (register 10018) ────────────────────────────────
# bit6-15 are reserved and ignored.
COMMS_BITS = {
    0: ("wifi_router", "Wi-Fi Router Link"),
    1: ("iot_cloud", "IoT Cloud Link"),
    2: ("inverter", "Inverter Link"),
    3: ("mid_meter", "MID Meter Link"),
    4: ("gw_meter", "GoodWe Meter Link"),
    5: ("ems", "EMS Link"),
}

# ── Fault / warning bit decoding ────────────────────────────────────────────
# Registers 10001-10003 and 10007 are hard faults; 10005-10006 are warnings.
# 10004 and 10008 are reserved by the protocol and are read but not decoded.

FAULT_BITS = {
    REG_FAULT_01: {
        0: "emergency_stop",
        1: "overvoltage",
        2: "overcurrent",
        3: "undervoltage",
        4: "connector_fault",
        5: "s2_disconnected",
        6: "environment_overtemperature",
        7: "gun_overtemperature",
    },
    REG_FAULT_02: {
        0: "door_access_fault",
        1: "grounding_fault",
        2: "handshake_timeout",
        3: "rfid_comm_fault",
        4: "display_comm_fault",
        5: "meter_ic_comm_fault",
        6: "output_relay_fault",
        7: "gun_lock_fault",
    },
    REG_FAULT_03: {
        0: "output_short_circuit",
        1: "leakage_current",
        2: "charge_paused_over_10min",
        3: "abnormal_meter_reading",
        4: "offline_on_pv_battery_start",
        5: "insufficient_pv_battery_power",
    },
    REG_FAULT_07: {
        0: "external_flash_fault",
        1: "eeprom_fault",
        2: "leak_detection_device_fault",
        3: "abnormal_input_power",
        4: "sn_not_registered",
        5: "factory_parameters_abnormal",
        6: "unauthorised_firmware",
    },
}

WARNING_BITS = {
    REG_FAULT_05: {
        0: "gun_overtemperature_alarm",
        1: "grounding_alarm",
        2: "handshake_timeout_alarm",
        3: "rfid_comm_alarm",
        4: "display_comm_alarm",
        5: "meter_ic_comm_alarm",
        6: "charging_stop_alarm",
        7: "abnormal_meter_reading_alarm",
    },
    REG_FAULT_06: {
        0: "environment_overtemperature_alarm",
    },
}

FAULT_STATE = ["ok", "warning", "fault"]


def decode_bits(value: int, bit_map: dict[int, str]) -> list[str]:
    """Return the names of every set bit in ``value`` present in ``bit_map``."""
    if not value:
        return []
    return [name for bit, name in bit_map.items() if value & (1 << bit)]
