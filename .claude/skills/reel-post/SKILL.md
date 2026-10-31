---
name: reel-post
description: Write the hand-off for a finished reel. POST.md holds one caption that works on Instagram Reels, TikTok and YouTube Shorts, the hook line, up to 5 hashtags, the client's comment keyword and its offer, the Shorts title, which export to upload and the cover frame. The LOG.md entry records paid spend (normally none), captures, SFX and music licence rows, loudness and QA results, each review round and the hook for the learning loop. Use it when a final is approved or nearly ready, or when the editor says "caption", "post text", "hashtags", "what do I write", "make the cover", "log it" or "ready to post". Never posts or schedules on the client's behalf.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# reel-post

The client's job is to watch, approve and post. This skill makes sure everything they paste is
ready, and that each video feeds the learning loop. Nobody in this workflow posts, schedules or
replies on the client's behalf: the client (or the editor, if the client says so) uploads.

## When to use
- `$V/final/<slug>-vN.mp4` exists and has passed `reel-audio-gate` and `reel-safezone-qa`.
- The editor asks for the caption, hashtags, or a new cover frame.
- After posting: fill in the post links and, later, the numbers in LOG.md.

## When NOT to use
- Scripting, beats or hook structure: `reel-shotlist`, `reel-hook-check`.
- Posting or scheduling. Not this kit's job.

## Inputs
- `V=videos/<client>/<slug>`: `SCRIPT.md`, `SHOTLIST.md`, `final/` (both exports, the SRT),
  `audio/`, `review/qa/RESULT.md`.
- `clients/<client>/BRAND.md`: tone, words to avoid, hashtag habits, the comment keyword and what
  it delivers, the safe CTA wording, the handle.
- The `cta` beat's inputs in `$V/input/shotlist.json` (the on-screen keyword must match exactly).

## Steps
1. **Hook line.** The spoken hook, tightened for reading. It must make sense with the sound off.
2. **One caption for all three apps.** First line = the hook, inside about 125 characters
   (Instagram cuts there with "more"; the first line also sits over the face area). Then 2-4 short
   payoff lines, then the client's CTA with the exact on-screen keyword. Keep it well under 2,200
   characters. Use the client's tone and reading level from BRAND.md.
3. **Hashtags.** 3-5 specific tags (Instagram reportedly caps posts at 5; third-party report, not an
   official rule). Topic and tool tags over generic ones; nothing banned or spammy.
4. **Shorts title.** The hook line, under 100 characters. Custom Shorts thumbnails need the YouTube
   Partner Program and a computer, so do not promise one.
5. **Which export.** Default: the with-music file. Trending sound wanted: upload `-nomusic.mp4` and
   add the sound in-app. If a platform mutes or flags the reel, re-upload `-nomusic.mp4` and add a
   track from the platform's own licensed library. A music licence does not stop automatic muting.
6. **Cover.** The frame where the hook title has fully landed (usually about 1 s in), bright and
   inviting:
   `ffmpeg -v error -y -ss <t> -i $V/final/<slug>-vN.mp4 -frames:v 1 -q:v 2 $V/final/cover.jpg`
   Title inside y 285-1440, x 80-1000 (check with `reel-safezone-qa` step 6).
7. **Write `$V/POST.md`** (copy an existing one to `.bak-<date>/` first):
   ```
   # <slug> vN - post
   Upload: final/<slug>-vN.mp4   (or -nomusic + trending sound: <name>)
   Cover: final/cover.jpg (frame at <t>s)
   Keyword: <KEYWORD> -> <what it delivers>
   ## Caption (Reels, TikTok, Shorts description)
   <hook line>
   <payoff lines>
   <CTA with the keyword>
   #tag1 #tag2 #tag3
   ## Shorts title
   <under 100 characters>
   ```
8. **Add to `$V/LOG.md`** (a dated entry; never overwrite older ones): version and date; runtime;
   paid spend (normally none) and paid shots; captures used; SFX source rows; music track and its
   licence row, or "none"; loudness I and true peak for both exports; QA result; thread, hook line,
   lock-in method, target emotion; the caption and keyword. Each review round: the editor's notes,
   one change per line with its time ("At 0:07 the logo covers the face"), mapped to a beat id, and
   the version that answered them. Leave blanks for post links, posting time, 24-hour and 7-day
   views, watch time, keyword comments and DMs, so the next script can learn from it.

## What to tell the editor (plain English)
"It's ready to post. Upload the main video, use the cover, and paste the caption from POST.md." Add
the hook line, the keyword, and one sentence if the no-music version suits this one better.

## Checklist
- [ ] First caption line is the hook, about 125 characters or less; the CTA keyword matches the
      on-screen keyword exactly.
- [ ] 5 hashtags or fewer; total well under 2,200 characters; Shorts title under 100.
- [ ] Cover pulled, bright, title inside y 285-1440 and x 80-1000.
- [ ] POST.md written (old one backed up). LOG.md entry added with licences, loudness, QA, the
      review rounds and blanks for results.
- [ ] Nothing was posted or scheduled.
