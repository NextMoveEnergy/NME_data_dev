import streamlit as st

pg = st.navigation([
    st.Page('_pages/generate_upn_xml.py', title="Generate UPN XML"),
    st.Page('_pages/retreive_meter_readings.py', title="Meter readings"),
    st.Page('_pages/retreive_meter_readings_small_batch.py', title="Meter readings SMALL BATCH"),
    st.Page('_pages/priloga_a.py', title="Priloga A 2.6"),
    st.Page('_pages/priloga_b.py', title="Priloga A 2.7"),
    #st.Page('_pages/priloga_c.py', title="Priloga A 2.7.5
    st.Page('_pages/priloga_2.7.1.py', title="Priloga A 2.7.1 - 2000OVE&SPTE"),
    st.Page('_pages/priloga_2.7_obvestilo.py', title="Priloga A 2.7 - Obvestilo"),
    st.Page('_pages/priloga_2.7_presezena_moc.py', title="Priloga A 2.7 - Presežena moč"),
    st.Page('_pages/json_dist.py', title="Json to distribution"),
    #st.Page('_pages/mojelektro_client.py', title="Moj Elektro"),
])

pg.run()