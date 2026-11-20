"""Which sounds make a genre's rack, and which channels fit a genre.

A genre's kit names a sound for each part it has: six drums, a bass, keys, a
pad, a guitar. Every sound has a STYLE word ("808", "Rock", "Cello", "Strings")
and the channel it is loaded into is named with that word ("Rock Kick",
"Cello", "808 Bass"). The name is how a channel is later recognised: a beat is
only written to channels whose style its genre accepts, so a classical piece
plays the cello and leaves the 808 silent, and one rack can hold several kits.

Sounds come from what FL Studio ships (stock samples and the HQ drum kits, 3x
Osc and FL Keys presets, BooBass, FLEX's General MIDI library) and from the
free FLEX packs (Essential / Core strings, bass guitars, guitars, pianos).
Options are listed best first; the ones not installed are skipped. Ids are the
ones `sounds.catalog()` gives. They were chosen from their names, not by ear.
"""

from collections import namedtuple

Sound = namedtuple("Sound", "style name options")
# style: the word that marks a channel as this kind of sound
# name: what the channel is called (it must contain the style word)

ROLES = ("kick", "snare", "clap", "hat", "openhat", "perc", "bass", "chords", "pad", "guitar")
DRUM_ROLES = ROLES[:6]
STEP_ROLES = DRUM_ROLES + ("bass",)         # written into the step sequencer

# role -> (plain channel name, colour, volume or None for FL's own)
CHANNELS = {
    "kick": ("Kick", "#C0504D", None), "snare": ("Snare", "#D9824F", None),
    "clap": ("Clap", "#D9A44F", None), "hat": ("Hat", "#D9C44F", None),
    "openhat": ("Open hat", "#B8C24F", None), "perc": ("Perc", "#8FB04F", None),
    "bass": ("Bass", "#8A5FBF", None), "chords": ("Keys", "#E0782F", 0.62),
    "pad": ("Pad", "#4F8FD9", 0.5), "guitar": ("Guitar", "#4FB8A8", 0.6),
}

K, S, H, P, C = ("Drums/Kicks/", "Drums/Snares/", "Drums/Hats/", "Drums/Percussion/",
                 "Drums/Cymbals/")
OSC, KEYS = "Presets/3x Osc/", "Plugin presets/FL Keys/"
DX10, SYTRUS = "Plugin presets/Fruity DX10/", "Plugin presets/Sytrus/"
GM = "FLEX/General Midi Library/"
STRINGS_PACK, CORE_STRINGS = "FLEX/Essential Strings/", "FLEX/Core Strings/STR "
BASS_PACK, CORE_BASS = "FLEX/Essential Bass Guitars/", "FLEX/Core Bass/BAS "
GUITAR_PACK, CORE_GUITAR = "FLEX/Essential Guitars/", "FLEX/Core Guitars/GTR "
PIANO_PACK, CORE_PIANO = "FLEX/Essential Pianos/", "FLEX/Core Pianos/KEY "
SYNTHS, SUBS = "FLEX/Core Synths/", "FLEX/Core 808s/"
BOOBASS = "Fruity/BooBass"
TAMBOURINE = [P + "Linn Tamb", P + "GM Tamb", P + "RD Tamb 2", P + "FPC Tamb"]


def _hq(kit, **pieces):
    """Samples of one of FL's HQ drum kits: eight takes per drum, soft to hard."""
    return {role: ["Drums/Kits/HQ %s Kit/%s HQ %s #%d" % (kit, piece, kit, take)
                   for take in (6, 7, 5)] for role, piece in pieces.items()}


