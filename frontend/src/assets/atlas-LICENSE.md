# Atlas map provenance

The local world basemap and point coordinates derive from Natural Earth, whose vector data is in the public domain. No map service or remote tiles are loaded by the app.

- Terms: https://www.naturalearthdata.com/about/terms-of-use/
- Official repository: https://github.com/nvkelso/natural-earth-vector
- Retrieved: 29 September 2026

## Inputs

- [ne_110m_admin_0_countries.geojson](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson), SHA-256 `6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f`.
- [ne_50m_admin_0_countries.geojson](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson), SHA-256 `3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb`.
- [ne_50m_admin_0_map_subunits.geojson](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_map_subunits.geojson), SHA-256 `b1df8433477614c89e6b724990a7ab3733ec647559863321b6255c3fa3fce3ec`.

## Transformation and meaning

`atlasWorldPaths.json` contains the 1:110m country polygon rings projected equirectangularly as `x = (longitude + 180) × 2`, `y = (90 − latitude) × 2`, rounded to two decimal places. Antarctica is omitted from this literary discovery viewport. Ring geometry is otherwise unchanged.

`../atlasGeography.ts` contains exact `LABEL_X`/`LABEL_Y` values and English label variants from 1:50m countries, followed by map subunits. First matching country labels take priority, while England, Scotland, Wales and Northern Ireland retain their own subunit coordinates. These are cartographic label points, not capitals, author birthplaces or historical borders. A small explicit alias table handles alternative spellings; labels are never merged in the catalog or its filters. Ambiguous multi-country, literary-tradition and historical-context labels remain unplaced.

The map provides a contemporary geographic reference only. Country boundaries and disputed territories reflect the source cartography, not a statement about sovereignty or the historical extent of a literary tradition. Small islands may have a label point even when their outline is absent at 1:110m scale.
