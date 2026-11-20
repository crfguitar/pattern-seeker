"""Instruments and samples on this PC, and how a new one gets into FL's rack.

FL's scripting API cannot add a channel or load a plugin. What does work (seen
live in FL Studio 2026): start FL's own program with a preset file (.fst) as its
argument. The FL that is already running takes the file and opens it in a NEW
channel - a plugin with its preset, or a sampler.

    instruments  every generator FL has scanned (FL's plugin database keeps one
                 .fst per plugin, VSTs included), the presets you saved, and the
                 channel presets and plugin presets FL ships (thousands: "Plugin
                 presets/Sytrus/...", "Plugin presets/FL Keys/ePiano")
    samples      FL's stock packs plus the folders in settings.json "sampleFolders".
                 A bare .wav handed to FL is ignored, so a small sampler preset
                 that names the sample is written first (sampler_preset)
    FLEX         every preset of every installed FLEX pack ("FLEX/Essential
                 Strings/Cellos Staccato"). FLEX saves its state as a fixed block
                 that names the pack and the preset, so a preset file for any of
                 them can be written (flex_preset)
"""

import os
import re
import struct
import subprocess

from seeker import link, pianoroll

SAMPLE_EXT = (".wav", ".mp3", ".ogg", ".flac", ".aif", ".aiff", ".wv")
PLUGIN_TYPES = ("Fruity", "VST3", "VST", "CLAP")    # the one kept when a plugin has several
SAMPLE_NAME_EVENT = 196     # FLP event: a sampler's sample file
CHANNEL_NAME_EVENT = 192
_cache = {}


class SoundError(Exception):
    """Plain words for whoever asked."""


def _presets():
    return os.path.join(link._documents(), "Image-Line", "FL Studio", "Presets")


def fl_folder():
    """The folder of the FL Studio that is running, or None."""
    exe = pianoroll.fl_exe()
    return os.path.dirname(exe) if exe else None


def _walk(root, exts):
    for folder, _, files in os.walk(root):
        for f in sorted(files, key=str.lower):
            if f.lower().endswith(exts):
                yield os.path.join(folder, f)


def _item(kind, root, path, prefix=""):
    rel = os.path.splitext(os.path.relpath(path, root))[0].replace(os.sep, "/")
    return {"kind": kind, "name": os.path.basename(rel), "id": prefix + rel, "path": path}


def _instruments(fl):
    out, seen = [], set()
    installed = os.path.join(_presets(), "Plugin database", "Installed", "Generators")
    for kind in PLUGIN_TYPES:
        for path in _walk(os.path.join(installed, kind), (".fst",)):
            item = _item("instrument", installed, path)
            if item["name"].lower() not in seen:
                seen.add(item["name"].lower())
                out.append(item)
    # Presets the user saved: plugin-database favourites that aren't just a plugin's
    # default, their channel presets, and the channel presets FL ships.
    saved = os.path.join(_presets(), "Plugin database", "Generators")
    for path in _walk(saved, (".fst",)):
        item = _item("instrument", saved, path, "Saved/")
        if item["name"].lower() not in seen:
            seen.add(item["name"].lower())
            out.append(item)
    roots = [(os.path.join(_presets(), "Channel presets"), "My presets/"),
             (os.path.join(_presets(), "Plugin presets", "Generators"), "My plugin presets/")]
    if fl:
        patches = os.path.join(fl, "Data", "Patches")
        roots.append((os.path.join(patches, "Channel presets"), "Presets/"))
        # A plugin's own preset file opens the plugin with that preset loaded.
        roots.append((os.path.join(patches, "Plugin presets", "Generators"), "Plugin presets/"))
    for root, prefix in roots:
        out.extend(_item("instrument", root, p, prefix) for p in _walk(root, (".fst",)))
    return out


def _samples(fl):
    roots = []
    if fl:
        roots.append(os.path.join(fl, "Data", "Patches", "Packs"))
    roots += [r for r in (link.load_settings().get("sampleFolders") or []) if os.path.isdir(r)]
    out = []
    for root in roots:
        out.extend(_item("sample", root, p) for p in _walk(root, SAMPLE_EXT))
    return out


# ---- FLEX ------------------------------------------------------------------------

FLEX_STATE_SIZE = 2707
FLEX_NAME_AT = (16, 1041)       # pack name, preset name: zero-padded text fields
FLEX_NAME_ROOM = 1024
# The rest of a saved FLEX state, as (offset, bytes) runs: its header and a neutral
# set of macro knobs. The knobs are reset to the preset's own after loading (the
# engine steps one preset on and back), so their values here don't matter.
_FLEX_STATE = (
    (0, "01000000010000001208"),
    (2066, "010001"), (2078, "02000000020000001402"),
    (2098, "080200000000000002000000800000000000003f0000003f0000003f0000003f0000003f"
           "0000003f0000003f0000003f0000003f0000003f0000003f0000003f0000003f"),
    (2189, "3f0000003f0000003f0000803f0000003f0821843dabaa2a3f00000000abff7e3e0000003f"
           "0000000000f6283f00c4753e00d7233f0000003f000000000000a83d007b143f0000803f"
           "0000803f0000803f0000003f0000803f0000803f0000003f8988883d"),
    (2626, "03000000380000000000000001"), (2694, "0400000001"),
)
PLUGIN_STATE_EVENT, NEW_PLUGIN_EVENT = 213, 212
FLEX_DIRECTORY = 1 << 19        # a pack's list of presets sits within its first bytes


