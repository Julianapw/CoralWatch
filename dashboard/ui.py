
"""English Streamlit interface for CoralWatch."""

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.data import (
    latest_by_region,
    composition_valid,
    coordinates,
    numeric,
)
from dashboard.trends import analyze_sst_history
from dashboard.charts import (
    plot,
    map_chart,
    bounds_points,
    BENTHIC,
    ALERTS,
    label,
)
from core.components import (
    kpi_card,
    alert_card,
    section_header,
    hero,
    insight,
    empty_chart,
    risk_pill,
    area_labels,
    display_frame,
)
from core.filters import render_filters
from core.theme import apply_theme
from core.data import load_bundle


PAGES = [
    "Overview",
    "Reef Composition",
    "Environmental Monitoring",
    "Early Warning System",
]

NOTICE = (
    "NASA CORAL provides historical benthic observations. NOAA provides "
    "thermal-stress and bleaching-risk indicators for the reported dates. "
    "These products do not diagnose the mortality of individual coral colonies."
)


def table(data, name):
    st.dataframe(data, hide_index=True, width="stretch")
    st.download_button(
        "Download filtered data (CSV)",
        data.to_csv(index=False).encode("utf-8-sig"),
        f"{name}.csv",
        "text/csv",
        key=f"download_{name}",
    )


def freshness(data):
    if data.empty or "date" not in data:
        st.info(
            "No NOAA observations are available in the selected filter. "
            "Check noaa_daily_summary.csv or noaa_thermal_timeseries.csv."
        )
        return

    observed = data["date"].max()
    st.caption(
        f"NOAA | Latest observation in the selected data: {observed:%Y-%m-%d}. "
        "Each region retains its own observation date."
    )

    today = pd.Timestamp(
        datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    )
    if (today - observed.normalize()).days > 7:
        st.warning(
            "The selected NOAA observations are more than 7 days old. "
            "They should not be interpreted as real-time monitoring."
        )


def methodology(bundle):
    with st.expander("Methodology and data sources"):
        st.write(NOTICE)

        source = bundle.get("source", "No NOAA source selected")
        if bundle.get("noaa", pd.DataFrame()).empty:
            source += " (no valid observations)"

        st.caption(f"Selected NOAA time-series source: {source}")

        st.write(
            "Display labels such as Area 01 and Area 02 are derived from the "
            "complete NASA flight catalog. Each area represents a flight "
            "footprint, not necessarily an individual reef. NASA and NOAA "
            "identifiers are not automatically matched."
        )

        st.write(
            "NASA benthic means are calculated from valid pixels in each "
            "flight. The coral summary card is an unweighted average across "
            "flight means; it is not an estimate of coral cover across the "
            "entire Great Barrier Reef. Class probabilities are not direct "
            "measurements of surface area."
        )

        st.write(
            "NOAA daily regional summaries are preferred over the legacy "
            "noaa_thermal_timeseries.csv format. BAA is the source-provided "
            "7-day maximum classification. HotSpot and DHW provide thermal "
            "context and are not used to reconstruct BAA."
        )

        st.write(
            "The long-term SST analysis first calculates monthly means from "
            "daily regional means. A month requires at least 15 valid daily "
            "observations; a year requires at least 9 valid months. At least "
            "10 valid years are required for statistical testing."
        )

        st.write(
            "Theil-Sen estimates the SST slope. The two-sided Mann-Kendall "
            "test evaluates monotonic trend evidence. P-values are adjusted "
            "across regions using the Benjamini-Hochberg procedure. The "
            "current implementation does not correct for serial "
            "autocorrelation, so results are exploratory."
        )

        st.write(
            "NOAA pixels represent ocean grid cells at approximately 5-km "
            "resolution within the selected geographic footprints. They are "
            "not individual coral colonies. NASA CORAL observations have "
            "approximately 7.9-m spatial resolution and are historical."
        )

        st.write(
            "No relationship between present-day NOAA thermal conditions "
            "and the historical 2016 NASA observations is inferred. Low "
            "classification coverage is not evidence of coral mortality."
        )

        st.markdown(
            "[NASA CORAL Browser](https://oceandata.sci.gsfc.nasa.gov/coral_browser/) "
            "· [NASA CORAL L2/RBEN DOI](https://doi.org/10.5067/PRISM/CORAL/L2/RBEN/V1) "
            "· [NOAA Coral Reef Watch v3.1](https://coralreefwatch.noaa.gov/product/5km/index.php) "
            "· [PacIOOS ERDDAP](https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km.html)"
        )

        st.caption(
            "The dashboard reads processed CSV and JSON files. It does not "
            "download or process NetCDF files when a page is opened."
        )

        for name, config in bundle.get("config", {}).items():
            st.write(name)
            st.json(config)

        for message in bundle.get("messages", []):
            st.warning(message)

        for name in (
            "variable_inventory.csv",
            "class_legend.csv",
            "nasa_pixel_quality.csv",
        ):
            if name in bundle.get("raw", {}):
                st.write(name)
                st.dataframe(bundle["raw"][name], hide_index=True)


