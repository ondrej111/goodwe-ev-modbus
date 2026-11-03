from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, COMMS_BITS
from .coordinator import GoodweEVCoordinator
from .sensor import _device_info


@dataclass(frozen=True, kw_only=True)
class GoodweBinarySensorDescription(BinarySensorEntityDescription):
    # Key into coordinator.data["comms_links"], or None for the fault/warning
    # entities which read a top-level list instead.
    link_key: str | None = None
    list_key: str | None = None


# Register 10018 exposes one bit per communication link. Splitting these into
# individual connectivity entities rather than one combined string sensor keeps
# each link independently graphable and usable as an automation trigger — the
# inverter and EMS bits in particular are what go dark when the charger loses
# its view of the house energy system.
BINARY_SENSORS: tuple[GoodweBinarySensorDescription, ...] = tuple(
    GoodweBinarySensorDescription(
        key=key,
        name=label,
        link_key=key,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    )
    for _bit, (key, label) in sorted(COMMS_BITS.items())
) + (
    GoodweBinarySensorDescription(
        key="fault",
        name="Fault",
        list_key="active_faults",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    GoodweBinarySensorDescription(
        key="warning",
        name="Warning",
        list_key="active_warnings",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoodweEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GoodweBinarySensor(coordinator, entry, desc) for desc in BINARY_SENSORS
    )


class GoodweBinarySensor(CoordinatorEntity[GoodweEVCoordinator], BinarySensorEntity):
    entity_description: GoodweBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GoodweEVCoordinator,
        entry: ConfigEntry,
        description: GoodweBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if self.entity_description.link_key is not None:
            links = data.get("comms_links") or {}
            return links.get(self.entity_description.link_key)
        if self.entity_description.list_key is not None:
            items = data.get(self.entity_description.list_key)
            if items is None:
                return None
            return bool(items)
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.list_key is None:
            return None
        return {"active": self.coordinator.data.get(self.entity_description.list_key)}
