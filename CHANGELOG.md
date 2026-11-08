# Changelog

## 1.0.0 — 2026-11-08

Breaking change: QBO requests no longer silently select Envision or read
QBO_COMPANY. Both client variants require an explicit company for get_access,
query and post; missing/empty values fail before I/O. Existing explicit calls
remain compatible.

Scripts may explicitly select environment configuration with from_env(),
which validates QBO_COMPANY and logs the selected name at INFO. Pass the
returned name to each request. All five existing companies remain supported.

See README.md for migration examples and docs/caller-inventory.md for the
read-only local caller inventory. This major bump replaces 0.1.0.
