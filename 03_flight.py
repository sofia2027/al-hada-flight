"""Step 3: path-trace every frame of the flight (raw frames, no HUD) with forge3d.

    python 03_flight.py                 # 480 frames (20 s at 24 fps), 1280 x 720 -> output/raw/f_00000.png ...
    python 03_flight.py --frames 240    # shorter / faster test flight
    python 03_flight.py --start 300     # resume from frame 300

Each frame is one call to forge3d's path tracer with a new pinhole camera. The terrain passed to forge3d is
a 20 x 20 km window (10 m cells) centred 6 km ahead of the camera, because the path tracer has a 512 MiB
ceiling. Already rendered frames are skipped, so the script can be stopped and restarted.
"""
import argparse, time
import numpy as np
from PIL import Image
from forge3d.path_tracing import render_terrain_poster
from alhada_common import Terrain, route, camera_for, HERE

# afternoon sun from the south-south-west: side light across the westward flight, long shadows in every ravine
SUN = dict(sun_azimuth_deg=205.0, sun_elevation_deg=28.0, sun_intensity=3.0, env_intensity=0.7)


def render_frame(terrain, x, y, bearing, alt, dip, w, h, spp_frames=2):
    cam, (r0, c0) = camera_for(terrain, x, y, bearing, alt, dip, aspect=w / h)
    z, alb = terrain.height_and_albedo(r0, c0)
    r = render_terrain_poster(z, w, h, camera=cam, tile=512, albedo_map=alb, spacing=(1.0, 1.0), exaggeration=1.0,
                              spp=1, min_frames=spp_frames, max_frames=spp_frames, variance_threshold=1e9, **SUN)
    return np.asarray(r["rgba"], np.uint8)[..., :3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=480)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--step", type=int, default=1, help="render every n-th frame (for parallel runs use --start k --step n)")
    a = ap.parse_args()
    out = HERE / "output" / "raw"; out.mkdir(parents=True, exist_ok=True)
    terrain = Terrain()
    xy, ang, alt, dip, g, length = route(terrain, a.frames)
    print(f"route {length / 1000:.2f} km, {a.frames} frames", flush=True)
    t0 = time.time(); done = 0
    for i in range(a.start, a.frames, a.step):
        p = out / f"f_{i:05d}.png"
        if p.exists():
            continue
        Image.fromarray(render_frame(terrain, *xy[i], ang[i], alt[i], dip[i], a.width, a.height)).save(p)
        done += 1
        print(f"frame {i + 1}/{a.frames}  {(time.time() - t0) / done:.1f} s/frame", flush=True)


if __name__ == "__main__":
    main()
