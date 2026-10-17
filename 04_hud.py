"""Step 4: grade the raw frames, draw the HUD and encode the video.

    python 04_hud.py                  # output/raw/*.png -> output/frames/*.png -> output/al_hada_flight.mp4
    python 04_hud.py --only 200       # compose one frame to check

Plain Python (Pillow) on top of the path-traced frames: an evening sky, haze towards the horizon and a warm
grade, a north-up minimap with the route and view cone, an elevation profile of the route with the camera
on it, a north arrow that turns with the heading, live numbers and a title card.
"""
import argparse, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from scipy.ndimage import gaussian_filter
from alhada_common import Terrain, route, TO_LL, TO_UTM, LANDMARKS, HERE, CELL, VEX

FONTS = HERE / "fonts"
FPS = 24
TXT, SUB, MUTE, ACC = (244, 238, 228), (196, 196, 204), (140, 140, 152), (240, 150, 80)
SKY_TOP, SKY_HOR, HAZE = np.array([28, 44, 78]), np.array([236, 186, 140]), np.array([214, 178, 150])


def font(size, kind="sans"):
    f = {"sans": "Inter[opsz,wght].ttf", "cond": "Oswald[wght].ttf", "serif": "SourceSerif4[opsz,wght].ttf"}[kind]
    return ImageFont.truetype(str(FONTS / f), size)


