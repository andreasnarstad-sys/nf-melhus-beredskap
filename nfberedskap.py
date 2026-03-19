import streamlit as st
import os
import requests
import pandas as pd
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA (MET & NVE) ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v1.8_andreas'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            instant = data['properties']['timeseries'][0]['data']['instant']['details']
            return instant.get('air_temperature', "N/A"), instant.get('wind_speed', "N/A")
    except: pass
    return "N/A", "N/A"

def hent_skogbrannfare_melhus():
    # MET Firehazard 2.0 API - Spesifikt for Melhus koordinater
    url = "https://api.met.no/weatherapi/firehazard/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v1.8_andreas'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Henter gjeldende indeks (index 0 i tidsserien)
            return data['properties']['timeseries'][0]['fire_hazard_index']
    except: pass
    return None

def hent_alle_varsom_data():
    # Nyeste API01 fra NVE for Trøndelag (Fylke 50)
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

# --- 3. HOVEDOPPSETT ---
st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
temp, vind = hent_vaer_melhus()
varsom_data = hent_alle_varsom_data()
brannfare = hent_skogbrannfare_melhus()

st.markdown("<h1 style='text-align: center;'>🚑 Norsk Folkehjelp Melhus</h1>", unsafe_allow_html=True)
st.write("---")

# --- 4. HOVEDSTATUS (BEREDSKAPSLEDER) ---
farge = "#28a745"
if "🟡" in d['nivaa']: farge = "#ffc107"
elif "🔴" in d['nivaa']: farge = "#dc3545"