def recent_table(latest):
    columns = {
        "region": "NOAA region / footprint",
        "date": "Observation date",
        "sst_mean": "Mean SST (°C)",
        "hotspot_mean": "Mean HotSpot (°C)",
        "hotspot_max": "Maximum HotSpot (°C)",
        "dhw_mean": "Mean DHW (°C-weeks)",
        "dhw_max": "Maximum DHW (°C-weeks)",
        "baa": "7-day maximum BAA",
    }

    available = [column for column in columns if column in latest]
    return latest[available].rename(columns=columns)


def source_period(data, source, date_column):
    if date_column not in data or data[date_column].dropna().empty:
        return f"{source} | observation period unavailable"

    return (
        f"{source} | {data[date_column].min():%Y-%m-%d} "
        f"to {data[date_column].max():%Y-%m-%d}"
    )


def thermal_status(latest, inline=False):
    if latest.empty:
        empty_chart("No NOAA footprint has an observation in the selected period.")
        return

    columns = st.columns(3, gap="medium") if inline else None

    for index, (_, row) in enumerate(latest.iterrows()):
        container = columns[index % 3] if columns else st.container()

        with container:
            st.markdown(f"**{row['region']}**")
            risk_pill(
                label(row.get("baa", float("nan"))),
                row.get("baa"),
            )
            st.caption(
                f"Observed on {row['date']:%Y-%m-%d} | "
                "NOAA 7-day maximum BAA"
            )

    st.caption(
        "Original NOAA identifiers are preserved. No new matching "
        "between NOAA regions and NASA flights is inferred."
    )


