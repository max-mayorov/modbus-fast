DOMAIN = "modbus_fast"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_UNIT_ID = "unit_id"
CONF_REGISTER_TYPE = "register_type"
CONF_START_ADDRESS = "start_address"
CONF_COUNT = "count"
CONF_SAMPLE_MS = "sample_period_ms"
CONF_NAME = "name"
CONF_ONLY_ON_CHANGE = "only_on_change"
CONF_TIMEOUT = "timeout"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
DEFAULT_REGISTER_TYPE = "holding"  # "holding", "input", or "coil"
DEFAULT_START_ADDRESS = 0
DEFAULT_COUNT = 32
DEFAULT_SAMPLE_MS = 15
DEFAULT_NAME = "Modbus Fast"
DEFAULT_ONLY_ON_CHANGE = True
DEFAULT_TIMEOUT = 1.0

SIGNAL_UPDATE = f"{DOMAIN}_update"
