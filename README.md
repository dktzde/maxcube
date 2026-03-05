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

# Use
Just put the full directory in the config/custom_components dir.
The use is the very same of the original integration.

# Changelog

## 2026-03-05
**Reconnect after connection loss (fix)**
- `MaxCubeHandle` now stores `host` and `port`
- On `socket.timeout` during update: automatic disconnect + reconnect instead of just logging an error
- Prevents heating from going offline until next HA restart after a network interruption or nightly Cube reboot

**New HA service: `maxcube.set_programme`**
- Allows setting the weekly heating schedule for any thermostat directly via HA service call
- Parameters: `rf_address` (device RF address), `day` (monday–sunday), `slots` (list of `{temp, until}`)
- No extra radio transmission if the programme is already identical
- Example call:
  ```yaml
  service: maxcube.set_programme
  data:
    rf_address: "190CFC"
    day: "monday"
    slots:
      - temp: 11.5
        until: "07:00"
      - temp: 19.5
        until: "08:00"
      - temp: 11.5
        until: "17:00"
      - temp: 18.5
        until: "19:00"
      - temp: 11.5
        until: "24:00"
  ```
