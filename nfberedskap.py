import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA ---

def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App v1.7'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_alle_farevarsler():
    varsler = []
    # Melhus (5028), Midtre Gauldal (5027), Skaun (5029)
    kommuner = {"5028": "Melhus", "5027": "M.Gauldal", "5029": "Skaun"}
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App v1.7'}
    
    # 1. NVE Sjekk (Flom og Jordskred)
    for k_id, k_navn in kommuner.items():
        for t_id in ["flood", "landslide"]:
            url = f"https://api01.nve.no/hydrology/forecast/{t_id}/v1.0.0/api/CountyOverview/{k_id}"
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    d = r.json()
                    if d:
                        lvl = d[0].get('ActivityLevel', 1)
                        t_navn = "Flom" if t_id == "flood" else "Jordskred"
                        ikon = "🟢" if lvl == 1 else ("🟡" if lvl == 2 else "🟠" if lvl == 3 else "🔴")
                        varsler.append(f"{ikon} {k_navn}: {t_navn} (Nivå {lvl})")
                else: varsler.append(f"⚪ {k_navn}: {t_navn} (Utilgjengelig)")
            except: varsler.append(f"❌ Feil ved henting av {k_navn}")

    # 2. MET Sjekk (Skogbrann, Vind, Regn)
    met_url = "https://api.met.no/weatherapi/metalerts/1.1/.json?lat=63.2859&lon=10.2781"
    try:
        r_met = requests.get(met_url, headers=headers, timeout=5)
        if r_met.status_code == 200:
            met_data = r_met.json()
            features = met_data.get('features', [])
            if features:
                for feature in features:
                    p = feature['properties']
                    farge = p.get('riskMatrixColor', 'Yellow')
                    ikon = "🟡" if farge == "Yellow" else ("🟠" if farge == "Orange" else "🔴")
                    varsler.append(f"{ikon} MET: {p.get('event', 'Farevarsel').upper()}")
            else: varsler.append("🟢 MET: Ingen aktive vær- eller brannvarsler")
    except: varsler.append("❌ MET: Systemfeil")
    
    return varsler

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
                content = f.read()
                if content:
                    for p in content.split(";"):
                        if "|" in p: k, v = p.split("|"); default[k] = v
        except: pass
    return default

def lagre_utrykning(data):
    file_exists = os.path.isfile("aksjonslogg.csv")
    pd.DataFrame([data]).to_csv("aksjonslogg.csv", mode='a', index=False, header=not file_exists, encoding="utf-8")

# --- 3. OPPSETT OG LAYOUT ---

st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
alle_varsler = hent_alle_farevarsler()
temp, vind = hent_vaer_melhus()

st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# Hovedstatus (Lederens beslutning)
farge = "#28a745" if "🟢" in d['nivaa'] else ("#ffc107" if "🟡" in d['nivaa'] else "#dc3545")
st.markdown(f"""
    <div style="background-color: {farge}; padding: 20px; border-radius: 15px; text-align: center; color: white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin: 0; font-size: 2.2rem;">{d['nivaa']}</h1>
        <p style="font-size: 1.2rem; margin-top: 10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# Naturfare-oversikt (Alltid synlig)
st.write("")
with st.expander("📡 Status Naturfare (NVE / MET)", expanded=True):
    v_col1, v_col2 = st.columns(2)
    for i, v in enumerate(alle_varsler):
        if i % 2 == 0: v_col1.write(v)
        else: v_col2.write(v)

# Aktivt Tiltakskort
if d['valgt_kort'] != "Ingen":
    st.write("")
    st.markdown(f"""<div style="border: 3px solid #dc3545; padding: 20px; border-radius: 10px; background-color: #fff5f5;">
    <h3 style="color: #dc3545; margin: 0;">📋 TILTAKSKORT: {d['valgt_kort'].upper()}</h3>""", unsafe_allow_html=True)
    if d['valgt_kort'] == "Jordras":
        st.write("- Etabler sikkerhetssone.\n- Varsle Politi/HRS.\n- Start registrering av evakuerte.")
    elif d['valgt_kort'] == "Skogbrann":
        st.write("- Monitorer vindretning.\n- Etabler møteplass for brannvesen.\n- Klargjør vanntransport.")
    elif d['valgt_kort'] == "Ekom-bortfall":
        st.write("- Aktiver nødnett (faste TG).\n- Etabler meldepunkter i isolerte kretser.\n- Sjekk batterikapasitet på utstyr.")
    st.markdown("</div>", unsafe_allow_html=True)

# Dashbord: Info
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("🌦️ Været")
    st.write(f"**Temp:** {temp}°C | **Vind:** {vind} m/s")
with c2:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}\n**Leder:** {d['leder']}")
with c3:
    st.subheader("📻 Operativt")
    st.info(f"**TG:** `{d['talegruppe']}`\n**Leder:** {d['operativ_leder']}\n**Sted:** {d['oppmote']}")

# --- 4. REGISTRERING ---
st.write("---")
st.header("📝 Registrering av deltakelse")
oppdrags_liste = d.get('aktive_oppdrag', 'Trening,Vakt,Annet').split(',')
with st.expander("Åpne registreringsskjema"):
    with st.form("reg_form", clear_on_submit=True):
        navn = st.text_input("Navn"); oppdrag = st.selectbox("Oppdrag", oppdrags_liste)
        t_u = st.text_input("Ut (HH:MM)"); t_i = st.text_input("Inn (HH:MM)")
        km = st.number_input("KM", min_value=0); ut = st.number_input("Utlegg", min_value=0)
        if st.form_submit_button("SEND INN"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": oppdrag, "Ut": t_u, "Inn": t_i, "KM": km, "Utlegg": ut})
            st.success(f"Takk, {navn}! Registrert.")

# --- 5. ADMIN ---
st.write("---")
with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("HENT UT LOGG (CSV)"):
            if os.path.exists("aksjonslogg.csv"): st.dataframe(pd.read_csv("aksjonslogg.csv"))
        
        st.markdown("### Oppdater innhold")
        ca, cb = st.columns(2)
        with ca:
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], index=0)
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Jordras", "Skogbrann", "Evakuering", "Strømbrudd", "Ekom-bortfall"], index=0)
            n_oppdrag = st.text_input("Aktive oppdrag (separer m/komma)", value=d['aktive_oppdrag'])
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])
        
        if st.button("LAGRE ALLE ENDRINGER"):
            d.update({"nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d); st.rerun()
