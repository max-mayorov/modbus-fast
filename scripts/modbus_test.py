#!/usr/bin/env python3
"""
Simple Modbus tester for reading values.
Supports Modbus TCP and RTU (serial).

Examples:
- TCP holding registers:  python scripts/modbus_test.py --host 192.168.1.10 --type holding --address 0 --count 2 --unit 1
- TCP coils:              python scripts/modbus_test.py --host 192.168.1.10 --type coils --address 0 --count 8 --unit 1
- RTU holding registers:  python scripts/modbus_test.py --mode rtu --serial COM3 --baud 9600 --type holding --address 0 --count 2 --unit 1
"""
from __future__ import annotations

import argparse
import sys

try:
    from pymodbus.client import ModbusTcpClient, ModbusSerialClient
except Exception as e:  # pragma: no cover
    print("pymodbus is required. Install it with: pip install pymodbus", file=sys.stderr)
    raise


def positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return ivalue


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read values from a Modbus device")
    p.add_argument("--mode", choices=["tcp", "rtu"], default="tcp", help="Connection mode")

    # TCP
    p.add_argument("--host", default="127.0.0.1", help="Modbus TCP host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=502, help="Modbus TCP port (default: 502)")

    # RTU
    p.add_argument("--serial", help="Serial port for RTU, e.g. COM3 or /dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=9600, help="Baud rate for RTU (default: 9600)")
    p.add_argument("--parity", choices=["N", "E", "O"], default="N", help="Parity for RTU (default: N)")
    p.add_argument("--stopbits", type=int, choices=[1, 2], default=1, help="Stop bits for RTU (default: 1)")
    p.add_argument("--bytesize", type=int, choices=[7, 8], default=8, help="Byte size for RTU (default: 8)")

    # Read operation
    p.add_argument("--type", choices=["holding", "input", "coils", "discrete"], default="holding", help="What to read")
    p.add_argument("--address", type=positive_int, default=0, help="Start address (default: 0)")
    p.add_argument("--count", type=positive_int, default=1, help="Number of items to read (default: 1)")
    p.add_argument("--unit", type=int, default=1, help="Modbus unit/device id (default: 1)")
    p.add_argument("--timeout", type=float, default=3.0, help="Socket/serial timeout in seconds (default: 3.0)")

    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.mode == "tcp":
        client = ModbusTcpClient(host=args.host, port=args.port, timeout=args.timeout)
    else:
        if not args.serial:
            print("--serial is required for RTU mode", file=sys.stderr)
            return 2
        client = ModbusSerialClient(
            method="rtu",
            port=args.serial,
            baudrate=args.baud,
            parity=args.parity,
            stopbits=args.stopbits,
            bytesize=args.bytesize,
            timeout=args.timeout,
        )

    if not client.connect():
        print("Failed to connect to Modbus device", file=sys.stderr)
        return 3

    try:
        if args.type == "holding":
            rr = client.read_holding_registers(args.address, count=args.count, device_id=args.unit)
        elif args.type == "input":
            rr = client.read_input_registers(args.address, count=args.count, device_id=args.unit)
        elif args.type == "coils":
            rr = client.read_coils(args.address, count=args.count, device_id=args.unit)
        else:  # discrete
            rr = client.read_discrete_inputs(args.address, count=args.count, device_id=args.unit)

        if rr.isError():
            print(f"Modbus error: {rr}", file=sys.stderr)
            return 4

        if args.type in {"holding", "input"}:
            values = getattr(rr, "registers", None)
        else:
            values = getattr(rr, "bits", None)

        if values is None:
            print("No data returned", file=sys.stderr)
            return 5

        end_addr = args.address + len(values) - 1
        print(
            {
                "mode": args.mode,
                "type": args.type,
                "unit": args.unit,
                "address": args.address,
                "end_address": end_addr,
                "count": len(values),
                "values": values,
            }
        )
        return 0
    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
