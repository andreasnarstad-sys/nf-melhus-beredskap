import streamlit as st
import os
import requests
import pandas as pd
import base64
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA (MET & NVE API01) ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v2.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_skogbrannfare_melhus():
    url = "https://api.met.no/weatherapi/firehazard/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v2.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data['properties']['timeseries'][0]['fire_hazard_index']
    except: pass
    return None

def hent_alle_varsom_data():
    # Nyeste API01 fra NVE
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
    except: return {}

# --- 2. LOGO-HÅNDTERING (Støtter nå både PNG og JPG) ---
def hent_logo_base64():
    for ext in ["png", "jpg", "jpeg"]:
        path = f"nf_logo.{ext}"
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode(), ext
    return None, None

# --- 3. LAGRINGSSYSTEM ---
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

# --- 4. OPPSETT OG VISUALISERING ---
st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
temp, vind = hent_vaer_melhus()
varsom_data = hent_alle_varsom_data()
brannfare = hent_skogbrannfare_melhus()
logo_b64, logo_ext = hent_logo_base64()

# --- 5. OVERSKRIFT: STOR LOGO ---
if logo_b64:
    st.markdown(f"""
        <div style="display: flex; justify-content: center; width: 100%; margin-top: -30px; padding-bottom: 20px;">
            <img src="data:image/{logo_ext};base64,{logo_b64}" style="width: 100%; max-width: 1000px; height: auto;">
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown("<h1 style='text-align: center; color: #dc3545;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)

st.write("---")

# --- 6. HOVEDSTATUS (LEDEREN BESTEMMER) ---
farge = "#28a745"
if "🟡" in d['nivaa']: farge = "#ffc107"
elif "🔴" in d['nivaa']: farge = "#dc3545"

st.markdown(f"""
    <div style="background-color: {farge}; padding: 25px; border-radius: 15px; text-align: center; color: white;">
        <h1 style="margin: 0; font-size: 2.5rem;">{d['nivaa']}</h1>
        <p style="font-size: 1.3rem; margin-top: 10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 7. AKTIVT TILTAKSKORT ---
if d['valgt_kort'] != "Ingen":
    st.write("")
    st.error(f"📋 **TILTAKSKORT AKTIVERT: {d['valgt_kort'].upper()}**")
    with st.expander("Se prioriterte tiltak nå", expanded=True):
        if d['valgt_kort'] == "Jordras":
            st.write("- **Sikkerhet:** Etabler sikkerhetssone.\n- **Varsling:** Bekreft varsling til Politi/HRS.")
        elif d['valgt_kort'] == "Ekom-bortfall":
            st.write("- **Samband:** Aktiver Nødnett.\n- **Oppmøte:** Etabler fysiske meldepunkter.")
        elif d['valgt_kort'] == "Skogbrann":
            st.write("- **Samvirke:** Kontakt Brann/110.\n- **Logistikk:** Klargjør pumper/vann.")
        elif d['valgt_kort'] == "Strømbrudd":
            st.write("- **Backup:** Start aggregat.\n- **Sårbarhet:** Sjekk pasientlister.")

# --- 8. FAREVARSLER (NVE & MET) ---
st.write("")
col_v1, col_v2 = st.columns([2, 1])

with col_v1:
    with st.expander("📊 Status Naturfare (Varsom)", expanded=False):
        cv = st.columns(3)
        for i, k_navn in enumerate(["Melhus", "Midtre Gauldal", "Skaun"]):
            info = varsom_data.get(k_navn, {"nivaa": 1, "tekst": "Data utilgjengelig"})
            with cv[i]:
                if info['nivaa'] > 1: st.warning(f"**{k_navn}:** Nivå {info['nivaa']}")
                else: st.success(f"**{k_navn}:** Normal")

with col_v2:
    if brannfare is not None:
        if brannfare > 3.0: st.error(f"🔥 **Skogbrannfare:** Høy ({brannfare})")
        elif brannfare > 1.0: st.warning(f"🔥 **Skogbrannfare:** Obs ({brannfare})")
        else: st.success(f"🔥 **Skogbrannfare:** Lav")
    else:
        st.info("🔥 Skogbrannfare: Henter...")

# --- 9. DASHBORD ---
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("🌦️ Været i Melhus")
    st.metric("Temp", f"{temp} °C"); st.metric("Vind", f"{vind} m/s")
with c2:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}\n\n**Leder:** {d['leder']}")
with c3:
    st.subheader("📻 Operativt")
    st.info(f"**TG:** `{d['talegruppe']}`\n\n**Sted:** {d['oppmote']}")

# --- 10. MANNSKAP: REGISTRERING ---
st.write("---")
st.header("📝 Registrer din deltakelse")
oppdrags_liste = d.get('aktive_oppdrag', 'Trening,Vakt,Annet').split(',')

with st.expander("Klikk her for å føre timer og utlegg"):
    with st.form("aksjon_form", clear_on_submit=True):
        navn = st.text_input("Navn")
        oppdrag = st.selectbox("Oppdrag", oppdrags_liste)
        c1, c2 = st.columns(2)
        t_ut = c1.text_input("Ut (HH:MM)"); t_inn = c2.text_input("Inn (HH:MM)")
        km = st.number_input("KM", min_value=0); ut = st.number_input("Utlegg (kr)", min_value=0)
        desc = st.text_input("Info om utlegg")
        if st.form_submit_button("SEND INN"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": oppdrag, "Ut": t_ut, "Inn": t_inn, "KM": km, "Utlegg": ut, "Beskrivelse": desc})
            st.success("Lagret! Takk for innsatsen.")

# --- 11. ADMIN-PANEL ---
st.write("---")
with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("HENT UT LOGG (CSV)"):
            if os.path.exists("aksjonslogg.csv"): 
                df_l = pd.read_csv("aksjonslogg.csv")
                st.dataframe(df_l)
                st.download_button("Last ned Excel-fil", df_l.to_csv(index=False), "logg.csv")
        
        ca, cb = st.columns(2)
        with ca:
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], 
                                   index=["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"].index(d['nivaa']))
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"], 
                                  index=["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"].index(d.get('valgt_kort', 'Ingen')))
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separer m/komma)", value=d.get('aktive_oppdrag', 'Trening,Vakt'))
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])

        if st.button("LAGRE ALLE ENDRINGER"):
            d.update({"nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, 
                      "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, 
                      "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d)
            st.rerun()