st.markdown(f"""
    <div style="background-color: {farge}; padding: 25px; border-radius: 15px; text-align: center; color: white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin: 0; font-size: 2.5rem;">{d['nivaa']}</h1>
        <p style="font-size: 1.3rem; margin-top: 10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. AKTIVT TILTAKSKORT ---
if d['valgt_kort'] != "Ingen":
    st.write("")
    st.error(f"📋 **OPERATIVT TILTAKSKORT AKTIVERT: {d['valgt_kort'].upper()}**")
    with st.expander("Klikk for å se prioriterte tiltak", expanded=True):
        if d['valgt_kort'] == "Jordras":
            st.write("- **Sikkerhet:** Etabler sikkerhetssone, vurder sekundærras.\n- **Varsling:** Bekreft varsling til Politi/HRS.\n- **Evakuering:** Start registrering av personer fra randsone.")
        elif d['valgt_kort'] == "Ekom-bortfall":
            st.write("- **Samband:** Aktiver alle Nødnett-terminaler, bruk faste TG.\n- **Oppmøte:** Etabler fysiske meldepunkter i isolerte kretser.\n- **Informasjon:** Bruk lokalradio/fysiske oppslag ved behov.")
        elif d['valgt_kort'] == "Skogbrann":
            st.write("- **Vind:** Monitorer vindretning kontinuerlig.\n- **Samvirke:** Etabler kontakt med Brannvesen/110.\n- **Logistikk:** Klargjør vanntransport og pumper.")
        elif d['valgt_kort'] == "Strømbrudd":
            st.write("- **Aggregat:** Start opp backup på depot og sjekk drivstoff.\n- **Sårbarhet:** Kontakt hjemmetjeneste for liste over kritiske pasienter.")

# --- 6. VARSEL-OVERSIKT (NABOKOMMUNER & SKOGBRANN) ---
st.write("")
col_v1, col_v2 = st.columns([2, 1])

with col_v1:
    with st.expander("📊 Status Naturfare (Melhus, M.Gauldal, Skaun)", expanded=False):
        cv = st.columns(3)
        kommuner = ["Melhus", "Midtre Gauldal", "Skaun"]
        for i, kommune in enumerate(kommuner):
            info = varsom_data.get(kommune, {"nivaa": 1, "tekst": "Ingen data"})
            with cv[i]:
                if info['nivaa'] > 1: st.warning(f"**{kommune}:** Nivå {info['nivaa']}")
                else: st.success(f"**{kommune}:** Normalt")

with col_v2:
    if brannfare is not None:
        if brannfare > 3.0: st.error(f"🔥 **Skogbrannfare:** Høy ({brannfare})")
        elif brannfare > 1.0: st.warning(f"🔥 **Skogbrannfare:** Moderat ({brannfare})")
        else: st.success(f"🔥 **Skogbrannfare:** Lav")
    else:
        st.info("🔥 Skogbrannfare: Henter data fra MET...")

# --- 7. DASHBORD: KONTAKT OG SAMBAND ---
st.write("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("🌦️ Været i Melhus")
    st.metric("Temp", f"{temp} °C")
    st.metric("Vind", f"{vind} m/s")
with col2:
    st.subheader("📞 Kontaktpunkt")
    st.write(f"**Vakt:** {d['vakt']}")
    st.write(f"**Leder:** {d['leder']}")
    st.write(f"**Sanitet:** {d['sanitet']}")
with col3:
    st.subheader("📻 Operativ Info")
    st.info(f"**TG:** `{d['talegruppe']}`\n\n**Operativ leder:** {d['operativ_leder']}\n\n**Oppmøte:** {d['oppmote']}")

# --- 8. REGISTRERING AV DELTAKELSE ---
st.write("---")
st.header("📝 Registrer din deltakelse")
oppdrags_liste = d.get('aktive_oppdrag', 'Trening,Vakt,Annet').split(',')

with st.expander("Klikk her for å registrere timer, kjøring og utlegg"):
    with st.form("aksjon_form", clear_on_submit=True):
        navn = st.text_input("Fullt navn")
        oppdrag = st.selectbox("Velg oppdrag/aksjon:", oppdrags_liste)
        c1, c2 = st.columns(2)
        t_ut = c1.text_input("Tid ut (HH:MM)")
        t_inn = c2.text_input("Tid inn (HH:MM)")
        km = st.number_input("Kjørte kilometer (totalt)", min_value=0)
        privat = st.checkbox("Brukt privatbil?")
        utlegg = st.number_input("Private utlegg (beløp i kr)", min_value=0)
        info_utlegg = st.text_input("Beskrivelse av utlegg")
        
        if st.form_submit_button("SEND INN REGISTRERING"):
            l_data = {
                "Dato": datetime.now().strftime("%d.%m.%Y"),
                "Navn": navn, "Oppdrag": oppdrag, "Ut": t_ut, "Inn": t_inn,
                "KM": km, "Privat": privat, "Utlegg": utlegg, "Beskrivelse": info_utlegg
            }
            lagre_utrykning(l_data)
            st.success(f"Takk {navn}! Din deltakelse på {oppdrag} er lagret.")

# --- 9. ADMIN-PANEL ---
st.write("---")
with st.expander("🔐 Administrasjon (Kun Beredskapsleder)"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("HENT UT LOGG (EXCEL-FORMAT)"):
            if os.path.exists("aksjonslogg.csv"):
                df_logg = pd.read_csv("aksjonslogg.csv")
                st.dataframe(df_logg)
                st.download_button("Last ned logg", df_logg.to_csv(index=False), "aksjonslogg.csv")
        
        st.write("---")
        st.markdown("### Oppdater operativ status")
        ca, cb = st.columns(2)
        with ca:
            n_nivaa = st.selectbox("Beredskapsnivå:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], 
                                   index=["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"].index(d['nivaa']))
            n_kort = st.selectbox("Aktivt tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"], 
                                  index=["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"].index(d.get('valgt_kort', 'Ingen')))
            n_beskjed = st.text_area("Beskjed til mannskap", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separer med komma)", value=d.get('aktive_oppdrag', 'Trening,Vakt'))
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])

        if st.button("LAGRE ALLE ENDRINGER"):
            d.update({
                "nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, 
                "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, 
                "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag
            })
            lagre_alt(d)
            st.success("Operativ status er oppdatert på tvers av alle enheter!")
            st.rerun()
