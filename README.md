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

There are two ways to drive it:

- **The Pattern Seeker window** (`pattern_seeker.pyw`): an always-on-top window
  with NEW BEAT, a global hotkey (Ctrl+Alt+B), and genre/key/scale pickers.
- **The Pattern Seeker MCP server** (`mcp_server.py`): the same engine exposed
  over the [Model Context Protocol](https://modelcontextprotocol.io), so Claude
  (or any MCP client) can make beats from a plain request: *"give me a lo-fi beat
  in A minor, no pad"*, *"another one"*, *"go back, I liked the last one"*,
  *"set up a house track from scratch at 124"*, *"add a Sytrus pluck and darken it"*.

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

| Tool | What it does |
| --- | --- |
| `fl_status` | Connection, current pattern, tempo, transport, and each channel with the role Pattern Seeker gives it |
| `list_genres` | The 22 genres and the tempo range each is idiomatic at |
| `new_beat` | `genre` (or `auto` = fits the project tempo), `key`, `scale`, toggles for `bass` / `chords` / `pad` / `guitar`, `play`, `set_tempo`, `new_pattern`, `tempo` (exact BPM, e.g. 90), `passing` (end on a passing diminished chord that leads back to the first chord), `build` (build the genre's rack first, see `build_rack`). Returns the genre, the chord progression (for example `Am(8) F(4) G(4)`), which channel got which part, and warnings |
| `write_part` | Your own notes (a solo, a melody, a riff) on any channel: `[[pitch, start beat, length, velocity], ...]`, off-grid timing allowed |
| `back` | Undo the last `new_beat` or `write_part`, again and again (50 deep) |
| `build_rack` | Build a genre's instruments: adds a named, coloured channel with a fitting stock sound for each part the rack lacks (`parts` limits it to `drums`, `bass`, `chords`, `pad` ...). Parts already there are kept |
| `list_sounds` | Search what can be loaded: instruments (every plugin FL has scanned, VSTs included, your saved presets, the channel and plugin presets FL ships, and every preset of every installed FLEX pack) and samples (FL's packs plus your `sampleFolders`) |
| `add_channel` | Add a new channel with an instrument or a sample in it; optional `name`, `color`, `volume`, `pan`. Name it Kick / Snare / Hat / 808 / Piano / Pad and `new_beat` writes to it |
| `channel_params` | A channel's color, volume, pan, and its plugin's parameters (searchable) and preset names |
| `set_channel` | Rename, recolour, set volume and pan, load a plugin preset by name or by stepping, and set plugin parameters (`{"Decay": 0.3}`) |

### Genre kits

`seeker/kits.py` says which sounds make each genre's rack. Every sound has a
style word, and the channel it is loaded into is named with it:

| Genres | Drums | Bass | Keys | Pad | Guitar |
| --- | --- | --- | --- | --- | --- |
| Trap, drill, R&B | `808 Kick` ... | `808 Bass` (FLEX Core 808s) | `Piano` / `Rhodes` | `Pad` | |
| House, garage, techno, Jersey club | `909 ...` | `Synth Bass` / `808 Bass` | `Piano`, `Organ`, `Stab Keys` | `Pad` | |
| Boom bap, lo-fi | `Dusty ...` | `Electric Bass` | `Rhodes`, `Piano` | `Strings` / `Pad` | |
| Pop, disco | `Linn ...` | `Synth Bass` / `Electric Bass` | `Piano` | `Pad` / `Strings` | |
| Afrobeats, amapiano, reggaeton | `Afro ...` | `Electric Bass` / `Log drum` / `808 Bass` | `Rhodes`, `Piano` | `Pad` | |
| Drum & bass, dubstep | `Break ...` / `Heavy ...` | `Growl Bass` | `Stab Keys` | `Pad` | |
| Funk, classic soul | `Acoustic ...` (HQ Funk Kit) | `Electric Bass` (flatwound for soul) | `Rhodes`, `Organ`, `Piano` | `Strings` | |
| Country | `Acoustic ...` (HQ Funk Kit) | `Electric Bass` / `Upright Bass` | `Piano` (honky-tonk) | | `Tele Guitar` (clean, bright) |
| Rock & roll | `Rock ...` (HQ Rock Kit) | `Rock Bass` (picked) | `Piano`, `Organ` | plays a `Pad` if there is one | `Rock Guitar` (overdriven, power chords) |
| Jazz | `Jazz Kick`, `Jazz Snare`, `Jazz Ride`, `Jazz Rim` (HQ Jazz Kit) | `Upright Bass` | `Rhodes`, `Piano` | | |
| Classical | none | `Cello` | `Piano` (grand), `Harpsichord` | `Strings` | |

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
that `list_sounds` prints can go in. No stock preset is a Telecaster; `Tele
Guitar` is the nearest clean, bright electric.

Each of the acoustic genres also has its own way of playing: jazz walks the bass
in quarter notes under a ride pattern and comped ninth chords; country plays
boom-chick (root, then the fifth below) with a train snare and a picked guitar;
rock & roll drives eighths or a boogie line on the bass under power chords;
soul has the Motown snare on all four and a tambourine; classical has no drums
and breaks its chords into Alberti figures and arpeggios.

**Bass register.** An 808 or a synth bass is written around FL's C5, the note at
which a sample plays untransposed. A channel named for a string bass (`Upright
Bass`, `Electric Bass`, `Rock Bass`) is written two octaves lower, and its notes
are kept between the open low E and FL's C4, where a real bass line sits. The
ranges are `BASS_RANGE` in `seeker/kits.py`.

**Swing.** FL's step sequencer is a 16th-note grid with no triplets. Jazz and the
rock & roll shuffle are written the way a drum machine plays them, with the
swung eighth on the last 16th of the beat. That is a harder shuffle than a real
triplet swing.

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
- Effects and mixer routing are not covered.

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

Start loopMIDI before FL Studio: FL looks for MIDI ports when it launches. Only
one program can hold the MIDI ports at a time, so close the Pattern Seeker
window while an MCP client is using the server.

### Using the desktop window instead

```bash
pythonw pattern_seeker.pyw
```

Pick a genre, key and scale, then press **NEW BEAT** (or Space, or Ctrl+Alt+B
from anywhere). **◀ Back** undoes. The window uses the same MIDI setup (steps 2-4).

## Tests

```bash
python -m unittest discover tests
```

65 tests. They cover the music rules (every 808 note in key, chords voiced close,
progressions that keep changing). They also load the **real FL controller
script** against a simulated channel rack and drive it through the real SysEx
encoder, for both the app's requests and the MCP engine (new beat, then Back
restores the user's own steps), and for building: adding channels, genre kits,
presets and parameters, and which channels a genre plays. One test starts the MCP server over stdio, does
the protocol handshake and calls a tool.

## Platform

Windows (the MIDI and window automation use Win32 APIs), with FL Studio 2026.
