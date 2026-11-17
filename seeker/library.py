"""Genre drum vocabulary.

Each lane is a list of interchangeable variants. A variant is one bar (16 chars)
or two bars (32 chars) of 16th-note steps:

    X accent    x hit    o ghost    . rest

An empty string means "this lane sits out". The generator picks one variant per
lane, so a genre with 6 kicks, 3 snares and 5 hats already yields 90 grooves
before bar-two variations are applied - add variants here to widen a genre.

bpm is the range the groove is idiomatic at; `straight` marks four-on-the-floor
styles whose kick should never be varied.

`bass` is the 808 / bass lane. Notes are scale degrees of the chosen key, so the
line is always in key: 1 root, 2-4 above it, 5-7 BELOW it (a bass walks down to
the fifth), 8 the root an octave up. Two ways to describe a line:

    lines     fixed rhythms, one degree per 16th step ("." = rest), 1 or 2 bars
    follow    the 808 doubles the kick (the number is the chance each
              syncopated kick keeps its 808); `contours` then say which degree
              is sounding on each of the 8 beats of the two bars
"""

GENRES = {
    "trap": dict(
        name="Trap", bpm=(128, 162),
        kick=["x.....x...x.....", "x......x..x.....", "x..x..x.....x...",
              "x.........x..x..", "x.x.......x.....", "x......x.x...x..",
              "x.....x...x.....x..x..x......x..", "x......x..x..x.."],
        snare=["........X.......", "........X.....o.", "........X..o...."],
        clap=["........x.......", "........x.......", ""],
        hat=["x.x.x.x.x.x.x.x.", "x.x.x.xxx.x.x.x.", "x.x.xxx.x.x.x.xx",
             "x.xxx.x.x.x.x.x.", "xxx.x.x.x.x.xxx.", "x.x.x.x.x.xxxxx."],
        openhat=["", "..............x.", "......x.........", "............x..."],
        perc=["", "", "...x......x.....", ".....x.......x.."],
        bass=dict(follow=0.9, contours=["11111111", "11111111", "11111137", "11111166", "11113311", "11111175", "11118111"]),
    ),
    "drill": dict(
        name="Drill", bpm=(136, 148),
        kick=["x.....x...x.....", "x..x......x..x..", "x.....x....x....",
              "x..x...x..x.....", "x.....x...x..x..x..x......x....."],
        snare=["........X.................X.....", "........X...................X...",
               "........X.....o...........X....."],
        clap=["", "........x.................x....."],
        hat=["x..x..x.x..x..x.", "x..x..x.x..x.xx.", "x.xx..x.x..x..x.",
             "x..x..xxx..x..x."],
        openhat=["", "......x.........", "..............x."],
        perc=["", "..x.....x..x....", "...x..x......x.."],
        bass=dict(follow=0.9, contours=["11111111", "11116611", "11111133", "11117766", "11111166"]),
    ),
    "boombap": dict(
        name="Boom Bap", bpm=(80, 100),
        kick=["x.......x.x.....", "x..x....x.x.....", "x.....x.x.......",
              "x......xx.x.....", "x.x.....x..x....", "x.........x....x",
              "x.......x.x.....x..x....x.x...x."],
        snare=["....X.......X...", "....X..o....X...", "....X.......X..o",
               "....X..o.o..X..."],
        clap=["", "", "....x.......x..."],
        hat=["x.x.x.x.x.x.x.x.", "x.x.x.x.x.x.x.xx", "x.xxx.x.x.xxx.x.",
             "x.x.x.xxx.x.x.x."],
        openhat=["", "..............x.", "......x.......x."],
        perc=["", "", "..........x....."],
        bass=dict(follow=0.8, contours=["11111111", "11111177", "11114411", "11111157"]),
    ),
    "lofi": dict(
        name="Lo-Fi", bpm=(66, 90),
        kick=["x.....x...x.....", "x......x..x.....", "x..x......x.....",
              "x.........x..x.."],
        snare=["....x.......x...", "....x.......x..o", "....x..o....x..."],
        clap=[""],
        hat=["x.x.x.x.x.x.x.x.", "..x...x...x...x.", "x.x.x.xxx.x.x.x.",
             "x.x.x.x.x.x.x.xx"],
        openhat=["", "", "..............x."],
        perc=["", "......x.........", "...x.......x...."],
        bass=dict(follow=0.8, contours=["11111111", "11114411", "11111155", "11116655"]),
    ),
    "rnb": dict(
        name="R&B", bpm=(60, 82),
        kick=["x......x..x.....", "x.x.......x..x..", "x..x...x..x.....",
              "x.........xx...x"],
        snare=["....X.......X...", "....X.......X.o.", "....X..o....X..."],
        clap=["....x.......x...", ""],
        hat=["xxxxxxxxxxxxxxxx", "x.xxx.xxx.xxx.xx", "xxx.xxx.xxx.xxx.",
             "x.x.x.x.x.x.x.x."],
        openhat=["", ".......x........", "..............x."],
        perc=["", "...x.....x......", "..x.......x..x.."],
        bass=dict(follow=0.85, contours=["11111111", "11116611", "11114455", "11113344"]),
    ),
    "house": dict(
        name="House", bpm=(118, 130), straight=True,
        kick=["x...x...x...x..."],
        snare=["", "", "....x.......x..o", "...............o"],
        clap=["....x.......x...", "....x.......x...", "....x.......x.x."],
        hat=["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", ".xx..xx..xx..xx.",
             "..x...x...x...x."],
        openhat=["..x...x...x...x.", "..x...x...x...x.", "......x.......x."],
        perc=["", "...x..x...x..x..", ".x...x.....x....", "x..x..x...x..x.."],
        bass=dict(lines=["..1...1...1...1.", "..1..1....1..1..", "..1...1..1....1.", "..1...1...1...1...1...1...3...7."]),
    ),
    "techno": dict(
        name="Techno", bpm=(126, 142), straight=True,
        kick=["x...x...x...x...", "x...x...x...x...", "x...x...x...x.x."],
        snare=["", "", "............x...", ".......o.......o"],
        clap=["....x.......x...", "", "............x..."],
        hat=["..x...x...x...x.", "xxxxxxxxxxxxxxxx", "x.xxx.xxx.xxx.xx",
             ".x.x.x.x.x.x.x.x"],
        openhat=["..x...x...x...x.", "", "..x...x...x...x."],
        perc=["", "..x..x..x..x..x.", "x..x..x..x..x...", "......x......x.."],
        bass=dict(lines=["..1...1...1...1.", ".111.111.111.111", "..11..11..11..11", "..1..1....1..1.."]),
    ),
    "garage": dict(
        name="UK Garage", bpm=(126, 138),
        kick=["x.........x.....", "x......x..x.....", "x.........x..x..",
              "x..x......x....."],
        snare=["....X.......X...", "....X.......X..o", "....X..o....X..."],
        clap=["....x.......x...", ""],
        hat=["..x...x...x...x.", "x.xx..x.x.xx..x.", ".xx..xx..xx..xx.",
             "x.x..xx.x.x..xx."],
        openhat=["", "..x.......x.....", "......x.......x."],
        perc=["", "...x.....x......", ".x......x....x.."],
        bass=dict(follow=0.8, contours=["11111111", "11111133", "11117711"], lines=["..1...1..1....1.", "...1..1......1.1"]),
    ),
    "reggaeton": dict(
        name="Reggaeton", bpm=(86, 104), straight=True,
        kick=["x...x...x...x...", "x...x...x...x...", "x.......x......."],
        snare=["...x..x....x..x.", "...x..x....x..x.", "...x..x....x..xx"],
        clap=["", "......x.......x."],
        hat=["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "..x...x...x...x."],
        openhat=["", "..............x.", "..x.......x....."],
        perc=["", "..x...x...x...x.", ".x...x...x...x.."],
        bass=dict(lines=["1..1..1.1..1..1.", "1...1...1...1...", "1..1..1.1..1..1.1..1..1.5..5..7."]),
    ),
    "afrobeats": dict(
        name="Afrobeats", bpm=(96, 118),
        kick=["x.....x...x.....", "x..x..x...x.....", "x.....x.x.....x.",
              "x...x..x..x....."],
        snare=["....x.......x...", "......x.....x...", "....x..x....x...",
               "...x..x....x..x."],
        clap=["", "....x.......x..."],
        hat=["x.xxx.xxx.xxx.xx", "xxxxxxxxxxxxxxxx", "x.x.x.x.x.x.x.x.",
             "xx.xxx.xxx.xxx.x"],
        openhat=["", "..x...x...x...x.", "..............x."],
        perc=["x..x..x...x.x...", "..x..x....x..x..", "x..x...x..x..x..", ""],
        bass=dict(follow=0.8, contours=["11111111", "11113311", "11111155"], lines=["1.....1...1.....", "1..1..1...1.....1..1..1...3.....", "1.....1.5.....1."]),
    ),
    "amapiano": dict(
        name="Amapiano", bpm=(108, 116),
        kick=["x...x...x...x...", "x.....x...x.....", "x...x...x..x...."],
        snare=["", "....x.......x...", "......x.......x."],
        clap=["....x.......x...", "....x.......x..."],
        hat=["xxxxxxxxxxxxxxxx", "x.xxx.xxx.xxx.xx", "xxx.xxx.xxx.xxx."],
        openhat=["", "..x...x...x...x."],
        perc=["..x..x..x..x.x..", "x..x..x..x..x.x.", ".x..x..x.x..x...",
              "...x..x...x..x.."],
        bass=dict(lines=["1..1..1...1.1...", "1.....1..1..1.1.", "1..1....1..1..3.1..1....1..5..7.", "..1..1.1...1..1."]),
    ),
    "dnb": dict(
        name="Drum & Bass", bpm=(164, 180),
        kick=["x.........x.....", "x.........xx....", "x.....x...x.....",
              "x.x.......x....."],
        snare=["....X.......X...", "....X..o.o..X...", "....X.......X.o.",
               "....X..o....X..o"],
        clap=[""],
        hat=["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "x.xxx.x.x.xxx.x."],
        openhat=["", "..............x.", "......x........."],
        perc=["", "......x......x..", ".......x........"],
        bass=dict(lines=["1.........1.....", "1.........1.....3.........1.....", "1.....1...1.....", "1.........1.....1.........7.5..."]),
    ),
    "jersey": dict(
        name="Jersey Club", bpm=(130, 146),
        kick=["x...x...x..x..x.", "x...x...x..x..x.", "x...x...x..x.x..",
              "x..xx...x..x..x."],
        snare=["", "....x.......x..."],
        clap=["....x.......x...", "....x.......x.x."],
        hat=["x.x.x.x.x.x.x.x.", "..x...x...x...x.", "xxxxxxxxxxxxxxxx"],
        openhat=["", "..x...x...x...x."],
        perc=["", "...x..x...x..x..", "..x.......x....."],
        bass=dict(follow=0.9, contours=["11111111", "11111133", "11117711"]),
    ),
    "pop": dict(
        name="Pop / Rock", bpm=(92, 132),
        kick=["x.......x.......", "x.......x.x.....", "x.....x.x.......",
              "x..x....x.......", "x.......xx......", "x.x.....x.x....."],
        snare=["....X.......X...", "....X.......X...", "....X.......X.o."],
        clap=["", "....x.......x..."],
        hat=["x.x.x.x.x.x.x.x.", "x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx",
             "x...x...x...x..."],
        openhat=["", "..............x.", "......x.......x."],
        perc=["", "", "..x...x...x...x."],
        bass=dict(follow=0.9, contours=["11111111", "11114455"], lines=["1.1.1.1.1.1.1.1.", "1.1.1.1.1.1.1.1.4.4.4.4.5.5.5.5."]),
    ),
    "funk": dict(
        name="Funk / Breaks", bpm=(94, 126),
        kick=["x.x.......x..x..", "x..x..x...x.....", "x.x....x..x.....",
              "x.x.......xx....", "x......x.xx....."],
        snare=["....X..o.o..X...", "....X..o....X.o.", "....X..o.o...X..",
               "....X.......X..o"],
        clap=[""],
        hat=["x.x.x.x.x.x.x.x.", "xxxxxxxxxxxxxxxx", "x.xxx.x.x.xxx.x.",
             "x.x.x.xxx.x.x.x."],
        openhat=["", "......x.........", "..............x.", "..x.......x....."],
        perc=["", "", "...x.....x......"],
        bass=dict(lines=["1..1..8.1...1.7.", "1.1....8..1..7.1", "1..1....8.1..5.7", "1.8...1.1..8.7.."]),
    ),
    "disco": dict(
        name="Disco", bpm=(110, 126), straight=True,
        kick=["x...x...x...x..."],
        snare=["....X.......X...", "....X.......X..o"],
        clap=["", "....x.......x..."],
        hat=["xxxxxxxxxxxxxxxx", "x.x.x.x.x.x.x.x.", "xx.xxx.xxx.xxx.x"],
        openhat=["..x...x...x...x.", "..x...x...x...x.", ""],
        perc=["", "..x...x...x...x.", "x..x..x...x..x.."],
        bass=dict(lines=["1.8.1.8.1.8.1.8.", "1.8.1.8.1.8.1.88", "1..18...1..18...", "1.8.1.8.1.8.1.8.1.8.1.8.4.8.5.8."]),
    ),
    "dubstep": dict(
        name="Dubstep", bpm=(136, 150),
        kick=["x.........x.....", "x.....x.........", "x..x......x.....",
              "x.........x..x.."],
        snare=["........X.......", "........X.....o."],
        clap=["........x.......", ""],
        hat=["x.x.x.x.x.x.x.x.", "x...x...x...x...", "x.x.x.xxx.x.x.x.",
             "..x...x...x...x."],
        openhat=["", "..............x.", "....x.......x..."],
        perc=["", "...x......x.....", "......x......x.."],
        bass=dict(follow=0.9, contours=["11111111", "11111133", "11116611", "11111177"]),
    ),
}

ROLES = ("kick", "snare", "clap", "hat", "openhat", "perc")

# Chords lane (written into the piano roll of the keys channel).
#
#   rhythm   16 or 32 steps:  x strike a chord   - hold it   . silence
#   voicing  triad, seventh or ninth - how rich the genre's chords are
#   pace     how fast the harmony moves through its four-bar cycle (see PACES)
#
# Chords are built by stacking scale notes on the root, so they are always in
# key, and the 808 and the synth pad follow the same chords.
CHORDS = {
    "trap": dict(pace=["slow", "slow3", "bar", "turn"], voicing="triad", rhythm=["x---------------", "x-----------x---"]),
    "drill": dict(pace=["slow", "slow3", "bar"], voicing="triad", rhythm=["x---------------", "x-----x---------"]),
    "boombap": dict(pace=["bar", "turn", "slow3"], voicing="seventh",
                    rhythm=["x-----x---......", "x---....x-x-....", "x-------..x-----"]),
    "lofi": dict(pace=["bar", "turn", "half"], voicing="ninth",
                 rhythm=["x-------..x-----", "x-----x---------", "x---------x-----"]),
    "rnb": dict(pace=["bar", "turn", "half"], voicing="ninth",
                rhythm=["x-------..x-----", "x---------------", "x-----x---..x---"]),
    "house": dict(pace=["bar", "slow3", "half"], voicing="seventh",
                  rhythm=["..x..x....x..x..", "x..x..x...x..x..", "..x...x...x...x.",
                          "x.....x..x......"]),
    "techno": dict(pace=["drone", "slow"], voicing="triad",
                   rhythm=["..x...x...x...x.", "x..x..x..x..x...", "......x.......x."]),
    "garage": dict(pace=["bar", "half", "turn"], voicing="seventh",
                   rhythm=["..x..x....x..x..", "...x..x...x..x.x", "x--...x--...x-.."]),
    "reggaeton": dict(pace=["bar", "half", "turn"], voicing="triad",
                      rhythm=["x..x..x.x..x..x.", "x-------x-------", "x--x--x-x--x--x-"]),
    "afrobeats": dict(pace=["bar", "half", "turn"], voicing="seventh",
                      rhythm=["x..x..x...x.....", "..x..x..x..x..x.", "x-----x---x-----"]),
    "amapiano": dict(pace=["bar", "turn", "slow3"], voicing="ninth",
                     rhythm=["x-------..x-----", "x---------x-----", "..x-----..x-----"]),
    "dnb": dict(pace=["slow", "slow3", "bar"], voicing="seventh", rhythm=["x---------------", "x---------x-----"]),
    "jersey": dict(pace=["bar", "half"], voicing="triad", rhythm=["x...x...x..x..x.", "x-------x-------"]),
    "pop": dict(pace=["bar", "half", "turn"], voicing="triad",
                rhythm=["x---x---x---x---", "x-------x-------", "x-x-x-x-x-x-x-x."]),
    "funk": dict(pace=["slow", "half", "drone"], voicing="seventh",
                 rhythm=["..x..x....x..x..", "x..x......x..x..", ".x..x..x.....x.."]),
    "disco": dict(pace=["bar", "half", "turn"], voicing="seventh",
                  rhythm=["..x...x...x...x.", "x.x...x.x.x...x.", "..x..x....x..x.."]),
    "dubstep": dict(pace=["drone", "slow", "slow3"], voicing="triad", rhythm=["x---------------"]),
}

# Chord progressions, shared by every genre: four chords each, as scale degrees
# (major "1625" = I vi ii V, in C: C Am Dm G). Each scale leaves out its
# diminished chord (vii in major, ii in minor). A genre's `pace` then decides
# how the four are spread over the four bars.
PROGRESSIONS = {
    "major": ["1625", "1564", "6415", "1465", "2516", "3456", "1345", "4536", "1645",
              "6251", "4156", "1436", "1425", "6341", "4165", "5641", "3625", "1563",
              "4516", "1356"],
    "minor": ["1637", "1467", "1767", "6711", "1376", "4617", "1564", "6417", "1645",
              "3716", "1647", "1436", "6345", "1543", "4516", "1736", "6734", "1675",
              "4673", "1746"],
}

# One character per beat of the four bars; a b c d are the progression's chords
# and t is a turnaround chord that leads back to the start.
PACES = {
    "bar":   "aaaabbbbccccdddd",    # a chord per bar
    "turn":  "aaaabbbbccccddtt",    # ... with a fifth chord squeezed in at the end
    "half":  "aabbccddaabbccdt",    # two chords per bar, twice round
    "slow":  "aaaaaaaabbbbbbbb",    # two chords, two bars each
    "slow3": "aaaaaaaabbbbcccc",
    "drone": "aaaaaaaaaaaaaaaa",    # one chord: techno, dubstep
}
TURNAROUNDS = {"major": "5423", "minor": "7564"}
