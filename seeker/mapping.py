"""Decide which channel-rack channel plays which drum role, by channel name."""

import re

_W = r"(?:^|[^a-z])"
_E = r"(?:[^a-z]|$)"

# Order matters: "Open Hat" must be claimed before the generic hat rule sees it.
_RULES = [
    ("openhat", r"open|" + _W + r"(?:oh|ohh|ophat)" + _E),
    ("hat", r"hat|" + _W + r"(?:hh|chh)" + _E),
    ("kick", r"kick|kik|bass ?drum|" + _W + r"(?:bd|kck)" + _E),
    ("snare", r"snare|snr|" + _W + r"(?:sd|sn)" + _E),
    ("clap", r"clap|clp|snap"),
    ("perc", r"perc|rim|shaker|shk|conga|bongo|cowbell|clave|tamb|stick|block|"
             r"triangle|cabasa|maraca|guiro|" + _W + r"toms?" + _E),
    # Chords go to the piano roll of this channel, never its step sequencer.
    ("chords", r"keys|piano|chord|rhodes|organ|wurli"),
    # Last, so "808 Kick" / "Bass Drum" stay drums and only a bare 808 is the bass.
    ("bass", r"808|bass|reese|log ?drum|" + _W + r"sub" + _E),
    # After the bass, so a "Synth Bass" stays a bass. Also piano roll only.
    ("pad", r"synth|pad|string|ambien|atmos|choir"),
]
_RULES = [(role, re.compile(rx)) for role, rx in _RULES]


def detect_role(name):
    low = name.lower()
    for role, rx in _RULES:
        if rx.search(low):
            return role
    return None


INSTRUMENTS = ("chords", "pad")


def map_rack(channels):
    """channels: [{'index', 'name', 'plugin'}] -> {role: channel dict}.

    The channel name decides first (first match wins). Instrument channels are
    usually named after their preset ("default", "Padilion"), which says nothing,
    so the instruments a name didn't place are then tried by their plugin
    ("FL Keys" plays the chords), and after that simply in rack order: the
    first spare instrument plays the chords, the next one the pad.
    Samplers with unknown names are never touched.
    """
    out, used = {}, set()
    for ch in channels:
        role = detect_role(ch["name"])
        if role and role not in out:
            out[role] = ch
        if role:
            used.add(ch["index"])
    spare = [ch for ch in channels if ch["index"] not in used and ch.get("plugin")]
    for ch in list(spare):
        role = detect_role(ch["plugin"])
        if role in INSTRUMENTS and role not in out:
            out[role] = ch
            spare.remove(ch)
    for role in INSTRUMENTS:
        if role not in out and spare:
            out[role] = spare.pop(0)
    return out


def _merge(a, b):
    return [max(x, y) for x, y in zip(a, b)]


def build_tracks(lanes, rolemap, pitches=None):
    """Lay a beat's lanes onto the channels this rack actually has.

    Every mapped drum channel gets a track, even an empty one, so the previous
    beat is cleared from it. Snare and clap cover for each other when only one
    exists. The bass channel is only touched when `lanes` has a bass lane, so
    switching the 808 off leaves a hand-made bassline alone. `pitches` maps a
    role to its MIDI note per step. Returns (tracks, missing_roles).
    """
    steps = len(next(iter(lanes.values())))
    silent = [0] * steps
    rolemap = {r: ch for r, ch in rolemap.items()
               if r not in ("chords", "pad") and (r != "bass" or "bass" in lanes)}
    play = {role: list(lanes.get(role, silent)) for role in rolemap}

    if "snare" in rolemap and "clap" not in rolemap:
        play["snare"] = _merge(lanes["snare"], lanes["clap"])
    elif "clap" in rolemap and "snare" not in rolemap:
        # Ghost notes on a clap sound like mistakes - keep only the real hits.
        backbeat = [v if v >= 80 else 0 for v in lanes["snare"]]
        play["clap"] = _merge(backbeat, lanes["clap"])

    tracks = []
    for role, ch in rolemap.items():
        vel = play[role]
        tracks.append({
            "channel": ch["index"], "name": ch["name"], "role": role,
            "bits": [1 if v else 0 for v in vel],
            "vel": [v or 100 for v in vel],
        })
        if pitches and role in pitches:
            tracks[-1]["pitch"] = list(pitches[role])
    missing = [r for r in lanes if r not in rolemap and any(lanes[r])
               and not (r in ("snare", "clap") and ("snare" in rolemap or "clap" in rolemap))]
    return tracks, missing
