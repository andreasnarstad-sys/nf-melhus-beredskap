import streamlit as st
import os
import requests
import pandas as pd
import base64
from datetime import datetime

# --- 1. KONFIGURASJON: MAPPING AV DISTRIKT (NVE & MET) ---
DISTRIKT_MAP = {
    "Troms": {"fylker": [54, 55], "met_navn": "Troms", "skred": ["Lyngen", "Tromsø", "Indre Troms", "Sør-Troms", "Nord-Troms", "Senja"]},
    "Finnmark": {"fylker": [54, 56], "met_navn": "Finnmark", "skred": ["Vest-Finnmark", "Nord-Finnmark", "Øst-Finnmark"]},
    "Nordland": {"fylker": [18], "met_navn": "Nordland", "skred": ["Ofoten", "Salten", "Svartisen", "Helgeland", "Lofoten", "Vesterålen"]},
    "Trøndelag": {"fylker": [50], "met_navn": "Trøndelag", "skred": ["Trollheimen"]},
    "Møre og Romsdal": {"fylker": [15], "met_navn": "Møre og Romsdal", "skred": ["Sunnmøre", "Romsdal"]},
    "Vest": {"fylker": [46], "met_navn": "Vestland", "skred": ["Hardanger", "Voss", "Indre Sogn", "Indre Fjordane"]},
    "Sør-Vest": {"fylker": [11, 42], "met_navn": "Rogaland", "skred": ["Heiane"]},
    "Agder": {"fylker": [42], "met_navn": "Agder", "skred": []},
    "Sør-Øst": {"fylker": [38, 33], "met_navn": "Vestfold og Telemark", "skred": ["Telemark"]},
    "Innlandet": {"fylker": [34], "met_navn": "Innlandet", "skred": ["Jotunheimen", "Rondane"]},
    "Øst": {"fylker": [3, 34], "met_navn": "Viken", "skred": []},
    "Oslo": {"fylker": [3], "met_navn": "Oslo", "skred": []}
}

# --- 2. DATA-HENTING (NVE & MET) ---
def hent_alle_varsler(distrikt_navn):
    config = DISTRIKT_MAP.get(distrikt_navn, {"fylker": [50], "met_navn": "Trøndelag", "skred": []})
    funnede = []

    # A) NVE: Flom og Jordskred (api01)
    for f_nr in config["fylker"]:
        url = f"https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/{f_nr}"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                for v in r.json():
                    nivaa = v.get('ActivityLevel', 1)
                    if nivaa > 1:
                        funnede.append({"Område": v['MunicipalityName'], "Nivå": nivaa, "Type": "Flom/Skred", "Info": v.get('MainText', '')})
        except: pass

    # B) NVE: Snøskred (api01 - Regionvis)
    for reg in config["skred"]:
        url = f"https://api01.nve.no/hydrology/forecast/avalanche/v1.0.0/api/AvalancheWarningByRegion/Detail/{reg}/1"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data:
                    nivaa = int(data[0].get('DangerLevel', 1))
                    if nivaa > 1:
                        funnede.append({"Område": f"REGION: {reg}", "Nivå": nivaa, "Type": "SNØSKRED", "Info": data[0].get('MainText', '')})
        except: pass

    # C) MET: Meteorologiske farevarsler (Vind, Is, Snø, Lyn)
    met_url = "https://api.met.no/weatherapi/metalerts/1.1/.json"
    headers = {'User-Agent': 'NF_Beredskap_App_v3.0'}
    try:
        r = requests.get(met_url, headers=headers, timeout=5)
        if r.status_code == 200:
            alerts = r.json().get('features', [])
            for alert in alerts:
                props = alert.get('properties', {})
                if config["met_navn"].lower() in props.get('area', '').lower():
                    risk_map = {"Moderate": 2, "Severe": 3, "Extreme": 4}
                    nivaa = risk_map.get(props.get('riskLevel'), 2)
                    funnede.append({
                        "Område": props.get('area', 'Lokalt'),
                        "Nivå": nivaa,
                        "Type": f"MET: {props.get('event', 'Vær')}".upper(),
                        "Info": props.get('description', '')
                    })
    except: pass
    return funnede

# --- 3. HJELPEFUNKSJONER ---
def hent_logo_base64():
    for ext in ["png", "jpg", "jpeg"]:
        if os.path.exists(f"nf_logo.{ext}"):
            with open(f"nf_logo.{ext}", "rb") as f:
                return base64.b64encode(f.read()).decode(), ext
    return None, None