# style -> the drums' options per role (+ "names": channel names that differ)
DRUMS = {
    "808": dict(kick=[K + "808 Kick"], snare=[S + "808 Snare"],
                clap=[P + "Grv Clap 01", P + "DNC Clap 1", P + "SC Clap"],
                hat=[H + "808 CH"], openhat=[H + "808 OH"],
                perc=[P + "808 Cowbell", P + "808 Clav", S + "707 Rim"]),
    "909": dict(kick=[K + "909 Kick"], snare=[S + "909 Snare"], clap=[P + "909 Clap"],
                hat=[H + "909 CH 1", H + "909 CH 2"], openhat=[H + "909 OH"],
                perc=[S + "909 Rim", P + "909 Clav", P + "RD Tamb 1"]),
    "Linn": dict(kick=[K + "Linn Kick", K + "707 Kick"], snare=[S + "Linn Snare", S + "707 Snare"],
                 clap=[P + "Pap Clap", P + "Ekit Clap 1"], hat=[H + "Linn CH", H + "707 CH"],
                 openhat=[H + "Linn OH", H + "707 OH"],
                 perc=[P + "Linn Tamb", P + "Linn Conga", P + "707 Cowbell"]),
    "Dusty": dict(kick=[K + "Grv Kick Acoustic 01", K + "22in Kick", K + "FPC 1 Kick"],
                  snare=[S + "FPC Snare 1", S + "Loose Snare", S + "Ring Snare"],
                  clap=[P + "Ekit Clap 1", P + "Pap Clap"], hat=[H + "Zild CH 1", H + "Stud CH 1"],
                  openhat=[H + "Zild OH"], perc=[S + "Stick Rim 1", P + "FPC Tamb", S + "14in Rim"]),
    "Break": dict(kick=[K + "Jung Kick"], snare=[S + "Jung Snare"], clap=[P + "SC Clap"],
                  hat=[H + "Jung Hat 1", H + "Jung Hat 2"], openhat=[H + "OverH OH"],
                  perc=[C + "Jung Ride", S + "Chromo Rim"]),
    "Afro": dict(kick=[K + "Grv Kick 03", K + "909 Kick"], snare=[S + "Linn Rim", S + "RD Rim"],
                 clap=[P + "Grv Clap 02", P + "909 Clap"], hat=[H + "Grv CH 01", H + "808 CH"],
                 openhat=[H + "Grv OH 01"],
                 perc=[P + "808 Conga", P + "Linn Conga", P + "Industrial Shaker",
                       P + "GM Cabasa"]),
    "Heavy": dict(kick=[K + "Monster Kick 002", K + "Nuked Kick"],
                  snare=[S + "Industrial Snare 1", S + "Nuked Snare"], clap=[P + "DNC Clap 2"],
                  hat=[H + "Clank CH 1", H + "Glotch CH"], openhat=[H + "Clank OH", H + "Glotch OH"],
                  perc=[P + "FPC Metal Hit", P + "Industrial Bongo"]),
    # The acoustic kits are FL's HQ kits, one sampler channel per drum.
    "Rock": dict(_hq("Rock", kick="Kick 1", snare="Snare Hit", hat="HH Closed", openhat="HH Open"),
                 clap=[P + "Pap Clap", P + "Ekit Clap 2"], perc=TAMBOURINE,
                 names={"perc": "Tambourine"}),
    "Acoustic": dict(_hq("Funk", kick="Kick 1", snare="Snare Hit", hat="HH Closed",
                         openhat="HH Open"),
                     clap=[P + "Pap Clap", P + "Ekit Clap 2"], perc=TAMBOURINE,
                     names={"perc": "Tambourine"}),
    # Jazz keeps time on the ride and the perc is a cross-stick; no clap, no open hat.
    "Jazz": dict(_hq("Jazz", kick="Kick 1", snare="Snare Hit", hat="Ride", perc="Snare Rim"),
                 names={"hat": "Ride", "perc": "Rim"}),
    "None": {},     # classical: no drum kit
}

# ---- bass -----------------------------------------------------------------------
SUB = Sound("808", "808 Bass", [SUBS + "808 Astronomic", SUBS + "808 Seismic",
                                SUBS + "808 Rumbler", OSC + "Pure bass", OSC + "Pure bass 2"])
SYNTH_BASS = Sound("Synth", "Synth Bass", [OSC + "Moog bass", OSC + "Synth bass",
                                           OSC + "Phat bass"])
SQUARE_BASS = Sound("Synth", "Synth Bass", [OSC + "Square bass", OSC + "Hard bass"])
GROWL = Sound("Growl", "Growl Bass", [OSC + "Noisy bass", OSC + "Hard bass", OSC + "Supa bass"])
LOG_DRUM = Sound("Log drum", "Log drum", [OSC + "Log drum", DX10 + "Log Drum"])
ELECTRIC = Sound("Electric", "Electric Bass", [
    BASS_PACK + "Golden Eden Fingered", BASS_PACK + "Good 80 Fingered",
    CORE_BASS + "Fingered Soft", GM + "Electric Finger Bass", BOOBASS])
