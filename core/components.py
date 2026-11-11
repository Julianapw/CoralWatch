
"""Reusable Streamlit components and stable NASA display labels."""

from html import escape

import pandas as pd
import streamlit as st


def area_labels(catalog):
    """Create display labels from the complete NASA flight catalog."""
    if "flight_line" not in catalog:
        return {}

    data = catalog.dropna(subset=["flight_line"]).copy()
    data["_sort_code"] = data["flight_line"].astype(str)

    if "observation_date" in data:
        data = data.sort_values(
            ["observation_date", "_sort_code"],
            kind="stable",
            na_position="last",
        )
    else:
        data = data.sort_values("_sort_code", kind="stable")

    data = data.drop_duplicates("flight_line")

    result = {}

    for number, (_, row) in enumerate(data.iterrows(), 1):
        date = row.get("observation_date")

        suffix = (
            f" | flight date {date:%Y-%m-%d}"
            if pd.notna(date)
            else " | date not available"
        )

        result[row["flight_line"]] = f"Area {number:02d}" + suffix

    return result


def display_name(code):
    return st.session_state.get("_cw_area_labels", {}).get(
        code,
        str(code),
    )


def display_frame(frame):
    """Add a presentation label without changing source identifiers."""
    data = frame.copy()

    if "flight_line" in data:
        data["_area"] = data["flight_line"].map(display_name)

    return data


def data_source_badge(source):
    text = (
        "NASA CORAL | historical observations"
        if source == "NASA"
        else "NOAA Coral Reef Watch | observation date"
    )
    return f'<p class="cw-source">{text}</p>'


def section_header(title, subtitle="", source="NASA"):
    st.subheader(title)

    if subtitle:
        st.caption(subtitle)


def kpi_card(title, value, detail, key, source="NASA"):
    st.metric(title, value)
    st.caption(detail)


def alert_card(code, title, count, detail):
    risk_pill(title, code)
    st.caption(f"{count} | {detail}")


def disclaimer():
    st.caption(
        "NASA CORAL provides historical observations. NOAA provides "
        "thermal-stress and bleaching-risk indicators for the reported "
        "dates. These products do not diagnose the mortality of individual "
        "coral colonies."
    )


def hero(title, subtitle):
    st.title(title)
    st.caption(subtitle)


def insight(text):
    st.caption(text)


def empty_chart(text):
    st.markdown(
        '<div class="cw-empty">'
        "<strong>No observations available</strong>"
        + escape(text)
        + "</div>",
        unsafe_allow_html=True,
    )


def summary_item(title, value):
    st.caption(title)
    st.write(str(value))


def risk_pill(text, code):
    try:
        numeric_code = float(code)
        if numeric_code.is_integer() and 0 <= numeric_code <= 4:
            category = str(int(numeric_code))
        else:
            category = "other"
    except (TypeError, ValueError):
        category = "other"

    st.markdown(
        f'<span class="cw-risk cw-risk-{category}">'
        f"{escape(str(text))}</span>",
        unsafe_allow_html=True,
    )