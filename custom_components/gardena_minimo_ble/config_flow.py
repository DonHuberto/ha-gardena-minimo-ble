"""Config flow for GARDENA SILENO minimo BLE."""

from collections.abc import Mapping
import random
from typing import Any, override

from automower_ble.mower import Mower
from automower_ble.protocol import ResponseResult
from bleak import BleakError
from bleak_retry_connector import close_stale_connections_by_address, get_device
from gardena_bluetooth.const import ScanService
from gardena_bluetooth.parse import ProductType
from gardena_bluetooth.scan import async_get_manufacturer_data
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.config_entries import SOURCE_BLUETOOTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_CLIENT_ID, CONF_PIN

from .const import CONF_MODEL, DOMAIN, LOGGER, PENDING_MOWERS

BLUETOOTH_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS): str,
        vol.Required(CONF_PIN): str,
    }
)

REAUTH_SCHEMA = BLUETOOTH_SCHEMA
PAIRABLE_FIELDS = {"pairable"}


def _pin_valid(pin: str) -> bool:
    """Check whether the PIN contains only digits."""
    try:
        int(pin)
    except (TypeError, ValueError):
        return False
    return True


class GardenaMinimoBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GARDENA SILENO minimo BLE."""

    VERSION = 1

    address: str | None = None
    mower_name: str = ""
    pin: str | None = None
    pairable: bool | None = None

    async def _is_supported(
        self,
        discovery_info: BluetoothServiceInfo,
    ) -> bool:
        """Check whether the discovered device is a mower."""
        if ScanService not in discovery_info.service_uuids:
            LOGGER.debug(
                "Unsupported device, missing service %s: %s",
                ScanService,
                discovery_info,
            )
            return False

        manufacturer_data = (
            await async_get_manufacturer_data({discovery_info.address})
        )[discovery_info.address]

        if manufacturer_data.product_type is not ProductType.MOWER:
            LOGGER.debug(
                "Unsupported device: %s (%s)",
                manufacturer_data,
                discovery_info,
            )
            return False

        self.pairable = manufacturer_data.pairable
        LOGGER.info(
            "PAIRING STATE [discovery] address=%s: pairable=%s; data=%s",
            discovery_info.address,
            self.pairable,
            manufacturer_data,
        )
        return True

    async def _log_pairing_state(
        self,
        stage: str,
        *,
        timeout: float = 12.0,
    ) -> bool | None:
        """Read and log an explicit, human-readable mower pairing state."""
        assert self.address

        try:
            manufacturer_data_by_address = await async_get_manufacturer_data(
                {self.address},
                fields=PAIRABLE_FIELDS,
                timeout=timeout,
            )
        except TimeoutError:
            self.pairable = None
            LOGGER.warning(
                "PAIRING STATE [%s] address=%s: pairable=UNKNOWN; "
                "no complete manufacturer packet received within %.1f seconds",
                stage,
                self.address,
                timeout,
            )
            return None

        manufacturer_data = manufacturer_data_by_address.get(self.address)
        if manufacturer_data is None:
            self.pairable = None
            LOGGER.warning(
                "PAIRING STATE [%s] address=%s: pairable=UNKNOWN; "
                "manufacturer data unavailable",
                stage,
                self.address,
            )
            return None

        self.pairable = manufacturer_data.pairable

        if self.pairable is None:
            LOGGER.warning(
                "PAIRING STATE [%s] address=%s: pairable=UNKNOWN; "
                "only partial manufacturer data was received within %.1f seconds; "
                "serial=%s group=%s model=%s variant=%s",
                stage,
                self.address,
                timeout,
                manufacturer_data.serial,
                manufacturer_data.group,
                manufacturer_data.model,
                manufacturer_data.variant,
            )
            return None

        message = (
            "PAIRING STATE [%s] address=%s: pairable=%s; "
            "serial=%s group=%s model=%s variant=%s"
        )
        arguments = (
            stage,
            self.address,
            self.pairable,
            manufacturer_data.serial,
            manufacturer_data.group,
            manufacturer_data.model,
            manufacturer_data.variant,
        )

        if self.pairable is True:
            LOGGER.info(message, *arguments)
        else:
            LOGGER.warning(message, *arguments)

        return self.pairable

    @override
    async def async_step_bluetooth(
        self,
        discovery_info: BluetoothServiceInfo,
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        LOGGER.debug("Discovered device: %s", discovery_info)

        if not await self._is_supported(discovery_info):
            return self.async_abort(reason="no_devices_found")

        self.address = discovery_info.address.upper()
        self.mower_name = discovery_info.name or self.address

        self.context["title_placeholders"] = {
            "name": self.mower_name,
            "address": self.address,
        }

        await self.async_set_unique_id(self.address)
        self._abort_if_unique_id_configured()
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm a discovered mower."""
        assert self.address
        errors: dict[str, str] = {}

        if user_input is not None:
            if not _pin_valid(user_input[CONF_PIN]):
                errors["base"] = "invalid_pin"
            else:
                self.pin = user_input[CONF_PIN]

                if self.pairable is False:
                    LOGGER.warning(
                        "The mower did not appear pairable during discovery. "
                        "The state will be checked again immediately before "
                        "the connection attempt."
                    )

                result = await self._connect_and_stage()
                if isinstance(result, str):
                    errors["base"] = result
                else:
                    channel_id, model = result
                    return self.async_create_entry(
                        title=self._entry_title(model),
                        data={
                            CONF_ADDRESS: self.address,
                            CONF_CLIENT_ID: channel_id,
                            CONF_PIN: self.pin,
                            CONF_MODEL: model,
                        },
                    )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                BLUETOOTH_SCHEMA,
                user_input,
            ),
            description_placeholders={
                "name": self.mower_name or self.address
            },
            errors=errors,
        )

    @override
    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle manual configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not _pin_valid(user_input[CONF_PIN]):
                errors["base"] = "invalid_pin"
            else:
                self.address = user_input[CONF_ADDRESS].upper()
                self.pin = user_input[CONF_PIN]
                self.mower_name = self.address

                await self.async_set_unique_id(
                    self.address,
                    raise_on_progress=False,
                )
                self._abort_if_unique_id_configured()

                result = await self._connect_and_stage()
                if isinstance(result, str):
                    errors["base"] = result
                else:
                    channel_id, model = result
                    return self.async_create_entry(
                        title=self._entry_title(model),
                        data={
                            CONF_ADDRESS: self.address,
                            CONF_CLIENT_ID: channel_id,
                            CONF_PIN: self.pin,
                            CONF_MODEL: model,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA,
                user_input,
            ),
            errors=errors,
        )

    def _entry_title(self, model: str) -> str:
        """Build a readable config-entry title."""
        if model.upper().startswith("GARDENA"):
            return model
        return f"GARDENA {model}"

    async def _connect_and_stage(
        self,
        channel_id: int | None = None,
    ) -> tuple[int, str] | str:
        """Pair once and retain the same live connection for setup."""
        assert self.address
        assert self.pin is not None

        channel_id = channel_id or random.randint(1, 0xFFFFFFFF)
        mower = Mower(channel_id, self.address, int(self.pin))

        await self._log_pairing_state("immediately before connection")
        await close_stale_connections_by_address(self.address)

        device = bluetooth.async_ble_device_from_address(
            self.hass,
            self.address,
            connectable=True,
        ) or await get_device(self.address)

        if device is None:
            LOGGER.debug("Could not find device %s", self.address)
            return "cannot_connect"

        try:
            LOGGER.debug(
                "Pairing on the first and only config-flow connection: %s",
                self.address,
            )
            response_result = await mower.connect(device)

            if response_result is not ResponseResult.OK:
                LOGGER.debug(
                    "Mower rejected the connection: %s",
                    response_result,
                )
                if mower.is_connected():
                    await mower.disconnect()

                await self._log_pairing_state(
                    "after rejected connection",
                    timeout=12.0,
                )

                if response_result in (
                    ResponseResult.INVALID_PIN,
                    ResponseResult.NOT_ALLOWED,
                ):
                    return "invalid_auth"
                return "cannot_connect"

            LOGGER.info(
                "PAIRING RESULT address=%s: Bluetooth authentication and "
                "Automower protocol handshake succeeded",
                self.address,
            )

            try:
                model = await mower.get_model()
                if not model:
                    model = self.mower_name or "SILENO minimo"
            except (BleakError, TimeoutError):
                LOGGER.exception("Unable to read mower model after pairing")
                model = self.mower_name or "SILENO minimo"

        except (BleakError, TimeoutError) as exception:
            LOGGER.exception(
                "PAIRING RESULT address=%s: FAILED: %s",
                self.address,
                exception,
            )
            if mower.is_connected():
                await mower.disconnect()

            await self._log_pairing_state(
                "after failed connection",
                timeout=12.0,
            )
            return "cannot_connect"

        domain_data = self.hass.data.setdefault(DOMAIN, {})
        pending: dict[str, tuple[Mower, str]] = domain_data.setdefault(
            PENDING_MOWERS,
            {},
        )

        previous = pending.pop(self.address, None)
        if previous is not None and previous[0].is_connected():
            await previous[0].disconnect()

        pending[self.address] = (mower, model)
        LOGGER.debug(
            "Staged live mower connection for config-entry setup: %s",
            self.address,
        )
        return channel_id, model

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        reauth_entry = self._get_reauth_entry()
        self.address = reauth_entry.data[CONF_ADDRESS].upper()
        self.mower_name = reauth_entry.title
        self.pin = reauth_entry.data.get(CONF_PIN, "")

        self.context["title_placeholders"] = {
            "name": self.mower_name,
            "address": self.address,
        }
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm a new PIN and retain the authenticated connection."""
        errors: dict[str, str] = {}

        if user_input is not None and not _pin_valid(user_input[CONF_PIN]):
            errors["base"] = "invalid_pin"
        elif user_input is not None:
            reauth_entry = self._get_reauth_entry()
            self.pin = user_input[CONF_PIN]

            result = await self._connect_and_stage(
                int(reauth_entry.data[CONF_CLIENT_ID])
            )

            if isinstance(result, str):
                errors["base"] = result
            else:
                channel_id, model = result
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data=reauth_entry.data
                    | {
                        CONF_CLIENT_ID: channel_id,
                        CONF_PIN: self.pin,
                        CONF_MODEL: model,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA,
                {CONF_PIN: self.pin},
            ),
            description_placeholders={"name": self.mower_name},
            errors=errors,
        )
