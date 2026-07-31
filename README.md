# GARDENA SILENO minimo BLE for Home Assistant

Custom Home Assistant integration for GARDENA SILENO minimo mowers connected
through an ESPHome Bluetooth Proxy.

## Why this exists

The core `husqvarna_automower_ble` configuration flow first probes the mower,
disconnects, opens a second BLE connection, and only then attempts pairing.

Some SILENO minimo units expose `pairable=True` for a short window but reject
pairing on that second connection with error `82` / `0x52`.

This integration performs pairing on the first connection and keeps that same
live `Mower` object for config-entry setup and normal polling.

## Supported baseline

- Home Assistant 2026.7.1
- ESPHome Bluetooth Proxy
- `automower-ble==0.2.9`
- `gardena-bluetooth==2.8.1`
- Tested target: GARDENA SILENO minimo 250

## Manual installation

Copy:

```text
custom_components/gardena_minimo_ble
```

to:

```text
/config/custom_components/gardena_minimo_ble
```

For the Synology Container installation used during development, the host path
is typically:

```text
/volume2/docker/homeassistant/config/custom_components/gardena_minimo_ble
```

Restart the full Home Assistant container.

## Configuration

1. Do not configure the built-in **Husqvarna Automower BLE** integration.
2. Keep the ESPHome Bluetooth Proxy close to the mower.
3. Remove the mower from the GARDENA phone app and the phone's system Bluetooth
   pairing list.
4. Disable Bluetooth on the phone.
5. Fully power off the mower, wait several seconds, and power it on.
6. Enter the physical mower PIN.
7. Confirm in Home Assistant Bluetooth logs that the mower advertises:

   ```text
   pairable=True
   ```

   or manufacturer data containing:

   ```text
   02 05 01
   ```

8. Add **GARDENA SILENO minimo BLE** and enter the numeric PIN.

For a button PIN:

```text
Start → Park → ON/OFF → Schedule
```

the numeric value is:

```text
3412
```

Mapping:

```text
ON/OFF   = 1
Schedule = 2
Start    = 3
Park     = 4
```

## Important behavior

The integration deliberately keeps one BLE connection open. It therefore uses
one connection slot on the ESPHome proxy.

If Home Assistant, the proxy, or the mower is restarted and reconnection fails,
restart the mower to reopen its pairing window, then reload this integration.

## HACS

After this project is published as a GitHub repository:

1. Open HACS.
2. Add the repository as a custom repository of type **Integration**.
3. Install **GARDENA SILENO minimo BLE**.
4. Restart Home Assistant.
