"""Strict ZPackage primitives shared by the profile and player codecs."""

import io
import math
import struct


INT32_MAX = (1 << 31) - 1


class NonfiniteFloat(float):
    """Keep original IEEE bits even when Python quiets a signaling NaN."""

    def __new__(cls, raw):
        value = super().__new__(cls, struct.unpack("<f", raw)[0])
        value.raw = raw
        return value

    def __reduce__(self):
        return type(self), (self.raw,)


def require_int(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{field} must be an integer between {low} and {high}.")
    return value


def require_bool(value, field):
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean.")
    return value


def require_object(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object.")
    return value


def require_array(value, field):
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be an array.")
    return value


def decode_hex(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a hexadecimal string.")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"Invalid hexadecimal bytes in {field}.") from exc


class BinaryReader:
    def __init__(self, data):
        self.stream = io.BytesIO(data)
        self.size = len(data)

    def check_remaining(self, length, field):
        if length < 0:
            raise ValueError(f"Invalid negative length for {field}: {length}.")
        remaining = self.size - self.stream.tell()
        if length > remaining:
            raise EOFError(f"Truncated {field}: needs {length} bytes, only {remaining} remain.")

    def read_bytes(self, length, field="payload"):
        self.check_remaining(length, field)
        return self.stream.read(length)

    def read_byte(self, field="byte"):
        return self.read_bytes(1, field)[0]

    def read_ushort(self):
        return struct.unpack("<H", self.read_bytes(2, "unsigned 16-bit integer"))[0]

    def read_int32(self):
        return struct.unpack("<i", self.read_bytes(4, "signed 32-bit integer"))[0]

    def read_long(self):
        return struct.unpack("<q", self.read_bytes(8, "signed 64-bit integer"))[0]

    def read_float(self):
        raw = self.read_bytes(4, "binary32 value")
        value = struct.unpack("<f", raw)[0]
        return value if math.isfinite(value) else NonfiniteFloat(raw)

    def read_bool(self):
        value = self.read_byte("boolean")
        if value > 1:
            raise ValueError(f"Noncanonical boolean byte {value}; editing would normalize it.")
        return bool(value)

    def read_vector3(self):
        return [self.read_float() for _ in range(3)]

    def read_7bit_encoded_int(self):
        value = 0
        for shift in range(0, 35, 7):
            byte = self.read_byte("7-bit string-length prefix")
            if shift == 28 and byte > 7:
                raise ValueError("Invalid 7-bit string-length prefix: exceeds a signed 32-bit length.")
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                if shift and byte == 0:
                    raise ValueError("Noncanonical 7-bit string-length prefix; editing would normalize it.")
                return value

    def read_string(self):
        raw = self.read_bytes(self.read_7bit_encoded_int(), "UTF-8 string")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Malformed UTF-8 string; editing would alter its bytes.") from exc

    def read_byte_array(self, field="byte array"):
        return self.read_bytes(self.read_int32(), field)

    def read_num_items(self):
        first = self.read_byte("compact item count")
        if first < 128:
            return first
        count = ((first & 0x7F) << 8) | self.read_byte("compact item count")
        if count < 128:
            raise ValueError("Noncanonical compact item count; editing would normalize it.")
        return count

    def read_count(self, field, minimum_item_bytes):
        count = self.read_int32()
        if count < 0:
            raise ValueError(f"Invalid {field} count: {count}.")
        self.check_remaining(count * minimum_item_bytes, field)
        return count

    def read_dictionary(self, count, read_key, read_value, field, *, game_rejects=False):
        values = {}
        for _ in range(count):
            key = read_key()
            if key in values:
                reason = "Valheim rejects duplicates" if game_rejects else "Valheim keeps the last value"
                raise ValueError(f"Duplicate key {key!r} in {field}. {reason}; editing is unavailable.")
            values[key] = read_value()
        return values


class BinaryWriter:
    def __init__(self):
        self.stream = io.BytesIO()

    def get_bytes(self):
        return self.stream.getvalue()

    def write_bytes(self, data):
        self.stream.write(data)

    def write_byte(self, value, field="byte"):
        self.stream.write(bytes([require_int(value, 0, 255, field)]))

    def write_ushort(self, value, field="unsigned 16-bit integer"):
        self.stream.write(struct.pack("<H", require_int(value, 0, 65535, field)))

    def write_int32(self, value, field="signed 32-bit integer"):
        self.stream.write(struct.pack("<i", require_int(value, -INT32_MAX - 1, INT32_MAX, field)))

    def write_long(self, value, field="signed 64-bit integer"):
        self.stream.write(struct.pack("<q", require_int(value, -(1 << 63), (1 << 63) - 1, field)))

    def write_bool(self, value, field="boolean"):
        self.stream.write(b"\x01" if require_bool(value, field) else b"\x00")

    def write_float(self, value, field="binary32 value"):
        if isinstance(value, NonfiniteFloat):
            raw = value.raw
        elif isinstance(value, dict) and set(value) == {"float32_hex"}:
            raw = decode_hex(value["float32_hex"], field)
            if len(raw) != 4 or math.isfinite(struct.unpack("<f", raw)[0]):
                raise ValueError(f"{field}.float32_hex must contain four little-endian bytes for a nonfinite value.")
        else:
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError(f"{field} must be a number.")
            try:
                raw = struct.pack("<f", value)
            except (OverflowError, struct.error) as exc:
                raise ValueError(f"{field} is outside the binary32 range.") from exc
        self.stream.write(raw)

    def write_vector3(self, value, field="vector"):
        channels = require_array(value, field)
        if len(channels) != 3:
            raise ValueError(f"{field} must contain exactly three binary32 components.")
        for index, channel in enumerate(channels):
            self.write_float(channel, f"{field}[{index}]")

    def write_7bit_encoded_int(self, value, field="string length"):
        require_int(value, 0, INT32_MAX, field)
        while value >= 0x80:
            self.write_byte((value & 0x7F) | 0x80)
            value >>= 7
        self.write_byte(value)

    def write_string(self, value, field="string"):
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string.")
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{field} contains invalid Unicode.") from exc
        self.write_7bit_encoded_int(len(encoded), f"{field} byte length")
        self.stream.write(encoded)

    def write_byte_array(self, data, field="byte array"):
        if not isinstance(data, bytes):
            raise ValueError(f"{field} must contain bytes.")
        self.write_int32(len(data), f"{field} length")
        self.stream.write(data)

    def write_num_items(self, count):
        require_int(count, 0, 32767, "item custom_data count")
        if count < 128:
            self.write_byte(count)
        else:
            self.write_byte((count >> 8) | 0x80)
            self.write_byte(count & 0xFF)

    def write_dictionary(self, value, write_key, write_value, field):
        entries = require_object(value, field)
        self.write_int32(len(entries), f"{field} count")
        for key, value in entries.items():
            write_key(key, f"{field} key")
            write_value(value, f"{field}[{key!r}]")
