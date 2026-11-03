from __future__ import annotations

import logging
import time
from datetime import timedelta

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    READ_DELAY,
    RELEASE_WHEN_IDLE,
    IDLE_FAILURE_GRACE,
    ACTIVE_BACKOFF,
    FAULT_STATUSES,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_ACTIVE,
    ACTIVE_STATUSES,
    ACTIVE_CAR_STATES,
    REG_SN,
    REG_SW_VERSION,
    REG_HW_VERSION,
    REG_POWER_SPEC,
    REG_CHARGER_TYPE,
    POWER_SPEC,
    CHARGER_TYPE,
    FAULT_BITS,
    WARNING_BITS,
    COMMS_BITS,
    POWER_SOURCE_BITS,
    decode_bits,
)

_LOGGER = logging.getLogger(__name__)

# Contiguous read ranges: (start, count, required)
# required=False blocks are skipped silently when the device doesn't respond.
_READ_RANGES = [
    (10000, 90, True),   # main block: faults, voltages, currents, config
    (10103, 6, False),   # green energy, grid energy, project type, power source
    (10157, 1, False),   # transparent mode (direct IoT vs via gateway)
]


def _u32(raw: dict, hi: int) -> int:
    return (raw.get(hi, 0) << 16) | raw.get(hi + 1, 0)


def _str_regs(raw: dict, start: int, count: int) -> str:
    chars = []
    for i in range(count):
        word = raw.get(start + i, 0)
        hi, lo = (word >> 8) & 0xFF, word & 0xFF
        if hi:
            chars.append(chr(hi))
        if lo:
            chars.append(chr(lo))
    return "".join(chars).strip("\x00")


class GoodweEVCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        unit_id: int,
        scan_interval_idle: int = SCAN_INTERVAL_IDLE,
        scan_interval_active: int = SCAN_INTERVAL_ACTIVE,
        read_delay: float = READ_DELAY,
        release_when_idle: bool = RELEASE_WHEN_IDLE,
        active_backoff: int = ACTIVE_BACKOFF,
    ) -> None:
        # Start on the idle cadence; the first successful read moves it to the
        # active one if a cable is already connected.
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_idle),
        )
        self._client = ModbusTcpClient(host, port=port, timeout=10)
        self._unit_id = unit_id
        self.device_info_static: dict = {}
        self._interval_idle = scan_interval_idle
        self._interval_active = scan_interval_active
        self._read_delay = read_delay
        self._release_when_idle = release_when_idle
        self._interval_backoff = active_backoff
        self._interval_seconds = scan_interval_idle
        self._in_backoff = False
        # Assume idle until the first read proves otherwise, so the socket is
        # released rather than squatted on if that first read never succeeds.
        self._active = False
        self._idle_failures = 0

    # ── Options ────────────────────────────────────────────────────────────

    @callback
    def async_apply_options(
        self,
        scan_interval_idle: int,
        scan_interval_active: int,
        read_delay: float,
        release_when_idle: bool,
        active_backoff: int,
    ) -> None:
        """Adopt new polling options without tearing down the integration.

        All three values are read fresh on each cycle rather than baked into
        anything at construction, so they can be swapped on a live coordinator.
        The read delay is consumed inside the executor thread; a poll already in
        flight simply finishes on the old value.
        """
        self._interval_idle = scan_interval_idle
        self._interval_active = scan_interval_active
        self._read_delay = read_delay
        self._release_when_idle = release_when_idle
        self._interval_backoff = active_backoff

        # Clearing the cached interval forces _apply_dynamic_interval to
        # reschedule even when the active/idle classification has not changed —
        # otherwise a new idle interval would not take effect until the next
        # plug-in event.
        self._interval_seconds = None
        if self.data:
            self._apply_dynamic_interval(self.data)
        else:
            self._interval_seconds = scan_interval_idle
            self.update_interval = timedelta(seconds=scan_interval_idle)

    # ── Public write helper ────────────────────────────────────────────────

    async def async_write_register(self, address: int, value: int) -> None:
        await self.hass.async_add_executor_job(self._write_register, address, value)
        await self.async_request_refresh()

    def _write_register(self, address: int, value: int) -> None:
        self._ensure_connected()
        resp = self._client.write_registers(address, [value], device_id=self._unit_id)
        if resp.isError():
            raise RuntimeError(f"Write failed at register {address}: {resp}")

    # ── DataUpdateCoordinator ──────────────────────────────────────────────

    async def _async_update_data(self) -> dict:
        try:
            data = await self.hass.async_add_executor_job(self._read_data)
        except UpdateFailed:
            if self._tolerate_idle_failure():
                return self.data
            if self._active:
                # Entities still go unavailable — this is a real failure and
                # should look like one — but the retry waits out the backoff
                # instead of hammering the charger every 30 seconds.
                self._enter_backoff("read failed")
            raise

        self._idle_failures = 0
        # Must happen on the event loop, never inside _read_data: assigning
        # update_interval reschedules the refresh timer, which is not
        # thread-safe from an executor thread.
        self._apply_dynamic_interval(data)

        faulted = self._charger_faulted(data)
        if self._active and faulted:
            self._enter_backoff(f"charger fault: {data.get('status')}")
        else:
            self._in_backoff = False

        # Note the backoff is deliberately excluded here: while a cable is
        # connected the charger's Modbus slot stays ours, faulted or not.
        if self._release_when_idle and not self._active:
            # Hand the charger's single Modbus slot back so its cloud uplink
            # can claim it for the rest of the interval. Closing is cheap and
            # _ensure_connected reopens on the next poll or write.
            await self.hass.async_add_executor_job(self._client.close)

        return data

    @staticmethod
    def _charger_faulted(data: dict) -> bool:
        return data.get("fault_state") == "fault" or data.get("status") in FAULT_STATUSES

    def _enter_backoff(self, reason: str) -> None:
        """Slow to the backoff cadence until the charger reads clean again.

        Only the polling rate changes — the connection is held throughout, so
        nothing else can claim the charger's Modbus slot mid-session.

        Deliberately not capped or escalated: each retry either clears the
        condition, in which case _apply_dynamic_interval restores the active
        interval on the very next poll, or re-enters the backoff.
        """
        first = not self._in_backoff
        self._in_backoff = True
        if self._interval_seconds != self._interval_backoff:
            self._interval_seconds = self._interval_backoff
            self.update_interval = timedelta(seconds=self._interval_backoff)
        if first:
            _LOGGER.info(
                "Backing off to %ss while a cable is connected (%s)",
                self._interval_backoff,
                reason,
            )

    def _tolerate_idle_failure(self) -> bool:
        """Absorb a contended idle poll instead of going unavailable.

        Only applies once the socket is being released: in that mode the cloud
        uplink legitimately holds the connection some of the time, so a failed
        read says nothing about the charger's health. Retry sooner than the
        idle interval, and give up after IDLE_FAILURE_GRACE attempts so a
        genuine outage still surfaces.
        """
        if not self._release_when_idle or self._active or self.data is None:
            return False
        if self._idle_failures >= IDLE_FAILURE_GRACE:
            return False

        self._idle_failures += 1
        _LOGGER.debug(
            "Idle poll failed (%s/%s), likely cloud uplink holding the socket; "
            "retrying in %ss",
            self._idle_failures,
            IDLE_FAILURE_GRACE,
            self._interval_active,
        )
        if self._interval_seconds != self._interval_active:
            self._interval_seconds = self._interval_active
            self.update_interval = timedelta(seconds=self._interval_active)
        return True

    def _apply_dynamic_interval(self, data: dict) -> None:
        """Poll faster while a cable is connected or a session is running."""
        active = (
            data.get("status") in ACTIVE_STATUSES
            or data.get("car_status") in ACTIVE_CAR_STATES
        )
        self._active = active
        wanted = self._interval_active if active else self._interval_idle
        if wanted == self._interval_seconds:
            return
        self._interval_seconds = wanted
        self.update_interval = timedelta(seconds=wanted)
        _LOGGER.debug("Poll interval now %ss (active=%s)", wanted, active)

    def _read_data(self) -> dict:
        self._ensure_connected()

        raw: dict[int, int] = {}
        try:
            for idx, (start, count, required) in enumerate(_READ_RANGES):
                # Pace consecutive reads: some chargers are overwhelmed by
                # back-to-back Modbus requests. Runs in an executor thread, so
                # a blocking sleep is safe here and never touches the event loop.
                if idx and self._read_delay:
                    time.sleep(self._read_delay)
                resp = self._client.read_holding_registers(
                    start, count=count, device_id=self._unit_id
                )
                if resp.isError():
                    if required:
                        raise UpdateFailed(f"Modbus error reading block {start}+{count}")
                    _LOGGER.debug("Optional block %s+%s unavailable, skipping", start, count)
                    continue
                for i, val in enumerate(resp.registers):
                    raw[start + i] = val
        except ModbusException as exc:
            self._client.close()
            raise UpdateFailed(f"Modbus exception: {exc}") from exc

        # Build static device info once we have a valid power-spec reading.
        # Register 10058 can read 0 ("7kW") transiently right after the charger
        # boots, before firmware initialises it. Since 0 is itself a *valid* spec,
        # a plain ``.get(..., 0)`` would silently cache "7kW" for the whole
        # session and persist it into HA's device registry. So we map a missing
        # register to None → "unknown" and only freeze device_info_static once the
        # spec resolves to a real value, letting a later refresh correct a
        # boot-time misread.
        if not self.device_info_static:
            power_spec = POWER_SPEC.get(raw.get(REG_POWER_SPEC), "unknown")
            if power_spec == "unknown":
                _LOGGER.debug(
                    "Power spec register %s not yet available (raw=%s); "
                    "retrying on next refresh",
                    REG_POWER_SPEC, raw.get(REG_POWER_SPEC),
                )
            else:
                self.device_info_static = {
                    "serial": _str_regs(raw, REG_SN, 8),
                    "sw_version": _str_regs(raw, REG_SW_VERSION, 2),
                    "hw_version": _str_regs(raw, REG_HW_VERSION, 2),
                    "power_spec": power_spec,
                    "charger_type": CHARGER_TYPE.get(
                        raw.get(REG_CHARGER_TYPE), "unknown"
                    ),
                }

        # Decode fault/warning bitmasks and communication link bits once here so
        # every entity that needs them reads a plain list rather than
        # re-deriving the same bit arithmetic.
        faults: list[str] = []
        for reg, bits in FAULT_BITS.items():
            faults.extend(decode_bits(raw.get(reg, 0), bits))
        warnings: list[str] = []
        for reg, bits in WARNING_BITS.items():
            warnings.extend(decode_bits(raw.get(reg, 0), bits))
        if faults:
            state = "fault"
        elif warnings:
            state = "warning"
        else:
            state = "ok"

        comms_raw = raw.get(10018, 0)
        comms_links = {
            key: bool(comms_raw & (1 << bit)) for bit, (key, _) in COMMS_BITS.items()
        }

        return {
            # ── Electrical measurements ────────────────────────────────────
            "phase_a_voltage":    raw.get(10009, 0) / 10.0,
            "phase_b_voltage":    raw.get(10010, 0) / 10.0,
            "phase_c_voltage":    raw.get(10011, 0) / 10.0,
            "phase_a_current":    raw.get(10012, 0) / 10.0,
            "phase_b_current":    raw.get(10013, 0) / 10.0,
            "phase_c_current":    raw.get(10014, 0) / 10.0,
            "charging_power":     raw.get(10015, 0) / 10.0,
            "session_energy":     raw.get(10016, 0) / 10.0,
            "accumulated_energy": _u32(raw, 10065) / 10.0,
            "green_energy":       _u32(raw, 10103) / 10.0,
            "grid_energy":        _u32(raw, 10105) / 10.0,
            # ── Status ────────────────────────────────────────────────────
            "status":             raw.get(10017, 0),
            "car_status":         raw.get(10075, 0),
            "cp_state":           raw.get(10084, 0),
            "charger_type":       raw.get(10059, 0),
            "start_mode":         raw.get(10076, 0),
            "charge_strategy":    raw.get(10077, 0),
            "strategy_param":     raw.get(10078, 0),
            "appointment":        raw.get(10079, 0),
            "project_type":       raw.get(10107, 0),
            "power_source":       raw.get(10108, 0),
            "power_source_bits":  decode_bits(raw.get(10108, 0), POWER_SOURCE_BITS),
            "comms_status":       raw.get(10018, 0),
            "charge_duration":    _u32(raw, 10063),
            # ── Configuration (RW) ────────────────────────────────────────
            "ems_dispatch":       raw.get(10000, 0),
            "plug_charge":        raw.get(10019, 0),
            "single_3ph":         raw.get(10023, 0),
            "charging_mode":      raw.get(10032, 0),
            "max_power":          raw.get(10029, 0) / 10.0,
            "battery_soc":        raw.get(10030, 0),
            "grid_limit":         raw.get(10039, 0) / 10.0,
            "breaker_current":    raw.get(10026, 0),
            "charge_control":     raw.get(10060, 0),
            # None when the optional block is unreadable, so the select shows
            # unknown rather than claiming the default.
            "transparent_mode":   raw.get(10157),
            # ── Fault bytes ───────────────────────────────────────────────
            "fault_01":           raw.get(10001, 0),
            "fault_02":           raw.get(10002, 0),
            "fault_03":           raw.get(10003, 0),
            "fault_05":           raw.get(10005, 0),
            "fault_06":           raw.get(10006, 0),
            "fault_07":           raw.get(10007, 0),
            # ── Decoded aggregates ────────────────────────────────────────
            "active_faults":      faults,
            "active_warnings":    warnings,
            "fault_state":        state,
            "comms_links":        comms_links,
        }

    def _ensure_connected(self) -> None:
        if not self._client.connected:
            if not self._client.connect():
                raise UpdateFailed("Cannot connect to GoodWe EV charger")

    def close(self) -> None:
        self._client.close()
