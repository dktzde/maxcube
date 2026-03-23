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
            hass.data[DATA_KEY][host] = MaxCubeHandle(cube, scan_interval, host, port)
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

    return True


class MaxCubeHandle:
    """Keep the cube instance in one place and centralize the update."""

    def __init__(self, cube, scan_interval, host, port):
        """Initialize the Cube Handle."""
        self.cube = cube
        self.cube.use_persistent_connection = True
        self.scan_interval = scan_interval
        self.mutex = Lock()
        self._updatets = time.monotonic()
        self._host = host
        self._port = port

    def update(self):
        """Pull the latest data from the MAX! Cube."""
        # Acquire mutex to prevent simultaneous update from multiple threads
        with self.mutex:
            # Only update every update_interval
            if ((time.monotonic() - self._updatets) >= self.scan_interval):
                _LOGGER.info("Updating: monotonic %s, updatets %s, delta %s, scan_interval: %s, time %s", time.monotonic(), self._updatets, (time.monotonic() - self._updatets), self.scan_interval, time.time())

                try:
                    self.cube.update()
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
