# maxcube_preview.py
# Generisches Preview-Script fuer MaxCube Wochenprogramm-Sync.
# Liest aktive Scheduler-Eintraege fuer ein beliebiges Climate-Entity,
# berechnet MaxCube-Slots, vergleicht mit dem aktuell im Ventil gespeicherten
# Programm und schreibt einen Vorschau-Text in input_text.maxcube_preview_text.
#
# Parameter (service_data):
#   climate_entity_id: Entity-ID des Climate-Entities (z.B. climate.untenbuero_untenburo10)
#
# Erstellt: 2026-03-09 durch Sonett 4.6
# Geaendert: 2026-03-09 generisch gemacht (ersetzt maxcube_buero_preview.py)
# Geaendert: 2026-03-10 Zeitkonflikt-Schutz: spezifischerer Eintrag gewinnt
#            Bugfix: "workday" (Scheduler-Konstante) statt "workdays" in expand_weekdays
# Geaendert: 2026-03-10 Anzeige: aufeinanderfolgende Tage komprimiert (Mo-Fr statt Mo-Di-Mi-Do-Fr)
#            Anzeige: Sched/Geraet fett gedruckt

BOOL_ENTITY    = "input_boolean.maxcube_preview_ready"
PREVIEW_ENTITY = "input_text.maxcube_preview_text"
GERAET_ENTITY  = "input_text.maxcube_preview_geraet"
PENDING_ENTITY = "input_text.maxcube_pending_entity"

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
    """Expandiert Scheduler-Wochentags-Gruppen auf konkrete Tage.
    Akzeptiert beide Schreibweisen: 'workday' (Scheduler-Konstante) und 'workdays'."""
    result = []
    for wd in weekdays:
        if wd == "daily":
            candidates = ALL_DAYS
        elif wd in ("workday", "workdays"):
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


def get_specificity(weekdays_raw, expanded_day):
    """Gibt an wie spezifisch ein Tag adressiert wurde.
    3 = direkte Tagesangabe (mon/sat/...), 2 = Gruppe (workday/weekend), 1 = daily."""
    for wd in weekdays_raw:
        if wd == expanded_day:
            return 3
        if wd in SHORT_TO_LONG and SHORT_TO_LONG[wd] == expanded_day:
            return 3
    for wd in weekdays_raw:
        if wd in ("workday", "workdays", "weekend"):
            return 2
    return 1


def mins_to_hhmm(minutes):
    if minutes >= 1440:
        return "24:00"
    h = minutes // 60
    m = minutes % 60
    return "{:02d}:{:02d}".format(h, m)


def format_slots_compact(slots):
    """Gibt eine kompakte Darstellung einer Slot-Liste zurueck."""
    parts = []
    prev = "00:00"
    for s in slots:
        parts.append("{}-{}:{}\u00b0".format(prev, s["until"], s["temp"]))
        prev = s["until"]
    return "  ".join(parts)


DAY_ORDER_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def compress_days(day_names_list):
    """Komprimiert aufeinanderfolgende Tage zu einem Bereich.
    Beispiel: ['Mo','Di','Mi','Do','Fr'] -> 'Mo-Fr', ['Sa','So'] -> 'Sa-So'."""
    if len(day_names_list) <= 1:
        return day_names_list[0] if day_names_list else ""
    indices = []
    for d in day_names_list:
        if d in DAY_ORDER_SHORT:
            indices.append(DAY_ORDER_SHORT.index(d))
    if not indices:
        return "-".join(day_names_list)
    indices.sort()
    is_consecutive = all(
        indices[i + 1] == indices[i] + 1 for i in range(len(indices) - 1)
    )
    if is_consecutive:
        return "{}-{}".format(DAY_ORDER_SHORT[indices[0]], DAY_ORDER_SHORT[indices[-1]])
    return "-".join(day_names_list)


def deduplicate_days(day_map):
    """Gibt Liste von (day_label, slots) zurueck, mit zusammengefassten gleichen Tagen."""
    seen = {}   # slots_key -> [day_names]
    order = []
    for day in ALL_DAYS:
        if day not in day_map:
            continue
        key = str(day_map[day])
        if key not in seen:
            seen[key] = []
            order.append(key)
        seen[key].append(DAY_NAMES[day])
    result = []
    for key in order:
        days_label = compress_days(seen[key])
        result.append((days_label, seen[key], key))
    return result


# --- Sauberer Startzustand ---
hass.services.call("input_boolean", "turn_off", {"entity_id": BOOL_ENTITY})

# --- Climate-Entity aus Service-Data lesen ---
climate_entity_id = data.get("climate_entity_id")
if not climate_entity_id:
    logger.error("maxcube_preview: climate_entity_id fehlt in service_data")
