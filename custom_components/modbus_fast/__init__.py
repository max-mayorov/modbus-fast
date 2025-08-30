from __future__ import annotations

import asyncio
import logging
import time
import inspect
from typing import List, Optional

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    SIGNAL_UPDATE,
    CONF_HOST,
    CONF_PORT,
    CONF_UNIT_ID,
    CONF_REGISTER_TYPE,
    CONF_START_ADDRESS,
    CONF_COUNT,
    CONF_SAMPLE_MS,
    CONF_NAME,
    CONF_ONLY_ON_CHANGE,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DEFAULT_REGISTER_TYPE,
    DEFAULT_START_ADDRESS,
    DEFAULT_COUNT,
    DEFAULT_SAMPLE_MS,
    DEFAULT_NAME,
    DEFAULT_ONLY_ON_CHANGE,
)

_LOGGER = logging.getLogger(__name__)

# YAML configuration for the domain
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.Coerce(int),
                vol.Optional(CONF_REGISTER_TYPE, default=DEFAULT_REGISTER_TYPE): vol.In(["holding", "input", "coil"]),
                vol.Optional(CONF_START_ADDRESS, default=DEFAULT_START_ADDRESS): vol.Coerce(int),
                vol.Optional(CONF_COUNT, default=DEFAULT_COUNT): vol.All(vol.Coerce(int), vol.Range(min=1, max=128)),
                vol.Optional(CONF_SAMPLE_MS, default=DEFAULT_SAMPLE_MS): vol.All(vol.Coerce(int), vol.Range(min=1, max=10000)),
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Optional(CONF_ONLY_ON_CHANGE, default=DEFAULT_ONLY_ON_CHANGE): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