def overview(bundle, catalog, benthic, full, spatial, noaa, pixels):
    latest = latest_by_region(noaa)

    regions = (
        catalog["region"].nunique()
        if "region" in catalog
        else 0
    )
    flights = (
        catalog["flight_line"].nunique()
        if "flight_line" in catalog
        else 0
    )

    coral = (
        full[full["variable"] == "coral"]
        if "variable" in full
        else pd.DataFrame()
    )

    compatible = (
        not coral.empty
        and "unit_label" in coral
        and coral["unit_label"].nunique() == 1
    )
    coral_value = (
        coral["measure"].mean()
        if compatible and "measure" in coral
        else float("nan")
    )

    if not noaa.empty and "baa" in noaa:
        latest_date = noaa["date"].max()
        baa = noaa.loc[noaa["date"] == latest_date, "baa"].max()
    elif not pixels.empty and "baa" in pixels:
        baa = pixels["baa"].max()
    else:
        baa = float("nan")

    if "region" in catalog:
        regions_text = " · ".join(
            str(value)
            for value in catalog["region"].dropna().unique()
        )
        st.write(f"NASA study region: {regions_text}")

    columns = st.columns(4, gap="medium")

    with columns[0]:
        kpi_card(
            "Geographic regions",
            regions if regions else "—",
            "Region labels from the NASA flight catalog.",
            "regions",
        )

    with columns[1]:
        kpi_card(
            "Survey areas / flights",
            flights,
            "Each area represents the footprint of one NASA flight.",
            "flights",
        )

    with columns[2]:
        kpi_card(
            "Mean coral probability",
            f"{coral_value:.1f}" if pd.notna(coral_value) else "—",
            str(coral["unit_label"].iloc[0])
            if compatible
            else "Comparable units unavailable.",
            "coral",
        )

    with columns[3]:
        kpi_card(
            "Highest BAA | latest date",
            label(baa),
            "NOAA source-provided 7-day maximum.",
            "alert_max",
            "NOAA",
        )

    st.caption(
        source_period(catalog, "Historical NASA CORAL", "observation_date")
    )
    freshness(noaa if not noaa.empty else pixels)

    st.caption(
        "An area is a flight footprint, not necessarily an individual reef. "
        "The coral mean is unweighted across flights and does not represent "
        "reef-wide coral cover."
    )

    layer = st.radio(
        "Map layer",
        ["Historical NASA observations", "Recent NOAA pixels"],
        horizontal=True,
    )

    left, right = st.columns([2.2, 1], gap="large")

    with left:
        section_header(
            "Surveyed areas"
            if layer == "Historical NASA observations"
            else "Recent NOAA pixels"
        )

        if layer == "Historical NASA observations":
            points = (
                spatial[spatial["variable"] == "coral"].copy()
                if "variable" in spatial
                else spatial
            )

            if not coordinates(points).empty:
                map_chart(
                    display_frame(points),
                    "value" if "value" in points else None,
                )
                st.caption(
                    "Coral class probability in the source unit. "
                    "Individual observations may be regularly sampled."
                )
            else:
                map_chart(display_frame(bounds_points(catalog)))
                st.caption(
                    "Approximate centroids of flight boundaries, "
                    "not observed pixels."
                )
        else:
            map_chart(pixels, "baa", True)
            if not pixels.empty:
                st.caption(
                    f"NOAA pixel observations dated "
                    f"{pixels['date'].max():%Y-%m-%d}."
                )

    with right:
        section_header("Thermal status by NOAA footprint")
        thermal_status(latest)

    section_header(
        "Historical benthic composition",
        "NASA CORAL | flight-level means in the declared source units.",
    )

    if benthic.empty:
        st.info(
            "No benthic measurements are available in the selected filter. "
            "Check benthic_variable_summary.csv and its unit metadata."
        )
    else:
        for unit, group in benthic.groupby("unit_label"):
            view = display_frame(group)
            figure = px.bar(
                view,
                x="_area",
                y="measure",
                color="variable",
                color_discrete_map=BENTHIC,
                barmode="group",
                hover_data=[
                    column
                    for column in (
                        "flight_line",
                        "source_file",
                        "observation_date",
                    )
                    if column in view
                ],
                labels={
                    "_area": "Survey area",
                    "measure": unit,
                    "variable": "Benthic class",
                },
            )
            plot(figure)

    with st.expander("View and export data"):
        st.write("NASA | full benthic summary")
        table(benthic, "overview_nasa")

        st.write("NOAA | latest observation by region")
        if not latest.empty:
            table(recent_table(latest), "overview_noaa")


