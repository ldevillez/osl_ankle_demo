"""Interactive low-impedance demo for the OSL ankle.

Two modes, both with a soft impedance controller so people can push the foot:

- hold: equilibrium at 0 deg
- oscillate: equilibrium follows a slow sine between -10 and +10 deg

Each mode has its own stiffness (oscillate needs more, to beat friction).

Keys while running: ``h`` hold, ``o`` oscillate, ``+``/``-`` stiffness of the current mode, ``q`` quit.
"""

import argparse
import math
import os
import select
import sys
import termios
import time
import tty

from osl_ankle_demo.config import DEFAULT_CONFIG, MAX_STIFFNESS, MODES, load_config
from osl_ankle_demo.hardware import enter_impedance_mode, find_port_on_bus, home_ankle, make_ankle_actuator

LOOP_FREQUENCY = 200.0  # Hz
STATUS_FREQUENCY = 5.0  # Hz

# Safety limits (stiffness and damping limits are in config.py)
MAX_EQUILIBRIUM = math.radians(15.0)  # rad, |equilibrium| never exceeds this
MAX_EQUILIBRIUM_SPEED = math.radians(30.0)  # rad/s, smooths start-up and mode changes
MAX_STIFFNESS_RATE = 40.0  # Nm/rad per s, smooths stiffness changes
MIN_PERIOD = 2.0  # s
MAX_ANGLE = math.radians(40.0)  # rad, beyond this the homing is wrong: stop

HOLD, OSCILLATE = MODES


class Keyboard:
    """Non-blocking single-key reader; does nothing when stdin is not a terminal."""

    def __enter__(self):
        self.enabled = sys.stdin.isatty()
        if self.enabled:
            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)  # keys arrive without Enter, Ctrl+C still works
        return self

    def __exit__(self, *exc):
        if self.enabled:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)

    def keys(self) -> str:
        """Return the keys pressed since the last call."""
        if not self.enabled or not select.select([self._fd], [], [], 0)[0]:
            return ""
        return os.read(self._fd, 32).decode(errors="ignore")


def target_angle(mode: str, t: float, amplitude: float, period: float) -> float:
    """Equilibrium requested by a mode, in rad.

    Parameters
    ----------
    t : float
        Time since the mode started, in s.
    amplitude : float
        Oscillation amplitude, in rad.
    period : float
        Oscillation period, in s.
    """
    if mode == OSCILLATE:
        return amplitude * math.sin(2 * math.pi * t / period)
    return 0.0


def step_towards(current: float, target: float, max_step: float) -> float:
    """Move ``current`` towards ``target`` by at most ``max_step``."""
    return current + max(-max_step, min(max_step, target - current))


def clamp(value: float, low: float, high: float) -> float:
    """Limit ``value`` to [low, high]."""
    return max(low, min(high, value))


