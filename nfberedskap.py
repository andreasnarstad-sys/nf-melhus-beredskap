import streamlit as st
import requests
import pandas as pd
import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import streamlit.components.v1 as components

# --- KONFIGURASJON ---

STD_HEADERS = {
    'User-Agent': 'NorskFolkehjelpBeredskap/27.0 (beredskap@folkehjelp.no)',
    'Accept': 'application/json'
}

REGION_FILTER = {
    "Trøndelag (Melhus/Orkland)": {
        "termer": ["50", "trøndelag", "melhus", "orkland", "trollheimen", "skaun", "gauldal", "trondheim", "oppdal", "rindal", "heiane"],
        "lat_min": 62.5, "lat_max": 64.5, "lon_min": 8.5, "lon_max": 12.5
    },
    "Hele Norge": {},
    "Nord-Norge": {"termer": ["18", "54", "55", "56", "nordland", "troms", "finnmark"]},
    "Vestlandet": {"termer": ["11", "46", "15", "rogaland", "vestland", "møre"]},
    "Sørlandet": {"termer": ["42", "agder"]},
    "Østlandet": {"termer": ["03", "31", "32", "33", "34", "39", "40", "oslo", "østfold", "akershus", "buskerud", "innlandet", "vestfold", "telemark"]}
}

KART_KOORDINATER = {
    "Trøndelag (Melhus/Orkland)": "lat=63.26&lon=10.15&zoom=8",
    "Hele Norge": "lat=64.00&lon=12.00&zoom=4",
    "Nord-Norge": "lat=68.50&lon=15.00&zoom=5",
    "Vestlandet": "lat=60.80&lon=6.00&zoom=6",
    "Sørlandet": "lat=58.50&lon=7.50&zoom=7",
    "Østlandet": "lat=60.50&lon=10.50&zoom=6"
}

EVENT_MAP = {
    "snowAvalanche": "SNØSKRED", "flood": "FLOM",
    "landslide": "JORDSKRED", "wind": "VIND",
    "gale": "STORM", "ice": "ISING", "snow": "SNØFOKK",
    "rain": "STYRTREGN", "forestFire": "SKOGBRANNFARE"
}

STATUS_FARGER = {
    "🟢 Normal Beredskap": "#28a745",
    "🟡 Forhøyet Beredskap": "#ffc107",
    "🔴 Rød / Høy beredskap": "#dc3545"
}

# --- DATALAGRING ---

FIL = "beredskap_data.json"
GAMLE_FILER = ["beredskap_melhus_v27.txt", "beredskap_data_v19.txt", "beredskap_data.txt"]
DELTAKELSE_FIL = "deltakelse_data.json"
AVVIK_FIL = "avvik_data.json"
VAKTPLAN_FIL = "vaktplan_data.json"
EPOST_CONFIG_FIL = "epost_config.json"
VEDLEGG_MAPPE = "vedlegg"

EPOST_DEFAULTS = {
    "smtp_server": "",
    "smtp_port": "587",
    "smtp_bruker": "",
    "smtp_passord": "",
    "fra": "",
    "til": "andreas.narstad@gmail.com"
}

VAKTPLAN_DEFAULTS = {
    "sted": "",
    "lagleder": "",
    "mannskaper": "",
    "utstyr": "",
    "legevakt": "",
    "sykehus": "",
    "talegruppe": "",
    "tid_fra": "",
    "tid_til": "",
    "notat": "",
    "aktiv": False
}

DEFAULTS = {
    "status": "🟢 Normal Beredskap",
    "beskjed": "Klar til innsats i Melhus og omegn.",
    "leder": "Ikke satt",
    "vakt": "9XX XX XXX",
    "kort": "Daglig drift",
    "logg": "",
    "ekom": "🟢 Normal drift",
    "vei": "🟢 Veinett åpent"
}

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

