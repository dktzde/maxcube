# maxcube_buero_preview.py
# Liest aktive Scheduler-Eintraege fuer Buero Unten, berechnet MaxCube-Slots,
# schreibt Vorschau-Text in input_text und aktiviert die Bestaetigungs-Karte.
#
# Erstellt: 2026-03-09 durch Sonett 4.6
# Geaendert: 2026-03-09 hass.data entfernt (RestrictedPython)
# Geaendert: 2026-03-09 Vorschau in input_text statt Notification

CLIMATE_ENTITY  = "climate.untenbuero_untenburo10"
BOOL_ENTITY     = "input_boolean.maxcube_buero_preview_ready"
PREVIEW_ENTITY  = "input_text.maxcube_buero_preview_text"

ALL_DAYS      = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WORKDAYS      = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKEND       = ["saturday", "sunday"]
SHORT_TO_LONG = {
    "mon": "monday", "tue": "tuesday", "wed": "wednesday",
    "thu": "thursday", "fri": "friday", "sat": "saturday", "sun": "sunday",
}
DAY_NAMES = {
    "monday": "Mo", "tuesday": "Di", "wednesday": "Mi",
    "thursday": "Do", "friday": "Fr", "saturday": "Sa", "sunday": "So",
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

# --- Sauberer Startzustand ---
hass.services.call("input_boolean", "turn_off", {"entity_id": BOOL_ENTITY})

# --- Climate-Entity und RF-Adresse lesen ---
climate_state = hass.states.get(CLIMATE_ENTITY)
if climate_state is None:
    logger.error("maxcube_buero_preview: Entity nicht gefunden: %s", CLIMATE_ENTITY)
else:
    rf_address = climate_state.attributes.get("device_rf_address")
    if not rf_address:
        logger.error("maxcube_buero_preview: device_rf_address fehlt fuer %s", CLIMATE_ENTITY)
    else:
        # --- Aktive Schedules sammeln ---
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
            logger.warning("maxcube_buero_preview: Keine aktiven Schedules fuer %s", CLIMATE_ENTITY)
            hass.services.call("input_text", "set_value", {
                "entity_id": PREVIEW_ENTITY,
                "value": "Keine aktiven Scheduler-Eintraege gefunden.",
            })
            hass.services.call("input_boolean", "turn_on", {"entity_id": BOOL_ENTITY})
        else:
            # --- MaxCube-Slots berechnen ---
            all_maxcube_slots = {}
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
                all_maxcube_slots[day] = maxcube_slots

            # --- Vorschau-Text bauen ---
            unique_keys = []
            for day in ALL_DAYS:
                if day not in all_maxcube_slots:
                    continue
                key = str(all_maxcube_slots[day])
                if key not in unique_keys:
                    unique_keys.append(key)

            lines = ["**Buero Unten – Vorschau**\n"]
            if len(unique_keys) == 1:
                lines.append("Mo–So (taeglich):\n")
                sample = list(all_maxcube_slots.values())[0]
                prev = "00:00"
                for s in sample:
                    lines.append("{} – {} -> {}°\n".format(prev, s["until"], s["temp"]))
                    prev = s["until"]
            else:
                for day in ALL_DAYS:
                    if day not in all_maxcube_slots:
                        continue
                    prev = "00:00"
                    slot_texts = []
                    for s in all_maxcube_slots[day]:
                        slot_texts.append("{}->{}°".format(s["until"], s["temp"]))
                        prev = s["until"]
                    lines.append("{}: {}\n".format(DAY_NAMES[day], "  ".join(slot_texts)))

            preview_text = "".join(lines)
            # Auf 255 Zeichen kuerzen falls noetig
            if len(preview_text) > 254:
                preview_text = preview_text[:251] + "..."

            hass.services.call("input_text", "set_value", {
                "entity_id": PREVIEW_ENTITY,
                "value": preview_text,
            })
            hass.services.call("input_boolean", "turn_on", {"entity_id": BOOL_ENTITY})
            logger.info(
                "maxcube_buero_preview: Vorschau bereit. %d Tage, rf=%s",
                len(all_maxcube_slots), rf_address
            )
