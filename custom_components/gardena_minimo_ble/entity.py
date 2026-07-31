"""Base entities for GARDENA SILENO minimo BLE."""

from typing import override

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import GardenaMinimoCoordinator


class GardenaMinimoBleEntity(CoordinatorEntity[GardenaMinimoCoordinator]):
    """Base coordinator entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GardenaMinimoCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)

        self._attr_device_info = DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{coordinator.address}_{coordinator.channel_id}",
                )
            },
            manufacturer=MANUFACTURER,
            model_id=coordinator.model,
            suggested_area="Garden",
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    format_mac(coordinator.address),
                )
            },
        )

    @property
    @override
    def available(self) -> bool:
        """Return whether the entity is available."""
        return super().available and self.coordinator.mower.is_connected()


class GardenaMinimoBleDescriptorEntity(GardenaMinimoBleEntity):
    """Base entity for entities with descriptions."""

    def __init__(
        self,
        coordinator: GardenaMinimoCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the described entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.address}_{coordinator.channel_id}_{description.key}"
        )
        self.entity_description = description