else:
    climate_state = hass.states.get(climate_entity_id)
    if climate_state is None:
        logger.error("maxcube_preview: Entity nicht gefunden: %s", climate_entity_id)
    else:
        rf_address = climate_state.attributes.get("device_rf_address")
        friendly_name = climate_state.attributes.get("friendly_name", climate_entity_id)
        device_programme = climate_state.attributes.get("programme")

        if not rf_address:
            logger.error("maxcube_preview: device_rf_address fehlt fuer %s", climate_entity_id)
        else:
            # --- Aktive Schedules sammeln mit Zeitkonflikt-Schutz ---
            # day_slots[day][time_minutes] = (temp, specificity)
            # Bei Zeitkonflikt gewinnt der spezifischere Eintrag.
            day_slots = {}
            for state in hass.states.all():
                if not state.entity_id.startswith("switch.schedule_"):
                    continue
                if state.state != "on":
                    continue
                attrs    = state.attributes
                entities = attrs.get("entities", [])
                if climate_entity_id not in entities:
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
                    spec = get_specificity(weekdays, day)
                    if day not in day_slots:
                        day_slots[day] = {}
                    existing = day_slots[day].get(time_minutes)
                    if existing is None:
                        day_slots[day][time_minutes] = (float(temp), spec)
                    elif spec > existing[1]:
                        logger.info(
                            "maxcube_preview: Zeitkonflikt %s tag=%s t=%d: "
                            "bevorzuge spezifischeren Schedule (spec=%d>%d, temp %.1f->%.1f)",
                            climate_entity_id, day, time_minutes,
                            spec, existing[1], existing[0], float(temp)
                        )
                        day_slots[day][time_minutes] = (float(temp), spec)
                    else:
                        logger.warning(
                            "maxcube_preview: Zeitkonflikt %s tag=%s t=%d: "
                            "behalte bestehenden (spec=%d>=neuer spec=%d, temp=%.1f)",
                            climate_entity_id, day, time_minutes,
                            existing[1], spec, existing[0]
                        )

            # --- Entity als "pending" speichern ---
            hass.services.call("input_text", "set_value", {
                "entity_id": PENDING_ENTITY,
                "value": climate_entity_id,
            })

            if not day_slots:
                logger.warning("maxcube_preview: Keine aktiven Schedules fuer %s", climate_entity_id)
                hass.services.call("input_text", "set_value", {
                    "entity_id": PREVIEW_ENTITY,
                    "value": "Keine aktiven Scheduler-Eintraege gefunden.",
                })
                hass.services.call("input_boolean", "turn_on", {"entity_id": BOOL_ENTITY})
            else:
                # --- day_slots von Dict-Format in sortierte Listen umwandeln ---
                # {time: (temp, spec)} -> [(time, temp), ...]
                day_slots_list = {}
                for day, time_map in day_slots.items():
                    day_slots_list[day] = sorted(
                        [(t, v[0]) for t, v in time_map.items()],
                        key=lambda x: x[0]
                    )

                # --- MaxCube-Slots berechnen ---
                all_maxcube_slots = {}
                for day in ALL_DAYS:
                    if day not in day_slots_list:
                        continue
                    slots_sorted = day_slots_list[day]
                    last_temp    = slots_sorted[-1][1]
                    maxcube_slots = []
                    first_time = slots_sorted[0][0]
                    if first_time > 0:
                        maxcube_slots.append({"temp": last_temp, "until": mins_to_hhmm(first_time)})
                    for i, (time_mins, temp) in enumerate(slots_sorted):
                        until_mins = slots_sorted[i + 1][0] if i + 1 < len(slots_sorted) else 1440
                        maxcube_slots.append({"temp": temp, "until": mins_to_hhmm(until_mins)})
                    all_maxcube_slots[day] = maxcube_slots

                # --- Sched-Text bauen (in PREVIEW_ENTITY) ---
                sched_lines = ["**Sched:**\n"]
                deduped = deduplicate_days(all_maxcube_slots)
                if len(deduped) == 1:
                    days_label, _, key = deduped[0]
                    sample = all_maxcube_slots[ALL_DAYS[0] if ALL_DAYS[0] in all_maxcube_slots else list(all_maxcube_slots.keys())[0]]
                    sched_lines.append("Mo-So: {}\n".format(format_slots_compact(sample)))
                else:
                    for days_label, _, key in deduped:
                        sample_slots = None
                        for day in ALL_DAYS:
                            if day in all_maxcube_slots and str(all_maxcube_slots[day]) == key:
                                sample_slots = all_maxcube_slots[day]
                                break
                        if sample_slots:
                            sched_lines.append("{}: {}\n".format(days_label, format_slots_compact(sample_slots)))

                sched_text = "".join(sched_lines)
                if len(sched_text) > 254:
                    sched_text = sched_text[:251] + "..."

                # --- Geraet-Text bauen (in GERAET_ENTITY) ---
                geraet_text = ""
                if device_programme:
                    geraet_lines = ["**Ger\u00e4t:**\n"]
                    deduped_dev = deduplicate_days(device_programme)
                    if len(deduped_dev) == 1:
                        _, _, key = deduped_dev[0]
                        sample = device_programme.get("monday") or list(device_programme.values())[0]
                        geraet_lines.append("Mo-So: {}\n".format(format_slots_compact(sample)))
                    else:
                        for days_label, _, key in deduped_dev:
                            sample_slots = None
                            for day in ALL_DAYS:
                                if day in device_programme and str(device_programme[day]) == key:
                                    sample_slots = device_programme[day]
                                    break
                            if sample_slots:
                                geraet_lines.append("{}: {}\n".format(days_label, format_slots_compact(sample_slots)))
                    geraet_text = "".join(geraet_lines)
                    if len(geraet_text) > 254:
                        geraet_text = geraet_text[:251] + "..."

                hass.services.call("input_text", "set_value", {
                    "entity_id": PREVIEW_ENTITY,
                    "value": sched_text,
                })
                hass.services.call("input_text", "set_value", {
                    "entity_id": GERAET_ENTITY,
                    "value": geraet_text,
                })
                hass.services.call("input_boolean", "turn_on", {"entity_id": BOOL_ENTITY})
                logger.info(
                    "maxcube_preview: Vorschau bereit fuer %s (%d Tage, rf=%s)",
                    climate_entity_id, len(all_maxcube_slots), rf_address
                )
