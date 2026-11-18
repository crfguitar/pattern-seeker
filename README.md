# Pattern Seeker


https://github.com/user-attachments/assets/a4e42051-d261-47b2-9309-70b2c10e83f5


**Genre-true beats in FL Studio, from one button or from an AI assistant.**

Pattern Seeker writes a complete starting point into FL Studio's current pattern:
drums (kick, snare, clap, hats, percussion), an 808 line in key, a four-bar chord
progression on the keys channel and a soft pad on the synth channel. Every press
gives a different groove and progression, always inside the style of the chosen
genre (17 genres: trap, boom bap, house, drill, lo-fi, garage, ...). One step of
**Back** restores exactly what the pattern held before.

There are two ways to drive it:

- **The Pattern Seeker window** (`pattern_seeker.pyw`): an always-on-top window
  with NEW BEAT, a global hotkey (Ctrl+Alt+B), and genre/key/scale pickers.
- **The Pattern Seeker MCP server** (`mcp_server.py`): the same engine exposed
  over the [Model Context Protocol](https://modelcontextprotocol.io), so Claude
  (or any MCP client) can make beats from a plain request: *"give me a lo-fi beat
  in A minor, no pad"*, *"another one"*, *"go back, I liked the last one"*.

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
| `list_genres` | The 17 genres and the tempo range each is idiomatic at |
| `new_beat` | `genre` (or `auto` = fits the project tempo), `key`, `scale`, toggles for `bass` / `chords` / `pad`, `play`, `set_tempo`, `new_pattern`. Returns the genre, the chord progression (for example `Am(8) F(4) G(4)`), which channel got which part, and warnings |
| `back` | Undo the last `new_beat`, again and again (50 deep) |

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

34 tests. They cover the music rules (every 808 note in key, chords voiced close,
progressions that keep changing). They also load the **real FL controller
script** against a simulated channel rack and drive it through the real SysEx
encoder, for both the app's requests and the MCP engine (new beat, then Back
restores the user's own steps). One test starts the MCP server over stdio, does
the protocol handshake and calls a tool.

## Platform

Windows (the MIDI and window automation use Win32 APIs), with FL Studio 2026.
