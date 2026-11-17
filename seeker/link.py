"""MIDI SysEx link to the FL Studio script, plus settings and script installation.

FL Studio's controller-script interpreter blocks file access, so the two sides
talk over a pair of virtual MIDI ports (loopMIDI):

    "Pattern Seeker In"   app -> FL   (FL input, Controller type "Pattern Seeker")
    "Pattern Seeker Out"  FL -> app   (FL output with the same port number)

Uses winmm through ctypes, so there is nothing to pip install.
"""

import atexit
import ctypes
import json
import os
import queue
import re
import shutil
import time
from ctypes import wintypes

from . import wire

ROOT = os.path.join(os.environ.get("LOCALAPPDATA")
                    or os.path.join(os.path.expanduser("~"), "AppData", "Local"),
                    "PatternSeeker")
SCRIPT_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "fl_script", "device_PatternSeeker.py")
ALIVE_SECONDS = 3.0
RETRY_SECONDS = 2.0
PORT_TO_FL = "Pattern Seeker In"
PORT_FROM_FL = "Pattern Seeker Out"

MIM_LONGDATA = 0x3C4
MHDR_DONE = 1
CALLBACK_FUNCTION = 0x30000
IN_BUFFERS, IN_BUFFER_SIZE = 32, 4096


class MIDIHDR(ctypes.Structure):
    _pack_ = 1      # mmsystem.h is byte-packed
    _fields_ = [("lpData", ctypes.c_void_p), ("dwBufferLength", wintypes.DWORD),
                ("dwBytesRecorded", wintypes.DWORD), ("dwUser", ctypes.c_size_t),
                ("dwFlags", wintypes.DWORD), ("lpNext", ctypes.c_void_p),
                ("reserved", ctypes.c_size_t), ("dwOffset", wintypes.DWORD),
                ("dwReserved", ctypes.c_size_t * 8)]


class MIDIOUTCAPS(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT), ("szPname", ctypes.c_wchar * 32),
                ("wTechnology", wintypes.WORD), ("wVoices", wintypes.WORD),
                ("wNotes", wintypes.WORD), ("wChannelMask", wintypes.WORD),
                ("dwSupport", wintypes.DWORD)]


class MIDIINCAPS(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT), ("szPname", ctypes.c_wchar * 32),
                ("dwSupport", wintypes.DWORD)]


_IN_PROC = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t,
                              ctypes.c_size_t, ctypes.c_size_t)
_HDR_SIZE = ctypes.sizeof(MIDIHDR)
_winmm = None


def _mm():
    global _winmm
    if _winmm is None:
        w = ctypes.WinDLL("winmm")
        h, u, p = ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p
        for name, args in (
                ("midiOutGetDevCapsW", [ctypes.c_size_t, p, u]),
                ("midiInGetDevCapsW", [ctypes.c_size_t, p, u]),
                ("midiOutOpen", [p, u, ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD]),
                ("midiInOpen", [p, u, _IN_PROC, ctypes.c_size_t, wintypes.DWORD]),
                ("midiOutPrepareHeader", [h, p, u]), ("midiOutUnprepareHeader", [h, p, u]),
                ("midiOutLongMsg", [h, p, u]), ("midiOutReset", [h]), ("midiOutClose", [h]),
                ("midiInPrepareHeader", [h, p, u]), ("midiInUnprepareHeader", [h, p, u]),
                ("midiInAddBuffer", [h, p, u]), ("midiInStart", [h]),
                ("midiInReset", [h]), ("midiInClose", [h])):
            fn = getattr(w, name)
            fn.argtypes, fn.restype = args, u
        _winmm = w
    return _winmm


