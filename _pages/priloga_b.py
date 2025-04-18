import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict

sifra_izvora_bremenitve = {
    'RR': 'Redni račun na mesečnem obračunu',
    'SO': 'Letni obračun',
    'OB': 'Obrok',
    'SP': 'Popravek, storno, izredni račun'
}

sifra_napetostni_nivo = {
    '1': 'Visoka napetost',
    '2': 'Visoka napetost',
    '3': 'Visoka napetost',
    '4': 'Visoka napetost',
    '5': 'Visoka napetost',
    '6': 'Visoka napetost',
    '7': 'Srednja napetost',
    '9': 'Srednja napetost',
    '10': 'Srednja napetost',
    '12': 'Srednja napetost',
    '13': 'Nizka napetost',
    '14': 'Nizka napetost',
    '15': 'Nizka napetost',
    '16': 'Nizka napetost',
    '18': 'Nizka napetost',
    '19': 'Nizka napetost',
    '20': 'Nizka napetost',
    '21': 'Srednja napetost',
    '22': 'Srednja napetost',
    '23': 'Srednja napetost',
    '24': 'Srednja napetost',
    '25': 'Nizka napetost',
    '26': 'Nizka napetost',
    '27': 'Nizka napetost',
    '28': 'Nizka napetost',
    '29': 'Nizka napetost',
    '30': 'Nizka napetost',
    '31': 'Nizka napetost',
    '32': 'Visoka napetost',
    '33': 'Visoka napetost',
    '34': 'Visoka napetost',
    '35': 'Srednja napetost',
    '36': 'Srednja napetost',
    '37': 'Srednja napetost',
    '38': 'Srednja napetost',
    '39': 'Nizka napetost',
    '40': 'Nizka napetost',
    '41': 'Nizka napetost',
    '42': 'Nizka napetost',
    '43': 'Nizka napetost',
}

sifra_odjemna_skupina = {
    '1': 'T>=6000 ur, visoka sezona',
    '2': 'T<2500 ur, visoka sezona',
    '3': 'T>=6000 ur, nizka sezona',
    '4': '6000 ur>T>=2500 ur, nizka sezona',
    '5': 'T<2500 ur, nizka sezona',
    '6': '6000 ur>T>=2500 ur, visoka sezona',
    '7': 'T>2500 ur, visoka sezona',
    '9': 'T>2500 ur, nizka sezona',
    '10': 'T<2500 ur, visoka sezona',
    '12': 'T<2500 ur, nizka sezona',
    '13': 'T>2500 ur, visoka sezona',
    '14': 'T>2500 ur, nizka sezona',
    '15': 'T<2500 ur, visoka sezona',
    '16': 'T<2500 ur, nizka sezona',
    '18': 'Ostali odjem',
    '19': 'Gospodinjstvo',
    '20': 'Javna razsvetljava',
    '21': 'T>2500 ur, odjem na zbiralkah RTP, visoka sezona',
    '22': 'T>2500 ur, odjem na zbiralkah RTP, nizka sezona',
    '23': 'T<2500 ur, odjem na zbiralkah RTP, visoka sezona',
    '24': 'T<2500 ur, odjem na zbiralkah RTP, nizka sezona',
    '25': 'T>2500 ur, odjem na zbiralkah TP, visoka sezona',
    '26': 'T>2500 ur, odjem na zbiralkah TP, nizka sezona',
    '27': 'T<2500 ur, odjem na zbiralkah TP, visoka sezona',
    '28': 'T<2500 ur, odjem na zbiralkah TP, nizka sezona',
    '29': 'Polnjenje EV',
    '30': 'Gospodinjstvo s KKT',
    '31': 'Brez merjenja moči s KKT',
    '32': 'T>=6000 ur',
    '33': '6000>T>=2500 ur',
    '34': 'T<2500 ur',
    '35': 'T>=2500 ur',
    '36': 'T<2500 ur',
    '37': 'T>=2500 ur',
    '38': 'T<2500 ur',
    '39': 'T>=2500 ur',
    '40': 'T<2500 ur',
    '41': 'T>=2500 ur',
    '42': 'T<2500 ur',
    '43': 'Brez merjena moči',
}

