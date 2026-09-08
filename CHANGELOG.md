# Changelog

## 1.1.0

- Replaced the fixed 30-minute measurement polling with a per-device keep-alive interval in Configure, defaulting to 4 minutes.
- Replaced characteristic reads with a connection followed immediately by a disconnect.
- Removed FF02 reads from discovery and setup.
- Added a last-successful-keep-alive diagnostic timestamp and kept existing measurement entities unavailable with their original IDs.
- Added interval validation, automatic reload on changes, serialized connections, bounded cleanup, and regression tests.