class HUD:
    def __init__(self, n_frames, W, H):
        self.t = Terrain()
        self.xy, self.ang, self.alt, self.dip, self.g, self.length = route(self.t, n_frames)
        self.n, self.W, self.H = n_frames, W, H
        self.speed = self.length / (n_frames / FPS) * 3.6
        self.g_real = self.g / VEX
        self.edge = self.g_real[: n_frames // 2].max()
        self._minimap()

    def _minimap(self, scale=8, size=300):
        t = self.t
        z = t.z_smooth[::scale, ::scale] / VEX
        gy, gx = np.gradient(z, CELL * scale)
        az, el = np.radians(315), np.radians(40)
        slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
        shade = np.sin(el) * np.cos(slope) + np.cos(el) * np.sin(slope) * np.cos(az - aspect)
        col = (t.rgb[::scale, ::scale].astype(np.float32) / 255) ** 0.9 * (0.45 + 0.8 * np.clip(shade, 0, 1))[..., None]
        im = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8))
        # crop to a square around the route
        r, c = t.rc(self.xy[:, 0], self.xy[:, 1]); r, c = r / scale, c / scale
        cx, cy, half = (c.min() + c.max()) / 2, (r.min() + r.max()) / 2, 75
        self.mm_box = (cx - half, cy - half); self.mm_k = size / (2 * half)
        self.mm = im.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half))).resize((size, size), Image.LANCZOS)
        self.mm_scale = scale

    def mm_px(self, x, y, ox, oy):
        r, c = self.t.rc(x, y)
        return ox + (c / self.mm_scale - self.mm_box[0]) * self.mm_k, oy + (r / self.mm_scale - self.mm_box[1]) * self.mm_k

    def grade(self, raw):
        img = raw.astype(np.float32)
        bg = np.all(np.abs(img - img[2, 2]) < 3, axis=2)
        H, W = bg.shape
        # horizon row per column = first terrain pixel from the top
        hor = np.where(bg.all(0), H, np.argmax(~bg, axis=0)).astype(np.float32)
        hor = gaussian_filter(hor, 6)
        rows = np.arange(H, dtype=np.float32)[:, None]
        # sky: deep blue at the top to a warm glow at the horizon
        u = np.clip(rows / max(np.median(hor), 1), 0, 1)[..., None] ** 1.6
        sky = SKY_TOP * (1 - u) + SKY_HOR * u
        # warm grade and a bit of contrast on the terrain
        t = img / 255.0
        t = np.clip((t - 0.5) * 1.18 + 0.5 + 0.03, 0, 1) ** 0.92
        t = t * np.array([1.08, 1.0, 0.88])
        t = t * 255
        # haze: strongest at the horizon, gone ~45% of the frame below it
        d = np.clip((rows - hor[None, :]) / (H * 0.45), 0, 1)
        w = (1 - d) ** 2.2 * 0.62
        t = t * (1 - w[..., None]) + HAZE * w[..., None]
        out = np.where(bg[..., None], sky, t)
        # soft vignette
        yy, xx = np.mgrid[0:H, 0:W]
        v = 1 - 0.22 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        return np.clip(out * v[..., None], 0, 255).astype(np.uint8)

    def compose(self, raw, i):
        im = Image.fromarray(self.grade(raw)).convert("RGBA")
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        W, H = self.W, self.H
        x, y = self.xy[i]; b = self.ang[i]; brg = np.degrees(b) % 360
        g = self.g_real[i]; agl = self.alt[i] - self.g[i]; alt = g + agl
        lon, lat = TO_LL.transform(x, y)
        drop = max(0.0, self.edge - g) if i > np.argmax(self.g_real[: self.n // 2]) else 0.0
        # info box (bottom left)
        bx, by = 24, H - 190
        d.rounded_rectangle([bx, by, bx + 400, by + 160], 10, fill=(12, 12, 20, 170))
        d.text((bx + 16, by + 12), "Al Hada escarpment · Taif, Saudi Arabia", font=font(17), fill=ACC)
        dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        d.text((bx + 16, by + 42), f"Heading {brg:03.0f}° {dirs[int((brg + 22.5) // 45) % 8]} · {self.speed:,.0f} km/h", font=font(14), fill=TXT)
        d.text((bx + 16, by + 62), f"Ground {g:,.0f} m · camera {agl:.0f} m above it", font=font(14), fill=TXT)
        d.text((bx + 16, by + 82), f"{lat:.4f}° N  {lon:.4f}° E", font=font(14), fill=SUB)
        d.text((bx + 16, by + 108), "Below the edge:", font=font(15), fill=TXT)
        d.text((bx + 140, by + 102), f"{drop:,.0f} m", font=font(24, "cond"), fill=ACC)
        # minimap (top right)
        mx, my = W - self.mm.width - 20, 20
        im.paste(self.mm.convert("RGBA"), (mx, my))
        d.rectangle([mx - 1, my - 1, mx + self.mm.width, my + self.mm.height], outline=(220, 215, 205, 200))
        d.line([self.mm_px(px_, py_, mx, my) for px_, py_ in self.xy[::6]], fill=(255, 255, 255, 230), width=2)
        for name in ("Al Hada", "Al Karr"):
            ex, ey = TO_UTM.transform(*LANDMARKS[name]); qx, qy = self.mm_px(ex, ey, mx, my)
            if mx < qx < mx + self.mm.width and my < qy < my + self.mm.height:
                d.ellipse([qx - 3, qy - 3, qx + 3, qy + 3], fill=(255, 255, 255, 230))
                d.text((qx, qy - 7), name, font=font(11), fill=TXT, anchor="mb")
        px_, py_ = self.mm_px(x, y, mx, my)
        cone = 1500 / (CELL * self.mm_scale) * self.mm_k
        d.polygon([(px_, py_), (px_ + cone * np.sin(b - 0.40), py_ - cone * np.cos(b - 0.40)),
                   (px_ + cone * np.sin(b + 0.40), py_ - cone * np.cos(b + 0.40))], fill=(255, 210, 140, 60), outline=(255, 210, 140, 200))
        d.ellipse([px_ - 5, py_ - 5, px_ + 5, py_ + 5], fill=ACC + (255,), outline=(255, 255, 255, 255))
        d.text((mx + 8, my + 6), "N ↑", font=font(12), fill=TXT)
        sb = 2000 / (CELL * self.mm_scale) * self.mm_k
        d.line([(mx + 10, my + self.mm.height - 14), (mx + 10 + sb, my + self.mm.height - 14)], fill=(255, 255, 255, 230), width=2)
        d.text((mx + 14 + sb, my + self.mm.height - 21), "2 km", font=font(11), fill=TXT)
        # north arrow, turning with the heading
        cx, cy, R = W - 70, my + self.mm.height + 52, 26
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(230, 230, 235, 220), width=2, fill=(12, 12, 20, 120))
        na = -b
        tip = (cx + R * 0.8 * np.sin(na), cy - R * 0.8 * np.cos(na)); tail = (cx - R * 0.6 * np.sin(na), cy + R * 0.6 * np.cos(na))
        left = (cx + R * 0.25 * np.sin(na - np.pi / 2), cy - R * 0.25 * np.cos(na - np.pi / 2)); right = (cx + R * 0.25 * np.sin(na + np.pi / 2), cy - R * 0.25 * np.cos(na + np.pi / 2))
        d.polygon([tip, left, tail, right], fill=(235, 235, 240, 230)); d.polygon([tip, left, (cx, cy), right], fill=ACC + (255,))
        # elevation profile of the route (bottom right)
        pw, ph = 360, 92; px0, py0 = W - pw - 24, H - ph - 50
        d.rounded_rectangle([px0 - 14, py0 - 30, px0 + pw + 14, py0 + ph + 22], 8, fill=(12, 12, 20, 170))
        d.text((px0, py0 - 22), "Elevation along the flight (m)", font=font(12), fill=TXT)
        zmin, zmax = 700, 2900
        k = np.linspace(0, self.n - 1, pw).astype(int)
        def py(v): return py0 + ph - (v - zmin) / (zmax - zmin) * ph
        poly = [(px0 + j, py(self.g_real[kk])) for j, kk in enumerate(k)]
        d.polygon(poly + [(px0 + pw, py0 + ph), (px0, py0 + ph)], fill=(150, 104, 70, 220))
        d.line([(px0 + j, py(self.g_real[kk] + self.alt[kk] - self.g[kk])) for j, kk in enumerate(k)], fill=(255, 255, 255, 140), width=1)
        cxp = px0 + i / (self.n - 1) * pw
        d.line([(cxp, py0), (cxp, py0 + ph)], fill=(255, 255, 255, 120))
        d.ellipse([cxp - 5, py(alt) - 5, cxp + 5, py(alt) + 5], fill=ACC + (255,), outline=(255, 255, 255, 255))
        for v in (1000, 2000):
            d.line([(px0, py(v)), (px0 + pw, py(v))], fill=(255, 255, 255, 40))
            d.text((px0 + pw - 2, py(v) - 2), f"{v:,}", font=font(10), fill=SUB, anchor="rb")
        # footer
        d.rectangle([0, H - 22, W, H], fill=(12, 12, 20, 150))
        d.text((W - 12, H - 6), f"Elevation: SRTM via AWS Terrain Tiles · Imagery: Sentinel-2 cloudless 2023 by EOX (Copernicus data) · "
               f"vertical scale ×{VEX:g} · path-traced with forge3d", font=font(10), fill=MUTE, anchor="rs")
        # title card for the first 3 seconds
        if i < FPS * 3:
            a = int(255 * min(1, (FPS * 3 - i) / FPS))
            d.text((W / 2, H * 0.40), "AL HADA", font=font(66, "serif"), fill=TXT[:3] + (a,), anchor="mm")
            d.text((W / 2, H * 0.40 + 54), "Over the edge of the Hejaz escarpment · Taif, Saudi Arabia", font=font(18), fill=SUB[:3] + (a,), anchor="mm")
        return Image.alpha_composite(im, ov).convert("RGB")


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=480)
    ap.add_argument("--only", type=int, help="compose a single frame (for checking)")
    ap.add_argument("--crf", type=int, default=22)
    a = ap.parse_args()
    raw = HERE / "output" / "raw"; out = HERE / "output" / "frames"; out.mkdir(parents=True, exist_ok=True)
    first = Image.open(raw / f"f_{(a.only or 0):05d}.png")
    hud = HUD(a.frames, *first.size)
    idx = [a.only] if a.only is not None else range(a.frames)
    for i in idx:
        p = raw / f"f_{i:05d}.png"
        if not p.exists():
            print("missing", p.name); continue
        hud.compose(np.asarray(Image.open(p).convert("RGB")), i).save(out / f"f_{i:05d}.png")
    if a.only is None:
        mp4 = HERE / "output" / "al_hada_flight.mp4"
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(out / "f_%05d.png"),
                        "-vf", "format=yuv420p", "-c:v", "libx264", "-crf", str(a.crf), "-movflags", "+faststart", str(mp4)], check=True)
        print("Saved", mp4)


if __name__ == "__main__":
    main()
