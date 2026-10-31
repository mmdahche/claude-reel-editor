#!/usr/bin/env python3
"""Clean the per-frame person masks from seg (Apple Vision) for a stable cutout.

For every frame: a blend with its neighbours in time to stop flicker: --temporal median (the
default; per-pixel median over t-1..t+1, which removes one-frame flicker but follows real motion,
so no ghost edges) or --temporal mean (weighted, --weights 1,2,1; ghosts when he moves fast), a levels curve that firms up the soft Vision edge (lo/hi), a choke
(erode the edge by --choke px), then a feather (Gaussian blur, --feather px). The frame's
bottom rows are forced opaque where the body reaches the bottom edge (--bottom-rows), so the
torso never fades out at the frame edge. Fix problems with these parameters, never by hand.

  python3 process_masks.py <mask_dir> <out_dir> [--temporal median|mean] [--weights 1,2,1] [--lo 0.35] [--hi 0.85]
                           [--smooth-below 0] [--smooth-sigma 5] [--choke 1] [--feather 1.2] [--bottom-rows 6]
--smooth-below Y (0 = off) smooths the outline below row Y (the shoulders, where a white shirt
meets a white chair and the Vision edge goes lumpy): a Gaussian blur of --smooth-sigma px, then a
re-threshold at 0.5, faded in over the 60 rows above Y so hair and face edges keep their detail.
Writes f_00001.png ... (8-bit grayscale, same size), streaming a small window of frames.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageFilter


def load(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mask_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--temporal", choices=["median", "mean"], default="median")
    ap.add_argument("--weights", default="1,2,1")
    ap.add_argument("--lo", type=float, default=0.35)
    ap.add_argument("--hi", type=float, default=0.85)
    ap.add_argument("--smooth-below", type=int, default=0)
    ap.add_argument("--smooth-sigma", type=float, default=5.0)
    ap.add_argument("--choke", type=int, default=1)
    ap.add_argument("--feather", type=float, default=1.2)
    ap.add_argument("--bottom-rows", type=int, default=6)
    a = ap.parse_args()
    files = sorted(f for f in os.listdir(a.mask_dir) if f.endswith(".png"))
    if not files:
        sys.exit(f"no masks in {a.mask_dir}")
    w = [float(x) for x in a.weights.split(",")]
    if len(w) % 2 != 1:
        sys.exit("--weights needs an odd count (centred on the frame)")
    half = len(w) // 2
    os.makedirs(a.out_dir, exist_ok=True)
    cache = {}
    for i, name in enumerate(files):
        window = []
        for k in range(len(w)):
            j = min(len(files) - 1, max(0, i + k - half))  # clamp at the ends
            if j not in cache:
                cache[j] = load(os.path.join(a.mask_dir, files[j]))
            window.append(cache[j])
        for j in [j for j in cache if j < i - half]:
            del cache[j]
        if a.temporal == "median":
            blended = np.median(np.stack(window), axis=0)
        else:
            blended = sum(m * wk for m, wk in zip(window, w)) / sum(w)
        m = np.clip((blended - a.lo) / max(1e-6, a.hi - a.lo), 0.0, 1.0)
        if a.smooth_below > 0:
            blur = np.asarray(Image.fromarray((m * 255.0 + 0.5).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(a.smooth_sigma)), dtype=np.float32) / 255.0
            smooth = np.clip((blur - 0.45) / 0.10, 0.0, 1.0)
            rows = np.arange(m.shape[0], dtype=np.float32)[:, None]
            wgt = np.clip((rows - (a.smooth_below - 60)) / 60.0, 0.0, 1.0)
            m = m * (1.0 - wgt) + smooth * wgt
        img = Image.fromarray((m * 255.0 + 0.5).astype(np.uint8), "L")
        for _ in range(max(0, a.choke)):
            img = img.filter(ImageFilter.MinFilter(3))
        if a.feather > 0:
            img = img.filter(ImageFilter.GaussianBlur(a.feather))
        out = np.asarray(img, dtype=np.uint8).copy()
        if a.bottom_rows > 0:
            # where the body touches the bottom edge, keep the last rows solid (no fade at the edge)
            edge = out[-(a.bottom_rows + 6)] > 128
            out[-a.bottom_rows:, edge] = 255
        Image.fromarray(out, "L").save(os.path.join(a.out_dir, name), compress_level=1)
        if (i + 1) % 200 == 0:
            print(f"{i + 1}/{len(files)}", flush=True)
    print(f"done {len(files)} masks -> {a.out_dir}")


if __name__ == "__main__":
    main()