def composition(bundle, catalog, benthic, full, spatial):
    st.caption(
        source_period(catalog, "NASA CORAL", "observation_date")
    )
    st.caption(
        "Coral, algae and sand are class probabilities. Percentages are "
        "shown only when supported by source metadata; they are not direct "
        "measurements of surface area."
    )

    if benthic.empty:
        st.info(
            "No benthic measurements are available. Select flights and "
            "classes or check benthic_variable_summary.csv."
        )

    valid = composition_valid(full, catalog)

    coral = (
        benthic[benthic["variable"] == "coral"].dropna(subset=["measure"])
        if "variable" in benthic
        else pd.DataFrame()
    )

    direction = st.radio(
        "Sort coral ranking",
        ["Highest values", "Lowest values"],
        horizontal=True,
    )

    left, right = st.columns([1.2, 1], gap="large")

    with left:
        section_header(
            "Composition by survey area",
            "Flight-level means | original denominator preserved.",
        )

        if benthic.empty:
            empty_chart("Select flights and classes with available measurements.")
        else:
            for unit, group in benthic.groupby("unit_label"):
                view = display_frame(group)
                figure = px.bar(
                    view,
                    x="_area",
                    y="measure",
                    color="variable",
                    color_discrete_map=BENTHIC,
                    barmode="stack" if valid else "group",
                    hover_data=[
                        column
                        for column in (
                            "flight_line",
                            "source_file",
                            "observation_date",
                        )
                        if column in view
                    ],
                    labels={
                        "measure": unit,
                        "_area": "Survey area",
                        "variable": "Benthic class",
                    },
                )
                plot(figure)

        insight(
            "The classes share a validated denominator. Values are not "
            "renormalized to 100%."
            if valid
            else "Stacking was not validated. Classes are displayed side by "
            "side; pixel values are not reconstructed or adjusted to 100%."
        )

    with right:
        section_header(
            "Coral ranking",
            "Up to 20 flight-level means in the source unit.",
        )

        if not coral.empty:
            ranked = display_frame(
                coral.sort_values(
                    "measure",
                    ascending=(direction == "Lowest values"),
                ).head(20)
            )

            figure = px.bar(
                ranked,
                x="measure",
                y="_area",
                orientation="h",
                text_auto=".1f",
                color_discrete_sequence=[BENTHIC["coral"]],
                hover_data=[
                    column
                    for column in (
                        "flight_line",
                        "source_file",
                        "observation_date",
                    )
                    if column in ranked
                ],
                labels={
                    "measure": str(coral["unit_label"].iloc[0]),
                    "_area": "Survey area",
                },
            )
            figure.update_yaxes(
                categoryorder="array",
                categoryarray=ranked["_area"].tolist()[::-1],
            )
            plot(figure)
        else:
            empty_chart("No valid coral means are available.")

        insight(
            "This is a comparison across historical flights. Low values "
            "alone do not prove coral mortality."
        )

    st.divider()
    section_header(
        "Explore observations",
        "NASA CORAL | relationships and distributions in historical data.",
    )

    left, right = st.columns(2, gap="large")

    with left:
        st.markdown("**Coral vs. algae**")
        figure = None

        if (
            not benthic.empty
            and not benthic.duplicated(["flight_line", "variable"]).any()
        ):
            pivot = benthic.pivot(
                index="flight_line",
                columns="variable",
                values="measure",
            ).reset_index()

            if (
                {"coral", "algae"}.issubset(pivot.columns)
                and benthic["unit_label"].nunique() == 1
            ):
                metadata = benthic.drop_duplicates("flight_line")
                extra = [
                    column
                    for column in (
                        "region",
                        "observation_date",
                        "source_file",
                    )
                    if column in metadata
                ]

                pivot = display_frame(
                    pivot.merge(
                        metadata[["flight_line"] + extra],
                        on="flight_line",
                        validate="one_to_one",
                    )
                )

                figure = px.scatter(
                    pivot,
                    x="coral",
                    y="algae",
                    hover_name="_area",
                    hover_data=["flight_line"] + extra,
                    color="region" if "region" in pivot else None,
                    labels={
                        "coral": "Coral | " + benthic["unit_label"].iloc[0],
                        "algae": "Algae | " + benthic["unit_label"].iloc[0],
                        "region": "Region",
                        "_area": "Survey area",
                    },
                )

        if figure is not None:
            figure.update_traces(marker_size=12)
            plot(figure)
        else:
            empty_chart(
                "Comparable coral and algae means are required, "
                "without ambiguous duplicates."
            )

        insight(
            "Each point represents a historical flight. It does not show "
            "a temporal trend or a causal relationship with NOAA."
        )

    with right:
        st.markdown("**Coral distribution**")

        individual = (
            spatial[spatial["variable"] == "coral"].copy()
            if "variable" in spatial
            else pd.DataFrame()
        )

        if "value" in individual:
            individual["value"] = numeric(individual["value"])
            individual = individual.dropna(subset=["value"])

        if (
            not individual.empty
            and "region" in individual
            and "value" in individual
        ):
            view = display_frame(individual)
            group = (
                "_area"
                if individual["region"].nunique() == 1 and "_area" in view
                else "region"
            )

            unit = (
                str(individual["units"].iloc[0])
                if "units" in individual
                else "unit not confirmed"
            )

            figure = px.box(
                view,
                x=group,
                y="value",
                points="outliers",
                hover_data=[
                    column
                    for column in ("flight_line", "source_file")
                    if column in view
                ],
                labels={
                    "value": "Coral | " + unit,
                    "region": "Region",
                    "_area": "Survey area",
                },
                color_discrete_sequence=[BENTHIC["coral"]],
            )
            plot(figure)
            insight(
                "Valid individual observations are exported. They may be "
                "regularly sampled and remain in their original unit."
            )
        elif not coral.empty:
            view = display_frame(coral)
            group = (
                "region"
                if "region" in coral and coral["region"].nunique() > 1
                else "_area"
            )
            figure = px.box(
                view,
                x=group,
                y="measure",
                points="all",
                labels={
                    "measure": coral["unit_label"].iloc[0],
                    "_area": "Survey area",
                    "region": "Region",
                },
                color_discrete_sequence=[BENTHIC["coral"]],
            )
            plot(figure)
            insight(
                "This distribution represents flight-level means, "
                "not individual pixels."
            )
        else:
            empty_chart("No coral observations are available for this distribution.")

    with st.expander("View and export data"):
        table(benthic, "reef_composition")


