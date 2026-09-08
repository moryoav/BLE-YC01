# Changelog

## 1.2.0

- Added a persistent Bluetooth connection to keep the device connected between measurements.
- Preserved the original FF02 measurement decoding and 30-minute polling interval.
- Added immediate reconnection after disconnects and 5-second retries without extra measurement reads.
- Added connection cleanup on setup failure, unload, and shutdown.
- Removed temporary connection probes from discovery and preserved existing measurement entity IDs.
