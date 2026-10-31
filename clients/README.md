# Clients

One folder per client. Each holds that client's look and rules; the engine itself has no look.

| Folder | What it is |
|---|---|
| `_example/` | Empty template: placeholders and comments only. Copy it for a new client. |
| `_demo-test-only/` | Flat greys for the synthetic install test. Not a design. Never copy it for a client. |
| `<client-name>/` | A real client: `BRAND.md` (the why, in plain words), `brand.json` (the values the build reads), `terms.txt` (names to spell right), plus their logo and font files. |

## Add a client
1. `cp -R clients/_example clients/<client-name>` (lowercase, dashes, no spaces).
2. Paste `DESIGN-INTERVIEW.md` into your Claude Code agent. It asks one question at a time and
   writes `BRAND.md`, `brand.json` and `terms.txt` from the answers.
3. Put the client's logo and font files in the folder (fonts only if their licence allows embedding
   in video; keep each licence file beside its font).
4. Check it builds: `node scripts/build.mjs --input demo-synthetic --brand clients/<client-name>/brand.json`
   then `HYPERFRAMES_NO_TELEMETRY=1 npx --yes hyperframes@0.8.143 check .` (0 errors, contrast included).

Client folders other than the two above are ignored by git (see `.gitignore`), because they hold
client files. If your repository is private and you want them versioned, remove that line.
