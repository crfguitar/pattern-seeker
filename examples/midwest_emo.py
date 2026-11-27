"""Porch Light - a hand-written indie rock / midwest emo song in F major, 148 BPM.

    python examples/midwest_emo.py          # compose and print the plan + checks
    python examples/midwest_emo.py build    # add the band's channels to the rack
    python examples/midwest_emo.py write    # write the patterns, lay out the song

What makes it midwest emo rather than plain rock:
  * Guitars in the open "emo tuning" F A C G C E. Every chord is a shape on the
    low four strings with the top two (C4, E4) left ringing, so the chords come
    out as maj9 / add9 / #11 colours (Fmaj9, Am7, Bbmaj9#11, Cadd9, Dm9, G9sus).
  * Twinkle: eighth-note arpeggios that cross strings, notes left to ring over
    each other (Twinkle L), against a second clean guitar playing a melody, or
    tapping in the bridge (Twinkle R).
  * A busy, melodic picked bass and a drummer who fills every four bars.
  * The chorus starts on IV (Bb) and the distorted guitar only arrives there.
  * An odd-meter bridge: 16 bars of 7/8 (2+2+3), which lands exactly on 14 bars
    of FL's 4/4 grid. Then a quiet breakdown that builds into the last chorus.

Form (bars): Intro 8 | Verse 16 | Chorus 8 | Verse 16 | Chorus 8 | Bridge 14 (7/8)
             | Breakdown 8 | Last chorus 16 | Outro 8  = 102 bars, about 2:45.

Dynamics follow the rules signed off on the Divertimento: every part is
written at a reference level and each section moves it (LEVEL), changes are
eased over the last two bars of a section, velocities stay within 50-100.
"""

import collections
import json
import os
import statistics
import sys

TEMPO = 148
HQ = "Drums/Kits/HQ Rock Kit/%s HQ Rock #6"

# channel: (sound, colour, volume, pan)
BAND = {
    "Kick": (HQ % "Kick 1", "#C8553D", 0.78, 0.0),
    "Snare": (HQ % "Snare Hit", "#E0A33A", 0.72, 0.0),
    "Hat": (HQ % "HH Closed", "#D9CB5E", 0.50, 0.25),
    "Ride": (HQ % "Ride", "#B5C25B", 0.50, -0.30),
    "Crash": (HQ % "Crash", "#E8E3A0", 0.48, 0.35),
    "Tom": (HQ % "Tom 2", "#A8714A", 0.62, 0.20),
    "Floor Tom": (HQ % "Tom 4", "#8A5A3A", 0.66, -0.25),
    "Bass": ("FLEX/Essential Bass Guitars/Good 80 Picked", "#8A5FBF", 0.72, 0.0),
    "Twinkle L": ("FLEX/Essential Guitars/Brighter Humbucker AC15", "#4FB8A8", 0.60, -0.60),
    "Twinkle R": ("FLEX/Core Guitars/GTR Electric Mellow", "#5FA8E0", 0.62, 0.60),
    "Drive Gtr": ("FLEX/Essential Guitars/Pignose HalfGain 1", "#D96A8B", 0.56, -0.10),
}

# ---- the open tuning ---------------------------------------------------------------
# F2 A2 C3 G3 C4 E4. Each voicing is string 1 (low) to 6; strings 5-6 stay open.
V = {
    "Fmaj9": [41, 45, 48, 55, 60, 64],       # all open
    "Am7": [45, 52, 55, 57, 60, 64],         # 4 7 7 2 0 0
    "Bbmaj9#11": [46, 53, 57, 62, 60, 64],   # 5 8 9 7 0 0
    "Cadd9": [48, 52, 55, 62, 60, 64],       # 7 7 7 7 0 0
    "Dm9": [50, 53, 57, 62, 60, 64],         # 9 8 9 7 0 0
    "G9sus": [43, 50, 53, 57, 60, 64],       # 2 5 5 2 0 0
}
ROOT = {"Fmaj9": 29, "Am7": 33, "Bbmaj9#11": 34, "Cadd9": 36, "Dm9": 38, "G9sus": 31}
F_MAJOR ={(5 + s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)}

