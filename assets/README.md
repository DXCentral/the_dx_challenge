# Map boundary data

`canada_mexico_admin1.geojson` contains optimized United States, Canada, and
Mexico features derived from Natural Earth's 1:50m and 1:10m Admin 1 – States,
Provinces datasets. The historical filename is retained for deployment
compatibility. Natural Earth data is public domain:
https://www.naturalearthdata.com/about/terms-of-use/

The existing US county assets are retained for the app's county choropleth.

`us_counties_overlay.geojson` is a simplified, display-only derivative of the
county choropleth geometry. It keeps the Station map overlay responsive while
preserving the stable county GEOID used for heard/unheard matching.

`world_countries_50m.geojson` contains simplified country and territory
boundaries derived from Natural Earth's public-domain 1:50m Admin 0 – Map Units
dataset for the Station map's heard-country overlay.
