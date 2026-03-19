import streamlit as st
import os
import requests
import pandas as pd
import base64
from datetime import datetime

# --- 1. KONFIGURASJON: POLITIDISTRIKT TIL FYLKE OG SNØSKRED-REGIONER ---
# Mapping som kobler politidistrikt til NVEs fylkesnumre og skredregioner
DISTRIKT_MAP = {
    "Oslo": {"fylker": [3], "skred": []},
    "Øst": {"fylker": [3, 34], "skred": []},
    "Innlandet": {"fylker": [34], "skred": ["Jotunheimen", "Romsdal"]},
    "Sør-Øst": {"fylker": [38, 33], "skred": ["Telemark"]},
    "Agder": {"fylker": [42], "skred": []},
    "Sør-Vest": {"fylker": [11, 42], "skred": ["Heiane"]},
    "Vest": {"fylker": [46], "skred": ["Hardanger", "Voss", "Indre Fjordane"]},
    "Møre og Romsdal": {"fylker": [15], "skred": ["Sunnmøre", "Romsdal"]},
    "Trøndelag": {"fylker": [50], "skred": ["Trollheimen"]},
    "Nordland": {"fylker": [18], "skred": ["Ofoten", "Salten", "Svartisen", "Helgeland"]},
    "Troms": {"fylker": [54, 55], "skred": ["Lyngen", "Tromsø", "Indre Troms", "Sør-Troms"]},
    "Finnmark": {"fylker": [54, 56], "skred": ["Vest-Finnmark", "Nord-Finnmark"]}
}

# --- 2. DATA-HENTING (NVE API01) ---
def hent_alle_nve_varsler(distrikt_navn):
    config = DISTRIKT_MAP.get(distrikt_navn, {"fylker": [50], "skred": []})
    alle_varsler = []
    
    # A) FLOM OG JORDSKRED (Kommunevis fra api01.nve.no)
    for f_nr in config["fylker"]:
        url = f"https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/{f_nr}"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                for v in r.json():
                    if v.get('ActivityLevel', 1) > 1:
                        alle_varsler.append({
                            "Område": v['MunicipalityName'],
                            "Nivå": v['ActivityLevel'],
                            "Type": "Flom/Jordskred",
                            "Beskrivelse": v['MainText']
                        })
        except: pass
    
    # B) SNØSKRED (Regionvis fra api01.nve.no)
    for region in config["skred"]:
        url = f"https://api01.nve.no/hydrology/forecast/avalanche/v1.0.0/api/AvalancheWarningByRegion/Detail/{region}/1"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()[0]
                nivaa = int(data.get('DangerLevel', 1))
                if nivaa > 1:
                    alle_varsler.append({
                        "Område": region,
                        "Nivå": nivaa,
                        "Type": "SNØSKRED",
                        "Beskrivelse": data.get('MainText', 'Se varsom.no for detaljer.')
                    })
        except: pass
        
    return alle_varsler

