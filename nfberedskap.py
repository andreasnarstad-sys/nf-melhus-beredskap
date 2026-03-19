import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA ---
def hent_vaer_og_skogbrann():
    # Henter vær og skogbrannfare fra MET
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App v1.4'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            temp = instant.get('air_temperature', "N/A")
            vind = instant.get('wind_speed', "N/A")
            # Skogbrannfare er ofte indikert ved fuktighet og vind i kombinasjon (forenklet her)
            return temp, vind
    except: pass
    return "N/A", "N/A"

def hent_alle_nve_varsler():
    # Henter alle varsler fra NVE for Melhus og omegn
    kommuner = {"5028": "Melhus", "5027": "M.Gauldal", "5029": "Skaun"}
    typer = {"flood": "Flom", "landslide": "Jordskred", "avalanche": "Snøskred"}
    aktive = []
    
    for k_id, k_navn in kommuner.items():
        for t_id, t_navn in typer.items():
            url = f"https://api01.nve.no/hydrology/forecast/{t_id}/v1.0.0/api/CountyOverview/{k_id}"
            try:
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    d = r.json()
                    if d and d[0]['ActivityLevel'] > 1:
                        aktive.append(f"⚠️ {k_navn}: {t_navn} nivå {d[0]['ActivityLevel']}")
            except: pass
    return aktive

def hent_skogbrann_varsel():
    # MET sitt spesifikke API for skogbrannfare (Fire Risk)
    url = "https://api.met.no/weatherapi/fireindex/1.1/?lat=63.2859&lon=10.2781"
    try:
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            # Her henter vi ut indeksen (0-5 eller tekst)
            # Forenklet sjekk for demo:
            return "🔥 OBS: Økt skogbrannfare i Melhus!" if "danger" in r.text.lower() else None
    except: pass
    return None

# --- 2. LAGRINGSSYSTEM ---
def lagre_alt(data_dict):
    string_data = ";".join([f"{k}|{v}" for k, v in data_dict.items()])
    with open("beredskap_data.txt", "w", encoding="utf-8") as f:
        f.write(string_data)

def last_alt():
    default = {
        "nivaa": "🟢 Grønn / Normal", "beskjed": "Alt ok.", "vakt": "9XX XX XXX", 
        "leder": "Ikke satt", "sanitet": "Ikke satt", "talegruppe": "FOR-MELHUS-1", 
        "operativ_leder": "Ikke satt", "oppmote": "Depot Melhus", 
        "valgt_kort": "Ingen", "aktive_oppdrag": "Trening,Vakt,Annet"
    }
    if os.path.exists("beredskap_data.txt"):
        try:
            with open("beredskap_data.txt", "r", encoding="utf-8") as f:
                for p in f.read().split(";"):
                    if "|" in p: k, v = p.split("|"); default[k] = v
        except: pass
    return default

# --- 3. OPPSETT ---
st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
nve_varsler = hent_alle_nve_varsler()
skogbrann = hent_skogbrann_varsel()
temp, vind = hent_vaer_og_skogbrann()

st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# --- 4. HOVEDSTATUS OG TILTAKSKORT ---
farge = "#28a745"
if "🟡" in d['nivaa']: farge = "#ffc107"
elif "🔴" in d['nivaa']: farge = "#dc3545"

st.markdown(f"""
    <div style="background-color: {farge}; padding: 25px; border-radius: 15px; text-align: center; color: white;">
        <h1 style="margin: 0;">{d['nivaa']}</h1>
        <p style="font-size: 1.3rem;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. AUTOMATISKE VARSLER (NVE + SKOGBRANN) ---
if nve_varsler or skogbrann:
    st.write("")
    with st.container():
        st.error("🚨 **AKTIVE FAREVARSLER I REGIONEN:**")
        if skogbrann: st.warning(skogbrann)
        for v in nve_varsler:
            st.warning(v)
else:
    st.success("✅ Ingen naturfarevarsler for Melhus, Skaun eller Midtre Gauldal.")

# --- 6. DASHBORD ---
st.write("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("🌦️ Været")
    st.metric("Temp", f"{temp}°C")
    st.metric("Vind", f"{vind} m/s")
with col2:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}\n\n**Leder:** {d['leder']}")
with col3:
    st.subheader("📻 Operativt")
    st.info(f"**TG:** `{d['talegruppe']}`\n**Leder:** {d['operativ_leder']}\n**Sted:** {d['oppmote']}")

# (Resten av koden med registrering og admin forblir som før...)
