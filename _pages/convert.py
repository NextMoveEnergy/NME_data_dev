import streamlit as st
import pandas as pd
import json
import _pages.mqdata as mqdata
import _pages.ceepsdata as ceepsdata

reading_types = {
    "0.0.2.4.1.2.12.0.0.0.0.0.0.0.0.3.72.0": "delovna_prejem",
    "0.0.2.4.19.2.12.0.0.0.0.0.0.0.0.3.72.0": "delovna_oddaja",
    "Unknown": "Unknown"
}

reading_qualities = {
    "1.4.0": "Obračunski reset",
    "1.4.9": "Premik / sprememba časa",
    "1.1.7": "Usodna napaka",
    "1.5.257": "Napačen podatek",
    "1.5.259": "Neprebran podatek",
    "1.2.32": "Izpad napetosti / Povrnitev napetosti",
    "3.10.1": "Sprememba vrednosti",
    "1.4.8": "Izbris pomnilnika",
    "1.4.6": "Sprememba parametrov v števcu",
    "1.8.0": "Uvoženi podatki",
    "1.4.131": "Podatki iz ročnih terminalov",
    "3.0.0": "Merjena vrednost",
    "3.8.1": "Končno ocenjena vrednost",
    "3.8.0": "Ocenjena vrednost",
    "3.5.259": "Manjkajoča vrednost",
    "3.7.3": "Zavrnjena vrednost",
    "3.10.0": "Začasna vrednost"
}


def convert_ceepsdata(ceepsdata):
    # Convert all interval readings to dataframes
    intervals = list()
    for data in ceepsdata:
        for interval_block in data.intervalBlocks:
            df = pd.DataFrame([(ir.timestamp, ir.value, [reading_qualities[rq.readingQualityType] for rq in ir.readingQualities]) for ir in interval_block.intervalReadings])
            df.columns = ['timestamp', reading_types[interval_block.readingType], 'readingQualities']

            df.attrs['messageType'] = data.messageType
            df.attrs['usagePoint'] = data.usagePoint
            df.attrs['readingType'] = interval_block.readingType
            df.attrs['messageCreated'] = data.messageCreated

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['timestamp'] = df['timestamp'].dt.tz_localize(None)
            df.set_index('timestamp', inplace=True)

            intervals.append(df)

    # Merge interval readings
    pass


def main():
    uploaded_files = st.file_uploader("Upload JSON files", accept_multiple_files=True, type=['json'])

    filetype = st.selectbox("Choose the format of the uploaded files", ('MQ', 'CEEPS'))

    if st.button("Convert"):
        match filetype:
            case "MQ":
                mqdata_object = [json.load(f, object_hook=mqdata.object_hook) for f in uploaded_files]
            case "CEEPS":
                ceepsdata_object = [json.load(f, object_hook=ceepsdata.object_hook) for f in uploaded_files]
                data = convert_ceepsdata(ceepsdata_object)


if __name__ == "__main__":
    main()
