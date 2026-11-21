"""Jazz Ballad: a whole trio ballad written note by note for the piano roll.

Built from the hand-written ballad the user approved (examples/jazz_ballad.py):

  form      Intro(4) A(8) A(8, turns to the bridge) B(8) A(8) + tag ending(4)
  harmony   functional: ii-V-I, iii-VI, backdoor bVII, tritone subs, a bridge
            on IV or toward II7; every chord a 9th, 11th, 13th or altered
  Rhodes    rootless A/B-form voicings moving as little as possible, the
            chord after a ii pushed a swung eighth early, a melody on top
  bass      a two-feel with swung chromatic approach notes in the A sections,
            walking quarters in the bridge, never above FL's C4 (MIDI 48)
  drums     soft spang-a-lang ride, cross-stick on 4, feathered kick, ghost
            snare triplets and a triplet lift into each new section

Everything is in beats from the start of a section; T (2/3) is a swung
offbeat. compose() is pure: no FL, same seed, same ballad.
"""
import random

T = 2.0 / 3.0
THIRD = 1.0 / 3.0

# ---- chords ---------------------------------------------------------------------
# Rootless voicings as intervals above the root, an A form and a B form (and
# for maj9 and m9 the 5th-on-the-bottom shape the hand-written ballad used);
# the voicing for each chord is the one closest to the chord before.
QUALITIES = {
    "maj9": [(4, 7, 11, 14), (11, 14, 16, 19), (7, 11, 14, 16)],     # + 5 7 9 3
    "6/9": [(4, 9, 14, 19), (9, 14, 16, 19)],
    "m9": [(3, 7, 10, 14), (10, 14, 15, 19), (7, 10, 14, 15)],       # + 5 b7 9 b3
    "m11": [(3, 5, 7, 10), (10, 14, 15, 17)],
    "13": [(10, 14, 16, 21), (4, 9, 10, 14)],
    "13b9": [(4, 9, 10, 13), (10, 13, 16, 21)],
    "7b9": [(4, 7, 10, 13), (10, 13, 16, 19)],
    "7alt": [(4, 8, 10, 15), (10, 15, 16, 20)],
    "9#11": [(2, 4, 6, 10), (10, 14, 16, 18)],
    "9sus": [(5, 7, 10, 14), (10, 14, 17, 19)],
    "7sus4b9": [(5, 7, 10, 13), (10, 13, 17, 19)],
    "m7b5": [(0, 3, 6, 10), (3, 6, 10, 12)],
    "maj7#11": [(0, 4, 7, 11), (4, 6, 7, 11)],
    "maj9#11": [(4, 6, 11, 14), (11, 14, 16, 18)],
}
# Tones a melody may land on, as intervals above the root.
COLOR = {
    "maj9": (4, 7, 11, 14), "6/9": (4, 7, 9, 14), "m9": (3, 7, 10, 14),
    "m11": (3, 7, 10, 14, 17), "13": (4, 10, 14, 21), "13b9": (4, 10, 13, 21),
    "7b9": (4, 7, 10, 13), "7alt": (4, 10, 13, 15, 20), "9#11": (4, 10, 14, 18),
    "9sus": (5, 10, 14, 7), "7sus4b9": (5, 10, 13, 7), "m7b5": (3, 6, 10, 0),
    "maj7#11": (4, 7, 11, 18), "maj9#11": (4, 11, 14, 18),
}
DOMINANT = {"13", "13b9", "7b9", "7alt", "9#11", "9sus", "7sus4b9"}
MINOR = {"m9", "m11", "m7b5"}
NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

COMP_LOW, COMP_HIGH = 46, 66      # where the left hand's voicings sit
MEL_LOW, MEL_HIGH = 63, 81        # the melody: around FL's Eb5 to A6
BASS_LOW, BASS_HIGH = 28, 48      # the upright: low E to FL's C4


def chord_name(key, root, quality):
    q = {"maj9": "maj9", "6/9": "6/9", "m9": "m9", "m11": "m11", "13": "13",
         "13b9": "13b9", "7b9": "7b9", "7alt": "7alt", "9#11": "9#11", "9sus": "9sus",
         "7sus4b9": "7sus4b9", "m7b5": "m7b5", "maj7#11": "maj7#11",
         "maj9#11": "maj9#11"}[quality]
    return NAMES[(key + root) % 12] + q


