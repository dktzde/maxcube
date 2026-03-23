# MaxCube Scheduler-Sync – Wochenprogramm aus HA an Thermostate übertragen

Dieses Verzeichnis enthält alles um das Wochenprogramm der
[custom:scheduler-card](https://github.com/nielsfaber/scheduler-card)
automatisch an MAX! Thermostate zu übertragen – über den in dieser Integration
eingebauten `maxcube.set_programme` Service.

## Funktionsweise

Der Sync läuft zweistufig:

1. **Vorschau** (`maxcube_preview.py`): Liest alle aktiven `switch.schedule_*`-Entities
   des Schedulers für ein Thermostat, berechnet daraus MaxCube-Slots und zeigt sie
   in einer Dashboard-Karte neben dem aktuell im Gerät gespeicherten Programm an.
2. **Bestätigung** (`maxcube_confirm.py`): Überträgt die Slots per RF an das Gerät,
   sobald der Nutzer „Übertragen" drückt. Nur wenn `input_boolean.maxcube_preview_ready`
   gesetzt ist (Schutz vor versehentlichem Auslösen).

## Dateien

```
ha_scripts/
  maxcube_preview.py        Generisches Preview-Script (beliebige Climate-Entity als Parameter)
  maxcube_confirm.py        Generisches Confirm-Script (liest pending Entity aus input_text)
  maxcube_buero_preview.py  Älteres Beispiel mit hardcodierter Entity (Einzelraum)
  maxcube_buero_confirm.py  Älteres Beispiel mit hardcodierter Entity (Einzelraum)

ha_helpers/
  maxcube_sync.yaml         input_boolean + input_text Hilfsentitäten (in packages/ ablegen)

ha_dashboard/
  example_dashboard.yaml    Minimales Beispiel-Dashboard ohne externe Abhängigkeiten (Entity-IDs anpassen)
```

## Einrichtung

### 1. Python-Scripts

Alle `.py`-Dateien nach `config/python_scripts/` kopieren.
In `configuration.yaml` muss aktiviert sein:
```yaml
python_script:
```

### 2. Hilfsentitäten

`maxcube_sync.yaml` nach `config/packages/` kopieren.
In `configuration.yaml` muss `homeassistant.packages` eingebunden sein:
```yaml
homeassistant:
  packages: !include_dir_named packages/
```

### 3. Dashboard

`maxcube_sync_card.yaml` nach `config/dashboards/Streamline_Vorlagen/` (oder dem
eigenen Streamline-Template-Verzeichnis) kopieren.

`example_dashboard.yaml` als neues Dashboard anlegen und die `entity`-Variablen
auf die eigenen Climate-Entity-IDs anpassen. Den `streamline_templates`-Pfad
ggf. ebenfalls anpassen.

### 4. Abhängigkeiten (HACS)

- [scheduler-card](https://github.com/nielsfaber/scheduler-card)
- [scheduler-component](https://github.com/nielsfaber/scheduler-component)
- [streamline-card](https://github.com/brunosabot/streamline-card)

## Service-Aufruf (manuell)

Das Wochenprogramm kann auch direkt per Service übertragen werden:

```yaml
service: maxcube.set_programme
data:
  rf_address: "AABBCC"   # RF-Adresse aus Attribut device_rf_address des Climate-Entity
  day: monday
  slots:
    - temp: 17.0
      until: "06:00"
    - temp: 21.0
      until: "22:00"
    - temp: 17.0
      until: "24:00"
```

Die RF-Adresse des Thermostats findet man unter:
**Developer Tools → States → climate.\<entity\> → Attribut `device_rf_address`**

## Duty Cycle beachten

Der MAX! Cube darf nur 1 % der Zeit senden (36 s/Stunde). Der Sensor
`sensor.maxcube_duty_cycle` zeigt die aktuelle Auslastung. Ein Wochenprogramm
für alle 7 Tage belegt ca. 7–14 RF-Pakete. Empfehlung: Sync nur ausführen wenn
Duty Cycle < 50 %.

## Slot-Kodierung (Protokoll-Details)

Jeder Slot besteht aus 2 Bytes:

```
Bit 15–9 (7 Bit): Temperatur × 2   (z.B. 21.0 °C → 42 → 0b0101010)
Bit  8–0 (9 Bit): Zeit in 5-Min-Schritten seit Mitternacht
                  (z.B. 22:00 = 1320 min → 1320/5 = 264 → 0b100001000)
```

Max. 7 Slots pro Tag. Der letzte Slot muss `until: "24:00"` haben.
Wenn der erste Slot nicht um 00:00 beginnt, wird automatisch ein Füll-Slot
mit der Temperatur des letzten Slots vorangestellt.
