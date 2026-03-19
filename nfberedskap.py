import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App v1.3'}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_varsom_status():
    url = "https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/5028"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if data: return data[0].get('ActivityLevel', 1), data[0].get('MainText', 'Ingen aktive varsler.')
    except: pass
    return 1, "Informasjon utilgjengelig."

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
v_nivaa, v_melding = hent_varsom_status()
temp, vind = hent_vaer_melhus()

st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# --- 4. HOVEDSTATUS OG TILTAKSKORT ---
# Fargevalg basert på status
farge = "#28a745"
if "🟡" in d['nivaa']: farge = "#ffc107"
elif "🔴" in d['nivaa']: farge = "#dc3545"

st.markdown(f"""
    <div style="background-color: {farge}; padding: 25px; border-radius: 15px; text-align: center; color: white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin: 0; font-size: 2.5rem;">{d['nivaa']}</h1>
        <p style="font-size: 1.3rem; margin-top: 10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

if d['valgt_kort'] != "Ingen":
    st.write("")
    st.markdown(f"""
        <div style="border: 3px solid #dc3545; padding: 20px; border-radius: 10px; background-color: #fff5f5;">
            <h3 style="color: #dc3545; margin-top: 0;">📋 AKTIVT TILTAKSKORT: {d['valgt_kort'].upper()}</h3>
    """, unsafe_allow_html=True)
    if d['valgt_kort'] == "Jordras":
        st.write("- **Sikkerhet:** Etabler sikkerhetssone, vurder sekundærras.\n- **Varsling:** Bekreft varsling til Politi/HRS.")
    elif d['valgt_kort'] == "Ekom-bortfall":
        st.write("- **Samband:** Bruk Nødnett/Satellitt.\n- **Oppmøte:** Etabler fysiske meldepunkter i kretser.")
    elif d['valgt_kort'] == "Strømbrudd":
        st.write("- **Aggregat:** Start backup på depot.\n- **Sårbarhet:** Kontakt hjemmetjeneste for pasientliste.")
    st.markdown("</div>", unsafe_allow_html=True)

# --- 5. DASHBORD ---
st.write("")
col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("🌦️ Vær & Varsom")
    st.write(f"**Temp:** {temp}°C | **Vind:** {vind}m/s")
    if v_nivaa > 1: st.warning(f"Varsom: {v_melding}")
    else: st.success("Ingen farevarsler fra NVE")
with col2:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}\n\n**Beredskapsleder:** {d['leder']}")
with col3:
    st.subheader("📻 Operativt")
    st.info(f"**TG:** `{d['talegruppe']}`\n**Leder:** {d['operativ_leder']}\n**Sted:** {d['oppmote']}")

# --- 6. REGISTRER DELTAKELSE ---
st.write("---")
st.header("📝 Registrer din deltakelse")
oppdrags_liste = d.get('aktive_oppdrag', 'Trening,Vakt,Annet').split(',')

with st.expander("Åpne registreringsskjema"):
    with st.form("aksjon_form", clear_on_submit=True):
        navn = st.text_input("Ditt navn")
        oppdrag = st.selectbox("Hvilket oppdrag/aksjon gjelder dette?", oppdrags_liste)
        c1, c2 = st.columns(2)
        t_ut = c1.text_input("Tid ut (HH:MM)")
        t_inn = c2.text_input("Tid inn (HH:MM)")
        km = st.number_input("Kjørte KM", min_value=0)
        privat = st.checkbox("Brukt privatbil?")
        utlegg = st.number_input("Utlegg (kr)", min_value=0)
        
        if st.form_submit_button("SEND INN REGISTRERING"):
            l_data = {"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": oppdrag, "Ut": t_ut, "Inn": t_inn, "KM": km, "Privat": privat, "Utlegg": utlegg}
            lagre_utrykning(l_data)
            st.success(f"Registrert på {oppdrag}!")

# --- 7. ADMIN (FORBEDRET LOGIKK) ---
st.write("---")
with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("VIS LOGG / EXCEL"):
            if os.path.exists("aksjonslogg.csv"): 
                df = pd.read_csv("aksjonslogg.csv")
                st.dataframe(df)
                st.download_button("Last ned CSV", df.to_csv(index=False), "aksjonslogg.csv")
        
        st.write("---")
        st.markdown("### Oppdater alt innhold")
        ca, cb = st.columns(2)
        
        # Sikker sjekk for index-feil
        status_valg = ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"]
        try:
            status_idx = status_valg.index(d['nivaa'])
        except:
            status_idx = 0

        with ca:
            n_nivaa = st.selectbox("Beredskapsnivå:", status_valg, index=status_idx)
            n_kort = st.selectbox("Aktivt tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"], 
                                  index=["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"].index(d.get('valgt_kort', 'Ingen')))
            n_beskjed = st.text_area("Melding til mannskap", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separer med komma)", value=d.get('aktive_oppdrag', 'Trening,Vakt,Annet'))
        
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])

        if st.button("LAGRE ALLE ENDRINGER"):
            oppdatert_data = {
                "nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, 
                "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, 
                "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag
            }
            lagre_alt(oppdatert_data)
            st.success("Alle data er lagret!")
            st.rerun()