"""Support for the MAX! Cube LAN Gateway."""
import logging
from socket import timeout
from threading import Lock
import time

from .maxcube.cube import MaxCube
import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.dt import now

# Service: set_programme - Wochenprogramm an Thermostat senden
# Erstellt: 2026-03-05 durch Sonett 4.6
# Doku: /homeassistant/claude-max.md
SERVICE_SET_PROGRAMME = "set_programme"
VALID_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

SET_PROGRAMME_SCHEMA = vol.Schema({
    vol.Required("rf_address"): cv.string,
    vol.Required("day"): vol.In(VALID_DAYS),
    vol.Required("slots"): vol.All(
        cv.ensure_list,
        [vol.Schema({
            vol.Required("temp"): vol.Coerce(float),
            vol.Required("until"): cv.string,
        })]
    ),
})

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 62910
DOMAIN = "maxcube"

DATA_KEY = "maxcube"

NOTIFICATION_ID = "maxcube_notification"
NOTIFICATION_TITLE = "Max!Cube gateway setup"

CONF_GATEWAYS = "gateways"

CONFIG_GATEWAY = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_SCAN_INTERVAL, default=300): cv.time_period,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_GATEWAYS, default={}): vol.All(
                    cv.ensure_list, [CONFIG_GATEWAY]
                )
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Establish connection to MAX! Cube."""

    if DATA_KEY not in hass.data:
        hass.data[DATA_KEY] = {}

    connection_failed = 0
    gateways = config[DOMAIN][CONF_GATEWAYS]
    for gateway in gateways:
        host = gateway[CONF_HOST]
        port = gateway[CONF_PORT]
        scan_interval = gateway[CONF_SCAN_INTERVAL].total_seconds()

        try:
            cube = MaxCube(host, port, now=now)
            hass.data[DATA_KEY][host] = MaxCubeHandle(cube, scan_interval, host, port, hass=hass)
        except timeout as ex:
            _LOGGER.error("Unable to connect to Max!Cube gateway: %s", str(ex))
            persistent_notification.create(
                hass,
                (
                    f"Error: {ex}<br />You will need to restart Home Assistant after"
                    " fixing."
                ),
                title=NOTIFICATION_TITLE,
                notification_id=NOTIFICATION_ID,
            )
            connection_failed += 1

    if connection_failed >= len(gateways):
        return False
        
    load_platform(hass, Platform.CLIMATE, DOMAIN, {}, config)
    load_platform(hass, Platform.BINARY_SENSOR, DOMAIN, {}, config)
    load_platform(hass, Platform.SENSOR, DOMAIN, {}, config)

    # Pairing: new_device_found_callback für jeden Handle registrieren
    # Erstellt: 2026-03-09 durch Sonett 4.6
    DEVICE_TYPE_NAMES = {
        1: "Heizkörperthermostat",
        2: "Heizkörperthermostat+",
        3: "Wandthermostat",
        4: "Fensterkontakt",
        5: "Eco-Taster",
    }

    for host, handle in hass.data[DATA_KEY].items():
        def _make_callback(h):
            def new_device_found(rf_address, device_type):
                type_name = DEVICE_TYPE_NAMES.get(device_type, f"Gerät (Typ {device_type})")
                options = []
                for _h in hass.data[DATA_KEY].values():
                    for room in _h.cube.rooms:
                        options.append(f"{room.name} (ID:{room.id})")
                try:
                    from homeassistant.helpers import area_registry as ar
                    area_reg = ar.async_get(hass)
                    for area in area_reg.areas.values():
                        options.append(f"Neu: {area.name}")
                except Exception:
                    pass
                if not options:
                    options = ["(kein Raum)"]
                hass.services.call("input_text", "set_value", {
                    "entity_id": "input_text.maxcube_new_device_rf", "value": rf_address})
                hass.services.call("input_text", "set_value", {
                    "entity_id": "input_text.maxcube_new_device_type", "value": type_name})
                hass.services.call("input_select", "set_options", {
                    "entity_id": "input_select.maxcube_assign_room", "options": options})
                hass.services.call("input_boolean", "turn_on", {
                    "entity_id": "input_boolean.maxcube_pairing_pending"})
                hass.services.call("input_boolean", "turn_off", {
                    "entity_id": "input_boolean.maxcube_pairing_active"})
                h._pairing_mode = False
                h.scan_interval = h._saved_scan_interval
                persistent_notification.create(
                    hass,
                    f"Neues Gerät gefunden: {type_name} (RF: {rf_address})\n"
                    "Raum im Dashboard zuweisen.",
                    title="MaxCube – Neues Gerät",
                    notification_id="maxcube_new_device",
                )
                _LOGGER.info("Pairing abgeschlossen: %s (%s)", rf_address, type_name)
            return new_device_found
        handle._new_device_found_callback = _make_callback(handle)

    # Service: Wochenprogramm an ein Thermostat senden
    # Erstellt: 2026-03-05 durch Sonett 4.6
    def handle_set_programme(call):
        rf_address = call.data["rf_address"].upper()
        day = call.data["day"]
        slots = call.data["slots"]

        for host, handle in hass.data[DATA_KEY].items():
            with handle.mutex:
                device = handle.cube.device_by_rf(rf_address)
                if device:
                    result = handle.cube.set_programme(device, day, slots)
                    _LOGGER.info(
                        "set_programme: %s day=%s slots=%s result=%s",
                        rf_address, day, slots, result
                    )
                    return

        _LOGGER.error("set_programme: Gerät nicht gefunden: %s", rf_address)

    hass.services.register(
        DOMAIN,
        SERVICE_SET_PROGRAMME,
        handle_set_programme,
        schema=SET_PROGRAMME_SCHEMA,
    )

    # Service: Pairing-Modus starten
    # Erstellt: 2026-03-09 durch Sonett 4.6
    SERVICE_START_PAIRING = "start_pairing"
    START_PAIRING_SCHEMA = vol.Schema({
        vol.Optional("timeout", default=60): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
    })

    def handle_start_pairing(call):
        timeout = call.data.get("timeout", 60)
        for host, handle in hass.data[DATA_KEY].items():
            with handle.mutex:
                handle._saved_scan_interval = handle.scan_interval
                handle.scan_interval = 5
                handle._pairing_mode = True
                handle.cube.start_pairing(timeout)
        hass.services.call("input_boolean", "turn_on", {
            "entity_id": "input_boolean.maxcube_pairing_active"})
        hass.services.call("input_boolean", "turn_off", {
            "entity_id": "input_boolean.maxcube_pairing_pending"})
        persistent_notification.create(
            hass,
            f"Pairing-Modus aktiv ({timeout}s) – Taste am neuen Gerät drücken!",
            title="MaxCube – Gerät anlernen",
            notification_id="maxcube_pairing_active",
        )
        _LOGGER.info("MaxCube Pairing gestartet (%ds)", timeout)

    hass.services.register(
        DOMAIN,
        SERVICE_START_PAIRING,
        handle_start_pairing,
        schema=START_PAIRING_SCHEMA,
    )

    # Service: Gerät einem Raum zuweisen (nach Pairing)
    # Erstellt: 2026-03-09 durch Sonett 4.6
    SERVICE_ASSIGN_ROOM = "assign_room"
    ASSIGN_ROOM_SCHEMA = vol.Schema({
        vol.Required("rf_address"): cv.string,
        vol.Optional("room_id"): vol.Coerce(int),
        vol.Optional("new_room_name"): cv.string,
    })

    def handle_assign_room(call):
        rf_address = call.data["rf_address"].upper()
        room_id = call.data.get("room_id")
        new_room_name = call.data.get("new_room_name")
        for host, handle in hass.data[DATA_KEY].items():
            with handle.mutex:
                device = handle.cube.device_by_rf(rf_address)
                if device:
                    result = handle.cube.assign_room(rf_address, room_id, new_room_name)
                    if result:
                        _LOGGER.info(
                            "assign_room: %s → room_id=%s new_name=%s",
                            rf_address, room_id, new_room_name,
                        )
                    return
        _LOGGER.error("assign_room: Gerät nicht gefunden: %s", rf_address)

    hass.services.register(
        DOMAIN,
        SERVICE_ASSIGN_ROOM,
        handle_assign_room,
        schema=ASSIGN_ROOM_SCHEMA,
    )

    return True


class MaxCubeHandle:
    """Keep the cube instance in one place and centralize the update."""

    def __init__(self, cube, scan_interval, host, port, hass=None):
        """Initialize the Cube Handle."""
        self.cube = cube
        self.cube.use_persistent_connection = True
        self.scan_interval = scan_interval
        self._saved_scan_interval = scan_interval
        self.mutex = Lock()
        self._updatets = time.monotonic()
        self._host = host
        self._port = port
        self.hass = hass
        # Dynamische Entity-Registrierung: bekannte RF-Adressen tracken
        # Erstellt: 2026-03-09 durch Sonett 4.6
        self._known_rf_addresses = {d.rf_address for d in cube.devices}
        self._new_climate_callback = None      # gesetzt von climate.setup_platform
        self._new_binary_sensor_callback = None  # gesetzt von binary_sensor.setup_platform
        self._new_device_found_callback = None   # gesetzt von setup() in __init__.py
        self._pairing_mode = False

    def update(self):
        """Pull the latest data from the MAX! Cube."""
        # Acquire mutex to prevent simultaneous update from multiple threads
        with self.mutex:
            # Only update every update_interval
            if ((time.monotonic() - self._updatets) >= self.scan_interval):
                _LOGGER.info("Updating: monotonic %s, updatets %s, delta %s, scan_interval: %s, time %s", time.monotonic(), self._updatets, (time.monotonic() - self._updatets), self.scan_interval, time.time())

                try:
                    self.cube.update()
                    self._check_new_devices()
                except timeout:
                    _LOGGER.error("Max!Cube connection failed, attempting reconnect...")
                    try:
                        self.cube.disconnect()
                    except Exception:
                        pass
                    try:
                        self.cube = MaxCube(self._host, self._port, now=now)
                        self.cube.use_persistent_connection = True
                        _LOGGER.info("Max!Cube reconnected successfully to %s", self._host)
                    except timeout:
                        _LOGGER.error("Max!Cube reconnect failed for %s", self._host)
                    return False

                self._updatets = time.monotonic()

    def _check_new_devices(self):
        """Erkennt neue Geräte in cube.devices und registriert HA-Entities.
        Erstellt: 2026-03-09 durch Sonett 4.6
        """
        for device in self.cube.devices:
            if device.rf_address not in self._known_rf_addresses:
                self._known_rf_addresses.add(device.rf_address)
                _LOGGER.info(
                    "Neues Gerät erkannt: rf=%s type=%s",
                    device.rf_address, device.type,
                )
                if self._new_climate_callback and (
                    device.is_thermostat() or device.is_wallthermostat()
                ):
                    self._new_climate_callback(device)
                if self._new_binary_sensor_callback:
                    self._new_binary_sensor_callback(device)
                if self._new_device_found_callback:
                    self._new_device_found_callback(device.rf_address, device.type)
