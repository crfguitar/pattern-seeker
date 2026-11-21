# Pattern Seeker

https://github.com/user-attachments/assets/a4e42051-d261-47b2-9309-70b2c10e83f5

**Genre-true beats in FL Studio, from one button or from an AI assistant.**

Pattern Seeker writes a complete starting point into FL Studio's current pattern:
drums (kick, snare, clap, hats, percussion), a bass line in key, a four-bar chord
progression on the keys channel, a soft pad on the synth channel and, in rock and
country, a guitar part. Every press gives a different groove and progression,
always inside the style of the chosen genre (22 genres: trap, boom bap, house,
jazz, country, classic soul, rock & roll, classical, ...). One step of **Back**
restores exactly what the pattern held before.

It can also build the rack the beat plays on. From an empty project, one request
adds a channel for each part of the genre (kick, snare, clap, hats, percussion,
bass, keys, pad, guitar), loads a fitting sound into each, names and colours
them, and writes the beat. No template is needed. A genre only plays channels
whose sound suits it: a classical piece gets a cello, never the 808.

And it can turn loops into a song. One request writes a pattern for each section
(verse, chorus, bridge) in the same genre, key and tempo, then lays the sections
out along a playlist track as pattern clips: ABABCB, AABA, or any order you name.
Longer forms are written note by note: a 40-bar jazz ballad in one request, or
a whole hand-composed piece (the `examples/` hold two three-movement pieces for
chamber orchestra) in one call.

Every channel gets its own named mixer insert, and the EQ is set on
CFilteR-01 in each insert, in Hz, dB and Q, from a genre's starting points or
worked out from a piece's score.

There are two ways to drive it:

- **The Pattern Seeker window** (`pattern_seeker.pyw`): an always-on-top window
  with NEW BEAT, a global hotkey (Ctrl+Alt+B), genre/key/tempo pickers, and
  tabs for whole songs and for the rack (build a kit, mixer routing, EQ).
