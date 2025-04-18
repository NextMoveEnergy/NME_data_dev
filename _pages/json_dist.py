import streamlit as st
import zipfile
from pandas import json_normalize, to_datetime, DataFrame, read_excel, MultiIndex, concat, ExcelWriter
import traceback
from json import load
from io import BytesIO

distribucije = {
    2: "2_Elektro_Celje",
    3: "3_Elektro_Ljubljana",
    4: "4_Elektro_Maribor",
    6: "6_Elektro_Gorenjska",
    7: "7_Elektro_Primorska"
}

missing_data = []


def get_dist_for_metering_point(metering_point, dobava_mt_df, odkup_mt_df, podpora_mt_df):
    df_dict = {"dobava": dobava_mt_df, "odkup": odkup_mt_df, "podpora": podpora_mt_df}

    for tip, df in df_dict.items():
        try:
            value = df.loc[df["merilna_tocka"] == metering_point, 'distribucija'].iloc[0]
            naziv_placnika = df.loc[df["merilna_tocka"] == metering_point, 'naziv_placnika'].iloc[0]
            return value, tip, naziv_placnika
        except IndexError:
            continue

    return -1, "", ""


def merge_to_dist_dfs(dataframes, mt_dist_file):
    df_dict_dobava = {
        2: DataFrame(),
        3: DataFrame(),
        4: DataFrame(),
        6: DataFrame(),
        7: DataFrame()
    }

    df_dict_odkup = {
        2: DataFrame(),
        3: DataFrame(),
        4: DataFrame(),
        6: DataFrame(),
        7: DataFrame()
    }

    df_dict_podpora = {
        2: DataFrame(),
        3: DataFrame(),
        4: DataFrame(),
        6: DataFrame(),
        7: DataFrame()
    }

    dobava_mt_df = read_excel(mt_dist_file, sheet_name='dobava')
    odkup_mt_df = read_excel(mt_dist_file, sheet_name='odkup')
    podpora_mt_df = read_excel(mt_dist_file, sheet_name='obratovalna_podpora')

    dobava_mt_df['merilna_tocka'] = dobava_mt_df['merilna_tocka'].astype(str)
    odkup_mt_df['merilna_tocka'] = odkup_mt_df['merilna_tocka'].astype(str)
    podpora_mt_df['merilna_tocka'] = podpora_mt_df['merilna_tocka'].astype(str)

    for df in dataframes:
        metering_point = df.columns[0]  # Get column name that is MT

        dist, tip, naziv_placnika = get_dist_for_metering_point(metering_point, dobava_mt_df, odkup_mt_df,
                                                                podpora_mt_df)
        if dist == -1:
            print("INFO: Could not find distribution for " + metering_point + ".")
            continue

        df.columns = MultiIndex.from_tuples([(naziv_placnika, df.columns[0])])

        match tip:
            case "dobava":
                df_dict_dobava[dist] = concat([df_dict_dobava[dist], df]).sort_values('timestamp')
            case "odkup":
                df_dict_odkup[dist] = concat([df_dict_odkup[dist], df]).sort_values('timestamp')
            case "podpora":
                df_dict_podpora[dist] = concat([df_dict_podpora[dist], df]).sort_values('timestamp')

    return df_dict_dobava, df_dict_odkup, df_dict_podpora


def create_df_from_mq_json(meter_reading, interval_readings):
    for reading in interval_readings:
        if len(reading.get('readingQualities')) != 0:
            missing_data.append(meter_reading['usagePoint'])
            break

    df = json_normalize(interval_readings)
    df = df[['timestamp', 'value']]
    # df.attrs['messageType'] = meter_reading['messageType']
    df.attrs['messageCreated'] = meter_reading['messageCreated']
    df['timestamp'] = to_datetime(df['timestamp'])
    df['timestamp'] = df['timestamp'].dt.tz_localize(None)
    df.set_index('timestamp', inplace=True)
    df.rename(columns={'value': meter_reading['usagePoint']}, inplace=True)
    return df


