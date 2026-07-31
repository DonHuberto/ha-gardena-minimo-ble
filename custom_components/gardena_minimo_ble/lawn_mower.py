"""Lawn mower platform for GARDENA SILENO minimo BLE."""

from typing import override

from automower_ble.protocol import MowerActivity, MowerState

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GardenaMinimoConfigEntry
from .const import LOGGER
from .coordinator import GardenaMinimoCoordinator
from .entity import GardenaMinimoBleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GardenaMinimoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mower entity."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [GardenaMinimoLawnMower(coordinator, coordinator.address)]
    )


class GardenaMinimoLawnMower(GardenaMinimoBleEntity, LawnMowerEntity):
    """GARDENA SILENO minimo mower."""

    _attr_name = None
    _attr_supported_features = (
        LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(
        self,
        coordinator: GardenaMinimoCoordinator,
        address: str,
    ) -> None:
        """Initialize the mower."""
        super().__init__(coordinator)
        self._attr_unique_id = address

    def _get_activity(self) -> LawnMowerActivity | None:
        """Translate mower protocol state into Home Assistant activity."""
        if self.coordinator.data is None:
            return None

        state = self.coordinator.data["state"]
        activity = self.coordinator.data["activity"]

        if state is None or activity is None:
            return None

        if state == MowerState.PAUSED:
            return LawnMowerActivity.PAUSED

        if state in (
            MowerState.STOPPED,
            MowerState.OFF,
            MowerState.WAIT_FOR_SAFETYPIN,
        ):
            return LawnMowerActivity.ERROR

        if (
            state == MowerState.PENDING_START
            and activity == MowerActivity.NONE
        ):
            return LawnMowerActivity.ERROR

        if state in (
            MowerState.RESTRICTED,
            MowerState.IN_OPERATION,
            MowerState.PENDING_START,
        ):
            if activity in (
                MowerActivity.CHARGING,
                MowerActivity.PARKED,
                MowerActivity.NONE,
            ):
                return LawnMowerActivity.DOCKED
            if activity in (
                MowerActivity.GOING_OUT,
                MowerActivity.MOWING,
            ):
                return LawnMowerActivity.MOWING
            if activity == MowerActivity.GOING_HOME:
                return LawnMowerActivity.RETURNING

        return LawnMowerActivity.ERROR

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle coordinator updates."""
        self._attr_activity = self._get_activity()
        self._attr_available = self._attr_activity is not None
        super()._handle_coordinator_update()

    @override
    async def async_start_mowing(self) -> None:
        """Start or resume mowing."""
        LOGGER.debug("Starting mower")
        await self.coordinator.async_ensure_connected()

        await self.coordinator.mower.mower_resume()
        if self._attr_activity is LawnMowerActivity.DOCKED:
            await self.coordinator.mower.mower_override()

        await self.coordinator.async_request_refresh()

    @override
    async def async_dock(self) -> None:
        """Send the mower to the charging station."""
        LOGGER.debug("Docking mower")
        await self.coordinator.async_ensure_connected()
        await self.coordinator.mower.mower_park()
        await self.coordinator.async_request_refresh()

    @override
    async def async_pause(self) -> None:
        """Pause mowing."""
        LOGGER.debug("Pausing mower")
        await self.coordinator.async_ensure_connected()
        await self.coordinator.mower.mower_pause()
        await self.coordinator.async_request_refresh()
