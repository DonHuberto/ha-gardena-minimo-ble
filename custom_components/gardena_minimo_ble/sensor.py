"""Sensor platform for GARDENA SILENO minimo BLE."""

from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GardenaMinimoConfigEntry
from .entity import GardenaMinimoBleDescriptorEntity

DESCRIPTIONS = (
    SensorEntityDescription(
        key="battery_level",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenaMinimoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up mower sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        GardenaMinimoBleSensor(coordinator, description)
        for description in DESCRIPTIONS
        if description.key in coordinator.data
    )


class GardenaMinimoBleSensor(
    GardenaMinimoBleDescriptorEntity,
    SensorEntity,
):
    """Mower sensor."""

    entity_description: SensorEntityDescription

    @property
    @override
    def native_value(self) -> str | int:
        """Return the coordinated sensor value."""
        return self.coordinator.data[self.entity_description.key]
