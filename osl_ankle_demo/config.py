"""Load and check the demo settings from a YAML file."""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")

# Safety limits: kept in code so a config file cannot raise them
MAX_STIFFNESS = 100.0  # Nm/rad
MAX_DAMPING = 3.0  # Nm s/rad

GAIN_NAMES = ("kp", "ki", "kd", "ff")
MODES = ("hold", "oscillate")


@dataclass
class ActuatorConfig:
    """How to find the ankle actpack.

    Parameters
    ----------
    port : str | None
        Serial port, e.g. a ``/dev/serial/by-id/...`` link. Used first when set.
    usb_bus : str | None
        USB bus number to search when ``port`` is not set.
    """

    port: str | None
    usb_bus: str | None

    def check(self) -> None:
        """Raise ValueError if neither way of finding the actpack is set."""
        if self.port is None and self.usb_bus is None:
            raise ValueError("actuator: set port or usb_bus")


@dataclass
class ImpedanceConfig:
    """Impedance settings of the demo.

    Parameters
    ----------
    stiffness : dict[str, float]
        Joint stiffness for each mode (``hold``, ``oscillate``), in Nm/rad.
    damping : float
        Joint damping, in Nm s/rad.
    stiffness_step : float
        Stiffness change per key press, in Nm/rad.
    current_gains : dict[str, int]
        Current-loop gains ``kp``, ``ki``, ``kd``, ``ff`` used in impedance mode, in actpack units.
    """

    stiffness: dict[str, float]
    damping: float
    stiffness_step: float
    current_gains: dict[str, int]

    def check(self) -> None:
        """Raise ValueError if a setting is outside its safe range."""
        if set(self.stiffness) != set(MODES):
            raise ValueError(f"stiffness must have exactly {', '.join(MODES)}")
        for mode, value in self.stiffness.items():
            if not 0 <= value <= MAX_STIFFNESS:
                raise ValueError(f"stiffness.{mode} must be between 0 and {MAX_STIFFNESS:g} Nm/rad, got {value:g}")
        if not 0 <= self.damping <= MAX_DAMPING:
            raise ValueError(f"damping must be between 0 and {MAX_DAMPING:g} Nm s/rad, got {self.damping:g}")
        if not 0 < self.stiffness_step <= MAX_STIFFNESS:
            raise ValueError(f"stiffness_step must be between 0 and {MAX_STIFFNESS:g} Nm/rad, got {self.stiffness_step:g}")
        if set(self.current_gains) != set(GAIN_NAMES):
            raise ValueError(f"current_gains must have exactly {', '.join(GAIN_NAMES)}")
        for name, value in self.current_gains.items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"current_gains.{name} must be a non-negative integer, got {value!r}")


@dataclass
class Config:
    """All settings of the demo."""

    actuator: ActuatorConfig
    impedance: ImpedanceConfig

    def check(self) -> None:
        """Raise ValueError if a setting is invalid."""
        self.actuator.check()
        self.impedance.check()


def _section(data: dict, name: str, keys: set[str], where: str) -> dict:
    """Return ``data[name]`` after checking it has exactly ``keys``."""
    section = data.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"{where}: missing section {name}")
    if missing := keys - section.keys():
        raise ValueError(f"{where}: {name}: missing {', '.join(sorted(missing))}")
    if unknown := section.keys() - keys:
        raise ValueError(f"{where}: {name}: unknown {', '.join(sorted(unknown))}")
    return section


def load_config(path: str | Path = DEFAULT_CONFIG) -> Config:
    """Read the settings from a YAML file and check them.

    Raises ValueError if a section or key is missing, unknown or out of range.
    """
    with open(path, encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if unknown := data.keys() - {"actuator", "impedance"}:
        raise ValueError(f"{path}: unknown section {', '.join(sorted(unknown))}")
    actuator = _section(data, "actuator", {"port", "usb_bus"}, path)
    impedance = _section(data, "impedance", {"stiffness", "damping", "stiffness_step", "current_gains"}, path)

    config = Config(
        actuator=ActuatorConfig(
            port=None if actuator["port"] is None else str(actuator["port"]),
            usb_bus=None if actuator["usb_bus"] is None else str(actuator["usb_bus"]),
        ),
        impedance=ImpedanceConfig(
            stiffness={mode: float(value) for mode, value in dict(impedance["stiffness"] or {}).items()},
            damping=float(impedance["damping"]),
            stiffness_step=float(impedance["stiffness_step"]),
            current_gains=dict(impedance["current_gains"] or {}),
        ),
    )
    config.check()
    return config
