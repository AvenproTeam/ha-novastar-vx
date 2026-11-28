# Contributing

Thanks for helping! Bug reports, captures from other controllers, translations and pull requests are all welcome.

## Reporting a bug or a new controller model

Open an [issue](https://github.com/AvenproTeam/ha-novastar-vx/issues/new/choose) and include:

- your Home Assistant version and the integration version,
- the controller model and firmware, and the receiving card model (NovaLCT shows both),
- the diagnostics file from the controller's device page (**Download diagnostics**),
- debug logs if you have them (see the README's Troubleshooting section).

**Especially useful:** a diagnostics file captured *while an output is running on backup*, or while a monitoring card or smart module is fitted. Those are the cases we couldn't test.

## Development setup

You need Python 3.13 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The tests use a small fake controller (`tests/fake_device.py`) that speaks the real protocol on localhost, so you don't need hardware to run them.

To try your changes in a real Home Assistant, copy `custom_components/novastar_vx` into the `custom_components` folder of a test instance and restart it.

## Code layout

| File | What it does |
| --- | --- |
| `protocol.py` | The NovaStar TCP protocol: framing, register addresses, decoding. Standard library only, so you can use it on its own. |
| `coordinator.py` | Polls the controller. |
| `config_flow.py` | Setup, reconfigure and options screens. |
| `entity.py` | Devices and the shared status logic (what counts as a problem or a warning). |
| `sensor.py`, `binary_sensor.py` | Monitoring entities. |
| `select.py`, `switch.py`, `number.py` | Control entities. Created only when "Allow control" is on. |
| `websocket.py` | Feeds the screen map card. |
| `frontend/novastar-screen-card.js` | The screen map card. Plain JavaScript, no build step. |
| `translations/` | UI text. Add a `<language>.json` copied from `en.json` to add a language. |
| `brand/` | Icon shown in Home Assistant. |

## Pull requests

- Keep changes focused; one feature or fix per pull request.
- Add or update tests for what you change.
- Run `ruff check` and `ruff format` before you push.
- If you add a text the user sees, add it to every file in `translations/`.
- **Monitoring must stay read-only.** Only the control entities (`select.py`, `switch.py`, `number.py`) may write, and only when the user turned on "Allow control". Never write from a poll, a setup step or a test against a real device.

## The protocol in short

Requests are sent over TCP port 5200. All multi-byte fields are little endian:

```
55 AA | ack | serial | FE | dst | device type | output | card index (2) | code | 00 | address (4) | length (2) | data | checksum (2)
```

Device type 0 is the sending card, 1 a receiving card. The code is 0 to read and 1 to write; the integration only reads. The checksum is the sum of every byte after `55 AA`, plus `0x5555`, truncated to 16 bits. Replies start with `AA 55` and have the same layout; `ack` is 0 on success. A receiving card index that doesn't exist gets a non-zero `ack`, which is how cards are discovered.

| Register | Device | What |
| --- | --- | --- |
| `0x00000002` | sender / card | Model id (2 bytes) |
| `0x0A000000` | card | Monitoring block (82 bytes): temperature, humidity, voltage, module status, monitoring card data |
| `0x020000B1` | sender | Per output: width, height, x, y (4 × u16) + 1 spare byte |
| `0x03000000 + output × 0x1000` | sender | Per card: x, y (u16) inside the output |
| `0x02000017` | card | Width, height (u16) of the area the card drives |
| `0x02300000` | sender | Backup table: main → backup output pairs |
| `0x02000098` | sender | Redundancy state, one byte per output (bit 7 = valid, low bits 0 = OK) |

The addresses come from [sarakusha/novastar](https://github.com/sarakusha/novastar), which reverse-engineered NovaLCT's address map.