sifra_uporabniska_skupina = {
    '0': 'uporabniška skupina 0, v katero so uvrščeni uporabniki sistema, priključeni na NN izvod',
    '1': 'uporabniška skupina 1, v katero so uvrščeni uporabniki sistema, priključeni na NN na zbiralnici NN v TP',
    '2': 'uporabniška skupina 2, v katero so uvrščeni uporabniki sistema, priključeni na SN izvod',
    '3': 'uporabniška skupina 3, v katero so uvrščeni uporabniki sistema, priključeni na SN na zbiralnici SN',
    '4': 'uporabniška skupina 4, v katero so uvrščeni uporabniki sistema, priključeni na VT izvod',
}

sifra_nacina_obracuna = {
    '1': 'Letni obračun',
    '3': 'Mesečni obračun'
}

sifra_zaracunljivega_elementa = {
    '1': 'obračunska moč',
    '3': 'omrežnina KT',
    '4': 'omrežnina VT',
    '5': 'omrežnina MT',
    '6': 'omrežnina ET',
    '9': 'jalova zaračunana',
    '10': 'Prispevek OVE+SPTE',
    '11': 'Prispevek DVE',
    '12': 'Prispevek za energetsko učinkovitost',
    '13': 'Prispevek OVE+SPTE z olajšavo',
    '14': 'Prispevek OVE+SPTE fiksni mesečni prispevek',
    '20': 'Dodatek za AGEN-RS',
    '21': 'Prispevek za delovanje operaterja trga',
    '50': 'Prispevek za URE',
    '51': 'Trošarina - neposlovna raba',
    '52': 'Trošarina - poslovna raba',
    '54': 'Energija VT - Napačne meritve',
    '55': 'Energija BT - Napačne meritve',
    '56': 'Energija ET - Napačne meritve',
    '64': 'Energija VT - Zasilna oskrba',
    '65': 'Energija MT - Zasilna oskrba',
    '66': 'Energija ET - Zasilna oskrba',
    '74': 'Energija - Neupravičen odjem',
    '84': 'Energija VT - Nujna oskrba',
    '85': 'Energija MT - Nujna oskrba',
    '86': 'Energija ET - Nujna oskrba',
    '95': 'Izravnava omrežnine',
    '96': 'Izravnava prispevka OVE+SPTE',
    '97': 'Izravnava prispevka DVE',
    '98': 'Izravnava trošarine',
    '100': 'Večkr.zag.stat.mer.in obr.pod.',
    '101': 'Zag.stat.mer.in obr.pod.',
    '102': 'Teh.prilag. MM za pod.stor.',
    '103': 'Dod. odčit. na zaht. - ročno',
    '104': 'Dod.odčit.na zaht.- daljinsko',
    '105': 'Odkl./prikl. MM na zaht. upor',
    '106': 'Spr.obr.m. v okviru prik.moči',
    '107': 'Kontr.točnosti mer. naprav',
    '108': 'A-test merilne naprave',
    '109': 'Parametr. elektron. števca',
    '110': 'Parametr. kom. vmesnika',
    '111': 'Pretarif. brez obiska monterja',
    '112': 'Pretarif. z obiskom monterja',
    '113': 'Zam.obr.varov.D (RDČ)',
    '114': 'Zam.obr.varov.D (izven RDČ)',
    '115': 'Zam.obr.varov.NV (RDČ)',
    '116': 'Zam.obr.varov.NV (izven RDČ)',
    '117': 'Obisk monterja (RDČ)',
    '118': 'Obisk monterja (IZR)',
    '119': 'Dnevno zagotavljanje merilnih podatkov',
    '120': 'Odklop-priklop MM brez obiska monterja',
    '250': 'Priklop in odklop začasne elektro omarice',
    '251': 'Priklop in odklop potopne omarice',
    '252': 'Dnevni najem začasne elektro omarice',
    '253': 'Dnevni najem potopne omarice',
    '501': 'Trošarina I. stopnja',
    '502': 'Trošarina II. stopnja ',
    '503': 'Trošarina III. stopnja ',
    '504': 'Trošarina IV. stopnja ',
    '1001': 'Omrežnina KKT v VT',
    '1002': 'Omrežnina KKT v MT',
    '1003': 'Oddana energija KT',
    '1004': 'Oddana energija VT',
    '1005': 'Oddana energija MT',
    '1006': 'Oddana energija ET',
    '1007': 'Oddana jalova izmerjena VT',
    '1008': 'Oddana jalova izmerjena MT',
    '1009': 'Omrežnina PKKT v VT',
    '1010': 'Omrežnina PKKT v MT',
    '1011': 'Omrežnina PKKT v ET',
    '1012': 'Omrežnina NKKT v VT',
    '1013': 'Omrežnina NKKT v MT',
    '1014': 'Omrežnina NKKT v ET',
    '1015': 'Omrežnina v VT 137. člen veljavnega omrežninskega akta (samooskrba pilotni projekti)',
    '1016': 'Omrežnina v MT 137. člen veljavnega omrežninskega akta (samooskrba pilotni projekti)',
    '1017': 'Prekoračitev obračunske moči nad priključno močjo',
    '9020': 'Poračun obračunske moči (žled)',
    '9021': 'Poračun prisp. OVE+SPTE (žled)',
    '2001': 'Dogovorjena obr. moč za blok 1',
    '2002': 'Dogovorjena obr. moč za blok 2',
    '2003': 'Dogovorjena obr. moč za blok 3',
    '2004': 'Dogovorjena obr. moč za blok 4',
    '2005': 'Dogovorjena obr. moč za blok 5',
    '2101': 'Presežna obr. moč za blok 1',
    '2102': 'Presežna obr. moč za blok 2',
    '2103': 'Presežna obr. moč za blok 3',
    '2104': 'Presežna obr. moč za blok 4',
    '2105': 'Presežna obr. moč za blok 5',
    '2201': 'Prenesena EE za blok 1',
    '2202': 'Prenesena EE za blok 2',
    '2203': 'Prenesena EE za blok 3',
    '2204': 'Prenesena EE za blok 4',
    '2205': 'Prenesena EE za blok 5',
    '2301': 'Prilagojena postavka za EE za značilen primer 1 za blok 1',
    '2302': 'Prilagojena postavka za EE za značilen primer 1 za blok 2',
    '2303': 'Prilagojena postavka za EE za značilen primer 1 za blok 3',
    '2304': 'Prilagojena postavka za EE za značilen primer 1 za blok 4',
    '2305': 'Prilagojena postavka za EE za značilen primer 1 za blok 5',
    '2401': 'Prilagojena postavka za EE za značilen primer 2 za blok 1',
    '2402': 'Prilagojena postavka za EE za značilen primer 2 za blok 2',
    '2403': 'Prilagojena postavka za EE za značilen primer 2 za blok 3',
    '2404': 'Prilagojena postavka za EE za značilen primer 2 za blok 4',
    '2405': 'Prilagojena postavka za EE za značilen primer 2 za blok 5',
    '2501': 'Prilagojena postavka za EE za značilen primer 3 za blok 1',
    '2502': 'Prilagojena postavka za EE za značilen primer 3 za blok 2',
    '2503': 'Prilagojena postavka za EE za značilen primer 3 za blok 3',
    '2504': 'Prilagojena postavka za EE za značilen primer 3 za blok 4',
    '2505': 'Prilagojena postavka za EE za značilen primer 3 za blok 5',
    '2601': 'Prilagojena postavka za EE za značilen primer 4 za blok 1',
    '2602': 'Prilagojena postavka za EE za značilen primer 4 za blok 2',
    '2603': 'Prilagojena postavka za EE za značilen primer 4 za blok 3',
    '2604': 'Prilagojena postavka za EE za značilen primer 4 za blok 4',
    '2605': 'Prilagojena postavka za EE za značilen primer 4 za blok 5',
    '2701': 'Prilagojena postavka za EE za značilen primer 5 za blok 1',
    '2702': 'Prilagojena postavka za EE za značilen primer 5 za blok 2',
    '2703': 'Prilagojena postavka za EE za značilen primer 5 za blok 3',
    '2704': 'Prilagojena postavka za EE za značilen primer 5 za blok 4',
    '2705': 'Prilagojena postavka za EE za značilen primer 5 za blok 5',
    '2801': 'Prilagojena postavka za EE za značilen primer 6 za blok 1',
    '2802': 'Prilagojena postavka za EE za značilen primer 6 za blok 2',
    '2803': 'Prilagojena postavka za EE za značilen primer 6 za blok 3',
    '2804': 'Prilagojena postavka za EE za značilen primer 6 za blok 4',
    '2805': 'Prilagojena postavka za EE za značilen primer 6 za blok 5',
    '2901': 'Prilagojena postavka za EE za značilen primer 7 za blok 1',
    '2902': 'Prilagojena postavka za EE za značilen primer 7 za blok 2',
    '2903': 'Prilagojena postavka za EE za značilen primer 7 za blok 3',
    '2904': 'Prilagojena postavka za EE za značilen primer 7 za blok 4',
    '2905': 'Prilagojena postavka za EE za značilen primer 7 za blok 5',
    '8001': 'Informativna presežna obr. moč za blok 1',
    '8002': 'Informativna presežna obr. moč za blok 2',
    '8003': 'Informativna presežna obr. moč za blok 3',
    '8004': 'Informativna presežna obr. moč za blok 4',
    '8005': 'Informativna presežna obr. moč za blok 5',
    '10001': 'Faktor doplačila za ZUS<=3 mesece 2,35',
    '10002': 'Faktor doplačila 3 mesece<ZUS<=4 mesecev 1,9',
    '10003': 'Faktor doplačila 4 mesece<ZUS<=5 mesecev 1,63',
    '10004': 'Faktor doplačila 5 mesecev<ZUS<=6 mesecev 1,45',
    '10005': 'Faktor doplačila ZUS>6 mesecev 1,32',
}

