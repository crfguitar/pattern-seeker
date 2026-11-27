"""Paper Satellites - a hand-written indietronica song in D major, 116 BPM: a
drum machine with glitches, a soft synth bass, chirpy sixteenth arpeggios, a
warm pad, a synth lead singing the vocal line, glockenspiel and a clean guitar.

    python examples/indietronica.py          # compose, print the plan and the checks
    python examples/indietronica.py build    # add the ten channels (inserts 1-10)
    python examples/indietronica.py write    # write the patterns, lay out the song

What makes it indietronica (the bedroom-electronic indie pop of the early 2000s):
  * Programmed, slightly stiff drum machine (Linn samples) with glitch clicks:
    a rim sample stuttered in 32nds and repitched, filling the gaps.
  * Sequenced, chirpy synths high up (the arp two octaves over the pad) next
    to warm sustained pads and a pulsing, octave-bouncing synth bass.
  * A conversational, syllabic vocal melody (here the Lead), eighths that
    start off the beat; a bigger hook in the chorus doubled by glockenspiel.
  * Real instruments mixed in sparingly: a clean guitar in verse 2 and the
    bridge. A glitchy breakdown where the beat falls apart before the last chorus.

Form (bars): Intro 8 | Verse 16 | Chorus 8 | Interlude 4 | Verse 16 | Chorus 8
             | Bridge 8 | Breakdown 8 | Last Chorus 16 | Outro 8 = 100 bars, 3:27.

Dynamics as in examples/midwest_emo.py and the Divertimento rules: parts at a
reference level, LEVEL per section, eased over the last two bars, 50-100.
"""

import collections
import json
import os
import random
import statistics
import sys

TEMPO = 116

# channel: (sound, colour, volume, pan)
BAND = {
    "Kick": ("Drums/Kicks/Linn Kick", "#C8553D", 0.78, 0.0),
    "Snare": ("Drums/Snares/Linn Snare", "#E0A33A", 0.70, 0.0),
    "Hat": ("Drums/Hats/Linn CH", "#D9CB5E", 0.48, 0.30),
    "Glitch": ("Drums/Snares/Linn Rim", "#B5C25B", 0.42, -0.35),
    "Synth Bass": ("FLEX/Core Synths/BAS Soft Atrik", "#8A5FBF", 0.70, 0.0),
    "Arp": ("FLEX/Core Synths/PLK Hermia", "#4FB8A8", 0.50, 0.45),
    "Pad": ("FLEX/Core Synths/PAD Omiran", "#4F8FD9", 0.52, 0.0),
    "Lead": ("FLEX/Core Synths/LED Analogia", "#E0782F", 0.60, 0.0),
    "Glock": ("FLEX/General Midi Library/Glockenspeil", "#E8E3A0", 0.46, 0.25),
    "Guitar": ("FLEX/Core Guitars/GTR Electric Soft", "#5FA8E0", 0.56, -0.50),
}

# ---- harmony (C4 = 60) ---------------------------------------------------------------
PAD = {     # close voicings around middle C
    "D": [54, 57, 62, 66], "A/C#": [52, 57, 61, 64], "Bm": [54, 59, 62, 66],
    "G": [55, 59, 62, 67], "A": [52, 57, 61, 64], "F#m": [54, 57, 61, 66],
    "Em7": [52, 55, 59, 62], "D/F#": [54, 57, 62, 66], "Gmaj7": [54, 59, 62, 67],
}
BASS = {"D": 50, "A/C#": 49, "Bm": 47, "G": 43, "A": 45, "F#m": 54, "Em7": 52,
        "D/F#": 54, "Gmaj7": 43}       # D3 down to G2: FLEX synth basses sit low already

VERSE = ["D", "A/C#", "Bm", "G"] * 2
CHORUS = ["G", "A", "F#m", "Bm", "G", "A", "Bm", "D"]
BRIDGE = ["Em7", "G", "D/F#", "A", "Em7", "Gmaj7", "Bm", "A"]

LEVEL = {"Intro": -6, "Verse 1": -4, "Chorus 1": 5, "Interlude": 1, "Verse 2": -2,
         "Chorus 2": 6, "Bridge": -1, "Breakdown": -6, "Last Chorus": 9, "Outro": 0}

# ---- tunes -----------------------------------------------------------------------------
VERSE_TUNE = ("r:0.5 F#4:0.5 F#4:0.5 E4:0.5 F#4:1 A4:1 | E4:0.5 E4:0.5 C#4:0.5 E4:0.5 A4:2"
              " | r:0.5 D4:0.5 D4:0.5 C#4:0.5 D4:1 F#4:1 | B3:0.5 D4:0.5 B3:0.5 A3:0.5 B3:2"
              " | r:0.5 F#4:0.5 F#4:0.5 E4:0.5 F#4:1 B4:1 | A4:0.5 G4:0.5 E4:0.5 C#4:0.5 E4:2"
              " | r:0.5 F#4:0.5 F#4:0.5 E4:0.5 D4:1 B3:1 | B3:1 A3:1 D4:2")
