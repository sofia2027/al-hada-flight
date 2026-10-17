"""Shared helpers for the Al Hada flight: data loading and reprojection, colours, route and camera.

Everything is reprojected to UTM zone 37N (EPSG:32637) on a 10 m grid whose row 0 is the northern edge.
forge3d counts one unit per grid cell on every axis, so heights and camera altitudes are divided by CELL.
"""
from __future__ import annotations
import io, json
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import map_coordinates, gaussian_filter

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CELL = 10.0                       # metres per grid cell
VEX = 1.5                         # vertical exaggeration (SRTM softens the cliffs; 1.5 brings back the drama)
CROP = 2000                       # forge3d's path tracer has a 512 MiB ceiling: 2000 x 2000 cells = 20 x 20 km per frame
X0, Y0, X1, Y1 = 609000, 2349000, 649000, 2382000      # UTM 37N window (40 x 33 km) inside both downloads
TO_UTM = Transformer.from_crs(4326, 32637, always_xy=True)
TO_LL = Transformer.from_crs(32637, 4326, always_xy=True)

LANDMARKS = {  # name: (lon, lat)
    "Al Hada": (40.287, 21.368), "Al Hada road (Route 15)": (40.262, 21.373), "Al Shafa side": (40.32, 21.30),
    "Al Karr": (40.205, 21.372), "Taif": (40.415, 21.27),
}
# route: Al Hada plateau -> over the edge -> down the escarpment towards the Al Karr valley (lon, lat)
WAYPOINTS_LL = [(40.287, 21.371), (40.276, 21.371), (40.264, 21.370), (40.250, 21.368), (40.234, 21.367),
                (40.217, 21.368)]


def _merc_px(lon, lat, z, x0, y0):
    n = 2 ** z * 256
    la = np.radians(lat)
    return (lon + 180) / 360 * n - x0 * 256, (1 - np.log(np.tan(la) + 1 / np.cos(la)) / np.pi) / 2 * n - y0 * 256


def reproject():
    """Read data/alhada_dem_s2.bin (01_download.py) and resample it to the UTM grid; cached in data/alhada_utm.npz."""
    raw = (DATA / "alhada_dem_s2.bin").read_bytes()
    h = json.loads(raw[:512].decode().strip()); D, I = h["dem"], h["img"]
    nd = D["ny"] * 256 * D["nx"] * 256 * 2
    dem = np.frombuffer(raw[512:512 + nd], np.int16).reshape(D["ny"] * 256, D["nx"] * 256).astype(np.float32)
    Image.MAX_IMAGE_PIXELS = None
    img = np.asarray(Image.open(io.BytesIO(raw[512 + nd:512 + nd + I["bytes"]])).convert("RGB")).astype(np.float32)
    nx, ny = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)
    xs = X0 + (np.arange(nx) + 0.5) * CELL
    out_z = np.zeros((ny, nx), np.float32); out_c = np.zeros((ny, nx, 3), np.uint8)
    for r0 in range(0, ny, 500):                     # in strips to keep memory low
        ys = Y1 - (np.arange(r0, min(r0 + 500, ny)) + 0.5) * CELL
        gx, gy = np.meshgrid(xs, ys)
        lon, lat = TO_LL.transform(gx, gy)
        px, py = _merc_px(lon, lat, D["z"], D["x0"], D["y0"])
        out_z[r0:r0 + len(ys)] = map_coordinates(dem, [py - 0.5, px - 0.5], order=3, mode="nearest")
        px, py = _merc_px(lon, lat, I["z"], I["x0"], I["y0"])
        for k in range(3):
            out_c[r0:r0 + len(ys), :, k] = np.clip(map_coordinates(img[..., k], [py - 0.5, px - 0.5], order=1, mode="nearest"), 0, 255)
    np.savez_compressed(DATA / "alhada_utm.npz", z=np.round(out_z * 4).astype(np.int16), rgb=out_c)   # z in 0.25 m steps
    return out_z, out_c