def _flex_folders(fl):
    out = [os.path.join(link._documents(), "Image-Line", "FLEX", "Packs")]
    if fl:
        out.append(os.path.join(fl, "Data", "Patches", "Packs", "FLEX", "Packs"))
    return out


def flex_pack_presets(path):
    """Preset names in a .flexpack / .flex2pack: its directory at the top of the
    file lists "<name>.flexpreset" entries, each behind a 4-byte length (which
    counts the closing zero)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(FLEX_DIRECTORY)
    except OSError:
        return []
    names = []
    for m in re.finditer(rb"[\x20-\x7e]{1,120}\.flex2?preset\x00", data):
        entry = m.group()[:-1]
        # the length's low byte is printable for long names, and gets matched too
        while entry and int.from_bytes(data[m.end() - 1 - len(entry) - 4:
                                            m.end() - 1 - len(entry)], "big") != len(entry) + 1:
            entry = entry[1:]
        if entry:
            names.append(entry.rsplit(b".", 1)[0].decode("latin-1"))
    return names


def _flex(fl):
    out, seen = [], set()
    for folder in _flex_folders(fl):
        try:
            packs = sorted(f for f in os.listdir(folder)
                           if f.lower().endswith((".flexpack", ".flex2pack")))
        except OSError:
            continue
        for f in packs:
            pack = os.path.splitext(f)[0]
            if pack.lower() in seen:
                continue
            seen.add(pack.lower())
            for preset in flex_pack_presets(os.path.join(folder, f)):
                out.append({"kind": "instrument", "name": preset,
                            "id": "FLEX/%s/%s" % (pack, preset), "flex": (pack, preset),
                            "path": os.path.join(folder, f)})
    return out


def flex_state(pack, preset):
    """The bytes FLEX saves when `preset` of `pack` is loaded."""
    state = bytearray(FLEX_STATE_SIZE)
    for at, run in _FLEX_STATE:
        state[at:at + len(run) // 2] = bytes.fromhex(run)
    for at, text in zip(FLEX_NAME_AT, (pack, preset)):
        try:
            raw = text.encode("latin-1")
        except UnicodeError:
            raise SoundError("FLEX preset name %r can't be written." % text)
        if len(raw) > FLEX_NAME_ROOM:
            raise SoundError("FLEX preset name %r is too long." % text)
        state[at:at + len(raw)] = raw
    return bytes(state)


def flex_bytes(template, pack, preset):
    """`template` (the plugin database's empty FLEX preset) with a state added."""
    header, events = _events(template)
    if not any(i == NEW_PLUGIN_EVENT for i, _ in events):
        raise SoundError("FL's FLEX preset has an unexpected layout.")
    body = bytearray()
    for ident, value in events:
        if ident == PLUGIN_STATE_EVENT:
            continue
        body += bytes([ident]) + (_varint(len(value)) if ident >= 192 else b"") + value
        if ident == NEW_PLUGIN_EVENT:
            state = flex_state(pack, preset)
            body += bytes([PLUGIN_STATE_EVENT]) + _varint(len(state)) + state
    return header + b"FLdt" + struct.pack("<I", len(body)) + bytes(body)


def flex_preset(pack, preset):
    """Write the preset file that opens FLEX on `preset`; returns its path."""
    template = os.path.join(_presets(), "Plugin database", "Installed", "Generators",
                            "Fruity", "FLEX.fst")
    try:
        with open(template, "rb") as fh:
            data = flex_bytes(fh.read(), pack, preset)
    except (OSError, ValueError, IndexError, struct.error):
        raise SoundError("Couldn't read FL's FLEX preset (%s)." % template)
    folder = os.path.join(link.ROOT, "load")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, "FLEX.fst")
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


def catalog():
    """Every instrument, then every sample: [{kind, name, id, path}]."""
    fl = fl_folder()
    key = (fl, tuple(link.load_settings().get("sampleFolders") or []))
    if key not in _cache:
        _cache.clear()
        _cache[key] = _instruments(fl) + _flex(fl) + _samples(fl)
    return _cache[key]


def search(text="", kind="all", items=None):
    """Items whose id holds every word of `text` (any order, any case)."""
    words = (text or "").lower().split()
    kind = (kind or "all").strip().lower().rstrip("s")
    return [it for it in (catalog() if items is None else items)
            if kind in ("all", "any", "", it["kind"])
            and all(w in it["id"].lower() for w in words)]


