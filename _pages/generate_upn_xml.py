from io import BytesIO
import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET


def convert(df):
    # Create the root of the XML document
    root = ET.Element('ArrayOfUPN')
    root.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    root.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')

    # Iterate over each row in the DataFrame
    for _, row in df.iterrows():
        # Create an element for this row
        row_element = ET.SubElement(root, 'UPN')

        # Add each column as a child element of the row
        for col in df.columns:
            col_element = ET.SubElement(row_element, col)
            col_value = row[col]

            # Check if the value is NaN
            if pd.isna(col_value):
                # Write a closing tag without any value
                col_element.text = None
            else:
                # Write the actual value
                col_element.text = str(col_value).lower() if isinstance(col_value, bool) else str(col_value)

    # Convert the ElementTree to a string
    xml_data = ET.tostring(root, encoding='utf-16')

    xml_file = BytesIO()
    xml_file.write(xml_data)
    return xml_file


def main():
    st.set_page_config(layout="wide")

    st.subheader("Generate UPN XML")

    uploaded_file = st.file_uploader(label="Upload file", type=["xlsx"])

    if uploaded_file is not None:
        # Read file
        converters = {'DobroSklic': str, 'RokPlacila': str}
        df = pd.read_excel(uploaded_file, converters=converters)

        # Convert RokPlacila string to date
        df['RokPlacila'] = pd.to_datetime(df['RokPlacila'], format='%d.%m.%Y').dt.strftime('%d.%m.%Y')

        # Create a text input for filtering
        query = st.text_input("Filter")

        # Apply the filter if the user entered a query
        if query:
            mask = df.applymap(lambda x: query.lower() in str(x).lower()).any(axis=1)
            df = df[mask]

        # Display the imported data
        edited_df = st.data_editor(df, hide_index=True, height=470)

        st.download_button("Download XML", type='primary', data=convert(edited_df), file_name='book_import.xml', mime='application/xml')

main()