def thermal_panel(noaa, key, title):
    section_header(
        title,
        source_period(noaa, "NOAA daily series", "date"),
        "NOAA",
    )

    if key not in noaa or not noaa[key].notna().any():
        empty_chart(f"{title}: this variable is unavailable in the selected source.")
        return

    figure = px.line(
        noaa.sort_values("date"),
        x="date",
        y=key,
        color="region",
        markers=True,
        labels={
            key: title,
            "date": "Observation date",
            "region": "NOAA region / footprint",
        },
    )
    figure.update_xaxes(tickformat="%d %b %Y")

    if key.startswith("dhw"):
        figure.add_hrect(
            y0=4,
            y1=8,
            fillcolor="#FFF06A",
            opacity=0.08,
            line_width=0,
        )
        for threshold in (4, 8):
            figure.add_hline(
                y=threshold,
                line_dash="dash",
                annotation_text=f"{threshold} °C-weeks reference",
            )

    plot(figure)


def long_term_trends(history):
    section_header(
        "Long-term SST trends",
        "Annual NOAA Sea Surface Temperature (SST) | regional analysis",
        "NOAA",
    )

    if history is None or history.empty:
        st.info(
            "Historical SST data are not available yet. Run the NOAA "
            "historical download command to create noaa_sst_history_daily.csv."
        )
        return

    annual, summary = analyze_sst_history(history)

    if annual.empty:
        st.warning(
            "There is not enough monthly coverage to calculate annual SST means."
        )
        return

    regions = sorted(annual["region"].dropna().unique().tolist())
    selected_regions = st.multiselect(
        "Regions included in the trend chart",
        regions,
        default=regions,
        key="trend_regions",
    )

    selected_annual = annual[
        annual["region"].isin(selected_regions)
    ].copy()

    if selected_annual.empty:
        st.info("Select at least one region to display the annual SST series.")
        return

    figure = px.line(
        selected_annual,
        x="year",
        y="annual_sst_mean",
        color="region",
        markers=True,
        labels={
            "year": "Year",
            "annual_sst_mean": "Annual mean SST (°C)",
            "region": "NOAA region / footprint",
        },
    )

    selected_summary = summary[
        summary["region"].isin(selected_regions)
    ].copy()

    for _, result in selected_summary.iterrows():
        if result["status"] != "Tested":
            continue

        group = selected_annual[
            selected_annual["region"] == result["region"]
        ].sort_values("year")

        if group.empty:
            continue

        x_values = group["year"].astype(float).to_numpy()
        y_values = group["annual_sst_mean"].astype(float).to_numpy()
        slope = float(result["slope_c_per_year"])
        intercept = float(np.median(y_values - slope * x_values))

        figure.add_scatter(
            x=x_values,
            y=slope * x_values + intercept,
            mode="lines",
            name=f"{result['region']} | Theil-Sen fit",
            line={"dash": "dash"},
        )

    plot(figure)

    if not selected_summary.empty:
        display = selected_summary.rename(
            columns={
                "region": "Region",
                "slope_c_per_decade": "Slope (°C/decade)",
                "ci_low_c_per_decade": "95% CI lower",
                "ci_high_c_per_decade": "95% CI upper",
                "kendall_tau": "Kendall tau",
                "p_value": "P-value",
                "q_value": "Adjusted q-value",
                "years": "Valid years",
                "first_year": "First year",
                "last_year": "Last year",
                "significant_fdr": "Significant (FDR)",
                "trend": "Trend",
                "status": "Test status",
            }
        )

        columns = [
            "Region",
            "Slope (°C/decade)",
            "95% CI lower",
            "95% CI upper",
            "Kendall tau",
            "P-value",
            "Adjusted q-value",
            "Valid years",
            "First year",
            "Last year",
            "Significant (FDR)",
            "Trend",
            "Test status",
        ]
        display = display[
            [column for column in columns if column in display]
        ]

        st.subheader("Trend statistics by region")
        st.dataframe(
            display.round(4),
            hide_index=True,
            width="stretch",
        )

        st.download_button(
            "Download annual SST and trend statistics",
            selected_annual.to_csv(index=False).encode("utf-8-sig"),
            "coralwatch_annual_sst_trends.csv",
            "text/csv",
        )

    st.caption(
        "Method: monthly means are calculated from daily regional means. "
        "Months need at least 15 valid daily observations; years need at "
        "least 9 valid months; statistical tests need at least 10 valid years. "
        "Theil-Sen slope is reported in °C per decade. Mann-Kendall p-values "
        "are adjusted across regions using Benjamini-Hochberg. Serial "
        "autocorrelation is not corrected in this exploratory analysis."
    )

    if not selected_summary.empty and (
        selected_summary["status"] == "Insufficient data"
    ).any():
        st.warning(
            "Some regions have fewer than 10 valid annual observations. "
            "Their long-term statistical trend is not evaluated."
        )


