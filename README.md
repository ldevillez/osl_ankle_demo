# OSL ankle demo

Interactive demo for the [Open Source Leg](https://opensourceleg.org/) ankle. The ankle runs a soft impedance controller so people can safely push the foot around.

Two modes:

- **hold**: the ankle springs back to 0 deg.
- **oscillate**: the equilibrium follows a slow sine between -10 and +10 deg.

The stiffness can be changed while it runs.

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
uv run osl-ankle-demo -k 10 -b 0.3           # softer, overrides config.yaml
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
| `+` / `-` | stiffness up / down by `stiffness_step` (5 Nm/rad) |
| `q` or Ctrl+C | quit (the ankle goes limp) |

## Impedance settings

The impedance settings are in [`osl_ankle_demo/config.yaml`](osl_ankle_demo/config.yaml):

| Key | Default | Limit |
|-----|---------|-------|
| `stiffness`, expressed in Nm/rad | 20 | 0 to 100 |
| `damping`, expressed in Nm s/rad | 0.5 | 0 to 3 |
| `stiffness_step`, change per key press, expressed in Nm/rad | 5 | above 0, up to 100 |
| `current_gains` (`kp`, `ki`, `kd`, `ff`), current loop in impedance mode, actpack units | 140, 150, 0, 120 | non-negative integers |

Edit that file, or copy it and pass `--config my_ankle.yaml`. The file is checked at start-up: a missing, misspelled or out-of-range key stops the demo with an error. The limits are set in the code, not in the file.

## Other options

| Option | Default | Limit |
|--------|---------|-------|
| `--stiffness`, `-k`, overrides the config, expressed in Nm/rad | from config | 0 to 100 |
| `--damping`, `-b`, overrides the config, expressed in Nm s/rad | from config | 0 to 3 |
| `--amplitude`, expressed in deg | 10 | 0 to 15 |
| `--period`, expressed in s | 4 | at least 2 |
| `--port` | found on USB bus 2 | |

Safety:

- The equilibrium moves at most 30 deg/s, so start-up and mode changes are smooth.
- The equilibrium never leaves ±15 deg.
- If the ankle reads beyond ±40 deg (wrong homing), the demo stops.
- Exiting, a thermal fault or any error stops the motor.

## How it finds the actuator

The ankle actpack is the serial device on USB bus 2 of the Pi (the knee is on bus 4), as in [opensourceleg-ros2](https://github.com/ldevillez/opensourceleg-ros2). If it is plugged elsewhere, pass `--port /dev/ttyACM0` (list ports with `ls /dev/ttyACM*`).

The ankle torque constant (0.145 Nm/A) replaces the library default (0.1133 Nm/A), so stiffness and damping are in true joint units.
