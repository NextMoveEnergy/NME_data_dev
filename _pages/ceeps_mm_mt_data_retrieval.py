import json
import math
import zipfile
import pandas as pd
import streamlit as st
import requests
import base64
from io import BytesIO
import streamlit as st

def main():
    st.set_page_config(layout="centered")
    st.title("Zahteva za podatke MT/MM meritev")

    # --- Podatki o merilni točki ---
    st.subheader("Podatki o merilni točki")
    gsrn_mt = st.text_input("GSNR MT", "483111589999999999")

    # --- Podatki o plačniku / prodajalcu ---
    st.subheader("Podatki o plačniku / prodajalcu")
    naziv = st.text_input("Naziv", "JANEZ NOVAK")
    ulica = st.text_input("Ulica", "KRATKA ULICA")
    hisna_stevilka = st.text_input("Hišna številka", "345")
    postna_stevilka = st.text_input("Poštna številka", "9220")
    posta = st.text_input("Pošta", "DOLGA VAS")
    davcni_zavezanec = st.checkbox("Davčni zavezanec", value=False)
    davcna_stevilka = st.text_input("Davčna številka", "11111119")

    # --- Pooblastilo ---
    ima_pooblastilo = st.checkbox("Ima veljavno pooblastilo za pridobivanje podatkov?", value=True)

    # --- Priloga ---
    st.subheader("Priloga (PDF)")
    uploaded_file = st.file_uploader("Naloži PDF datoteko", type="pdf")
    vrsta_dokumenta = st.selectbox(
        "Vrsta dokumenta",
        (
            "POOBLASTILO_ZA_PRIDOBITEV_MERILNIH_PODATKOV",
            "VLOGA_ZA_PRIKLJUCITEV_IN_DOSTOP_DO_OMREZJA",
            "DRUGA"
        )
    )

    if uploaded_file is not None:
        file_content = uploaded_file.read()
        encoded_file = base64.b64encode(file_content).decode("utf-8")
        file_name = uploaded_file.name

    # --- Pošlji zahtevo ---
    if st.button("Pošlji zahtevo"):
        if uploaded_file is None:
            st.error("⚠️ Naloži PDF datoteko!")
            return

        body = {
            "gsrnMT": gsrn_mt,
            "placnikAliProdajalec": {
                "naziv": naziv,
                "ulica": ulica,
                "hisnaStevilka": hisna_stevilka,
                "postnaStevilka": postna_stevilka,
                "posta": posta,
                "davcniZavezanec": davcni_zavezanec,
                "davcnaStevilka": davcna_stevilka
            },
            "imaVeljavnoPooblastiloZaPridobivanjePodatkov": ima_pooblastilo,
            "priloge": [
                {
                    "naziv": file_name,
                    "datoteka": encoded_file,
                    "vrstaDokumenta": vrsta_dokumenta
                }
            ]
        }

        url = "https://test-api.informatika.si/enotna-vstopna-tocka/evidenca-zahtev/merilne-tocke/podatki-mt-mm-meritve"
        encoded_string = st.secrets["encoded_string_nme"]  # ali sfa, po potrebi
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_string}"
        }

        try:
            response = requests.post(url, headers=headers, data=json.dumps(body), timeout=120)
            if response.status_code == 200:
                st.success(f"Zahteva uspešno dodana! ID zahteve: {response.json().get('idZahteva')}")
            elif response.status_code == 401:
                st.error("⚠️ Neavtoriziran dostop do storitve (401)")
            else:
                st.error(f"Napaka: {response.status_code} - {response.text}")
        except requests.exceptions.Timeout:
            st.error("⚠️ Timeout: Server je predolgo časa nedosegljiv.")
        except requests.exceptions.RequestException as e:
            st.error(f"⚠️ Napaka pri pošiljanju zahtevka: {e}")

if __name__ == "__main__":
    main()