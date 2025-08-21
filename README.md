# Modbus Fast Poller (custom integration)

A minimal Home Assistant custom integration that **bulk-reads 32 Modbus values and maps each to a `binary_sensor`**, with a best‑effort polling period down to a few milliseconds (default **5 ms**).

> ⚠️ **Reality check**: 5 ms end‑to‑end updates are often unrealistic in Home Assistant due to Python/async scheduling, the Modbus stack, transport latency (TCP/serial), and the target device’s response time. This integration performs a *single bulk read* each cycle and only pushes updates for changed points to minimize load. Still, expect practical rates closer to 10–50 ms on capable hardware and networks.

## Install

1. Copy the `custom_components/modbus_fast` folder into your Home Assistant `/config/custom_components/` directory.
2. Restart Home Assistant.
3. Add YAML to `configuration.yaml` and restart again.

```yaml
modbus_fast:
  host: 192.168.1.50   # Modbus TCP server (PLC/RTU gateway)
  port: 502
  unit_id: 1
  register_type: holding   # "holding", "input", or "coil"
  start_address: 0
  count: 32
  sample_period_ms: 5      # target poll period (ms)
  name: "PLC Inputs"
  only_on_change: true     # only push updates for changed points
```

This will create 32 binary sensors named like `PLC Inputs R0`, `PLC Inputs R1`, ...

### HACS installation

You can also install this integration via HACS (recommended for easy updates):

1. In HACS, choose "Integrations" -> "Explore & Download repositories".
2. Add this repository (or install via the URL) and install it.
3. Restart Home Assistant.

After HACS installation, configure the integration using the same YAML shown above or convert to the UI config flow if added later.

- For `register_type: coil`, the integration reads 32 coils and maps bits directly to sensors.
- For `holding`/`input`, each 16‑bit register is treated as ON if its value is non‑zero.

## Notes & Tips

- **Bulk reads**: One request per cycle (`read_coils`, `read_holding_registers`, or `read_input_registers`) to get 32 values at once.
- **Push model**: Entities don’t poll; the hub pushes updates via a dispatcher.
- **Change-only updates**: With `only_on_change: true`, HA state updates are emitted only for indices that changed.
- **Availability**: Entities expose `available` based on the Modbus client’s connection status and auto‑reconnect.
- **Throughput**: If you truly need 5 ms reliably, consider running the fast loop in a dedicated process (or microcontroller) that shares memory/MQTT with HA, then reflect those states as HA sensors.

## Troubleshooting

- Enable debug logging:
  ```yaml
  logger:
    default: warning
    logs:
      custom_components.modbus_fast: debug
      pymodbus: debug
  ```
- If your target is a **coil block**, use `register_type: coil` for true bit‑level coil reading.
- If you prefer **per‑bit** extraction from a 16‑bit register (e.g., register 0 contains 16 digital points), extend the code to split bits into sensors (not included here by default).

## Uninstall

- Remove the YAML block, restart HA, and delete the folder from `custom_components`.
