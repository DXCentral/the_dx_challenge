from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache

import pandas as pd
try:
    import plotly.graph_objects as go
except ModuleNotFoundError:  # Deployed builds install Plotly from requirements.txt.
    go = None

from dxcore.config import ADMIN1_GEOJSON_FILE


COUNTRY_LABELS = {"CAN": "Canada", "MEX": "Mexico"}
COUNTRY_ALIASES = {
    "CAN": {"can", "canada"},
    "MEX": {"mex", "mexico"},
}

CANADA_NAMES = {
    "CA-AB": "Alberta",
    "CA-BC": "British Columbia",
    "CA-MB": "Manitoba",
    "CA-NB": "New Brunswick",
    "CA-NL": "Newfoundland and Labrador",
    "CA-NS": "Nova Scotia",
    "CA-NT": "Northwest Territories",
    "CA-NU": "Nunavut",
    "CA-ON": "Ontario",
    "CA-PE": "Prince Edward Island",
    "CA-QC": "Quebec",
    "CA-SK": "Saskatchewan",
    "CA-YT": "Yukon",
}
MEXICO_NAMES = {
    "MX-AGU": "Aguascalientes",
    "MX-BCN": "Baja California",
    "MX-BCS": "Baja California Sur",
    "MX-CAM": "Campeche",
    "MX-CHH": "Chihuahua",
    "MX-CHP": "Chiapas",
    "MX-CMX": "Mexico City",
    "MX-COA": "Coahuila",
    "MX-COL": "Colima",
    "MX-DIF": "Mexico City",
    "MX-DUR": "Durango",
    "MX-GRO": "Guerrero",
    "MX-GUA": "Guanajuato",
    "MX-HID": "Hidalgo",
    "MX-JAL": "Jalisco",
    "MX-MEX": "State of Mexico",
    "MX-MIC": "Michoacan",
    "MX-MOR": "Morelos",
    "MX-NAY": "Nayarit",
    "MX-NLE": "Nuevo Leon",
    "MX-OAX": "Oaxaca",
    "MX-PUE": "Puebla",
    "MX-QUE": "Queretaro",
    "MX-ROO": "Quintana Roo",
    "MX-SIN": "Sinaloa",
    "MX-SLP": "San Luis Potosi",
    "MX-SON": "Sonora",
    "MX-TAB": "Tabasco",
    "MX-TAM": "Tamaulipas",
    "MX-TLA": "Tlaxcala",
    "MX-VER": "Veracruz",
    "MX-YUC": "Yucatan",
    "MX-ZAC": "Zacatecas",
}
SUBDIVISION_NAMES = {**CANADA_NAMES, **MEXICO_NAMES}


def _token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _aliases() -> dict[str, dict[str, str]]:
    canada = {
        "ab": "CA-AB", "alberta": "CA-AB",
        "bc": "CA-BC", "british columbia": "CA-BC",
        "mb": "CA-MB", "manitoba": "CA-MB",
        "nb": "CA-NB", "new brunswick": "CA-NB",
        "nl": "CA-NL", "newfoundland": "CA-NL",
        "newfoundland and labrador": "CA-NL",
        "ns": "CA-NS", "nova scotia": "CA-NS",
        "nt": "CA-NT", "northwest territories": "CA-NT",
        "nu": "CA-NU", "nunavut": "CA-NU",
        "on": "CA-ON", "ontario": "CA-ON",
        "pe": "CA-PE", "pei": "CA-PE", "prince edward island": "CA-PE",
        "qc": "CA-QC", "pq": "CA-QC", "quebec": "CA-QC", "qu bec": "CA-QC",
        "sk": "CA-SK", "saskatchewan": "CA-SK",
        "yt": "CA-YT", "yukon": "CA-YT",
    }
    mexico = {
        "agu": "MX-AGU", "aguascalientes": "MX-AGU",
        "bcn": "MX-BCN", "baja california": "MX-BCN",
        "bcs": "MX-BCS", "baja california sur": "MX-BCS",
        "cam": "MX-CAM", "campeche": "MX-CAM",
        "chh": "MX-CHH", "chihuahua": "MX-CHH",
        "chp": "MX-CHP", "chiapas": "MX-CHP",
        "coa": "MX-COA", "coahuila": "MX-COA",
        "col": "MX-COL", "colima": "MX-COL",
        "dif": "MX-DIF", "cmx": "MX-DIF", "df": "MX-DIF",
        "ciudad mexico": "MX-DIF", "ciudad de mexico": "MX-DIF",
        "mexico city": "MX-DIF", "distrito federal": "MX-DIF",
        "dur": "MX-DUR", "durango": "MX-DUR",
        "gro": "MX-GRO", "guerrero": "MX-GRO",
        "gua": "MX-GUA", "guanajuato": "MX-GUA",
        "hid": "MX-HID", "hidalgo": "MX-HID",
        "jal": "MX-JAL", "jalisco": "MX-JAL",
        "mex": "MX-MEX", "mexico": "MX-MEX", "m xico": "MX-MEX",
        "estado de mexico": "MX-MEX", "estado de m xico": "MX-MEX",
        "state of mexico": "MX-MEX",
        "mic": "MX-MIC", "michoacan": "MX-MIC", "michoac n": "MX-MIC",
        "mor": "MX-MOR", "morelos": "MX-MOR",
        "nay": "MX-NAY", "nayarit": "MX-NAY",
        "nle": "MX-NLE", "nuevo leon": "MX-NLE", "nuevo le n": "MX-NLE",
        "oax": "MX-OAX", "oaxaca": "MX-OAX",
        "pue": "MX-PUE", "puebla": "MX-PUE",
        "que": "MX-QUE", "queretaro": "MX-QUE", "quer taro": "MX-QUE",
        "roo": "MX-ROO", "quintana roo": "MX-ROO",
        "sin": "MX-SIN", "sinaloa": "MX-SIN",
        "slp": "MX-SLP", "san luis potosi": "MX-SLP", "san luis potos": "MX-SLP",
        "son": "MX-SON", "sonora": "MX-SON",
        "tab": "MX-TAB", "tabasco": "MX-TAB",
        "tam": "MX-TAM", "tamaulipas": "MX-TAM",
        "tla": "MX-TLA", "tlaxcala": "MX-TLA",
        "ver": "MX-VER", "veracruz": "MX-VER",
        "yuc": "MX-YUC", "yucatan": "MX-YUC", "yucat n": "MX-YUC",
        "zac": "MX-ZAC", "zacatecas": "MX-ZAC",
    }
    return {"CAN": canada, "MEX": mexico}


