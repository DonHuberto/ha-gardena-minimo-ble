"""Data coordinator for GARDENA SILENO minimo BLE."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any, override

from automower_ble.mower import Mower
from automower_ble.protocol import ResponseResult
from bleak import BleakError
from bleak_retry_connector import close_stale_connections_by_address

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from . import GardenaMinimoConfigEntry

SCAN_INTERVAL = timedelta(seconds=60)


class GardenaMinimoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage the long-lived BLE connection and mower polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: "GardenaMinimoConfigEntry",
        mower: Mower,
        address: str,
        channel_id: int,
        model: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.address = address
        self.channel_id = channel_id
        self.model = model
        self.mower = mower

    @override
    async def async_shutdown(self) -> None:
        """Shut down and close the BLE connection."""
        LOGGER.debug("Shutting down coordinator")
        await super().async_shutdown()
        if self.mower.is_connected():
            await self.mower.disconnect()

    async def async_ensure_connected(self) -> None:
        """Reconnect when the long-lived connection was lost."""
        if self.mower.is_connected():
            return

        LOGGER.debug("Trying to reconnect to %s", self.address)
        await close_stale_connections_by_address(self.address)

        device = bluetooth.async_ble_device_from_address(
            self.hass,
            self.address,
            connectable=True,
        )

        if device is None:
            raise UpdateFailed("Mower is not currently discoverable")

        try:
            response = await self.mower.connect(device)
        except (BleakError, TimeoutError) as err:
            await close_stale_connections_by_address(self.address)
            raise UpdateFailed(
                "Failed to reconnect. Restart the mower to reopen its "
                "pairing window, then reload the integration."
            ) from err

        if response is not ResponseResult.OK:
            raise UpdateFailed(
                f"Failed to reconnect: {response.name}. Restart the mower "
                "and reload the integration."
            )

    @override
    async def _async_update_data(self) -> dict[str, Any]:
        """Poll the mower while keeping the BLE session open."""
        LOGGER.debug("Polling mower")
        await self.async_ensure_connected()

        try:
            battery_level = await self.mower.battery_level()
            activity = await self.mower.mower_activity()
            state = await self.mower.mower_state()
        except (BleakError, TimeoutError) as err:
            raise UpdateFailed("Error getting data from mower") from err

        if battery_level is None or activity is None or state is None:
            raise UpdateFailed("Mower returned incomplete data")

        return {
            "battery_level": battery_level,
            "activity": activity,
            "state": state,
        }
