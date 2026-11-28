# Changelog

## 1.1.0 – Unreleased

- **Control** (new, off by default; turn on "Allow control" in the options): input source, display mode (normal / freeze / black) with freeze and black-out switches, brightness (0–100 %), picture in picture and front-panel lock. Commands come from NovaStar's own VX4S protocol sheet and are **untested on a real VX1000**.
- Control entities show the value read back from the controller on each poll. Nothing is written until you use one of them.
- Diagnostics include the raw control register values.

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