- **The Pattern Seeker MCP server** (`mcp_server.py`): the same engine exposed
  over the [Model Context Protocol](https://modelcontextprotocol.io), so Claude
  (or any MCP client) can make beats from a plain request: *"give me a lo-fi beat
  in A minor, no pad"*, *"another one"*, *"go back, I liked the last one"*,
  *"set up a house track from scratch at 124"*, *"add a Sytrus pluck and darken it"*,
  *"make it a full song, verse chorus verse chorus bridge chorus"*.

## How it works

```text
 Claude / MCP client                      FL Studio 2026
        │  stdio (MCP)                  ┌──────────────────────────────┐
        ▼                               │ device_PatternSeeker.py      │
 mcp_server.py ──┐                      │ (MIDI controller script)     │
                 ├─► seeker/engine.py   │                              │
 pattern_seeker  │     │ generator  (music)      ▲         │           │
  .pyw (window) ─┘     │ mapping    (which channel)        │ channels, │
                       │ link ── SysEx over loopMIDI ──────┘ patterns  │
                       │ pianoroll ─► .pyscript + hands-free run in    │
                       │              the piano roll (chords, pad)     │
                                        └──────────────────────────────┘
```

Both front ends share one engine (`seeker/engine.py`): the MCP server calls it
directly, and the window runs the same calls on a worker thread so it never
freezes while FL writes the pattern.

- **The music** (`seeker/library.py`, `seeker/generator.py`): each genre is a
  vocabulary of interchangeable one/two-bar lane variants plus bar-two
  variations, velocity shaping, an 808 that either plays fixed lines or doubles
  the kick, a chord rhythm, a harmonic pace and a voicing. Progressions come from
  a shared pool of 20 per scale, and the last 8 are never repeated.
- **Channel mapping** (`seeker/mapping.py`): roles are found by channel name,
  then by plugin name ("FL Keys" means chords), then by rack order. FL names
  instrument channels after their preset, so names alone weren't enough. Channels
  it can't place (vocals, samples) are never touched.
- **The link** (`seeker/link.py`, `seeker/wire.py`): FL Studio 2026 blocks file
  I/O, `ctypes` and `subprocess` inside controller scripts, so the app and FL talk
  over MIDI SysEx through two loopMIDI ports. JSON is framed into 7-bit-safe,
  800-byte chunks. The MIDI layer is raw `winmm` via `ctypes`, with no
  dependencies.
- **Chords without clicking** (`seeker/pianoroll.py`): FL's controller API can
  only write step-sequencer steps, not piano-roll notes. Pattern Seeker generates
  a piano-roll script with the notes baked in. FL aims the piano roll at the keys
  channel and the app runs the script from the Tools menu itself. It confirms the
  edit landed through FL's refresh flags, then restores your view.
- **Safety**: the FL script checks that the rack it was planned against hasn't
  changed (`rack_changed`). It returns the previous steps so Back is exact, tiles
  drums to the pattern's length, and only replaces its own colour-9 piano-roll
  notes.

## MCP server

### Tools

| Tool               | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fl_status`      | Connection, current pattern, tempo, transport, and each channel with the role Pattern Seeker gives it                                                                                                                                                                                                                                                                                                                                                                              |
| `list_genres`    | The 22 genres and the tempo range each is idiomatic at                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `new_beat`       | `genre` (or `auto` = fits the project tempo), `key`, `scale`, toggles for `bass` / `chords` / `pad` / `guitar`, `play`, `set_tempo`, `new_pattern`, `tempo` (exact BPM, e.g. 90), `passing` (end on a passing diminished chord that leads back to the first chord), `build` (build the genre's rack first, see `build_rack`). Returns the genre, the chord progression (for example `Am(8) F(4) G(4)`), which channel got which part, and warnings |
| `write_part`     | Your own notes (a solo, a melody, a riff) on any channel: `[[pitch, start beat, length, velocity], ...]`, off-grid timing allowed                                                                                                                                                                                                                                                                                                                                                |
| `back`           | Undo the last `new_beat` or `write_part`, again and again (50 deep). After `arrange` or `new_song` it first takes the clips out of the playlist                                                                                                                                                                                                                                                                                                                            |
| `new_song`       | A whole song: a new pattern per letter of `structure` (`ABABCB` by default; A = verse, B = chorus, C = bridge), then the sections laid out in the playlist, `bars` each (8 by default). Takes the same `genre`, `key`, `scale`, `tempo`, part toggles and `build` as `new_beat`, plus `track` and `start_bar`                                                                                                                                                |
| `arrange`        | Place existing patterns in the playlist as clips, one after another on a `track`: `[{"pattern": 1, "bars": 8}, {"pattern": 2}]`. Without `start_bar` it continues where the song ends, so a song can be built section by section                                                                                                                                                                                                                                             |
| `build_rack`     | Build a genre's instruments: adds a named, coloured channel with a fitting stock sound for each part the rack lacks (`parts` limits it to `drums`, `bass`, `chords`, `pad` ...). Parts already there are kept                                                                                                                                                                                                                                                            |
| `list_sounds`    | Search what can be loaded: instruments (every plugin FL has scanned, VSTs included, your saved presets, the channel and plugin presets FL ships, and every preset of every installed FLEX pack) and samples (FL's packs plus your `sampleFolders`)                                                                                                                                                                                                                               |
| `add_channel`    | Add a new channel with an instrument or a sample in it; optional `name`, `color`, `volume`, `pan`. Name it Kick / Snare / Hat / 808 / Piano / Pad and `new_beat` writes to it                                                                                                                                                                                                                                                                                            |
| `channel_params` | A channel's color, volume, pan, and its plugin's parameters (searchable) and preset names                                                                                                                                                                                                                                                                                                                                                                                          |
| `set_channel`    | Rename, recolour, set volume and pan, load a plugin preset by name or by stepping, and set plugin parameters (`{"Decay": 0.3}`)                                                                                                                                                                                                                                                                                                                                                  |
| `write_song`     | A hand-written piece in one call: a new pattern per section with every part's notes, laid out in the playlist (`arrange=false` writes the patterns only, for repeats and gaps between movements) |
| `new_ballad`     | A whole jazz ballad written note by note (intro, A A B A + tag, 40 bars) for the jazz trio; `seed` rebuilds the same one |
| `route_channels` | Give every channel its own named, coloured mixer insert instead of the master |
| `eq`             | One channel's EQ on CFilteR-01 in its insert, in Hz / dB / Q, read back from the plugin |
| `mix_eq`         | The genre's starting EQ on every part's insert |

### Genre kits

`seeker/kits.py` says which sounds make each genre's rack. Every sound has a
style word, and the channel it is loaded into is named with it:

| Genres                             | Drums                                                                    | Bass                                            | Keys                                | Pad                             | Guitar                                     |
| ---------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------- | ----------------------------------- | ------------------------------- | ------------------------------------------ |
| Trap, drill, R&B                   | `808 Kick` ...                                                         | `808 Bass` (FLEX Core 808s)                   | `Piano` / `Rhodes`              | `Pad`                         |                                            |
| House, garage, techno, Jersey club | `909 ...`                                                              | `Synth Bass` / `808 Bass`                   | `Piano`, `Organ`, `Stab Keys` | `Pad`                         |                                            |
| Boom bap, lo-fi                    | `Dusty ...`                                                            | `Electric Bass`                               | `Rhodes`, `Piano`               | `Strings` / `Pad`           |                                            |
| Pop, disco                         | `Linn ...`                                                             | `Synth Bass` / `Electric Bass`              | `Piano`                           | `Pad` / `Strings`           |                                            |
| Afrobeats, amapiano, reggaeton     | `Afro ...`                                                             | `Electric Bass` / `Log drum` / `808 Bass` | `Rhodes`, `Piano`               | `Pad`                         |                                            |
| Drum & bass, dubstep               | `Break ...` / `Heavy ...`                                            | `Growl Bass`                                  | `Stab Keys`                       | `Pad`                         |                                            |
| Funk, classic soul                 | `Acoustic ...` (HQ Funk Kit)                                           | `Electric Bass` (flatwound for soul)          | `Rhodes`, `Organ`, `Piano`    | `Strings`                     |                                            |
| Country                            | `Acoustic ...` (HQ Funk Kit)                                           | `Electric Bass` / `Upright Bass`            | `Piano` (honky-tonk)              |                                 | `Tele Guitar` (clean, bright)            |
| Rock & roll                        | `Rock ...` (HQ Rock Kit)                                               | `Rock Bass` (picked)                          | `Piano`, `Organ`                | plays a `Pad` if there is one | `Rock Guitar` (overdriven, power chords) |
| Jazz                               | `Jazz Kick`, `Jazz Snare`, `Jazz Ride`, `Jazz Rim` (HQ Jazz Kit) | `Upright Bass`                                | `Rhodes`, `Piano`               |                                 |                                            |
| Classical                          | none                                                                     | `Cello`                                       | `Piano` (grand), `Harpsichord`  | `Strings`                     |                                            |

**A genre only plays channels that suit it.** For each part, a beat picks a
channel whose style the genre accepts (`Rock Kick` for rock), then a plainly
named one (`Kick`, `Bass` suit every genre). Without `build`, a channel of
another style may stand in, except machines and synths under an acoustic genre:
classical, jazz, country, rock and soul never play an 808, a 909 or a synth pad.
With `build`, only the genre's own sounds count, and what is missing is added.
The drums and basses of other kits are silenced in the pattern being written,
and so are the keys, pads and guitars Pattern Seeker wrote there before, so one
rack can hold several kits side by side.

Sounds come from what FL Studio ships (stock samples, the HQ drum kits, 3x Osc
and FL Keys presets, FLEX's General MIDI library) and from the free FLEX packs
when they are installed (Essential / Core strings, bass guitars, guitars,
pianos). Options are listed best first and the missing ones are skipped. They
were chosen from their names, not by ear, so edit the lists to taste: any id
that `list_sounds` prints can go in. No stock preset is a Telecaster; `Tele Guitar` is the nearest clean, bright electric.

Each of the acoustic genres also has its own way of playing: jazz walks the bass
in quarter notes under a ride pattern and comped ninth chords; country plays
boom-chick (root, then the fifth below) with a train snare and a picked guitar;
rock & roll drives eighths or a boogie line on the bass under power chords;
soul has the Motown snare on all four and a tambourine; classical has no drums
and breaks its chords into Alberti figures and arpeggios.

**Bass register.** An 808 or a synth bass is written around FL's C5, the note at
which a sample plays untransposed. A channel named for a string bass (`Upright Bass`, `Electric Bass`, `Rock Bass`) is written two octaves lower, and its notes
are kept between the open low E and FL's C4, where a real bass line sits. The
ranges are `BASS_RANGE` in `seeker/kits.py`.

**Swing.** FL's step sequencer is a 16th-note grid with no triplets. Jazz and the
rock & roll shuffle are written the way a drum machine plays them, with the
swung eighth on the last 16th of the beat. That is a harder shuffle than a real
triplet swing.

### Songs: patterns into the playlist

`new_song` makes one pattern per section and gives each its own groove and chord
progression. The sections differ in what plays: the verse has no pad, the
chorus has every part, and the bridge is a breakdown without drums. A repeated
letter reuses its pattern, so both verses are the same. Patterns are named and
coloured by section ("Verse - Seek Trap B2B5"), which makes the playlist readable.

FL's scripting API has no call that places a clip in the playlist, so the clips
are clicked in with the mouse (`seeker/playlist.py`). FL's hint bar, read back
by the controller script, is what makes that reliable:

- Over the grid the hint shows the time under the mouse (`6:04:90`). Two hovers
  give the zoom and the scroll position, whatever the window layout is.
- Over a track's header it shows the track's name, which finds the row.
- After a click with the draw tool it shows where the clip landed (`12:01:00 for 4:00:00`). Every clip is checked against that, and undone if it is wrong.

A clip only lands exactly on a bar when the playlist's own snap (the magnet in
its toolbar) is set to Bar. That setting is not in the scripting API, so it is
set through the magnet menu for the duration and put back afterwards. Bars and
tracks that are off screen are scrolled to with the mouse wheel. A channel rack,
mixer or piano roll lying over the spot is hidden and shown again afterwards.

Limits:

- The playlist must be open, and FL comes to the front while the mouse works
  (about a second per clip). Don't move the mouse meanwhile.
- It does not see clips that are already on a track. Give it a free track, or
  let it continue at the end of the song (the default).
- `back` removes the clips through FL's own undo, one step per clip, so it
  should follow straight after. Patterns can't be deleted from here.
- The menu positions were measured in FL Studio 2026 with the default theme.

### Hand-written pieces

`examples/` holds whole pieces written note by note, as models for generators:
`jazz_ballad.py` (the source of `new_ballad`), `sinfonietta.py` and
`divertimento.py` (three-movement Classical-era pieces for chamber orchestra).
Each one composes, checks every part's range and bar lengths, and writes
through the engine while the MCP server runs (the Divertimento has about
10,000 notes, too many for one MCP call): `python examples/divertimento.py` prints the plan, `build`
or `add_channel` makes the channels, `write` writes and lays it out, and
`rewrite` puts new notes into the same patterns without touching the
playlist.

Dynamics are velocity, and FLEX turns velocity straight into loudness, so the
Divertimento keeps pp to ff within velocity 54-88. Changes are smoothed into
two-bar crescendos and diminuendos, and ff is kept for each movement's climax
and coda. `divertimento_eq.py` works its EQ out from the score: low cuts
under each part's lowest note in any movement, and small cuts, at most two
per part, on whichever part is accompanying where two parts share a
frequency at the same time. `sinfonietta_eq.py` does the same for the
Sinfonietta: each low cut sits at 0.65 x the part's lowest note in any movement
(under 1 dB lost there), contrabass and timpani only lose subsonic rumble, and
the pocket cuts (cello vs bassoon and horns, violas vs inner winds, violins II
vs oboe and violin I) all stay under 4 kHz. Both print their plan, and `apply`
sets it.

### Building the rack

FL's scripting API has no call that adds a channel or loads a plugin. Pattern
Seeker starts FL's own program with a preset file (`.fst`) as its argument: the
FL Studio that is already running takes the file and opens it in a new channel.
FL keeps one `.fst` per scanned plugin in its plugin database, so every
generator it knows can be loaded this way. So can the channel presets and the
plugin presets FL ships (about 5,500 of them: `Plugin presets/Sytrus/...`,
`Plugin presets/FL Keys/ePiano`), which open with the preset already loaded.
FLEX presets are not files, but FLEX saves its state as a fixed block that names
the pack and the preset, so a preset file for any of them is written on the
spot (`FLEX/Essential Strings/Cellos Staccato`); the pack lists come from the
directory at the top of each `.flexpack`. A bare audio file is ignored, so for
a sample a small sampler preset that names the file is written first
(`seeker/sounds.py`). Once the channel exists, the controller script names it,
sets its colour, level and pan, and reads and sets the plugin's parameters and
presets.

Limits:

- A channel can't be removed from here. Delete it in FL.
- FL comes to the front while it loads a channel (about one to three seconds each).
- FL has no call for which preset a plugin has loaded. Loading a preset by name
  works for plugins that show the preset's name in FL's hint bar after a step
  (FLEX does). For the others (FL Keys), step with `preset=1`, or add a new
  channel from the preset's file.
- An effect can't be loaded into a mixer insert from here (FL always opens it
  on the master). Channels are routed to their own inserts (`route_channels`),
  and CFilteR-01 is set (`eq`, `mix_eq`) where a template already has it.

Add your own sample folders in
`%LOCALAPPDATA%\PatternSeeker\settings.json`: `"sampleFolders": ["D:\\Samples"]`.

### Setup

1. Python 3.10+ and `pip install -r requirements.txt` (only the MCP server needs it; the window has no dependencies).
2. [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) with two
   ports, `Pattern Seeker In` and `Pattern Seeker Out`.
3. Start the server or the app once. It installs the controller script into
   `Documents\Image-Line\FL Studio\Settings\Hardware\Pattern Seeker`.
4. In FL Studio, open Options › MIDI settings. Set input `Pattern Seeker In` to
   Controller type **Pattern Seeker**, enable it, and give it a port number.
   Give output `Pattern Seeker Out` the **same** port number.
5. Register the server with your MCP client:

   ```bash
   # Claude Code
   claude mcp add pattern-seeker --scope user -- python C:/path/to/pattern-seeker/mcp_server.py
   ```

   For Claude Desktop, add this to `claude_desktop_config.json`:

   ```json
   { "mcpServers": { "pattern-seeker": {
       "command": "python", "args": ["C:/path/to/pattern-seeker/mcp_server.py"] } } }
   ```
6. Restart the MCP client and ask for a beat, for example *"make me a boom bap
   beat in D minor"*.

Start loopMIDI before FL Studio: FL looks for MIDI ports when it launches. With
the classic Windows MIDI driver only one program can hold the MIDI ports at a
time, so close the Pattern Seeker window while an MCP client is using the
server. Under the newer Windows MIDI Service (Windows 11) they could be shared:
the example scripts ran beside a running MCP server on the author's PC.

### Using the desktop window instead

```bash
pythonw pattern_seeker.pyw
```

The top of the window says what to write: genre, key and scale, an exact tempo
(empty keeps FL's), which parts play (drums, bass, chords, pad, guitar), a
passing chord at the end, and **Build rack** to add the genre's instruments
first. The tabs say where it goes:

- **Beat**: **NEW BEAT** (or Space, or Ctrl+Alt+B from anywhere) writes a groove
  on the current pattern, or on a new one.
- **Song**: **NEW SONG** writes a pattern per letter of the structure (`ABABCB`)
  and lays them out on a playlist track. **Jazz ballad** writes the 40-bar
  ballad (type a seed to get the same one again). **Add pattern to song**
  places the pattern selected in FL at the song's end.
- **Rack**: every channel with its part and mixer insert. **Build kit** adds
  the genre's sounds, **Route to mixer** gives each channel its own insert,
  **EQ the mix** sets the genre's starting EQ on CFilteR-01. Search for a sound
  to add it as a channel, or rename a channel so a genre picks it up.

**◀ Back** undoes the last beat, or takes a song's clips out of the playlist.
The window uses the same MIDI setup (steps 2-4). Writing single notes
(`write_part`), per-band EQ and plugin parameters stay with the MCP tools.

## Tests

```bash
python -m unittest discover tests
```

101 tests. They cover the music rules (every 808 note in key, chords voiced close,
progressions that keep changing). They also load the **real FL controller
script** against a simulated channel rack and drive it through the real SysEx
encoder, for both the app's requests and the MCP engine (new beat, then Back
restores the user's own steps), and for building: adding channels, genre kits,
presets and parameters, and which channels a genre plays. Songs are tested
against a simulated playlist window that answers hovers and clicks the way FL
does (snap menu, scrolling, a channel rack in the way), and so are the jazz
ballad (480 generated ballads checked for clashes and lengths), `write_song`,
mixer routing and the EQ read-back (including a plugin that reports a value it
didn't take). The desktop window's text for beats, songs, ballads and the rack
is checked on real engine results. One test starts the MCP server over stdio,
does the protocol handshake and calls a tool.

## Platform

Windows (the MIDI and window automation use Win32 APIs), with FL Studio 2026.
