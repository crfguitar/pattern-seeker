"""SysEx framing shared by the companion app and (duplicated in) the FL script.

One message = one JSON object, sent as ASCII in one or more SysEx packets:

    F0 7D 50 53  kind  id  index  total  <json bytes>  F7

7D is the non-commercial manufacturer id; 50 53 is "PS". json.dumps emits pure
ASCII, so every data byte is already 7-bit clean.
"""

import json

MAGIC = b"\xF0\x7D\x50\x53"
REQUEST, RESPONSE, HEARTBEAT = 1, 2, 3
CHUNK = 800     # stays well under the 1024-byte SysEx buffers some drivers use


def encode(kind, msg_id, payload):
    """Return the list of SysEx packets carrying `payload`."""
    data = json.dumps(payload, separators=(",", ":")).encode("ascii")
    total = max(1, -(-len(data) // CHUNK))
    if total > 127:
        raise ValueError("message too large for the SysEx link")
    return [MAGIC + bytes((kind, msg_id & 0x7F, i, total))
            + data[i * CHUNK:(i + 1) * CHUNK] + b"\xF7" for i in range(total)]


class Assembler:
    """Rebuilds messages from packets; feed() returns (kind, payload) when one completes."""

    def __init__(self):
        self._parts = {}    # kind -> (msg id, {index: bytes})

    def feed(self, packet):
        packet = bytes(packet)
        if len(packet) < 9 or packet[:4] != MAGIC:
            return None
        kind, msg_id, index, total = packet[4:8]
        body = packet[8:-1] if packet[-1] == 0xF7 else packet[8:]
        held = self._parts.get(kind)
        if held is None or held[0] != msg_id or index == 0:
            held = (msg_id, {})
            self._parts[kind] = held
        held[1][index] = body
        if len(held[1]) < total:
            return None
        del self._parts[kind]
        try:
            data = b"".join(held[1][i] for i in range(total))
            return kind, json.loads(data.decode("ascii"))
        except (KeyError, ValueError):
            return None