class ModbusFastHub:
    """Shared hub that polls Modbus quickly and pushes updates to entities."""

    def __init__(self, hass: HomeAssistant, conf: dict) -> None:
        self.hass = hass
        self.host: str = conf[CONF_HOST]
        self.port: int = conf[CONF_PORT]
        self.unit_id: int = conf[CONF_UNIT_ID]
        self.register_type: str = conf[CONF_REGISTER_TYPE]
        self.start_address: int = conf[CONF_START_ADDRESS]
        self.count: int = conf[CONF_COUNT]
        self.sample_ms: int = max(1, conf[CONF_SAMPLE_MS])
        self.name: str = conf[CONF_NAME]
        self.only_on_change: bool = conf[CONF_ONLY_ON_CHANGE]

        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self.values: List[Optional[bool]] = [None] * self.count
        self.connected: bool = False
        self._client = None
        # Cache which kwarg the installed pymodbus expects for unit id ('unit' vs 'slave')
        self._unit_kw_name: Optional[str] = None

    async def async_setup(self) -> None:
        from pymodbus.client import AsyncModbusTcpClient  # type: ignore

        _LOGGER.info(
            "Setting up Modbus Fast Poller to %s:%s (unit %s), type=%s, addr=%s, count=%s, period=%sms",
            self.host,
            self.port,
            self.unit_id,
            self.register_type,
            self.start_address,
            self.count,
            self.sample_ms,
        )
        # Be a bit more tolerant on initial timeout; 50ms is often too tight
        self._client = AsyncModbusTcpClient(host=self.host, port=self.port, timeout=1.0)
        ok = await self._client.connect()
        self.connected = bool(ok)
        if not self.connected:
            _LOGGER.warning("Modbus client failed to connect initially (will keep retrying).")
        self._task = self.hass.loop.create_task(self._poll_loop())
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_hass_stop)

    async def _on_hass_stop(self, _event) -> None:
        await self.async_close()

    async def async_close(self) -> None:
        self._stop_evt.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        self.connected = False

    async def _ensure_connected(self):
        if self._client is None:
            return
        if not getattr(self._client, "connected", False):
            try:
                ok = await self._client.connect()
                self.connected = bool(ok)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Reconnect failed: %s", exc)
                self.connected = False

    def _get_unit_kwargs(self, method) -> dict:
        """Determine whether this pymodbus expects 'unit' or 'slave' kwarg and cache it."""
        if self._unit_kw_name is None:
            try:
                params = inspect.signature(method).parameters
                if "unit" in params:
                    self._unit_kw_name = "unit"
                elif "slave" in params:
                    self._unit_kw_name = "slave"
                else:
                    # Default to 'unit' when unknown
                    self._unit_kw_name = "unit"
            except Exception:  # noqa: BLE001
                self._unit_kw_name = "unit"
            _LOGGER.debug("Using '%s' kwarg for unit id", self._unit_kw_name)
        return {self._unit_kw_name: self.unit_id}

    async def _read_call(self, method_name: str):
        """Call a pymodbus read method with compatibility for unit/slave kwarg."""
        if self._client is None:
            return None
        method = getattr(self._client, method_name, None)
        if method is None:
            raise AttributeError(f"Client missing method {method_name}")

        try:
            return await method(address=self.start_address, count=self.count, **self._get_unit_kwargs(method))
        except TypeError as te:
            # Retry once with the alternate kwarg name if first try failed due to bad kw
            msg = str(te)
            if ("unit" in msg and "unexpected" in msg) or ("got an unexpected keyword" in msg):
                self._unit_kw_name = "slave"
                return await method(address=self.start_address, count=self.count, **self._get_unit_kwargs(method))
            if ("slave" in msg and "unexpected" in msg) or ("got an unexpected keyword" in msg):
                self._unit_kw_name = "unit"
                return await method(address=self.start_address, count=self.count, **self._get_unit_kwargs(method))
            raise

    async def _poll_once(self) -> Optional[List[bool]]:
        """Fetch a batch of values as booleans."""
        if self._client is None:
            return None
        await self._ensure_connected()
        if not getattr(self._client, "connected", False):
            return None

        try:
            if self.register_type == "coil":
                rr = await self._read_call("read_coils")
                if rr.isError():
                    raise Exception(str(rr))  # noqa: TRY002
                bits = list(getattr(rr, "bits", []) )[: self.count]
                self.connected = True
                return [bool(b) for b in bits]
            elif self.register_type == "input":
                rr = await self._read_call("read_input_registers")
                if rr.isError():
                    raise Exception(str(rr))  # noqa: TRY002
                regs = getattr(rr, "registers", [])
            else:  # holding
                rr = await self._read_call("read_holding_registers")
                if rr.isError():
                    raise Exception(str(rr))  # noqa: TRY002
                regs = getattr(rr, "registers", [])
            self.connected = True
            return [bool(v) for v in regs]
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Poll error: %s", exc)
            self.connected = False
            return None

    async def _poll_loop(self) -> None:
        """Tight poll loop with best-effort sleep to approximate the sample period."""
        period = self.sample_ms / 1000.0
        # Clamp to a minimum period because of HA & asyncio scheduling realities
        min_period = 0.001  # 1ms absolute lower bound
        period = max(min_period, period)

        try:
            while not self._stop_evt.is_set():
                t0 = time.perf_counter()
                new_vals = await self._poll_once()
                changed_idx = None
                if new_vals is not None:
                    if self.values is None or len(self.values) != len(new_vals):
                        self.values = [None] * len(new_vals)
                    if self.only_on_change:
                        changed_idx = [i for i, (a, b) in enumerate(zip(self.values, new_vals)) if a != b]
                        if changed_idx:
                            self.values = new_vals
                            async_dispatcher_send(self.hass, SIGNAL_UPDATE, changed_idx)
                    else:
                        self.values = new_vals
                        async_dispatcher_send(self.hass, SIGNAL_UPDATE, None)

                # sleep the remainder
                elapsed = time.perf_counter() - t0
                sleep_for = max(0.0, period - elapsed)
                await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("Poll loop crashed: %s", exc)
        finally:
            _LOGGER.info("Modbus Fast Poller stopped.")
            self.connected = False

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    conf = config.get(DOMAIN)
    if not conf:
        return True

    hub = ModbusFastHub(hass, conf)
    await hub.async_setup()
    hass.data[DOMAIN] = hub

    # Load the binary_sensor platform
    hass.async_create_task(
        async_load_platform(hass, "binary_sensor", DOMAIN, {}, conf)
    )
    return True