FLATWOUND = Sound("Electric", "Electric Bass", [        # the Motown bass
    BASS_PACK + "BB FlatWound Tough", CORE_BASS + "BB Flat Wound",
    BASS_PACK + "Major Bruce Fingered", GM + "Electric Finger Bass", BOOBASS])
ROCK_BASS = Sound("Rock", "Rock Bass", [
    BASS_PACK + "Rocker RoundWounder", BASS_PACK + "5String NewRock Picked",
    CORE_BASS + "Rocker", CORE_BASS + "Pick It Up", GM + "Electric Pick Bass", BOOBASS])
UPRIGHT = Sound("Upright", "Upright Bass", [
    GM + "Acoustic Bass 1", GM + "Acoustic Bass 2", GM + "Acoustic Bass 3",
    DX10 + "Upright Bass 1", DX10 + "Upright Bass 2"])
CELLO = Sound("Cello", "Cello", [
    STRINGS_PACK + "Cellos Staccato", STRINGS_PACK + "Cellos Pizzicato",
    CORE_STRINGS + "Cellos Staccato", STRINGS_PACK + "Bass Pizzicato", GM + "Cello",
    GM + "Contrabass", SYTRUS + "Synth string/Cello"])

# The register of the string basses, as (lowest, highest) MIDI note: the open low
# E up to FL's C4, the top of where a bass line sits. Other basses (the 808, the
# synths) are written around FL's C5, where a sample plays untransposed.
BASS_RANGE = {"Upright": (28, 48), "Electric": (28, 48), "Rock": (28, 48)}


def bass_range(channel_name):
    """(lowest, highest) note for a bass channel named after a string bass, else None."""
    return BASS_RANGE.get(style_of("bass", channel_name))


# ---- keys -----------------------------------------------------------------------
PIANO = Sound("Piano", "Piano", [KEYS + "Concert Piano", KEYS + "Plain Piano",
                                 GM + "Acoustic Piano"])
GRAND = Sound("Piano", "Piano", [PIANO_PACK + "Grand Piano", CORE_PIANO + "Grand Piano",
                                 KEYS + "Concert Piano", GM + "Acoustic Piano"])
DARK_PIANO = Sound("Piano", "Piano", [KEYS + "Dark Piano", GM + "Piano Dark"])
DANCE_PIANO = Sound("Piano", "Piano", [KEYS + "Dance Piano", KEYS + "Compressed Piano",
                                       GM + "Piano Bright"])
HONKY_TONK = Sound("Piano", "Piano", [GM + "Honky Tonk Piano", KEYS + "Plain Piano",
                                      KEYS + "School Piano"])
RHODES = Sound("Rhodes", "Rhodes", [PIANO_PACK + "Rhodes Basic", CORE_PIANO + "Rhodes Basic",
                                    KEYS + "ePiano", GM + "Electric Piano 1"])
ORGAN = Sound("Organ", "Organ", [OSC + "Organ 2", OSC + "Organ", GM + "Organ 1"])
STAB = Sound("Stab", "Stab Keys", [OSC + "Pluck", OSC + "Short 2"])
HARPSICHORD = Sound("Harpsichord", "Harpsichord", [GM + "Harpsichord", DX10 + "Harpsichord",
                                                   SYTRUS + "Plucked/Harpsichord"])

# ---- pads and guitars -----------------------------------------------------------
SOFT_PAD = Sound("Pad", "Pad", [SYNTHS + "PAD Deep Space", SYNTHS + "PAD Blicloud",
                                SYNTHS + "PAD Ashword", SYNTHS + "PAD Omiran", GM + "Warm Pad",
                                OSC + "Smooth synth"])
TECH_PAD = Sound("Pad", "Pad", [OSC + "Pilch tech pad", SYNTHS + "PAD Tariant",
                                SYNTHS + "PAD Wamplo", GM + "Sweep Pad"])