def hent_skogbrannfare_lokal(lat, lon):
    url = f"https://api.met.no/weatherapi/firehazard/2.0/compact?lat={lat}&lon={lon}"
    headers = {'User-Agent': 'NF_Beredskap_App_v2.6_PRO'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()['properties']['timeseries'][0]['fire_hazard_index']
    except: return None

# --- 3. LOGO OG LAGRING ---
def hent_logo_base64():
    for ext in ["png", "jpg", "jpeg"]:
        path = f"nf_logo.{ext}"
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode(), ext
    return None, None

def last_alt():
    default = {
        "nivaa": "🟢 Grønn / Normal", "beskjed": "Alt ok.", "vakt": "9XX XX XXX", 
        "leder": "Ikke satt", "distrikt": "Troms", "talegruppe": "FOR-TROMS-1", 
        "oppmote": "Depot Tromsø", "valgt_kort": "Ingen", "aktive_oppdrag": "Vakt,Trening",
        "lat": "69.6492", "lon": "18.9553"
    }
    if os.path.exists("beredskap_data.txt"):
        try:
            with open("beredskap_data.txt", "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    for p in content.split(";"):
                        if "|" in p: k, v = p.split("|"); default[k] = v
        except: pass
    return default

def lagre_alt(data_dict):
    string_data = ";".join([f"{k}|{v}" for k, v in data_dict.items()])
    with open("beredskap_data.txt", "w", encoding="utf-8") as f:
        f.write(string_data)

def lagre_utrykning(data):
    file_exists = os.path.isfile("aksjonslogg.csv")
    pd.DataFrame([data]).to_csv("aksjonslogg.csv", mode='a', index=False, header=not file_exists, encoding="utf-8")

# --- 4. HOVEDAPP ---
st.set_page_config(page_title="NF Beredskap v2.6", layout="wide")
d = last_alt()
logo_b64, logo_ext = hent_logo_base64()

# Header
if logo_b64:
    st.markdown(f'<div style="text-align:center; margin-top:-30px;"><img src="data:image/{logo_ext};base64,{logo_b64}" style="width:100%; max-width:1000px;"></div>', unsafe_allow_html=True)
else:
    st.title("🚑 Norsk Folkehjelp Beredskap")

st.write("---")

# Hovedstatus (Lederens vurdering)
farge_leder = "#28a745"
if "🟡" in d['nivaa']: farge_leder = "#ffc107"
elif "🔴" in d['nivaa']: farge_leder = "#dc3545"

st.markdown(f"""
    <div style="background-color:{farge_leder}; padding:25px; border-radius:15px; text-align:center; color:white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin:0; font-size:2.5rem;">{d['nivaa']}</h1>
        <p style="font-size:1.3rem; margin-top:10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. VARSLING (FLOM, JORDSKRED OG SNØSKRED) ---
st.write("")
st.subheader(f"⚠️ Aktive farevarsler: {d['distrikt']} Politidistrikt")

varsler = hent_alle_nve_varsler(d['distrikt'])
brannfare = hent_skogbrannfare_lokal(d['lat'], d['lon'])

col_v1, col_v2 = st.columns([2, 1])

with col_v1:
    if varsler:
        df = pd.DataFrame(varsler).sort_values(by="Nivå", ascending=False)
        
        def fargelegg_fare(row):
            farger = {2: ("#FFFF00", "#000000"), 3: ("#FF9900", "#FFFFFF"), 4: ("#FF0000", "#FFFFFF"), 5: ("#000000", "#FFFFFF")}
            bg, txt = farger.get(row.Nivå, ("#28a745", "#ffffff"))
            return [f'background-color: {bg}; color: {txt}; font-weight: bold'] * len(row)

        st.dataframe(df.style.apply(fargelegg_fare, axis=1), use_container_width=True, hide_index=True)
    else:
        st.success(f"✅ Ingen aktive farevarsler (Flom/Skred/Snø) i {d['distrikt']}.")

with col_v2:
    st.subheader("🔥 Skogbrannfare (MET)")
    if brannfare is not None:
        b_bg = "green" if brannfare <= 1 else "orange" if brannfare <= 3 else "red"
        st.markdown(f'<div style="background-color:{b_bg}; color:white; padding:20px; border-radius:10px; text-align:center; font-weight:bold; font-size:1.4rem;">BRANNINDEKS: {brannfare}</div>', unsafe_allow_html=True)
    else:
        st.info("Henter lokale data...")

# --- 6. DASHBORD ---
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}\n\n**Leder:** {d['leder']}")
with c2:
    st.subheader("📻 Operativt")
    st.info(f"**TG:** `{d['talegruppe']}`\n\n**Sted:** {d['oppmote']}")
with c3:
    st.subheader("📋 Status")
    if d['valgt_kort'] != "Ingen": st.error(f"KORT AKTIVT: {d['valgt_kort']}")
    else: st.write("Normaldrift")

# --- 7. REGISTRERING OG ADMIN ---
with st.expander("📝 Registrer deltakelse"):
    oppdrag_valg = d.get('aktive_oppdrag', 'Vakt').split(',')
    with st.form("reg_form", clear_on_submit=True):
        navn = st.text_input("Navn")
        valgt_op = st.selectbox("Oppdrag", oppdrag_valg)
        if st.form_submit_button("Send inn"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": valgt_op})
            st.success("Registrert!")

with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        ca, cb = st.columns(2)
        with ca:
            n_distrikt = st.selectbox("Politidistrikt:", list(DISTRIKT_MAP.keys()), index=list(DISTRIKT_MAP.keys()).index(d.get('distrikt', 'Troms')))
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], index=0)
        with cb:
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Snøskred", "Jordras", "Ekom-bortfall", "Strømbrudd"])
            n_oppdrag = st.text_input("Aktive oppdrag (separer m/komma)", value=d.get('aktive_oppdrag', 'Vakt,Trening'))

        if st.button("LAGRE ALT"):
            d.update({"distrikt": n_distrikt, "nivaa": n_nivaa, "beskjed": n_beskjed, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d)
            st.rerun()
