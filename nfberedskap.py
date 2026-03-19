import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App v1.6'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_alle_farevarsler():
    # Sjekker NVE (Flom, Jord, Snø) og MET (Brann, Vind, Regn)
    varsler = []
    # Vi fokuserer primært på Melhus, men sjekker nabokommuner for flom/jord
    kommuner = {"5028": "Melhus", "5027": "M.Gauldal", "5029": "Skaun"}
    
    # 1. NVE Sjekk (Viser nå ALLE nivåer)
    for k_id, k_navn in kommuner.items():
        for t_id in ["flood", "landslide", "avalanche"]:
            url = f"https://api01.nve.no/hydrology/forecast/{t_id}/v1.0.0/api/CountyOverview/{k_id}"
            try:
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    d = r.json()
                    if d:
                        lvl = d[0]['ActivityLevel']
                        t_navn = "Flom" if t_id == "flood" else ("Jordskred" if t_id == "landslide" else "Snøskred")
                        ikon = "🟢" if lvl == 1 else ("🟡" if lvl == 2 else "🟠" if lvl == 3 else "🔴")
                        varsler.append(f"{ikon} {k_navn}: {t_navn} (Nivå {lvl})")
            except: pass

    # 2. MET Sjekk (Farevarsler for vær og brann)
    met_url = "https://api.met.no/weatherapi/metalerts/1.1/.json?lat=63.2859&lon=10.2781"
    try:
        r_met = requests.get(met_url, headers={'User-Agent': 'NF_Melhus'}, timeout=5)
        if r_met.status_code == 200:
            met_data = r_met.json()
            features = met_data.get('features', [])
            if features:
                for feature in features:
                    props = feature['properties']
                    event = props.get('event', 'Farevarsel').upper()
                    varsler.append(f"⚠️ MET: {event}")
            else:
                varsler.append("🟢 MET: Ingen aktive vær- eller brannvarsler")
    except: pass
    
    return varsler

# --- 2. LAGRING OG OPPSETT (Uendret) ---
def lagre_alt(data_dict):
    string_data = ";".join([f"{k}|{v}" for k, v in data_dict.items()])
    with open("beredskap_data.txt", "w", encoding="utf-8") as f:
        f.write(string_data)

def last_alt():
    default = {"nivaa": "🟢 Grønn / Normal", "beskjed": "Alt ok.", "vakt": "9XX XX XXX", "leder": "Ikke satt", "sanitet": "Ikke satt", "talegruppe": "FOR-MELHUS-1", "operativ_leder": "Ikke satt", "oppmote": "Depot Melhus", "valgt_kort": "Ingen", "aktive_oppdrag": "Trening,Vakt,Annet"}
    if os.path.exists("beredskap_data.txt"):
        try:
            with open("beredskap_data.txt", "r", encoding="utf-8") as f:
                for p in f.read().split(";"):
                    if "|" in p: k, v = p.split("|"); default[k] = v
        except: pass
    return default

st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
alle_varsler = hent_alle_farevarsler()
temp, vind = hent_vaer_melhus()

# --- 3. VISNING ---
st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# Hovedstatus
farge = "#28a745" if "🟢" in d['nivaa'] else ("#ffc107" if "🟡" in d['nivaa'] else "#dc3545")
st.markdown(f'<div style="background-color: {farge}; padding: 20px; border-radius: 15px; text-align: center; color: white;"><h1>{d['nivaa']}</h1><p>{d['beskjed']}</p></div>', unsafe_allow_html=True)

# NATURFARE-OVERSIKT (Vises alltid)
st.write("")
with st.expander("📡 Status Naturfare (NVE / MET)", expanded=True):
    cols = st.columns(2)
    for i, v in enumerate(alle_varsler):
        cols[i % 2].write(v)

# --- RESTEN AV APPEN (Dashboard, Registrering, Admin) ---
# ... (Samme som i forrige versjon)
