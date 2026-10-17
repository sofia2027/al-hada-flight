"""Step 2: render one still to check the look before the long flight render.

    python 02_still.py               # frame 180 of 480 (going over the edge) -> output/still_0180.png
    python 02_still.py --frame 320   # halfway down the escarpment
"""
import argparse, importlib
from PIL import Image
from alhada_common import Terrain, route, HERE

flight = importlib.import_module("03_flight")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=int, default=180)
    ap.add_argument("--frames", type=int, default=480)
    a = ap.parse_args()
    t = Terrain(); xy, ang, alt, dip, g, _ = route(t, a.frames); i = a.frame
    img = flight.render_frame(t, *xy[i], ang[i], alt[i], dip[i], 1280, 720)
    out = HERE / "output"; out.mkdir(exist_ok=True)
    p = out / f"still_{i:04d}.png"; Image.fromarray(img).save(p); print("Saved", p)


if __name__ == "__main__":
    main()
