# maxcube_confirm.py
# Generisches Confirm-Script fuer MaxCube Wochenprogramm-Sync.
# Liest die Climate-Entity-ID aus input_text.maxcube_pending_entity,
# berechnet die Slots erneut aus den Scheduler-Entities und uebertraegt
# das Wochenprogramm via maxcube.set_programme.
# Prueft vorher ob input_boolean.maxcube_preview_ready gesetzt ist.
#
# Aufruf:  service: python_script.maxcube_confirm  (keine Parameter noetig)
#
# Erstellt: 2026-03-09 durch Sonett 4.6
# Geaendert: 2026-03-09 generisch gemacht (ersetzt maxcube_buero_confirm.py)
# Geaendert: 2026-03-10 Zeitkonflikt-Schutz: spezifischerer Eintrag gewinnt
#            Bugfix: "workday" (Scheduler-Konstante) statt "workdays" in expand_weekdays

BOOL_ENTITY    = "input_boolean.maxcube_preview_ready"
PENDING_ENTITY = "input_text.maxcube_pending_entity"

ALL_DAYS      = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WORKDAYS      = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKEND       = ["saturday", "sunday"]
SHORT_TO_LONG = {
    "mon": "monday", "tue": "tuesday", "wed": "wednesday",
    "thu": "thursday", "fri": "friday", "sat": "saturday", "sun": "sunday",
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


# --- Vorschau-Boolean pruefen ---
bool_state = hass.states.get(BOOL_ENTITY)
if bool_state is None or bool_state.state != "on":
    logger.warning("maxcube_confirm: Kein Boolean gesetzt - erst Vorschau aufrufen.")
    hass.services.call("persistent_notification", "create", {
        "title": "MaxCube - Fehler",
        "message": "Keine Vorschau vorhanden. Bitte zuerst 'Vorschau erstellen' druecken.",
        "notification_id": "maxcube_confirm_error",
    })
else:
    # --- Entity-ID aus Pending-Entity lesen ---
    pending_state = hass.states.get(PENDING_ENTITY)
    climate_entity_id = pending_state.state if pending_state else None

    if not climate_entity_id or climate_entity_id in ("", "unknown"):
        logger.error("maxcube_confirm: Keine pending Entity in %s", PENDING_ENTITY)
        hass.services.call("persistent_notification", "create", {
            "title": "MaxCube - Fehler",
            "message": "Kein Thermostat ausgewaehlt. Bitte zuerst Vorschau aufrufen.",
            "notification_id": "maxcube_confirm_error",
        })
    else:
        # --- Boolean sofort ausschalten (Karte ausblenden) ---
        hass.services.call("input_boolean", "turn_off", {"entity_id": BOOL_ENTITY})

        # --- RF-Adresse lesen ---
        climate_state = hass.states.get(climate_entity_id)
        if climate_state is None:
            logger.error("maxcube_confirm: Entity nicht gefunden: %s", climate_entity_id)
        else:
            rf_address = climate_state.attributes.get("device_rf_address")
            if not rf_address:
                logger.error("maxcube_confirm: device_rf_address fehlt fuer %s", climate_entity_id)
            else:
                # --- Slots neu berechnen mit Zeitkonflikt-Schutz ---
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
                                "maxcube_confirm: Zeitkonflikt %s tag=%s t=%d: "
                                "bevorzuge spezifischeren Schedule (spec=%d>%d, temp %.1f->%.1f)",
                                climate_entity_id, day, time_minutes,
                                spec, existing[1], existing[0], float(temp)
                            )
                            day_slots[day][time_minutes] = (float(temp), spec)
                        else:
                            logger.warning(
                                "maxcube_confirm: Zeitkonflikt %s tag=%s t=%d: "
                                "behalte bestehenden (spec=%d>=neuer spec=%d, temp=%.1f)",
                                climate_entity_id, day, time_minutes,
                                existing[1], spec, existing[0]
                            )

                if not day_slots:
                    logger.warning("maxcube_confirm: Keine Schedules gefunden fuer %s", climate_entity_id)
                    hass.services.call("persistent_notification", "create", {
                        "title": "MaxCube - Fehler",
                        "message": "Keine aktiven Scheduler-Eintraege gefunden fuer {}.".format(climate_entity_id),
                        "notification_id": "maxcube_confirm_error",
                    })
                else:
                    # --- day_slots von Dict-Format in sortierte Listen umwandeln ---
                    # {time: (temp, spec)} -> [(time, temp), ...]
                    day_slots_list = {}
                    for day, time_map in day_slots.items():
                        day_slots_list[day] = sorted(
                            [(t, v[0]) for t, v in time_map.items()],
                            key=lambda x: x[0]
                        )

                    # --- Uebertragen ---
                    days_sent = 0
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

                        hass.services.call("maxcube", "set_programme", {
                            "rf_address": rf_address,
                            "day":        day,
                            "slots":      maxcube_slots,
                        })
                        logger.info("maxcube_confirm: Gesendet %s %s -> %s", climate_entity_id, day, maxcube_slots)
                        days_sent += 1

                    hass.services.call("persistent_notification", "create", {
                        "title": "MaxCube - Erfolg",
                        "message": "Wochenprogramm uebertragen: {} Tage, rf={}.".format(days_sent, rf_address),
                        "notification_id": "maxcube_confirm_ok",
                    })
                    logger.info(
                        "maxcube_confirm: Fertig. %d Tage an rf=%s (%s) gesendet.",
                        days_sent, rf_address, climate_entity_id
                    )
