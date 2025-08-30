from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATE

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(hass: HomeAssistant, config: dict, add_entities, discovery_info=None) -> None:
    hub = hass.data[DOMAIN]
    entities = []
    name_prefix = getattr(hub, "name", "Modbus Fast")
    # Map register type to letter per request
    type_letter = {
        "holding": "H",
        "input": "R",
        "coil": "C",
        "discrete": "I",
    }.get(getattr(hub, "register_type", "holding"), "H")

    for i in range(hub.count):
        base_addr = hub.start_address + i
        # Adjust for one-based naming if enabled
        display_addr = base_addr + 1 if getattr(hub, "one_based_names", False) else base_addr
        name = f"{name_prefix} {type_letter}{display_addr}"
        entities.append(ModbusFastBinarySensor(hub, i, name))
    add_entities(entities)


class ModbusFastBinarySensor(BinarySensorEntity):
    _attr_should_poll = False

    def __init__(self, hub, index: int, name: str) -> None:
        self._hub = hub
        self._index = index
        self._attr_name = name
        # Compute unique id address respecting one_based_names
        _base_addr = hub.start_address + index
        _id_addr = _base_addr + 1 if getattr(hub, "one_based_names", False) else _base_addr
        # Include port in unique_id to avoid collisions across ports
        self._attr_unique_id = f"{DOMAIN}_{hub.host}_{hub.port}_{hub.unit_id}_{_id_addr}"
        self._last_state: Optional[bool] = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_hub_update)
        )

    @property
    def is_on(self) -> Optional[bool]:
        vals = self._hub.values
        if vals is None or self._index >= len(vals):
            return None
        return vals[self._index]

    @property
    def available(self) -> bool:
        return bool(self._hub.connected)

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, f"{self._hub.host}:{self._hub.port}:{self._hub.unit_id}")},
            "name": self._hub.name,
            "manufacturer": "Modbus Device",
            "model": f"{self._hub.register_type}@{self._hub.start_address}+{self._hub.count}",
        }

    @callback
    def _handle_hub_update(self, changed_idx: Optional[list[int]]) -> None:
        # Only write state if ours changed (or if hub signaled a full update)
        if changed_idx is None or self._index in changed_idx:
            self._last_state = self.is_on
            self.async_write_ha_state()
