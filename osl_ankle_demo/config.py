"""Load and check the impedance settings from a YAML file."""

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")

# Safety limits: kept in code so a config file cannot raise them
MAX_STIFFNESS = 100.0  # Nm/rad
MAX_DAMPING = 3.0  # Nm s/rad

GAIN_NAMES = ("kp", "ki", "kd", "ff")


@dataclass
class ImpedanceConfig:
    """Impedance settings of the demo.

    Parameters
    ----------
    stiffness : float
        Joint stiffness, in Nm/rad.
    damping : float
        Joint damping, in Nm s/rad.
    stiffness_step : float
        Stiffness change per key press, in Nm/rad.
    current_gains : dict[str, int]
        Current-loop gains ``kp``, ``ki``, ``kd``, ``ff`` used in impedance mode, in actpack units.
    """

    stiffness: float
    damping: float
    stiffness_step: float
    current_gains: dict[str, int]

    def check(self) -> None:
        """Raise ValueError if a setting is outside its safe range."""
        if not 0 <= self.stiffness <= MAX_STIFFNESS:
            raise ValueError(f"stiffness must be between 0 and {MAX_STIFFNESS:g} Nm/rad, got {self.stiffness:g}")
        if not 0 <= self.damping <= MAX_DAMPING:
            raise ValueError(f"damping must be between 0 and {MAX_DAMPING:g} Nm s/rad, got {self.damping:g}")
        if not 0 < self.stiffness_step <= MAX_STIFFNESS:
            raise ValueError(f"stiffness_step must be between 0 and {MAX_STIFFNESS:g} Nm/rad, got {self.stiffness_step:g}")
        if set(self.current_gains) != set(GAIN_NAMES):
            raise ValueError(f"current_gains must have exactly {', '.join(GAIN_NAMES)}")
        for name, value in self.current_gains.items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"current_gains.{name} must be a non-negative integer, got {value!r}")


def load_config(path: str | Path = DEFAULT_CONFIG) -> ImpedanceConfig:
    """Read the impedance settings from a YAML file and check them.

    Raises ValueError if a key is missing, unknown or out of range.
    """
    with open(path, encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    expected = {"stiffness", "damping", "stiffness_step", "current_gains"}
    if missing := expected - data.keys():
        raise ValueError(f"{path}: missing {', '.join(sorted(missing))}")
    if unknown := data.keys() - expected:
        raise ValueError(f"{path}: unknown {', '.join(sorted(unknown))}")

    config = ImpedanceConfig(
        stiffness=float(data["stiffness"]),
        damping=float(data["damping"]),
        stiffness_step=float(data["stiffness_step"]),
        current_gains=dict(data["current_gains"] or {}),
    )
    config.check()
    return config
