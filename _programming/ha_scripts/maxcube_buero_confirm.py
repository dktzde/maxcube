# maxcube_buero_confirm.py
# Berechnet die Slots erneut (aus Scheduler-Entities) und uebertraegt sie
# als Wochenprogramm an den MaxCube via maxcube.set_programme.
# Zeigt Fehler wenn kein Boolean gesetzt ist (erst Vorschau aufrufen).
#
# Kein hass.data - Slots werden direkt neu berechnet.
#
# Aufruf:  service: python_script.maxcube_buero_confirm
#
# Erstellt: 2026-03-09 durch Sonett 4.6
# Geaendert: 2026-03-09 hass.data entfernt, Slots werden neu berechnet

CLIMATE_ENTITY = "climate.untenbuero_untenburo10"
BOOL_ENTITY    = "input_boolean.maxcube_buero_preview_ready"

ALL_DAYS      = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WORKDAYS      = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKEND       = ["saturday", "sunday"]
SHORT_TO_LONG = {
    "mon": "monday", "tue": "tuesday", "wed": "wednesday",
    "thu": "thursday", "fri": "friday", "sat": "saturday", "sun": "sunday",
}

def expand_weekdays(weekdays):
    result = []
    for wd in weekdays:
        if wd == "daily":
            candidates = ALL_DAYS
        elif wd == "workdays":
            candidates = WORKDAYS
        elif wd == "weekend":
            candidates = WEEKEND
        elif wd in SHORT_TO_LONG:
            candidates = [SHORT_TO_LONG[wd]]
        elif wd in ALL_DAYS:
            candidates = [wd]
        else:
            candidates = []
        for d in candidates:
            if d not in result:
                result.append(d)
    return result

def mins_to_hhmm(minutes):
    if minutes >= 1440:
        return "24:00"
    h = minutes // 60
    m = minutes % 60
    return "{:02d}:{:02d}".format(h, m)

# --- Vorschau-Boolean pruefen ---
bool_state = hass.states.get(BOOL_ENTITY)
if bool_state is None or bool_state.state != "on":
    logger.warning("maxcube_buero_confirm: Kein Boolean gesetzt - erst Vorschau aufrufen.")
    hass.services.call("persistent_notification", "create", {
        "title": "MaxCube Buero - Fehler",
        "message": "Keine Vorschau vorhanden. Bitte zuerst 'Vorschau erstellen' druecken.",
        "notification_id": "maxcube_buero_error",
    })
else:
    # --- Boolean sofort ausschalten (Karte ausblenden) ---
    hass.services.call("input_boolean", "turn_off", {"entity_id": BOOL_ENTITY})

    # --- RF-Adresse lesen ---
    climate_state = hass.states.get(CLIMATE_ENTITY)
    if climate_state is None:
        logger.error("maxcube_buero_confirm: Entity nicht gefunden: %s", CLIMATE_ENTITY)
    else:
        rf_address = climate_state.attributes.get("device_rf_address")
        if not rf_address:
            logger.error("maxcube_buero_confirm: device_rf_address fehlt fuer %s", CLIMATE_ENTITY)
        else:
            # --- Slots neu berechnen ---
            day_slots = {}
            for state in hass.states.all():
                if not state.entity_id.startswith("switch.schedule_"):
                    continue
                if state.state != "on":
                    continue
                attrs    = state.attributes
                entities = attrs.get("entities", [])
                if CLIMATE_ENTITY not in entities:
                    continue
                timeslots = attrs.get("timeslots", [])
                actions   = attrs.get("actions", [])
                weekdays  = attrs.get("weekdays", [])
                if not timeslots or not actions:
                    continue
                action = actions[0]
                if action.get("service") != "climate.set_temperature":
                    continue
                temp = action.get("data", {}).get("temperature")
                if temp is None:
                    continue
                parts        = timeslots[0].split(":")
                time_minutes = int(parts[0]) * 60 + int(parts[1])
                for day in expand_weekdays(weekdays):
                    if day not in day_slots:
                        day_slots[day] = []
                    day_slots[day].append((time_minutes, float(temp)))

            if not day_slots:
                logger.warning("maxcube_buero_confirm: Keine Schedules gefunden fuer %s", CLIMATE_ENTITY)
                hass.services.call("persistent_notification", "create", {
                    "title": "MaxCube Buero - Fehler",
                    "message": "Keine aktiven Scheduler-Eintraege gefunden.",
                    "notification_id": "maxcube_buero_error",
                })
            else:
                # --- Uebertragen ---
                days_sent = 0
                for day in ALL_DAYS:
                    if day not in day_slots:
                        continue
                    slots_sorted = sorted(day_slots[day], key=lambda x: x[0])
                    last_temp    = slots_sorted[-1][1]
                    maxcube_slots = []
                    first_time = slots_sorted[0][0]
                    if first_time > 0:
                        maxcube_slots.append({"temp": last_temp, "until": mins_to_hhmm(first_time)})
                    for i, (time_mins, temp) in enumerate(slots_sorted):
                        until_mins = slots_sorted[i + 1][0] if i + 1 < len(slots_sorted) else 1440
                        maxcube_slots.append({"temp": temp, "until": mins_to_hhmm(until_mins)})

                    hass.services.call("maxcube", "set_programme", {
                        "rf_address": rf_address,
                        "day":        day,
                        "slots":      maxcube_slots,
                    })
                    logger.info("maxcube_buero_confirm: Gesendet %s -> %s", day, maxcube_slots)
                    days_sent += 1

                hass.services.call("persistent_notification", "dismiss", {
                    "notification_id": "maxcube_buero_preview",
                })
                hass.services.call("persistent_notification", "create", {
                    "title": "MaxCube Buero - Erfolg",
                    "message": "Wochenprogramm uebertragen: {} Tage, rf={}.".format(days_sent, rf_address),
                    "notification_id": "maxcube_buero_confirm",
                })
                logger.info(
                    "maxcube_buero_confirm: Fertig. %d Tage an rf=%s gesendet.",
                    days_sent, rf_address
                )
