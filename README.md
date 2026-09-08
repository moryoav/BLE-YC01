# BLE-YC01

I am using this experimental fork of [jdeath/BLE-YC01](https://github.com/jdeath/BLE-YC01) to test whether a simple Bluetooth connection followed by a disconnect keeps the pool monitor awake.

I replaced the original 30-minute measurement polling with a configurable keep-alive interval, set to **4 minutes** by default. This version does not read `FF02` or any other characteristic during discovery, setup, or scheduled cycles. It does not write characteristics or subscribe to notifications. The Bluetooth stack may still discover GATT services as part of connecting.

## Installation

1. Add `https://github.com/moryoav/BLE-YC01` to HACS as a custom repository with category **Integration**.
2. Download BLE-YC01 and restart Home Assistant.
3. Add the discovered device under **Settings → Devices & services**.

If the upstream integration is already installed, replace its HACS repository with this fork and download it again. Both use the `ble_yc01` domain, so install only one copy. Existing configuration entries and measurement entity IDs are retained.

A connectable Bluetooth adapter or an ESPHome Bluetooth proxy with active connections enabled is required.

## Configuration

Open **Settings → Devices & services → BLE-YC01 → Configure** for the device.

Set **Keep-alive interval (minutes)** to a positive whole number. The default is **4**. Saving reloads that device's integration and applies the new interval without restarting Home Assistant.

A connect → disconnect cycle runs when the entry loads, then repeats at the selected interval after each attempt finishes. Each cycle makes one connection attempt and disconnects immediately after connecting. Connection and disconnect timeouts are 30 and 10 seconds. Failed scheduled attempts are logged and retried at the next interval. If the first connection fails, Home Assistant retries setup.

The timer runs even if all sensor entities are disabled. Unloading or disabling the integration stops it. Home Assistant's **Enable polling for updates** system option must remain enabled.

## Checking the experiment

The diagnostic sensor **Last successful keep-alive** records when both connection and disconnect complete. It becomes unavailable if the latest attempt fails and recovers on a successful cycle.

Pool measurements, including pH, temperature, and battery, are **unavailable** in this experiment because their source was the `FF02` read. The previous measurement entity IDs remain in place.

I will consider the experiment successful only after the physical device stays awake beyond its usual sleep period. A successful connection timestamp alone does not prove that. Avoid another app or automation connecting to or reading the device during the test, since that would affect the result. If connection alone is insufficient, a later experiment can add a GATT read.

## Development

I run the tests on Linux with Python 3.14:

```sh
python -m pip install -r requirements-test.txt
python -m pytest
ruff check .
ruff format --check .
```

The tests use Home Assistant with mocked Bluetooth connections; they do not validate the physical device's sleep behavior.

## Credits

This fork is based on [jdeath/BLE-YC01](https://github.com/jdeath/BLE-YC01). The original device research and decoding came from @anasm2010, @RubenKona, and contributors to the [Home Assistant community discussion](https://community.home-assistant.io/t/pool-monitor-device-yieryi-ble-yc01).