HOOK = ("D5:1 B4:0.5 A4:0.5 B4:1 D5:1 | C#5:1 A4:0.5 G4:0.5 A4:1 E4:1"
        " | F#4:1 A4:0.5 C#5:0.5 E5:1.5 C#5:0.5 | D5:3 r:1 | D5:1 B4:0.5 A4:0.5 B4:1 D5:1"
        " | E5:1 C#5:0.5 A4:0.5 E5:1 F#5:1 | F#5:1.5 E5:0.5 D5:1 C#5:1 | D5:3 r:1")
MOTIF = ("A5:1 F#5:1 E5:1 D5:1 | E5:1 C#5:1 A4:2 | F#5:1 D5:1 B4:1 D5:1 | D5:2 B4:2")
BRIDGE_TUNE = ("B4:2 A4:1 G4:1 | B4:2 D5:2 | A4:3 F#4:1 | E4:4"
               " | G4:2 F#4:1 E4:1 | F#4:2 B4:2 | D5:3 C#5:1 | C#5:4")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    pc, rest = PC[name[0]], name[1:]
    while rest and rest[0] in "#b":
        pc += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + pc


class Sec:
    def __init__(self, name, bars, color):
        self.name, self.bars, self.color = name, bars, color
        self.parts = collections.defaultdict(list)

    def add(self, ch, pitch, start, length, vel):
        self.parts[ch].append([pitch, start, length, vel])


def tune(s, text, bar, vel, ch="Lead", shift=0, legato=0.92):
    t = bar * 4
    for b, chunk in enumerate(text.split("|")):
        at = 0.0
        for tok in chunk.split():
            name, length = tok.split(":")
            length = float(length)
            if name != "r":
                accent = 3 if at == 0 else 0
                s.add(ch, midi(name) + shift, t + b * 4 + at, length * legato, vel + accent)
            at += length


# ---- synths ----------------------------------------------------------------------------
ARP = [0, 2, 1, 3, 2, 1, 3, 2]


def arp(s, chords, bar, vel, up=24):
    """Sixteenths over the chord, two octaves above the pad: the chirp."""
    for i, c in enumerate(chords):
        tones, t = [p + up for p in PAD[c]], (bar + i) * 4
        for k in range(16):
            accent = 5 if k % 4 == 0 else 2 if k % 2 == 0 else 0
            s.add("Arp", tones[ARP[k % 8]], t + k * 0.25, 0.2, vel + accent)


def pad(s, chords, bar, vel, bars_each=1):
    for i, c in enumerate(chords):
        for k, p in enumerate(PAD[c]):
            s.add("Pad", p, (bar + i * bars_each) * 4, 4 * bars_each - 0.05, vel - k)


def bass_pulse(s, chords, bar, vel):
    """Eighths bouncing root / octave, the last eighth leading on."""
    for i, c in enumerate(chords):
        r, t = BASS[c], (bar + i) * 4
        for k in range(8):
            s.add("Synth Bass", r + (12 if k % 2 else 0), t + k * 0.5, 0.42,
                  vel + (4 if k in (0, 3, 6) else 0) - (3 if k % 2 else 0))


def bass_long(s, chords, bar, vel):
    for i, c in enumerate(chords):
        s.add("Synth Bass", BASS[c], (bar + i) * 4, 1.9, vel + 2)
        s.add("Synth Bass", BASS[c], (bar + i) * 4 + 2.5, 1.4, vel - 2)


def guitar(s, chords, bar, vel):
    """Clean guitar: a soft strum on 1, then two picked chord tones."""
    for i, c in enumerate(chords):
        t, v = (bar + i) * 4, PAD[c]
        for k, p in enumerate([BASS[c] + 12] + v):
            s.add("Guitar", p, round(t + k * 0.02, 3), 1.9, vel - k)
        s.add("Guitar", v[3] + 12, t + 2.5, 0.9, vel - 4)
        s.add("Guitar", v[2] + 12, t + 3, 0.9, vel - 5)


# ---- drum machine (sampler channels: 60 plays the sample as recorded) ---------------
def hit(s, ch, t, vel, pitch=60, length=0.2):
    s.add(ch, pitch, round(t, 4), length, vel)


def glitches(s, bar, bars, rng, dense=1.0):
    """Rim clicks in 32nd stutters, repitched: the 'broken laptop' layer."""
    for i in range(bars):
        t = (bar + i) * 4
        for at in (0.75, 2.25, 3.25):
            if rng.random() < 0.55 * dense:
                n = rng.choice((2, 3, 4))
                p = rng.choice((60, 58, 55))          # at or under the rim's own pitch
                for k in range(n):
                    hit(s, "Glitch", t + at + k * 0.125, 56 + k * 2, p - k, 0.1)


