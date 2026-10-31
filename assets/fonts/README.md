# Fonts

The kit ships **no fonts** and no default look. Each client's fonts live in that client's own
folder, `clients/<client-name>/fonts/`, and are named in its `brand.json` ("fonts"). The build
writes the `@font-face` rules from there, so renders never need the internet.

How to add a client's font:
1. Get the font from its official source (the foundry, or the font's own repository).
2. Check its licence allows embedding in video and commercial use. Open-source fonts under the SIL
   Open Font License (OFL) do; many commercial fonts need a specific licence for video.
3. Copy the font files AND the full licence text (for OFL fonts, the `OFL.txt` from the font's own
   repository) into `clients/<client-name>/fonts/`.
4. Name them in `brand.json`, for example:
   `"sans": {"family": "Client Sans", "fallback": "sans-serif", "files": [{"src": "clients/<client-name>/fonts/ClientSans.ttf", "weight": "100 900"}]}`

The interview (`DESIGN-INTERVIEW.md`) asks about fonts and writes this for you.
