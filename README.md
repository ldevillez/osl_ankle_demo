# OSL ankle demo

Interactive demo for the [Open Source Leg](https://opensourceleg.org/) ankle. The ankle runs a soft impedance controller so people can safely push the foot around.

Two modes:

- **hold**: the ankle springs back to 0 deg.
- **oscillate**: the equilibrium follows a slow sine between -10 and +10 deg.

Each mode has its own stiffness: hold is soft so people can push the foot, oscillate is stiffer so the foot actually moves despite friction. Both can be changed while it runs.

## Install on the OSL

On the Raspberry Pi, with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

It installs Python 3.11 if needed and creates the environment from `uv.lock`.

Your user needs access to the actpack serial port (once, then log out and back in):

```bash
sudo usermod -aG dialout $USER
```

## Run

```bash
uv run osl-ankle-demo                        # hold mode, settings from config.yaml
uv run osl-ankle-demo --mode oscillate       # start oscillating
uv run osl-ankle-demo -k 10 -K 70 -b 0.3     # hold K, oscillate K and B, override config.yaml
uv run osl-ankle-demo --config my_ankle.yaml # another settings file
uv run osl-ankle-demo --help                 # all options
```

1. The demo first **homes** the ankle: it asks you to press Enter, then drives the foot slowly to its hard stop. Keep hands clear.
2. The ankle then moves smoothly to 0 deg and the demo starts.

Keys while running:

| Key | Action |
|-----|--------|
| `h` | hold at 0 deg |
| `o` | oscillate between -10 and +10 deg |
| `+` / `-` | stiffness of the current mode up / down by `stiffness_step` (5 Nm/rad) |
| `q` or Ctrl+C | quit (the ankle goes limp) |

## Settings

The settings are in [`osl_ankle_demo/config.yaml`](osl_ankle_demo/config.yaml), in two sections.

`actuator`, how to find the ankle actpack (see [below](#how-it-finds-the-actuator)):

| Key | Default |
|-----|---------|
| `port`, e.g. `/dev/serial/by-id/usb-...` | `null` (not set) |
| `usb_bus`, searched when `port` is not set | 2 (CM5 + interface board) |

`impedance`:

| Key | Default | Limit |
|-----|---------|-------|
| `stiffness.hold`, expressed in Nm/rad | 20 | 0 to 100 |
| `stiffness.oscillate`, expressed in Nm/rad | 60 | 0 to 100 |
| `damping`, expressed in Nm s/rad | 0.5 | 0 to 3 |
| `stiffness_step`, change per key press, expressed in Nm/rad | 5 | above 0, up to 100 |
| `current_gains` (`kp`, `ki`, `kd`, `ff`), current loop in impedance mode, actpack units | 140, 150, 0, 120 | non-negative integers |

Edit that file, or copy it and pass `--config my_ankle.yaml` (handy for one file per OSL). The file is checked at start-up: a missing, misspelled or out-of-range key stops the demo with an error. The limits are set in the code, not in the file.

## Other options

| Option | Default | Limit |
|--------|---------|-------|
| `--hold-stiffness`, `-k`, overrides the config, expressed in Nm/rad | from config | 0 to 100 |
| `--oscillate-stiffness`, `-K`, overrides the config, expressed in Nm/rad | from config | 0 to 100 |
| `--damping`, `-b`, overrides the config, expressed in Nm s/rad | from config | 0 to 3 |
| `--amplitude`, expressed in deg | 10 | 0 to 15 |
| `--period`, expressed in s | 4 | at least 2 |
| `--port`, overrides the config | from config | |

Safety:

- The equilibrium moves at most 30 deg/s, so start-up and mode changes are smooth.
- The stiffness changes by at most 40 Nm/rad per second, including when switching mode.
- The equilibrium never leaves ±15 deg.
- If the ankle reads beyond ±40 deg (wrong homing), the demo stops.
- Exiting, a thermal fault or any error stops the motor.

## How it finds the actuator

In order:

1. `--port` on the command line.
2. `actuator.port` in the config.
3. The actpack on USB bus `actuator.usb_bus`, as in [opensourceleg-ros2](https://github.com/ldevillez/opensourceleg-ros2).

A port set with 1 or 2 must exist: the demo stops instead of searching, so it never picks the knee by mistake.

**CM5 with the interface board:** keep `usb_bus: 2`. Each connector has its own bus (ankle on 2, knee on 4).

**Regular Raspberry Pi:** two USB ports share each bus, so set `port` instead. With the ankle actpack plugged in and powered:

```bash
ls -l /dev/serial/by-id/     # name tied to the actpack: works in any USB port
ls -l /dev/serial/by-path/   # name tied to the USB port: the ankle must always use that port
```

Copy one of the names into `actuator.port`, e.g. `port: /dev/serial/by-id/usb-...`.

The ankle torque constant (0.145 Nm/A) replaces the library default (0.1133 Nm/A), so stiffness and damping are in true joint units.