# ---- forms: each bar is a list of (degree in semitones above the key, quality, beats)
def _bar(*chords):
    return list(chords)


def _ii_v(rng, last=False):
    """ii - V in one bar, sometimes with the tritone sub or a b9."""
    v = rng.choice(["13", "13", "13b9", "7b9"] + (["13b9"] if last else []))
    if rng.random() < 0.25:
        return _bar((2, "m9", 2), (1, "9#11", 2))     # ii - bII7
    return _bar((2, "m9", 2), (7, v, 2))


def a_section(rng):
    """Bars 1-7 of an A section; bar 8 depends on what follows."""
    one = rng.choice([_bar((0, "maj9", 2), (9, "m11", 2)),
                      _bar((0, "maj9", 2), (9, "7b9", 2)),
                      _bar((0, "6/9", 2), (9, "m11", 2))])
    three = rng.choice([_bar((4, "m9", 2), (9, "7b9", 2)),
                        _bar((4, "m9", 2), (9, "7alt", 2)),
                        _bar((6, "m7b5", 2), (11, "7alt", 2))])     # #iv - VII into iii
    five = rng.choice([_bar((5, "maj9", 2), (10, "9#11", 2)),       # backdoor
                       _bar((5, "maj9", 2), (5, "m9", 2)),          # IV - iv
                       _bar((5, "maj9", 4))])
    six = rng.choice([_bar((4, "m9", 2), (9, "7alt", 2)),
                      _bar((4, "m9", 2), (3, "13", 2)),             # iii - bIII7 (tritone of VI)
                      _bar((0, "maj9", 2), (9, "7alt", 2))])
    return [one, _ii_v(rng), three, _ii_v(rng), five, six,
            _bar((2, "m9", 2), (7, rng.choice(["13b9", "7alt"]), 2))]


A_TURNAROUND = [_bar((0, "maj9", 2), (2, "m9", 1), (7, "13", 1))]
A_TO_BRIDGE = {5: [_bar((7, "m9", 2), (0, "7b9", 2))],               # ii - V of IV
               2: [_bar((4, "m7b5", 2), (9, "7alt", 2))]}            # ii - V of ii


def bridge(rng):
    """(first degree, bars): the bridge, and the degree it starts on."""
    pick = rng.randrange(3)
    if pick == 0:       # on IV, through iv - bVII, back by way of vi and II7
        return 5, [_bar((5, "maj9", 4)), _bar((5, "m9", 2), (10, "13", 2)),
                   _bar((4, "m9", 2), (9, "7b9", 2)), _bar((11, "m7b5", 2), (4, "7alt", 2)),
                   _bar((9, "m9", 4)), _bar((2, "13", 4)), _bar((2, "m9", 4)),
                   _bar((7, "9sus", 2), (7, "7b9", 2))]
    if pick == 1:       # on IV, then down to the II7 of a classic bridge
        return 5, [_bar((5, "maj9", 4)), _bar((4, "m9", 2), (9, "7alt", 2)),
                   _bar((2, "m9", 4)), _bar((2, "m9", 2), (1, "9#11", 2)),
                   _bar((0, "maj9", 4)), _bar((2, "13", 4)), _bar((2, "m9", 4)),
                   _bar((7, "9sus", 2), (7, "7b9", 2))]
    # on ii: a long ii - V, a resting I, then II7 pulling back
    return 2, [_bar((2, "m9", 4)), _bar((7, "13", 4)), _bar((0, "maj9", 4)),
               _bar((4, "m7b5", 2), (9, "7alt", 2)), _bar((2, "m9", 4)),
               _bar((2, "13", 4)), _bar((4, "m9", 2), (9, "7alt", 2)),
               _bar((7, "9sus", 2), (7, "7b9", 2))]


def intro(rng):
    return rng.choice([
        [_bar((5, "maj9", 4)), _bar((4, "m9", 2), (9, "7b9", 2)), _bar((2, "m9", 4)),
         _bar((7, "9sus", 2), (7, "7b9", 2))],
        [_bar((2, "m9", 2), (7, "13", 2)), _bar((4, "m9", 2), (9, "7alt", 2)),
         _bar((2, "m9", 2), (1, "9#11", 2)), _bar((7, "9sus", 2), (7, "7b9", 2))],
        [_bar((8, "maj7#11", 4)), _bar((7, "9sus", 4)), _bar((8, "maj7#11", 4)),
         _bar((7, "9sus", 2), (7, "7b9", 2))],
    ])


