"""Decide which channel-rack channel plays which part, by channel name.

detect_role says what a channel is (a kick, a bass, keys ...). fit_rack then
picks, for a genre, the one channel per part whose sound suits it (kits.py).
"""

import re

from seeker import kits

_W = r"(?:^|[^a-z])"
_E = r"(?:[^a-z]|$)"

# Order matters: "Open Hat" must be claimed before the generic hat rule sees it.
_RULES = [
    ("openhat", r"open|" + _W + r"(?:oh|ohh|ophat)" + _E),
    ("hat", r"hat|" + _W + r"(?:hh|chh|ride)" + _E),      # jazz keeps time on the ride
    ("kick", r"kick|kik|bass ?drum|" + _W + r"(?:bd|kck)" + _E),
    ("snare", r"snare|snr|" + _W + r"(?:sd|sn)" + _E),
    ("clap", r"clap|clp|snap"),
    ("perc", r"perc|rim|shaker|shk|conga|bongo|cowbell|clave|tamb|stick|block|"
             r"triangle|cabasa|maraca|guiro|" + _W + r"toms?" + _E),
    # Chords go to the piano roll of this channel, never its step sequencer.
    ("chords", r"keys|piano|chord|rhodes|organ|wurli|harpsichord"),
    # Last, so "808 Kick" / "Bass Drum" stay drums and only a bare 808 is the bass.
    ("bass", r"808|bass|reese|log ?drum|cello|upright|" + _W + r"sub" + _E),
    # After the bass, so a "Bass Guitar" stays a bass.
    ("guitar", r"guitar|gtr|" + _W + r"(?:tele|strat)" + _E),
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


def fit_rack(channels, genre, strict=False):
    """The channels a beat of `genre` is written to: ({role: channel}, idle).

    Per part, in order of preference: a channel whose style the genre accepts
    ("Rock Kick" for rock), then a plainly named one ("Kick"), then - unless
    `strict`, which is how a rack is built - one of another style, as long as
    it isn't a machine or a synth under an acoustic genre (kits.fallback_ok).
    A part the genre doesn't have gets no channel.

    `idle` are the step-sequencer channels of other kits: recognised drums and
    basses that sit this beat out and must be silenced in its pattern.
    """
    accepts = kits.accepts(genre)
    by_role, used = {}, set()
    for ch in channels:
        role = detect_role(ch["name"])
        if role:
            by_role.setdefault(role, []).append(ch)
            used.add(ch["index"])
    out, idle = {}, []
    for role, found in by_role.items():
        styled = [(ch, kits.style_of(role, ch["name"])) for ch in found]
        plain = [ch for ch, style in styled if style is None][:1]
        pick = None
        if role in accepts:
            fits = [ch for ch, style in styled if style in accepts[role]]
            other = [] if strict else [ch for ch, style in styled if style is not None
                                       and kits.fallback_ok(genre, role, style)]
            pick = (fits + plain + other + [None])[0]
        if pick:
            out[role] = pick
        if role in kits.STEP_ROLES:
            idle += [ch for ch, style in styled
                     if ch is not pick and (style is not None or ch in plain)]
    if not strict:
        # Instruments named after their preset ("default", "Padilion") say nothing:
        # try their plugin ("FL Keys" plays the chords), then plain rack order.
        spare = [ch for ch in channels if ch["index"] not in used and ch.get("plugin")]
        for ch in list(spare):
            role = detect_role(ch["plugin"])
            if role in INSTRUMENTS and role in accepts and role not in out:
                out[role] = ch
                spare.remove(ch)
        for role in INSTRUMENTS:
            if role in accepts and role not in out and spare:
                out[role] = spare.pop(0)
    return out, idle


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
               if r in kits.STEP_ROLES and (r != "bass" or "bass" in lanes)}
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