def thermal_map(pixels):
    section_header(
        "Thermal map",
        "NOAA pixels from the latest exported observation date.",
        "NOAA",
    )

    available = [
        column
        for column in ("sst", "hotspot", "dhw")
        if column in pixels and pixels[column].notna().any()
    ]

    if not available:
        empty_chart(
            "Thermal pixels are unavailable. The map requires "
            "noaa_latest_map.csv with valid coordinates and measurements."
        )
        return

    labels = {
        "sst": "SST (°C)",
        "hotspot": "HotSpot (°C)",
        "dhw": "DHW (°C-weeks)",
    }

    metric = st.selectbox(
        "Map indicator",
        available,
        format_func=lambda value: labels[value],
    )

    map_chart(pixels, metric)

    dates = (
        pixels["date"].dt.strftime("%Y-%m-%d").dropna().unique()
        if "date" in pixels
        else []
    )
    st.caption("Observation date: " + ", ".join(dates))


def environmental(bundle, noaa, pixels):
    if noaa.empty:
        st.info(
            "Recent NOAA daily observations are unavailable. "
            "Long-term SST analysis can still be displayed when historical "
            "data are present."
        )
    else:
        freshness(noaa)

        thermal_panel(
            noaa,
            "sst_mean",
            "Sea Surface Temperature (SST) | mean (°C)",
        )

        left, right = st.columns(2, gap="large")

        with left:
            thermal_panel(
                noaa,
                "dhw_mean",
                "Mean Degree Heating Weeks (°C-weeks)",
            )

        with right:
            thermal_panel(
                noaa,
                "dhw_max",
                "Maximum Degree Heating Weeks (°C-weeks)",
            )

        st.caption(
            "The 4 and 8 °C-weeks reference levels indicate accumulated "
            "thermal stress. They are not diagnoses of individual coral mortality."
        )

        with st.expander("SST anomaly and HotSpot"):
            thermal_panel(
                noaa,
                "anomaly_mean",
                "Mean SST anomaly (°C)",
            )
            thermal_panel(
                noaa,
                "hotspot_mean",
                "Mean Coral Bleaching HotSpot (°C)",
            )

        latest = latest_by_region(noaa)
        section_header(
            "Latest observation by NOAA footprint",
            "Means and maxima are kept separate; each region retains its own date.",
            "NOAA",
        )
        if not latest.empty:
            st.dataframe(
                recent_table(latest),
                hide_index=True,
                width="stretch",
            )

    st.divider()
    long_term_trends(bundle.get("history", pd.DataFrame()))
    st.divider()
    thermal_map(pixels)

    if not noaa.empty:
        with st.expander("View and export data"):
            latest = latest_by_region(noaa)
            st.write("Latest observation by NOAA region")
            table(recent_table(latest), "latest_environmental")

            st.write("Complete daily time series")
            table(noaa, "environmental_timeseries")


