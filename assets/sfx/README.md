# Sound effects (you supply them)

This kit ships **no sound files**. The free libraries these sounds usually come from (for example
the Pixabay Content License and the Mixkit free licences) let you use the sounds inside your videos,
but not hand out the files themselves as a pack. So each editor downloads their own.

## What to get (five files, short and quiet)
The audio pass looks for these exact names in this folder (`.wav`, `.mp3`, `.m4a`, `.aiff` or `.ogg`):

| File | Fires on | What it should sound like |
|---|---|---|
| `whoosh.*` | a card, tile, plate or frame dropping in | a soft air whoosh, under 0.6 s, no "cartoon" swoosh |
| `tick.*` | table rows, steps landing, a button press | a dry, quiet click or tick |
| `pop.*` | a stat landing, a check mark, a chat bubble | a small soft pop |
| `thud.*` | a stamp, a "VS" seal, a word slam | a low, short impact; trimmed to 0.6 s |
| `keys.*` | text typing in (comment box, log lines) | light keyboard typing |

Optional: `<cue>.json` beside a file with `{"in": 0.4}` skips the first 0.4 s of a file that starts
slowly (a typing clip, for example).

The pass trims each cue to 0.6 s or less, fades it, and sets its level from its own measured
loudness so it lands 6-10 dB under the voice. Never on caption changes. Quiet and tactile beats
showy: if a sound would make someone look up from their phone, it is too much.

A missing file is not an error: that cue type is skipped and the render log says which. The client
still gets a finished video, just without that sound.

## Where to look
Pixabay Sound Effects, Mixkit Sound Effects, Kenney (CC0), Freesound (filter to CC0 only). Avoid
anything that needs on-screen attribution, or whose licence has NC (non-commercial), ND or SA terms.
Read the licence page on the day you download; licences change.

## Licence rows (no row, no file)
Keep `assets/sfx/LICENSES.md` (git-ignored by default, like the sound files) with one row per file:

| id | file | kind | title | author | source | source URL | licence name | licence URL | attribution needed | commercial social use | downloaded | verified | proof | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SFX-0001 | assets/sfx/whoosh.wav | whoosh | <title> | <author> | <site> | <page URL> | <licence name> | <licence URL> | no | yes | <date> | <date> | <screenshot file of the licence page> | <trim notes> |

Reject any file whose row needs attribution, whose licence has NC, ND or SA terms, or whose
commercial-social-media use is not a clear yes.
