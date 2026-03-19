import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA (OPPDATERT TIL API01.NVE.NO) ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v1.5'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_alle_varsom_data():
    """Henter flomvarsel for hele Trøndelag fra nyeste API01"""
    url = "https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/50"
    varsler = {}
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for k in data:
                navn = k.get('MunicipalityName')
                if navn in ["Melhus", "Skaun", "Midtre Gauldal"]:
                    varsler[navn] = {
                        "nivaa": k.get('ActivityLevel', 1),
                        "tekst": k.get('MainText', 'Ingen aktive varsler.')
                    }
        return varsler
    except:
        return {}

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
varsom_data = hent_alle_varsom_data()

st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# --- 4. HOVEDSTATUS ---
farge = "#28a745"
if "🟡" in d['nivaa']: farge = "#ffc107"
elif "🔴" in d['nivaa']: farge = "#dc3545"

st.markdown(f"""
    <div style="background-color: {farge}; padding: 25px; border-radius: 15px; text-align: center; color: white;">
        <h1 style="margin: 0;">{d['nivaa']}</h1>
        <p style="font-size: 1.2rem;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. AUTOMATISK TILTAKSKORT ---
if d['valgt_kort'] != "Ingen":
    st.write("")
    st.error(f"📋 **AKTIVT TILTAKSKORT: {d['valgt_kort'].upper()}**")
    with st.expander("Se tiltak", expanded=True):
        if d['valgt_kort'] == "Ekom-bortfall":
            st.write("**1.** Aktiver Nødnett-terminaler og sjekk dekning i isolerte soner.")
            st.write("**2.** Etabler faste meldepunkter (fysisk oppmøte) ved grendehus.")
            st.write("**3.** Vurder behov for satellittsamband mot KO.")
        elif d['valgt_kort'] == "Jordras":
            st.write("**1.** Etabler sikkerhetssone og observasjonspost.")
            st.write("**2.** Start registrering av evakuerte i samarbeid med Politi.")

# --- 6. VARSOM OVERSIKT (API01 DATA) ---
st.write("")
with st.expander("📊 Status Naturfare (Melhus m/naboer)", expanded=False):
    cols = st.columns(3)
    kommuner = ["Melhus", "Midtre Gauldal", "Skaun"]
    for i, kommune in enumerate(kommuner):
        info = varsom_data.get(kommune, {"nivaa": 1, "tekst": "Data utilgjengelig"})
        with cols[i]:
            if info['nivaa'] > 1:
                st.warning(f"**{kommune}:** Nivå {info['nivaa']}\n\n{info['tekst']}")
            else:
                st.success(f"**{kommune}:** Normalt")

# --- 7. DASHBORD ---
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("🌦️ Været")
    st.metric("Temp", f"{temp} °C"); st.metric("Vind", f"{vind} m/s")
with c2:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}\n\n**Leder:** {d['leder']}")
with c3:
    st.subheader("📻 Siste")
    st.info(f"**TG:** `{d['talegruppe']}`\n**Oppmøte:** {d['oppmote']}")

# --- 8. REGISTRERING ---
st.write("---")
st.header("📝 Registrer deltakelse")
oppdrags_liste = d.get('aktive_oppdrag', 'Trening,Vakt,Annet').split(',')
with st.expander("Åpne skjema"):
    with st.form("aksjon_form", clear_on_submit=True):
        navn = st.text_input("Navn")
        oppdrag = st.selectbox("Oppdrag", oppdrags_liste)
        c1, c2 = st.columns(2)
        t_u = c1.text_input("Ut (HH:MM)"); t_i = c2.text_input("Inn (HH:MM)")
        km = st.number_input("KM", min_value=0); ut = st.number_input("Utlegg", min_value=0)
        if st.form_submit_button("SEND INN"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": oppdrag, "Ut": t_u, "Inn": t_i, "KM": km, "Utlegg": ut})
            st.success("Lagret!")

# --- 9. ADMIN ---
st.write("---")
with st.expander("🔐 Admin"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        ca, cb = st.columns(2)
        with ca:
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], index=0)
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd"], index=0)
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separer med komma)", value=d.get('aktive_oppdrag', 'Trening,Vakt'))
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])

        if st.button("OPPDATER"):
            d.update({"nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, 
                      "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, 
                      "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d)
            st.rerun()
