from __future__ import annotations


STATION_DATA_ATTRIBUTION = {
    "MW": (
        "Station information and data come from multiple sources, including "
        "[Mesa Mike's U.S. station list](https://mesamike.org/radio/amdb/amdb.mvc), "
        "[Tim Tromp's U.S. and Canadian station information](https://amdxer.com/ambc/), "
        "Mike Jeziorski's personal Mexican station notes, Loyd Van Horn's personal "
        "logbook, and crowdsourced data from all seasons of the MW Frequency Challenge "
        "and Summer of DX Challenges."
    ),
    "FM": (
        "Station data are sourced from the "
        "[Worldwide TV-FM DX Association (WTFDA) Station Database](https://db.wtfda.org/), "
        "Loyd Van Horn's personal logs, and crowdsourced information from previous seasons "
        "of the MW Frequency Challenge and Summer of DX Challenges."
    ),
    "NWR": (
        "Station data are sourced from publicly available "
        "[NOAA Weather Radio station information](https://www.weather.gov/nwr/station_listing)."
    ),
}


def station_data_attribution(band: str) -> str:
    return STATION_DATA_ATTRIBUTION.get(str(band).strip().upper(), "")