sifra_pridobitve_stanja = {
    '1': 'SODO',
    '2': 'Odjemalec',
    '3': 'Daljinsko odčitavanje',
    '4': 'Ocena SODO',
    'T': 'Telefonski odzivnik',
    'I': 'Portal'
}

sifra_korekcije_kolicin = {
    '0': 'odbirek',
    '4': 'ocena ',
    '6': 'vzporedne meritve - sumiranje',
    '5': 'pripis količin',
    '7': 'odpis količin',
    '8': 'pripis količin zaradi KKT',
    '9': 'odpis količin zaradi KKT',
    '10': 'Pripis proizvedene količine iz naslova samooskrbe',
    '11': 'Odpis proizvedene količine iz naslova samooskrbe',
    '12': 'Pripis porabe'
}

sifra_olajsave_za_obracun_omreznine = {
    '0': 'vsi elementi omrežnine',
    '1': 'obračunana olajšava omrežnine',
}

sifra_uvrstitve_obracuna = {
    'M0-1': 'obračun po 17.členu brez 15 min meritev (M0-1)',
    'M0-2': 'obračun za začasno uporabo sistema (M0-2)',
    'M1-1': 'obračun po časovnih blokih (M1-1)',
    'M1-2': 'obračun po VT/MT/ET, LP pod 90% (M1-2)',
    'M1-3': 'obračun samooskrbe po EZ-1, moč po dogovorjeni moči (M1-3)',
    'M1-4': 'obračun za nove uporabnike po časovnih blokih (M1-4)',
    'M1-5': 'obračun za nove uporabnike po VT/MT/ET, LP pod 90% (M1-5)',
}

