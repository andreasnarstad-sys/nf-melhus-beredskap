import streamlit as st
import requests
import pandas as pd
import os
import base64
from datetime import datetime
import streamlit.components.v1 as components

# --- 1. DATAKILDER (MET & NVE) ---

def hent_vaer_data():
    """Henter nåvær og 6-timers prognose for Melhus"""
    url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.28&lon=10.28"
    headers = {'User-Agent': 'NF-Beredskap-Melhus-v14'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            timeseries = data['properties']['timeseries']
            curr = timeseries[0]['data']['instant']['details']
            prog = []
            for i in range(1, 7):
                ts = timeseries[i]
                tid = datetime.fromisoformat(ts['time'].replace('Z', '+00:00')).strftime('%H:00')
                t = ts['data']['instant']['details'].get('air_temperature')
                v = ts['data']['instant']['details'].get('wind_speed')
                prog.append({"Tid": tid, "Temp": f"{t}°C", "Vind": f"{v} m/s"})
            return curr.get('air_temperature'), curr.get('wind_speed'), prog
    except:
        return None, None, []

def hent_lokale_varsler():
    funnede = []
    headers = {'User-Agent': 'NF-Beredskap-Melhus-v14'}
    
    # A) SNØSKRED
    skred_url = "https://api01.nve.no/hydrology/forecast/avalanche/v1.0.0/api/AvalancheWarningByRegion/Detail/All/1"
    try:
        r = requests.get(skred_url, headers=headers, timeout=10)
        if r.status_code == 200:
            relevante = ["Trollheimen", "Heiane", "Oppdal", "Romsdal"] 
            for v in r.json():
                if v.get('RegionName') in relevante and int(v.get('DangerLevel', 1)) >= 2:
                    funnede.append({"Område": v.get('RegionName'), "Nivå": int(v.get('DangerLevel')), "Type": "SNØSKRED", "Info": v.get('MainText', '')})
    except: pass

    # B) FLOM & JORDSKRED
    flom_url = "https://api01.nve.no/hydrology/forecast/flood/v1.0.0/api/CountyOverview/50"
    try:
        r_f = requests.get(flom_url, headers=headers, timeout=10)
        if r_f.status_code == 200:
            kommuner = ["Melhus", "Orkland", "Skaun", "Midtre Gauldal", "Trondheim"]
            for f in r_f.json():
                if f.get('MunicipalityName') in kommuner and int(f.get('ActivityLevel', 1)) >= 2:
                    funnede.append({"Område": f.get('MunicipalityName'), "Nivå": int(f.get('ActivityLevel')), "Type": "FLOM/SKRED", "Info": f.get('MainText', '')})
    except: pass

    return funnede

# --- 2. AVANSERT LOKAL LAGRING ---
DATA_FIL = "beredskap_status_v14.txt"

def lagre_alt(data_dict):
    # Lagrer alle feltene som en semikolon-separert streng
    content = ";".join([f"{k}|{v}" for k, v in data_dict.items()])
    with open(DATA_FIL, "w", encoding="utf-8") as f:
        f.write(content)

def last_alt():
    d = {
        "status": "🟢 Normal Beredskap",
        "beskjed": "Alt ok i Melhus og Orkland.",
        "leder": "Ikke satt",
        "vakt": "9XX XX XXX",
        "kort": "Ingen"
    }
    if os.path.exists(DATA_FIL):
        try:
            with open(DATA_FIL, "r", encoding="utf-8") as f:
                parts = f.read().split(";")
                for p in parts:
                    k, v = p.split("|")
                    d[k] = v
        except: pass
    return d

# --- 3. UI OPPSETT ---
st.set_page_config(page_title="NF Operativ Tavle", layout="wide")
d = last_alt()

# Logo
if os.path.exists("nf_logo.png"):
    with open("nf_logo.png", "rb") as f:
        img = base64.b64encode(f.read()).decode()
    st.markdown(f'<div style="text-align:center;"><img src="data:image/png;base64,{img}" style="width:100%; max-width:400px;"></div>', unsafe_allow_html=True)

st.write("---")

# HOVEDBANNER: STATUS
f_bg = "#28a745"
if "🟡" in d['status']: f_bg = "#ffc107"
elif "🔴" in d['status']: f_bg = "#dc3545"

st.markdown(f"""
    <div style="background-color:{f_bg}; padding:30px; border-radius:15px; text-align:center; color:white; border:2px solid rgba(0,0,0,0.2);">
        <h1 style="margin:0; font-size:3.5rem; font-weight:bold;">{d['status']}</h1>
        <p style="font-size:1.6rem; margin-top:15px;">{d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

st.write("")

# RAD 2: VÆR OG OPERATIV INFO
c_vaer, c_info, c_kort = st.columns([1.5, 1, 1])

with c_vaer:
    temp, vind, prog = hent_vaer_data()
    if temp is not None:
        st.markdown(f"""
            <div style="background-color:#f8f9fa; padding:15px; border-radius:15px; border:1px solid #ddd; min-height:180px;">
                <h4 style="margin:0; text-align:center; color:#333;">Været i Melhus</h4>
                <h2 style="text-align:center; color:#1f77b4; margin:10px 0;">{temp}°C | {vind} m/s</h2>
                <div style="display: flex; justify-content: space-between; font-size:0.75rem; text-align:center;">
                    {"".join([f"<div>{p['Tid']}<br><b>{p['Temp']}</b><br>{p['Vind']}</div>" for p in prog[:4]])}
                </div>
            </div>
        """, unsafe_allow_html=True)

with c_info:
    st.markdown(f"""
        <div style="background-color:#ffffff; padding:15px; border-radius:15px; border:2px solid #2e5984; min-height:180px;">
            <h4 style="margin:0; color:#2e5984;">📞 Operativ Ledelse</h4>
            <p style="margin:10px 0 5px 0;"><b>Leder:</b> {d['leder']}</p>
            <p style="margin:0;"><b>Vakt-tlf:</b> {d['vakt']}</p>
            <p style="font-size:0.8rem; color:gray; margin-top:20px;">Oppdatert: {datetime.now().strftime('%H:%M:%S')}</p>
        </div>
    """, unsafe_allow_html=True)

with c_kort:
    kort_farge = "#f8f9fa" if d['kort'] == "Ingen" else "#fff3cd"
    kort_border = "#ddd" if d['kort'] == "Ingen" else "#ffeeba"
    st.markdown(f"""
        <div style="background-color:{kort_farge}; padding:15px; border-radius:15px; border:2px solid {kort_border}; min-height:180px;">
            <h4 style="margin:0; color:#856404;">📋 Aktivt Tiltakskort</h4>
            <h2 style="margin:15px 0; color:#856404;">{d['kort']}</h2>
        </div>
    """, unsafe_allow_html=True)

# RAD 3: WINDY OG FAREVARSLER
st.write("---")
col_map, col_alerts = st.columns([2, 1])

with col_map:
    st.subheader("💨 Live Vindkart (Melhus/Orkland)")
    windy_url = "https://embed.windy.com/embed2.html?lat=63.260&lon=10.100&zoom=9&level=surface&overlay=wind&product=ecmwf&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=m%2Fs&metricTemp=%C2%B0C&radarRange=false"
    components.iframe(windy_url, height=500)

with col_alerts:
    st.subheader("🚨 Aktive Farevarsler")
    varsler = hent_lokale_varsler()
    if varsler:
        df = pd.DataFrame(varsler).sort_values(by="Nivå", ascending=False)
        def style_f(row):
            colors = {2: ("#FFFF00", "black"), 3: ("#FF9900", "white"), 4: ("#FF0000", "white")}
            bg, txt = colors.get(row.Nivå, ("white", "black"))
            return [f'background-color: {bg}; color: {txt}; font-weight: bold'] * len(row)
        st.dataframe(df.style.apply(style_f, axis=1), use_container_width=True, hide_index=True)
    else:
        st.success("✅ Ingen farevarsler over nivå 1.")
    
    if st.button("🔄 Oppdater nå"):
        st.rerun()

# --- 4. ADMIN-PANEL (OPERATIV KONTROLL) ---
st.write("---")
with st.expander("🔐 Administrasjon (Oppdater situasjonsbilde)"):
    c1, c2 = st.columns(2)
    with c1:
        n_stat = st.selectbox("Status:", ["🟢 Normal Beredskap", "🟡 Forhøyhet Beredskap", "🔴 Rød / Aksjon"], 
                             index=["🟢 Normal Beredskap", "🟡 Forhøyhet Beredskap", "🔴 Rød / Aksjon"].index(d['status']))
        n_besk = st.text_area("Beskjed til mannskap:", value=d['beskjed'])
        n_kort = st.selectbox("Tiltakskort i bruk:", ["Ingen", "Snøskred", "Flom", "Jordras", "Ekom-bortfall", "Isolasjon", "Søk/Redning"],
                             index=["Ingen", "Snøskred", "Flom", "Jordras", "Ekom-bortfall", "Isolasjon", "Søk/Redning"].index(d['kort']))
    with c2:
        n_led = st.text_input("Operativ leder (Navn):", value=d['leder'])
        n_vak = st.text_input("Vakttelefon (Nummer):", value=d['vakt'])
        
    if st.button("💾 Lagre og Oppdater Tavle"):
        ny_data = {
            "status": n_stat,
            "beskjed": n_besk,
            "leder": n_led,
            "vakt": n_vak,
            "kort": n_kort
        }
        lagre_alt(ny_data)
        st.rerun()