def beat(s, bar, bars, rng, snare=True, busy=False, end_fill=True, glitch=1.0):
    for i in range(bars):
        t = (bar + i) * 4
        last = i == bars - 1
        fill4 = i % 4 == 3
        hit(s, "Kick", t, 86)
        hit(s, "Kick", t + 1.75, 72)
        hit(s, "Kick", t + 2.5, 80)
        if busy:
            hit(s, "Kick", t + 3.5, 70)
        if snare:
            hit(s, "Snare", t + 1, 84)
            if not fill4:
                hit(s, "Snare", t + 3, 86)
        for k in range(16 if not fill4 else 14):
            v = (68 if k % 4 == 0 else 62 if k % 2 == 0 else 54) + (4 if busy else 0)
            hit(s, "Hat", t + k * 0.25, v)
        if fill4 and snare:                                    # a 32nd stutter into beat 4
            n = 8 if (last and end_fill) or i % 8 == 7 else 4
            start = 4 - n * 0.125
            for k in range(n):
                hit(s, "Snare", t + start + k * 0.125, 66 + k * (3 if n == 8 else 5))
    glitches(s, bar, bars, rng, glitch)


def half_time(s, bar, bars, rng):
    for i in range(bars):
        t = (bar + i) * 4
        hit(s, "Kick", t, 82)
        hit(s, "Kick", t + 2.75, 70)
        hit(s, "Snare", t + 2, 82)
        for k in range(8):
            hit(s, "Hat", t + k * 0.5, 62 if k % 2 == 0 else 54)
    glitches(s, bar, bars, rng, 1.4)


# ---- sections --------------------------------------------------------------------------
def intro(rng):
    s = Sec("Intro", 8, "#4FB8A8")
    arp(s, VERSE, 0, 62)
    pad(s, VERSE[4:], 4, 64)
    tune(s, MOTIF, 0, 70, ch="Glock")
    tune(s, MOTIF, 4, 72, ch="Glock")
    glitches(s, 0, 4, rng, 0.6)
    beat(s, 4, 4, rng, snare=False)
    bass_long(s, VERSE[4:], 4, 66)
    return s


def verse(name, rng, second):
    s = Sec(name, 16, "#5FA8E0")
    for half in (0, 8):
        arp(s, VERSE, half, 62)
        pad(s, VERSE, half, 64)
        tune(s, VERSE_TUNE, half, 74, shift=12)
        (bass_pulse if second or half else bass_long)(s, VERSE, half, 68)
    if second:
        guitar(s, VERSE, 0, 66)
        guitar(s, VERSE, 8, 66)
        beat(s, 0, 16, rng)
    else:
        beat(s, 0, 8, rng, snare=False)                         # the snare joins halfway
        beat(s, 8, 8, rng)
    return s


def chorus(name, rng, bars=8):
    s = Sec(name, bars, "#E0782F")
    for half in range(0, bars, 8):
        arp(s, CHORUS, half, 66)
        pad(s, CHORUS, half, 68)
        bass_pulse(s, CHORUS, half, 72)
        tune(s, HOOK, half, 80)
        tune(s, HOOK, half, 72, ch="Glock", shift=12)
        if half:                                                # last time: guitar too
            guitar(s, CHORUS, half, 68)
    beat(s, 0, bars, rng, busy=True)
    for i in range(0, bars, 4):
        hit(s, "Snare", i * 4, 76)                              # a downbeat clap on each phrase
    return s


def interlude(rng):
    s = Sec("Interlude", 4, "#4FB8A8")
    arp(s, VERSE[:4], 0, 64)
    pad(s, VERSE[:4], 0, 64)
    tune(s, MOTIF, 0, 76, ch="Glock")
    bass_pulse(s, VERSE[:4], 0, 68)
    beat(s, 0, 4, rng)
    return s


def bridge(rng):
    s = Sec("Bridge", 8, "#7A6FBF")
    pad(s, BRIDGE, 0, 66)
    guitar(s, BRIDGE, 0, 68)
    tune(s, BRIDGE_TUNE, 0, 74, legato=0.97)
    bass_long(s, BRIDGE, 0, 68)
    arp(s, BRIDGE[4:], 4, 60)                                    # the chirp comes back late
    half_time(s, 0, 8, rng)
    return s


