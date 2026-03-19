import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA (OPPDATERT FOR SKY-DRIFT) ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v1.4'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_varsom_status_kommune(kommune_navn):
    # Henter fylkesoversikt for Trøndelag (Fylke 50) som er mest stabil i skyen
    url = "https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/50"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for k in data:
                if kommune_navn.lower() in k.get('MunicipalityName', '').lower():
                    return k.get('ActivityLevel', 1), k.get('MainText', 'Ingen varsler.')
    except: pass
    return 1, "Data utilgjengelig"

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
                        if "|" in p:
                            k, v = p.split("|")
                            default[k] = v
        except: pass
    return default

def lagre_utrykning(data):
    file_exists = os.path.isfile("aksjonslogg.csv")
    pd.DataFrame([data]).to_csv("aksjonslogg.csv", mode='a', index=False, header=not file_exists, encoding="utf-8")

# --- 3. OPPSETT ---
st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
temp, vind = hent_vaer_melhus()

# Henter varsel for Melhus og naboer
m_nivaa, m_tekst = hent_varsom_status_kommune("Melhus")
s_nivaa, s_tekst = hent_varsom_status_kommune("Skaun")
mg_nivaa, mg_tekst = hent_varsom_status_kommune("Midtre Gauldal")

st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# --- 4. HOVEDSTATUS ---
farge = "#28a745"
if "🟡" in d['nivaa']: farge = "#ffc107"
elif "🔴" in d['nivaa']: farge = "#dc3545"

st.markdown(f"""
    <div style="background-color: {farge}; padding: 25px; border-radius: 15px; text-align: center; color: white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin: 0; font-size: 2.5rem;">{d['nivaa']}</h1>
        <p style="font-size: 1.3rem; margin-top: 10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. TILTAKSKORT (HVIS AKTIVT) ---
if d['valgt_kort'] != "Ingen":
    st.write("")
    st.error(f"📋 **AKTIVT TILTAKSKORT: {d['valgt_kort'].upper()}**")
    with st.expander("Se detaljerte instruksjoner", expanded=True):
        if d['valgt_kort'] == "Jordras":
            st.write("- **Sikkerhet:** Fare for sekundærras. Etabler sikkerhetssone.")
            st.write("- **Varsling:** Bekreft varsling til Politi/HRS.")
        elif d['valgt_kort'] == "Ekom-bortfall":
            st.write("- **Samband:** Bruk Nødnett/Satellitt. Etabler fysiske meldepunkter.")
        # Legg til flere kort her ved behov

# --- 6. NATURFARE-OVERSIKT (NABOKOMMUNER) ---
st.write("")
with st.expander("📊 Status Naturfare (Varsom / NVE)", expanded=False):
    c1, c2, c3 = st.columns(3)
    def vis_varsel(nivaa, tekst, navn):
        if nivaa > 1: st.warning(f"**{navn}:** Nivå {nivaa}\n\n{tekst}")
        else: st.success(f"**{navn}:** Normalt")
    
    with c1: vis_varsel(m_nivaa, m_tekst, "Melhus")
    with c2: vis_varsel(mg_nivaa, mg_tekst, "M. Gauldal")
    with c3: vis_varsel(s_nivaa, s_tekst, "Skaun")

# --- 7. DASHBORD: INFO OG KONTAKT ---
st.write("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("🌦️ Været i Melhus")
    st.metric("Temp", f"{temp} °C"); st.metric("Vind", f"{vind} m/s")
with col2:
    st.subheader("📞 Kontaktpunkt")
    st.write(f"**Vakt:** {d['vakt']}\n\n**Leder:** {d['leder']}")
with col3:
    st.subheader("📻 Operativ Info")
    st.info(f"**TG:** `{d['talegruppe']}`\n**Leder:** {d['operativ_leder']}\n**Sted:** {d['oppmote']}")

# --- 8. REGISTRERING ---
st.write("---")
st.header("📝 Registrer deltakelse")
oppdrags_liste = d.get('aktive_oppdrag', 'Trening,Vakt,Annet').split(',')
with st.expander("Åpne skjema"):
    with st.form("aksjon_form", clear_on_submit=True):
        navn = st.text_input("Ditt navn")
        oppdrag = st.selectbox("Oppdrag", oppdrags_liste)
        c1, c2 = st.columns(2)
        t_u = c1.text_input("Tid ut"); t_i = c2.text_input("Tid inn")
        km = st.number_input("KM", min_value=0); ut = st.number_input("Utlegg", min_value=0)
        if st.form_submit_button("SEND INN"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": oppdrag, "Ut": t_u, "Inn": t_i, "KM": km, "Utlegg": ut})
            st.success("Registrert!")

# --- 9. ADMIN ---
st.write("---")
with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("VIS LOGG"):
            if os.path.exists("aksjonslogg.csv"): st.dataframe(pd.read_csv("aksjonslogg.csv"))
        
        ca, cb = st.columns(2)
        with ca:
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], index=0)
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"], index=0)
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separert med komma)", value=d.get('aktive_oppdrag', 'Trening,Vakt,Annet'))
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])

        if st.button("LAGRE ALT"):
            d.update({"nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, 
                      "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, 
                      "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d)
            st.rerun()