STRINGS = Sound("Strings", "Strings", [
    STRINGS_PACK + "All Strings Sustain", STRINGS_PACK + "All Strings Slow",
    CORE_STRINGS + "All Sustain", GM + "Strings 1", OSC + "Smooth string", OSC + "Long string"])
ROCK_GUITAR = Sound("Rock", "Rock Guitar", [       # overdriven: power chords are written to it
    GUITAR_PACK + "Dark Star Overdriven", GUITAR_PACK + "Pignose FullGain",
    GUITAR_PACK + "Dark Star Metal", GM + "Overdriven Guitar", GM + "Distortion Guitar"])
TELE = Sound("Tele", "Tele Guitar", [               # the nearest to a Telecaster: clean, bright
    GM + "Electric Guitar Clean", CORE_GUITAR + "Electric Hard",
    GUITAR_PACK + "Bright Humbucker AC15", GUITAR_PACK + "BritBlub", GM + "Electric 60s Guitar",
    GM + "Steel Guitar"])


def _kit(drums, bass, keys, pad=None, guitar=None, optional=(), acoustic=False):
    return dict(drums=drums, bass=bass, chords=keys, pad=pad, guitar=guitar,
                optional=tuple(optional), acoustic=acoustic)


_GENRES = {
    "trap": _kit("808", [SUB], [DARK_PIANO], [SOFT_PAD]),
    "drill": _kit("808", [SUB], [DARK_PIANO], [SOFT_PAD]),
    "boombap": _kit("Dusty", [ELECTRIC], [RHODES, PIANO], [STRINGS, SOFT_PAD]),
    "lofi": _kit("Dusty", [ELECTRIC], [RHODES], [SOFT_PAD]),
    "rnb": _kit("808", [SUB], [RHODES], [SOFT_PAD]),
    "house": _kit("909", [SYNTH_BASS], [DANCE_PIANO, ORGAN], [SOFT_PAD]),
    "techno": _kit("909", [SQUARE_BASS], [STAB], [TECH_PAD]),
    "garage": _kit("909", [SYNTH_BASS], [ORGAN], [SOFT_PAD]),
    "reggaeton": _kit("Afro", [SUB], [PIANO], [SOFT_PAD]),
    "afrobeats": _kit("Afro", [ELECTRIC, SYNTH_BASS], [RHODES, PIANO], [SOFT_PAD]),
    "amapiano": _kit("Afro", [LOG_DRUM], [RHODES], [SOFT_PAD]),
    "dnb": _kit("Break", [GROWL], [STAB, RHODES], [TECH_PAD]),
    "jersey": _kit("909", [SUB], [DANCE_PIANO], [SOFT_PAD]),
    "pop": _kit("Linn", [SYNTH_BASS], [PIANO], [SOFT_PAD, STRINGS]),
    "funk": _kit("Acoustic", [ELECTRIC], [RHODES, ORGAN], [STRINGS]),
    "disco": _kit("Linn", [ELECTRIC, SYNTH_BASS], [PIANO], [STRINGS]),
    "dubstep": _kit("Heavy", [GROWL], [STAB], [TECH_PAD]),
    # The acoustic styles. `optional` parts are played when the rack has them but
    # are not built: a rock band can keep a synth behind it.
    "jazz": _kit("Jazz", [UPRIGHT], [RHODES, PIANO], acoustic=True),
    "country": _kit("Acoustic", [ELECTRIC, UPRIGHT], [HONKY_TONK], guitar=[TELE], acoustic=True),
    "classical": _kit("None", [CELLO], [GRAND, HARPSICHORD], [STRINGS], acoustic=True),
    "rocknroll": _kit("Rock", [ROCK_BASS], [PIANO, ORGAN], [SOFT_PAD, STRINGS],
                      guitar=[ROCK_GUITAR], optional=["pad"], acoustic=True),
    "soul": _kit("Acoustic", [FLATWOUND], [RHODES, ORGAN, PIANO], [STRINGS], acoustic=True),
}

# Styles an acoustic genre never falls back on: machines and synths.
ELECTRONIC = {"drums": {"808", "909", "Linn", "Dusty", "Break", "Afro", "Heavy"},
              "bass": {"808", "Synth", "Growl", "Log drum"},
              "chords": {"Stab"}, "pad": {"Pad"}, "guitar": set()}


