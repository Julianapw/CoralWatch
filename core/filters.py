
"""Shared sidebar filters for the NASA and NOAA data sources."""

import streamlit as st

from core.components import display_name


def date_filter(data, column, title, key):
    if column not in data or data[column].dropna().empty:
        st.sidebar.caption(f"{title}: valid dates are unavailable.")
        return data

    lower = data[column].min().date()
    upper = data[column].max().date()

    interval = st.sidebar.date_input(
        title,
        (lower, upper),
        min_value=lower,
        max_value=upper,
        key=key,
    )

    if len(interval) != 2:
        st.sidebar.caption("Select both a start date and an end date.")
        return data.iloc[0:0]

    return data[
        data[column].dt.date.between(*interval)
    ]


def choice_filter(data, column, title, key):
    if column not in data or data[column].dropna().empty:
        st.sidebar.caption(f"{title}: field is unavailable.")
        return data

    options = sorted(
        data[column].dropna().unique().tolist(),
        key=str,
    )

    def presentation(value):
        if column == "flight_line":
            return display_name(value)

        if column == "variable":
            return {
                "coral": "Coral",
                "algae": "Algae",
                "sand": "Sand",
            }.get(value, str(value))

        return str(value)

    selected = st.sidebar.multiselect(
        title,
        options,
        default=options,
        key=key,
        format_func=presentation,
    )

    return data[data[column].isin(selected)]


def nasa_filters(bundle):
    st.sidebar.markdown("**NASA | historical campaign**")

    catalog = bundle["catalog"].copy()
    benthic = bundle["benthic"].copy()

    base = catalog if not catalog.empty else benthic

    for column, title in [
        ("region", "NASA region"),
        ("flight_line", "Flight ID"),
        ("geographic_region", "Geographic region"),
    ]:
        base = choice_filter(
            base,
            column,
            title,
            "nasa_" + column,
        )

    base = date_filter(
        base,
        "observation_date",
        "NASA survey date",
        "nasa_dates",
    )

    if "flight_line" in base:
        flights = base["flight_line"].unique()

        if "flight_line" in benthic:
            benthic = benthic[
                benthic["flight_line"].isin(flights)
            ]

        if "flight_line" in catalog:
            catalog = catalog[
                catalog["flight_line"].isin(flights)
            ]

    elif base.empty:
        benthic = benthic.iloc[0:0]
        catalog = catalog.iloc[0:0]

    full = benthic.copy()

    benthic = choice_filter(
        benthic,
        "variable",
        "Benthic class",
        "classes",
    )

    spatial = bundle["spatial"].copy()

    if not spatial.empty:
        if "flight_line" in spatial and "flight_line" in base:
            spatial = spatial[
                spatial["flight_line"].isin(base["flight_line"])
            ]

        elif "source_file" in spatial and "source_file" in base:
            spatial = spatial[
                spatial["source_file"].isin(base["source_file"])
            ]

        else:
            spatial = spatial.iloc[0:0]

        if "variable" in spatial and "variable" in benthic:
            spatial = spatial[
                spatial["variable"].isin(benthic["variable"])
            ]

    return catalog, benthic, full, spatial


def noaa_filters(bundle):
    st.sidebar.markdown("**NOAA | independent time window**")

    noaa = bundle["noaa"].copy()

    if bundle["regional"]:
        noaa = choice_filter(
            noaa,
            "region",
            "NOAA region / footprint",
            "noaa_region",
        )
    else:
        st.sidebar.caption(
            "The selected NOAA series is global and has no regional filter. "
            "NASA filters do not change NOAA data."
        )

    pixels = bundle["pixels"].copy()

    if noaa.empty and bundle["noaa"].empty and not pixels.empty:
        pixels = date_filter(
            pixels,
            "date",
            "NOAA pixel dates",
            "noaa_pixel_dates",
        )
    else:
        noaa = date_filter(
            noaa,
            "date",
            "NOAA observation dates",
            "noaa_dates",
        )

    if not pixels.empty:
        if bundle["regional"]:
            if "region" in pixels:
                if "region" in noaa:
                    pixels = pixels[
                        pixels["region"].isin(noaa["region"].unique())
                    ]
                else:
                    pixels = pixels.iloc[0:0]
            else:
                pixels = pixels.iloc[0:0]

        if "date" in noaa and not noaa.empty:
            pixels = pixels[
                pixels["date"].between(
                    noaa["date"].min(),
                    noaa["date"].max(),
                )
            ]
        elif not bundle["noaa"].empty:
            pixels = pixels.iloc[0:0]

    return noaa, pixels


def clear_filters():
    for key in list(st.session_state):
        if key.startswith(("nasa_", "noaa_")) or key == "classes":
            del st.session_state[key]


def render_filters(bundle):
    st.sidebar.button(
        "Clear filters",
        on_click=clear_filters,
        width="stretch",
    )

    catalog, benthic, full, spatial = nasa_filters(bundle)
    noaa, pixels = noaa_filters(bundle)

    st.sidebar.caption(
        f"{len(benthic):,} benthic records | "
        f"{len(noaa):,} NOAA daily records selected"
    )
    st.sidebar.caption(
        "NASA flight, survey and class filters do not apply to NOAA."
    )

    return catalog, benthic, full, spatial, noaa, pixels
