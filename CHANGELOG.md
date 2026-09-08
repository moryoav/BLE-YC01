# Changelog

## 1.6.0

- Added a diagnostic Bluetooth RSSI sensor in dBm using the last advertisement from a connectable scanner.
- Included the reporting source and original observation timestamp to identify potentially stale readings.
- Updated signal strength passively without changing the persistent connection or measurement schedule.

## 1.5.0

- Added an Estimated Bromine sensor in ppm, calculated as the chlorine reading multiplied by 2.25.
- Updated the estimate with each measurement read without additional Bluetooth traffic.

## 1.4.0

- Added a Refresh button to read measurements immediately without disconnecting.
- Restarted the polling countdown from each button press, replacing the previous scheduled read.
- Allowed manual reads while automatic polling is disabled.

## 1.3.0

- Added a data polling interval in minutes during setup and through Configure, defaulting to 30 minutes.
- Applied interval changes without reloading the integration, disconnecting, or reading measurements immediately.
- Preserved the 30-minute default for existing installations.

## 1.2.0

- Added a persistent Bluetooth connection to keep the device connected between measurements.
- Preserved the original FF02 measurement decoding and 30-minute polling interval.
- Added immediate reconnection after disconnects and 5-second retries without extra measurement reads.
- Added connection cleanup on setup failure, unload, and shutdown.
- Removed temporary connection probes from discovery and preserved existing measurement entity IDs.
