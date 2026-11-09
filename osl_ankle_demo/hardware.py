"""Hardware helpers for the OSL ankle, adapted from opensourceleg-ros2."""

import dataclasses

import numpy as np
import pyudev
from opensourceleg.actuators.base import CONTROL_MODES
from opensourceleg.actuators.dephy import DEPHY_ACTUATOR_CONSTANTS, DephyActuator

# Transmission: 9:1 planetary gearbox and 83:18 belt
GEAR_RATIO = 9.0 * 83.0 / 18.0

# Torque constant of the ankle motor, in Nm/A (the library default, 0.1133, is the old knee motor)
NM_PER_AMP_ANKLE = 0.1450

# Vendor ID of Linux USB root hubs (Linux Foundation), skipped when searching a bus
USB_ROOT_HUB_VENDOR = "1d6b"

# Joint angle at the homing hard stop, in rad
HOMING_STOP_ANGLE = np.deg2rad(30.0)


def find_port_on_bus(bus: str) -> str | None:
    """Return the serial port of the actpack plugged on a USB bus, or None if absent.

    Parameters
    ----------
    bus : str
        USB bus number, as reported by ``lsusb``.
    """
    for device in pyudev.Context().list_devices(subsystem="tty"):
        usb = device.find_parent("usb", "usb_device")
        if usb is None:
            continue
        busnum = usb.attributes.get("busnum")
        vendor = usb.attributes.get("idVendor")
        if busnum and busnum.decode() == bus and vendor and vendor.decode() != USB_ROOT_HUB_VENDOR:
            return device.device_node
    return None


def make_ankle_actuator(port: str) -> DephyActuator:
    """Create the ankle actuator with the ankle torque constant.

    Replacing ``MOTOR_CONSTANTS`` also updates the library's impedance
    unit conversions, so stiffness and damping are correct in Nm/rad.
    """
    actuator = DephyActuator(
        tag="ankle",
        port=port,
        gear_ratio=GEAR_RATIO,
        debug_level=0,
        dephy_log=False,
    )
    actuator.MOTOR_CONSTANTS = dataclasses.replace(DEPHY_ACTUATOR_CONSTANTS, NM_PER_AMP=NM_PER_AMP_ANKLE)
    return actuator


def home_ankle(actuator: DephyActuator) -> bool:
    """Drive the ankle to its hard stop and set 0 rad at the neutral angle.

    Asks the operator to press Enter first. Returns True if homing completed.
    """
    actuator.home(output_position_offset=HOMING_STOP_ANGLE)
    return actuator.is_homed


def enter_impedance_mode(
    actuator: DephyActuator, stiffness: float, damping: float, current_gains: dict[str, int]
) -> float:
    """Switch to impedance mode, holding the current angle.

    Parameters
    ----------
    stiffness : float
        Joint stiffness, in Nm/rad.
    damping : float
        Joint damping, in Nm s/rad.
    current_gains : dict[str, int]
        Current-loop gains ``kp``, ``ki``, ``kd``, ``ff``, in actpack units.

    Returns
    -------
    float
        Joint angle at the switch, in rad, used as the first equilibrium.
    """
    actuator.update()
    angle = actuator.output_position

    actuator.set_control_mode(CONTROL_MODES.IMPEDANCE)
    actuator.set_impedance_cc_pidf_gains(**current_gains)
    # Equilibrium first, so the controller never pulls towards a stale setpoint
    actuator.set_output_position(angle)
    actuator.set_output_impedance(k=stiffness, b=damping)
    actuator.set_output_position(angle)
    return angle
