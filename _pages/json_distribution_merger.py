import json
import zipfile
from collections import defaultdict
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st


DISTRIBUTIONS = {
    2: "2_Elektro_Celje",
    3: "3_Elektro_Ljubljana",
    4: "4_Elektro_Maribor",
    6: "6_Elektro_Gorenjska",
    7: "7_Elektro_Primorska",
}

REFERENCE_SHEETS = {
    "dobava": "Supply",
    "odkup": "Purchase",
    "obratovalna_podpora": "Operating support",
}

REQUIRED_REFERENCE_COLUMNS = {
    "merilna_tocka",
    "distribucija",
    "naziv_placnika",
}


class ProcessingError(Exception):
    pass


def normalize_metering_point(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_reference_data(uploaded_file) -> dict[str, tuple[int, str, str]]:
    try:
        workbook = pd.ExcelFile(uploaded_file)
    except Exception as exc:
        raise ProcessingError(f"Could not open the reference Excel file: {exc}") from exc

    missing_sheets = [
        sheet for sheet in REFERENCE_SHEETS if sheet not in workbook.sheet_names
    ]
    if missing_sheets:
        raise ProcessingError(
            "The reference Excel file is missing required sheet(s): "
            + ", ".join(missing_sheets)
        )

    lookup: dict[str, tuple[int, str, str]] = {}
    duplicates: set[str] = set()

    for sheet_name in REFERENCE_SHEETS:
        try:
            df = pd.read_excel(workbook, sheet_name=sheet_name)
        except Exception as exc:
            raise ProcessingError(
                f"Could not read sheet '{sheet_name}': {exc}"
            ) from exc

        missing_columns = REQUIRED_REFERENCE_COLUMNS.difference(df.columns)
        if missing_columns:
            raise ProcessingError(
                f"Sheet '{sheet_name}' is missing required column(s): "
                + ", ".join(sorted(missing_columns))
            )

        subset = df[
            ["merilna_tocka", "distribucija", "naziv_placnika"]
        ].copy()

        subset["merilna_tocka"] = (
            subset["merilna_tocka"]
            .astype(str)
            .str.strip()
        )

        for row in subset.itertuples(index=False):
            metering_point = normalize_metering_point(row.merilna_tocka)
            if not metering_point or metering_point.lower() == "nan":
                continue

            try:
                distribution = int(row.distribucija)
            except (TypeError, ValueError):
                continue

            if distribution not in DISTRIBUTIONS:
                continue

            payer = "" if pd.isna(row.naziv_placnika) else str(row.naziv_placnika).strip()

            if metering_point in lookup:
                duplicates.add(metering_point)
                continue

            lookup[metering_point] = (
                distribution,
                sheet_name,
                payer,
            )

    if not lookup:
        raise ProcessingError(
            "No usable metering-point mappings were found in the reference file."
        )

    if duplicates:
        st.warning(
            f"{len(duplicates)} duplicate metering-point mapping(s) were found in "
            "the reference workbook. The first occurrence is used."
        )

    return lookup


def iter_meter_readings(payload: Any, file_type: str):
    if file_type == "MQ":
        if not isinstance(payload, dict):
            raise ProcessingError("MQ JSON root must be an object.")

        meter_readings = payload.get("meterReadings")
        if not isinstance(meter_readings, list):
            raise ProcessingError("MQ JSON does not contain a 'meterReadings' list.")

        for meter_reading in meter_readings:
            if isinstance(meter_reading, dict):
                yield meter_reading
        return

    if isinstance(payload, dict) and isinstance(payload.get("meterReadings"), list):
        for meter_reading in payload["meterReadings"]:
            if isinstance(meter_reading, dict):
                yield meter_reading
        return

    if isinstance(payload, dict) and "usagePoint" in payload:
        yield payload
        return

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "usagePoint" in item:
                yield item
        return

    raise ProcessingError(
        "CEEPS JSON structure is not recognized. Expected a meter-reading object "
        "or an object containing 'meterReadings'."
    )


def extract_series_from_meter_reading(
    meter_reading: dict[str, Any],
) -> tuple[str, list[pd.Series], bool]:
    metering_point = normalize_metering_point(meter_reading.get("usagePoint"))
    if not metering_point:
        raise ProcessingError("Meter reading is missing 'usagePoint'.")

    interval_blocks = meter_reading.get("intervalBlocks")
    if not isinstance(interval_blocks, list) or not interval_blocks:
        return metering_point, [], False

    series_list: list[pd.Series] = []
    has_quality_flags = False

    for block in interval_blocks:
        if not isinstance(block, dict):
            continue

        readings = block.get("intervalReadings")
        if not isinstance(readings, list) or not readings:
            continue

        timestamps = []
        values = []

        for reading in readings:
            if not isinstance(reading, dict):
                continue

            timestamp = reading.get("timestamp")
            value = reading.get("value")

            if timestamp is None or value is None:
                continue

            qualities = reading.get("readingQualities")
            if isinstance(qualities, list) and qualities:
                has_quality_flags = True

            timestamps.append(timestamp)
            values.append(value)

        if not timestamps:
            continue

        parsed_timestamps = pd.to_datetime(
            timestamps,
            errors="coerce",
            utc=True,
        )

        numeric_values = pd.to_numeric(
            pd.Series(values, dtype="object"),
            errors="coerce",
        )

        valid_mask = (~parsed_timestamps.isna()) & (~numeric_values.isna())
        if not valid_mask.any():
            continue

        index = pd.DatetimeIndex(parsed_timestamps[valid_mask]).tz_convert(None)
        series = pd.Series(
            numeric_values[valid_mask].to_numpy(),
            index=index,
            dtype="float64",
        )

        if series.index.has_duplicates:
            series = series.groupby(level=0).sum()

        series_list.append(series)

    return metering_point, series_list, has_quality_flags


def add_meter_series(
    storage: dict[
        tuple[str, int],
        dict[tuple[str, str], list[pd.Series]],
    ],
    category: str,
    distribution: int,
    payer: str,
    metering_point: str,
    series_list: list[pd.Series],
) -> None:
    key = (category, distribution)
    column_key = (payer, metering_point)
    storage[key][column_key].extend(series_list)


def build_distribution_dataframe(
    columns: dict[tuple[str, str], list[pd.Series]],
) -> pd.DataFrame:
    output_series = []

    for column_key, parts in columns.items():
        if not parts:
            continue

        if len(parts) == 1:
            series = parts[0]
        else:
            series = pd.concat(parts, axis=0)
            if series.index.has_duplicates:
                series = series.groupby(level=0).sum()

        series = series.sort_index()
        series.name = column_key
        output_series.append(series)

    if not output_series:
        return pd.DataFrame()

    df = pd.concat(output_series, axis=1)
    df.columns = pd.MultiIndex.from_tuples(
        df.columns,
        names=["Payer", "Metering point"],
    )
    df = df.sort_index()
    df = df.reindex(sorted(df.columns), axis=1)
    df.index.name = "timestamp"
    return df


def write_excel_to_bytes(
    storage: dict[
        tuple[str, int],
        dict[tuple[str, str], list[pd.Series]],
    ],
    category: str,
) -> bytes | None:
    category_has_data = any(
        key_category == category and columns
        for (key_category, _), columns in storage.items()
    )
    if not category_has_data:
        return None

    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book
        header_format = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "border": 1,
            }
        )
        timestamp_format = workbook.add_format(
            {"num_format": "yyyy-mm-dd hh:mm:ss"}
        )

        for distribution, sheet_name in DISTRIBUTIONS.items():
            columns = storage.get((category, distribution))
            if not columns:
                continue

            df = build_distribution_dataframe(columns)
            if df.empty:
                continue

            df.to_excel(
                writer,
                sheet_name=sheet_name,
                merge_cells=True,
            )

            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(3, 1)
            worksheet.set_column(0, 0, 20, timestamp_format)

            max_data_columns = len(df.columns)
            if max_data_columns:
                worksheet.set_column(1, max_data_columns, 16)

            worksheet.set_row(0, 22, header_format)
            worksheet.set_row(1, 22, header_format)
            worksheet.set_selection(3, 1, 3, 1)

    output.seek(0)
    return output.getvalue()