TAG = [_bar((4, "m9", 2), (9, "7alt", 2)), _bar((2, "m9", 2), (7, "13b9", 2)),
       _bar((4, "m9", 2), (9, "7alt", 2)),
       _bar((8, "maj7#11", 2), (7, "7sus4b9", 2)), _bar((0, "maj9#11", 4))]


def timeline(bars):
    """[(start beat, length, degree, quality)] from bars of chords."""
    out, at = [], 0.0
    for bar in bars:
        for degree, quality, beats in bar:
            out.append((at, float(beats), degree, quality))
            at += beats
    return out


# ---- the Rhodes: voicings and comping ----------------------------------------------
def voice(key, degree, quality, prev):
    """The voicing of this chord nearest to `prev` (a list of 4 MIDI notes)."""
    root = (key + degree) % 12
    options = []
    for shape in QUALITIES[quality]:
        for octave in range(2, 7):
            notes = [12 * octave + root + i for i in shape]
            if notes[0] >= COMP_LOW and notes[-1] <= COMP_HIGH:
                options.append(notes)
    if not options:     # a wide shape that fits no octave of the range: the nearest
        options = [[12 * o + root + i for i in shape] for shape in QUALITIES[quality]
                   for o in range(2, 7)]
        options = [n for n in options if n[0] >= COMP_LOW - 6 and n[-1] <= COMP_HIGH + 6]
    centre = (COMP_LOW + COMP_HIGH) / 2.0 - 2

    def cost(notes):
        if prev:
            return sum(abs(a - b) for a, b in zip(sorted(notes), sorted(prev)))
        return abs(sum(notes) / 4.0 - centre)
    return min(options, key=cost)


def comp(key, chords, rng, level=0, held_restrike=0.6, voicing=None):
    """Rhodes left hand: [pitch, start, length, velocity]. The chord after a ii
    (or any dominant that follows a minor chord mid-bar) is pushed a swung eighth
    early; a chord held a whole bar is struck again on the and of 3, softly."""
    out, prev = [], voicing
    starts = []
    for i, (start, length, degree, quality) in enumerate(chords):
        at = start
        before = chords[i - 1] if i else None
        if (before and quality in DOMINANT and before[3] in MINOR and start % 4 == 2
                and before[1] >= 2 and rng.random() < 0.75):
            at = start - THIRD
        starts.append(at)
    for i, (start, length, degree, quality) in enumerate(chords):
        notes = voice(key, degree, quality, prev)
        prev = notes
        at = starts[i]
        end = starts[i + 1] if i + 1 < len(chords) else start + length
        vel = 60 + level + rng.randint(-4, 4)
        if length >= 4 and rng.random() < held_restrike and i + 1 < len(chords):
            out += [[p, at, 1.9, vel] for p in notes]
            out += [[p, at + 2 + T, end - (at + 2 + T) - 0.1, vel - 10] for p in notes]
        else:
            out += [[p, at, max(0.3, end - at - 0.1), vel] for p in notes]
    return out, prev


# ---- the melody ------------------------------------------------------------------
# One bar of rhythm each: (start, length), from the hand-written ballad.
RHYTHMS = [
    [(0, 1.5), (1 + T, THIRD), (2, 4 * THIRD), (3 + THIRD, THIRD), (3 + T, THIRD)],
    [(0, 5 * THIRD), (1 + T, THIRD), (2, 1), (3, T), (3 + T, THIRD)],
    [(0, 1.5), (1 + T, THIRD), (2, 1), (3, T), (3 + T, THIRD)],
    [(0, 2), (2, 1), (3 + THIRD, THIRD), (3 + T, THIRD)],
    [(0, T), (T, 1), (1 + T, THIRD), (2, T), (2 + T, T), (3 + THIRD, THIRD), (3 + T, THIRD)],
    [(0, 1), (1, T), (1 + T, THIRD), (2, T), (2 + T, T), (3 + THIRD, T)],
    [(0, 1.5), (1 + T, THIRD), (2, 2)],
    [(0, T), (T, THIRD), (1, 5 * THIRD), (2 + T, THIRD), (3, T), (3 + T, THIRD)],
]
CADENCE = [[(0, 2.5)], [(0, 3)], [(0, 4 * THIRD), (1 + THIRD, THIRD), (2, 2)]]


