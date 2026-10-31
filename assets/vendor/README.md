# Vendor scripts

`gsap.min.js` is NOT committed. GSAP is free for commercial use under its own "Standard" licence
(https://gsap.com/standard-license), which does not clearly allow redistributing the file in another
repository. So `package.json` pins the `gsap` npm package (3.15.0), and `scripts/build.mjs` copies
`node_modules/gsap/dist/gsap.min.js` here on the first build. The copy is git-ignored. Renders then
need no network.