razlog_obracuna = {
    '1': 'Obračun',
    '2': 'Števec ni beležil porabe',
    '3': 'Napačna registracija porabe',
    '4': 'Ni bilo preklopa tarife',
    '5': 'Okvara prikazovalnika',
    '6': 'Okvara števca',
    '7': 'Drugo',
    '8': 'Ocena pri rednem popisu',
    '9': 'Napačen popis',
    '10': 'Napačna varovalka ',
    '11': 'Sprememba plačnika ',
    '13': 'Odjemalec javil napačno stanje ',
    '14': 'Sprememba dobavitelja in plačnika ',
    '15': 'Stečaj, Likvidacija, Prisilna poravnava ',
    '16': 'Sprememba dobavitelja ',
    '17': 'Napačno obračunana moč ',
    '18': 'Sprememba vrste bremenitve ',
    '19': 'Sprememba načina posredovanja računa ',
    '20': 'Pravno nasledstvo ',
    '21': 'Pretarifiranje ',
    '22': 'Sprememba obračunske moči ',
    '23': 'Odjava/odklop ',
    '24': 'Napačni podatki s strani dobavitelja ',
}

vrsta_tarife_za_obracun = {
    '1': 'Enotarifni (ET)',
    '2': 'Dvotarifni (VT, MT)',
    '3': 'Tritarifni (KT, VT, MT)',
    '4': 'Posebni tritarifni (KKT,VT,MT)',
}


def calculate_dni_value(start_date, end_date):
    date1_obj = datetime.strptime(start_date, "%Y-%m-%d")
    date2_obj = datetime.strptime(end_date, "%Y-%m-%d")
    return abs((date2_obj - date1_obj).days) + 1


def convert_datetime(datetime_str):
    original_datetime = datetime.fromisoformat(datetime_str)
    return original_datetime.strftime("%d.%m.%Y %H:%M")