def create_output_zip(
    storage: dict[
        tuple[str, int],
        dict[tuple[str, str], list[pd.Series]],
    ],
) -> bytes:
    files = {
        "dobava": "Supply.xlsx",
        "odkup": "Purchase.xlsx",
        "obratovalna_podpora": "Operating_support.xlsx",
    }

    zip_buffer = BytesIO()

    with zipfile.ZipFile(
        zip_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        written_files = 0

        for category, filename in files.items():
            excel_bytes = write_excel_to_bytes(storage, category)
            if excel_bytes:
                archive.writestr(filename, excel_bytes)
                written_files += 1

    if written_files == 0:
        raise ProcessingError("No output files could be generated.")

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def process_files(
    uploaded_files,
    file_type: str,
    reference_lookup: dict[str, tuple[int, str, str]],
):
    storage = defaultdict(lambda: defaultdict(list))

    missing_mapping: set[str] = set()
    quality_flags: set[str] = set()
    empty_readings: set[str] = set()
    file_errors: list[dict[str, str]] = []

    processed_files = 0
    processed_meter_readings = 0
    matched_meter_readings = 0
    interval_series_count = 0

    total_files = len(uploaded_files)
    progress = st.progress(0)
    status = st.empty()

    for file_index, uploaded_file in enumerate(uploaded_files, start=1):
        status.info(
            f"Processing file {file_index} of {total_files}: {uploaded_file.name}"
        )

        try:
            uploaded_file.seek(0)
            payload = json.load(uploaded_file)

            for meter_reading in iter_meter_readings(payload, file_type):
                processed_meter_readings += 1

                try:
                    metering_point, series_list, has_quality = (
                        extract_series_from_meter_reading(meter_reading)
                    )
                except ProcessingError as exc:
                    file_errors.append(
                        {
                            "File": uploaded_file.name,
                            "Error": str(exc),
                        }
                    )
                    continue

                if has_quality:
                    quality_flags.add(metering_point)

                if not series_list:
                    empty_readings.add(metering_point)
                    continue

                mapping = reference_lookup.get(metering_point)
                if mapping is None:
                    missing_mapping.add(metering_point)
                    continue

                distribution, category, payer = mapping

                add_meter_series(
                    storage=storage,
                    category=category,
                    distribution=distribution,
                    payer=payer,
                    metering_point=metering_point,
                    series_list=series_list,
                )

                matched_meter_readings += 1
                interval_series_count += len(series_list)

            processed_files += 1

        except json.JSONDecodeError as exc:
            file_errors.append(
                {
                    "File": uploaded_file.name,
                    "Error": (
                        f"Invalid JSON at line {exc.lineno}, column {exc.colno}: "
                        f"{exc.msg}"
                    ),
                }
            )
        except ProcessingError as exc:
            file_errors.append(
                {
                    "File": uploaded_file.name,
                    "Error": str(exc),
                }
            )
        except Exception as exc:
            file_errors.append(
                {
                    "File": uploaded_file.name,
                    "Error": f"Unexpected processing error: {exc}",
                }
            )

        progress.progress(file_index / total_files)

    status.info("Building Excel workbooks and ZIP archive...")

    if matched_meter_readings == 0:
        progress.empty()
        status.empty()
        raise ProcessingError(
            "No meter readings matched the reference workbook. "
            "No output was generated."
        )

    zip_bytes = create_output_zip(storage)

    progress.progress(1.0)
    status.empty()

    summary = {
        "files": processed_files,
        "meter_readings": processed_meter_readings,
        "matched": matched_meter_readings,
        "series": interval_series_count,
        "missing_mapping": sorted(missing_mapping),
        "quality_flags": sorted(quality_flags),
        "empty_readings": sorted(empty_readings),
        "errors": file_errors,
    }

    return zip_bytes, summary


def render_summary(summary: dict[str, Any]) -> None:
    st.subheader("Processing summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Files processed", summary["files"])
    col2.metric("Meter readings", summary["meter_readings"])
    col3.metric("Matched readings", summary["matched"])
    col4.metric("Data blocks", summary["series"])

    missing_mapping = summary["missing_mapping"]
    quality_flags = summary["quality_flags"]
    empty_readings = summary["empty_readings"]
    errors = summary["errors"]

    if missing_mapping:
        with st.expander(
            f"Metering points not found in reference file ({len(missing_mapping)})"
        ):
            st.dataframe(
                pd.DataFrame({"Metering point": missing_mapping}),
                use_container_width=True,
                hide_index=True,
            )

    if quality_flags:
        with st.expander(
            f"Metering points with reading-quality flags ({len(quality_flags)})"
        ):
            st.dataframe(
                pd.DataFrame({"Metering point": quality_flags}),
                use_container_width=True,
                hide_index=True,
            )

    if empty_readings:
        with st.expander(
            f"Metering points with no usable interval readings ({len(empty_readings)})"
        ):
            st.dataframe(
                pd.DataFrame({"Metering point": empty_readings}),
                use_container_width=True,
                hide_index=True,
            )

    if errors:
        with st.expander(f"File / data errors ({len(errors)})", expanded=True):
            st.dataframe(
                pd.DataFrame(errors),
                use_container_width=True,
                hide_index=True,
            )


def main():
    st.set_page_config(
        page_title="JSON Distribution Merger",
        layout="wide",
    )

    st.title("JSON Distribution Merger")
    st.caption(
        "Match CEEPS or MQ meter-reading JSON files to distribution metadata "
        "and export grouped Excel workbooks."
    )

    with st.sidebar:
        st.subheader("Input settings")

        file_type = st.selectbox(
            "JSON format",
            ("CEEPS", "MQ"),
        )

        st.info(
            "Files are processed sequentially to reduce memory usage. "
            "Large batches can therefore be handled more reliably."
        )

    uploaded_files = st.file_uploader(
        "Upload JSON files",
        type=["json"],
        accept_multiple_files=True,
        help="You can upload a large batch of meter-reading JSON files.",
    )

    reference_file = st.file_uploader(
        "Upload distribution reference workbook",
        type=["xlsx"],
        help=(
            "Required sheets: dobava, odkup, obratovalna_podpora. "
            "Required columns: merilna_tocka, distribucija, naziv_placnika."
        ),
    )

    if not uploaded_files or reference_file is None:
        st.info(
            "Upload JSON files and the distribution reference workbook to continue."
        )
        return

    st.write(
        f"Ready to process **{len(uploaded_files)} JSON file"
        f"{'s' if len(uploaded_files) != 1 else ''}**."
    )

    if st.button(
        "Process and merge",
        type="primary",
        use_container_width=True,
    ):
        st.session_state.pop("json_distribution_zip", None)
        st.session_state.pop("json_distribution_summary", None)

        try:
            with st.spinner("Loading distribution reference data..."):
                reference_lookup = load_reference_data(reference_file)

            zip_bytes, summary = process_files(
                uploaded_files=uploaded_files,
                file_type=file_type,
                reference_lookup=reference_lookup,
            )

            st.session_state["json_distribution_zip"] = zip_bytes
            st.session_state["json_distribution_summary"] = summary

            st.success(
                "Processing completed successfully. "
                "The ZIP archive is ready for download."
            )

        except ProcessingError as exc:
            st.error(str(exc))
        except MemoryError:
            st.error(
                "The server ran out of memory while processing the batch. "
                "Try splitting the upload into smaller groups or increasing "
                "the Streamlit instance memory."
            )
        except Exception as exc:
            st.error(
                "An unexpected error occurred while processing the files: "
                f"{exc}"
            )

    summary = st.session_state.get("json_distribution_summary")
    if summary:
        render_summary(summary)

    zip_bytes = st.session_state.get("json_distribution_zip")
    if zip_bytes:
        st.download_button(
            "Download merged Excel files",
            data=zip_bytes,
            file_name="distribution_meter_readings.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )


main()