def _group(role):
    return "drums" if role in DRUM_ROLES else role


def _styles(group):
    if group == "drums":
        return [s for s in DRUMS if s != "None"]
    out = []
    for kit in _GENRES.values():
        for sound in kit[group] or ():
            if sound.style not in out:
                out.append(sound.style)
    return out


_KNOWN = {g: sorted(_styles(g), key=len, reverse=True)
          for g in ("drums", "bass", "chords", "pad", "guitar")}


def style_of(role, channel_name):
    """The style word in a channel's name ("Rock Kick" -> "Rock"), or None for a
    plain name ("Kick", "Bass") that suits any genre."""
    low = channel_name.lower()
    for style in _KNOWN[_group(role)]:
        if style.lower() in low:
            return style
    return None


def parts(genre):
    """{role: [Sound, ...]} for a genre key from GENRES, in rack order. A part the
    genre doesn't have (a pad in jazz, drums in classical) is left out."""
    kit = _GENRES[genre]
    drums = DRUMS[kit["drums"]]
    names = drums.get("names", {})
    out = {}
    for role in ROLES:
        if role in DRUM_ROLES:
            if drums.get(role):
                name = "%s %s" % (kit["drums"], names.get(role, CHANNELS[role][0]))
                out[role] = [Sound(kit["drums"], name, list(drums[role]))]
        elif kit[role]:
            out[role] = list(kit[role])
    return out


def optional(genre):
    """Parts the genre plays when the rack has them, but that are not built."""
    return _GENRES[genre]["optional"]


def accepts(genre):
    """{role: styles a channel may have to play that part in this genre}."""
    return {role: {s.style for s in sounds} for role, sounds in parts(genre).items()}


def fallback_ok(genre, role, style):
    """May a channel of another style stand in (when the rack isn't being built)?
    Always, except machines and synths under an acoustic genre."""
    return not (_GENRES[genre]["acoustic"] and style in ELECTRONIC[_group(role)])


# ---- EQ starting points (CFilteR-01 on each channel's mixer insert) --------------
# Bands in real units: shape, freq (Hz), gain (dB), q, slope (dB/oct). Every part
# gets a low cut under its own range so the low end belongs to the kick and the
# bass; a genre adds the cuts and lifts that make its parts fit together. These
# are starting points chosen from how the instruments sit, not by ear: the user
# tunes them. `eq_for(genre, role)` falls back on DEFAULT_EQ.
def _cut(freq, slope=12):
    return {"shape": "low cut", "freq": freq, "slope": slope}


def _bell(freq, gain, q=1.0):
    return {"shape": "bell", "freq": freq, "gain": gain, "q": q}


DEFAULT_EQ = {
    "kick": [_cut(30)],
    "snare": [_cut(100)],
    "clap": [_cut(150)],
    "hat": [_cut(300, 18)],
    "openhat": [_cut(300, 18)],
    "perc": [_cut(150)],
    "bass": [_cut(30)],
    "chords": [_cut(120)],
    "pad": [_cut(150)],
    "guitar": [_cut(90)],
}

GENRE_EQ = {
    # A trio: the kick's body (60-70 Hz) and the upright's fundamentals (41-131 Hz)
    # share the bottom, so the bass steps aside at the kick's note; the Rhodes'
    # rootless voicings (147-330 Hz) leave the roots to the bass; the ride loses
    # its low wash and some ping.
    "jazz": {
        "kick": [_cut(30), _bell(65, 2.0, 1.0), _bell(350, -3.0, 1.4)],
        "bass": [_cut(38), _bell(65, -2.0, 1.2), _bell(800, 1.5, 1.0)],
        "chords": [_cut(140), _bell(320, -2.0, 1.0)],
        "hat": [_cut(300, 18), _bell(4000, -2.5, 1.2)],
        "snare": [_cut(120), _bell(500, -1.5, 1.2)],
        "perc": [_cut(200)],
    },
}


def eq_for(genre, role):
    """The starting EQ bands for a part in a genre, or [] when there are none."""
    return list(GENRE_EQ.get(genre, {}).get(role) or DEFAULT_EQ.get(role) or [])