def resolve(sound, items=None):
    """One catalog item for what was asked: a file path, an id ('Drums/Kicks/909
    Kick'), a name ('FLEX'), or search words that fit exactly one sound."""
    text = (sound or "").strip().strip('"')
    if not text:
        raise SoundError("Say which instrument or sample (see list_sounds).")
    if os.path.isfile(text):
        ext = os.path.splitext(text)[1].lower()
        if ext == ".fst" or ext in SAMPLE_EXT:
            name = os.path.splitext(os.path.basename(text))[0]
            return {"kind": "instrument" if ext == ".fst" else "sample",
                    "name": name, "id": name, "path": os.path.abspath(text)}
        raise SoundError("%s is not a preset (.fst) or an audio file." % text)
    items = catalog() if items is None else items
    want = text.lower().replace("\\", "/")
    for field in ("id", "name"):
        hits = [it for it in items if it[field].lower() == want]
        if hits:
            return hits[0]          # instruments come first in the catalog
    hits = search(text, items=items)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SoundError("No instrument or sample matches %r. Try list_sounds." % sound)
    raise SoundError("%d sounds match %r - use one id: %s%s" % (
        len(hits), sound, "; ".join(it["id"] for it in hits[:8]),
        " ..." if len(hits) > 8 else ""))


# ---- a sampler preset for one sample -------------------------------------------

def _events(data):
    """(header bytes, [(event id, payload)]) of an FL preset/project file."""
    if data[:4] != b"FLhd":
        raise ValueError("not an FL file")
    p = 8 + struct.unpack("<I", data[4:8])[0]
    if data[p:p + 4] != b"FLdt":
        raise ValueError("no data chunk")
    header, end = data[:p], p + 8 + struct.unpack("<I", data[p + 4:p + 8])[0]
    p += 8
    out = []
    while p < end:
        ident = data[p]
        p += 1
        if ident < 192:
            size = 1 if ident < 64 else 2 if ident < 128 else 4
        else:
            size = shift = 0
            while True:
                byte = data[p]
                p += 1
                size |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
        out.append((ident, data[p:p + size]))
        p += size
    return header, out


def _varint(n):
    out = bytearray()
    while True:
        out.append((n & 0x7F) | (0x80 if n > 0x7F else 0))
        n >>= 7
        if not n:
            return bytes(out)


def sampler_bytes(template, sample_path, name):
    """`template` (FL's default sampler preset) with a name and a sample put in.

    The template is in FL's old text format, where strings are ANSI: a path or
    name that Windows' ANSI code page cannot spell raises SoundError."""
    try:
        sample = sample_path.encode("mbcs", "strict") + b"\0"
        label = name.encode("mbcs", "strict") + b"\0"
    except (UnicodeError, LookupError):
        raise SoundError("FL can't be given %r: its name has characters outside this "
                         "PC's ANSI code page. Rename the file." % sample_path)
    header, events = _events(template)
    events = [(i, v) for i, v in events if i != SAMPLE_NAME_EVENT]
    body = bytearray()
    placed = False
    for ident, value in events:
        if ident == CHANNEL_NAME_EVENT and not placed:
            value = label
        body += bytes([ident]) + (_varint(len(value)) if ident >= 192 else b"") + value
        if ident == CHANNEL_NAME_EVENT and not placed:
            placed = True
            body += bytes([SAMPLE_NAME_EVENT]) + _varint(len(sample)) + sample
    if not placed:
        raise SoundError("FL's default sampler preset has an unexpected layout.")
    return header + b"FLdt" + struct.pack("<I", len(body)) + bytes(body)


def sampler_preset(sample_path, name):
    """Write the preset that loads `sample_path` into a sampler; returns its path."""
    fl = fl_folder()
    template = os.path.join(fl or "", "Data", "Patches", "Channel presets", "Sampler",
                            "Default.fst")
    try:
        with open(template, "rb") as fh:
            data = sampler_bytes(fh.read(), sample_path, name)
    except (OSError, ValueError, IndexError, struct.error):
        raise SoundError("Couldn't read FL's default sampler preset (%s)." % template)
    folder = os.path.join(link.ROOT, "load")
    os.makedirs(folder, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "sample"
    dest = os.path.join(folder, safe + ".fst")
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


def open_in_fl(item, name=None):
    """Hand a catalog item to the running FL, which opens it in a new channel."""
    exe = pianoroll.fl_exe()
    if not exe:
        raise SoundError("Couldn't find the running FL Studio program.")
    path = item["path"]
    if item.get("flex"):
        path = flex_preset(*item["flex"])
    elif item["kind"] == "sample":
        path = sampler_preset(path, name or item["name"])
    # stdout is the MCP channel: the child must not inherit it.
    subprocess.Popen([exe, path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
