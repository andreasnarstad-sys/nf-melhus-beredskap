import os, json, smtplib
import requests
import streamlit as st
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- KONSTANTER ---

STD_HEADERS = {
    'User-Agent': 'NorskFolkehjelpBeredskap/27.0 (beredskap@folkehjelp.no)',
    'Accept': 'application/json'
}

REGION_FILTER = {
    "Trøndelag (Melhus/Orkland)": {
        "termer": ["50","trøndelag","melhus","orkland","trollheimen","skaun","gauldal","trondheim","oppdal","rindal","heiane"],
        "lat_min": 62.5, "lat_max": 64.5, "lon_min": 8.5, "lon_max": 12.5
    },
    "Hele Norge": {},
    "Nord-Norge": {"termer": ["18","54","55","56","nordland","troms","finnmark"]},
    "Vestlandet": {"termer": ["11","46","15","rogaland","vestland","møre"]},
    "Sørlandet":  {"termer": ["42","agder"]},
    "Østlandet":  {"termer": ["03","31","32","33","34","39","40","oslo","østfold","akershus","buskerud","innlandet","vestfold","telemark"]}
}

KART_KOORDINATER = {
    "Trøndelag (Melhus/Orkland)": "lat=63.26&lon=10.15&zoom=8",
    "Hele Norge":   "lat=64.00&lon=12.00&zoom=4",
    "Nord-Norge":   "lat=68.50&lon=15.00&zoom=5",
    "Vestlandet":   "lat=60.80&lon=6.00&zoom=6",
    "Sørlandet":    "lat=58.50&lon=7.50&zoom=7",
    "Østlandet":    "lat=60.50&lon=10.50&zoom=6"
}

EVENT_MAP = {
    "snowAvalanche": "SNØSKRED", "flood": "FLOM", "landslide": "JORDSKRED",
    "wind": "VIND", "gale": "STORM", "ice": "ISING", "snow": "SNØFOKK",
    "rain": "STYRTREGN", "forestFire": "SKOGBRANNFARE"
}

STATUS_FARGER = {
    "🟢 Normal Beredskap":    "#28a745",
    "🟡 Forhøyet Beredskap":  "#ffc107",
    "🔴 Rød / Høy beredskap": "#dc3545"
}

NVE_REGIONER = {
    "Trøndelag (Melhus/Orkland)": [3019, 3020, 3022],
    "Hele Norge":  list(range(3001, 3035)),
    "Nord-Norge":  [3005,3006,3007,3008,3009,3010,3011,3012,3013,3014,3015,3016,3017,3018],
    "Vestlandet":  [3021, 3023, 3024],
    "Sørlandet":   [],
    "Østlandet":   [3025],
}

KALKYLE_PRISER = {
    "grunnpris": 800, "sanitet": 160, "ambulanse_m": 300,
    "mbil": 300, "amb_kjt": 900, "atv_kjt": 300,
    "km": 8, "atv_t": 200
}

# --- FILER ---

FIL             = "beredskap_data.json"
GAMLE_FILER     = ["beredskap_melhus_v27.txt", "beredskap_data_v19.txt", "beredskap_data.txt"]
DELTAKELSE_FIL  = "deltakelse_data.json"
AVVIK_FIL       = "avvik_data.json"
VAKTPLAN_FIL    = "vaktplan_data.json"
EPOST_CONFIG_FIL= "epost_config.json"
VEDLEGG_MAPPE   = "vedlegg"

DEFAULTS = {
    "status": "🟢 Normal Beredskap",
    "beskjed": "Klar til innsats i Melhus og omegn.",
    "leder": "Ikke satt", "vakt": "9XX XX XXX",
    "kort": "Daglig drift", "logg": "",
    "ekom": "🟢 Normal drift", "vei": "🟢 Veinett åpent"
}

VAKTPLAN_DEFAULTS = {
    "sted":"", "lagleder":"", "mannskaper":"", "utstyr":"",
    "legevakt":"", "sykehus":"", "talegruppe":"",
    "tid_fra":"", "tid_til":"", "notat":"", "aktiv": False
}

EPOST_DEFAULTS = {
    "smtp_server":"", "smtp_port":"587", "smtp_bruker":"",
    "smtp_passord":"", "fra":"", "til":"andreas.narstad@gmail.com"
}

# --- DATA-FUNKSJONER ---

