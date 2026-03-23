"""Support for MAX! valve opening percentage sensors via MAX! Cube."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DATA_KEY

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Iterate through all MAX! Radiator Thermostat Devices."""
    devices: list[MaxCubePercentageSensorBase] = []
    for handler in hass.data[DATA_KEY].values():
        # Duty Cycle + Free Slots pro Cube
        # Erstellt: 2026-03-05 durch Sonett 4.6
        devices.append(MaxCubeDutyCycleSensor(handler))
        devices.append(MaxCubeFreeSlotsSensor(handler))
        for device in handler.cube.devices:
            if device.is_thermostat():
                devices.append(MaxCubeValve(handler, device))

    add_entities(devices)

class MaxCubePercentageSensorBase(SensorEntity):
    """Base class for maxcube binary sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, handler, device):
        """Initialize MAX! Cube SensorEntity."""
        self._cubehandle = handler
        self._device = device
        self._room = handler.cube.room_by_id(device.room_id)

    def update(self) -> None:
        """Get latest data from MAX! Cube."""
        self._cubehandle.update()

# Duty Cycle Sensor - zeigt 868MHz Funkauslastung des Cubes in %
# Aktualisiert sich: beim HA-Start (H-Message) und nach jedem set_programme-Aufruf (S-Message)
# Erstellt: 2026-03-05 durch Sonett 4.6
class MaxCubeDutyCycleSensor(SensorEntity):
    """Duty Cycle des MAX! Cube (868MHz Funkauslastung, max 1% = 36s/Stunde)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, handler):
        """Initialize the sensor."""
        self._cubehandle = handler
        self._attr_name = "MaxCube Duty Cycle"
        self._attr_unique_id = f"{handler.cube.serial}_duty_cycle"
        self._state = None

    @property
    def state(self):
        """Return the duty cycle percentage."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return "%"

    @property
    def icon(self) -> str:
        return "mdi:radio-tower"

    def update(self) -> None:
        self._state = self._cubehandle.cube.duty_cycle


class MaxCubeFreeSlotsSensor(SensorEntity):
    """Freie Speicherslots im MAX! Cube."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, handler):
        """Initialize the sensor."""
        self._cubehandle = handler
        self._attr_name = "MaxCube Free Memory Slots"
        self._attr_unique_id = f"{handler.cube.serial}_free_memory_slots"
        self._state = None

    @property
    def state(self):
        """Return the number of free memory slots."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        return "slots"

    @property
    def icon(self) -> str:
        return "mdi:memory"

    def update(self) -> None:
        self._state = self._cubehandle.cube.free_memory_slots


class MaxCubeValve(MaxCubePercentageSensorBase):
    """Representation of a MAX! Cube valve aperture Sensor device."""

    def __init__(self, handler, device):
        """Initialize the sensor."""
        super().__init__(handler, device)

        self._attr_name = f"{self._room.name} {device.name} valve aperture"
        self._attr_unique_id = f"{self._device.serial}_valve_aperture"
        self._state = None
        
    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    def update(self) -> None:
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        self._state = self._device.valve_position