def warning_page(bundle, noaa, pixels):
    freshness(noaa if not noaa.empty else pixels)
    latest = latest_by_region(noaa)

    regional = (
        bundle.get("regional", False)
        and not latest.empty
        and "baa" in latest
    )

    if regional:
        alerts = latest.copy()
        counts = alerts["baa"].value_counts()
        st.caption(
            f"{len(alerts)} NOAA regions / footprints identified. "
            "Each uses its latest available date in the selected period."
        )
    elif not pixels.empty and "baa" in pixels:
        alerts = pixels[pixels["baa"].notna()].copy()
        counts = alerts["baa"].value_counts()
        st.caption(
            f"Denominator: {len(alerts)} valid ocean pixels, not affected reefs. "
            f"Observation date: {pixels['date'].max():%Y-%m-%d}."
        )
    else:
        alerts = pd.DataFrame()
        counts = pd.Series(dtype=float)
        st.info(
            "No dated regional BAA classification or pixel data are available. "
            "Missing data do not mean No Stress."
        )

    section_header(
        "Bleaching status by NOAA footprint",
        "Source-provided Bleaching Alert Area (7-day maximum).",
        "NOAA",
    )

    if regional:
        thermal_status(
            latest.sort_values("baa", ascending=False, na_position="last"),
            inline=True,
        )

    st.caption(
        "HotSpot is measured in °C; DHW is measured in °C-weeks. "
        "These indicators provide context and do not recalculate BAA."
    )

    if not alerts.empty:
        alerts["Alert level"] = alerts["baa"].map(label)
        columns = [
            column
            for column in (
                "region",
                "date",
                "baa",
                "Alert level",
                "hotspot_mean",
                "hotspot_max",
                "dhw_mean",
                "dhw_max",
            )
            if column in alerts
        ]

        st.dataframe(
            alerts[columns].rename(
                columns={
                    "region": "NOAA region / footprint",
                    "date": "Observation date",
                    "baa": "BAA code",
                    "hotspot_mean": "Mean HotSpot (°C)",
                    "hotspot_max": "Maximum HotSpot (°C)",
                    "dhw_mean": "Mean DHW (°C-weeks)",
                    "dhw_max": "Maximum DHW (°C-weeks)",
                }
            ),
            hide_index=True,
            width="stretch",
        )

    st.subheader("BAA levels")

    descriptions = {
        0: "No stress indicated by the source classification",
        1: "Bleaching watch",
        2: "Bleaching warning",
        3: "Alert level 1",
        4: "Alert level 2",
    }

    columns = st.columns(5)
    for index, (code, name) in enumerate(ALERTS.items()):
        count = int(counts.get(code, 0)) if not alerts.empty else "—"
        with columns[index]:
            alert_card(
                code,
                name,
                count,
                descriptions[code],
            )

    section_header(
        "Bleaching alert map",
        "NOAA 7-day maximum BAA classification.",
        "NOAA",
    )

    if not pixels.empty and "baa" in pixels:
        map_chart(pixels, "baa", True)
    elif regional:
        geometry = bundle.get("raw", {}).get(
            "noaa_spatial_summary.csv",
            pd.DataFrame(),
        )

        bounds = [
            column
            for column in (
                "latitude_min",
                "latitude_max",
                "longitude_min",
                "longitude_max",
            )
            if column in geometry
        ]

        if "region" in geometry and bounds:
            mapped = latest.merge(
                geometry[["region"] + bounds],
                on="region",
                how="left",
                validate="one_to_one",
            )
            map_chart(bounds_points(mapped), "baa", True)
            st.caption(
                "Approximate centroids of NOAA regional boundaries. "
                "The alert level and date come from the daily series."
            )
        else:
            empty_chart(
                "Valid pixel coordinates or regional boundaries are required."
            )
    else:
        empty_chart("No compatible NOAA geometry is available.")

    with st.expander("View and export alert data"):
        if not alerts.empty:
            table(alerts, "early_warning")


