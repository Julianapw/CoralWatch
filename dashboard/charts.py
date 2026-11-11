
"""Consistent Plotly and PyDeck presentation."""

from html import escape

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from dashboard.data import coordinates, numeric
from core.theme import (
    BENTHIC,
    ALERT_COLORS,
    SERIES_COLORS,
    CHART_HEIGHT,
    MAP_HEIGHT,
    plotly_template,
)
from core.components import empty_chart


ALERTS = {
    0: "No Stress",
    1: "Bleaching Watch",
    2: "Bleaching Warning",
    3: "Alert Level 1",
    4: "Alert Level 2",
}


def label(value):
    if pd.isna(value):
        return "No data"

    try:
        code = int(value)
    except (TypeError, ValueError):
        return f"Unknown BAA code: {value}"

    return ALERTS.get(
        code,
        f"BAA code {value:g} - check source metadata",
    )


def plot(figure):
    figure.update_layout(
        template=plotly_template(),
        height=CHART_HEIGHT,
        legend_title_text="",
    )

    for index, trace in enumerate(figure.data):
        if trace.type == "scatter":
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            trace.line.color = color
            trace.marker.color = color

        if trace.name in ("coral", "algae", "sand"):
            trace.name = {
                "coral": "Coral",
                "algae": "Algae",
                "sand": "Sand",
            }[trace.name]

    st.plotly_chart(
        figure,
        width="stretch",
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "responsive": True,
        },
    )


def bounds_points(frame):
    data = frame.copy()

    required = [
        "latitude_min",
        "latitude_max",
        "longitude_min",
        "longitude_max",
    ]

    if not set(required).issubset(data.columns):
        return pd.DataFrame()

    for column in required:
        data[column] = numeric(data[column])

    data = data[
        data["latitude_min"].between(-90, 90)
        & data["latitude_max"].between(-90, 90)
        & data["longitude_min"].between(-180, 180)
        & data["longitude_max"].between(-180, 180)
        & (data["latitude_min"] <= data["latitude_max"])
        & (data["longitude_min"] <= data["longitude_max"])
    ].copy()

    data["latitude"] = (
        data["latitude_min"] + data["latitude_max"]
    ) / 2

    data["longitude"] = (
        data["longitude_min"] + data["longitude_max"]
    ) / 2

    data["geometry_note"] = "Approximate centroid of geographic boundaries"

    return data


def map_chart(frame, value=None, categorical=False):
    data = coordinates(frame)

    if data.empty:
        empty_chart(
            "The map requires valid latitude and longitude coordinates "
            "or geographic boundaries."
        )
        return

    if value and value in data:
        data[value] = numeric(data[value])
        data = data.dropna(subset=[value])

    if data.empty:
        empty_chart("No valid measurements are available for this map.")
        return

    if len(data) > 50000:
        step = max(2, (len(data) + 49999) // 50000)
        data = data.iloc[::step].copy()
        st.caption(
            "Map display uses a regular subsample of up to 50,000 points. "
            "Tables and downloads retain the filtered data."
        )

    def rgb(code):
        color = ALERT_COLORS.get(code, "#697687")
        return [int(color[i:i + 2], 16) for i in (1, 3, 5)]

    if categorical and value in data:
        data["color"] = data[value].map(rgb)
        data["alert_label"] = data[value].map(label)

    elif value and value in data:
        low = data[value].min()
        high = data[value].max()

        scaled = (
            (data[value] - low) / (high - low)
            if high > low
            else pd.Series(0.5, index=data.index)
        )

        data["color"] = [
            [
                int(40 + 190 * value),
                int(170 - 100 * value),
                int(190 - 130 * value),
            ]
            for value in scaled
        ]

        st.caption(
            f"{value} scale: turquoise {low:.2f} to orange {high:.2f}."
        )

    else:
        data["color"] = [[0, 143, 149]] * len(data)

    tooltip_columns = [
        column
        for column in (
            "_area",
            "flight_line",
            "source_file",
            "region",
            "date",
            "observation_date",
            "alert_label",
            value,
            "units",
            "coral",
            "algae",
            "sand",
            "unit_label",
            "geometry_note",
        )
        if column and column in data
    ]

    names = {
        "_area": "Survey area",
        "flight_line": "Flight ID",
        "source_file": "Original file",
        "region": "Region / footprint",
        "date": "Observation date",
        "observation_date": "Survey date",
        "alert_label": "BAA level (7-day maximum)",
        "value": "Source value",
        "units": "Units",
        "geometry_note": "Geometry",
        "unit_label": "Unit",
    }

    tooltip = "<br/>".join(
        f"{names.get(column, column)}: {{{column}}}"
        for column in dict.fromkeys(tooltip_columns)
    )

    for column in data.select_dtypes(
        include=["datetime", "datetimetz"]
    ).columns:
        data[column] = data[column].dt.strftime("%Y-%m-%d")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data.to_dict("records"),
        get_position="[longitude, latitude]",
        get_fill_color="color",
        get_radius=350,
        radius_min_pixels=4,
        pickable=True,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(
            latitude=float(data["latitude"].mean()),
            longitude=float(data["longitude"].mean()),
            zoom=4,
        ),
        map_style=pdk.map_styles.LIGHT,
        tooltip={
            "html": tooltip or "Georeferenced observation",
        },
    )

    st.pydeck_chart(deck, height=MAP_HEIGHT)

    if categorical:
        legend = "".join(
            (
                '<span><span class="cw-risk cw-risk-'
                + str(code)
                + '">'
                + escape(name)
                + "</span></span>"
            )
            for code, name in ALERTS.items()
        )

        st.markdown(
            '<div class="cw-legend">'
            + legend
            + "<span>Other codes: gray | No data: unclassified</span>"
            + "</div>",
            unsafe_allow_html=True,
        )