def extract_splosno_priloge(priloga):
    return [{
        'Verzija': priloga.find('Verzija').text,
        'ZaporednaStevilkaPrilogaA': priloga.find('ZaporednaStevilkaPrilogaA').text,
        'CasObjave': convert_datetime(priloga.find('CasObjave').text),
        'StevilkaGS1MerilneTocke': priloga.find('MerilnaTocka/StevilkaGS1MerilneTocke').text,
        'TipMerilneTocke': priloga.find('MerilnaTocka/TipMerilneTocke').text,
        'Distribucija': priloga.find('Distribucija').text,
        'DavcnaStevilkaPlacnika': priloga.find('Splosno/PlacnikNaMerilniTocki/DavcnaStevilkaPlacnika').text,
        'NazivPlacnika': priloga.find('Splosno/PlacnikNaMerilniTocki/NazivPlacnika').text,
        'NaslovnikNaMerilniTocki': priloga.find('Splosno/NaslovnikNaMerilniTocki/NazivNaslovnika').text,
        'LetoPodatka': priloga.find('Splosno/LetoPodatka').text,
        'MesecFinancneRealizacije': priloga.find('Splosno/MesecFinancneRealizacije').text,
        'SkupniRacun': priloga.find('Splosno/SkupniRacun').text,
        'Meritve15min': priloga.find('Splosno/Meritve15min').text if priloga.find('Splosno/Meritve15min') != None else "",
        'DatumMeritve15minOd': priloga.find('Splosno/DatumMeritve15minOd').text,
        'SifraUvrstitveObracuna': sifra_uvrstitve_obracuna[priloga.find('Splosno/SifraUvrstitveObracuna').text],
        'SifraIzvoraBremenitve': sifra_izvora_bremenitve[priloga.find('Splosno/SifraIzvoraBremenitve').text],
        'DatumIzstavitve': priloga.find('Splosno/DatumIzstavitve').text,
        'DatumZapadlosti': priloga.find('Splosno/DatumZapadlosti').text,
        'ObdobjeOd': priloga.find('Splosno/ObdobjeOd').text,
        'ObdobjeDo': priloga.find('Splosno/ObdobjeDo').text,
        'StevilkaIzvornegaPodatka': priloga.find('Splosno/StevilkaIzvornegaPodatka').text,
        'LetoIzvornegaPodatka': priloga.find('Splosno/LetoIzvornegaPodatka').text,
        'Odjava': priloga.find('Splosno/Odjava').text,
        'RazlogObracuna': razlog_obracuna[priloga.find('Splosno/RazlogObracuna').text],
        'PotrebenObracunDobavitelja': priloga.find('Splosno/PotrebenObracunDobavitelja').text,
        'VrstaTarifeZaObracun': vrsta_tarife_za_obracun[priloga.find('Splosno/VrstaTarifeZaObracun').text],
    }]


def extract_merilna_mesta(priloga):
    data = []
    for item in priloga.findall('.//MerilnoMesto'):
        entry = {
            'EnotniIdentifikatorMerilnegaMesta': item.find('EnotniIdentifikatorMerilnegaMesta').text,
            'GS1MerilnegaMesta': item.find('GS1MerilnegaMesta').text,
            'NazivMerilnegaMesta': item.find('NazivMerilnegaMesta').text,
            'SNizvod': item.find('SNizvod').text,
            'PrikljucnaMoc': item.find('PrikljucnaMoc').text,
            'StevilkaStevca': item.find('StevilkaStevca').text,
            'ObracunskaVarovalka': item.find('ObracunskaVarovalka').text,
            'SifraOdjemneSkupine': sifra_odjemna_skupina[item.find('SifraOdjemneSkupine').text],
            'SifraUporabniskeSkupine': sifra_uporabniska_skupina[item.find('SifraUporabniskeSkupine').text],
            'SifraNacinaObracuna': sifra_nacina_obracuna[item.find('SifraNacinaObracuna').text],
            'OdstotekIzgubTransformacije': item.find('OdstotekIzgubTransformacije').text,
            'SifraOlajsaveZaObracunOmreznine': sifra_olajsave_za_obracun_omreznine[
                item.find('SifraOlajsaveZaObracunOmreznine').text],
        }
        data.append(entry)
    return data


