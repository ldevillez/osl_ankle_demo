"""Interactive low-impedance demo for the OSL ankle.

Two modes, both with a soft impedance controller so people can push the foot:

- hold: equilibrium at 0 deg
- oscillate: equilibrium follows a slow sine between -10 and +10 deg

Keys while running: ``h`` hold, ``o`` oscillate, ``+``/``-`` stiffness, ``q`` quit.
"""

import argparse
import math
import os
import select
import sys
import termios
import time
import tty

from osl_ankle_demo.config import DEFAULT_CONFIG, MAX_STIFFNESS, load_config
from osl_ankle_demo.hardware import enter_impedance_mode, find_ankle_port, home_ankle, make_ankle_actuator

LOOP_FREQUENCY = 200.0  # Hz
STATUS_FREQUENCY = 5.0  # Hz

# Safety limits (stiffness and damping limits are in config.py)
MAX_EQUILIBRIUM = math.radians(15.0)  # rad, |equilibrium| never exceeds this
MAX_EQUILIBRIUM_SPEED = math.radians(30.0)  # rad/s, smooths start-up and mode changes
MIN_PERIOD = 2.0  # s
MAX_ANGLE = math.radians(40.0)  # rad, beyond this the homing is wrong: stop

HOLD = "hold"
OSCILLATE = "oscillate"


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
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="impedance settings, YAML (default: the packaged config.yaml)")
    parser.add_argument("-k", "--stiffness", type=float, help="stiffness in Nm/rad, overrides the config")
    parser.add_argument("-b", "--damping", type=float, help="damping in Nm s/rad, overrides the config")
    parser.add_argument("--amplitude", type=float, default=10.0, help="oscillation amplitude in deg (default: 10)")
    parser.add_argument("--period", type=float, default=4.0, help="oscillation period in s (default: 4)")
    parser.add_argument("--port", help="actpack serial port (default: found from the USB bus)")
    args = parser.parse_args(argv)

    try:
        args.impedance = load_config(args.config)
        if args.stiffness is not None:
            args.impedance.stiffness = args.stiffness
        if args.damping is not None:
            args.impedance.damping = args.damping
        args.impedance.check()
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))

    if not 0 <= math.radians(args.amplitude) <= MAX_EQUILIBRIUM:
        parser.error(f"amplitude must be between 0 and {math.degrees(MAX_EQUILIBRIUM):g} deg")
    if args.period < MIN_PERIOD:
        parser.error(f"period must be at least {MIN_PERIOD:g} s")
    return args


def run(args: argparse.Namespace) -> int:
    """Home the ankle, then run the impedance demo until the user quits."""
    port = args.port or find_ankle_port()
    if port is None:
        print("Ankle actpack not found on its USB bus. Is it plugged in and powered? Use --port to force one.")
        return 1
    print(f"Ankle actpack on {port}")

    actuator = make_ankle_actuator(port)
    actuator.start()
    try:
        if not home_ankle(actuator):
            print("Homing did not complete, stopping.")
            return 1

        impedance = args.impedance
        stiffness, damping = impedance.stiffness, impedance.damping
        amplitude, period = math.radians(args.amplitude), args.period
        mode = args.mode
        equilibrium = enter_impedance_mode(actuator, stiffness, damping, impedance.current_gains)

        print(
            "\nRunning. Keys: [h] hold at 0 deg  [o] oscillate  [+/-] stiffness  [q] quit (or Ctrl+C)\n"
        )

        dt = 1.0 / LOOP_FREQUENCY
        max_step = MAX_EQUILIBRIUM_SPEED * dt
        status_every = int(LOOP_FREQUENCY / STATUS_FREQUENCY)
        mode_start = time.perf_counter()
        next_tick = mode_start
        tick = 0

        with Keyboard() as keyboard:
            while True:
                # Keyboard
                new_stiffness = stiffness
                for key in keyboard.keys():
                    if key == "q":
                        return 0
                    if key in "ho":
                        new_mode = HOLD if key == "h" else OSCILLATE
                        if new_mode != mode:
                            mode, mode_start = new_mode, time.perf_counter()
                    elif key in "+=":
                        new_stiffness += impedance.stiffness_step
                    elif key in "-_":
                        new_stiffness -= impedance.stiffness_step
                new_stiffness = clamp(new_stiffness, 0.0, MAX_STIFFNESS)
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
                        f"\r{mode:<9}  K {stiffness:5.1f} Nm/rad  B {damping:.2f} Nm s/rad  "
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