def chord_at(chords, beat):
    for start, length, degree, quality in chords:
        if start <= beat < start + length:
            return degree, quality
    return chords[-1][2], chords[-1][3]


def _scale(key):
    return {(key + i) % 12 for i in (0, 2, 4, 5, 7, 9, 11)}


def melody(key, chords, rng, bars, cadence_bars=(), peak_bar=None, level=0, start_pitch=None,
           rhythms=None):
    """A melody over `chords`: strong notes on the chord's color tones, the
    notes between them stepping toward the next one. The line rises to
    `peak_bar` and settles after it; `cadence_bars` get long notes."""
    scale = _scale(key)
    rhythms = list(rhythms or [])
    events = []
    for bar in range(bars):
        if bar in cadence_bars:
            cells = rng.choice(CADENCE)
        elif bar < len(rhythms):
            cells = rhythms[bar]
        else:
            cells = rng.choice(RHYTHMS)
        if bar >= len(rhythms):
            rhythms.append(cells)
        events += [(bar * 4 + s, l) for s, l in cells]
    peak = peak_bar if peak_bar is not None else bars * 5 // 8
    prev = start_pitch or (MEL_LOW + MEL_HIGH) // 2 - 2
    out = []
    for i, (start, length) in enumerate(events):
        degree, quality = chord_at(chords, start)
        root = (key + degree) % 12
        strong = (start % 1 == 0) or length >= 1
        # the contour: drift up toward the peak bar, down after it
        bar = int(start // 4)
        aim = MEL_LOW + 5 + min(bar, peak) * 1.4 - max(0, bar - peak) * 1.6
        aim += rng.uniform(-2, 2)
        if strong:
            pcs = {(root + c) % 12 for c in COLOR[quality]}
        else:
            chord = {(root + c) % 12 for c in QUALITIES[quality][0]} | {root}
            pcs = (scale | chord) - {(root + 5) % 12} if quality not in ("9sus", "7sus4b9", "m11") \
                else scale | chord
        cands = [p for p in range(MEL_LOW, MEL_HIGH + 1) if p % 12 in pcs]
        if not strong:
            cands = [p for p in cands if 1 <= abs(p - prev) <= 3] or cands

        def cost(p):
            leap = abs(p - prev)
            return (leap if leap <= 5 else leap * 2.5) * 0.6 + abs(p - aim) * 0.5 \
                + (3 if p == prev else 0) + rng.uniform(0, 1.5)
        pitch = min(cands, key=cost)
        vel = (84 if strong else 74) + level + rng.randint(-5, 5) + (6 if bar == peak else 0)
        out.append([pitch, start, length, vel])
        prev = pitch
    return out, rhythms


# ---- the upright -------------------------------------------------------------------
def _bass_note(pc, near):
    options = [p for p in range(BASS_LOW, BASS_HIGH + 1) if p % 12 == pc]
    return min(options, key=lambda p: abs(p - near))


def two_feel(key, chords, rng, level=0, prev=39):
    """Roots on the chord, a fifth on beat 3 of a held bar, and a swung chromatic
    approach into the next root about half the time."""
    out = []
    for i, (start, length, degree, quality) in enumerate(chords):
        root = (key + degree) % 12
        nxt = chords[i + 1] if i + 1 < len(chords) else None
        note = _bass_note(root, prev)
        prev = note
        vel = 94 + level + rng.randint(-4, 6)
        if length >= 4:
            fifth = _bass_note((root + 7) % 12, note)
            out += [[note, start, 1.9, vel], [fifth, start + 2, 1.9, vel - 6]]
            continue
        approach = nxt and length >= 2 and rng.random() < 0.5
        if approach:
            target = _bass_note((key + nxt[2]) % 12, note)
            side = -1 if rng.random() < 0.6 else 1
            out += [[note, start, length - 0.6, vel],
                    [max(BASS_LOW, min(BASS_HIGH, target + side)), start + length - THIRD,
                     0.3, vel - 14]]
        else:
            out.append([note, start, max(0.5, length - 0.1), vel])
    return out, prev


def walking(key, chords, rng, level=0, prev=39, then=0):
    """Quarter notes: the root on the chord's first beat, chord tones and scale
    steps between, a chromatic step into the next root on the last beat (after
    the last chord: degree `then`, the next section's first chord)."""
    scale = _scale(key)
    out = []
    for i, (start, length, degree, quality) in enumerate(chords):
        root = (key + degree) % 12
        target_pc = (key + (chords[i + 1][2] if i + 1 < len(chords) else then)) % 12
        tones = [(root + c) % 12 for c in (0, QUALITIES[quality][0][0], 7, 10)]
        beats = int(round(length))
        note = _bass_note(root, prev)
        line = [note]
        for b in range(1, beats):
            if b == beats - 1:
                target = _bass_note(target_pc, line[-1])
                line.append(max(BASS_LOW, min(BASS_HIGH, target + rng.choice((-1, 1)))))
            else:
                pcs = set(tones) | (scale if rng.random() < 0.4 else set())
                cands = [p for p in range(BASS_LOW, BASS_HIGH + 1)
                         if p % 12 in pcs and 1 <= abs(p - line[-1]) <= 5]
                line.append(rng.choice(cands) if cands else line[-1])
        for b, p in enumerate(line):
            out.append([p, start + b, 0.85, (98 if b % 2 == 0 else 90) + level])
        prev = line[-1]
    return out, prev


# ---- the drums -------------------------------------------------------------------
def ride(bars, level=0, start=0.0):
    out = []
    for bar in range(bars):
        b = start + bar * 4
        for off, v in ((0, 66), (1, 58), (1 + T, 42), (2, 64), (3, 58), (3 + T, 42)):
            out.append([60, b + off, 0.25, max(1, v + level)])
    return out


def cross_stick(bars, level=0):
    return [[60, bar * 4 + 3, 0.25, (50 if bar % 2 else 44) + level] for bar in range(bars)]


def feathered_kick(bars, level=0):
    out = []
    for bar in range(bars):
        out += [[60, bar * 4, 0.25, 34 + level], [60, bar * 4 + 2, 0.25, 28 + level]]
    return out


def ghosts(bars, rng, count=3, comping=False, lift=True):
    """Ghost-note triplets on the snare; `comping` adds a soft hit most bars, and
    `lift` a triplet run into the next section on the last beat and a half."""
    out = []
    spots = sorted(rng.sample(range(bars - 1), min(count, bars - 1)))
    for bar in spots:
        out.append([60, bar * 4 + rng.choice((1 + T, 2 + THIRD, 2 + T, 3 + THIRD)), 0.25,
                    rng.randint(24, 30)])
    if comping:
        for bar in range(bars - 1):
            if rng.random() < 0.8:
                out.append([60, bar * 4 + rng.choice((1 + T, 2 + T)), 0.25, rng.randint(34, 40)])
    if lift:
        end = bars * 4
        out += [[60, end - 5 * THIRD + THIRD * i, 0.25, 30 + 6 * i] for i in range(5)]
    merged = {}
    for n in out:                       # two hits on one spot: keep the louder
        key = round(n[1], 3)
        if key not in merged or n[3] > merged[key][3]:
            merged[key] = n
    return sorted(merged.values(), key=lambda n: n[1])


# ---- the song ----------------------------------------------------------------------
SECTION_COLORS = {"Intro": 0x7A5C99, "A": 0x4F7FB0, "B": 0xD9824F, "Ending": 0x8FB04F}


def _clean(notes, melody_notes=()):
    """Round, drop any accompaniment note on the same pitch as a melody note it
    would overlap (FL merges those), and sort."""
    out = []
    for p, s, l, v in notes:
        clash = any(m[0] == p and s < m[1] + m[2] and m[1] < s + l for m in melody_notes)
        if not clash:
            out.append([int(p), round(s, 4), round(l, 4), int(max(1, min(127, v)))])
    return sorted(out, key=lambda n: (n[1], n[0]))


def compose(key, seed=None):
    """A whole ballad in `key` (0 = C ... 11 = B).

    Returns {"sections": [{"name", "bars", "chords": [names per bar], "parts":
    {"keys" / "bass" / "ride" / "rim" / "kick" / "snare": notes}}], "form": [names]}.
    Notes are [MIDI pitch, start beat, length in beats, velocity]."""
    rng = random.Random(seed)
    a_bars = a_section(rng)
    b_first, b_bars = bridge(rng)
    to_bridge = A_TO_BRIDGE.get(b_first, A_TO_BRIDGE[5])
    sections = []

    def section(name, bars_of_chords, mel_kwargs, bass_kind="two", level=0, drums=True,
                lift=True, comping=False, ride_level=0, mel=None):
        chords = timeline(bars_of_chords)
        bars = len(bars_of_chords)
        keys, _ = comp(key, chords, rng, level=level - 2)
        if mel is None:
            mel, _ = melody(key, chords, rng, bars, level=level, **mel_kwargs)
        if bass_kind == "walk":
            bass, _ = walking(key, chords, rng, level=level, then=0)
        else:
            bass, _ = two_feel(key, chords, rng, level=level)
        parts = {"keys": _clean(keys, mel) + _clean(mel), "bass": _clean(bass)}
        if drums:
            parts.update({
                "ride": _clean(ride(bars, ride_level)),
                "rim": _clean(cross_stick(bars)),
                "kick": _clean(feathered_kick(bars, 6 if level > 0 else 0)),
                "snare": _clean(ghosts(bars, rng, comping=comping, lift=lift))})
        sections.append({"name": name, "bars": bars, "parts": parts,
                         "chords": [" ".join(chord_name(key, d, q) for d, q, _ in bar)
                                    for bar in bars_of_chords]})
        return mel

    # Intro: the Rhodes and the bass alone
    intro_bars = intro(rng)
    section("Intro", intro_bars, dict(cadence_bars=(1, 3), peak_bar=2), level=-12,
            drums=False)
    # A1: the theme. Its first six bars come back in every A.
    first = a_bars + A_TURNAROUND
    mel_a, rhythm_a = melody(key, timeline(first), rng, 8, cadence_bars=(7,), peak_bar=5)
    head = [n for n in mel_a if n[1] < 24]

    def new_tail(bars_of_chords, **kwargs):
        """A melody for bars 7 on, carrying on from the theme's bar 6."""
        tail, _ = melody(key, timeline(bars_of_chords[6:]), rng, len(bars_of_chords) - 6,
                         start_pitch=head[-1][0], **kwargs)
        return [[p, s + 24, l, v] for p, s, l, v in tail]

    section("A1", first, {}, mel=mel_a)
    # A2: the theme again, bar 8 turning toward the bridge
    second = a_bars + to_bridge
    section("A2", second, {}, mel=head + new_tail(second, peak_bar=1))
    # B: higher, walking bass, the ride and snare up a notch
    section("B", b_bars, dict(cadence_bars=(), peak_bar=4, start_pitch=head[0][0] + 5),
            bass_kind="walk", level=6, comping=True, ride_level=6)
    # A3 and the tag ending: 12 bars, the last chord held
    last = a_bars + TAG
    tail = new_tail(last, cadence_bars=(5,), peak_bar=2, level=-2)
    for n in tail:
        if n[1] >= 36:
            n[3] -= 8                   # the tag fades
    section("A3", last, {}, mel=head + tail, lift=False, level=-2)
    end = sections[-1]["parts"]
    end["ride"] = [n if n[1] < 40 else [n[0], n[1], n[2], n[3] - 10]
                   for n in end["ride"] if n[1] < 44] + [[60, 44.0, 0.25, 58]]
    end["kick"] = [n for n in end["kick"] if n[1] < 44] + [[60, 44.0, 0.25, 40]]
    end["rim"] = [n for n in end["rim"] if n[1] < 44]
    end["snare"] = [n for n in end["snare"] if n[1] < 40]
    for part in ("keys", "bass"):      # the last bar rings out
        for n in end[part]:
            if n[1] >= 44:
                again = [m[1] for m in end[part] if m[0] == n[0] and m[1] > n[1]]
                n[2] = round(min(again + [47.9]) - n[1] - (0.02 if again else 0), 4)
    return {"sections": sections, "form": ["Intro", "A1", "A2", "B", "A3"]}