def extract_merilni_podatki(priloga):
    data = []
    for item in priloga.findall('.//MerilniPodatkiVrstica'):
        sifra = item.findtext('SifraZaracunljivegaElementa')
        entry = {
            sifra + '_SifraZaracunljivegaElementa': sifra_zaracunljivega_elementa[sifra],
            sifra + '_StanjeStaro_Odbirek': item.find('StanjeStaro/Odbirek').text.replace(".", ","),
            sifra + '_StanjeStaro_DatumStanja': item.find('StanjeStaro/DatumStanja').text,
            sifra + '_StanjeNovo_Odbirek': item.find('StanjeNovo/Odbirek').text.replace(".", ","),
            sifra + '_StanjeNovo_DatumStanja': item.find('StanjeNovo/DatumStanja').text,
            sifra + '_StanjeRazlika': item.findtext('StanjeRazlika').replace(".", ","),
            sifra + '_SifraNacinaPridobitveStanja': sifra_pridobitve_stanja[item.findtext('SifraNacinaPridobitveStanja')],
            sifra + '_KonstantaStevca': item.findtext('KonstantaStevca').replace(".", ","),
            sifra + '_Kolicina': item.findtext('Kolicina').replace(".", ","),
            sifra + '_SifraKorekcijeKolicin': sifra_korekcije_kolicin[item.findtext('SifraKorekcijeKolicin')]
        }
        data.append(entry)
    return data


def extract_obracunski_podatki(priloga):
    data = []
    for item in priloga.findall('.//ObracunVrstica'):
        sifra = item.findtext('SifraZaracunljivegaElementa')
        entry = {
            sifra + '_SifraZaracunljivegaElementa': sifra_zaracunljivega_elementa[sifra],
            sifra + '_ObdobjeOd': item.find('ObdobjeOd').text,
            sifra + '_ObdobjeDo': item.find('ObdobjeDo').text,
            sifra + '_Kolicina': item.find('Kolicina').text.replace(".", ","),
            sifra + '_EnotaMere': item.find('EnotaMere').text,
            sifra + '_Cena': item.find('Cena/Cena').text.replace(".", ","),
            sifra + '_DatumUveljavitveCene': item.find('Cena/DatumUveljavitveCene').text,
            sifra + '_Valuta': item.find('Cena/Valuta').text,
            sifra + '_Znesek': item.find('Znesek').text.replace(".", ","),
            sifra + '_StopnjaDDV': item.find('StopnjaDDV').text,
        }
        data.append(entry)
    return data


def extract_sumarne_kolicine(priloga):
    data = []
    for item in priloga.findall('.//SumarneKolicineEnergijaVrstica'):
        sifra = item.findtext('SifraZaracunljivegaElementa')
        entry = {
            # sifra + '_SifraZaracunljivegaElementa': sifra_zaracunljivega_elementa[sifra],
            sifra + '_SumarnaKolicina': item.find('SumarnaKolicina').text.replace(".", ","),
        }
        data.append(entry)
    return data