def breakdown(rng):
    """The beat falls apart into glitches, then builds back."""
    s = Sec("Breakdown", 8, "#8A5A3A")
    pad(s, ["D", "Bm"], 0, 66, bars_each=2)
    pad(s, ["G", "A"], 4, 68, bars_each=2)
    tune(s, MOTIF, 0, 70, ch="Glock")
    tune(s, "A5:4 | F#5:4 | G5:4 | A5:2 C#6:2", 4, 72, ch="Glock")
    glitches(s, 0, 8, rng, 1.8)
    for b in range(4, 8):                                       # the kick comes back in quarters
        for q in range(4):
            hit(s, "Kick", b * 4 + q, 64 + (b - 4) * 5 + q)
    for k in range(32):                                         # last bar: a 32nd snare build
        hit(s, "Snare", 28 + k * 0.125, 58 + int(k * 0.9))
    for i, c in enumerate(["G", "G", "A", "A"]):
        s.add("Synth Bass", BASS[c], (4 + i) * 4, 3.9, 64 + i * 3)
    return s


def outro(rng):
    s = Sec("Outro", 8, "#4FB8A8")
    arp(s, VERSE[:4], 0, 64)
    pad(s, VERSE[:4], 0, 66)
    tune(s, MOTIF, 0, 72, ch="Glock")
    bass_long(s, VERSE[:4], 0, 66)
    beat(s, 0, 4, rng, snare=True, end_fill=False, glitch=0.6)
    for p in PAD["D"]:                                          # the last chord, held
        s.add("Pad", p, 16, 16, 66)
    s.add("Synth Bass", BASS["D"], 16, 8, 66)
    tune(s, "A5:2 F#5:2 | D5:4", 4, 66, ch="Glock")
    for k in range(16):                                         # the arp slows to a stop
        s.add("Arp", PAD["D"][k % 4] + 24, 16 + k * 0.5, 0.4, 64 - k)
    glitches(s, 4, 2, rng, 0.8)
    return s


def compose(seed=2003):
    rng = random.Random(seed)
    secs = [intro(rng), verse("Verse 1", rng, False), chorus("Chorus 1", rng), interlude(rng),
            verse("Verse 2", rng, True), chorus("Chorus 2", rng), bridge(rng), breakdown(rng),
            chorus("Last Chorus", rng, 16), outro(rng)]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for notes in s.parts.values():
            for n in notes:
                ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(n[1], 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)
    return secs


def check(secs):
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ns in s.parts.values() for n in ns if b * 4 <= n[1] < b * 4 + 4]
            meds.append((s.name, b + 1, statistics.median(vs) if vs else None))
    return sorted(((abs(b[2] - a[2]), a, b) for a, b in zip(meds, meds[1:]) if a[2] and b[2]),
                  reverse=True)


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    secs = compose()
    do = argv[1] if len(argv) > 1 else "plan"
    if do == "plan":
        bar = 1
        for s in secs:
            vs = [n[3] for ns in s.parts.values() for n in ns]
            print("bars %3d-%3d  %-12s %4d notes  vel %d-%d  %s" % (
                bar, bar + s.bars - 1, s.name, len(vs), min(vs), max(vs), ", ".join(sorted(s.parts))))
            bar += s.bars
        print("%d bars, %.2f minutes at %d BPM" % (bar - 1, (bar - 1) * 4 / TEMPO, TEMPO))
        for jump, a, b in check(secs)[:3]:
            print("  median move %.1f: %s %d -> %s %d" % (jump, a[0], a[1], b[0], b[1]))
        return
    from seeker import link
    from seeker.engine import Engine
    engine = Engine()
    try:
        if do == "build":
            have = {c["name"] for c in engine.status()["channels"]}
            for name, (sound, color, volume, pan) in BAND.items():
                if name in have:
                    continue
                made = engine.add_channel(sound, name, color, volume, pan)
                print(name, "-> channel", made["channel"], "insert", made.get("insert"),
                      made["warnings"], file=sys.stderr)
        elif do == "rewrite":
            # new notes for some parts in the patterns `write` made, playlist kept:
            #   python examples/indietronica.py rewrite "Synth Bass" Glitch
            parts = argv[2:] or list(BAND)
            for n, sec in enumerate(secs):
                engine._song(pattern=2 + n)
                for ch in parts:
                    if sec.parts.get(ch):
                        bad = engine.write_part(ch, sec.parts[ch])["problems"]
                        print("pattern %d %s %s %s" % (2 + n, sec.name, ch, bad or "ok"), flush=True)
        elif do == "write":
            sections = [{"name": s.name, "color": s.color, "parts": dict(s.parts)} for s in secs]
            done = engine.write_song(sections, tempo=TEMPO, track=1, start_bar=1)
            print(json.dumps({"sections": [(s["section"], s["pattern"]) for s in done["sections"]],
                              "arrangement": done.get("arrangement"),
                              "problems": done["problems"]}, default=str))
    finally:
        link.close()


if __name__ == "__main__":
    main(sys.argv)