VERSE = ["Fmaj9", "Am7", "Bbmaj9#11", "Cadd9", "Fmaj9", "Am7", "Dm9", "G9sus"]
CHORUS = ["Bbmaj9#11", "Cadd9", "Dm9", "Am7", "Bbmaj9#11", "Cadd9", "Dm9", "Cadd9"]
BRIDGE = ["Dm9", "Dm9", "Bbmaj9#11", "Bbmaj9#11", "Fmaj9", "Fmaj9", "Cadd9", "Cadd9"]
BREAK = ["Bbmaj9#11", "Cadd9", "Dm9", "Dm9", "Bbmaj9#11", "Cadd9", "Dm9", "Cadd9"]
OUTRO = ["Fmaj9", "Am7", "Bbmaj9#11", "Cadd9", "Fmaj9", "Fmaj9", "Fmaj9", "Fmaj9"]

# section -> dynamic level, added to every part's reference velocity
LEVEL = {"Intro": -8, "Verse 1": -4, "Chorus 1": 6, "Verse 2": -3, "Chorus 2": 7,
         "Bridge": 2, "Breakdown": -5, "Last Chorus": 10, "Outro": -3}

# ---- melodies (C4 = 60) ----------------------------------------------------------------
VERSE_TUNE = ("A4:1.5 G4:0.5 F4:1 C5:1 | E5:1.5 D5:0.5 C5:1 A4:1 | D5:1.5 C5:0.5 A4:1 F4:0.5 G4:0.5"
              " | E4:2 r:1 G4:0.5 A4:0.5 | A4:1.5 G4:0.5 F4:1 C5:1 | E5:1.5 G5:0.5 E5:1 C5:1"
              " | D5:1.5 E5:0.5 F5:1 A5:1 | G5:3 r:1")
HOOK = ("D5:1 F5:1 E5:1 C5:1 | E5:1.5 D5:0.5 C5:1 G4:1 | A4:1 C5:1 F5:1.5 E5:0.5 | E5:3 r:1"
        " | D5:1 F5:1 E5:1 C5:1 | E5:1.5 D5:0.5 C5:1 E5:1 | F5:1.5 E5:0.5 D5:1 A5:1 | G5:4")
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


# ---- guitars ---------------------------------------------------------------------------
TWINKLE = ([0, 4, 3, 5, 2, 4, 3, 5], [1, 4, 3, 5, 2, 5, 4, 3])


def twinkle(s, chords, bar, vel, ch="Twinkle L"):
    """Eighth-note arpeggios across the strings, each note left to ring."""
    for i, c in enumerate(chords):
        t = (bar + i) * 4
        for k, idx in enumerate(TWINKLE[i % 2]):
            accent = 4 if k == 0 else 2 if k == 4 else 0
            s.add(ch, V[c][idx], t + k * 0.5, 1.5, vel + accent - (1 if idx >= 4 else 0))


def tune(s, text, bar, vel, ch="Twinkle R", shift=0):
    t = bar * 4
    for b, chunk in enumerate(text.split("|")):
        at = 0.0
        for tok in chunk.split():
            name, length = tok.split(":")
            length = float(length)
            if name != "r":
                accent = 3 if at == 0 else 0
                s.add(ch, midi(name) + shift, t + b * 4 + at, length * 0.95, vel + accent)
            at += length


def strum(s, chord, t, length, vel, up=False, ch="Drive Gtr"):
    notes = V[chord][2:] if up else V[chord]           # upstrokes catch the top four
    order = notes[::-1] if up else notes
    for k, p in enumerate(order):
        s.add(ch, p, round(t + k * 0.012, 3), length - k * 0.012, vel - k)


def drive(s, chords, bar, vel):
    """Big open chord on 1, then eighths: D . . U D U D U"""
    for i, c in enumerate(chords):
        t = (bar + i) * 4
        strum(s, c, t, 1.45, vel + 5)
        for at, up in ((1.5, True), (2, False), (2.5, True), (3, False), (3.5, True)):
            strum(s, c, t + at, 0.45, vel - (6 if up else 0) + (3 if at == 1.5 else 0), up)