def lagre_data(d):
    with open(FIL, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def last_liste(fil):
    if os.path.exists(fil):
        try:
            with open(fil, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def lagre_liste(fil, data):
    with open(fil, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def last_vaktplan():
    if os.path.exists(VAKTPLAN_FIL):
        try:
            with open(VAKTPLAN_FIL, "r", encoding="utf-8") as f:
                data = json.load(f)
            r = dict(VAKTPLAN_DEFAULTS); r.update({k:v for k,v in data.items() if k in VAKTPLAN_DEFAULTS})
            return r
        except Exception:
            pass
    return dict(VAKTPLAN_DEFAULTS)

def lagre_vaktplan(vp):
    with open(VAKTPLAN_FIL, "w", encoding="utf-8") as f:
        json.dump(vp, f, ensure_ascii=False, indent=2)

def last_epost_config():
    if os.path.exists(EPOST_CONFIG_FIL):
        try:
            with open(EPOST_CONFIG_FIL, "r", encoding="utf-8") as f:
                data = json.load(f)
            r = dict(EPOST_DEFAULTS); r.update({k:v for k,v in data.items() if k in EPOST_DEFAULTS})
            return r
        except Exception:
            pass
    return dict(EPOST_DEFAULTS)

def lagre_epost_config(cfg):
    with open(EPOST_CONFIG_FIL, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def _les_gammel_format(filnavn):
    data = dict(DEFAULTS)
    try:
        with open(filnavn, "r", encoding="utf-8") as f:
            for item in f.read().split("###"):
                if "===" in item:
                    k, v = item.split("===", 1)
                    if k.strip() in data:
                        data[k.strip()] = v.strip()
    except Exception:
        pass
    return data

def last_data():
    if os.path.exists(FIL):
        try:
            with open(FIL, "r", encoding="utf-8") as f:
                data = json.load(f)
            r = dict(DEFAULTS); r.update({k:v for k,v in data.items() if k in DEFAULTS})
            return r
        except Exception:
            pass
    for gammel in GAMLE_FILER:
        if os.path.exists(gammel):
            data = _les_gammel_format(gammel)
            lagre_data(data); return data
    return dict(DEFAULTS)

# --- E-POST ---

def send_avvik_epost(avvik, cfg):
    if not cfg.get("smtp_server") or not cfg.get("til") or not cfg.get("fra"):
        return False, "E-postkonfigurasjon mangler (SMTP-server, fra og til er påkrevd)."
    try:
        haster = avvik.get("umiddelbar_oppfolging", False)
        msg = MIMEMultipart()
        msg['From'] = cfg['fra']; msg['To'] = cfg['til']
        msg['Subject'] = f"{'⚡ AKUTT – ' if haster else ''}Avvik – Norsk Folkehjelp Melhus"
        msg.attach(MIMEText(
            f"Tidspunkt : {avvik['registrert']}\n"
            f"Navn      : {avvik['navn']}\n"
            f"E-post    : {avvik.get('epost') or '–'}\n"
            f"Haster    : {'⚡ JA' if haster else 'Nei'}\n\n"
            f"HENDELSE:\n{avvik['hendelse']}\n\n"
            f"KONSEKVENS:\n{avvik.get('konsekvens') or '–'}\n\n"
            f"---\nNF Operativ Tavle – Norsk Folkehjelp Melhus",
            'plain', 'utf-8'
        ))
        with smtplib.SMTP(cfg['smtp_server'], int(cfg.get('smtp_port', 587)), timeout=10) as srv:
            srv.ehlo(); srv.starttls(); srv.ehlo()
            if cfg.get('smtp_bruker') and cfg.get('smtp_passord'):
                srv.login(cfg['smtp_bruker'], cfg['smtp_passord'])
            srv.send_message(msg)
        return True, f"E-post sendt til {cfg['til']}"
    except Exception as e:
        return False, f"E-postfeil: {e}"

# --- HJELPEFUNKSJONER ---

def beregn_rig_tid(tid_fra_str):
    try:
        t = datetime.strptime(tid_fra_str.strip(), "%H:%M")
        return (t - timedelta(minutes=30)).strftime("%H:%M")
    except Exception:
        return ""

def inject_css():
    st.markdown("""
    <style>
    .nf-card       { background:rgba(128,128,128,0.07); border:1px solid rgba(128,128,128,0.2); border-radius:12px; padding:15px; }
    .nf-card-blue  { background:rgba(46,89,132,0.08); border:2px solid #2e5984; border-radius:12px; padding:15px; min-height:160px; }
    .nf-card-danger{ background:rgba(220,53,69,0.10); border:1px solid #dc3545; border-radius:10px; padding:14px; margin-top:10px; }
    .nf-card-info  { background:rgba(33,150,243,0.10); border:1px solid #2196f3; border-radius:10px; padding:14px; margin-top:10px; }
    .nf-rig        { background:rgba(255,193,7,0.18); border:1px solid #ffc107; border-radius:8px; padding:10px 14px; margin-bottom:10px; }
    .nf-ok-box     { border:2px solid #28a745; border-radius:12px; padding:60px 20px; text-align:center; height:430px;
                     display:flex; flex-direction:column; justify-content:center; background:rgba(40,167,69,0.06); }
    .nf-infra-base { border-radius:12px; padding:15px; min-height:160px; }
    .nf-infra-ok   { border:2px solid #28a745; background:rgba(40,167,69,0.07); }
    .nf-infra-warn { border:2px solid #ffc107; background:rgba(255,193,7,0.09); }
    .nf-infra-err  { border:2px solid #dc3545; background:rgba(220,53,69,0.07); }
    .nf-label      { font-size:0.75rem; text-transform:uppercase; letter-spacing:0.05em; opacity:0.6; margin-bottom:4px; }
    .nf-val        { font-size:1.05rem; font-weight:bold; }
    .nf-divider    { border-bottom:1px solid rgba(128,128,128,0.2); padding:3px 0; }
    .nf-step       { background:rgba(128,128,128,0.05); border:1px solid rgba(128,128,128,0.15);
                     border-radius:10px; padding:18px 20px; margin-bottom:14px; }
    .nf-step-title { font-size:0.8rem; text-transform:uppercase; letter-spacing:0.06em;
                     opacity:0.55; margin-bottom:12px; font-weight:bold; }
    .nf-subtotal   { text-align:right; font-size:0.85rem; opacity:0.7; margin-top:8px; }
    </style>
    """, unsafe_allow_html=True)

def vis_sidebar_status():
    """Viser logo og beredskapsstatus i sidebar."""
    d = last_data()
    avvik_liste = last_liste(AVVIK_FIL)
    akutte = [a for a in avvik_liste if a.get("umiddelbar_oppfolging") and not a.get("fulgt_opp")]
    if os.path.exists("nf_logo.png"):
        st.sidebar.image("nf_logo.png", width=160)
    bg = STATUS_FARGER.get(d['status'], "#333")
    st.sidebar.markdown(f"""
        <div style='background:{bg}; color:white; padding:8px 12px;
        border-radius:8px; font-weight:bold; font-size:0.9rem; margin-bottom:8px;'>
        {d['status']}
        </div>""", unsafe_allow_html=True)
    if akutte:
        st.sidebar.error(f"⚡ {len(akutte)} avvik krever umiddelbar oppfølging!")

# --- API ---

def _sjekk_koordinat(koordinater, region_valg):
    reg = REGION_FILTER.get(region_valg, {})
    if not all(k in reg for k in ("lat_min","lat_max","lon_min","lon_max")):
        return False
    try:
        lon, lat = koordinater[0][0][0][0], koordinater[0][0][0][1]
        return reg["lat_min"] <= lat <= reg["lat_max"] and reg["lon_min"] <= lon <= reg["lon_max"]
    except (IndexError, TypeError):
        return False

def _sjekk_region(omrade, fylke, region_valg):
    if region_valg == "Hele Norge": return True
    termer = REGION_FILTER.get(region_valg, {}).get("termer", [])
    return any(t in f"{omrade} {fylke}".lower() for t in termer)

@st.cache_data(ttl=300)
def hent_nve_varsler(region_valg):
    varsler = {}
    region_ids = NVE_REGIONER.get(region_valg, [])
    if not region_ids: return varsler
    today = datetime.now().strftime('%Y-%m-%d')
    feil_vist = False
    for rid in region_ids:
        try:
            r = requests.get(
                f"https://api01.nve.no/hydrology/forecast/avalanche/v6.3.0/api/AvalancheWarningByRegion/Detail/{rid}/no/{today}/{today}",
                headers=STD_HEADERS, timeout=10)
            r.raise_for_status()
            for v in r.json():
                try: nivaa = int(v.get('DangerLevel', 0))
                except: nivaa = 0
                if nivaa < 2: continue
                omrade = v.get('RegionName','')
                varsler[f"{omrade}_SNØSKRED"] = {
                    "Område": omrade, "Nivå": nivaa, "Type": "SNØSKRED",
                    "Kilde": "Varsom.no", "Info": v.get('MainText','Se Varsom.no')}
        except requests.exceptions.ConnectionError:
            if not feil_vist: st.warning("⚠️ Kan ikke nå Varsom – sjekk internett."); feil_vist=True; break
        except requests.exceptions.Timeout:
            if not feil_vist: st.warning("⚠️ Varsom svarte ikke innen 10 sek."); feil_vist=True; break
        except requests.exceptions.HTTPError as e:
            if not feil_vist: st.warning(f"⚠️ Varsom feil: {e}"); feil_vist=True; break
        except Exception as e:
            if not feil_vist: st.warning(f"⚠️ Uventet feil: {e}"); feil_vist=True; break
    return varsler

@st.cache_data(ttl=300)
def hent_met_varsler(region_valg):
    varsler = {}
    try:
        r = requests.get("https://api.met.no/weatherapi/metalerts/2.0/current.json", headers=STD_HEADERS, timeout=10)
        r.raise_for_status()
        for feat in r.json().get('features', []):
            p = feat.get('properties', {})
            if p.get('geographicDomain') == 'marine': continue
            farge = p.get('riskMatrixColor','').lower()
            if 'red' in farge: nivaa=4
            elif 'orange' in farge: nivaa=3
            elif 'yellow' in farge: nivaa=2
            else: continue
            omrade = p.get('area',''); fylke = p.get('county','')
            treff = _sjekk_region(omrade, fylke, region_valg)
            if not treff: treff = _sjekk_koordinat(feat.get('geometry',{}).get('coordinates',[]), region_valg)
            if not treff: continue
            event_type = p.get('event','')
            if event_type == "snowAvalanche": continue
            norsk_type = EVENT_MAP.get(event_type, event_type.upper())
            kilde = "Varsom/NVE" if event_type in ("flood","landslide") else "Yr/MET"
            navn = omrade.split(",")[0]
            varsler[f"{navn}_{norsk_type}"] = {
                "Område": navn, "Nivå": nivaa, "Type": norsk_type,
                "Kilde": kilde, "Info": p.get('title','Aktivt farevarsel')}
    except requests.exceptions.ConnectionError: st.warning("⚠️ Kan ikke nå MET.no")
    except requests.exceptions.Timeout: st.warning("⚠️ MET.no svarte ikke")
    except requests.exceptions.HTTPError as e: st.warning(f"⚠️ MET.no feil: {e}")
    except Exception as e: st.warning(f"⚠️ Uventet feil MET: {e}")
    return varsler

def hent_alle_varsler(region_valg):
    v = {}; v.update(hent_nve_varsler(region_valg)); v.update(hent_met_varsler(region_valg))
    return list(v.values())

@st.cache_data(ttl=300)
def hent_lokal_vaer():
    try:
        r = requests.get("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.28&lon=10.28",
                         headers=STD_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()['properties']['timeseries']
        now = data[0]['data']['instant']['details']
        prog = [{"t": datetime.fromisoformat(data[i]['time'].replace('Z','+00:00')).strftime('%H:%M'),
                 "temp": data[i]['data']['instant']['details']['air_temperature']} for i in range(1,5)]
        return now['air_temperature'], now['wind_speed'], prog
    except Exception:
        return None, None, []

# --- HTML-EKSPORT ---

def generer_html_export(vp, d):
    ml = "".join(f"<li>{n.strip()}</li>" for n in vp["mannskaper"].splitlines() if n.strip()) or "<li><em>Ikke oppgitt</em></li>"
    ul = "".join(f"<li>{u.strip()}</li>" for u in vp["utstyr"].splitlines() if u.strip()) or "<li><em>Ikke oppgitt</em></li>"
    rig = beregn_rig_tid(vp["tid_fra"])
    dato_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"""<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8"><title>Beredskapsplan</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Arial,sans-serif;color:#222;background:#fff;padding:30px}}
.header{{background:#cc0000;color:white;padding:22px 28px;border-radius:10px;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.card{{background:#f7f7f7;border:1px solid #ddd;border-radius:8px;padding:16px}}
.card h3{{font-size:0.8rem;text-transform:uppercase;color:#888;margin-bottom:8px}}
.card .val{{font-weight:bold;color:#111}}.card ul{{margin-left:18px;line-height:1.8}}
.rig{{background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:14px;margin-bottom:16px;font-weight:bold}}
.nood{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.nood .card{{border-left:4px solid #cc0000}}
.footer{{color:#aaa;font-size:0.8rem;text-align:center;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
@media print{{body{{padding:15px}}}}</style></head><body>
<div class="header"><h1>🚑 Norsk Folkehjelp – Beredskapsplan</h1>
<p>Norsk Folkehjelp Melhus | Generert: {dato_str} | Status: {d['status']}</p></div>
{f'<div class="rig">⏰ Ferdig rigget: {rig} (30 min før)</div>' if rig else ''}
<div class="grid">
<div class="card"><h3>📍 Sted</h3><div class="val">{vp['sted'] or '–'}</div></div>
<div class="card"><h3>🕐 Tid</h3><div class="val">{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div></div>
<div class="card"><h3>👷 Lagleder</h3><div class="val">{vp['lagleder'] or '–'}</div></div>
<div class="card"><h3>📻 Talegruppe</h3><div class="val">{vp['talegruppe'] or '–'}</div></div>
<div class="card"><h3>👥 Mannskaper</h3><ul>{ml}</ul></div>
<div class="card"><h3>🎒 Utstyr</h3><ul>{ul}</ul></div>
</div>
<div class="nood">
<div class="card"><h3>🏥 Legevakt</h3><div class="val">{vp['legevakt'] or '–'}</div></div>
<div class="card"><h3>🏨 Sykehus</h3><div class="val">{vp['sykehus'] or '–'}</div></div>
</div>
{f'<div class="card" style="margin-bottom:16px"><h3>📝 Merknader</h3><div>{vp["notat"]}</div></div>' if vp["notat"] else ''}
<div class="footer">Norsk Folkehjelp Melhus | Vaktleder: {d['leder']} | {d['vakt']}</div>
</body></html>"""

def generer_tilbud_html(kunde, arrangement, dato_str, linjer, total, forbruk):
    rader = ""
    for navn, beregning, belop in linjer:
        if belop == 0: continue
        rader += f"<tr><td>{navn}</td><td style='color:#666;font-size:0.85rem'>{beregning}</td><td style='text-align:right;font-weight:bold'>{belop:,.0f} kr</td></tr>".replace(",", " ")
    if forbruk:
        rader += f"<tr><td>Forbruksmateriell</td><td style='color:#666;font-size:0.85rem'>Manuelt oppgitt</td><td style='text-align:right;font-weight:bold'>{forbruk:,.0f} kr</td></tr>".replace(",", " ")
    dato_gen = datetime.now().strftime("%d.%m.%Y")
    return f"""<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8"><title>Tilbud – {arrangement}</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Arial,sans-serif;color:#222;padding:40px;max-width:750px;margin:0 auto}}
.header{{background:#cc0000;color:white;padding:28px 32px;border-radius:10px;margin-bottom:28px}}
.header h1{{font-size:1.6rem;margin-bottom:6px}}.header p{{opacity:0.88}}
.meta{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}}
.meta div{{background:#f5f5f5;border-radius:8px;padding:14px 18px}}
.meta .label{{font-size:0.75rem;text-transform:uppercase;color:#888;margin-bottom:4px}}
.meta .val{{font-weight:bold;font-size:1rem}}
table{{width:100%;border-collapse:collapse;margin-bottom:20px}}
th{{background:#222;color:white;padding:10px 14px;text-align:left;font-size:0.85rem}}
th:last-child{{text-align:right}}td{{padding:10px 14px;border-bottom:1px solid #eee}}
tr:hover td{{background:#fafafa}}
.total-row td{{border-top:3px solid #cc0000;font-weight:bold;background:#fff8f8;font-size:1.15rem}}
.total-row td:last-child{{color:#cc0000;font-size:1.3rem;text-align:right}}
.footer{{color:#aaa;font-size:0.8rem;text-align:center;margin-top:28px;border-top:1px solid #eee;padding-top:14px}}
@media print{{body{{padding:20px}}}}</style></head><body>
<div class="header"><h1>🚑 Tilbud – Sanitetsvakt</h1>
<p>Norsk Folkehjelp Melhus · Utstedt: {dato_gen}</p></div>
<div class="meta">
<div><div class="label">Kunde / Arrangør</div><div class="val">{kunde or '–'}</div></div>
<div><div class="label">Arrangement</div><div class="val">{arrangement or '–'}</div></div>
<div><div class="label">Dato for vakt</div><div class="val">{dato_str or '–'}</div></div>
</div>
<table><thead><tr><th>Beskrivelse</th><th>Beregning</th><th style='text-align:right'>Beløp</th></tr></thead>
<tbody>{rader}<tr class="total-row"><td colspan="2">TOTALT</td><td>{total:,.0f} kr</td></tr></tbody>
</table>
<div class="footer">Norsk Folkehjelp Melhus | Generert {dato_gen} via NF Operativ Tavle<br>
Priser er veiledende og ekskl. mva. der annet ikke er avtalt.</div>
</body></html>""".replace(",", " ")