def render_page(index):
    bundle, catalog, benthic, full, spatial, noaa, pixels = (
        st.session_state["_cw_context"]
    )

    hero(
        "CoralWatch" if index == 0 else PAGES[index],
        "Historical reef composition and recent thermal context",
    )

    if not bundle["raw"]:
        st.info(
            "No processed CSV files were found in data/processed/. "
            "Place the processed NASA and/or NOAA files in that folder."
        )

    if index == 0:
        overview(bundle, catalog, benthic, full, spatial, noaa, pixels)
    elif index == 1:
        composition(bundle, catalog, benthic, full, spatial)
    elif index == 2:
        environmental(bundle, noaa, pixels)
    else:
        warning_page(bundle, noaa, pixels)

    st.caption(NOTICE)
    methodology(bundle)


def main():
    apply_theme()

    st.sidebar.title("CoralWatch")
    st.sidebar.caption(
        "Historical reef composition and recent thermal context"
    )

    page_files = [
        "1_Overview.py",
        "2_Reef_Composition.py",
        "3_Environmental_Monitoring.py",
        "4_Early_Warning.py",
    ]

    page_dir = Path(__file__).resolve().parents[1] / "pages"

    navigation = st.navigation(
        [
            st.Page(page_dir / filename, title=title)
            for filename, title in zip(page_files, PAGES)
        ]
    )

    if st.sidebar.button("Refresh cached data", width="stretch"):
        st.cache_data.clear()

    bundle = load_bundle()
    st.session_state["_cw_area_labels"] = area_labels(bundle["catalog"])

    filtered = render_filters(bundle)
    st.session_state["_cw_context"] = (bundle, *filtered)

    navigation.run()


from core.data import load_bundle