def harmonics(s, chords, bar, vel):
    """Twinkle R in the intro: chimes, the chord's top tones an octave up."""
    for i, c in enumerate(chords):
        t = (bar + i) * 4
        s.add("Twinkle R", V[c][4] + 12, t, 1.9, vel)
        s.add("Twinkle R", V[c][5] + 12, t + 2, 1.9, vel - 2)


# ---- bass ------------------------------------------------------------------------------
def approach(target):
    """The scale step under the next root (a step above when that is closer)."""
    for d in (-1, -2, 1, 2):
        if (target + d) % 12 in F_MAJOR:
            return target + d
    return target


def bass_verse(s, chords, bar, vel, after):
    for i, c in enumerate(chords):
        r, t = ROOT[c], (bar + i) * 4
        nxt = chords[i + 1] if i + 1 < len(chords) else after
        s.add("Bass", r, t, 1.4, vel + 3)
        s.add("Bass", r + 7, t + 1.5, 0.45, vel - 3)
        s.add("Bass", r + 12, t + 2, 0.9, vel)
        s.add("Bass", approach(ROOT[nxt]) + (12 if ROOT[nxt] < r else 0), t + 3, 0.9, vel - 1)


def bass_eighths(s, chords, bar, vel, after):
    for i, c in enumerate(chords):
        r, t = ROOT[c], (bar + i) * 4
        nxt = chords[i + 1] if i + 1 < len(chords) else after
        for k in range(7):
            s.add("Bass", r, t + k * 0.5, 0.42, vel + (4 if k in (0, 3) else 0))
        s.add("Bass", approach(ROOT[nxt]), t + 3.5, 0.42, vel)


def bass_long(s, chords, bar, vel, beats=4):
    for i, c in enumerate(chords):
        s.add("Bass", ROOT[c], (bar + i) * 4, beats - 0.1, vel)


# ---- drums (one sampler per drum: pitch 60 plays the sample as recorded) --------------
def hit(s, ch, t, vel):
    s.add(ch, 60, round(t, 4), 0.25, vel)


def small_fill(s, t):
    hit(s, "Snare", t + 3, 78)
    hit(s, "Tom", t + 3.25, 74)
    hit(s, "Tom", t + 3.5, 76)
    hit(s, "Floor Tom", t + 3.75, 80)


def big_fill(s, t):
    for at, ch, v in ((2, "Snare", 76), (2.25, "Snare", 72), (2.5, "Tom", 78), (2.75, "Tom", 76),
                      (3, "Floor Tom", 82), (3.25, "Floor Tom", 80), (3.5, "Snare", 84),
                      (3.75, "Snare", 86)):
        hit(s, ch, t + at, v)
    hit(s, "Kick", t + 3, 76)


def groove(s, bar, bars, cym="Hat", busy=False, crash_every=8, end_fill="big"):
    """Rock beat with an emo drummer's kick: 1, and-of-2 (+ and-of-3 on odd bars);
    a fill every 4th bar, a bigger one every 8th."""
    for i in range(bars):
        t = (bar + i) * 4
        last = i == bars - 1
        big = (i % 8 == 7 and not last) or (last and end_fill == "big")
        small = (i % 4 == 3 and not big) and not (last and end_fill is None)
        stop = 2 if big else 3 if small else 4
        hit(s, "Kick", t, 84)
        hit(s, "Kick", t + 1.5, 74)
        if i % 2 or busy:
            hit(s, "Kick", t + 2.5, 74)
        if busy:
            hit(s, "Kick", t + 2, 70)
        hit(s, "Snare", t + 1, 82)
        if stop > 3:
            hit(s, "Snare", t + 3, 84)
            if i % 2 == 0:
                hit(s, "Snare", t + 3.75, 54)        # ghost into the next bar
        k = 0
        while k * 0.5 < stop:
            v = (70 if k % 2 == 0 else 60) if cym == "Ride" else (64 if k % 2 == 0 else 54)
            hit(s, cym, t + k * 0.5, v)
            k += 1
        if i % crash_every == 0:
            hit(s, "Crash", t, 84)
        if big:
            big_fill(s, t)
        elif small:
            small_fill(s, t)