def get_dataframes_mq_json(readings):
    dataframes = []
    for data in readings.values():
        meter_readings = data['meterReadings']
        for meter_reading in meter_readings:
            try:
                interval_readings = meter_reading['intervalBlocks'][0]['intervalReadings']
            except IndexError:
                st.write("INFO: Empty interval readings for " + meter_reading['usagePoint'] + ".")
                continue
            df = create_df_from_mq_json(meter_reading, interval_readings)
            if df is not None:
                dataframes.append(df)
    return dataframes


def get_dataframes_ceeps_json(readings):
    dataframes = []
    for meter_reading in readings.values():
        for idx, intervalBlock in enumerate(meter_reading['intervalBlocks']):
            try:
                interval_readings = meter_reading['intervalBlocks'][idx]['intervalReadings']
            except IndexError:
                st.write("INFO: Empty interval readings for " + meter_reading['usagePoint'] + ".")
                continue
            # Use code from MQ because it is the same from this point forward
            df = create_df_from_mq_json(meter_reading, interval_readings)
            if df is not None:
                dataframes.append(df)

    return dataframes


def save_distributions(df_dict_dobava, df_dict_odkup, df_dict_podpora):
    # Initialize a BytesIO object for the zip file
    zip_io = BytesIO()

    # Initialize a ZipFile object
    with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        data_and_names = [
            (df_dict_dobava, 'Odjem.xlsx'),
            (df_dict_odkup, 'Oddaja.xlsx'),
            (df_dict_podpora, 'Obratovalna_podpora.xlsx')
        ]

        for df_dict, excel_filename in data_and_names:
            if all(df.empty for df in df_dict.values()):
                continue

            try:
                output = BytesIO()

                with ExcelWriter(output, engine='xlsxwriter') as writer:
                    for key in df_dict:
                        if df_dict[key].empty:
                            continue

                        # Sort columns and group by 'timestamp'
                        df_dict[key] = df_dict[key].reindex(sorted(df_dict[key].columns), axis=1)
                        df_dict[key] = df_dict[key].groupby('timestamp').sum().reset_index(col_level=1)

                        sheet_name = distribucije[key]

                        # Write each key as a separate sheet in the Excel file
                        df_dict[key].to_excel(writer, sheet_name=sheet_name)

                        writer.sheets[sheet_name].set_row(2, None, None, {'hidden': True})

                        writer.sheets[sheet_name].autofit()
                        writer.sheets[sheet_name].set_column_pixels(1, 1, 130)

                        writer.sheets[sheet_name].set_selection(3, 2, 3, 2)

                output.seek(0)

                # Add the Excel file to the zip file
                zip_file.writestr(excel_filename, output.getvalue())

            except Exception as e:
                traceback.print_exc()
                print(f"ERROR - Could not write: {excel_filename}")

    # Move the file pointer of the zip file back to the start
    zip_io.seek(0)

    # Create a download button for the zip file
    st.download_button(label="Download", data=zip_io, file_name='files.zip', mime='application/zip', key='zip_file')


def main():
    st.set_page_config(layout="centered")

    st.subheader("Json to distributions")

    uploaded_files = st.file_uploader(label="Upload files", type=["json"], accept_multiple_files=True)

    filetype = st.selectbox("Choose the format of the uploaded files", ('CEEPS', 'MQ'))

    mt_dist_file = st.file_uploader(label="Upload mt_dist file", type=["xlsx"])

    if uploaded_files is not None:
        if st.button('Merge to distributions', type='primary'):
            # Initialize an empty dictionary
            data = {}

            # Iterate over the uploaded files
            for uploaded_file in uploaded_files:
                # Load the file content
                json_data = load(uploaded_file)

                # Get the filename without extension
                filename_without_extension = uploaded_file.name.split(".")[0]

                # Add the file content to the dictionary
                data[filename_without_extension] = json_data

            if data is not None:
                if filetype == "CEEPS":
                    dataframes = get_dataframes_ceeps_json(data)
                else:
                    dataframes = get_dataframes_mq_json(data)

                df_dict_dobava, df_dict_odkup, df_dict_podpora = merge_to_dist_dfs(dataframes, mt_dist_file)

                save_distributions(df_dict_dobava, df_dict_odkup, df_dict_podpora)

                st.dataframe(missing_data)

main()
