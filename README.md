# BLE-YC01

I maintain this fork of [jdeath/BLE-YC01](https://github.com/jdeath/BLE-YC01) to keep the pool monitor connected to Home Assistant continuously. The device has been observed to remain awake while a phone holds a Bluetooth connection.

## Connection and measurements

The integration connects when its configuration entry loads, reads the initial measurements from `FF02`, and **keeps that connection open**. It reads measurements again every **30 minutes by default** over the same connection.

If the link drops, the integration attempts to reconnect immediately. Failed attempts retry after 5 seconds. It also checks the client's local connection state every 5 seconds in case a disconnect callback is missed. These checks and reconnects do not read any characteristics or reset the measurement schedule.

One Bluetooth proxy connection slot stays occupied while connected. Measurement entities become unavailable while the connection is down. Disabling or unloading the integration, or stopping Home Assistant, closes the connection and stops reconnection attempts.

The connection worker remains active even if all sensor entities are disabled or Home Assistant's **Enable polling for updates** option is turned off. That option controls measurement polling only.

A connection cannot be guaranteed during radio interference, a proxy outage, or a Home Assistant restart. If the device falls asleep during an outage and cannot be woken remotely, wake it manually so the integration can reconnect.

## Installation

1. Add `https://github.com/moryoav/BLE-YC01` to HACS as a custom repository with category **Integration**.
2. Download BLE-YC01 and restart Home Assistant.
3. Add the discovered device under **Settings > Devices & services**.

A connectable Bluetooth adapter or an ESPHome Bluetooth proxy with active connections enabled is required. Disconnect BLE Scanner or another phone app before testing Home Assistant's connection.

If BLE-YC01 is already configured, update the files through HACS and restart Home Assistant. The integration domain and existing measurement entity IDs are preserved. This version replaces the earlier connect/disconnect experiment; there is no wake-up interval setting.

## Measurement interval

Set **Data polling interval (minutes)** when adding the device, or change it later under **Settings > Devices & services > BLE-YC01 > Configure**. Enter a positive whole number of minutes. The default is **30 minutes**, including for existing installations.

Saving a different interval starts the new countdown immediately without reading measurements or interrupting the Bluetooth connection. For example, selecting 5 minutes schedules the next read in 5 minutes and repeats every 5 minutes. The connection remains open between readings. Turning off **Enable polling for updates** still disables scheduled reads.

## Manual refresh

Press the device's **Refresh** button to read measurements immediately over the existing Bluetooth connection. Each press restarts the polling countdown from the time you pressed it. For example, with a 30-minute interval, pressing Refresh 15 minutes after the last read updates the data now and schedules the next read 30 minutes after the press.

The button also works when **Enable polling for updates** is turned off, performing one read without enabling scheduled polling. A failed read reports an error; the button is unavailable while Bluetooth is disconnected.

## Development

I run the tests on Linux with Python 3.14:

```sh
python -m pip install -r requirements-test.txt
python -m pytest
ruff check .
ruff format --check .
```

The tests run Home Assistant with mocked Bluetooth transport. Keeping this device awake through a persistent proxy connection still needs physical testing.

## Credits

This fork is based on [jdeath/BLE-YC01](https://github.com/jdeath/BLE-YC01). The original decoding work came from @anasm2010, @RubenKona, and contributors to the [Home Assistant community discussion](https://community.home-assistant.io/t/pool-monitor-device-yieryi-ble-yc01).