# ---- the sections ----------------------------------------------------------------------
def intro():
    s = Sec("Intro", 8, "#4FB8A8")
    twinkle(s, VERSE, 0, 68)
    harmonics(s, VERSE[4:], 4, 64)
    bass_long(s, VERSE[4:], 4, 66)
    for i in range(4, 8):
        t = i * 4
        for q in range(4):
            hit(s, "Ride", t + q, 62 if q == 0 else 56)
        hit(s, "Kick", t, 72)
        hit(s, "Floor Tom", t + 2, 62)
    for k, at in enumerate((3, 3.25, 3.5, 3.75)):            # into the verse
        hit(s, "Snare", 28 + at, 66 + 5 * k)
    return s


def verse(name, quiet_start):
    s = Sec(name, 16, "#5FA8E0")
    for half in (0, 8):
        twinkle(s, VERSE, half, 68)
        bass_verse(s, VERSE, half, 68, "Fmaj9" if half == 0 else "Bbmaj9#11")
    if quiet_start:
        harmonics(s, VERSE, 0, 64)                           # the tune waits a phrase
    else:
        tune(s, VERSE_TUNE, 0, 72)
    tune(s, VERSE_TUNE, 8, 72)
    groove(s, 0, 16, cym="Hat" if quiet_start else "Ride")
    return s


def chorus(name, bars=8):
    s = Sec(name, bars, "#D96A8B")
    for half in range(0, bars, 8):
        after = "Bbmaj9#11" if half + 8 < bars else "Fmaj9"
        if half == 8:                                        # last time: Twinkle L doubles
            tune(s, HOOK, half, 72, ch="Twinkle L", shift=-12)  # the hook an octave down
        else:
            twinkle(s, CHORUS, half, 70)
        drive(s, CHORUS, half, 72)
        tune(s, HOOK, half, 78)
        bass_eighths(s, CHORUS, half, 70, after)
    groove(s, 0, bars, cym="Ride", busy=True, crash_every=4)
    return s


SEVEN = 3.5                       # a bar of 7/8 in beats
TWINKLE_7 = [0, 4, 3, 5, 2, 4, 5]


def bridge():
    """16 bars of 7/8, grouped 2+2+3: lands exactly on 14 bars of 4/4."""
    s = Sec("Bridge", 14, "#C8A23D")
    for rep in range(16):
        c, t, loud = BRIDGE[rep % 8], rep * SEVEN, rep >= 8
        for k, idx in enumerate(TWINKLE_7):
            s.add("Twinkle L", V[c][idx], t + k * 0.5, 1.5,
                  68 + (4 if k in (0, 2, 4) else 0))
        top = sorted(p + 12 for p in V[c][2:])
        for k, idx in enumerate([0, 1, 2, 3, 2, 1, 3]):      # tapped line on Twinkle R
            s.add("Twinkle R", top[idx], t + k * 0.5, 0.48, 70 + (4 if k in (0, 2, 4) else 0))
        r = ROOT[c]
        s.add("Bass", r, t, 0.95, 74)
        s.add("Bass", r + 7, t + 1, 0.95, 70)
        s.add("Bass", r + 12, t + 2, 1.45, 72)
        if loud:
            strum(s, c, t, 0.9, 76)
            strum(s, c, t + 1, 0.9, 70)
            strum(s, c, t + 2, 1.45, 74)
        # drums: kick on the 2s, snare on the 2nd group and the 7th eighth
        fill = rep in (7, 15)
        hit(s, "Kick", t, 84)
        hit(s, "Snare", t + 1, 80)
        hit(s, "Kick", t + 2, 76)
        cym = "Ride" if loud else "Hat"
        for k in range(7 if not fill else 4):
            hit(s, cym, t + k * 0.5, (70 if loud else 62) if k in (0, 2, 4) else (60 if loud else 52))
        if fill:
            for at, ch, v in ((2, "Tom", 74), (2.25, "Tom", 76), (2.5, "Floor Tom", 78),
                              (2.75, "Floor Tom", 80), (3, "Snare", 84), (3.25, "Snare", 86)):
                hit(s, ch, t + at, v)
        else:
            hit(s, "Snare", t + 3, 82)
        if rep == 0 or (loud and rep % 2 == 0):
            hit(s, "Crash", t, 84)
    return s


