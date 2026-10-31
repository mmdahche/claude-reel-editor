# Music beds (you supply them)

This kit ships **no music**. Free music licences (Mixkit, Pixabay Music and similar) allow using a
track inside your video but not redistributing the file, so each editor downloads their own.

## What to get
5-8 instrumental beds, 60-90 s each, in two or three moods your clients use (for example: calm,
warm and optimistic, focused). No vocals, no big drops, nothing that fights a speaking voice.
The audio pass loops a short bed, starts it at 0:00 with a 0.5 s fade-in, ducks it about 7-8 dB
under speech, and fades it over the last 1.5 s. Default level in the gaps: -19 LUFS (`--bed-lufs`).

Listen on a phone speaker before you keep a bed: crackles on bass hits and harsh highs show up there.

## Where to look
Mixkit Music first, Pixabay Music as a backup. Not free tiers that exclude business use. For paid
libraries, confirm in writing that client work on social platforms is covered before using them.

## A licence does not stop muting
Instagram and TikTok fingerprint music in uploads, quiet beds included. A licence only helps an
appeal. That is why every render also writes a `-nomusic` export: if a reel is muted, re-upload
the `-nomusic` file and add a track from the platform's own library in the app.

## Licence rows (no row, no bed in a posted video)
Keep `assets/music/LICENSES.md` (git-ignored by default, like the music files) with one row per track:

| id | file | title | artist | source | source URL | licence name | licence URL | attribution needed | commercial social use | downloaded | verified | proof | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MUS-0001 | assets/music/<file> | <title> | <artist> | <site> | <track page URL> | <licence name> | <licence URL> | no | yes | <date> | <date> | <screenshot file of the licence page> | <mood, length, phone listen result> |

Reject any track whose row needs attribution, whose licence has NC, ND or SA terms, or whose
commercial-social-media use is not a clear yes. Log the bed's id in the video's LOG.md every time.
