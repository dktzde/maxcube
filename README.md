# maxcube
A review of the official homeassistant integration for ELV MAX! heating system

# Context
The official ELV MAX! integration is buggy and misses some useful features. Also che python class it is based on is buggy, no more mantained and bla bla bla  
The ELV MAX! system seems almost abandoned, noone is taking the maintenance of the code.  
So i created a custom integration based on the above, but with some fixes and features added. Here it is.
  
This is touching:  
- the official integration https://github.com/home-assistant/core/tree/dev/homeassistant/components/maxcube
- the python-maxcube-api library used https://github.com/uebelack/python-maxcube-api  

# Fixes and new features
Integration:  
- added a binary sensor for link quality of devices  
- added a fake HVAC for cube to set config of all rooms in one place  
- fixed the use of presets (away is useless, but windows open is not)  
- extended windows open value also to wall thermostat  
- widely extended devices attributes. Taken valve position also on wall thermostat  
- new sensor for valve opening value  
  
Class:  
- included management of more devices' data  
- extended "get_programmed_temp_at" also to wall thermostat  
- fixed command transmission to manage cube-level commands

# Additional fixes and features (dktzde fork)

Integration:
- **Auto-reconnect after Cube reboot**: `MaxCubeHandle.update()` catches socket timeouts,
  cleanly disconnects and re-establishes the connection automatically. Previously the
  integration would stop updating until Home Assistant was restarted.
- **`maxcube.set_programme` service**: Send a weekly heating schedule to any thermostat
  via RF. Accepts `rf_address`, `day` (monday–sunday) and up to 7 slots with `temp` and
  `until` time. Transmission is skipped when the programme on the device is already
  identical, saving RF duty cycle.
- **Duty cycle and free slots sensors**: Two new diagnostic `SensorEntity` entities per
  Cube show the current 868 MHz RF duty cycle (%) and the number of free memory slots.
  Values are updated from S-message responses after every `set_programme` call and fall
  back to the H-message value on startup.
- **`programme` attribute on climate entities**: The full weekly programme stored on the
  thermostat is exposed as a state attribute so it can be read directly from HA.

Class:
- `cube.py`: Added `duty_cycle` and `free_memory_slots` properties; H-message parser
  now reads duty cycle (token 5) and free slots (token 6) with corrected token index.
- `commander.py`: Added `set_programme` command (Command 10) with correct 2-byte
  slot encoding (7-bit temperature × 2, 9-bit time in 5-minute steps).

# Use
Just put the full directory in the config/custom_components dir.
The use is the very same of the original integration.