def breakdown():
    """Quiet, then everything builds into the last chorus."""
    s = Sec("Breakdown", 8, "#7A6FBF")
    twinkle(s, BREAK[:4], 0, 70)
    for i, c in enumerate(BREAK[4:]):                         # the twinkle grows with the drums
        twinkle(s, [c], 4 + i, 66 + i * 3)
    for i, name in enumerate(["D5", "E5", "F5", "E5", "D5", "E5", "F5", "G5"]):
        s.add("Twinkle R", midi(name), i * 4, 3.8, 68 + i * 2)
    for i, c in enumerate(BREAK[4:]):                         # quarters, getting louder
        for q in range(4):
            s.add("Bass", ROOT[c], (4 + i) * 4 + q, 0.9, 64 + i * 4 + q)
    for b in range(4, 8):
        for q in range(4):
            hit(s, "Kick", b * 4 + q, 62 + (b - 4) * 6 + q)
    for k in range(8):                                        # bar 7: eighths
        hit(s, "Snare", 24 + k * 0.5, 66 + k * 2)
    for k in range(16):                                       # bar 8: sixteenths
        hit(s, "Snare", 28 + k * 0.25, 74 + int(k * 1.5))
    return s


def outro():
    s = Sec("Outro", 8, "#4FB8A8")
    twinkle(s, OUTRO[:4], 0, 72)
    harmonics(s, OUTRO[:4], 0, 68)
    bass_verse(s, OUTRO[:4], 0, 66, "Fmaj9")
    for i in range(4):
        for q in range(4):
            hit(s, "Ride", i * 4 + q, 66 if q == 0 else 60)
        hit(s, "Kick", i * 4, 70)
        hit(s, "Snare", i * 4 + 3, 64)
    for k, p in enumerate(V["Fmaj9"]):                        # the last chord rings out
        s.add("Twinkle L", p, 16 + k * 0.08, 16 - k * 0.08, 70 - k)
    for p in (77, 81, 84):
        s.add("Twinkle R", p, 16, 16, 62)
    s.add("Bass", 29, 16, 15.9, 70)
    hit(s, "Kick", 16, 76)
    hit(s, "Crash", 16, 76)
    return s


def compose():
    secs = [intro(), verse("Verse 1", True), chorus("Chorus 1"), verse("Verse 2", False),
            chorus("Chorus 2"), bridge(), breakdown(), chorus("Last Chorus", 16), outro()]
    for i, s in enumerate(secs):
        level = LEVEL[s.name]
        nxt = LEVEL[secs[i + 1].name] if i + 1 < len(secs) else level
        end = s.bars * 4
        for ch, notes in s.parts.items():
            for n in notes:
                ramp = max(0.0, (n[1] - (end - 8)) / 8) * (nxt - level) * 0.5
                n[3] = int(round(min(100, max(50, n[3] + level + ramp))))
                n[1] = round(n[1], 4)
                n[2] = round(max(0.05, min(n[2], end - n[1])), 4)   # nothing rings past the end
    return secs


def check(secs):
    """Per bar median velocity across the band, and the biggest jump between bars."""
    meds = []
    for s in secs:
        for b in range(s.bars):
            vs = [n[3] for ns in s.parts.values() for n in ns if b * 4 <= n[1] < b * 4 + 4]
            meds.append((s.name, b + 1, statistics.median(vs) if vs else None))
    jumps = [(abs(b[2] - a[2]), a, b) for a, b in zip(meds, meds[1:]) if a[2] and b[2]]
    return meds, max(jumps)


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
        _, (jump, a, b) = check(secs)
        print("%d bars, %.2f minutes at %d BPM; biggest bar-to-bar median move %.1f (%s %d -> %s %d)"
              % (bar - 1, (bar - 1) * 4 / TEMPO, TEMPO, jump, a[0], a[1], b[0], b[1]))
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
