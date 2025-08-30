# Modbus Fast Poller (custom integration)

A minimal Home Assistant custom integration that bulk-reads Modbus values and maps each to a `binary_sensor`, with a best‑effort polling period down to a few milliseconds (default 5 ms).

> ⚠️ Reality check: 5 ms end‑to‑end updates are often unrealistic in Home Assistant due to Python/async scheduling, the Modbus stack, transport latency (TCP/serial), and the target device’s response time. This integration performs a single bulk read each cycle and, when configured, only pushes updates for changed points to minimize load. Expect practical rates closer to 10–50 ms on capable hardware and networks.

## Install

1. Copy the `custom_components/modbus_fast` folder into your Home Assistant `/config/custom_components/` directory.
2. Restart Home Assistant.
3. Add YAML to `configuration.yaml` and restart again.

```yaml
modbus_fast:
  host: 192.168.1.50        # Modbus TCP server (PLC/RTU gateway)
  port: 502
  unit_id: 1
  register_type: holding    # one of: holding (FC03), input (FC04), coil (FC01), discrete (FC02)
  start_address: 0          # zero-based address; 40001/30001/00001/10001 -> 0
  count: 32                 # 1..128
  sample_period_ms: 5       # target poll period (ms)
  timeout: 1.0              # socket timeout in seconds
  name: "PLC Points"
  only_on_change: true      # push updates only for changed points
  one_based_names: false    # when true, add +1 to the displayed address in names
```

This will create `count` binary sensors named with a type letter and address, for example:
- holding (H): `PLC Points H0`, `PLC Points H1`, ...
- input (R):   `PLC Points R0`, `PLC Points R1`, ...
- coil (C):    `PLC Points C0`, `PLC Points C1`, ...
- discrete (I):`PLC Points I0`, `PLC Points I1`, ...

If `one_based_names: true`, names will be `H1`, `R1`, `C1`, `I1`, etc.

### HACS installation

You can also install this integration via HACS (recommended for easy updates):

1. In HACS, choose "Integrations" → "Explore & Download repositories".
2. Add this repository and install it.
3. Restart Home Assistant.

Configure the integration using the YAML shown above.

## Behavior

- Bulk reads: One request per cycle using the function that matches `register_type`:
  - holding → FC03 `read_holding_registers`
  - input → FC04 `read_input_registers`
  - coil → FC01 `read_coils`
  - discrete → FC02 `read_discrete_inputs`
- Binary mapping:
  - For coils/discrete, the returned bits map directly to sensors.
  - For holding/input registers, each 16‑bit value is considered ON when non‑zero.
- Push model: Entities don’t poll; the hub pushes updates via a dispatcher.
- Change‑only updates: With `only_on_change: true`, state updates are emitted only for indices that changed.
- Availability: Entities expose `available` based on the Modbus client’s connection status and auto‑reconnect.

## Tips

- Start with conservative settings, e.g. `sample_period_ms: 50` and `timeout: 1.0`, then tune down if stable.
- Verify addressing: if your map is 10001/00001/30001/40001‑based, subtract the base to get zero‑based `start_address`.
- Ensure `unit_id` and `port` match the device/gateway configuration.

## Troubleshooting

- Enable debug logging:
  ```yaml
  logger:
    default: warning
    logs:
      custom_components.modbus_fast: debug
      pymodbus: debug
  ```
- Common Modbus exceptions:
  - `ExceptionResponse(..., function_code=0x84, exception_code=0x02)`: Illegal Data Address → the requested start address/count aren’t valid for that function or range. Check `register_type`, address base, and `count`.
- If you expected 1‑based names, set `one_based_names: true`.
- If your device exposes a 16‑bit register where each bit is a digital point, this integration treats the whole register as a single boolean (non‑zero = ON). Splitting bits into separate entities would require a custom extension.

## Uninstall

- Remove the YAML block, restart HA, and delete the folder from `custom_components`.