def parse_args(argv=None) -> argparse.Namespace:
    """Read the command-line options."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=[HOLD, OSCILLATE], default=HOLD, help="starting mode (default: hold)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="settings, YAML (default: the packaged config.yaml)")
    parser.add_argument("-k", "--hold-stiffness", type=float, help="hold stiffness in Nm/rad, overrides the config")
    parser.add_argument(
        "-K", "--oscillate-stiffness", type=float, help="oscillate stiffness in Nm/rad, overrides the config"
    )
    parser.add_argument("-b", "--damping", type=float, help="damping in Nm s/rad, overrides the config")
    parser.add_argument("--amplitude", type=float, default=10.0, help="oscillation amplitude in deg (default: 10)")
    parser.add_argument("--period", type=float, default=4.0, help="oscillation period in s (default: 4)")
    parser.add_argument("--port", help="actpack serial port, overrides the config")
    args = parser.parse_args(argv)

    try:
        args.settings = load_config(args.config)
        if args.hold_stiffness is not None:
            args.settings.impedance.stiffness[HOLD] = args.hold_stiffness
        if args.oscillate_stiffness is not None:
            args.settings.impedance.stiffness[OSCILLATE] = args.oscillate_stiffness
        if args.damping is not None:
            args.settings.impedance.damping = args.damping
        args.settings.check()
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))

    if not 0 <= math.radians(args.amplitude) <= MAX_EQUILIBRIUM:
        parser.error(f"amplitude must be between 0 and {math.degrees(MAX_EQUILIBRIUM):g} deg")
    if args.period < MIN_PERIOD:
        parser.error(f"period must be at least {MIN_PERIOD:g} s")
    return args


def find_port(port: str | None, usb_bus: str | None) -> str | None:
    """Return the actpack serial port, or None after explaining why it was not found.

    A given ``port`` must exist: it never falls back to the bus search, which
    could pick another actpack.
    """
    if port is not None:
        if os.path.exists(port):
            return os.path.realpath(port)
        print(f"Actpack port {port} does not exist. Is it plugged in and powered? Check `ls /dev/serial/by-id/`.")
        return None

    found = find_port_on_bus(usb_bus)
    if found is None:
        print(
            f"No actpack found on USB bus {usb_bus}. Is it plugged in and powered? "
            "Set actuator.port in the config or pass --port."
        )
    return found


def run(args: argparse.Namespace) -> int:
    """Home the ankle, then run the impedance demo until the user quits."""
    port = find_port(args.port or args.settings.actuator.port, args.settings.actuator.usb_bus)
    if port is None:
        return 1
    print(f"Ankle actpack on {port}")

    actuator = make_ankle_actuator(port)
    actuator.start()
    try:
        if not home_ankle(actuator):
            print("Homing did not complete, stopping.")
            return 1

        impedance = args.settings.impedance
        stiffness_per_mode = dict(impedance.stiffness)  # targets, changed with +/-
        damping = impedance.damping
        amplitude, period = math.radians(args.amplitude), args.period
        mode = args.mode
        # Start at the mode's stiffness: the equilibrium starts at the current
        # angle, so there is no torque jump
        stiffness = stiffness_per_mode[mode]
        equilibrium = enter_impedance_mode(actuator, stiffness, damping, impedance.current_gains)

        print(
            "\nRunning. Keys: [h] hold at 0 deg  [o] oscillate  [+/-] stiffness of this mode  [q] quit (or Ctrl+C)\n"
        )

        dt = 1.0 / LOOP_FREQUENCY
        max_step = MAX_EQUILIBRIUM_SPEED * dt
        max_stiffness_step = MAX_STIFFNESS_RATE * dt
        status_every = int(LOOP_FREQUENCY / STATUS_FREQUENCY)
        mode_start = time.perf_counter()
        next_tick = mode_start
        tick = 0

        with Keyboard() as keyboard:
            while True:
                # Keyboard
                for key in keyboard.keys():
                    if key == "q":
                        return 0
                    if key in "ho":
                        new_mode = HOLD if key == "h" else OSCILLATE
                        if new_mode != mode:
                            mode, mode_start = new_mode, time.perf_counter()
                    elif key in "+=-_":
                        change = impedance.stiffness_step if key in "+=" else -impedance.stiffness_step
                        stiffness_per_mode[mode] = clamp(stiffness_per_mode[mode] + change, 0.0, MAX_STIFFNESS)

                # Stiffness ramps to the current mode's value, never jumps
                new_stiffness = step_towards(stiffness, stiffness_per_mode[mode], max_stiffness_step)
                if new_stiffness != stiffness:
                    stiffness = new_stiffness
                    actuator.set_output_impedance(k=stiffness, b=damping)

                # Control
                actuator.update()
                angle = actuator.output_position
                if abs(angle) > MAX_ANGLE:
                    print(f"\nAnkle at {math.degrees(angle):.0f} deg: outside the expected range, stopping.")
                    return 1

                # Clamp the target, not the equilibrium: at start-up the equilibrium
                # begins at the homing stop and must ramp from there, never jump
                target = target_angle(mode, time.perf_counter() - mode_start, amplitude, period)
                target = clamp(target, -MAX_EQUILIBRIUM, MAX_EQUILIBRIUM)
                equilibrium = step_towards(equilibrium, target, max_step)
                actuator.set_output_position(equilibrium)

                # Status line
                if tick % status_every == 0:
                    sys.stdout.write(
                        f"\r{mode:<9}  K {stiffness:5.1f} (target {stiffness_per_mode[mode]:5.1f}) Nm/rad  "
                        f"B {damping:.2f} Nm s/rad  "
                        f"eq {math.degrees(equilibrium):+5.1f} deg  angle {math.degrees(angle):+5.1f} deg  "
                        f"case {actuator.case_temperature:4.1f} °C "
                    )
                    sys.stdout.flush()
                tick += 1

                # Fixed rate
                next_tick += dt
                delay = next_tick - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.perf_counter()
    except KeyboardInterrupt:
        return 0
    finally:
        print("\nStopping the actuator (the ankle goes limp).")
        actuator.stop()


def main(argv=None) -> None:
    """Entry point of ``osl-ankle-demo``."""
    sys.exit(run(parse_args(argv)))


if __name__ == "__main__":
    main()