def _find(kind, wanted):
    """Device id of the MIDI port called `wanted` (exact, else substring), or None."""
    mm = _mm()
    count = (mm.midiOutGetNumDevs if kind == "out" else mm.midiInGetNumDevs)()
    caps = MIDIOUTCAPS() if kind == "out" else MIDIINCAPS()
    get = mm.midiOutGetDevCapsW if kind == "out" else mm.midiInGetDevCapsW
    names = []
    for i in range(count):
        if get(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            names.append((i, caps.szPname.lower()))
    wanted = wanted.lower()
    for i, name in names:
        if name == wanted:
            return i
    for i, name in names:
        if wanted in name:
            return i
    return None


class MidiLink:
    """Both directions of the SysEx link. Call pump() regularly from one thread."""

    def __init__(self, to_fl=PORT_TO_FL, from_fl=PORT_FROM_FL):
        self.to_fl, self.from_fl = to_fl, from_fl
        self.problem = "not connected yet"
        self._out = self._in = None
        self._closing = False
        self._raw = queue.Queue()
        self._asm = wire.Assembler()
        self._headers, self._buffers = [], []
        self._proc = _IN_PROC(self._on_midi)     # keep a reference for winmm
        self._last_try = 0.0
        self._msg_id = 0
        self._hb, self._hb_at = None, 0.0
        self._responses = {}

    # ---- connection ---------------------------------------------------
    def _connect(self):
        self._last_try = time.monotonic()
        mm = _mm()
        if self._in is None:
            dev = _find("in", self.from_fl)
            if dev is None:
                self.problem = "MIDI port '%s' not found - create it in loopMIDI" % self.from_fl
                return
            handle = ctypes.c_void_p()
            err = mm.midiInOpen(ctypes.byref(handle), dev, self._proc, 0, CALLBACK_FUNCTION)
            if err:
                self.problem = "can't open MIDI port '%s' (error %d) - is another app " \
                               "using it?" % (self.from_fl, err)
                return
            self._closing = False
            self._headers, self._buffers = [], []
            for _ in range(IN_BUFFERS):
                buf = ctypes.create_string_buffer(IN_BUFFER_SIZE)
                hdr = MIDIHDR(lpData=ctypes.addressof(buf), dwBufferLength=IN_BUFFER_SIZE)
                mm.midiInPrepareHeader(handle, ctypes.byref(hdr), _HDR_SIZE)
                mm.midiInAddBuffer(handle, ctypes.byref(hdr), _HDR_SIZE)
                self._buffers.append(buf)
                self._headers.append(hdr)
            mm.midiInStart(handle)
            self._in = handle
        if self._out is None:
            dev = _find("out", self.to_fl)
            if dev is None:
                self.problem = "MIDI port '%s' not found - create it in loopMIDI" % self.to_fl
                return
            handle = ctypes.c_void_p()
            err = mm.midiOutOpen(ctypes.byref(handle), dev, 0, 0, 0)
            if err:
                self.problem = "can't open MIDI port '%s' (error %d) - is another app " \
                               "using it?" % (self.to_fl, err)
                return
            self._out = handle
        self.problem = ""

    def _on_midi(self, handle, msg, instance, p1, p2):
        # Runs on a winmm thread: copy the packet out and hand the buffer back.
        if msg != MIM_LONGDATA or not p1:
            return
        hdr = MIDIHDR.from_address(p1)
        if hdr.dwBytesRecorded:
            self._raw.put(ctypes.string_at(hdr.lpData, hdr.dwBytesRecorded))
        if not self._closing:
            _mm().midiInAddBuffer(handle, p1, _HDR_SIZE)

    def close(self):
        mm = _mm()
        self._closing = True
        if self._in is not None:
            mm.midiInReset(self._in)
            for hdr in self._headers:
                mm.midiInUnprepareHeader(self._in, ctypes.byref(hdr), _HDR_SIZE)
            mm.midiInClose(self._in)
            self._in = None
        if self._out is not None:
            mm.midiOutReset(self._out)
            mm.midiOutClose(self._out)
            self._out = None

    # ---- traffic ------------------------------------------------------
    def pump(self):
        if (self._in is None or self._out is None) \
                and time.monotonic() - self._last_try >= RETRY_SECONDS:
            self._connect()
        while True:
            try:
                packet = self._raw.get_nowait()
            except queue.Empty:
                break
            done = self._asm.feed(packet)
            if not done:
                continue
            kind, payload = done
            if kind == wire.HEARTBEAT:
                self._hb, self._hb_at = payload, time.monotonic()
            elif kind == wire.RESPONSE:
                self._responses[payload.get("id")] = payload
                if payload.get("state"):
                    self._hb, self._hb_at = payload["state"], time.monotonic()

    def heartbeat(self):
        self.pump()
        if self._hb and time.monotonic() - self._hb_at < ALIVE_SECONDS:
            return self._hb
        return None

    def send(self, request):
        self.pump()
        if self._out is None:
            return False
        mm = _mm()
        self._msg_id = (self._msg_id + 1) % 128
        for packet in wire.encode(wire.REQUEST, self._msg_id, request):
            buf = ctypes.create_string_buffer(packet, len(packet))
            hdr = MIDIHDR(lpData=ctypes.addressof(buf), dwBufferLength=len(packet),
                          dwBytesRecorded=len(packet))
            err = mm.midiOutPrepareHeader(self._out, ctypes.byref(hdr), _HDR_SIZE) \
                or mm.midiOutLongMsg(self._out, ctypes.byref(hdr), _HDR_SIZE)
            deadline = time.monotonic() + 0.5
            while not err and not hdr.dwFlags & MHDR_DONE and time.monotonic() < deadline:
                time.sleep(0.001)
            mm.midiOutUnprepareHeader(self._out, ctypes.byref(hdr), _HDR_SIZE)
            if err:
                # The port went away (loopMIDI closed?) - reopen on the next pump.
                mm.midiOutClose(self._out)
                self._out = None
                self.problem = "lost MIDI port '%s'" % self.to_fl
                return False
        return True

    def response(self, request_id):
        self.pump()
        return self._responses.pop(request_id, None)


_link = None


def _get():
    global _link
    if _link is None:
        s = load_settings()
        _link = MidiLink(s.get("portToFL", PORT_TO_FL), s.get("portFromFL", PORT_FROM_FL))
        atexit.register(_link.close)
    return _link


def heartbeat():
    """Latest rack snapshot from FL, or None if the script isn't answering."""
    return _get().heartbeat()


def problem():
    """Why the MIDI ports aren't usable ('' when they are open)."""
    return _get().problem


def send(request):
    """Send a request to FL; returns the id to pass to `response`."""
    request = dict(request, id="%d" % time.time_ns())
    _get().send(request)
    return request["id"]


def response(request_id):
    return _get().response(request_id)


def cancel():
    pass    # nothing is queued on our side; a late answer is simply dropped


def close():
    if _link is not None:
        _link.close()


def _path(name):
    os.makedirs(ROOT, exist_ok=True)
    return os.path.join(ROOT, name)


def load_settings():
    try:
        with open(_path("settings.json"), "r") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    with open(_path("settings.json"), "w") as fh:
        json.dump(settings, fh, indent=1)


def script_version():
    with open(SCRIPT_SRC, "r") as fh:
        m = re.search(r"^SCRIPT_VERSION\s*=\s*(\d+)", fh.read(), re.M)
    return int(m.group(1)) if m else 0


def _documents():
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_PERSONAL
    return buf.value or os.path.join(os.path.expanduser("~"), "Documents")


def install_script():
    """Copy the FL script into FL's Hardware folder if missing or outdated.

    Returns 'installed', 'updated', 'current', or 'no-fl' when FL Studio's
    settings folder can't be found.
    """
    hardware = os.path.join(_documents(), "Image-Line", "FL Studio", "Settings", "Hardware")
    if not os.path.isdir(hardware):
        return "no-fl"
    dest_dir = os.path.join(hardware, "Pattern Seeker")
    dest = os.path.join(dest_dir, os.path.basename(SCRIPT_SRC))
    with open(SCRIPT_SRC, "rb") as fh:
        wanted = fh.read()
    existed = os.path.isfile(dest)
    if existed:
        with open(dest, "rb") as fh:
            if fh.read() == wanted:
                return "current"
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copyfile(SCRIPT_SRC, dest)
    return "updated" if existed else "installed"
