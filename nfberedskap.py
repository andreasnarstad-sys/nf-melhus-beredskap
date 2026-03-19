import streamlit as st
import os
import requests
import pandas as pd
import base64
from datetime import datetime

# --- 1. FUNKSJONER FOR EKSTERNE DATA (NVE API01 & MET) ---
def hent_vaer_melhus():
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.2859&lon=10.2781"
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v2.3'}
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
    headers = {'User-Agent': 'NF_Melhus_Beredskap_App_v2.3'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data['properties']['timeseries'][0]['fire_hazard_index']
    except: pass
    return None

def hent_trondelag_varsler():
    """Henter alle aktive flom- og skredvarsler for Trøndelag (Fylke 50)"""
    url = "https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/50"
    aktive_varsler = []
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for k in data:
                nivaa = k.get('ActivityLevel', 1)
                if nivaa > 1:
                    aktive_varsler.append({
                        "Kommune": k.get('MunicipalityName'),
                        "Nivå": nivaa,
                        "Type": "Flom/Skred",
                        "Beskrivelse": k.get('MainText', 'Ingen detaljer tilgjengelig.')
                    })
        return aktive_varsler
    except: return []

# --- 2. HJELPEFUNKSJONER FOR VISUALISERING ---
def hent_farefarge(nivaa):
    """Returnerer CSS-farger basert på NVEs offisielle skala"""
    if nivaa == 2: return "#FFFF00", "#000000", "GULT"      # Gul
    if nivaa == 3: return "#FF9900", "#FFFFFF", "ORANSJE"   # Oransje
    if nivaa >= 4: return "#FF0000", "#FFFFFF", "RØDT"      # Rød
    return "#28A745", "#FFFFFF", "GRØNT"                    # Grønn

def hent_logo_base64():
    for ext in ["png", "jpg", "jpeg"]:
        path = f"nf_logo.{ext}"
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode(), ext
    return None, None

# --- 3. LAGRING OG DATAHÅNDTERING ---
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

def lagre_alt(data_dict):
    string_data = ";".join([f"{k}|{v}" for k, v in data_dict.items()])
    with open("beredskap_data.txt", "w", encoding="utf-8") as f:
        f.write(string_data)

def lagre_utrykning(data):
    file_exists = os.path.isfile("aksjonslogg.csv")
    pd.DataFrame([data]).to_csv("aksjonslogg.csv", mode='a', index=False, header=not file_exists, encoding="utf-8")

# --- 4. HOVEDAPP OPPSETT ---
st.set_page_config(page_title="NF Melhus Beredskap", layout="wide")
d = last_alt()
temp, vind = hent_vaer_melhus()
trondelag_varsler = hent_trondelag_varsler()
brannfare = hent_skogbrannfare_melhus()
logo_b64, logo_ext = hent_logo_base64()

# Logovisning
if logo_b64:
    st.markdown(f'<div style="text-align:center; margin-top:-30px;"><img src="data:image/{logo_ext};base64,{logo_b64}" style="width:100%; max-width:1000px;"></div>', unsafe_allow_html=True)
else:
    st.title("🚑 Norsk Folkehjelp Melhus")

st.write("---")

# Lederens manuelle status
farge_leder = "#28a745"
if "🟡" in d['nivaa']: farge_leder = "#ffc107"
elif "🔴" in d['nivaa']: farge_leder = "#dc3545"

st.markdown(f"""
    <div style="background-color:{farge_leder}; padding:25px; border-radius:15px; text-align:center; color:white; border: 2px solid rgba(0,0,0,0.1);">
        <h1 style="margin:0; font-size:2.5rem;">{d['nivaa']}</h1>
        <p style="font-size:1.3rem; margin-top:10px;"><b>Lederens beskjed:</b> {d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

# --- 5. DYNAMISK VARSLINGSMODUL (TRØNDELAG & SKOGBRANN) ---
st.write("")
col_v1, col_v2 = st.columns([2, 1])

with col_v1:
    st.subheader("⚠️ Aktive farevarsler i Trøndelag (NVE)")
    if trondelag_varsler:
        # Spesifikk sjekk for Melhus
        melhus_varsel = next((v for v in trondelag_varsler if v['Kommune'] == "Melhus"), None)
        
        if melhus_varsel:
            bg, txt, label = hent_farefarge(melhus_varsel['Nivå'])
            st.markdown(f"""
                <div style="background-color:{bg}; color:{txt}; padding:20px; border-radius:10px; border: 3px solid #333; margin-bottom:15px;">
                    <h2 style="margin:0;">🚨 {label} VARSEL FOR MELHUS: Nivå {melhus_varsel['Nivå']}</h2>
                    <p style="font-size:1.1rem; margin-top:10px;">{melhus_varsel['Beskrivelse']}</p>
                </div>
            """, unsafe_allow_html=True)

        # Fargekodet tabell for fylket
        df_varsel = pd.DataFrame(trondelag_varsler).sort_values(by="Nivå", ascending=False)
        
        def fargelegg_nivaa(row):
            bg, txt, _ = hent_farefarge(row.Nivå)
            return [f'background-color: {bg}; color: {txt}'] * len(row)

        st.dataframe(df_varsel.style.apply(fargelegg_nivaa, axis=1), use_container_width=True, hide_index=True)
    else:
        st.success("✅ Ingen aktive flom- eller skredvarsler i Trøndelag for øyeblikket.")

with col_v2:
    st.subheader("🔥 Skogbrannfare (MET)")
    if brannfare is not None:
        if brannfare > 3.0: 
            st.markdown(f'<div style="background-color:red; color:white; padding:20px; border-radius:10px; text-align:center; font-weight:bold; font-size:1.5rem;">HØY FARE ({brannfare})</div>', unsafe_allow_html=True)
        elif brannfare > 1.0: 
            st.markdown(f'<div style="background-color:orange; color:white; padding:20px; border-radius:10px; text-align:center; font-weight:bold; font-size:1.5rem;">MODERAT FARE ({brannfare})</div>', unsafe_allow_html=True)
        else: 
            st.markdown(f'<div style="background-color:green; color:white; padding:20px; border-radius:10px; text-align:center; font-weight:bold; font-size:1.5rem;">LAV FARE ({brannfare})</div>', unsafe_allow_html=True)
    else:
        st.info("Henter skogbrann-indeks...")

# --- 6. DASHBORD: KONTAKT OG SAMBAND ---
st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("🌦️ Været i Melhus")
    st.metric("Temperatur", f"{temp} °C")
    st.metric("Vind", f"{vind} m/s")
with c2:
    st.subheader("📞 Kontakt")
    st.write(f"**Vakt:** {d['vakt']}")
    st.write(f"**Leder:** {d['leder']}")
    st.write(f"**Sanitet:** {d['sanitet']}")
with c3:
    st.subheader("📻 Operativt")
    st.info(f"**TG:** `{d['talegruppe']}`\n\n**Sted:** {d['oppmote']}")

# --- 7. REGISTRERING OG ADMIN ---
st.write("---")
with st.expander("📝 Registrer din deltakelse (Timer/KM/Utlegg)"):
    oppdrags_liste = d.get('aktive_oppdrag', 'Vakt,Trening').split(',')
    with st.form("reg_form", clear_on_submit=True):
        navn = st.text_input("Fullt navn")
        oppdrag = st.selectbox("Oppdrag", oppdrags_liste)
        c_t1, c_t2 = st.columns(2)
        t_ut = c_t1.text_input("Tid ut (HH:MM)")
        t_inn = c_t2.text_input("Tid inn (HH:MM)")
        km = st.number_input("KM", min_value=0)
        utlegg = st.number_input("Utlegg (kr)", min_value=0)
        if st.form_submit_button("Send inn"):
            lagre_utrykning({"Dato": datetime.now().strftime("%d.%m.%Y"), "Navn": navn, "Oppdrag": oppdrag, "Ut": t_ut, "Inn": t_inn, "KM": km, "Utlegg": utlegg})
            st.success("Registrert!")

with st.expander("🔐 Administrasjon"):
    pw = st.text_input("Passord", type="password")
    if pw == "melhus123":
        if st.button("Hent Logg (CSV)"):
            if os.path.exists("aksjonslogg.csv"):
                df_l = pd.read_csv("aksjonslogg.csv")
                st.dataframe(df_l)
                st.download_button("Last ned logg", df_l.to_csv(index=False), "logg.csv")
        
        st.write("---")
        ca, cb = st.columns(2)
        with ca:
            n_nivaa = st.selectbox("Status:", ["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"], index=["🟢 Grønn / Normal", "🟡 Gul / Forhøyhet", "🔴 Rød / Høy"].index(d['nivaa']))
            n_kort = st.selectbox("Tiltakskort:", ["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"], index=["Ingen", "Jordras", "Ekom-bortfall", "Strømbrudd", "Skogbrann"].index(d.get('valgt_kort', 'Ingen')))
            n_beskjed = st.text_area("Beskjed", value=d['beskjed'])
            n_oppdrag = st.text_input("Aktive oppdrag (separer m/komma)", value=d.get('aktive_oppdrag', 'Trening,Vakt'))
        with cb:
            n_vakt = st.text_input("Vakttelefon", value=d['vakt'])
            n_leder = st.text_input("Beredskapsleder", value=d['leder'])
            n_tg = st.text_input("Talegruppe", value=d['talegruppe'])
            n_op = st.text_input("Operativ leder", value=d['operativ_leder'])
            n_sted = st.text_input("Oppmøte", value=d['oppmote'])
            n_sanitet = st.text_input("Sanitetsleder", value=d['sanitet'])

        if st.button("LAGRE ENDRINGER"):
            d.update({"nivaa": n_nivaa, "beskjed": n_beskjed, "vakt": n_vakt, "leder": n_leder, "sanitet": n_sanitet, "talegruppe": n_tg, "operativ_leder": n_op, "oppmote": n_sted, "valgt_kort": n_kort, "aktive_oppdrag": n_oppdrag})
            lagre_alt(d)
            st.rerun()