def last_epost_config():
    if os.path.exists(EPOST_CONFIG_FIL):
        try:
            with open(EPOST_CONFIG_FIL, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = dict(EPOST_DEFAULTS)
            result.update({k: v for k, v in data.items() if k in EPOST_DEFAULTS})
            return result
        except Exception:
            pass
    return dict(EPOST_DEFAULTS)

def lagre_epost_config(cfg):
    with open(EPOST_CONFIG_FIL, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def send_avvik_epost(avvik, cfg):
    if not cfg.get("smtp_server") or not cfg.get("til") or not cfg.get("fra"):
        return False, "E-postkonfigurasjon er ikke fullstendig (SMTP-server, fra og til er påkrevd)."
    try:
        haster = avvik.get("umiddelbar_oppfolging", False)
        emne = f"{'⚡ AKUTT – ' if haster else ''}Avvik registrert – NF Melhus/Orkland"
        kropp = f"""Nytt avvik er registrert i NF Operativ Tavle.

Tidspunkt : {avvik['registrert']}
Navn      : {avvik['navn']}
E-post    : {avvik.get('epost') or '–'}
Haster    : {'⚡ JA – krever umiddelbar oppfølging' if haster else 'Nei'}

HENDELSE:
{avvik['hendelse']}

KONSEKVENS:
{avvik.get('konsekvens') or '–'}

---
NF Operativ Tavle – Melhus & Orkland
"""
        msg = MIMEMultipart()
        msg['From'] = cfg['fra']
        msg['To'] = cfg['til']
        msg['Subject'] = emne
        msg.attach(MIMEText(kropp, 'plain', 'utf-8'))

        with smtplib.SMTP(cfg['smtp_server'], int(cfg.get('smtp_port', 587)), timeout=10) as srv:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            if cfg.get('smtp_bruker') and cfg.get('smtp_passord'):
                srv.login(cfg['smtp_bruker'], cfg['smtp_passord'])
            srv.send_message(msg)
        return True, f"E-post sendt til {cfg['til']}"
    except Exception as e:
        return False, f"E-postfeil: {e}"

def last_vaktplan():
    if os.path.exists(VAKTPLAN_FIL):
        try:
            with open(VAKTPLAN_FIL, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = dict(VAKTPLAN_DEFAULTS)
            result.update({k: v for k, v in data.items() if k in VAKTPLAN_DEFAULTS})
            return result
        except Exception:
            pass
    return dict(VAKTPLAN_DEFAULTS)

def lagre_vaktplan(vp):
    with open(VAKTPLAN_FIL, "w", encoding="utf-8") as f:
        json.dump(vp, f, ensure_ascii=False, indent=2)

def _beregn_rig_tid(tid_fra_str):
    """Returnerer tid 30 min før tid_fra, eller tom streng ved feil."""
    try:
        t = datetime.strptime(tid_fra_str.strip(), "%H:%M")
        from datetime import timedelta
        rig = (t - timedelta(minutes=30)).strftime("%H:%M")
        return rig
    except Exception:
        return ""

def generer_html_export(vp, d):
    mannskaper_html = "".join(
        f"<li>{navn.strip()}</li>"
        for navn in vp["mannskaper"].splitlines() if navn.strip()
    ) or "<li><em>Ikke oppgitt</em></li>"
    utstyr_html = "".join(
        f"<li>{u.strip()}</li>"
        for u in vp["utstyr"].splitlines() if u.strip()
    ) or "<li><em>Ikke oppgitt</em></li>"
    rig_tid = _beregn_rig_tid(vp["tid_fra"])
    rig_linje = f"{rig_tid} (30 min før oppmøte)" if rig_tid else "–"
    dato_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="no"><head><meta charset="UTF-8">
<title>Beredskapsplan – {vp['sted'] or 'NF Vakt'}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; color: #222; background: #fff; padding: 30px; }}
  .header {{ background: #cc0000; color: white; padding: 22px 28px; border-radius: 10px; margin-bottom: 22px; }}
  .header h1 {{ font-size: 1.7rem; margin-bottom: 4px; }}
  .header p {{ font-size: 0.95rem; opacity: 0.9; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .card {{ background: #f7f7f7; border: 1px solid #ddd; border-radius: 8px; padding: 16px; }}
  .card.full {{ grid-column: 1 / -1; }}
  .card h3 {{ font-size: 0.8rem; text-transform: uppercase; color: #888; letter-spacing: 0.05em; margin-bottom: 8px; }}
  .card .val {{ font-size: 1.05rem; font-weight: bold; color: #111; }}
  .card ul {{ margin-left: 18px; color: #333; line-height: 1.8; }}
  .rig {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 14px 18px;
           font-size: 1rem; font-weight: bold; margin-bottom: 16px; }}
  .nood {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .nood .card {{ border-left: 4px solid #cc0000; }}
  .footer {{ color: #aaa; font-size: 0.8rem; text-align: center; margin-top: 24px; border-top: 1px solid #eee; padding-top: 12px; }}
  @media print {{ body {{ padding: 15px; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>🚑 Norsk Folkehjelp – Beredskapsplan</h1>
  <p>Melhus &amp; Orkland &nbsp;|&nbsp; Generert: {dato_str} &nbsp;|&nbsp; Status: {d['status']}</p>
</div>

<div class="rig">⏰ Ferdig rigget: <span style="color:#b35c00;">{rig_linje}</span></div>

<div class="grid">
  <div class="card">
    <h3>📍 Sted / Lokasjon</h3>
    <div class="val">{vp['sted'] or '–'}</div>
  </div>
  <div class="card">
    <h3>🕐 Tid</h3>
    <div class="val">{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div>
  </div>
  <div class="card">
    <h3>👷 Lagleder</h3>
    <div class="val">{vp['lagleder'] or '–'}</div>
  </div>
  <div class="card">
    <h3>📻 Talegruppe i bruk</h3>
    <div class="val">{vp['talegruppe'] or '–'}</div>
  </div>
  <div class="card">
    <h3>👥 Mannskaper</h3>
    <ul>{mannskaper_html}</ul>
  </div>
  <div class="card">
    <h3>🎒 Utstyr</h3>
    <ul>{utstyr_html}</ul>
  </div>
</div>

<div class="nood">
  <div class="card">
    <h3>🏥 Nærmeste legevakt</h3>
    <div class="val">{vp['legevakt'] or '–'}</div>
  </div>
  <div class="card">
    <h3>🏨 Nærmeste sykehus</h3>
    <div class="val">{vp['sykehus'] or '–'}</div>
  </div>
</div>

{f'<div class="card full" style="margin-bottom:16px;"><h3>📝 Merknader</h3><div>{vp["notat"]}</div></div>' if vp["notat"] else ''}

<div class="footer">Norsk Folkehjelp – Melhus &amp; Orkland &nbsp;|&nbsp; Vaktleder: {d['leder']} &nbsp;|&nbsp; Vakt-tlf: {d['vakt']}</div>
</body></html>"""

def _les_gammel_format(filnavn):
    data = dict(DEFAULTS)
    try:
        with open(filnavn, "r", encoding="utf-8") as f:
            for item in f.read().split("###"):
                if "===" in item:
                    k, v = item.split("===", 1)
                    k = k.strip()
                    if k in data:
                        data[k] = v.strip()
    except Exception:
        pass
    return data

def last_data():
    if os.path.exists(FIL):
        try:
            with open(FIL, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = dict(DEFAULTS)
            result.update({k: v for k, v in data.items() if k in DEFAULTS})
            return result
        except Exception:
            pass
    # Migrer fra gammelt format hvis JSON ikke finnes
    for gammel in GAMLE_FILER:
        if os.path.exists(gammel):
            data = _les_gammel_format(gammel)
            lagre_data(data)
            return data
    return dict(DEFAULTS)

# NVE-regioner tilgjengelig via Varsom API (kun fjellområder med skredvarsling)
NVE_REGIONER = {
    # 3019=Nord-Trøndelag, 3020=Sør-Trøndelag (viktigst!), 3022=Trollheimen
    "Trøndelag (Melhus/Orkland)": [3019, 3020, 3022],
    "Hele Norge":                  list(range(3001, 3035)),
    "Nord-Norge":                  [3005, 3006, 3007, 3008, 3009, 3010, 3011, 3012, 3013, 3014, 3015, 3016, 3017, 3018],
    "Vestlandet":                  [3021, 3023, 3024],  # Ytre Nordmøre, Romsdal, Sunnmøre
    "Sørlandet":                   [],
    "Østlandet":                   [3025],              # Nord-Gudbrandsdalen
}

# --- API-HJELPER ---

def _sjekk_koordinat(koordinater, region_valg):
    reg = REGION_FILTER.get(region_valg, {})
    if not all(k in reg for k in ("lat_min", "lat_max", "lon_min", "lon_max")):
        return False
    try:
        lon, lat = koordinater[0][0][0][0], koordinater[0][0][0][1]
        return reg["lat_min"] <= lat <= reg["lat_max"] and reg["lon_min"] <= lon <= reg["lon_max"]
    except (IndexError, TypeError):
        return False

def _sjekk_region(omrade, fylke, region_valg):
    if region_valg == "Hele Norge":
        return True
    termer = REGION_FILTER.get(region_valg, {}).get("termer", [])
    tekst = f"{omrade} {fylke}".lower()
    return any(term in tekst for term in termer)

# --- API: VARSLER ---

@st.cache_data(ttl=300)
def hent_nve_varsler(region_valg):
    varsler = {}
    region_ids = NVE_REGIONER.get(region_valg, [])
    if not region_ids:
        return varsler

    today = datetime.now().strftime('%Y-%m-%d')
    feil_vist = False

    for region_id in region_ids:
        try:
            r = requests.get(
                f"https://api01.nve.no/hydrology/forecast/avalanche/v6.3.0/api/AvalancheWarningByRegion/Detail/{region_id}/no/{today}/{today}",
                headers=STD_HEADERS, timeout=10
            )
            r.raise_for_status()
            for v in r.json():
                try:
                    nivaa = int(v.get('DangerLevel', 0))
                except (ValueError, TypeError):
                    nivaa = 0
                if nivaa < 2:
                    continue
                omrade = v.get('RegionName', '')
                varsler[f"{omrade}_SNØSKRED"] = {
                    "Område": omrade, "Nivå": nivaa, "Type": "SNØSKRED",
                    "Kilde": "Varsom.no", "Info": v.get('MainText', 'Se Varsom.no for detaljer')
                }
        except requests.exceptions.ConnectionError:
            if not feil_vist:
                st.warning("⚠️ Kan ikke nå Varsom (NVE) – sjekk internettforbindelsen.")
                feil_vist = True
            break
        except requests.exceptions.Timeout:
            if not feil_vist:
                st.warning("⚠️ Varsom (NVE) svarte ikke innen 10 sekunder.")
                feil_vist = True
            break
        except requests.exceptions.HTTPError as e:
            if not feil_vist:
                st.warning(f"⚠️ Varsom (NVE) returnerte feil: {e}")
                feil_vist = True
            break
        except Exception as e:
            if not feil_vist:
                st.warning(f"⚠️ Uventet feil fra Varsom (NVE): {e}")
                feil_vist = True
            break
    return varsler

@st.cache_data(ttl=300)
def hent_met_varsler(region_valg):
    varsler = {}
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/metalerts/2.0/current.json",
            headers=STD_HEADERS, timeout=10
        )
        r.raise_for_status()
        for feat in r.json().get('features', []):
            p = feat.get('properties', {})

            if p.get('geographicDomain') == 'marine':
                continue

            farge = p.get('riskMatrixColor', '').lower()
            if 'red' in farge:       nivaa = 4
            elif 'orange' in farge:  nivaa = 3
            elif 'yellow' in farge:  nivaa = 2
            else:                    continue

            omrade = p.get('area', '')
            fylke = p.get('county', '')

            treff = _sjekk_region(omrade, fylke, region_valg)
            if not treff:
                treff = _sjekk_koordinat(feat.get('geometry', {}).get('coordinates', []), region_valg)
            if not treff:
                continue

            event_type = p.get('event', '')
            if event_type == "snowAvalanche":
                continue  # dekkes av NVE

            norsk_type = EVENT_MAP.get(event_type, event_type.upper())
            kilde = "Varsom/NVE" if event_type in ("flood", "landslide") else "Yr/MET"
            navn = omrade.split(",")[0]

            varsler[f"{navn}_{norsk_type}"] = {
                "Område": navn, "Nivå": nivaa, "Type": norsk_type,
                "Kilde": kilde, "Info": p.get('title', 'Aktivt farevarsel')
            }
    except requests.exceptions.ConnectionError:
        st.warning("⚠️ Kan ikke nå MET.no – sjekk internettforbindelsen.")
    except requests.exceptions.Timeout:
        st.warning("⚠️ MET.no svarte ikke innen 10 sekunder.")
    except requests.exceptions.HTTPError as e:
        st.warning(f"⚠️ MET.no returnerte feil: {e}")
    except Exception as e:
        st.warning(f"⚠️ Uventet feil fra MET.no: {e}")
    return varsler

def hent_alle_varsler(region_valg):
    varsler = {}
    varsler.update(hent_nve_varsler(region_valg))
    varsler.update(hent_met_varsler(region_valg))
    return list(varsler.values())

@st.cache_data(ttl=300)
def hent_lokal_vaer():
    try:
        r = requests.get(
            "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.28&lon=10.28",
            headers=STD_HEADERS, timeout=10
        )
        r.raise_for_status()
        data = r.json()['properties']['timeseries']
        now = data[0]['data']['instant']['details']
        prog = [
            {
                "t": datetime.fromisoformat(data[i]['time'].replace('Z', '+00:00')).strftime('%H:%M'),
                "temp": data[i]['data']['instant']['details']['air_temperature']
            }
            for i in range(1, 5)
        ]
        return now['air_temperature'], now['wind_speed'], prog
    except Exception:
        return None, None, []

def generer_tilbud_html(kunde, arrangement, dato_str, linjer, total, forbruk):
    rader = ""
    for navn, beregning, belop in linjer:
        if belop == 0:
            continue
        rader += f"""
        <tr>
          <td>{navn}</td>
          <td style='color:#555; font-size:0.85rem;'>{beregning}</td>
          <td style='text-align:right; font-weight:bold;'>{belop:,.0f} kr</td>
        </tr>""".replace(",", " ")
    if forbruk:
        rader += f"""
        <tr>
          <td>Forbruksmateriell</td>
          <td style='color:#555; font-size:0.85rem;'>Manuelt oppgitt</td>
          <td style='text-align:right; font-weight:bold;'>{forbruk:,.0f} kr</td>
        </tr>""".replace(",", " ")
    dato_generert = datetime.now().strftime("%d.%m.%Y")
    return f"""<!DOCTYPE html>
<html lang="no"><head><meta charset="UTF-8">
<title>Tilbud – {arrangement}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, sans-serif; color: #222; padding: 40px; max-width: 750px; margin: 0 auto; }}
  .header {{ background: #cc0000; color: white; padding: 28px 32px; border-radius: 10px; margin-bottom: 28px; }}
  .header h1 {{ font-size: 1.6rem; margin-bottom: 6px; }}
  .header p {{ opacity: 0.88; font-size: 0.95rem; }}
  .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 24px; }}
  .meta div {{ background: #f5f5f5; border-radius: 8px; padding: 14px 18px; }}
  .meta .label {{ font-size: 0.75rem; text-transform: uppercase; color: #888; margin-bottom: 4px; }}
  .meta .val {{ font-weight: bold; font-size: 1rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  th {{ background: #222; color: white; padding: 10px 14px; text-align: left; font-size: 0.85rem; }}
  th:last-child {{ text-align: right; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #eee; }}
  tr:hover td {{ background: #fafafa; }}
  .total-row td {{ border-top: 3px solid #cc0000; font-size: 1.15rem; font-weight: bold; background: #fff8f8; }}
  .total-row td:last-child {{ color: #cc0000; font-size: 1.3rem; text-align: right; }}
  .footer {{ color: #aaa; font-size: 0.8rem; text-align: center; margin-top: 28px; border-top: 1px solid #eee; padding-top: 14px; }}
  @media print {{ body {{ padding: 20px; }} }}
</style>
</head>
<body>
<div class="header">
  <h1>🚑 Tilbud – Sanitetsvakt</h1>
  <p>Norsk Folkehjelp Melhus &amp; Orkland &nbsp;·&nbsp; Utstedt: {dato_generert}</p>
</div>
<div class="meta">
  <div><div class="label">Kunde / Arrangør</div><div class="val">{kunde or '–'}</div></div>
  <div><div class="label">Arrangement</div><div class="val">{arrangement or '–'}</div></div>
  <div><div class="label">Dato for vakt</div><div class="val">{dato_str or '–'}</div></div>
</div>
<table>
  <thead><tr><th>Beskrivelse</th><th>Beregning</th><th style='text-align:right;'>Beløp</th></tr></thead>
  <tbody>
    {rader}
    <tr class="total-row">
      <td colspan="2">TOTALT</td>
      <td>{total:,.0f} kr</td>
    </tr>
  </tbody>
</table>
<div class="footer">
  Norsk Folkehjelp – Melhus &amp; Orkland &nbsp;|&nbsp;
  Tilbud generert {dato_generert} via NF Operativ Tavle<br>
  Priser er veiledende og ekskl. mva. der annet ikke er avtalt.
</div>
</body></html>""".replace(",", " ")


# --- UI ---

st.set_page_config(page_title="NF Operativ Tavle – Melhus/Orkland", layout="wide")

# CSS – fungerer i både lys og mørk modus
st.markdown("""
<style>
.nf-card {
    background: rgba(128,128,128,0.07);
    border: 1px solid rgba(128,128,128,0.2);
    border-radius: 12px; padding: 15px; min-height: 160px;
}
.nf-card-blue {
    background: rgba(46,89,132,0.08);
    border: 2px solid #2e5984;
    border-radius: 12px; padding: 15px; min-height: 160px;
}
.nf-label {
    font-size: 0.75rem; text-transform: uppercase;
    letter-spacing: 0.05em; opacity: 0.6; margin-bottom: 4px;
}
.nf-val { font-size: 1.05rem; font-weight: bold; }
.nf-card-danger {
    background: rgba(220,53,69,0.10); border: 1px solid #dc3545;
    border-radius: 10px; padding: 14px; margin-top: 10px;
}
.nf-card-info {
    background: rgba(33,150,243,0.10); border: 1px solid #2196f3;
    border-radius: 10px; padding: 14px; margin-top: 10px;
}
.nf-rig {
    background: rgba(255,193,7,0.18); border: 1px solid #ffc107;
    border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; font-size: 0.9rem;
}
.nf-ok-box {
    border: 2px solid #28a745; border-radius: 12px;
    padding: 60px 20px; text-align: center; height: 430px;
    display: flex; flex-direction: column; justify-content: center;
    background: rgba(40,167,69,0.06);
}
.nf-infra-base { border-radius: 12px; padding: 15px; min-height: 160px; }
.nf-infra-ok   { border: 2px solid #28a745; background: rgba(40,167,69,0.07); }
.nf-infra-warn { border: 2px solid #ffc107; background: rgba(255,193,7,0.09); }
.nf-infra-err  { border: 2px solid #dc3545; background: rgba(220,53,69,0.07); }
.nf-divider    { border-bottom: 1px solid rgba(128,128,128,0.2); margin: 3px 0; }
</style>
""", unsafe_allow_html=True)
d = last_data()
vp = last_vaktplan()
epost_cfg = last_epost_config()
avvik_liste = last_liste(AVVIK_FIL)
deltakelse_liste = last_liste(DELTAKELSE_FIL)
akutte = [a for a in avvik_liste if a.get("umiddelbar_oppfolging") and not a.get("fulgt_opp")]

# --- SIDEMENY ---
with st.sidebar:
    if os.path.exists("nf_logo.png"):
        st.image("nf_logo.png", width=180)
    st.markdown("## 📋 Registreringer")

    if akutte:
        st.markdown(f"""
            <div style='background:linear-gradient(135deg,#e65c00,#c0392b);
            padding:12px 15px; border-radius:8px; color:white; font-weight:bold;
            margin-bottom:8px; border-left:5px solid #ff0000;'>
            ⚡ {len(akutte)} avvik krever umiddelbar oppfølging!
            </div>""", unsafe_allow_html=True)

    tab_del, tab_avvik, tab_vakt, tab_kalkyle = st.tabs(["👤 Deltakelse", "⚠️ Avvik", "📋 Vaktinstruks", "💰 Kalkyle"])

    with tab_del:
        with st.form("deltakelse_form", clear_on_submit=True):
            navn = st.text_input("Navn *")
            oppdrag = st.selectbox("Oppdrag", ["SAR", "Sanitetsvakt", "Annen hendelse", "Kurs/øvelse"])
            kol1, kol2 = st.columns(2)
            with kol1:
                tid_ut = st.text_input("Tid ut", placeholder="08:00")
            with kol2:
                tid_inn = st.text_input("Tid inn", placeholder="16:00")
            utlegg = st.number_input("Private utlegg (kr)", min_value=0, step=50, value=0)
            opplastet = st.file_uploader(
                "Kvittering / vedlegg",
                type=["jpg", "jpeg", "png", "pdf"],
                accept_multiple_files=True
            )
            if st.form_submit_button("💾 Registrer", use_container_width=True, type="primary"):
                if not navn.strip():
                    st.error("Navn er påkrevd.")
                else:
                    os.makedirs(VEDLEGG_MAPPE, exist_ok=True)
                    vedlegg_navn = []
                    for fil in (opplastet or []):
                        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filnavn = f"{ts}_{fil.name}"
                        with open(os.path.join(VEDLEGG_MAPPE, filnavn), "wb") as f:
                            f.write(fil.read())
                        vedlegg_navn.append(filnavn)
                    liste = last_liste(DELTAKELSE_FIL)
                    liste.append({
                        "registrert": datetime.now().strftime('%d.%m.%Y %H:%M'),
                        "navn": navn.strip(),
                        "oppdrag": oppdrag,
                        "tid_ut": tid_ut.strip(),
                        "tid_inn": tid_inn.strip(),
                        "utlegg_kr": utlegg,
                        "vedlegg": vedlegg_navn
                    })
                    lagre_liste(DELTAKELSE_FIL, liste)
                    st.success("✅ Deltakelse registrert!")

    with tab_avvik:
        with st.form("avvik_form", clear_on_submit=True):
            av_navn = st.text_input("Navn *")
            av_epost = st.text_input("E-post")
            av_hendelse = st.text_area("Hendelse *", placeholder="Beskriv hva som skjedde...", height=100)
            av_konsekvens = st.text_area("Konsekvens", placeholder="Hva ble konsekvensen?", height=80)
            av_umiddelbar = st.checkbox("⚡ Krever umiddelbar oppfølging")
            if st.form_submit_button("📨 Send avvik", use_container_width=True, type="primary"):
                if not av_navn.strip() or not av_hendelse.strip():
                    st.error("Navn og hendelse er påkrevd.")
                else:
                    nytt_avvik = {
                        "id": datetime.now().strftime('%Y%m%d%H%M%S'),
                        "registrert": datetime.now().strftime('%d.%m.%Y %H:%M'),
                        "navn": av_navn.strip(),
                        "epost": av_epost.strip(),
                        "hendelse": av_hendelse.strip(),
                        "konsekvens": av_konsekvens.strip(),
                        "umiddelbar_oppfolging": av_umiddelbar,
                        "fulgt_opp": False,
                        "oppfolging_notat": ""
                    }
                    liste = last_liste(AVVIK_FIL)
                    liste.append(nytt_avvik)
                    lagre_liste(AVVIK_FIL, liste)
                    if av_umiddelbar:
                        st.warning("⚡ Avvik registrert – krever umiddelbar oppfølging!")
                    else:
                        st.success("✅ Avvik registrert!")
                    # Send e-post
                    ok, melding = send_avvik_epost(nytt_avvik, epost_cfg)
                    if ok:
                        st.caption(f"📧 {melding}")
                    elif epost_cfg.get("smtp_server"):
                        st.caption(f"⚠️ {melding}")

    with tab_vakt:
        if vp["aktiv"] and (vp["sted"] or vp["lagleder"]):
            rig = _beregn_rig_tid(vp["tid_fra"])
            st.markdown(f"""
            <div style='background:#fff3cd; border:1px solid #ffc107;
            border-radius:8px; padding:10px 14px; margin-bottom:10px;
            font-size:0.9rem;'>
            ⏰ <b>Ferdig rigget:</b> {rig + " (30 min før)" if rig else "–"}
            </div>""", unsafe_allow_html=True)
            felter = [
                ("📍 Sted", vp["sted"]),
                ("🕐 Tid", f"{vp['tid_fra']} – {vp['tid_til']}"),
                ("👷 Lagleder", vp["lagleder"]),
                ("📻 Talegruppe", vp["talegruppe"]),
                ("🏥 Legevakt", vp["legevakt"]),
                ("🏨 Sykehus", vp["sykehus"]),
            ]
            for label, verdi in felter:
                if verdi.strip():
                    st.markdown(f"**{label}:** {verdi}")
            if vp["mannskaper"]:
                st.markdown("**👥 Mannskaper:**")
                for m in vp["mannskaper"].splitlines():
                    if m.strip():
                        st.markdown(f"&nbsp;&nbsp;• {m.strip()}")
            if vp["utstyr"]:
                st.markdown("**🎒 Utstyr:**")
                for u in vp["utstyr"].splitlines():
                    if u.strip():
                        st.markdown(f"&nbsp;&nbsp;• {u.strip()}")
            if vp["notat"]:
                st.markdown(f"**📝 Merknad:** {vp['notat']}")
            html_innhold = generer_html_export(vp, d)
            st.download_button(
                "📥 Eksporter beredskapsplan",
                data=html_innhold.encode("utf-8"),
                file_name=f"beredskapsplan_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                mime="text/html",
                use_container_width=True
            )
        else:
            st.info("Ingen aktiv vaktinstruks. Fyll ut under ⚙️ Administrasjon.")

    with tab_kalkyle:
        st.markdown("**Kalkyle – Sanitetsvakt**")

        k_kunde       = st.text_input("Kunde / Arrangør", key="k_kunde", placeholder="Melhus IL")
        k_arrangement = st.text_input("Arrangement", key="k_arr", placeholder="Sommerstevne 2026")
        k_dato        = st.text_input("Dato for vakt", key="k_dato", placeholder="21.06.2026")

        st.markdown("<small style='opacity:0.6;'>── Grunnlag ──</small>", unsafe_allow_html=True)
        k_dager = st.number_input("Dager", min_value=0, value=1, step=1, key="k_dag")

        st.markdown("<small style='opacity:0.6;'>── Mannskap ──</small>", unsafe_allow_html=True)
        ks1, ks2 = st.columns(2)
        with ks1:
            k_san_ant   = st.number_input("Sanitet – pers.", min_value=0, value=0, step=1, key="k_s_ant")
            k_ambu_ant  = st.number_input("Ambulanse – pers.", min_value=0, value=0, step=1, key="k_a_ant")
        with ks2:
            k_san_tim   = st.number_input("Sanitet – t/dag", min_value=0, value=0, step=1, key="k_s_tim")
            k_ambu_tim  = st.number_input("Ambulanse – t/dag", min_value=0, value=0, step=1, key="k_a_tim")

        st.markdown("<small style='opacity:0.6;'>── Kjøretøy ──</small>", unsafe_allow_html=True)
        kv1, kv2, kv3 = st.columns(3)
        with kv1: k_mbil  = st.number_input("Mannskapsbil", min_value=0, value=0, step=1, key="k_mbil")
        with kv2: k_amb   = st.number_input("Ambulanse", min_value=0, value=0, step=1, key="k_amb")
        with kv3: k_atv   = st.number_input("ATV", min_value=0, value=0, step=1, key="k_atv")

        st.markdown("<small style='opacity:0.6;'>── Kjøring (km) ──</small>", unsafe_allow_html=True)
        kk1, kk2 = st.columns(2)
        with kk1:
            k_km_51  = st.number_input("T/F tjenestested 5.1", min_value=0, value=0, step=1, key="k_51")
            k_km_56  = st.number_input("T/F tjenestested 5.6", min_value=0, value=0, step=1, key="k_56")
        with kk2:
            k_km_bil = st.number_input("I tjeneste – bil", min_value=0, value=0, step=1, key="k_kbil")
            k_km_amb = st.number_input("I tjeneste – ambulanse", min_value=0, value=0, step=1, key="k_kamb")
        k_atv_tim = st.number_input("ATV/scooter i tjeneste (timer)", min_value=0, value=0, step=1, key="k_atv_t")

        st.markdown("<small style='opacity:0.6;'>── Annet ──</small>", unsafe_allow_html=True)
        k_forbruk = st.number_input("Forbruksmateriell (kr)", min_value=0, value=0, step=50, key="k_forb")

        # Kalkulasjon
        PRISER = {
            "grunnpris": 800, "sanitet": 160, "ambulanse_m": 300,
            "mbil": 300, "amb_kjt": 900, "atv_kjt": 300,
            "km": 8, "atv_t": 200
        }
        linjer = [
            ("Grunnpris",
             f"{k_dager} dag{'er' if k_dager != 1 else ''} × {PRISER['grunnpris']} kr",
             PRISER["grunnpris"] * k_dager),
            ("Mannskap sanitet",
             f"{k_san_ant} pers. × {k_dager} dag × {k_san_tim} t × {PRISER['sanitet']} kr",
             PRISER["sanitet"] * k_san_ant * k_dager * k_san_tim),
            ("Mannskap ambulanse",
             f"{k_ambu_ant} pers. × {k_dager} dag × {k_ambu_tim} t × {PRISER['ambulanse_m']} kr",
             PRISER["ambulanse_m"] * k_ambu_ant * k_dager * k_ambu_tim),
            ("Mannskapsbil (grunnpris)",
             f"{k_mbil} stk × {k_dager} dag × {PRISER['mbil']} kr",
             PRISER["mbil"] * k_mbil * k_dager),
            ("Ambulanse (grunnpris)",
             f"{k_amb} stk × {k_dager} dag × {PRISER['amb_kjt']} kr",
             PRISER["amb_kjt"] * k_amb * k_dager),
            ("ATV 6.1 (grunnpris)",
             f"{k_atv} stk × {k_dager} dag × {PRISER['atv_kjt']} kr",
             PRISER["atv_kjt"] * k_atv * k_dager),
            ("Kjøring t/f tjenestested 5.1",
             f"{k_km_51} km × {PRISER['km']} kr",
             PRISER["km"] * k_km_51),
            ("Kjøring t/f tjenestested 5.6",
             f"{k_km_56} km × {PRISER['km']} kr",
             PRISER["km"] * k_km_56),
            ("Kjøring i tjeneste – bil",
             f"{k_km_bil} km × {PRISER['km']} kr",
             PRISER["km"] * k_km_bil),
            ("Kjøring i tjeneste – ambulanse",
             f"{k_km_amb} km × {PRISER['km']} kr",
             PRISER["km"] * k_km_amb),
            ("Kjøring i tjeneste – ATV/scooter",
             f"{k_atv_tim} t × {PRISER['atv_t']} kr",
             PRISER["atv_t"] * k_atv_tim),
        ]
        total = sum(b for _, _, b in linjer) + k_forbruk

        # Vis total
        st.markdown(f"""
        <div style='background:#cc0000; color:white; border-radius:8px;
        padding:12px 16px; text-align:center; margin:10px 0;'>
        <div style='font-size:0.8rem; opacity:0.85;'>ESTIMERT TOTALPRIS</div>
        <div style='font-size:1.8rem; font-weight:bold;'>{total:,.0f} kr</div>
        </div>""".replace(",", " "), unsafe_allow_html=True)

        if st.button("📄 Generer tilbud", use_container_width=True, type="primary", key="k_gen"):
            html = generer_tilbud_html(k_kunde, k_arrangement, k_dato, linjer, total, k_forbruk)
            filnavn = f"tilbud_{(k_arrangement or 'sanitetsvakt').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.html"
            st.download_button(
                "📥 Last ned tilbud (HTML)",
                data=html.encode("utf-8"),
                file_name=filnavn,
                mime="text/html",
                use_container_width=True,
                key="k_dl"
            )

    st.markdown("---")
    m1, m2 = st.columns(2)
    m1.metric("Deltakelser", len(deltakelse_liste))
    m2.metric("Avvik", len(avvik_liste),
              delta=f"{len(akutte)} akutte" if akutte else None,
              delta_color="inverse")

# --- HOVEDINNHOLD ---

st.markdown(
    "<h2 style='text-align:center; color:#cc0000;'>🚑 Norsk Folkehjelp: Melhus & Orkland</h2>",
    unsafe_allow_html=True
)

# STATUS-BANNER
bg = STATUS_FARGER.get(d['status'], "#333")
st.markdown(f"""
    <div style="background-color:{bg}; padding:20px; border-radius:15px;
    text-align:center; color:white; border:2px solid rgba(0,0,0,0.2);">
        <h1 style="margin:0; font-size:3.5rem;">{d['status']}</h1>
        <p style="font-size:1.5rem; margin-top:5px; font-weight:500;">{d['beskjed']}</p>
    </div>
""", unsafe_allow_html=True)

st.write("")

# ALARMTONE VED RØD BEREDSKAP
if d['status'] == "🔴 Rød / Høy beredskap":
    if not st.session_state.get("alarm_spilt"):
        st.session_state["alarm_spilt"] = True
        components.html("""
        <script>
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        function pip(freq, start, dur) {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.type = 'square';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0.4, ctx.currentTime + start);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
            osc.start(ctx.currentTime + start);
            osc.stop(ctx.currentTime + start + dur + 0.05);
        }
        // Tre korte pip etterfulgt av ett langt
        pip(880, 0.0, 0.15);
        pip(880, 0.2, 0.15);
        pip(880, 0.4, 0.15);
        pip(660, 0.7, 0.6);
        </script>
        """, height=0)
else:
    st.session_state["alarm_spilt"] = False

# AKUTT AVVIK-BANNER
if akutte:
    st.markdown(f"""
        <div style='background:linear-gradient(135deg,#e65c00,#c0392b);
        padding:15px 20px; border-radius:10px; color:white;
        border-left:6px solid #ff0000; margin-bottom:10px;'>
        <b style='font-size:1.1rem;'>⚡ {len(akutte)} avvik krever umiddelbar oppfølging</b>
        &nbsp;–&nbsp; åpne administrasjonspanelet nedenfor.
        </div>""", unsafe_allow_html=True)

# INFO-PANEL
c_vaer, c_led, c_infra = st.columns([1.2, 1, 1.2])

with c_vaer:
    t, v, prog = hent_lokal_vaer()
    if t is not None:
        prog_str = ' | '.join([f"{i['t']}: {i['temp']}°" for i in prog])
        st.markdown(
            f"<div class='nf-card'>"
            f"<b>📍 Melhus Sentrum:</b><br>"
            f"<h2 style='margin:5px 0; color:#1f77b4;'>{t}°C &nbsp;|&nbsp; {v} m/s</h2>"
            f"<small style='opacity:0.7;'>{prog_str}</small></div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div class='nf-card'>"
            "<b>📍 Melhus Sentrum:</b><br><br>"
            "<small>⚠️ Værvarselet er ikke tilgjengelig akkurat nå.</small></div>",
            unsafe_allow_html=True
        )

with c_led:
    kort_stil = (
        "background:rgba(128,128,128,0.15); color:inherit; border:1px solid rgba(128,128,128,0.3); font-size:0.85rem; opacity:0.7;"
        if d['kort'] in ('Ingen', 'Daglig drift') else
        "background:#cc0000; color:white; border:2px solid #990000; box-shadow:0 2px 8px rgba(200,0,0,0.4); font-size:1rem;"
    )
    st.markdown(
        f"<div class='nf-card-blue'>"
        f"<b>📞 Operativ Ledelse:</b><br>"
        f"<span style='font-size:1.1rem;'>Leder: <b>{d['leder']}</b></span><br>"
        f"<span style='font-size:1.1rem;'>Vakt-tlf: <b>{d['vakt']}</b></span>"
        f"<br><br><div style='display:inline-block; {kort_stil} padding:4px 12px; border-radius:6px; font-weight:bold;'>"
        f"📋 {d['kort']}</div></div>",
        unsafe_allow_html=True
    )

with c_infra:
    # Bakgrunnsfarge basert på verste status
    if "🔴" in d['ekom'] or "🔴" in d['vei']:
        infra_bg, infra_border = "#ffebee", "#dc3545"
    elif "🟡" in d['ekom'] or "🟡" in d['vei']:
        infra_bg, infra_border = "#fff8e1", "#ffc107"
    else:
        infra_bg, infra_border = "#f1fff4", "#28a745"

    infra_cls = "nf-infra-err" if ("🔴" in d['ekom'] or "🔴" in d['vei']) else ("nf-infra-warn" if ("🟡" in d['ekom'] or "🟡" in d['vei']) else "nf-infra-ok")
    st.markdown(
        f"<div class='nf-infra-base {infra_cls}'>"
        f"<b>📡 Kritisk Infrastruktur:</b><br><br>"
        f"<span style='font-weight:bold; font-size:1rem;'>EKOM:</span>"
        f"<br><span style='font-size:0.9rem; opacity:0.9;'>{d['ekom']}</span><br><br>"
        f"<span style='font-weight:bold; font-size:1rem;'>VEI / ISOLASJON:</span>"
        f"<br><span style='font-size:0.9rem; opacity:0.9;'>{d['vei']}</span></div>",
        unsafe_allow_html=True
    )

# KART OG VARSLER
st.write("---")
c_tittel, c_filter = st.columns([3, 1])
with c_tittel:
    st.subheader("🚨 Operativ Oversikt & Farevarsler")
with c_filter:
    valgt_region = st.selectbox("🌍 Velg område:", list(KART_KOORDINATER.keys()), index=0)

coords = KART_KOORDINATER.get(valgt_region, "lat=63.26&lon=10.15&zoom=8")
c_map, c_alerts = st.columns([1.5, 1])

with c_map:
    windy_url = f"https://embed.windy.com/embed2.html?{coords}&overlay=wind&metricWind=m%2Fs"
    components.iframe(windy_url, height=450)

with c_alerts:
    varsler = hent_alle_varsler(valgt_region)
    if varsler:
        df = pd.DataFrame(varsler).sort_values(by=["Nivå", "Område"], ascending=[False, True])
        def style_row(row):
            c = {2: ("#FFFF00", "black"), 3: ("#FF9900", "white"), 4: ("#FF0000", "white")}.get(row.Nivå, ("white", "black"))
            return [f'background-color: {c[0]}; color: {c[1]}; font-weight: bold'] * len(row)
        st.dataframe(df.style.apply(style_row, axis=1), use_container_width=True, height=450, hide_index=True)
    else:
        region_kort = valgt_region.split(" ")[0]
        st.markdown(f"""
            <div class='nf-ok-box'>
            <div style='font-size:3rem;'>✅</div>
            <div style='font-size:1.2rem; font-weight:bold; color:#28a745; margin-top:10px;'>
                Ingen aktive farevarsler</div>
            <div style='opacity:0.6; margin-top:6px;'>for {region_kort}</div>
            </div>""", unsafe_allow_html=True)

# OPERATIV LOGG
if d['logg']:
    st.write("---")
    st.subheader("📝 Operativ Logg")
    st.text_area("", value=d['logg'], height=120, disabled=True, label_visibility="collapsed")

# VAKTINSTRUKS I HOVEDVISNING
if vp["aktiv"] and (vp["sted"] or vp["lagleder"]):
    st.write("---")
    st.subheader("📋 Instruks for aktivitet/vakt")
    rig = _beregn_rig_tid(vp["tid_fra"])
    vi1, vi2, vi3 = st.columns(3)
    with vi1:
        rig_html = f"<div class='nf-rig' style='margin-top:8px;'>⏰ Ferdig rigget: <b>{rig}</b></div>" if rig else ""
        st.markdown(f"""
        <div class='nf-card' style='min-height:unset;'>
        <div class='nf-label'>📍 Sted</div>
        <div class='nf-val' style='font-size:1.15rem;'>{vp['sted'] or '–'}</div>
        <div class='nf-label' style='margin-top:10px;'>🕐 Tid</div>
        <div class='nf-val'>{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div>
        {rig_html}
        </div>""", unsafe_allow_html=True)
    with vi2:
        mannskaper_vis = "".join(
            f"<div class='nf-divider'>• {m.strip()}</div>"
            for m in vp["mannskaper"].splitlines() if m.strip()
        ) or "<em style='opacity:0.4;'>Ikke oppgitt</em>"
        st.markdown(f"""
        <div class='nf-card' style='min-height:unset;'>
        <div class='nf-label'>👷 Lagleder</div>
        <div class='nf-val' style='margin-bottom:10px;'>{vp['lagleder'] or '–'}</div>
        <div class='nf-label'>👥 Mannskaper</div>
        <div style='font-size:0.9rem; line-height:1.8;'>{mannskaper_vis}</div>
        </div>""", unsafe_allow_html=True)
    with vi3:
        utstyr_vis = "".join(
            f"<div class='nf-divider'>• {u.strip()}</div>"
            for u in vp["utstyr"].splitlines() if u.strip()
        ) or "<em style='opacity:0.4;'>Ikke oppgitt</em>"
        st.markdown(f"""
        <div class='nf-card' style='min-height:unset;'>
        <div class='nf-label'>🎒 Utstyr</div>
        <div style='font-size:0.9rem; line-height:1.8;'>{utstyr_vis}</div>
        </div>""", unsafe_allow_html=True)

    vi4, vi5, vi6 = st.columns(3)
    with vi4:
        st.markdown(f"""
        <div class='nf-card-danger'>
        <div class='nf-label'>🏥 Nærmeste legevakt</div>
        <div class='nf-val'>{vp['legevakt'] or '–'}</div>
        </div>""", unsafe_allow_html=True)
    with vi5:
        st.markdown(f"""
        <div class='nf-card-danger'>
        <div class='nf-label'>🏨 Nærmeste sykehus</div>
        <div class='nf-val'>{vp['sykehus'] or '–'}</div>
        </div>""", unsafe_allow_html=True)
    with vi6:
        st.markdown(f"""
        <div class='nf-card-info'>
        <div class='nf-label'>📻 Talegruppe</div>
        <div class='nf-val'>{vp['talegruppe'] or '–'}</div>
        </div>""", unsafe_allow_html=True)

    if vp["notat"]:
        st.info(f"📝 {vp['notat']}")

    html_innhold = generer_html_export(vp, d)
    st.download_button(
        "📥 Eksporter beredskapsplan (HTML)",
        data=html_innhold.encode("utf-8"),
        file_name=f"beredskapsplan_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
        mime="text/html"
    )

# ADMIN
st.write("---")
st.markdown(
    "<div style='text-align:right; color:#999; font-size:0.85rem; margin-bottom:-20px;'>"
    "⚙️ Administrasjon tilgjengelig nedenfor</div>",
    unsafe_allow_html=True
)
with st.expander("⚙️ Administrasjon & Logg"):
    if not st.session_state.get("admin_ok"):
        st.markdown("🔒 **Adminpanelet er passordbeskyttet**")
        pw = st.text_input("Passord", type="password", placeholder="Skriv inn passord...", label_visibility="collapsed")
        if st.button("Logg inn", type="primary"):
            if pw == "melhus123":
                st.session_state["admin_ok"] = True
                st.rerun()
            else:
                st.error("❌ Feil passord")
    else:
        col_lock, _ = st.columns([1, 5])
        with col_lock:
            if st.button("🔓 Logg ut admin"):
                st.session_state["admin_ok"] = False
                st.rerun()

        a1, a2 = st.columns(2)
        with a1:
            status_valg = ["🟢 Normal Beredskap", "🟡 Forhøyet Beredskap", "🔴 Rød / Høy beredskap"]
            n_stat = st.selectbox("Nivå:", status_valg, index=status_valg.index(d['status']))
            n_besk = st.text_area("Beskjed:", value=d['beskjed'])
            kort_valg = ["Ingen", "Daglig drift", "Snøskred", "Flom", "Jordras", "Ekom-bortfall", "Isolasjon / Evakuering", "Søk/Redning"]
            n_kort = st.selectbox("Kort:", kort_valg, index=kort_valg.index(d['kort']))
        with a2:
            n_led = st.text_input("Leder:", value=d['leder'])
            n_vak = st.text_input("Vakt-tlf:", value=d['vakt'])
            n_logg = st.text_area("Logg (siste hendelser):", value=d['logg'], height=150)

        st.write("**Infrastruktur-status**")
        a3, a4 = st.columns(2)
        with a3:
            ekom_valg = ["🟢 Normal drift", "🟡 Redusert kapasitet/Utfall noen steder", "🔴 Omfattende ekom-bortfall"]
            n_ekom = st.selectbox("Ekom / Samband:", ekom_valg, index=ekom_valg.index(d['ekom']))
        with a4:
            vei_valg = ["🟢 Veinett åpent", "🟡 Lokale stengninger", "🔴 Kritiske brudd / Isolerte bygder"]
            n_vei = st.selectbox("Vei / Isolasjon:", vei_valg, index=vei_valg.index(d['vei']))

        if st.button("💾 Lagre alt", type="primary"):
            lagre_data({
                "status": n_stat, "beskjed": n_besk, "leder": n_led,
                "vakt": n_vak, "kort": n_kort, "logg": n_logg,
                "ekom": n_ekom, "vei": n_vei
            })
            st.toast("✅ Innstillinger lagret!", icon="💾")
            st.rerun()

        st.markdown("---")
        st.write("**📋 Instruks for aktivitet/vakt**")
        vp_aktiv = st.checkbox("✅ Aktiver vaktinstruks (vises i appen)", value=vp.get("aktiv", False))
        vp1, vp2 = st.columns(2)
        with vp1:
            vp_sted = st.text_input("📍 Sted / Lokasjon", value=vp.get("sted", ""))
            vp_lagleder = st.text_input("👷 Lagleder", value=vp.get("lagleder", ""))
            vp_talegruppe = st.text_input("📻 Talegruppe i bruk", value=vp.get("talegruppe", ""))
            vp_legevakt = st.text_input("🏥 Nærmeste legevakt", value=vp.get("legevakt", ""), placeholder="f.eks. Melhus legesenter, tlf 72 85 00 00")
            vp_sykehus = st.text_input("🏨 Nærmeste sykehus", value=vp.get("sykehus", ""), placeholder="f.eks. St. Olavs Hospital, Trondheim")
        with vp2:
            vp_tid_fra = st.text_input("🕐 Tid fra (HH:MM)", value=vp.get("tid_fra", ""), placeholder="08:00")
            vp_tid_til = st.text_input("🕑 Tid til (HH:MM)", value=vp.get("tid_til", ""), placeholder="16:00")
            rig_preview = _beregn_rig_tid(vp_tid_fra)
            if rig_preview:
                st.caption(f"⏰ Ferdig rigget: **{rig_preview}** (30 min før oppstart)")
            vp_mannskaper = st.text_area("👥 Mannskaper (ett navn per linje)", value=vp.get("mannskaper", ""), height=100, placeholder="Ola Nordmann\nKari Nordmann")
            vp_utstyr = st.text_area("🎒 Utstyr (ett element per linje)", value=vp.get("utstyr", ""), height=100, placeholder="Båre\nFørstehjelpsveske\nVarmeposer")
        vp_notat = st.text_area("📝 Merknader / Notat", value=vp.get("notat", ""), height=60)

        if st.button("💾 Lagre vaktinstruks", type="primary"):
            lagre_vaktplan({
                "aktiv": vp_aktiv,
                "sted": vp_sted, "lagleder": vp_lagleder,
                "talegruppe": vp_talegruppe, "legevakt": vp_legevakt,
                "sykehus": vp_sykehus, "tid_fra": vp_tid_fra, "tid_til": vp_tid_til,
                "mannskaper": vp_mannskaper, "utstyr": vp_utstyr, "notat": vp_notat
            })
            st.toast("✅ Vaktinstruks lagret!", icon="📋")
            st.rerun()

        st.markdown("---")
        st.write("**📋 Registrerte deltakelser**")
        if deltakelse_liste:
            df_d = pd.DataFrame(deltakelse_liste)[["registrert", "navn", "oppdrag", "tid_ut", "tid_inn", "utlegg_kr"]]
            df_d.columns = ["Tidspunkt", "Navn", "Oppdrag", "Tid ut", "Tid inn", "Utlegg (kr)"]
            st.dataframe(df_d, use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen deltakelser registrert ennå.")

        st.markdown("---")
        åpne = [a for a in avvik_liste if not a.get("fulgt_opp")]
        lukkede = [a for a in avvik_liste if a.get("fulgt_opp")]
        st.write(f"**⚠️ Avvik – {len(åpne)} åpne / {len(lukkede)} lukket**")

        if not avvik_liste:
            st.caption("Ingen avvik registrert ennå.")
        else:
            avvik_endret = False
            for i, a in enumerate(avvik_liste):
                fulgt = a.get("fulgt_opp", False)
                haster = a.get("umiddelbar_oppfolging", False) and not fulgt
                border = "#dc3545" if haster else ("#28a745" if fulgt else "#ffc107")
                bg = "rgba(40,167,69,0.07)" if fulgt else ("rgba(220,53,69,0.07)" if haster else "rgba(255,193,7,0.07)")
                status_ikon = "✅ Lukket" if fulgt else ("⚡ Akutt" if haster else "🟡 Åpen")
                st.markdown(f"""
                <div style='border-left:4px solid {border}; background:{bg};
                border-radius:6px; padding:10px 14px; margin-bottom:6px;'>
                <b>{a.get('navn','–')}</b> &nbsp;·&nbsp;
                <small style='opacity:0.7;'>{a.get('registrert','')}</small>
                &nbsp;·&nbsp; <b>{status_ikon}</b><br>
                <span style='font-size:0.9rem;'>{a.get('hendelse','')}</span>
                {f"<br><small><i>Konsekvens: {a.get('konsekvens','')}</i></small>" if a.get('konsekvens') else ""}
                {f"<br><small>📝 Oppfølging: {a.get('oppfolging_notat','')}</small>" if a.get('oppfolging_notat') else ""}
                </div>""", unsafe_allow_html=True)

                if not fulgt:
                    kol_a, kol_b = st.columns([2, 1])
                    with kol_a:
                        notat = st.text_input(
                            "Notat ved lukking", key=f"notat_{i}",
                            placeholder="Tiltak / kommentar...",
                            label_visibility="collapsed"
                        )
                    with kol_b:
                        if st.button("✅ Marker lukket", key=f"lukk_{i}", use_container_width=True):
                            avvik_liste[i]["fulgt_opp"] = True
                            avvik_liste[i]["oppfolging_notat"] = notat
                            avvik_endret = True
                else:
                    if st.button("↩️ Gjenåpne", key=f"aapne_{i}"):
                        avvik_liste[i]["fulgt_opp"] = False
                        avvik_endret = True

            if avvik_endret:
                lagre_liste(AVVIK_FIL, avvik_liste)
                st.rerun()

        st.markdown("---")
        st.write("**📧 E-postkonfigurasjon for avvarsler**")
        st.caption("Avvik sendes automatisk til oppgitt adresse ved registrering.")
        ep1, ep2 = st.columns(2)
        with ep1:
            ep_server = st.text_input("SMTP-server", value=epost_cfg.get("smtp_server",""), placeholder="smtp.gmail.com")
            ep_port   = st.text_input("Port", value=epost_cfg.get("smtp_port","587"), placeholder="587")
            ep_bruker = st.text_input("SMTP-bruker", value=epost_cfg.get("smtp_bruker",""), placeholder="din@epost.no")
        with ep2:
            ep_passord = st.text_input("SMTP-passord", value=epost_cfg.get("smtp_passord",""), type="password")
            ep_fra     = st.text_input("Fra-adresse", value=epost_cfg.get("fra",""), placeholder="nf-melhus@folkehjelp.no")
            ep_til     = st.text_input("Send avvik til", value=epost_cfg.get("til",""), placeholder="leder@folkehjelp.no")

        ep_kol1, ep_kol2 = st.columns(2)
        with ep_kol1:
            if st.button("💾 Lagre e-postkonfig", use_container_width=True):
                lagre_epost_config({"smtp_server": ep_server, "smtp_port": ep_port,
                    "smtp_bruker": ep_bruker, "smtp_passord": ep_passord,
                    "fra": ep_fra, "til": ep_til})
                st.toast("✅ E-postkonfigurasjon lagret!", icon="📧")
                st.rerun()
        with ep_kol2:
            if st.button("📤 Send testmelding", use_container_width=True):
                test = {"registrert": datetime.now().strftime('%d.%m.%Y %H:%M'),
                        "navn": "Test", "epost": "", "hendelse": "Dette er en testmelding fra NF Operativ Tavle.",
                        "konsekvens": "", "umiddelbar_oppfolging": False}
                ok, melding = send_avvik_epost(test, {"smtp_server": ep_server, "smtp_port": ep_port,
                    "smtp_bruker": ep_bruker, "smtp_passord": ep_passord, "fra": ep_fra, "til": ep_til})
                if ok:
                    st.success(f"✅ {melding}")
                else:
                    st.error(melding)

st.markdown(
    f"<div style='text-align:right; color:#aaa;'>"
    f"<small>Sist lastet: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</small></div>",
    unsafe_allow_html=True
)
