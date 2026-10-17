"""Step 1: download the elevation and the satellite image for the Al Hada escarpment (Taif, Saudi Arabia).

    python 01_download.py          # -> data/alhada_dem_s2.bin (about 18 MB)

Two free tile services, no key needed:
  * Elevation: AWS Terrain Tiles ("terrarium" PNG encoding), zoom 13, about 18 m per pixel at 21 N.
    Height in metres = R * 256 + G + B / 256 - 32768. In this area the source is SRTM (30 m).
  * Colour: Sentinel-2 cloudless 2023 by EOX (JPEG, Web Mercator), zoom 14, about 9 m per pixel.

Both are stitched into one mosaic each and written to a single binary file:
  512-byte JSON header (tile ranges, space padded) | int16 DEM, row-major | JPEG of the image mosaic
The window covers lon 40.05-40.45 E, lat 21.22-21.55 N: the Taif plateau, the Al Hada / Al Shafa edge and
the lowlands towards Makkah.
"""
import io, json
from pathlib import Path
import numpy as np
import requests
from PIL import Image

HERE = Path(__file__).resolve().parent
DEM = dict(z=13, x0=5007, y0=3593, nx=10, ny=9)
IMG = dict(z=14, x0=10014, y0=7187, nx=19, ny=17)
DEM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
IMG_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg"


def get(url):
    r = requests.get(url, timeout=60, headers={"User-Agent": "al-hada-flight (github)"})
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))


def main():
    dem = np.zeros((DEM["ny"] * 256, DEM["nx"] * 256), np.int16)
    for j in range(DEM["ny"]):
        for i in range(DEM["nx"]):
            t = np.asarray(get(DEM_URL.format(z=DEM["z"], x=DEM["x0"] + i, y=DEM["y0"] + j)).convert("RGB")).astype(np.float64)
            h = t[..., 0] * 256 + t[..., 1] + t[..., 2] / 256 - 32768
            dem[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = np.round(h).astype(np.int16)
        print(f"elevation row {j + 1}/{DEM['ny']}", flush=True)
    mosaic = Image.new("RGB", (IMG["nx"] * 256, IMG["ny"] * 256))
    for j in range(IMG["ny"]):
        for i in range(IMG["nx"]):
            mosaic.paste(get(IMG_URL.format(z=IMG["z"], x=IMG["x0"] + i, y=IMG["y0"] + j)).convert("RGB"), (i * 256, j * 256))
        print(f"image row {j + 1}/{IMG['ny']}", flush=True)
    buf = io.BytesIO(); mosaic.save(buf, "JPEG", quality=92); jpg = buf.getvalue()
    head = json.dumps({"dem": DEM, "img": dict(IMG, bytes=len(jpg))}).encode().ljust(512, b" ")
    out = HERE / "data"; out.mkdir(exist_ok=True)
    (out / "alhada_dem_s2.bin").write_bytes(head + dem.tobytes() + jpg)
    print("saved", out / "alhada_dem_s2.bin", f"DEM {dem.min()}-{dem.max()} m")


if __name__ == "__main__":
    main()
