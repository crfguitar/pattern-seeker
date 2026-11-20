# Pattern Seeker

This repo is an MCP server (`mcp_server.py`) and desktop window (`pattern_seeker.pyw`)
that write genre-true beats into FL Studio. Both run on `seeker/engine.py`.

## Making beats in FL Studio

When the user asks for a beat, a groove, drums, an 808, chords or a pad in FL Studio,
use the **pattern-seeker** MCP tools. Don't write MIDI files or scripts by hand.

- Request a beat → call `new_beat` straight away. Map their words to its arguments:

  - `genre`: a name from `list_genres`. Use `auto` if they don't name one. Common
    other names work too: "rock n roll", "motown", "swing", "orchestral".
  - `key`, `scale` (`minor` / `major`).
  - `bass`, `chords`, `pad`, `guitar`: turn a part off when they ask, e.g. "no pad" →
    `pad=false`. Only rock and country have a guitar part.
  - `tempo`: the exact BPM when they name one, e.g. "90 bpm" → `tempo=90`.
  - `passing`: `true` when they ask for a passing / diminished chord at the end.

  Use `set_tempo=true` only when they want a tempo that suits the genre but give no
  number. Leave `new_pattern` off unless they ask for a new pattern.
- "Another one", "again", "different" → call `new_beat` again with the same arguments.
  Every call gives a different groove and progression.
- "Go back", "undo", "I liked the last one" → call `back`.
- Questions about the project (tempo, which channel is what) → call `fl_status`.

## Building the rack

Pattern Seeker can add channels and load sounds, so the user needs no template.

- "Make me a trap song from scratch", "set up a house track", "build the
  instruments", or a beat request when `fl_status` shows an empty rack → call
  `new_beat` with `build=true` and a genre. It adds a channel for each part the
  rack lacks (kick, snare, clap, hat, open hat, perc, bass, keys, pad), then
  writes the beat. `build_rack` does the building alone; `parts` limits it,
  e.g. `["drums"]`.
- A beat request on a rack that has some parts → plain `new_beat`. If it returns
  parts under `noChannelFor`, say so and offer to add them. Don't add channels
  the user didn't ask for: they can't be removed from here.
- A genre only plays channels whose sound suits it. Channels are told apart by
  the style word in their name: `Rock Kick`, `Jazz Ride`, `Cello`, `808 Bass`,
  `Strings`. Plain names (`Kick`, `Bass`) suit every genre. Classical, jazz,
  country, rock and soul never play an 808, a drum machine or a synth pad, so
  on a trap rack they come back with most parts under `noChannelFor`: that is
  the cue to offer `build=true`, which adds the genre's own kit beside the
  others. When the user says a part sounds wrong for the genre ("there's an
  808 in my classical"), rename the channel to say what it is with
  `set_channel`, or build the right one.
- A specific sound ("add a Sytrus pluck", "a different kick") → `list_sounds`
  to find it, then `add_channel`. Name the channel Kick, Snare, Clap, Hat,
  Open hat, Perc, 808, Bass, Piano, Keys or Pad when `new_beat` should write to
  it, with the style word in front when it belongs to one kind of music
  ("Rock Kick", "Tele Guitar").
- "Make the pad darker", "more release", "try another preset" →
  `channel_params` for the parameter and preset names, then `set_channel`.
  Parameters run from 0 to 1. Loading a preset by name works on FLEX; on
  plugins where it fails, step with `preset=1`.

After building, list the channels added and the sound in each, and relay any
`problems`. The kit sounds were chosen from their names, not by ear, so invite
the user to swap any they don't like.

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
- After changing `fl_script/`, bump `SCRIPT_VERSION`, then reload it in FL: View >
  Script output > Pattern Seeker In tab > Reload script.
- Genre kits and channel styles live in `seeker/kits.py`; which channel plays which
  part is `mapping.fit_rack`; loading sounds into FL is `seeker/sounds.py`.
- FL controller scripts (`fl_script/`) can't use file I/O, `ctypes` or `subprocess`.
  Everything crosses as SysEx (`seeker/wire.py`).