SUBDIVISION_ALIASES = _aliases()


@lru_cache(maxsize=2)
def subdivision_geojson(country_code: str) -> dict[str, object]:
    code = str(country_code).upper()
    with ADMIN1_GEOJSON_FILE.open(encoding="utf-8") as handle:
        source = json.load(handle)
    features = [
        feature
        for feature in source.get("features", [])
        if feature.get("properties", {}).get("adm0_a3") == code
        and feature.get("properties", {}).get("iso_3166_2") in SUBDIVISION_NAMES
    ]
    return {"type": "FeatureCollection", "features": features}


def add_subdivision_keys(logs: pd.DataFrame, country_code: str) -> pd.DataFrame:
    """Filter one country and add canonical ISO subdivision code and display name."""
    code = str(country_code).upper()
    if logs.empty:
        result = logs.copy()
        result["admin1_code"] = pd.Series(dtype="string")
        result["admin1_name"] = pd.Series(dtype="string")
        return result
    country_tokens = logs["station_country"].map(_token)
    result = logs[country_tokens.isin(COUNTRY_ALIASES[code])].copy()
    result["admin1_code"] = result["station_region"].map(
        lambda value: SUBDIVISION_ALIASES[code].get(_token(value), "")
    )
    result["admin1_name"] = result["admin1_code"].map(SUBDIVISION_NAMES).fillna("")
    return result[result["admin1_code"] != ""].copy()


def subdivision_counts(logs: pd.DataFrame, country_code: str, metric: str) -> pd.DataFrame:
    rows = add_subdivision_keys(logs, country_code)
    counts = (
        rows.groupby(["admin1_code", "admin1_name"])
        .size()
        .reset_index(name=metric)
    )
    all_regions = pd.DataFrame(
        [
            {"admin1_code": code, "admin1_name": name}
            for code, name in SUBDIVISION_NAMES.items()
            if code.startswith("CA-" if country_code.upper() == "CAN" else "MX-")
            and code != "MX-CMX"
        ]
    )
    return (
        all_regions.merge(counts, on=["admin1_code", "admin1_name"], how="left")
        .fillna({metric: 0})
        .assign(**{metric: lambda frame: frame[metric].astype(int)})
        .sort_values([metric, "admin1_name"], ascending=[False, True])
        .reset_index(drop=True)
    )


def subdivision_figure(
    counts: pd.DataFrame,
    country_code: str,
    metric: str,
    *,
    background: str,
    surface: str,
    text_color: str,
    border_color: str,
    daylight: bool,
) -> object:
    code = str(country_code).upper()
    if go is None:
        raise RuntimeError("Plotly is required to render subdivision choropleth maps.")
    fig = go.Figure(
        go.Choropleth(
            geojson=subdivision_geojson(code),
            featureidkey="properties.iso_3166_2",
            locations=counts["admin1_code"],
            z=counts[metric],
            customdata=counts["admin1_name"],
            colorscale=[
                [0.0, "#E2E8F0" if daylight else "#1B2A3A"],
                [0.5, "#168CC4"],
                [1.0, "#7DE3FF"],
            ],
            zmin=0,
            zmax=max(int(counts[metric].max()), 1),
            marker_line_color=border_color,
            marker_line_width=0.65,
            colorbar_title=metric,
            hovertemplate=f"%{{customdata}}<br>%{{z:,}} {metric.casefold()}<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_white" if daylight else "plotly_dark",
        height=500,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor=background,
        font_color=text_color,
        dragmode="pan",
        geo=dict(
            fitbounds="locations",
            visible=False,
            bgcolor=background,
            showland=True,
            landcolor=surface,
            showocean=True,
            oceancolor=surface,
            projection_type="mercator",
        ),
    )
    return fig
