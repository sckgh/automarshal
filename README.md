# automarshal

Automated Race Track Marshalling & Communication System – a Python-based platform that interfaces with Garmin MyLaps (X2 SDK / Orbits) to automate track safety lights and radio communications in real time.

## Features

| Feature | Description |
|---------|-------------|
| **Sector flag automation** | White / Yellow / Blue flags triggered from timing-loop and GPS telemetry |
| **GPS clearance** | Automatic flag clearance once speed and distance criteria are met (2 s persistence window → 5 s green display) |
| **Global flag overrides** | Red, Safety Car, Chequered via voice or API |
| **YAML rule engine** | Plain-English rules evaluated safely against live telemetry |
| **Dual-channel radio** | Channel A (Race Control): three-step handshake. Channel B (Drivers): priority-stack interrupt broadcast |
| **Hardware stubs** | DMX-512 panel control, MQTT light publishing, GPIO PTT relay |
| **Failsafe heartbeat** | Defaults all panels to MANUAL ONLY if telemetry latency exceeds 500 ms |

## Project Structure

```
automarshal/
├── automarshal/
│   ├── main.py                # Async application entry point
│   ├── models/                # FlagState, CarTelemetry, Sector
│   ├── engine/
│   │   ├── session_state.py   # Thread-safe session state store
│   │   ├── rule_parser.py     # YAML DSL parser (safe sandbox eval)
│   │   └── flag_engine.py     # Sector & global flag logic
│   ├── ingestion/
│   │   ├── mylaps_client.py   # MyLaps X2 SDK adapter (stub)
│   │   └── gps_client.py      # X2 Link GPS adapter (stub)
│   ├── radio/
│   │   ├── radio_controller.py  # Dual-channel state machine
│   │   ├── tts_engine.py        # Text-to-speech stub
│   │   └── stt_engine.py        # Speech-to-text stub
│   ├── hardware/
│   │   ├── dmx_controller.py   # DMX-512 light panel stub
│   │   ├── mqtt_controller.py  # MQTT light panel stub
│   │   └── gpio_controller.py  # GPIO PTT relay stub
│   └── safety/
│       └── heartbeat.py        # 500 ms failsafe monitor
├── rules/
│   └── rules.yaml             # Example YAML ruleset
└── tests/                     # pytest test suite (33 tests)
```

## Quick Start

```bash
pip install -e ".[dev]"
automarshal          # run with stub telemetry (simulated cars)
```

## YAML Rule Format

```yaml
- name: "Hazard Turn 4"
  if: "car.velocity_kmh < 10 and car.track_position == 'Turn 4'"
  then:
    light: "Sector_4_Yellow"
    radio_drivers: "Caution Turn 4. Caution Turn 4."
    radio_rc: "Car traveling slowly, Turn 4."
```

Available attributes on `car`:

| Attribute | Type | Description |
|-----------|------|-------------|
| `car.car_id` | str | Transponder / car number |
| `car.car_class` | str | Racing class (e.g. `"GT3"`) |
| `car.track_position` | str | Named location (e.g. `"Turn 4"`) |
| `car.sector_id` | int | Zero-based sector index |
| `car.velocity_kmh` | float | Speed in km/h |
| `car.current_sector_time` | float | Elapsed sector time (seconds) |
| `car.last_sector_time` | float | Previous completed sector time |
| `car.gap_to_car_ahead` | float \| None | Gap in seconds to car ahead |

## Flag Logic (Built-in)

| Flag | Condition |
|------|-----------|
| WHITE | `current_sector_time > best * 1.3` |
| YELLOW | `current_sector_time > best * 1.8` OR `velocity < 10 km/h` |
| BLUE | `gap_to_car_ahead < 2.0 s` |
| CLEAR | `velocity > racing_avg * 0.8` AND distance > 50 m for 2 s → GREEN for 5 s |

## Radio Handshake (Channel A)

```
System  → "Race Control, this is Sector 1."
RC      → (STT) "Go ahead Sector 1."
System  → "Car 42 traveling slowly."
```

## Tests

```bash
pytest tests/ -v
```

## Hardware Integration

Replace the stub implementations in `automarshal/hardware/` and `automarshal/ingestion/` with real SDK calls:

- **DMX**: Use OLA (Open Lighting Architecture) Python bindings or a pyserial DMX adapter.
- **MQTT**: The `MQTTController` calls are pre-wired for `aiomqtt` – uncomment the real publish call.
- **GPIO PTT**: Replace the `asyncio.sleep(0)` stubs with `RPi.GPIO.output(pin, active)`.
- **MyLaps**: Replace `_simulate_loop` in `MyLapsClient` with actual X2 SDK / Orbits callbacks.
- **GPS**: Replace `_idle_loop` in `GPSClient` with X2 Link TCP frame decoding.
- **TTS/STT**: Replace `TTSEngine.speak` / `STTEngine.listen` with `edge-tts` or Whisper.
