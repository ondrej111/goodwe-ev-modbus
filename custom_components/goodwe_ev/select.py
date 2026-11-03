from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    REG_CHARGING_MODE,
    CHARGING_MODE,
    REG_TRANSPARENT_MODE,
    TRANSPARENT_MODE,
)
from .coordinator import GoodweEVCoordinator
from .sensor import _device_info

# Reverse map: label → register value
_MODE_TO_INT = {v: k for k, v in CHARGING_MODE.items()}
_TRANSPARENT_TO_INT = {v: k for k, v in TRANSPARENT_MODE.items()}


@dataclass(frozen=True, kw_only=True)
class GoodweSelectDescription(SelectEntityDescription):
    data_key: str = ""
    register: int = 0
    int_to_option: dict[int, str] = None  # type: ignore[assignment]
    option_to_int: dict[str, int] = None  # type: ignore[assignment]


SELECTS: tuple[GoodweSelectDescription, ...] = (
    GoodweSelectDescription(
        key="charging_mode",
        data_key="charging_mode",
        name="Charging Mode",
        register=REG_CHARGING_MODE,
        options=list(CHARGING_MODE.values()),
        int_to_option=CHARGING_MODE,
        option_to_int=_MODE_TO_INT,
    ),
    # Changes how the charger reaches GoodWe's cloud, so it is a config entity
    # and off by default: enable it deliberately to inspect or test it.
    GoodweSelectDescription(
        key="transparent_mode",
        data_key="transparent_mode",
        name="Transparent Mode",
        translation_key="transparent_mode",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        register=REG_TRANSPARENT_MODE,
        options=list(TRANSPARENT_MODE.values()),
        int_to_option=TRANSPARENT_MODE,
        option_to_int=_TRANSPARENT_TO_INT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GoodweEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GoodweSelect(coordinator, entry, desc) for desc in SELECTS
    )


class GoodweSelect(CoordinatorEntity[GoodweEVCoordinator], SelectEntity):
    entity_description: GoodweSelectDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GoodweEVCoordinator,
        entry: ConfigEntry,
        description: GoodweSelectDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(coordinator, entry)
        self._attr_options = description.options

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.data.get(self.entity_description.data_key)
        if raw is None:
            return None
        return self.entity_description.int_to_option.get(raw)

    async def async_select_option(self, option: str) -> None:
        raw = self.entity_description.option_to_int[option]
        await self.coordinator.async_write_register(
            self.entity_description.register, raw
        )
