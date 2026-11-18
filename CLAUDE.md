# Pattern Seeker

This repo is an MCP server (`mcp_server.py`) and desktop window (`pattern_seeker.pyw`)
that write genre-true beats into FL Studio. Both run on `seeker/engine.py`.

## Making beats in FL Studio

When the user asks for a beat, a groove, drums, an 808, chords or a pad in FL Studio,
use the **pattern-seeker** MCP tools. Don't write MIDI files or scripts by hand.

- Request a beat → call `new_beat` straight away. Map their words to its arguments:

  - `genre`: a name from `list_genres`. Use `auto` if they don't name one.
  - `key`, `scale` (`minor` / `major`).
  - `bass`, `chords`, `pad`: turn a part off when they ask, e.g. "no pad" → `pad=false`.
  - `tempo`: the exact BPM when they name one, e.g. "90 bpm" → `tempo=90`.
  - `passing`: `true` when they ask for a passing / diminished chord at the end.

  Use `set_tempo=true` only when they want a tempo that suits the genre but give no
  number. Leave `new_pattern` off unless they ask for a new pattern.
- "Another one", "again", "different" → call `new_beat` again with the same arguments.
  Every call gives a different groove and progression.
- "Go back", "undo", "I liked the last one" → call `back`.
- Questions about the project (tempo, which channel is what) → call `fl_status`.

After each beat, reply in one or two lines: the genre, the key, the chord progression,
and which channel got which part. Mention any warnings the tool returned.

If a tool returns `ok: false`, relay its error. It says what to fix, usually the FL
MIDI settings, or that the Pattern Seeker window is open and holding the ports.

## Working on the code

- Tests: `python -m unittest discover tests`. They run the real FL controller script
  against a simulated rack.
- `mcp_server.py` talks MCP over stdout, so nothing may print to stdout. Log to stderr.
- Only one process can open the loopMIDI ports. Close the window before testing the
  server, and the other way round.
- FL controller scripts (`fl_script/`) can't use file I/O, `ctypes` or `subprocess`.
  Everything crosses as SysEx (`seeker/wire.py`).
