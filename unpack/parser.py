import base64
import struct


def parse_unity_catalog(catalog):
    def b642bytes(s):
        return bytearray(base64.b64decode(s))

    class ByteReader:
        __slots__ = ["data", "pos"]

        def __init__(self, data):
            self.data = data
            self.pos = 0

        def read(self, ln):
            res = self.data[self.pos : self.pos + ln]
            self.pos += ln
            return res

        def read_int32(self):
            return struct.unpack("<i", self.read(4))[0]

    key_bytes = b642bytes(catalog["m_KeyDataString"])
    bucket_bytes = b642bytes(catalog["m_BucketDataString"])
    entry_bytes = b642bytes(catalog["m_EntryDataString"])

    reader = ByteReader(bucket_bytes)
    bucket_count = reader.read_int32()
    table = []

    for _ in range(bucket_count):
        key_pos = reader.read_int32()
        key_type = key_bytes[key_pos] if key_pos < len(key_bytes) else -1
        curr_kp = key_pos + 1
        key_val = None

        if key_type in (0, 1):
            str_len = key_bytes[curr_kp] if curr_kp < len(key_bytes) else 0
            curr_kp += 4
            s_byte = key_bytes[curr_kp : curr_kp + str_len]
            if key_type == 0:
                key_val = bytes(s_byte).decode("utf-8", errors="ignore")
            else:
                key_val = bytes(s_byte).decode("utf-16-le", errors="ignore")
        elif key_type == 4:
            key_val = key_bytes[curr_kp] if curr_kp < len(key_bytes) else 0

        entry_val = 65535
        entry_count = reader.read_int32()
        for _ in range(entry_count):
            entry_pos = reader.read_int32()
            entry_start = 4 + 28 * entry_pos
            e_byte = entry_bytes[entry_start + 8 : entry_start + 10]
            entry_val = struct.unpack("<H", bytes(e_byte))[0] if len(e_byte) == 2 else 65535

        table.append([key_val, entry_val])

    for i in range(len(table)):
        val = table[i][1]
        if val != 65535 and 0 <= val < len(table):
            table[i][1] = table[val][0]

    return table
