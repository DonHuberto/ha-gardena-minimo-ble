"""GARDENA SILENO minimo BLE integration.

This custom integration keeps the first authenticated BLE connection created
during the config flow and hands it directly to the runtime coordinator.
That avoids the probe -> disconnect -> pair sequence used by the core
Husqvarna Automower BLE integration.
"""

from typing import Any

from automower_ble.mower import Mower
from automower_ble.protocol import ResponseResult
from bleak import BleakError
from bleak_retry_connector import close_stale_connections_by_address, get_device

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothReachabilityIntent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_CLIENT_ID, CONF_PIN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_MODEL, DOMAIN, LOGGER, PENDING_MOWERS
from .coordinator import GardenaMinimoCoordinator

type GardenaMinimoConfigEntry = ConfigEntry[GardenaMinimoCoordinator]

PLATFORMS = [Platform.LAWN_MOWER, Platform.SENSOR]


def _connection_not_ready(
    hass: HomeAssistant,
    address: str,
    error: str,
) -> ConfigEntryNotReady:
    """Build a translated connection error."""
    return ConfigEntryNotReady(
        translation_domain=DOMAIN,
        translation_key="connection_failed",
        translation_placeholders={
            "address": address,
            "error": error,
            "reason": bluetooth.async_address_reachability_diagnostics(
                hass,
                address.upper(),
                BluetoothReachabilityIntent.CONNECTION,
            ),
        },
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GardenaMinimoConfigEntry,
) -> bool:
    """Set up GARDENA SILENO minimo BLE from a config entry."""
    if CONF_PIN not in entry.data:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="pin_required",
            translation_placeholders={"domain_name": "GARDENA SILENO minimo BLE"},
        )

    address = entry.data[CONF_ADDRESS].upper()
    pin = int(entry.data[CONF_PIN])
    channel_id = int(entry.data[CONF_CLIENT_ID])
    model = entry.data.get(CONF_MODEL, entry.title)

    domain_data: dict[str, Any] = hass.data.setdefault(DOMAIN, {})
    pending: dict[str, tuple[Mower, str]] = domain_data.setdefault(
        PENDING_MOWERS, {}
    )

    staged = pending.pop(address, None)
    mower: Mower | None = None

    if staged is not None:
        staged_mower, staged_model = staged
        if staged_mower.is_connected():
            LOGGER.debug(
                "Using the still-connected mower from the config flow: %s",
                address,
            )
            mower = staged_mower
            model = staged_model or model
        else:
            LOGGER.debug("Discarding a disconnected staged mower: %s", address)

    if mower is None:
        mower = Mower(channel_id, address, pin)
        await close_stale_connections_by_address(address)

        device = bluetooth.async_ble_device_from_address(
            hass, address, connectable=True
        ) or await get_device(address)

        if device is None:
            raise _connection_not_ready(hass, address, "device not found")

        LOGGER.debug(
            "Connecting to %s with channel ID %s",
            address,
            channel_id,
        )

        try:
            response_result = await mower.connect(device)
        except (TimeoutError, BleakError) as exception:
            raise _connection_not_ready(
                hass,
                address,
                str(exception) or type(exception).__name__,
            ) from exception

        if response_result is ResponseResult.INVALID_PIN:
            raise ConfigEntryAuthFailed(
                f"Unable to connect to device {address} due to wrong PIN"
            )

        if response_result is not ResponseResult.OK:
            raise _connection_not_ready(hass, address, response_result.name)

    LOGGER.debug("Connected and authenticated: %s", address)

    coordinator = GardenaMinimoCoordinator(
        hass,
        entry,
        mower,
        address,
        channel_id,
        model,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        if mower.is_connected():
            await mower.disconnect()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: GardenaMinimoConfigEntry,
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        coordinator = entry.runtime_data
        await coordinator.async_shutdown()

    return unload_ok
