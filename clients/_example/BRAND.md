# BRAND: <client name>

<!--
This is an EMPTY template. Do not fill it in by hand unless you want to: paste DESIGN-INTERVIEW.md
into your Claude Code agent and it will ask you (or your client) one question at a time and write
this file and brand.json for you.

Copy the whole folder first:   cp -R clients/_example clients/<client-name>
Every skill reads this file before it works on one of this client's videos. Write in plain words.
Anything left as "<...>" means "not decided yet": the agent will ask before guessing.
-->

## Who and what
- Client / show name: <...>
- Handle(s): <...>
- What they do, in one sentence: <...>
- Who watches: <...>
- Platforms: <Instagram Reels / TikTok / YouTube Shorts: one export for all, or which ones>

## Tone
- How they talk: <e.g. short words, warm, direct; reading level>
- Words and topics to avoid: <...>
- The emotion most videos should leave: <...>

## Look (the values live in brand.json "tokens"; this section says WHY)
- Overall feel in a few words: <...>
- Stage (background) colour and mood: <...>
- Accent colour and how much of it (keep accents to about a tenth of the frame): <...>
- Text colour on the stage: <...>
- "Good" colour (money saved, checks) and "stakes" colour (warnings, losses): <...>
- Light plate colour (behind phone mockups and quotes): <...>
- Corners: <sharp / soft / round>
- Footage grade: <none, or the feel: warm, cool, neutral; how strong>
- References they like (links or names), and what to take from each: <...>

## Fonts
- Headline / caption font (sans): <family, weight, where the files come from, licence>
- Label / kicker font (mono): <...>
- Accent font for one word per title (serif italic, optional): <...>
- Licence check: <each font's licence allows embedding in video: yes/no, with the licence file kept
  in clients/<client-name>/fonts/>

## Captions
- Style: <big words one at a time (bigword) / a short pill of 2-4 words (pill)>
- Caption colour and size feel: <...>
- (Fixed for every client, not a brand choice: captions sit on one line at y 1280, inside x 150-930.)

## Layout
- Real footage: <split (footage on top, face below) / card (footage in a card on the stage) /
  decide per beat with the default rule: split for the first reveal and anything the viewer must
  read, card when the graphic carries the point>
- Face: <in the rounded face box / cut out and standing free on the stage (macOS only)>
- Speed: <whole take at 1.08x (default) / natural speed>
- Runtime target: <e.g. 40-55 s; single tip 35 s or less; never over 60 s>
- Scenes they like or never want: <...>

## Logo and marks
- Logo file(s): <clients/<client-name>/logo.png ...> (shown unaltered: no recolour, no glow)
- Where the logo may appear: <CTA footer only / never / ...> (never as a watermark unless asked)
- Other people's logos (tools, partners): official files only, unaltered, name as plain text beside it

## Call to action
- Comment keyword: <KEYWORD> and what it delivers: <...>
- Safe CTA wording (what they are happy to say every time): <...>
- Footer line under the CTA (optional, short): <...>
- Videos that end without a keyword CTA: <allowed? which kind?>

## Sound
- Sound effects: <on (quiet, tactile) / off>
- Music bed mood: <...> (every bed needs a licence row in assets/music/LICENSES.md)
- Voice: <bright enough already (voice EQ off) / needs the presence lift (voice EQ on, default)>

## Rules this client changed
<Any default from WORKFLOW.md this client asked to drop or change, with the date they said so.>

## Names to spell right
Put every brand, product and person name the transcriber may mishear in `terms.txt` next to this
file, one per line.
