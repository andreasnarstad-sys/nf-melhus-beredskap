import streamlit as st
import os
import requests
import pandas as pd
import base64
from datetime import datetime

# --- 1. KONFIGURASJON: POLITIDISTRIKT TIL FYLKE (NVE-MAPPING) ---
DISTRIKT_MAP = {
    "Oslo": [3], 
    "Øst": [3, 34], 
    "Innlandet": [34], 
    "Sør-Øst": [38, 33],
    "Agder": [42], 
    "Sør-Vest": [11, 42], 
    "Vest": [46], 
    "Møre og Romsdal": [15],
    "Trøndelag": [50], 
    "Nordland": [18], 
    "Troms": [54, 55], 
    "Finnmark": [54, 56]
}

# --- 2. DATA-HENTING (API-ER) ---
def hent_logo_base64():
    for ext in ["png", "jpg", "jpeg"]:
        path = f"nf_logo.{ext}"
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode(), ext
    return None, None

def hent_alle_nve_varsler(distrikt_navn):
    fylker = DISTRIKT_MAP.get(distrikt_navn, [50])
    alle_varsler = []
    for f_nr in fylker:
        url = f"https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/{f_nr}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                alle_varsler.extend(r.json())
        except: pass
    return alle_varsler

def hent_skogbrannfare_lokal(lat, lon):
    url = f"https://api.met.no/weatherapi/firehazard/2.0/compact?lat={lat}&lon={lon}"
    headers = {'User-Agent': 'NF_Beredskap_App_v2.5_PRO'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()['properties']['timeseries'][0]['fire_hazard_index']
    except: return None

# --- 3. LAGRING OG LASTING ---
def last_alt():
    default = {
        "nivaa": "🟢 Grønn / Normal", "beskjed": "Alt ok.", "vakt": "9XX XX XXX", 
        "leder": "Ikke satt", "sanitet": "Ikke satt", "distrikt": "Trøndelag", 
        "talegruppe": "FOR-MELHUS-1", "oppmote": "Depot Melhus", 
        "valgt_kort": "Ingen", "aktive_oppdrag": "Vakt,Trening",
        "lat": "63.2859", "lon": "10.2781", "op_leder": "Ikke satt"
    }
    if os.path.exists("beredskap_data.txt"):
        try:
            with open("beredskap_data.txt", "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    for p in content.split(";"):
                        if "|" in p:
                            k, v = p.split("|")
                            default[k] = v
        except: pass
    return default

def lagre_alt(data_dict):
    string_data = ";".join([f"{k}|{v}" for k, v in data_dict.items()])
    with open("beredskap_data.txt", "w", encoding="utf-8") as f:
        f.write(string_data)

def lagre_utrykning(data):
    file_exists = os.path.isfile("aksjonslogg.csv")
    pd.DataFrame([data]).to_csv("aksjonslogg.csv", mode='a', index=False, header=not file_exists, encoding="utf-8")

# --- 4. HOVEDAPP OPPSETT ---
st.set_page_config(page_title="NF Beredskap v2.5", layout="wide")
d = last_alt()
logo_b64, logo_ext = hent_logo_base64()

# Header-seksjon
if logo_b64:
    st.markdown(f'<div style="text-align:center; margin-top:-30px;"><img src="data:image/{logo_ext};base64,{logo_b64}" style="width:100%; max-width:1000px;"></div>', unsafe_allow_html=True)
else:
    st.title("🚑 Norsk Folkehjelp Beredskap")

st.write("---")

# Hovedstatus (Lederstyrt)
farge_leder = "#28a745"
if "🟡" in d['nivaa']: farge_leder = "#ffc107"
elif "🔴" in d['nivaa']: farge_leder = "#dc3545"

st.markdown(f"""
    <div style="background-color:{farge_leder}; padding:25px; border-radius:15px; text-align:center; color:white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin:0; font-size:2.5rem;">{d['nivaa']}</h1>
        <p style="font-size:1.3rem; margin-top:10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. DYNAMISK VARSLING (POLITIDISTRIKT + MET) ---
st.write("")
col_v1, col_v2 = st.columns([2, 1])

with col_v1:
    st.subheader(f"⚠️ Aktive varsler: {d['distrikt']} Politidistrikt")
    varsler = hent_alle_nve_varsler(d['distrikt'])
    aktive = [v for v in varsler if v.get('ActivityLevel', 1) > 1]
    
    if aktive:
        df = pd.DataFrame([{
            "Kommune": v['MunicipalityName'],
            "Nivå": v['ActivityLevel'],
            "Type": "Flom/Skred",
            "Beskrivelse": v['MainText']
        } for v in aktive]).sort_values(by="Nivå", ascending=False)

        def fargelegg_rader(row):
            farger = {2: ("#FFFF00", "#000000"), 3: ("#FF9900", "#FFFFFF"), 4: ("#FF0000", "#FFFFFF")}
            bg, txt = farger.get(row.Nivå, ("#28a745", "#ffffff"))
            return [f'background-color: {bg}; color: {txt}'] * len(row)

        st.dataframe(df.style.apply(fargelegg_rader, axis=1), use_container_width=True, hide_index=True)
    else:
        st.success(f"✅ Ingen aktive farevarsler i {d['distrikt']} politidistrikt.")

with col_v2:
    st.subheader("🔥 Skogbrannfare (Lokal)")
    brannfare = hent_skogbrannfare_lokal(d['lat'], d['lon'])
    if brannfare is not None:
        b_bg = "green" if brannfare <= 1 else "orange" if brannfare <= 3 else "red"
        st.markdown(f"""
            <div style="background-color:{b_bg}; color:white; padding:20px; border-radius:10px; text-align:center; font-weight:bold; font-size:1.4rem;">
                BRANNINDEKS: {brannfare}
            </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Henter lokale data fra MET...")

# --- 6. INFO-PANEL ---
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}")
    st.write(f"**Leder:** {d['leder']}")
with c2:
    st.subheader("📻 Samband")
    st.info(f"**TG:** `{d['talegruppe']}`\n\n**Oppmøte:** {d['oppmote']}")
with c3:
    st.subheader("📋 Tiltak")
    if d['valgt_kort'] != "Ingen":
        st.error(f"AKTIVT KORT: {d['valgt_kort']}")
    else:
        st.write("Ingen aktive tiltakskort.")

# --- 7. REGISTRERING OG ADMIN ---
st.write("---")
with st.expander("📝 Registrer deltakelse (Timer/KM)"):
    oppdrag_valg = d.get('aktive_oppdrag', 'Vakt').split(',')
    with st.form("reg_form", clear_on_submit=True):
        navn = st.text_input("Navn")
        valgt_op = st.selectbox("Oppdrag", oppdrag_valg)
        c_t1, c_t2 = st.columns(2)
        t_ut = c_t1.text_input("Ut (HH:MM)")
        t_inn = c_t2.text_input("Inn (HH:MM)")
        km = st.number_input("KM", min_value=0)
        if st.form_submit_button("Send inn"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": valgt_op, "Ut": t_ut, "Inn": t_inn, "KM": km})
            st.success("Registrert!")

with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("HENT LOGG (CSV)"):
            if os.path.exists("aksjonslogg.csv"):
                df_l = pd.read_csv("aksjonslogg.csv")
                st.dataframe(df_l)
                st.download_button("Last ned", df_l.to_csv(index=False), "logg.csv")
        
        st.write("---")
        ca, cb = st.columns(2)
        with ca:
            n_distrikt = st.selectbox("Velg Politidistrikt:", list(DISTRIKT_MAP.keys()), index=list(DISTRIKT_MAP.keys()).index(d.get('distrikt', 'Trøndelag')))
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], index=0)
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separer m/komma)", value=d.get('aktive_oppdrag', 'Vakt,Trening'))
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_lat = st.text_input("Breddegrad (for brannfare)", value=d['lat'])
            n_lon = st.text_input("Lengdegrad (for brannfare)", value=d['lon'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Skogbrann", "Strømbrudd"])

        if st.button("LAGRE ALT"):
            d.update({"distrikt": n_distrikt, "nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "lat": n_lat, "lon": n_lon, "leder": n_leder, "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d)
            st.rerun()