class Terrain:
    def __init__(self):
        p = DATA / "alhada_utm.npz"
        if p.exists():
            f = np.load(p); self.z = f["z"].astype(np.float32) / 4; self.rgb = f["rgb"]
        else:
            self.z, self.rgb = reproject()
        self.ny, self.nx = self.z.shape
        z_real = gaussian_filter(self.z, 2.0)                              # takes the SRTM stair-steps out
        self.alb = albedo(z_real, self.rgb)                                # rock tone from the real slopes
        self.z_smooth = z_real * VEX                                       # everything below works in exaggerated metres
        from scipy.ndimage import maximum_filter
        self.ground_max = maximum_filter(self.z_smooth, 41)                # for a safe camera height

    def rc(self, x, y):
        return (Y1 - np.asarray(y)) / CELL - 0.5, (np.asarray(x) - X0) / CELL - 0.5

    def sample(self, arr, x, y):
        r, c = self.rc(x, y)
        return map_coordinates(arr, [np.atleast_1d(r), np.atleast_1d(c)], order=1, mode="nearest")

    def crop(self, cx, cy):
        r, c = self.rc(cx, cy)
        r0 = int(np.clip(r - CROP / 2, 0, self.ny - CROP)); c0 = int(np.clip(c - CROP / 2, 0, self.nx - CROP))
        return r0, c0

    def height_and_albedo(self, r0, c0):
        sl = (slice(r0, r0 + CROP), slice(c0, c0 + CROP))
        return np.ascontiguousarray(self.z_smooth[sl] / CELL, np.float32), np.ascontiguousarray(self.alb[sl])


def slope_deg(z):
    gy, gx = np.gradient(z, CELL)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


ROCK = np.array([0.46, 0.33, 0.25])          # warm granite/basement rock of the Hejaz edge


def albedo(z, rgb):
    """Sentinel-2 colour, lifted a little; steep faces blend to a warm rock tone (the 'Yosemite' trick)."""
    c = gaussian_filter((rgb.astype(np.float32) / 255.0) ** 1.1 * 1.15, (0.8, 0.8, 0))   # soften the 10 m cells
    s = slope_deg(z)
    w = np.clip((s - 32) / 16, 0, 1)[..., None] * 0.7          # SRTM smooths cliffs, so the ramp starts at ~32 deg
    c = c * (1 - w) + ROCK * w
    a = np.ones(z.shape + (4,), np.float32); a[..., :3] = np.clip(c, 0, 1)
    return a


def route(terrain, n_frames):
    """Camera path: Catmull-Rom through the waypoints at equal steps, heading smoothed, altitude profile."""
    W = np.array([TO_UTM.transform(lo, la) for lo, la in WAYPOINTS_LL])
    P = np.vstack([W[0] * 2 - W[1], W, W[-1] * 2 - W[-2]])
    pts = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, 80, endpoint=False):
            pts.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    pts.append(P[-2]); pts = np.array(pts)
    s = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    q = np.linspace(0, s[-1], n_frames)
    xy = np.c_[np.interp(q, s, pts[:, 0]), np.interp(q, s, pts[:, 1])]
    d = np.gradient(xy, axis=0)
    from scipy.ndimage import gaussian_filter1d
    ang = gaussian_filter1d(np.unwrap(np.arctan2(d[:, 0], d[:, 1])), 20, mode="nearest")
    # altitude: hold over the plateau, then glide down the escarpment, always >= 180 m above the highest ground nearby
    u = q / s[-1]
    g = terrain.sample(terrain.z_smooth, xy[:, 0], xy[:, 1])
    gmax = terrain.sample(terrain.ground_max, xy[:, 0], xy[:, 1])
    start, end = g[0] + 620, g[-1] + 520
    ease = np.where(u < 0.20, 0, 0.5 - 0.5 * np.cos(np.pi * np.clip((u - 0.20) / 0.80, 0, 1)))
    alt = start + (end - start) * ease
    alt = gaussian_filter1d(np.maximum(alt, gmax + 380), 15, mode="nearest")
    # camera dip: level-ish over the plateau, tipping down as it goes over the edge, easing back out
    dip = 15 + 15 * np.exp(-((u - 0.42) / 0.13) ** 2)
    return xy, ang, alt, dip, g, s[-1]


def camera_for(terrain, x, y, bearing, alt, dip_deg, lookahead=600.0, fov=46.0, aspect=16 / 9):
    tx, ty = x + lookahead * np.sin(bearing), y + lookahead * np.cos(bearing)
    talt = alt - lookahead * np.tan(np.deg2rad(dip_deg))
    # 20 x 20 km crop centred 6 km ahead: covers the view to ~16 km, the rest fades into haze
    r0, c0 = terrain.crop(x + 6000 * np.sin(bearing), y + 6000 * np.cos(bearing))
    def world(px, py, z):
        r, c = terrain.rc(px, py)
        return (float(c - c0 - CROP / 2), float(z / CELL), float(r - r0 - CROP / 2))
    cam = {"model": "pinhole", "origin": world(x, y, alt), "look_at": world(tx, ty, talt), "up": (0.0, 1.0, 0.0),
           "fov_y": fov, "aspect": aspect, "exposure": 1.0}
    return cam, (r0, c0)
