# Data licences

Code: MIT (see LICENSE).

`data/alhada_dem_s2.bin` holds a stitched copy of the two tile sets below for the flight window (lon 40.03–40.47 E, lat 21.21–21.58 N), as written by `01_download.py`.

- **Elevation:** [Terrain Tiles on AWS](https://registry.opendata.aws/terrain-tiles/) (Mapzen / Tilezen "terrarium" encoding), zoom 13. In this area the source is **SRTM** (NASA / USGS, public domain). Attribution requested by the tile set: "Terrain Tiles were made with data from SRTM, GMTED, NED, ETOPO1 and others" (see the tile set's [attribution page](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)).
- **Imagery:** **Sentinel-2 cloudless 2023** by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2023), https://s2maps.eu. Licence: **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0)**. That means:
  - **Attribution:** credit EOX and Copernicus.
  - **No commercial use:** the video and any frames from it may not be used commercially.
  - **ShareAlike:** derived images such as the video and the preview frame are shared under the same licence.

`data/alhada_utm.npz` (created on first run, not committed) is a reprojected copy of the same data.

Fonts: Inter, Oswald and Source Serif 4, SIL Open Font License 1.1 (see `fonts/OFL-*.txt`).
