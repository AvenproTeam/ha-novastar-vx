# Changelog

## 1.0.1 – 2026-11-25

- Screen map card: takes the full width by default in Sections views.
- Screen map card: visual editor (controller, title, default view, hide labels).
- Screen map card: `hide_labels` replaces `labels` (the old `labels: false` still works).

## 1.0.0 – 2026-11-25

First release.

- Set up NovaStar controllers from the UI; outputs and receiving cards are found automatically.
- Per card: temperature, voltage and problem (offline / over temperature).
- Per output and for the whole screen: cards online, highest temperature, lowest voltage, problem.
- Running on backup, for outputs with a backup configured.
- Live screen map Lovelace card, loaded automatically: every cabinet in its real position, green / yellow / red, details on tap, front and back view.
- Options: update interval, temperature alarm, per-card entities on/off, rescan outputs. Reconfigure to change the address.
- Diagnostics download.
- English, Spanish and Catalan translations.