def last_data():
    d = {"nivaa": "🟢 Normal", "beskjed": "Alt ok.", "distrikt": "Troms", "vakt": "9XX XX XXX", "leder": "Ikke satt", "oppmote": "Depot", "kort": "Ingen"}
    if os.path.exists("beredskap_data.txt"):
        try:
            with open("beredskap_data.txt", "r", encoding="utf-8") as f:
                for p in f.read().split(";"):
                    if "|" in p: k, v = p.split("|"); d[k] = v
        except: pass
    return d

def lagre_data(d):
    with open("beredskap_data.txt", "w", encoding="utf-8") as f:
        f.write(";".join([f"{k}|{v}" for k, v in d.items()]))

# --- 4. HOVEDAPP ---
st.set_page_config(page_title="NF Beredskap v3.0", layout="wide")
d = last_data()
logo_b64, logo_ext = hent_logo_base64()

if logo_b64:
    st.markdown(f'<div style="text-align:center; margin-top:-30px;"><img src="data:image/{logo_ext};base64,{logo_b64}" style="width:100%; max-width:1000px;"></div>', unsafe_allow_html=True)
else:
    st.title("🚑 Norsk Folkehjelp Beredskap")

st.write("---")

# Hovedstatus-banner
f_banner = "#28a745"
if "🟡" in d['nivaa']: f_banner = "#ffc107"
elif "🔴" in d['nivaa']: f_banner = "#dc3545"
st.markdown(f'<div style="background-color:{f_banner}; padding:20px; border-radius:15px; text-align:center; color:white; border: 2px solid rgba(0,0,0,0.1);"><h1>{d["nivaa"]}</h1><p style="font-size:1.2rem;">{d["beskjed"]}</p></div>', unsafe_allow_html=True)

# --- 5. VISNING AV FAREBILDE (NVE + MET) ---
st.write("")
st.subheader(f"⚠️ Situasjonsbilde: {d['distrikt']} Politidistrikt")

alle_varsler = hent_alle_varsler(d['distrikt'])

if alle_varsler:
    df = pd.DataFrame(alle_varsler).sort_values(by="Nivå", ascending=False)
    
    def style_fare(row):
        colors = {2: ("#FFFF00", "#000000"), 3: ("#FF9900", "#FFFFFF"), 4: ("#FF0000", "#FFFFFF"), 5: ("#000000", "#FFFFFF")}
        bg, txt = colors.get(row.Nivå, ("#28a745", "#ffffff"))
        return [f'background-color: {bg}; color: {txt}; font-weight: bold'] * len(row)

    st.dataframe(df.style.apply(style_fare, axis=1), use_container_width=True, hide_index=True)
else:
    st.success(f"✅ Ingen aktive farevarsler fra NVE eller MET i {d['distrikt']} akkurat nå.")

# --- 6. OPERATIV DASHBORD ---
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.write(f"**📞 Vakttelefon:** {d['vakt']}")
    st.write(f"**👤 Beredskapsleder:** {d['leder']}")
with c2:
    st.info(f"**📍 Oppmøtested:**\n{d['oppmote']}")
with c3:
    if d['kort'] != "Ingen":
        st.error(f"📋 **AKTIVT TILTAKSKORT:**\n{d['kort']}")
    else:
        st.write("✅ Ingen aktive tiltakskort.")

# --- 7. ADMIN ---
st.write("---")
with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        c1, c2 = st.columns(2)
        with c1:
            n_dist = st.selectbox("Politidistrikt:", list(DISTRIKT_MAP.keys()), index=list(DISTRIKT_MAP.keys()).index(d['distrikt']))
            n_niv = st.selectbox("Beredskapsstatus:", ["🟢 Normal", "🟡 Forhøyhet", "🔴 Rød / Aksjon"])
            n_besk = st.text_area("Beskjed til mannskap", value=d['beskjed'])
        with c2:
            n_vak = st.text_input("Vakttelefon", value=d['vakt'])
            n_led = st.text_input("Leder", value=d['leder'])
            n_opp = st.text_input("Oppmøtested", value=d['oppmote'])
            n_kor = st.selectbox("Tiltakskort:", ["Ingen", "Snøskred", "Jordras", "Ekom-bortfall", "Isolasjon", "Ekstremvær"])

        if st.button("OPPDATER TAVLE"):
            d.update({"distrikt": n_dist, "nivaa": n_niv, "beskjed": n_besk, "vakt": n_vak, "leder": n_led, "oppmote": n_opp, "kort": n_kor})
            lagre_data(d)
            st.rerun()