def convert_to_df(data):
    columns=[
        "Verzija",	
        "ZaporednaStevilkaPrilogaA",
        "CasObjave",
        "StevilkaGS1MerilneTocke",
        "TipMerilneTocke",
        "Distribucija",
        "DavcnaStevilkaPlacnika",
        "NazivPlacnika",
        "NaslovnikNaMerilniTocki",	
        "LetoPodatka",
        "MesecFinancneRealizacije",
        "SkupniRacun",	
        "Meritve15min",
        "DatumMeritve15minOd",
        "SifraUvrstitveObracuna",
        "SifraIzvoraBremenitve",
        "DatumIzstavitve",
        "DatumZapadlosti",
        "ObdobjeOd",
        "ObdobjeDo",
        "StevilkaIzvornegaPodatka",
        "LetoIzvornegaPodatka",
        "Odjava",
        "RazlogObracuna",	
        "PotrebenObracunDobavitelja",
        "VrstaTarifeZaObracun",
        "EnotniIdentifikatorMerilnegaMesta",
        "GS1MerilnegaMesta",
        "NazivMerilnegaMesta",
        "SNizvod",
        "PrikljucnaMoc",
        "StevilkaStevca",
        "ObracunskaVarovalka",
        "SifraOdjemneSkupine",
        "SifraUporabniskeSkupine",
        "SifraNacinaObracuna",
        "OdstotekIzgubTransformacije",
        "SifraOlajsaveZaObracunOmreznine",

        "4_SifraZaracunljivegaElementa_1",
        "4_StanjeStaro_Odbirek_1",
        "4_StanjeStaro_DatumStanja_1",
        "4_StanjeNovo_Odbirek_1",
        "4_StanjeNovo_DatumStanja_1",
        "4_StanjeRazlika_1",
        "4_SifraNacinaPridobitveStanja_1",
        "4_KonstantaStevca_1",
        "4_Kolicina_1",
        "4_SifraKorekcijeKolicin_1",

        "4_SifraZaracunljivegaElementa_2",
        "4_StanjeStaro_Odbirek_2",
        "4_StanjeStaro_DatumStanja_2",
        "4_StanjeNovo_Odbirek_2",
        "4_StanjeNovo_DatumStanja_2",
        "4_StanjeRazlika_2",
        "4_SifraNacinaPridobitveStanja_2",
        "4_KonstantaStevca_2",
        "4_Kolicina_2",
        "4_SifraKorekcijeKolicin_2",

        "4_SumarnaKolicina",

        "5_SifraZaracunljivegaElementa_1",
        "5_StanjeStaro_Odbirek_1",
        "5_StanjeStaro_DatumStanja_1",
        "5_StanjeNovo_Odbirek_1",
        "5_StanjeNovo_DatumStanja_1",
        "5_StanjeRazlika_1",
        "5_SifraNacinaPridobitveStanja_1",
        "5_KonstantaStevca_1",
        "5_Kolicina_1",
        "5_SifraKorekcijeKolicin_1",

        "5_SifraZaracunljivegaElementa_2",
        "5_StanjeStaro_Odbirek_2",
        "5_StanjeStaro_DatumStanja_2",
        "5_StanjeNovo_Odbirek_2",
        "5_StanjeNovo_DatumStanja_2",
        "5_StanjeRazlika_2",
        "5_SifraNacinaPridobitveStanja_2",
        "5_KonstantaStevca_2",
        "5_Kolicina_2",
        "5_SifraKorekcijeKolicin_2",

        "5_SumarnaKolicina",

        "6_SifraZaracunljivegaElementa_1",
        "6_StanjeStaro_Odbirek_1",
        "6_StanjeStaro_DatumStanja_1",
        "6_StanjeNovo_Odbirek_1",
        "6_StanjeNovo_DatumStanja_1",
        "6_StanjeRazlika_1",
        "6_SifraNacinaPridobitveStanja_1",
        "6_KonstantaStevca_1",
        "6_Kolicina_1",
        "6_SifraKorekcijeKolicin_1",

        "6_SifraZaracunljivegaElementa_2",
        "6_StanjeStaro_Odbirek_2",
        "6_StanjeStaro_DatumStanja_2",
        "6_StanjeNovo_Odbirek_2",
        "6_StanjeNovo_DatumStanja_2",
        "6_StanjeRazlika_2",
        "6_SifraNacinaPridobitveStanja_2",
        "6_KonstantaStevca_2",
        "6_Kolicina_2",
        "6_SifraKorekcijeKolicin_2",

        "6_SumarnaKolicina",

        "2001_SifraZaracunljivegaElementa",
        "2001_ObdobjeOd",
        "2001_ObdobjeDo",
        "2001_Kolicina",
        "2001_EnotaMere",
        "2001_Cena",
        "2001_DatumUveljavitveCene",
        "2001_Valuta",
        "2001_Znesek",
        "2001_StopnjaDDV",

        "2002_SifraZaracunljivegaElementa",
        "2002_ObdobjeOd",
        "2002_ObdobjeDo",
        "2002_Kolicina",
        "2002_EnotaMere",
        "2002_Cena",
        "2002_DatumUveljavitveCene",
        "2002_Valuta",
        "2002_Znesek",
        "2002_StopnjaDDV",

        "2003_SifraZaracunljivegaElementa",
        "2003_ObdobjeOd",
        "2003_ObdobjeDo",
        "2003_Kolicina",
        "2003_EnotaMere",
        "2003_Cena",
        "2003_DatumUveljavitveCene",
        "2003_Valuta",
        "2003_Znesek",
        "2003_StopnjaDDV",

        "2004_SifraZaracunljivegaElementa",
        "2004_ObdobjeOd",
        "2004_ObdobjeDo",
        "2004_Kolicina",
        "2004_EnotaMere",
        "2004_Cena",
        "2004_DatumUveljavitveCene",
        "2004_Valuta",
        "2004_Znesek",
        "2004_StopnjaDDV",

        "2201_SifraZaracunljivegaElementa",
        "2201_ObdobjeOd",
        "2201_ObdobjeDo",
        "2201_Kolicina",
        "2201_EnotaMere",
        "2201_Cena",
        "2201_DatumUveljavitveCene",
        "2201_Valuta",
        "2201_Znesek",
        "2201_StopnjaDDV",

        "2202_SifraZaracunljivegaElementa",
        "2202_ObdobjeOd",
        "2202_ObdobjeDo",
        "2202_Kolicina",
        "2202_EnotaMere",
        "2202_Cena",
        "2202_DatumUveljavitveCene",
        "2202_Valuta",
        "2202_Znesek",
        "2202_StopnjaDDV",

        "2203_SifraZaracunljivegaElementa",
        "2203_ObdobjeOd",
        "2203_ObdobjeDo",
        "2203_Kolicina",
        "2203_EnotaMere",
        "2203_Cena",
        "2203_DatumUveljavitveCene",
        "2203_Valuta",
        "2203_Znesek",
        "2203_StopnjaDDV",

        "2204_SifraZaracunljivegaElementa",
        "2204_ObdobjeOd",
        "2204_ObdobjeDo",
        "2204_Kolicina",
        "2204_EnotaMere",
        "2204_Cena",
        "2204_DatumUveljavitveCene",
        "2204_Valuta",
        "2204_Znesek",
        "2204_StopnjaDDV",

        "9_SifraZaracunljivegaElementa",
        "9_ObdobjeOd",
        "9_ObdobjeDo",
        "9_Kolicina",
        "9_EnotaMere",
        "9_Cena",
        "9_DatumUveljavitveCene",
        "9_Valuta",
        "9_Znesek",
        "9_StopnjaDDV",

        "10_SifraZaracunljivegaElementa",
        "10_ObdobjeOd",
        "10_ObdobjeDo",
        "10_Kolicina",
        "10_EnotaMere",
        "10_Cena",
        "10_DatumUveljavitveCene",
        "10_Valuta",
        "10_Znesek",
        "10_StopnjaDDV",

        "12_SifraZaracunljivegaElementa",
        "12_ObdobjeOd",
        "12_ObdobjeDo",
        "12_Kolicina",
        "12_EnotaMere",
        "12_Cena",
        "12_DatumUveljavitveCene",
        "12_Valuta",
        "12_Znesek",
        "12_StopnjaDDV",

        "21_SifraZaracunljivegaElementa",
        "21_ObdobjeOd",
        "21_ObdobjeDo",
        "21_Kolicina",
        "21_EnotaMere",
        "21_Cena",
        "21_DatumUveljavitveCene",
        "21_Valuta",
        "21_Znesek",
        "21_StopnjaDDV",
        ]
    
    table = pd.DataFrame()
    
    for priloga in data:
        entries = defaultdict(list)
        for section in priloga:
            for index, item in enumerate(section):
                for column, value in item.items():
                    entries[column].append(value)
        row = {}
        for column_name, values in entries.items():
            for index, value in enumerate(values):
                if len(values) > 1:
                    suffix = index + 1
                    column = column_name + "_" + str(suffix)
                    row[column] = value
                elif column_name.startswith(('4_SumarnaKolicina', '5_SumarnaKolicina', '6_SumarnaKolicina')):
                    column = column_name
                    row[column] = value
                elif len(values) == 1 and column_name.startswith(('4', '5', '6')):
                    suffix = index + 1
                    column = column_name + "_" + str(suffix)
                    row[column] = value
                else:
                    column = column_name
                    row[column] = value
        
        temp_df = pd.DataFrame.from_dict([row])

        table = pd.concat([table, temp_df])

    priloge = pd.DataFrame()

    for column in columns:
        priloge[column] = table.get(column)

    return priloge.sort_values(by='ZaporednaStevilkaPrilogaA')


def convert(path):
    data = []
    for uploaded_file in path:
        file_content = uploaded_file.read()

        # Load XML into an ElementTree object
        root = ET.fromstring(file_content)

        # Go through each priloga
        for priloga in root.findall('PrilogaA'):
            data.append([
                extract_splosno_priloge(priloga),
                extract_merilna_mesta(priloga),
                extract_merilni_podatki(priloga),
                extract_sumarne_kolicine(priloga),
                extract_obracunski_podatki(priloga),
            ])

    data = convert_to_df(data)

    st.dataframe(data, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(layout="wide")

    st.subheader("Priloga A")

    path = st.file_uploader("Choose Priloga A XML files", type="xml", accept_multiple_files=True)

    if path is not None:
        convert(path)

main()
