import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import os, json, io, struct, math, re
from datetime import datetime, timedelta

try:
    import gspread
    from google.oauth2.service_account import Credentials as GSCredentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

# ── KONFIGURASJON ────────────────────────────────────────────────────────────

STD_HEADERS = {'User-Agent':'NorskFolkehjelpBeredskap/28.0','Accept':'application/json'}

REGION_FILTER = {
    "Trøndelag (Melhus)": {
        "termer":["50","trøndelag","melhus","orkland","trollheimen","skaun","gauldal","trondheim","oppdal","rindal","heiane"],
        "lat_min":62.5,"lat_max":64.5,"lon_min":8.5,"lon_max":12.5},
    "Hele Norge":{},
    "Nord-Norge":{"termer":["18","54","55","56","nordland","troms","finnmark"]},
    "Vestlandet":{"termer":["11","46","15","rogaland","vestland","møre"]},
    "Sørlandet": {"termer":["42","agder"]},
    "Østlandet": {"termer":["03","31","32","33","34","39","40","oslo","østfold","akershus","buskerud","innlandet","vestfold","telemark"]}
}
KART_KOORDINATER = {
    "Trøndelag (Melhus)":"lat=63.26&lon=10.15&zoom=8",
    "Hele Norge":"lat=64.00&lon=12.00&zoom=4","Nord-Norge":"lat=68.50&lon=15.00&zoom=5",
    "Vestlandet":"lat=60.80&lon=6.00&zoom=6","Sørlandet":"lat=58.50&lon=7.50&zoom=7",
    "Østlandet":"lat=60.50&lon=10.50&zoom=6"
}
EVENT_MAP = {"snowAvalanche":"SNØSKRED","flood":"FLOM","landslide":"JORDSKRED",
             "wind":"VIND","gale":"STORM","ice":"ISING","snow":"SNØFOKK",
             "rain":"STYRTREGN","forestFire":"SKOGBRANNFARE"}
STATUS_FARGER = {"🟢 Normal Beredskap":"#28a745","🟡 Forhøyet Beredskap":"#ffc107","🔴 Rød / Høy beredskap":"#dc3545"}
NVE_REGIONER  = {
    "Trøndelag (Melhus)":[3019,3020,3022],
    "Hele Norge":list(range(3001,3035)),
    "Nord-Norge":[3005,3006,3007,3008,3009,3010,3011,3012,3013,3014,3015,3016,3017,3018],
    "Vestlandet":[3021,3023,3024],"Sørlandet":[],"Østlandet":[3025]
}
PRISER = {"grunnpris":800,"sanitet":160,"ambulanse_m":300,"mbil":300,"amb_kjt":900,"atv_kjt":300,"km":8,"atv_t":200}

# ── DATAFILER ────────────────────────────────────────────────────────────────

FIL              = "beredskap_data.json"
DELTAKELSE_FIL   = "deltakelse_data.json"
AVVIK_FIL        = "avvik_data.json"
VAKTPLAN_FIL     = "vaktplan_data.json"
SKADE_FIL        = "skade_data.json"
LOGG_FIL         = "logg_data.json"
VEDLEGG_MAPPE    = "vedlegg"

# ── GOOGLE SHEETS ─────────────────────────────────────────────────────────────

DELTAKELSE_HDR = ["registrert","navn","oppdrag","tid_ut","tid_inn","utlegg_kr","privatbil","km_kjort","regnr","vedlegg"]
AVVIK_HDR      = ["id","registrert","navn","epost","hendelse","konsekvens",
                   "umiddelbar_oppfolging","fulgt_opp","oppfolging_notat"]
SKADE_HDR      = ["registrert","innsats","behandler","kjonn","alder","skadetype",
                   "behandling","rad","konsultert","utstyr","merknad"]
LOGG_HDR       = ["id","tidspunkt","forfatter","gradering","tekst"]

_GS_BOOL   = {"vaktplan":["aktiv","skjul_forside"],
               "avvik":["umiddelbar_oppfolging","fulgt_opp"]}
_GS_JSON   = {"skade":["skadetype","utstyr"],"deltakelse":["vedlegg"]}

@st.cache_resource
def _gs_sh():
    """Cached spreadsheet connection – gjenbrukes på tvers av alle renders."""
    if not HAS_GSPREAD: return None
    try:
        if "gcp_service_account" not in st.secrets: return None
        # Bruker service_account_from_dict (nyeste gspread API, ingen deprecated-advarsler)
        gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
        return gc.open_by_key(st.secrets["google_sheets"]["spreadsheet_id"])
    except Exception:
        return None

def _gs_ws(tab):
    sh = _gs_sh()
    if not sh: return None
    try: return sh.worksheet(tab)
    except Exception:
        try: return sh.add_worksheet(title=tab, rows=5000, cols=50)
        except: return None

def _gs_deser(row, tab):
    r = dict(row)
    for f in _GS_BOOL.get(tab, []):
        if f in r:
            v = r[f]
            r[f] = (v is True or str(v).upper() in ("TRUE", "1", "YES"))
    for f in _GS_JSON.get(tab, []):
        if f in r and isinstance(r[f], str):
            try: r[f] = json.loads(r[f]) if r[f] else []
            except: r[f] = []
    return r

def _gs_ser_val(v):
    if isinstance(v, bool): return "TRUE" if v else "FALSE"
    if isinstance(v, list): return json.dumps(v, ensure_ascii=False)
    return str(v) if v is not None else ""

@st.cache_data(ttl=12)
def _gs_fetch(tab):
    """Henter alle rader fra et ark – cachet i 12 sek for å begrense API-kall."""
    ws = _gs_ws(tab)
    if ws is None: return None
    try: return ws.get_all_records()
    except: return None

def _gs_invalidate():
    """Tømmer bare data-cachen (ikke vær/NVE) etter skriveoperasjoner."""
    _gs_fetch.clear()

def gs_last_json(tab, fallback_fil, defaults):
    recs = _gs_fetch(tab)
    if recs is None: return last_json(fallback_fil, defaults)
    if not recs: return dict(defaults)
    row = _gs_deser(recs[0], tab)
    r = dict(defaults); r.update({k: v for k, v in row.items() if k in defaults})
    return r

def gs_lagre_json(tab, fallback_fil, data):
    ws = _gs_ws(tab)
    if ws is None: lagre_json(fallback_fil, data); return
    try:
        hdrs = list(data.keys())
        vals = [_gs_ser_val(v) for v in data.values()]
        # Én batch-oppdatering = 1 API-kall uansett størrelse
        ws.update([hdrs, vals], value_input_option="RAW")
        _gs_invalidate()
    except Exception as e:
        st.warning(f"GS lagringsfeil: {e}")
        lagre_json(fallback_fil, data)

def gs_last_liste(tab, fallback_fil):
    recs = _gs_fetch(tab)
    if recs is None: return last_liste(fallback_fil)
    return [_gs_deser(r, tab) for r in recs]

def gs_append(tab, fallback_fil, row_dict, headers):
    ws = _gs_ws(tab)
    if ws is None:
        lst = last_liste(fallback_fil); lst.append(row_dict); lagre_liste(fallback_fil, lst); return
    try:
        existing = ws.get_all_values()
        if not existing: ws.append_row(headers)
        ws.append_row([_gs_ser_val(row_dict.get(h, "")) for h in headers],
                      value_input_option="RAW")
        _gs_invalidate()
    except Exception as e:
        st.warning(f"GS lagringsfeil: {e}")
        lst = last_liste(fallback_fil); lst.append(row_dict); lagre_liste(fallback_fil, lst)

def gs_lagre_liste(tab, fallback_fil, data, headers):
    ws = _gs_ws(tab)
    if ws is None: lagre_liste(fallback_fil, data); return
    try:
        rows = [headers] + [[_gs_ser_val(row.get(h, "")) for h in headers] for row in data]
        # ws.update() = alltid 1 API-kall, uansett antall rader
        ws.clear()
        if rows: ws.update(rows, value_input_option="RAW")
        _gs_invalidate()
    except Exception as e:
        st.warning(f"GS lagringsfeil: {e}")
        lagre_liste(fallback_fil, data)

DEFAULTS = {"status":"🟢 Normal Beredskap","beskjed":"Klar til innsats i Melhus.",
            "leder":"Ikke satt","vakt":"9XX XX XXX","kort":"Daglig drift",
            "logg":"","ekom":"🟢 Normal drift","vei":"🟢 Veinett åpent"}
VP_DEFAULTS = {"sted":"","lagleder":"","mannskaper":"","utstyr":"","legevakt":"",
               "sykehus":"","talegruppe":"","tid_fra":"","tid_til":"","notat":"","aktiv":False,"skjul_forside":False}

# ── DATAFUNKSJONER ───────────────────────────────────────────────────────────

def lagre_json(fil, data):
    with open(fil,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)

def last_json(fil, defaults):
    if os.path.exists(fil):
        try:
            with open(fil,"r",encoding="utf-8") as f: data=json.load(f)
            r=dict(defaults); r.update({k:v for k,v in data.items() if k in defaults}); return r
        except: pass
    return dict(defaults)

def last_liste(fil):
    if os.path.exists(fil):
        try:
            with open(fil,"r",encoding="utf-8") as f: return json.load(f)
        except: pass
    return []

def lagre_liste(fil,data):
    with open(fil,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)

def generer_alarm_wav():
    sr = 22050
    sekvens = [(880,0,180),(880,220,180),(880,440,180),(660,700,500),(880,1300,180),(880,1520,180),(660,1780,600)]
    total = int(sr * 2.6)
    samples = [0] * total
    for freq, start_ms, dur_ms in sekvens:
        s = int(sr * start_ms / 1000)
        n = int(sr * dur_ms / 1000)
        for i in range(min(n, total - s)):
            t = i / sr
            env = min(1.0, i/(sr*0.01+1)) * min(1.0, (n-i-1)/(sr*0.03+1))
            val = int(32767 * 0.38 * env * math.sin(2 * math.pi * freq * t))
            samples[s+i] = max(-32767, min(32767, samples[s+i] + val))
    raw = struct.pack(f'<{total}h', *samples)
    buf = io.BytesIO()
    buf.write(b'RIFF'); buf.write(struct.pack('<I', 36+len(raw))); buf.write(b'WAVE')
    buf.write(b'fmt '); buf.write(struct.pack('<IHHIIHH', 16, 1, 1, sr, sr*2, 2, 16))
    buf.write(b'data'); buf.write(struct.pack('<I', len(raw))); buf.write(raw)
    buf.seek(0); return buf.getvalue()

def beregn_rig(tid):
    try: return (datetime.strptime(tid.strip(),"%H:%M")-timedelta(minutes=30)).strftime("%H:%M")
    except: return ""

# ── E-POST ───────────────────────────────────────────────────────────────────


# ── API ───────────────────────────────────────────────────────────────────────

def _sjekk_region(omrade,fylke,region_valg):
    if region_valg=="Hele Norge": return True
    termer=REGION_FILTER.get(region_valg,{}).get("termer",[])
    return any(t in f"{omrade} {fylke}".lower() for t in termer)

def _sjekk_koordinat(koordinater,region_valg):
    reg=REGION_FILTER.get(region_valg,{})
    if not all(k in reg for k in ("lat_min","lat_max","lon_min","lon_max")): return False
    try:
        lon,lat=koordinater[0][0][0][0],koordinater[0][0][0][1]
        return reg["lat_min"]<=lat<=reg["lat_max"] and reg["lon_min"]<=lon<=reg["lon_max"]
    except: return False

@st.cache_data(ttl=300)
def hent_nve_varsler(region_valg):
    varsler={}; region_ids=NVE_REGIONER.get(region_valg,[])
    if not region_ids: return varsler
    today=datetime.now().strftime('%Y-%m-%d'); feil=False
    for rid in region_ids:
        try:
            r=requests.get(f"https://api01.nve.no/hydrology/forecast/avalanche/v6.3.0/api/AvalancheWarningByRegion/Detail/{rid}/no/{today}/{today}",headers=STD_HEADERS,timeout=10)
            r.raise_for_status()
            for v in r.json():
                try: nivaa=int(v.get('DangerLevel',0))
                except: nivaa=0
                if nivaa<2: continue
                omrade=v.get('RegionName','')
                varsler[f"{omrade}_SNØSKRED"]={"Område":omrade,"Nivå":nivaa,"Type":"SNØSKRED","Kilde":"Varsom.no","Info":v.get('MainText','Se Varsom.no')}
        except requests.exceptions.HTTPError as e:
            if not feil: st.warning(f"⚠️ Varsom feil: {e}"); feil=True; break
        except Exception:
            if not feil: feil=True; break
    return varsler

@st.cache_data(ttl=300)
def hent_met_varsler(region_valg):
    varsler={}
    try:
        r=requests.get("https://api.met.no/weatherapi/metalerts/2.0/current.json",headers=STD_HEADERS,timeout=10)
        r.raise_for_status()
        for feat in r.json().get('features',[]):
            p=feat.get('properties',{})
            if p.get('geographicDomain')=='marine': continue
            farge=p.get('riskMatrixColor','').lower()
            if 'red' in farge: nivaa=4
            elif 'orange' in farge: nivaa=3
            elif 'yellow' in farge: nivaa=2
            else: continue
            omrade=p.get('area',''); fylke=p.get('county','')
            if not _sjekk_region(omrade,fylke,region_valg) and not _sjekk_koordinat(feat.get('geometry',{}).get('coordinates',[]),region_valg): continue
            event_type=p.get('event','')
            if event_type=="snowAvalanche": continue
            navn=omrade.split(",")[0]
            varsler[f"{navn}_{EVENT_MAP.get(event_type,event_type.upper())}"]={"Område":navn,"Nivå":nivaa,"Type":EVENT_MAP.get(event_type,event_type.upper()),"Kilde":"Yr/MET","Info":p.get('title','Aktivt farevarsel')}
    except Exception: pass
    return varsler

def send_avvik_kvittering(avvik, tiltak_notat):
    """
    Pilot: sender varsel til admin (andreas.narstad@gmail.com) med avsenders kontaktinfo.
    Når domene er verifisert i Resend sendes svaret direkte til avvikmelder.
    """
    try:
        api_key = st.secrets["resend"]["api_key"]
    except Exception:
        return False, "Resend API-nøkkel mangler i Streamlit Secrets."

    navn      = avvik.get("navn", "–")
    epost     = avvik.get("epost", "–") or "–"
    hendelse  = avvik.get("hendelse", "")
    registrert= avvik.get("registrert", "")
    admin_til = "andreas.narstad@gmail.com"

    tekst = (
        f"Avvik er nå lukket i NF Melhus beredskapssystem.\n\n"
        f"── AVSENDER ──────────────────────────\n"
        f"Navn   : {navn}\n"
        f"E-post : {epost}\n\n"
        f"── AVVIK ─────────────────────────────\n"
        f"Registrert : {registrert}\n"
        f"Hendelse   : {hendelse}\n\n"
        f"── TILTAK ────────────────────────────\n"
        f"{tiltak_notat or 'Ikke oppgitt'}\n\n"
        f"──────────────────────────────────────\n"
        f"Husk å sende svar direkte til {epost} om ønskelig.\n\n"
        f"NF Melhus – Beredskapssystem (pilot)"
    )
    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": "NF Beredskap <onboarding@resend.dev>",
                "to":   [admin_til],
                "subject": f"✅ Avvik lukket – {navn}",
                "text": tekst,
            },
            timeout=10
        )
        if r.status_code in (200, 201):
            return True, f"Varsel sendt til {admin_til}"
        return False, f"Feil fra Resend ({r.status_code}): {r.text}"
    except Exception as e:
        return False, f"Kunne ikke sende e-post: {e}"

@st.cache_data(ttl=300)
def hent_lokal_vaer():
    try:
        r=requests.get("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.28&lon=10.28",headers=STD_HEADERS,timeout=10)
        r.raise_for_status(); data=r.json()['properties']['timeseries']
        now=data[0]['data']['instant']['details']
        prog=[{"t":datetime.fromisoformat(data[i]['time'].replace('Z','+00:00')).strftime('%H:%M'),"temp":data[i]['data']['instant']['details']['air_temperature']} for i in range(1,5)]
        return now['air_temperature'],now['wind_speed'],prog
    except: return None,None,[]

# Kommuner i Melhus-regionen vi filtrerer på
POLITILOGG_TEMA = {
    "Alle":    "",
    "Redning": "redning",
    "Savnet":  "savnet",
    "Vær":     "vaer",
    "Annet":   "annet",
}
POLITILOGG_FARGER = {
    "Redning":"#dc3545","Savnet":"#fd7e14","Trafikk":"#ffc107",
    "Brann":"#ff4500","Vær":"#2196f3","Annet":"#6c757d",
    "Orden":"#9c27b0","Narkotika":"#795548","Vold":"#e91e63",
}

@st.cache_data(ttl=90)
def hent_politilogg(tema=""):
    url = "https://www.politiet.no/politiloggen?distrikt=trondelag"
    if tema: url += f"&tema={tema}"
    try:
        r = requests.get(url, headers=STD_HEADERS, timeout=15)
        r.raise_for_status()
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not m: return []
        nd = json.loads(m.group(1))
        pp = nd.get("props",{}).get("pageProps",{})
        for key in ["messageThreads","messages","incidents","data","items","logs","events"]:
            if key in pp and isinstance(pp[key], list):
                return pp[key][:30]
        # Recurse one level deeper
        for v in pp.values():
            if isinstance(v, dict):
                for key in ["messageThreads","messages","incidents","data","items"]:
                    if key in v and isinstance(v[key], list):
                        return v[key][:30]
        return []
    except: return []

_TENSIO_KOMMUNER = ["melhus","orkland","midtre gauldal","skaun","trondheim","malvik",
                    "klæbu","rissa","ørland","bjugn","agdenes","snillfjord","hitra","frøya"]

@st.cache_data(ttl=120)
def hent_tensio_brudd():
    """
    Henter pågående (lag 0=punkt) og planlagte (lag 2=punkt) strømbrudd
    fra Tensio Nord sitt offentlige ArcGIS FeatureServer.
    Returnerer (pagaende, planlagte) – lister av dicts.
    """
    BASE = "https://kart.tensio.no/enterprise/rest/services/Hosted"
    PARAMS = "where=1%3D1&outFields=*&returnGeometry=false&f=geojson"
    pagaende=[]; planlagte=[]
    try:
        # Pågående punkt – TN
        r=requests.get(f"{BASE}/StromstansTN/FeatureServer/0/query?{PARAMS}",
                       headers=STD_HEADERS,timeout=10)
        r.raise_for_status()
        for feat in r.json().get("features",[]):
            p=feat.get("properties",{})
            kom=(p.get("municipal_txt") or "").lower()
            if not any(k in kom for k in _TENSIO_KOMMUNER): continue
            start_ms=p.get("starttime")
            start_str=""
            if start_ms:
                try: start_str=datetime.fromtimestamp(int(start_ms)/1000).strftime("%d.%m %H:%M")
                except: pass
            pagaende.append({
                "kommune":   p.get("municipal_txt","–"),
                "antall":    p.get("num_ab",0) or 0,
                "start":     start_str,
                "arsak":     p.get("reason_txt","") or p.get("type_txt","") or "Ukjent",
                "info":      p.get("customer_web_text","") or "",
                "oppdatert": p.get("last_updated",""),
            })
        # Planlagte punkt – TN (lag 2)
        r2=requests.get(f"{BASE}/StromstansTN/FeatureServer/2/query?{PARAMS}",
                        headers=STD_HEADERS,timeout=10)
        r2.raise_for_status()
        for feat in r2.json().get("features",[]):
            p=feat.get("properties",{})
            kom=(p.get("municipal_txt") or "").lower()
            if not any(k in kom for k in _TENSIO_KOMMUNER): continue
            start_ms=p.get("starttime")
            start_str=""
            if start_ms:
                try: start_str=datetime.fromtimestamp(int(start_ms)/1000).strftime("%d.%m %H:%M")
                except: pass
            planlagte.append({
                "kommune":   p.get("municipal_txt","–"),
                "antall":    p.get("num_ab",0) or 0,
                "start":     start_str,
                "arsak":     p.get("reason_txt","") or p.get("type_txt","") or "Planlagt",
                "info":      p.get("customer_web_text","") or "",
            })
    except Exception as e:
        pass
    return pagaende, planlagte

# ── HTML-EKSPORT ─────────────────────────────────────────────────────────────

def generer_beredskapsplan(vp,d):
    ml="".join(f"<li>{n.strip()}</li>" for n in vp["mannskaper"].splitlines() if n.strip()) or "<li><em>Ikke oppgitt</em></li>"
    ul="".join(f"<li>{u.strip()}</li>" for u in vp["utstyr"].splitlines() if u.strip()) or "<li><em>Ikke oppgitt</em></li>"
    rig=beregn_rig(vp["tid_fra"]); dato=datetime.now().strftime("%d.%m.%Y %H:%M")
    return f"""<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8"><title>Beredskapsplan</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Arial,sans-serif;color:#222;background:#fff;padding:30px}}
.hdr{{background:#cc0000;color:white;padding:22px 28px;border-radius:10px;margin-bottom:22px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.card{{background:#f7f7f7;border:1px solid #ddd;border-radius:8px;padding:16px}}
.card h3{{font-size:0.8rem;text-transform:uppercase;color:#888;margin-bottom:8px}}
.card .v{{font-weight:bold;color:#111}}.card ul{{margin-left:18px;line-height:1.8}}
.rig{{background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:14px;margin-bottom:16px;font-weight:bold}}
.nood{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
.nood .card{{border-left:4px solid #cc0000}}
.ftr{{color:#aaa;font-size:0.8rem;text-align:center;margin-top:24px;border-top:1px solid #eee;padding-top:12px}}
@media print{{body{{padding:15px}}}}</style></head><body>
<div class="hdr"><h1>🚑 Norsk Folkehjelp – Beredskapsplan</h1><p>Melhus | {dato} | {d['status']}</p></div>
{f'<div class="rig">⏰ Ferdig rigget: {rig} (30 min før)</div>' if rig else ''}
<div class="grid">
<div class="card"><h3>📍 Sted</h3><div class="v">{vp['sted'] or '–'}</div></div>
<div class="card"><h3>🕐 Tid</h3><div class="v">{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div></div>
<div class="card"><h3>👷 Lagleder</h3><div class="v">{vp['lagleder'] or '–'}</div></div>
<div class="card"><h3>📻 Talegruppe</h3><div class="v">{vp['talegruppe'] or '–'}</div></div>
<div class="card"><h3>👥 Mannskaper</h3><ul>{ml}</ul></div>
<div class="card"><h3>🎒 Utstyr</h3><ul>{ul}</ul></div></div>
<div class="nood">
<div class="card"><h3>🏥 Legevakt</h3><div class="v">{vp['legevakt'] or '–'}</div></div>
<div class="card"><h3>🏨 Sykehus</h3><div class="v">{vp['sykehus'] or '–'}</div></div></div>
{f'<div class="card" style="margin-bottom:16px"><h3>📝 Merknader</h3><div>{vp["notat"]}</div></div>' if vp["notat"] else ''}
<div class="ftr">NF Melhus | Vaktleder: {d['leder']} | {d['vakt']}</div>
</body></html>"""

def generer_tilbud(kunde,arr,dato_str,linjer,total,forbruk):
    rader="".join(f"<tr><td>{n}</td><td style='color:#666;font-size:0.85rem'>{b}</td><td style='text-align:right;font-weight:bold'>{v:,.0f} kr</td></tr>".replace(","," ") for n,b,v in linjer if v>0)
    if forbruk: rader+=f"<tr><td>Forbruksmateriell</td><td style='color:#666;font-size:0.85rem'>Manuelt</td><td style='text-align:right;font-weight:bold'>{forbruk:,.0f} kr</td></tr>".replace(","," ")
    dato_gen=datetime.now().strftime("%d.%m.%Y")
    return f"""<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8"><title>Tilbud</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Arial,sans-serif;color:#222;padding:40px;max-width:750px;margin:0 auto}}
.hdr{{background:#cc0000;color:white;padding:28px 32px;border-radius:10px;margin-bottom:28px}}
.meta{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:24px}}
.meta div{{background:#f5f5f5;border-radius:8px;padding:14px 18px}}
.meta .lbl{{font-size:0.75rem;text-transform:uppercase;color:#888;margin-bottom:4px}}
.meta .v{{font-weight:bold}}
table{{width:100%;border-collapse:collapse;margin-bottom:20px}}
th{{background:#222;color:white;padding:10px 14px;text-align:left;font-size:0.85rem}}
th:last-child{{text-align:right}}td{{padding:10px 14px;border-bottom:1px solid #eee}}
.tot td{{border-top:3px solid #cc0000;font-weight:bold;background:#fff8f8}}
.tot td:last-child{{color:#cc0000;font-size:1.3rem;text-align:right}}
.ftr{{color:#aaa;font-size:0.8rem;text-align:center;margin-top:28px;border-top:1px solid #eee;padding-top:14px}}
@media print{{body{{padding:20px}}}}</style></head><body>
<div class="hdr"><h1>🚑 Tilbud – Sanitetsvakt</h1><p>Norsk Folkehjelp Melhus · {dato_gen}</p></div>
<div class="meta">
<div><div class="lbl">Kunde / Arrangør</div><div class="v">{kunde or '–'}</div></div>
<div><div class="lbl">Arrangement</div><div class="v">{arr or '–'}</div></div>
<div><div class="lbl">Dato</div><div class="v">{dato_str or '–'}</div></div></div>
<table><thead><tr><th>Beskrivelse</th><th>Beregning</th><th style='text-align:right'>Beløp</th></tr></thead>
<tbody>{rader}<tr class="tot"><td colspan="2">TOTALT</td><td>{total:,.0f} kr</td></tr></tbody></table>
<div class="ftr">Norsk Folkehjelp – Melhus | Generert {dato_gen}<br>Priser er veiledende og ekskl. mva.</div>
</body></html>""".replace(","," ")

# ── CSS ───────────────────────────────────────────────────────────────────────

NATT_CSS = """
<style>
/* ═══ TAKTISK NATTMODUS – RØDLYS ═══ */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] > div { background-color:#060000 !important; }

[data-testid="stSidebar"],
[data-testid="stSidebar"] > div      { background-color:#030000 !important; }

/* All tekst */
p,span,div,h1,h2,h3,h4,h5,label,small,li,td,th,
.stMarkdown,.stText,
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"],
[data-testid="stMetricDelta"],
[data-testid="stCaptionContainer"]   { color:#cc1a00 !important; }

/* Inputs */
input,textarea,select,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea  {
    background:#0d0000 !important;
    color:#cc1a00 !important;
    border-color:#440000 !important; }

/* Buttons */
.stButton > button, button {
    background:#150000 !important;
    color:#cc1a00 !important;
    border:1px solid #440000 !important; }
.stButton > button:hover { background:#2a0000 !important; }

/* Selectbox / multiselect */
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div  {
    background:#0d0000 !important;
    border-color:#440000 !important; }

/* Expander */
[data-testid="stExpander"]           { border-color:#440000 !important; background:#0a0000 !important; }

/* Tabs */
[data-testid="stTabs"] button        { color:#993300 !important; }
[data-testid="stTabs"] button[aria-selected="true"] { color:#ff3300 !important; border-bottom-color:#ff3300 !important; }

/* Dataframe */
[data-testid="stDataFrame"] iframe   { filter:brightness(0.25) sepia(1) saturate(4) hue-rotate(320deg) !important; }

/* Kart og iframes */
iframe                               { filter:brightness(0.2) sepia(1) saturate(3) hue-rotate(300deg) !important; }

/* Bilder */
img                                  { filter:brightness(0.3) sepia(1) saturate(4) hue-rotate(310deg) !important; }

/* Separatorlinjer */
hr                                   { border-color:#330000 !important; }

/* Metrikkbokser */
[data-testid="metric-container"]     { background:#0a0000 !important; border:1px solid #330000 !important; border-radius:8px; padding:8px; }

/* Skjul Streamlit-header i nattmodus */
[data-testid="stHeader"]             { background:#030000 !important; }

/* Scrollbar */
::-webkit-scrollbar                  { background:#030000; }
::-webkit-scrollbar-thumb            { background:#440000; border-radius:4px; }
</style>
"""

CSS = """
<style>
/* Skjul Streamlits automatiske sidenavigasjon */
[data-testid="stSidebarNav"] {display: none !important;}
[data-testid="stSidebarNavItems"] {display: none !important;}
[data-testid="stSidebarNavSeparator"] {display: none !important;}

.nf-card      {background:rgba(128,128,128,0.07);border:1px solid rgba(128,128,128,0.2);border-radius:12px;padding:15px;}
.nf-card-blue {background:rgba(46,89,132,0.08);border:2px solid #2e5984;border-radius:12px;padding:15px;min-height:160px;}
.nf-danger    {background:rgba(220,53,69,0.10);border:1px solid #dc3545;border-radius:10px;padding:14px;margin-top:10px;}
.nf-info      {background:rgba(33,150,243,0.10);border:1px solid #2196f3;border-radius:10px;padding:14px;margin-top:10px;}
.nf-rig       {background:rgba(255,193,7,0.18);border:1px solid #ffc107;border-radius:8px;padding:10px 14px;margin-bottom:10px;}
.nf-ok-box    {border:2px solid #28a745;border-radius:12px;padding:60px 20px;text-align:center;height:430px;
               display:flex;flex-direction:column;justify-content:center;background:rgba(40,167,69,0.06);}
.nf-infra     {border-radius:12px;padding:15px;min-height:160px;}
.nf-infra-ok  {border:2px solid #28a745;background:rgba(40,167,69,0.07);}
.nf-infra-warn{border:2px solid #ffc107;background:rgba(255,193,7,0.09);}
.nf-infra-err {border:2px solid #dc3545;background:rgba(220,53,69,0.07);}
.nf-lbl       {font-size:0.75rem;text-transform:uppercase;letter-spacing:0.05em;opacity:0.6;margin-bottom:4px;}
.nf-val       {font-size:1.05rem;font-weight:bold;}
.nf-div       {border-bottom:1px solid rgba(128,128,128,0.2);padding:3px 0;}
.nf-step      {background:rgba(128,128,128,0.05);border:1px solid rgba(128,128,128,0.15);border-radius:10px;padding:18px 20px;margin-bottom:14px;}
.nf-step-ttl  {font-size:0.8rem;text-transform:uppercase;letter-spacing:0.06em;opacity:0.55;margin-bottom:12px;font-weight:bold;}
.nf-sub       {text-align:right;font-size:0.85rem;opacity:0.7;margin-top:8px;}
audio         {position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;}
</style>
"""

# ═══════════════════════════════════════════════════════════════════════════════
# APP START
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="NF Operativ Tavle – Melhus", layout="wide", page_icon="🚑")
if "natt_modus" not in st.session_state:
    st.session_state["natt_modus"] = False
st.markdown(CSS, unsafe_allow_html=True)
if st.session_state["natt_modus"]:
    st.markdown(NATT_CSS, unsafe_allow_html=True)

d            = gs_last_json("beredskap",    FIL,              DEFAULTS)
vp           = gs_last_json("vaktplan",     VAKTPLAN_FIL,     VP_DEFAULTS)
avvik_liste  = gs_last_liste("avvik",   AVVIK_FIL)
del_liste    = gs_last_liste("deltakelse", DELTAKELSE_FIL)
skade_liste  = gs_last_liste("skade",   SKADE_FIL)
logg_liste   = gs_last_liste("logg",    LOGG_FIL)
akutte       = [a for a in avvik_liste if a.get("umiddelbar_oppfolging") and not a.get("fulgt_opp")]

# ── SIDEMENY ──────────────────────────────────────────────────────────────────
with st.sidebar:
    if os.path.exists("nf_logo.png"):
        st.markdown("<div style='text-align:center;padding:10px 16px 4px;'>", unsafe_allow_html=True)
        st.image("nf_logo.png", width=180)
        st.markdown("</div>", unsafe_allow_html=True)

    bg = STATUS_FARGER.get(d['status'], "#333")
    st.markdown(f"<div style='background:{bg};color:white;padding:10px 14px;border-radius:8px;"
                f"font-weight:bold;margin-bottom:10px;'>{d['status']}</div>", unsafe_allow_html=True)

    if akutte:
        st.error(f"⚡ {len(akutte)} avvik krever umiddelbar oppfølging!")

    st.markdown("---")
    side = st.radio("Navigasjon", [
        "🏠 Operativ tavle",
        "👤 Registrer deltakelse",
        "⚠️ Registrer avvik",
        "🩹 Skaderegistrering",
        "📝 Loggføring",
        "📋 Vaktinstruks",
        "💰 Kalkyle – Sanitetsvakt",
        "⚙️ Administrasjon",
    ], label_visibility="collapsed")

    st.markdown("---")
    m1, m2 = st.columns(2)
    m1.metric("Deltakelser", len(del_liste))
    m2.metric("Avvik", len(avvik_liste),
              delta=f"{len(akutte)} akutte" if akutte else None,
              delta_color="inverse")
    st.metric("Skader", len(skade_liste))

    st.markdown("---")
    natt_label = "🔴 Nattmodus PÅ" if st.session_state["natt_modus"] else "🌙 Taktisk nattmodus"
    natt_hjelp  = "Rødlys – bevarer nattsynet i felt. Klikk for å slå av." if st.session_state["natt_modus"] else "Slår på rødlys-modus for bruk i mørket. Bevarer nattsynet."
    if st.button(natt_label, use_container_width=True, help=natt_hjelp):
        st.session_state["natt_modus"] = not st.session_state["natt_modus"]
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: OPERATIV TAVLE
# ═══════════════════════════════════════════════════════════════════════════════
if side == "🏠 Operativ tavle":

    st.markdown("<h2 style='text-align:center;color:#cc0000;'>🚑 Norsk Folkehjelp Melhus</h2>", unsafe_allow_html=True)

    # Status-banner
    st.markdown(f"""<div style="background:{bg};padding:20px;border-radius:15px;
    text-align:center;color:white;border:2px solid rgba(0,0,0,0.2);">
    <h1 style="margin:0;font-size:3.5rem;">{d['status']}</h1>
    <p style="font-size:1.5rem;margin-top:5px;font-weight:500;">{d['beskjed']}</p>
    </div>""", unsafe_allow_html=True)
    st.write("")

    # Alarmtone rød beredskap
    if d['status'] == "🔴 Rød / Høy beredskap":
        if not st.session_state.get("alarm_spilt"):
            st.session_state["alarm_spilt"] = True
            st.audio(generer_alarm_wav(), format="audio/wav", autoplay=True)
    else:
        st.session_state["alarm_spilt"] = False

    if akutte:
        st.markdown(f"""<div style='background:linear-gradient(135deg,#e65c00,#c0392b);
        padding:15px 20px;border-radius:10px;color:white;border-left:6px solid #ff0000;margin-bottom:10px;'>
        <b style='font-size:1.1rem;'>⚡ {len(akutte)} avvik krever umiddelbar oppfølging</b>
        &nbsp;–&nbsp; åpne administrasjonspanelet nedenfor.</div>""", unsafe_allow_html=True)

    # Info-panel
    c1, c2, c3 = st.columns([1.2,1,1.2])
    with c1:
        t,v,prog = hent_lokal_vaer()
        if t is not None:
            ps=' | '.join([f"{i['t']}: {i['temp']}°" for i in prog])
            st.markdown(f"<div class='nf-card'><b>📍 Melhus Sentrum:</b><br>"
                        f"<h2 style='margin:5px 0;color:#1f77b4;'>{t}°C &nbsp;|&nbsp; {v} m/s</h2>"
                        f"<small style='opacity:0.7;'>{ps}</small></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='nf-card'><b>📍 Melhus Sentrum:</b><br><br><small>⚠️ Værvarselet utilgjengelig.</small></div>", unsafe_allow_html=True)
    with c2:
        ks = ("background:rgba(128,128,128,0.15);color:inherit;border:1px solid rgba(128,128,128,0.3);font-size:0.85rem;opacity:0.7;"
              if d['kort'] in ('Ingen','Daglig drift') else
              "background:#cc0000;color:white;border:2px solid #990000;box-shadow:0 2px 8px rgba(200,0,0,0.4);font-size:1rem;")
        st.markdown(f"<div class='nf-card-blue'><b>📞 Operativ Ledelse:</b><br>"
                    f"<span style='font-size:1.1rem;'>Leder: <b>{d['leder']}</b></span><br>"
                    f"<span style='font-size:1.1rem;'>Vakt-tlf: <b>{d['vakt']}</b></span>"
                    f"<br><br><div style='display:inline-block;{ks}padding:4px 12px;border-radius:6px;font-weight:bold;'>"
                    f"📋 {d['kort']}</div></div>", unsafe_allow_html=True)
    with c3:
        pagaende_brudd, planlagte_brudd = hent_tensio_brudd()
        tot_berort = sum(b["antall"] for b in pagaende_brudd)
        har_strom_feil = bool(pagaende_brudd)
        har_strom_plan = bool(planlagte_brudd) and not pagaende_brudd

        ic = ("nf-infra-err" if "🔴" in d['ekom'] or "🔴" in d['vei'] or har_strom_feil
              else "nf-infra-warn" if "🟡" in d['ekom'] or "🟡" in d['vei'] or har_strom_plan
              else "nf-infra-ok")

        if pagaende_brudd:
            brudd_linjer = ""
            for b in pagaende_brudd[:3]:
                arsak_str = f" ({b['arsak']})" if b.get('arsak') else ""
                start_str = f" – {b['start']}" if b.get('start') else ""
                brudd_linjer += f"<br><span style='font-size:0.82rem;opacity:0.85;'>• {b['kommune']}{arsak_str}{start_str}</span>"
            ekstra = f"<br><span style='font-size:0.8rem;opacity:0.5;'>+{len(pagaende_brudd)-3} til</span>" if len(pagaende_brudd) > 3 else ""
            strom_html = f"<span style='color:#dc3545;font-weight:bold;'>⚡ {len(pagaende_brudd)} brudd – {tot_berort} kunder berørt</span>{brudd_linjer}{ekstra}"
        elif planlagte_brudd:
            plan_linjer = ""
            for b in planlagte_brudd[:2]:
                start_str = f" – {b['start']}" if b.get('start') else ""
                plan_linjer += f"<br><span style='font-size:0.82rem;opacity:0.85;'>• {b['kommune']}{start_str}</span>"
            strom_html = f"<span style='color:#b8860b;font-weight:bold;'>🔧 {len(planlagte_brudd)} planlagt</span>{plan_linjer}"
        else:
            strom_html = "<span style='color:#28a745;font-size:0.88rem;'>✅ Ingen strømbrudd</span>"

        st.markdown(
            f"<div class='nf-infra {ic}'><b>📡 Kritisk Infrastruktur:</b><br><br>"
            f"<b>EKOM:</b><br><span style='opacity:0.9;font-size:0.9rem;'>{d['ekom']}</span><br><br>"
            f"<b>VEI / ISOLASJON:</b><br><span style='opacity:0.9;font-size:0.9rem;'>{d['vei']}</span><br><br>"
            f"<b>STRØM (Tensio):</b><br>{strom_html}"
            f"<br><span style='font-size:0.72rem;opacity:0.4;'>↻ 2 min</span></div>",
            unsafe_allow_html=True)

    # Politilogg-boks på operativ tavle
    st.write("")
    pl_siste = hent_politilogg("")
    if pl_siste:
        pl_linjer = ""
        for h in pl_siste[:5]:
            kat  = str(h.get("category") or h.get("tema") or h.get("type") or h.get("kategori") or "Annet").strip().capitalize()
            kom  = h.get("municipality") or h.get("kommune") or h.get("location") or h.get("sted") or "–"
            tid_r = h.get("createdOn") or h.get("time") or h.get("timestamp") or h.get("dato") or ""
            try:
                tid_str = datetime.fromisoformat(str(tid_r).replace("Z","+00:00")).strftime("%d.%m %H:%M") if tid_r else "–"
            except: tid_str = str(tid_r)[:11]
            tekst = h.get("text") or h.get("description") or h.get("desc") or h.get("melding") or h.get("title") or ""
            tekst_kort = (tekst[:80] + "…") if len(tekst) > 80 else tekst
            farge = POLITILOGG_FARGER.get(kat, "#6c757d")
            pl_linjer += (
                f"<span style='display:inline-block;background:{farge};color:white;"
                f"font-size:0.68rem;border-radius:3px;padding:1px 5px;margin-right:4px;'>{kat}</span>"
                f"<span style='font-size:0.82rem;'><b>{kom}</b> &nbsp;"
                f"<span style='opacity:0.55;'>{tid_str}</span>"
                f"{(' – ' + tekst_kort) if tekst_kort else ''}</span><br>"
            )
        st.markdown(
            f"<div class='nf-card' style='padding:12px 16px;'>"
            f"<b style='font-size:0.85rem;'>👮 Politilogg – Trøndelag</b>"
            f"<span style='float:right;font-size:0.72rem;opacity:0.45;'>↻ 90 sek</span><br><br>"
            f"{pl_linjer}"
            f"</div>",
            unsafe_allow_html=True)
    else:
        st.markdown(
            "<div class='nf-card' style='padding:12px 16px;'>"
            "<b style='font-size:0.85rem;'>👮 Politilogg – Trøndelag</b><br><br>"
            "<span style='opacity:0.5;font-size:0.85rem;'>Ingen data tilgjengelig – "
            "<a href='https://www.politiet.no/politiloggen?distrikt=trondelag' target='_blank'>åpne politiet.no</a></span>"
            "</div>",
            unsafe_allow_html=True)

    # Kart og varsler
    st.write("---")
    ct, cf = st.columns([3,1])
    with ct: st.subheader("🚨 Operativ Oversikt & Farevarsler")
    with cf: valgt_region = st.selectbox("🌍 Velg område:", list(KART_KOORDINATER.keys()), index=0)
    cm, ca = st.columns([1.5,1])
    with cm:
        components.iframe(f"https://embed.windy.com/embed2.html?{KART_KOORDINATER[valgt_region]}&overlay=wind&metricWind=m%2Fs", height=450)
    with ca:
        varsler = {**hent_nve_varsler(valgt_region), **hent_met_varsler(valgt_region)}
        varsler = list(varsler.values())
        if varsler:
            df=pd.DataFrame(varsler).sort_values(by=["Nivå","Område"],ascending=[False,True])
            def srow(row):
                c={2:("#FFFF00","black"),3:("#FF9900","white"),4:("#FF0000","white")}.get(row.Nivå,("white","black"))
                return [f'background-color:{c[0]};color:{c[1]};font-weight:bold']*len(row)
            st.dataframe(df.style.apply(srow,axis=1),use_container_width=True,height=450,hide_index=True)
        else:
            st.markdown(f"""<div class='nf-ok-box'><div style='font-size:3rem;'>✅</div>
            <div style='font-size:1.2rem;font-weight:bold;color:#28a745;margin-top:10px;'>Ingen aktive farevarsler</div>
            <div style='opacity:0.6;margin-top:6px;'>for {valgt_region.split()[0]}</div></div>""", unsafe_allow_html=True)

    # Operativ logg
    if d['logg']:
        st.write("---"); st.subheader("📝 Operativ Logg")
        st.text_area("", value=d['logg'], height=120, disabled=True, label_visibility="collapsed")

    # Vaktinstruks i dashboard
    if vp.get("aktiv") and not vp.get("skjul_forside") and (vp.get("sted") or vp.get("lagleder")):
        st.write("---"); st.subheader("📋 Instruks for aktivitet/vakt")
        rig = beregn_rig(vp["tid_fra"])
        vi1,vi2,vi3 = st.columns(3)
        with vi1:
            rh=f"<div class='nf-rig' style='margin-top:8px;'>⏰ Ferdig rigget: <b>{rig}</b></div>" if rig else ""
            st.markdown(f"<div class='nf-card' style='min-height:unset;'>"
                        f"<div class='nf-lbl'>📍 Sted</div><div class='nf-val' style='font-size:1.15rem;'>{vp['sted'] or '–'}</div>"
                        f"<div class='nf-lbl' style='margin-top:10px;'>🕐 Tid</div><div class='nf-val'>{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div>{rh}</div>", unsafe_allow_html=True)
        with vi2:
            mv="".join(f"<div class='nf-div'>• {m.strip()}</div>" for m in vp["mannskaper"].splitlines() if m.strip()) or "<em style='opacity:0.4;'>Ikke oppgitt</em>"
            st.markdown(f"<div class='nf-card' style='min-height:unset;'>"
                        f"<div class='nf-lbl'>👷 Lagleder</div><div class='nf-val' style='margin-bottom:10px;'>{vp['lagleder'] or '–'}</div>"
                        f"<div class='nf-lbl'>👥 Mannskaper</div><div style='font-size:0.9rem;line-height:1.8;'>{mv}</div></div>", unsafe_allow_html=True)
        with vi3:
            uv="".join(f"<div class='nf-div'>• {u.strip()}</div>" for u in vp["utstyr"].splitlines() if u.strip()) or "<em style='opacity:0.4;'>Ikke oppgitt</em>"
            st.markdown(f"<div class='nf-card' style='min-height:unset;'>"
                        f"<div class='nf-lbl'>🎒 Utstyr</div><div style='font-size:0.9rem;line-height:1.8;'>{uv}</div></div>", unsafe_allow_html=True)
        vi4,vi5,vi6 = st.columns(3)
        with vi4: st.markdown(f"<div class='nf-danger'><div class='nf-lbl'>🏥 Legevakt</div><div class='nf-val'>{vp['legevakt'] or '–'}</div></div>", unsafe_allow_html=True)
        with vi5: st.markdown(f"<div class='nf-danger'><div class='nf-lbl'>🏨 Sykehus</div><div class='nf-val'>{vp['sykehus'] or '–'}</div></div>", unsafe_allow_html=True)
        with vi6: st.markdown(f"<div class='nf-info'><div class='nf-lbl'>📻 Talegruppe</div><div class='nf-val'>{vp['talegruppe'] or '–'}</div></div>", unsafe_allow_html=True)
        if vp.get("notat"): st.info(f"📝 {vp['notat']}")
        st.download_button("📥 Eksporter beredskapsplan", data=generer_beredskapsplan(vp,d).encode("utf-8"),
                           file_name=f"beredskapsplan_{datetime.now().strftime('%Y%m%d_%H%M')}.html", mime="text/html")

    st.markdown(f"<div style='text-align:right;color:#aaa;'><small>Sist lastet: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</small></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: REGISTRER DELTAKELSE
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "👤 Registrer deltakelse":
    st.markdown("<h2>👤 Registrer deltakelse</h2>", unsafe_allow_html=True)
    st.caption("Fyll ut skjemaet etter endt oppdrag eller vakt.")

    with st.form("deltakelse_form", clear_on_submit=True):
        k1,k2 = st.columns(2)
        with k1:
            navn    = st.text_input("Navn *")
            oppdrag = st.selectbox("Type oppdrag *", ["SAR","Sanitetsvakt","Annen hendelse","Kurs/øvelse"])
            utlegg  = st.number_input("Private utlegg (kr)", min_value=0, step=50, value=0)
        with k2:
            t1,t2=st.columns(2)
            with t1: tid_ut=st.text_input("Tid ut",placeholder="08:00")
            with t2: tid_inn=st.text_input("Tid inn",placeholder="16:00")
            opplastet=st.file_uploader("Kvittering / vedlegg",type=["jpg","jpeg","png","pdf"],accept_multiple_files=True)
        st.markdown("---")
        privatbil = st.checkbox("🚗 Brukte privatbil")
        b1,b2 = st.columns(2)
        with b1: km_kjort = st.number_input("Kjørte km", min_value=0, step=1, value=0, disabled=not privatbil)
        with b2: regnr    = st.text_input("Reg.nummer", placeholder="AB 12345", disabled=not privatbil)
        if st.form_submit_button("💾 Registrer deltakelse", use_container_width=True, type="primary"):
            if not navn.strip(): st.error("Navn er påkrevd.")
            else:
                os.makedirs(VEDLEGG_MAPPE, exist_ok=True)
                vn=[]
                for f in (opplastet or []):
                    fn=f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{f.name}"
                    with open(os.path.join(VEDLEGG_MAPPE,fn),"wb") as fp: fp.write(f.read())
                    vn.append(fn)
                gs_append("deltakelse",DELTAKELSE_FIL,
                          {"registrert":datetime.now().strftime('%d.%m.%Y %H:%M'),"navn":navn.strip(),
                           "oppdrag":oppdrag,"tid_ut":tid_ut.strip(),"tid_inn":tid_inn.strip(),
                           "utlegg_kr":utlegg,
                           "privatbil":"Ja" if privatbil else "Nei",
                           "km_kjort":km_kjort if privatbil else 0,
                           "regnr":regnr.strip().upper() if privatbil else "",
                           "vedlegg":vn},DELTAKELSE_HDR)
                st.success(f"✅ Deltakelse registrert for **{navn.strip()}**")

    st.write("---"); st.subheader("📋 Registreringer i dag")
    today=datetime.now().strftime('%d.%m.%Y')
    dagens=[r for r in gs_last_liste("deltakelse", DELTAKELSE_FIL) if r.get("registrert","").startswith(today)]
    if dagens:
        _kol_navn={"registrert":"Tidspunkt","navn":"Navn","oppdrag":"Oppdrag","tid_ut":"Tid ut",
                   "tid_inn":"Tid inn","utlegg_kr":"Utlegg (kr)","privatbil":"Privatbil",
                   "km_kjort":"Km","regnr":"Reg.nr"}
        dfd=pd.DataFrame(dagens)
        vis_kol=[c for c in _kol_navn if c in dfd.columns]
        dfd=dfd[vis_kol].rename(columns=_kol_navn)
        st.dataframe(dfd, use_container_width=True, hide_index=True)
    else:
        st.caption("Ingen registreringer i dag ennå.")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: REGISTRER AVVIK
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "⚠️ Registrer avvik":
    st.markdown("<h2>⚠️ Registrer avvik</h2>", unsafe_allow_html=True)
    st.caption("Avvik sendes automatisk på e-post til ansvarlig og lagres for oppfølging.")

    with st.form("avvik_form", clear_on_submit=True):
        ak1,ak2=st.columns(2)
        with ak1: av_navn=st.text_input("Ditt navn *")
        with ak2: av_epost=st.text_input("Din e-post",placeholder="din@epost.no")
        av_hendelse  =st.text_area("Hva skjedde? *",placeholder="Beskriv hendelsen – hva, hvor, når...",height=130)
        av_konsekvens=st.text_area("Hva ble konsekvensen?",placeholder="Skade, forsinkelse, nesten-ulykke...",height=100)
        st.markdown("---")
        av_umiddelbar=st.checkbox("⚡ Hendelsen krever umiddelbar oppfølging",
                                   help="Kryss av om dette ikke kan vente til neste arbeidsdag.")
        if st.form_submit_button("📨 Send avvik", use_container_width=True, type="primary"):
            if not av_navn.strip() or not av_hendelse.strip():
                st.error("Navn og hendelse er påkrevd.")
            else:
                nytt={"id":datetime.now().strftime('%Y%m%d%H%M%S'),
                      "registrert":datetime.now().strftime('%d.%m.%Y %H:%M'),
                      "navn":av_navn.strip(),"epost":av_epost.strip(),
                      "hendelse":av_hendelse.strip(),"konsekvens":av_konsekvens.strip(),
                      "umiddelbar_oppfolging":av_umiddelbar,"fulgt_opp":False,"oppfolging_notat":""}
                gs_append("avvik",AVVIK_FIL,nytt,AVVIK_HDR)
                if av_umiddelbar: st.warning("⚡ Avvik registrert – merket som akutt!")
                else: st.success("✅ Avvik registrert. Takk for tilbakemeldingen.")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: SKADEREGISTRERING
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "🩹 Skaderegistrering":
    st.markdown("<h2>🩹 Skaderegistrering</h2>", unsafe_allow_html=True)
    st.caption("Registrer pasienter behandlet under oppdrag eller sanitetsvakt.")

    with st.form("skade_form", clear_on_submit=True):
        sf1, sf2 = st.columns(2)
        with sf1:
            sk_innsats = st.text_input("Oppdrag / arrangement", placeholder="Sommerstevne 2026")
            sk_behandler = st.text_input("Behandlerens navn *")
            sk_kjonn = st.selectbox("Kjønn", ["Ikke oppgitt","Mann","Kvinne","Annet"])
            sk_alder = st.selectbox("Aldersgruppe", ["Ikke oppgitt","0–12 år","13–17 år","18–30 år","31–50 år","51–65 år","66+ år"])
            sk_konsultert = st.selectbox("Konsultert / viderehenvist til",
                ["Ingen","AMK / 113","Legevakt","Lege på stedet","Sykehus","Annet"])
        with sf2:
            sk_skadetype = st.multiselect("Skadetype / symptom",
                ["Sårskade","Brudd / mistanke om brudd","Forstuing / strekk","Hodeskade",
                 "Bevisstløshet / synkope","Brystsmerter","Pustebesvær","Allergi / anafylaksi",
                 "Diabetisk episode","Kramper","Varme- / kuldesykdom","Psykisk krise","Annet"])
            sk_behandling = st.text_area("Behandling gitt", placeholder="Sårskylling, bandasje, RICE...", height=100)
            sk_rad = st.text_area("Videre råd gitt til pasient", placeholder="Oppsøk lege, hvil, is på...", height=80)
            sk_utstyr = st.multiselect("Utstyr benyttet",
                ["Forbindingspakke","Brannskadepakke","Tourniquet","Svelgtube / NPA",
                 "Oksygen","AED / Hjertestarter","BVM / Bag-maske","Nødpute / båre",
                 "Halskrage","Splint","Blodtrykksapparat","Pulsoksymeter","Blodsukkerapparat","Annet"])
        sk_merknad = st.text_area("Merknader", height=60)
        if st.form_submit_button("💾 Registrer skade", use_container_width=True, type="primary"):
            if not sk_behandler.strip():
                st.error("Behandlerens navn er påkrevd.")
            else:
                ny = {"registrert": datetime.now().strftime('%d.%m.%Y %H:%M'),
                      "innsats": sk_innsats.strip(), "behandler": sk_behandler.strip(),
                      "kjonn": sk_kjonn, "alder": sk_alder,
                      "skadetype": sk_skadetype, "behandling": sk_behandling.strip(),
                      "rad": sk_rad.strip(), "konsultert": sk_konsultert,
                      "utstyr": sk_utstyr, "merknad": sk_merknad.strip()}
                gs_append("skade",SKADE_FIL,ny,SKADE_HDR)
                st.success(f"✅ Skade registrert av **{sk_behandler.strip()}**")

    st.write("---")
    fresh_skade = gs_last_liste("skade", SKADE_FIL)
    if fresh_skade:
        st.subheader(f"📋 Registrerte skader ({len(fresh_skade)} totalt)")
        for i, s in enumerate(reversed(fresh_skade)):
            with st.expander(f"🩹 {s.get('registrert','')}  –  {', '.join(s['skadetype']) if s.get('skadetype') else 'Ukjent skadetype'}  |  {s.get('kjonn','')} {s.get('alder','')}"):
                c1,c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Behandler:** {s.get('behandler','–')}")
                    st.markdown(f"**Oppdrag:** {s.get('innsats') or '–'}")
                    st.markdown(f"**Konsultert:** {s.get('konsultert','–')}")
                    if s.get('utstyr'): st.markdown(f"**Utstyr:** {', '.join(s['utstyr'])}")
                with c2:
                    if s.get('behandling'): st.markdown(f"**Behandling:** {s['behandling']}")
                    if s.get('rad'):        st.markdown(f"**Råd gitt:** {s['rad']}")
                    if s.get('merknad'):    st.info(f"📝 {s['merknad']}")
    else:
        st.caption("Ingen skader registrert ennå.")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: LOGGFØRING
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "📝 Loggføring":

    GRADERING = {
        "frigjort":         {"label":"Frigjort til media",      "farge":"#28a745","bg":"rgba(40,167,69,0.12)", "ikon":"📢","kort":"MEDIA"},
        "intern_offentlig": {"label":"Intern – offentlig",      "farge":"#2196f3","bg":"rgba(33,150,243,0.10)","ikon":"🔓","kort":"INTERN"},
        "intern_ikke_off":  {"label":"Intern – ikke offentlig", "farge":"#cc0000","bg":"rgba(200,0,0,0.08)",   "ikon":"🔒","kort":"LÅST"},
    }
    er_admin = st.session_state.get("admin_ok", False)

    # ── KOMMUNIKASJONSANSVARLIG-MODUS ─────────────────────────────────────────
    if st.session_state.get("komm_modus"):
        st.markdown(f"""<div style='background:linear-gradient(135deg,#1a3a1a,#0d2b0d);
        color:white;padding:20px 28px;border-radius:14px;margin-bottom:20px;
        border:2px solid #28a745;'>
        <div style='font-size:1.4rem;font-weight:bold;'>📡 Kommunikasjonsansvarlig</div>
        <div style='opacity:0.7;margin-top:4px;font-size:0.9rem;'>
        Viser kun informasjon frigitt til media · {d['status']}</div>
        </div>""", unsafe_allow_html=True)
        if st.button("← Tilbake til logg", key="komm_tilbake"):
            st.session_state["komm_modus"] = False; st.rerun()
        st.write("")
        fresh = gs_last_liste("logg", LOGG_FIL)
        frigjorte = [e for e in fresh if e.get("gradering") == "frigjort"]
        if not frigjorte:
            st.markdown("""<div style='text-align:center;padding:60px 20px;opacity:0.5;'>
            <div style='font-size:3rem;'>📭</div>
            <div style='margin-top:12px;font-size:1.1rem;'>Ingen informasjon er frigitt til media ennå</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.caption(f"📢 {len(frigjorte)} melding(er) frigitt til media")
            for e in reversed(frigjorte):
                st.markdown(f"""<div style='border-left:5px solid #28a745;
                background:rgba(40,167,69,0.08);border-radius:10px;
                padding:16px 20px;margin-bottom:12px;'>
                <div style='font-size:0.78rem;color:#28a745;font-weight:bold;
                margin-bottom:8px;letter-spacing:0.05em;'>
                📢 FRIGITT TIL MEDIA &nbsp;·&nbsp; {e.get('tidspunkt','')}
                {f" &nbsp;·&nbsp; ✍️ {e.get('forfatter','')}" if e.get('forfatter') else ''}
                </div>
                <div style='font-size:1.05rem;line-height:1.7;'>{e.get('tekst','')}</div>
                </div>""", unsafe_allow_html=True)

        st.write("---")
        with st.expander("📋 Huskeregel for mediahåndtering", expanded=False):
            st.markdown("""
<div style='line-height:1.8;font-size:0.95rem;'>

<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;'>

<div style='background:rgba(220,53,69,0.08);border:1px solid #dc3545;border-radius:10px;padding:14px;'>
<div style='font-weight:bold;color:#dc3545;margin-bottom:6px;'>🚔 Politiet eier totalbildet</div>
<div style='font-size:0.88rem;opacity:0.85;'>Uttal deg kun om <b>din egen innsats</b>: antall mannskaper, utstyr og terrengforhold. Alt om årsak, taktikk og pasient → henvis til politiets innsatsleder.</div>
</div>

<div style='background:rgba(255,193,7,0.08);border:1px solid #ffc107;border-radius:10px;padding:14px;'>
<div style='font-weight:bold;color:#b8860b;margin-bottom:6px;'>🚫 Aldri spekuler</div>
<div style='font-size:0.88rem;opacity:0.85;'>«Tror dere skredet ble utløst av..?» → svar alltid med <b>kalde fakta</b> om arbeidet her og nå. Ingen teorier, ingen antakelser.</div>
</div>

<div style='background:rgba(33,150,243,0.08);border:1px solid #2196f3;border-radius:10px;padding:14px;'>
<div style='font-weight:bold;color:#1565c0;margin-bottom:6px;'>🛡️ Skjerm pasient og pårørende</div>
<div style='font-size:0.88rem;opacity:0.85;'>Bekreft <b>aldri</b> alder, kjønn, relasjoner eller identitet. Kun helse og politi frigir slik informasjon.</div>
</div>

</div>

<div style='background:rgba(128,128,128,0.06);border-radius:10px;padding:14px;margin-bottom:12px;'>
<div style='font-weight:bold;margin-bottom:8px;'>🌉 Bruk broen – slik styrer du intervjuet</div>
<div style='font-size:0.88rem;'>
<b>Journalist spør:</b> «Hvor kritisk skadet er personen dere nettopp hentet ut?»<br>
<b>Svar med bro:</b> <i>«Helsevesenet må uttale seg om skadeomfanget, men det jeg kan si om vår innsats er at vi fikk pasienten raskt ned til ventende ambulanse til tross for svært krevende terreng.»</i>
</div>
</div>

<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;'>
<div style='background:rgba(128,128,128,0.06);border-radius:10px;padding:12px;'>
<div style='font-weight:bold;margin-bottom:4px;'>⏱️ Kjøp deg tid</div>
<div style='font-size:0.85rem;opacity:0.85;'>«Jeg er midt i en operativ vurdering. Send SMS – jeg ringer tilbake om 15 minutter.»<br>Bruk tiden til å hente ut godkjente fakta fra denne skjermen.</div>
</div>
<div style='background:rgba(128,128,128,0.06);border-radius:10px;padding:12px;'>
<div style='font-weight:bold;margin-bottom:4px;'>👁️ Én stemme ut</div>
<div style='font-size:0.85rem;opacity:0.85;'>Kun operativ leder eller dedikert kommunikasjonsansvarlig snakker med media. Pass på at KO-tavla ikke synes i bakgrunnen på bilder/video.</div>
</div>
</div>

</div>""", unsafe_allow_html=True)

        # ── PRESSEMELDING ─────────────────────────────────────────────────────
        st.write("---")
        st.markdown("### 📰 Generer pressemelding")
        st.caption("Fyll ut feltene til venstre – pressemeldingen oppdateres i sanntid til høyre.")
        st.write("")

        skj, prev = st.columns([1, 1], gap="large")

        with skj:
            st.markdown("**📋 Oppdragsinfo**")
            pm_oppdragsgiver = st.text_input("Oppdragsgiver", placeholder="Trøndelag politidistrikt", key="pm_og")
            pm_hendelse      = st.text_area("Hva har skjedd?", placeholder="et omfattende jordskred som har tatt med seg fylkesveien og isolert flere husstander", height=80, key="pm_hend")
            pm_sted          = st.text_input("Geografisk område", placeholder="Hovin i Melhus kommune", key="pm_sted")
            pm_tid           = st.text_input("Tidspunkt for varsling", value=datetime.now().strftime("%d.%m.%Y kl. %H:%M"), key="pm_tid")

            st.write("")
            st.markdown("**👥 Vår innsats**")
            pm_antall        = st.number_input("Antall frivillige mannskaper", min_value=1, value=10, key="pm_ant")
            pm_ressurser     = st.multiselect("Spesialressurser i bruk",
                                ["ATV","Snøscooter","Drone","Ambulanse","KO-vogn","Båt","Hundeekvipasje","Båre/terrengbåre"],
                                key="pm_res")
            pm_oppgave       = st.text_area("Vår konkrete oppgave", placeholder="Vi bistår med evakuering av beboere, driver førstehjelp på samleplass...", height=90, key="pm_opp")
            pm_samvirke      = st.text_input("Samvirke (hvem jobber vi med?)", placeholder="Norske Redningshunder og Røde Kors", key="pm_sam")

            st.write("")
            st.markdown("**🌧️ Forhold og publikum**")
            pm_forhold       = st.text_area("Utfordrende forhold (fakta)", placeholder="Dårlig vær, utfall av mobilnett og ufremkommelige veier.", height=70, key="pm_for")
            pm_rad           = st.text_area("Råd til publikum", placeholder="Hold avstand til skredområdet og ikke oppsøk rasstedet på egenhånd.", height=70, key="pm_rad")

            st.write("")
            st.markdown("**🔁 Henvisninger**")
            pm_hvem_bistaar  = st.text_input("NF Melhus bistår hvem?", placeholder="nødetatene", value="nødetatene", key="pm_bis",
                                              help="Vises i tittelen: «Norsk Folkehjelp bistår [dette]»")
            pm_henvis        = st.text_input("Henvis media videre til", placeholder="Politiets innsatsleder eller AMK", value="Politiets innsatsleder eller AMK", key="pm_hen",
                                              help="Vises nederst i pressemeldingen")

            st.write("")
            st.markdown("**📞 Pressekontakt**")
            pm_kontakt       = st.text_input("Navn, tittel og telefon", placeholder="Ola Nordmann, Operativ leder – 9XX XX XXX", key="pm_kon")

        # ── Generer tekst ──────────────────────────────────────────────────────
        dato_str = datetime.now().strftime("%d.%m.%Y").upper()
        by_str   = (pm_sted.split()[0].upper() if pm_sted else "MELHUS")
        res_str  = (", ".join(pm_ressurser[:-1]) + " og " + pm_ressurser[-1]
                    if len(pm_ressurser) > 1 else (pm_ressurser[0] if pm_ressurser else ""))

        pm_tekst = f"""PRESSEMELDING: Norsk Folkehjelp bistår {pm_hvem_bistaar or 'nødetatene'}{f' i {pm_sted}' if pm_sted else ''}

{by_str}, {dato_str}: Norsk Folkehjelp Melhus og Orkland er kalt ut på oppdrag{f' fra {pm_oppdragsgiver}' if pm_oppdragsgiver else ''} for å bistå ved {pm_hendelse or '[beskriv hendelse]'}{f' på {pm_sted}' if pm_sted else ''}. Våre mannskaper ble varslet {pm_tid}, og vi var raskt på plass med våre første ressurser.

SITUASJON OG VÅR ROLLE I FELT
Akkurat nå har Norsk Folkehjelp {pm_antall} frivillige mannskaper i aktiv innsats.{f' Vår hovedoppgave i denne fasen av aksjonen er å {pm_oppgave}' if pm_oppgave else ''}
{f'I tillegg til bakkemannskaper har vi satt inn spesialressurser, herunder {res_str}. ' if res_str else ''}{f'Vi jobber tett og godt sammen med {pm_samvirke} for å løse oppdraget mest mulig effektivt.' if pm_samvirke else ''}

{f'''KREVENDE FORHOLD
Operasjonen foregår under krevende forhold. Innsatsen påvirkes av {pm_forhold}
''' if pm_forhold else ''}
{f'''OPPFORDRING TIL PUBLIKUM
Av hensyn til den pågående redningsaksjonen ber vi publikum om å {pm_rad} Vi ber alle følge politiets anvisninger.
''' if pm_rad else ''}
VIKTIG INFORMASJON OM HENDELSEN
Norsk Folkehjelp er en støtteressurs for myndighetene. For overordnet status på hendelsens omfang, årsakssammenhenger, eller opplysninger om savnede/skadde, henviser vi direkte til {pm_henvis or 'Politiets innsatsleder eller AMK'}.

{f'''KUN FOR MEDIA – PRESSEKONTAKT:
{pm_kontakt} – Norsk Folkehjelp Melhus og Orkland''' if pm_kontakt else ''}

[Slutt på pressemelding]"""

        with prev:
            st.markdown("**👁️ Forhåndsvisning**")
            st.markdown(f"""<div style='background:rgba(40,167,69,0.05);border:2px solid #28a745;
            border-radius:12px;padding:20px 24px;font-family:Georgia,serif;
            font-size:0.92rem;line-height:1.8;white-space:pre-wrap;'>{pm_tekst}</div>""",
            unsafe_allow_html=True)
            st.write("")

            # Eksport som tekstfil
            st.download_button("📄 Last ned som tekstfil", data=pm_tekst.encode("utf-8"),
                file_name=f"pressemelding_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain", use_container_width=True)

            # Eksport som HTML
            pm_html = f"""<!DOCTYPE html><html lang="no"><head><meta charset="UTF-8">
<title>Pressemelding – NF Melhus og Orkland</title>
<style>body{{font-family:Georgia,serif;max-width:700px;margin:50px auto;color:#222;line-height:1.8;padding:0 20px}}
h1{{color:#cc0000;border-bottom:2px solid #cc0000;padding-bottom:10px}}
.meta{{color:#666;font-size:0.9rem;margin-bottom:24px}}
.seksjon{{margin-top:24px;font-weight:bold;text-transform:uppercase;letter-spacing:0.05em;color:#333}}
.footer{{margin-top:32px;border-top:1px solid #ddd;padding-top:16px;font-size:0.85rem;color:#666}}
@media print{{body{{margin:20px}}}}</style></head><body>
<h1>Pressemelding</h1>
<div class="meta">Norsk Folkehjelp Melhus og Orkland · {dato_str}</div>
<pre style="font-family:Georgia,serif;white-space:pre-wrap">{pm_tekst}</pre>
</body></html>"""
            st.download_button("🌐 Last ned som HTML (hjemmeside)", data=pm_html.encode("utf-8"),
                file_name=f"pressemelding_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                mime="text/html", use_container_width=True)

            # Publiser til logg
            st.write("")
            if st.button("📢 Publiser til logg som «Frigitt til media»",
                         use_container_width=True, type="primary", key="pm_pub"):
                liste = gs_last_liste("logg", LOGG_FIL)
                liste.append({
                    "id": datetime.now().strftime('%Y%m%d%H%M%S'),
                    "tidspunkt": datetime.now().strftime('%d.%m.%Y %H:%M'),
                    "forfatter": "Kommunikasjonsansvarlig",
                    "gradering": "frigjort",
                    "tekst": pm_tekst
                })
                gs_lagre_liste("logg", LOGG_FIL, liste, LOGG_HEADERS)
                st.success("✅ Pressemelding publisert i loggen som «Frigitt til media»")

        st.stop()

    # ── HEADER + KOMMUNIKASJONSKNAPP ─────────────────────────────────────────
    hc1, hc2 = st.columns([3,1])
    with hc1:
        st.markdown("<h2 style='margin-bottom:0'>📝 Operativ logg</h2>", unsafe_allow_html=True)
    with hc2:
        st.write("")
        if st.session_state.get("admin_ok"):
            if st.button("📡 Kommunikasjonsansvarlig", use_container_width=True, type="primary"):
                st.session_state["komm_modus"] = True; st.rerun()
        else:
            st.button("📡 Kommunikasjonsansvarlig", use_container_width=True, disabled=True,
                      help="🔒 Krever innlogging som administrator")

    # ── STATISTIKKBAR ─────────────────────────────────────────────────────────
    fresh_logg = gs_last_liste("logg", LOGG_FIL)
    n_media  = sum(1 for e in fresh_logg if e.get("gradering")=="frigjort")
    n_intern = sum(1 for e in fresh_logg if e.get("gradering")=="intern_offentlig")
    n_laaст  = sum(1 for e in fresh_logg if e.get("gradering")=="intern_ikke_off")
    s1,s2,s3,s4 = st.columns(4)
    s1.metric("Totalt", len(fresh_logg))
    s2.metric("📢 Media", n_media)
    s3.metric("🔓 Intern", n_intern)
    s4.metric("🔒 Låst", n_laaст if er_admin else "–")
    st.write("")

    # ── NY LOGGOPPFØRING (kun admin) ──────────────────────────────────────────
    if not er_admin:
        st.markdown("""<div style='border:2px dashed rgba(128,128,128,0.3);border-radius:12px;
        padding:28px;text-align:center;opacity:0.6;margin-bottom:20px;'>
        <div style='font-size:2rem;'>🔒</div>
        <div style='margin-top:8px;font-weight:bold;'>Loggføring krever innlogging</div>
        <div style='font-size:0.85rem;margin-top:4px;'>Logg inn via ⚙️ Administrasjon på operativ tavle</div>
        </div>""", unsafe_allow_html=True)
    else:
        with st.form("logg_form", clear_on_submit=True):
            lc1, lc2 = st.columns([2,1])
            with lc1:
                lf_tekst = st.text_area("Loggmelding *",
                    placeholder="Beskriv hendelsen, statusoppdatering, tiltak iverksatt...",
                    height=120, label_visibility="collapsed")
            with lc2:
                lf_forfatter = st.text_input("Ditt navn", placeholder="Ola Nordmann")
                st.markdown("<div style='font-size:0.78rem;opacity:0.55;text-transform:uppercase;"
                            "letter-spacing:0.05em;margin:10px 0 6px;'>Gradering</div>",
                            unsafe_allow_html=True)
                lf_grad = st.radio("Gradering",
                    options=["intern_offentlig","frigjort","intern_ikke_off"],
                    format_func=lambda k: f"{GRADERING[k]['ikon']} {GRADERING[k]['label']}",
                    index=0, label_visibility="collapsed")

            # Farget preview-stripe
            g = GRADERING[lf_grad]
            st.markdown(f"""<div style='border-radius:8px;border-left:5px solid {g["farge"]};
            background:{g["bg"]};padding:9px 16px;margin:4px 0 6px;
            display:flex;justify-content:space-between;align-items:center;'>
            <span style='font-weight:bold;color:{g["farge"]};font-size:0.92rem;'>
            {g["ikon"]} {g["label"]}</span>
            <span style='font-size:0.8rem;opacity:0.6;'>
            {"Synlig for media og kommunikasjonsansvarlig" if lf_grad=="frigjort"
             else "Synlig for alle interne brukere" if lf_grad=="intern_offentlig"
             else "🔒 Kun synlig for innloggede administratorer"}
            </span></div>""", unsafe_allow_html=True)

            if st.form_submit_button("💾 Loggfør", use_container_width=True, type="primary"):
                if not lf_tekst.strip():
                    st.error("Loggmeldingen kan ikke være tom.")
                else:
                    ny = {"id": datetime.now().strftime('%Y%m%d%H%M%S%f'),
                          "tidspunkt": datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                          "forfatter": lf_forfatter.strip() or "Admin",
                          "tekst": lf_tekst.strip(),
                          "gradering": lf_grad}
                    gs_append("logg", LOGG_FIL, ny, LOGG_HDR)
                    st.toast(f"✅ Logget som {g['ikon']} {g['kort']}", icon="📝"); st.rerun()

    # ── LOGG-TIDSLINJE ────────────────────────────────────────────────────────
    st.write("---")
    fresh_logg = gs_last_liste("logg", LOGG_FIL)

    if not fresh_logg:
        st.markdown("""<div style='text-align:center;padding:50px 20px;opacity:0.4;'>
        <div style='font-size:3rem;'>📋</div>
        <div style='margin-top:10px;'>Loggen er tom</div></div>""", unsafe_allow_html=True)
    else:
        # Filterrad
        fc1, fc2 = st.columns([3,1])
        with fc1:
            valg = ["frigjort","intern_offentlig"]
            if er_admin: valg.append("intern_ikke_off")
            vis_grad = st.multiselect("Vis", options=valg,
                default=valg,
                format_func=lambda k: f"{GRADERING[k]['ikon']} {GRADERING[k]['label']}")
        with fc2:
            st.write("")
            vis_ant = st.selectbox("Antall", [10,25,50,999], format_func=lambda x:"Alle" if x==999 else str(x))

        filtrert = [e for e in reversed(fresh_logg)
                    if e.get("gradering","intern_offentlig") in vis_grad
                    and (er_admin or e.get("gradering") != "intern_ikke_off")][:vis_ant]

        if not filtrert:
            st.caption("Ingen oppføringer matcher filteret.")

        # Tidslinje
        siste_dato = None
        for i, e in enumerate(filtrert):
            grad  = e.get("gradering","intern_offentlig")
            g     = GRADERING.get(grad, GRADERING["intern_offentlig"])
            tid   = e.get("tidspunkt","")
            dato  = tid[:10] if len(tid) >= 10 else tid
            klokkeslett = tid[11:19] if len(tid) >= 19 else tid[11:]

            # Datoskillelinje
            if dato != siste_dato:
                siste_dato = dato
                st.markdown(f"""<div style='display:flex;align-items:center;
                gap:12px;margin:18px 0 10px;'>
                <div style='flex:1;height:1px;background:rgba(128,128,128,0.2);'></div>
                <span style='font-size:0.78rem;opacity:0.5;font-weight:bold;
                letter-spacing:0.06em;'>{dato}</span>
                <div style='flex:1;height:1px;background:rgba(128,128,128,0.2);'></div>
                </div>""", unsafe_allow_html=True)

            # Låst vises nedtonet for admin, skjult for andre
            if grad == "intern_ikke_off" and not er_admin:
                st.markdown(f"""<div style='border-left:4px solid #777;
                background:rgba(128,128,128,0.05);border-radius:8px;
                padding:9px 16px;margin-bottom:6px;opacity:0.4;'>
                🔒 <em>Intern – ikke offentlig</em>
                <span style='float:right;font-size:0.75rem;'>{klokkeslett}</span>
                </div>""", unsafe_allow_html=True)
                continue

            # Badge-farge for gradering
            adm_strip = (f"<span style='background:{g['farge']};color:white;font-size:0.68rem;"
                         f"font-weight:bold;padding:2px 7px;border-radius:4px;letter-spacing:0.05em;"
                         f"margin-right:8px;'>{g['kort']}</span>")

            # Slette-knapp kun for admin
            slett_html = ""
            if er_admin:
                col_txt, col_del = st.columns([20,1])
            else:
                col_txt = st.container()

            with col_txt:
                st.markdown(f"""<div style='border-left:4px solid {g["farge"]};
                background:{g["bg"]};border-radius:0 10px 10px 0;
                padding:13px 18px;margin-bottom:6px;'>
                <div style='display:flex;justify-content:space-between;
                align-items:center;margin-bottom:7px;'>
                <div>{adm_strip}
                <span style='font-size:0.8rem;opacity:0.7;'>
                {f"✍️ <b>{e['forfatter']}</b> &nbsp;·&nbsp; " if e.get('forfatter') else ''}
                🕐 {klokkeslett}</span></div>
                </div>
                <div style='font-size:0.97rem;line-height:1.7;white-space:pre-wrap;'>{e.get('tekst','')}</div>
                </div>""", unsafe_allow_html=True)

            if er_admin:
                with col_del:
                    st.write("")
                    if st.button("🗑️", key=f"del_logg_{e.get('id',i)}", help="Slett oppføring"):
                        ny_liste = [x for x in gs_last_liste("logg", LOGG_FIL) if x.get("id") != e.get("id")]
                        gs_lagre_liste("logg", LOGG_FIL, ny_liste, LOGG_HDR)
                        st.toast("Oppføring slettet", icon="🗑️"); st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: VAKTINSTRUKS
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "📋 Vaktinstruks":
    st.markdown("<h2>📋 Instruks for aktivitet/vakt</h2>", unsafe_allow_html=True)
    if not vp.get("aktiv") or not (vp.get("sted") or vp.get("lagleder")):
        st.info("Ingen aktiv vaktinstruks. Admin fyller ut under ⚙️ Administrasjon på hovedsiden.")
    else:
        rig=beregn_rig(vp["tid_fra"])
        if rig: st.markdown(f"<div class='nf-rig'>⏰ Ferdig rigget: <b>{rig}</b> (30 min før oppstart)</div>", unsafe_allow_html=True)
        r1,r2,r3=st.columns(3)
        with r1:
            st.markdown(f"<div class='nf-card'>"
                        f"<div class='nf-lbl'>📍 Sted</div><div class='nf-val' style='font-size:1.2rem'>{vp['sted'] or '–'}</div>"
                        f"<div class='nf-lbl' style='margin-top:12px'>🕐 Tid</div><div class='nf-val'>{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div>"
                        f"<div class='nf-lbl' style='margin-top:12px'>👷 Lagleder</div><div class='nf-val'>{vp['lagleder'] or '–'}</div>"
                        f"</div>", unsafe_allow_html=True)
        with r2:
            mv="".join(f"<div class='nf-div'>• {m.strip()}</div>" for m in vp["mannskaper"].splitlines() if m.strip()) or "<em style='opacity:0.4'>Ikke oppgitt</em>"
            st.markdown(f"<div class='nf-card'><div class='nf-lbl'>👥 Mannskaper</div>"
                        f"<div style='line-height:1.9;font-size:0.95rem'>{mv}</div></div>", unsafe_allow_html=True)
        with r3:
            uv="".join(f"<div class='nf-div'>• {u.strip()}</div>" for u in vp["utstyr"].splitlines() if u.strip()) or "<em style='opacity:0.4'>Ikke oppgitt</em>"
            st.markdown(f"<div class='nf-card'><div class='nf-lbl'>🎒 Utstyr</div>"
                        f"<div style='line-height:1.9;font-size:0.95rem'>{uv}</div></div>", unsafe_allow_html=True)
        st.write("")
        n1,n2,n3=st.columns(3)
        with n1: st.markdown(f"<div class='nf-danger'><div class='nf-lbl'>🏥 Nærmeste legevakt</div><div class='nf-val'>{vp['legevakt'] or '–'}</div></div>", unsafe_allow_html=True)
        with n2: st.markdown(f"<div class='nf-danger'><div class='nf-lbl'>🏨 Nærmeste sykehus</div><div class='nf-val'>{vp['sykehus'] or '–'}</div></div>", unsafe_allow_html=True)
        with n3: st.markdown(f"<div class='nf-info'><div class='nf-lbl'>📻 Talegruppe i bruk</div><div class='nf-val'>{vp['talegruppe'] or '–'}</div></div>", unsafe_allow_html=True)
        if vp.get("notat"): st.write(""); st.info(f"📝 {vp['notat']}")
        st.write("---")
        st.download_button("📥 Eksporter beredskapsplan (HTML)",
                           data=generer_beredskapsplan(vp,d).encode("utf-8"),
                           file_name=f"beredskapsplan_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                           mime="text/html")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: KALKYLE
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "💰 Kalkyle – Sanitetsvakt":
    st.markdown("<h2>💰 Kalkyle – Sanitetsvakt</h2>", unsafe_allow_html=True)
    if not st.session_state.get("admin_ok"):
        st.warning("🔒 Kalkylen er kun tilgjengelig for innloggede administratorer.")
        st.caption("Logg inn via **⚙️ Administrasjon** på operativ tavle.")
        st.stop()
    st.caption("Fyll inn feltene – totalprisen oppdateres automatisk til høyre.")

    venstre, høyre = st.columns([3,2], gap="large")
    with venstre:

        st.markdown("<div class='nf-step'><div class='nf-step-ttl'>📄 Tilbudsinformasjon</div>", unsafe_allow_html=True)
        t1,t2=st.columns(2)
        with t1: k_kunde=st.text_input("Kunde / Arrangør",placeholder="Melhus IL")
        with t2: k_arr=st.text_input("Arrangement",placeholder="Sommerstevne 2026")
        k_dato=st.text_input("Dato for vakt",placeholder="21.06.2026")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='nf-step'><div class='nf-step-ttl'>📅 Varighet</div>", unsafe_allow_html=True)
        k_dager=st.slider("Antall dager",min_value=1,max_value=14,value=1)
        gsum=PRISER["grunnpris"]*k_dager
        st.markdown(f"<div class='nf-sub'>Grunnpris: {gsum:,.0f} kr</div>".replace(","," "), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        TIMER=[0,2,4,6,8,10,12,16,24]
        st.markdown("<div class='nf-step'><div class='nf-step-ttl'>👥 Mannskap</div>", unsafe_allow_html=True)
        ma1,ma2=st.columns(2)
        with ma1:
            st.markdown("**Sanitetspersonell**")
            k_san_ant=st.selectbox("Antall",list(range(11)),format_func=lambda x:"Ingen" if x==0 else f"{x} person{'er' if x>1 else ''}",key="s_ant")
        with ma2:
            st.markdown("**&nbsp;**")
            k_san_tim=st.selectbox("Timer per dag",TIMER,index=TIMER.index(8),format_func=lambda x:"Ikke i bruk" if x==0 else f"{x} timer",key="s_tim",disabled=k_san_ant==0)
        mb1,mb2=st.columns(2)
        with mb1:
            st.markdown("**Ambulansepersonell**")
            k_amb_ant=st.selectbox("Antall",list(range(11)),format_func=lambda x:"Ingen" if x==0 else f"{x} person{'er' if x>1 else ''}",key="a_ant")
        with mb2:
            st.markdown("**&nbsp;**")
            k_amb_tim=st.selectbox("Timer per dag",TIMER,index=TIMER.index(8),format_func=lambda x:"Ikke i bruk" if x==0 else f"{x} timer",key="a_tim",disabled=k_amb_ant==0)
        msum=PRISER["sanitet"]*k_san_ant*k_dager*k_san_tim + PRISER["ambulanse_m"]*k_amb_ant*k_dager*k_amb_tim
        st.markdown(f"<div class='nf-sub'>Mannskap totalt: {msum:,.0f} kr</div>".replace(","," "), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        KJT=[0,1,2,3,4]
        st.markdown("<div class='nf-step'><div class='nf-step-ttl'>🚑 Kjøretøy</div>", unsafe_allow_html=True)
        kj1,kj2,kj3=st.columns(3)
        with kj1: k_mbil=st.selectbox("Mannskapsbil",KJT,format_func=lambda x:"Ingen" if x==0 else f"{x} stk",key="mbil")
        with kj2: k_amb =st.selectbox("Ambulanse",   KJT,format_func=lambda x:"Ingen" if x==0 else f"{x} stk",key="amb_k")
        with kj3: k_atv =st.selectbox("ATV",         KJT,format_func=lambda x:"Ingen" if x==0 else f"{x} stk",key="atv_k")
        kjsum=(PRISER["mbil"]*k_mbil+PRISER["amb_kjt"]*k_amb+PRISER["atv_kjt"]*k_atv)*k_dager
        st.markdown(f"<div class='nf-sub'>Kjøretøy totalt: {kjsum:,.0f} kr</div>".replace(","," "), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='nf-step'><div class='nf-step-ttl'>🛣️ Kjøring</div>", unsafe_allow_html=True)
        kk1,kk2=st.columns(2)
        with kk1:
            k_km51 =st.number_input("Til/fra tjenestested 5.1 (km)",min_value=0,value=0,step=5)
            k_km56 =st.number_input("Til/fra tjenestested 5.6 (km)",min_value=0,value=0,step=5)
            k_kmbil=st.number_input("I tjeneste – bil (km)",         min_value=0,value=0,step=5)
        with kk2:
            k_kmamb=st.number_input("I tjeneste – ambulanse (km)",   min_value=0,value=0,step=5)
            k_atvt =st.number_input("ATV/scooter i tjeneste (timer)",min_value=0,value=0,step=1,
                                     help="Antall timer ATV eller scooter brukes i aktiv tjeneste")
        kjrsum=PRISER["km"]*(k_km51+k_km56+k_kmbil+k_kmamb)+PRISER["atv_t"]*k_atvt
        st.markdown(f"<div class='nf-sub'>Kjøring totalt: {kjrsum:,.0f} kr</div>".replace(","," "), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='nf-step'><div class='nf-step-ttl'>🩹 Forbruksmateriell</div>", unsafe_allow_html=True)
        k_forbruk=st.number_input("Estimert kostnad (kr)",min_value=0,value=0,step=100)
        st.markdown("</div>", unsafe_allow_html=True)

    # Kalkulasjon
    linjer=[
        ("Grunnpris",            f"{k_dager} dag × {PRISER['grunnpris']} kr",              gsum),
        ("Mannskap sanitet",     f"{k_san_ant} pers × {k_dager} dag × {k_san_tim} t × {PRISER['sanitet']} kr", PRISER["sanitet"]*k_san_ant*k_dager*k_san_tim),
        ("Mannskap ambulanse",   f"{k_amb_ant} pers × {k_dager} dag × {k_amb_tim} t × {PRISER['ambulanse_m']} kr", PRISER["ambulanse_m"]*k_amb_ant*k_dager*k_amb_tim),
        ("Mannskapsbil",         f"{k_mbil} stk × {k_dager} dag × {PRISER['mbil']} kr",   PRISER["mbil"]*k_mbil*k_dager),
        ("Ambulanse (kjøretøy)", f"{k_amb} stk × {k_dager} dag × {PRISER['amb_kjt']} kr", PRISER["amb_kjt"]*k_amb*k_dager),
        ("ATV",                  f"{k_atv} stk × {k_dager} dag × {PRISER['atv_kjt']} kr", PRISER["atv_kjt"]*k_atv*k_dager),
        ("Kjøring t/f 5.1",      f"{k_km51} km × {PRISER['km']} kr",                      PRISER["km"]*k_km51),
        ("Kjøring t/f 5.6",      f"{k_km56} km × {PRISER['km']} kr",                      PRISER["km"]*k_km56),
        ("Kjøring tjeneste – bil",       f"{k_kmbil} km × {PRISER['km']} kr",             PRISER["km"]*k_kmbil),
        ("Kjøring tjeneste – ambulanse", f"{k_kmamb} km × {PRISER['km']} kr",             PRISER["km"]*k_kmamb),
        ("ATV/scooter tjeneste", f"{k_atvt} t × {PRISER['atv_t']} kr",                    PRISER["atv_t"]*k_atvt),
    ]
    total=sum(v for _,_,v in linjer)+k_forbruk

    with høyre:
        st.markdown("### 📊 Prissammendrag")
        st.markdown(f"""<div style='background:#cc0000;color:white;border-radius:12px;
        padding:20px;text-align:center;margin-bottom:16px;'>
        <div style='font-size:0.85rem;opacity:0.85;margin-bottom:4px;'>ESTIMERT TOTALPRIS</div>
        <div style='font-size:2.5rem;font-weight:bold;'>{total:,.0f} kr</div>
        </div>""".replace(","," "), unsafe_allow_html=True)

        for navn,bere,belop in linjer:
            if belop==0: continue
            st.markdown(f"""<div style='display:flex;justify-content:space-between;align-items:baseline;
            padding:6px 0;border-bottom:1px solid rgba(128,128,128,0.15);'>
            <span style='font-size:0.88rem;'>{navn}</span>
            <span style='font-weight:bold;font-size:0.95rem;'>{belop:,.0f} kr</span>
            </div>""".replace(","," "), unsafe_allow_html=True)
        if k_forbruk:
            st.markdown(f"""<div style='display:flex;justify-content:space-between;
            padding:6px 0;border-bottom:1px solid rgba(128,128,128,0.15);'>
            <span style='font-size:0.88rem;'>Forbruksmateriell</span>
            <span style='font-weight:bold;'>{k_forbruk:,.0f} kr</span>
            </div>""".replace(","," "), unsafe_allow_html=True)

        st.write("")
        if st.button("📄 Generer tilbud", type="primary", use_container_width=True):
            html=generer_tilbud(k_kunde,k_arr,k_dato,linjer,total,k_forbruk)
            fn=f"tilbud_{(k_arr or 'sanitetsvakt').replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.html"
            st.download_button("📥 Last ned tilbud (HTML)",data=html.encode("utf-8"),
                               file_name=fn,mime="text/html",use_container_width=True,key="dl_t")
        st.caption("Åpne i nettleseren → Ctrl+P for å lagre som PDF.")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDE: ADMINISTRASJON
# ═══════════════════════════════════════════════════════════════════════════════
elif side == "⚙️ Administrasjon":
    st.markdown("<h2>⚙️ Administrasjon</h2>", unsafe_allow_html=True)

    if not st.session_state.get("admin_ok"):
        st.markdown("""<div style='max-width:380px;margin:60px auto;text-align:center;'>
        <div style='font-size:3rem;margin-bottom:16px;'>🔒</div>
        <div style='font-size:1.2rem;font-weight:bold;margin-bottom:8px;'>Adminpanelet er passordbeskyttet</div>
        <div style='opacity:0.6;font-size:0.9rem;margin-bottom:24px;'>Kun autoriserte brukere har tilgang.</div>
        </div>""", unsafe_allow_html=True)
        _,lc,_ = st.columns([1,2,1])
        with lc:
            pw = st.text_input("Passord", type="password", placeholder="Skriv inn passord...", label_visibility="collapsed")
            if st.button("🔓 Logg inn", type="primary", use_container_width=True):
                if pw == "melhus123": st.session_state["admin_ok"]=True; st.rerun()
                else: st.error("❌ Feil passord")
    else:
        cl,_ = st.columns([1,5])
        with cl:
            if st.button("🔒 Logg ut"): st.session_state["admin_ok"]=False; st.rerun()
        st.write("")

        # ── SYSTEMSTATUS PANEL ───────────────────────────────────────────────
        def sjekk_api(url, headers=None, timeout=5):
            try:
                r = requests.get(url, headers=headers or STD_HEADERS, timeout=timeout)
                return r.status_code < 500
            except: return False

        def lampe(ok, tekst, detalj=""):
            farge = "#28a745" if ok else "#dc3545"
            status = "OK" if ok else "FEIL"
            return f"""<div style='display:flex;align-items:center;gap:10px;padding:8px 12px;
            background:rgba(128,128,128,0.06);border-radius:8px;'>
            <div style='width:14px;height:14px;border-radius:50%;background:{farge};
            box-shadow:0 0 6px {farge};flex-shrink:0;'></div>
            <div><b style='font-size:0.9rem;'>{tekst}</b>
            <span style='font-size:0.78rem;opacity:0.6;margin-left:6px;'>{status}{(' – '+detalj) if detalj else ''}</span>
            </div></div>"""

        with st.expander("🔌 Systemstatus", expanded=False):
            with st.spinner("Sjekker tilkoblinger..."):
                # Google Sheets
                try:
                    sh = _gs_sh()
                    gs_ok = sh is not None
                    gs_detalj = sh.title if gs_ok else "Ingen tilkobling"
                except: gs_ok=False; gs_detalj="Feil"

                # MET / Yr
                met_ok = sjekk_api("https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=63.28&lon=10.28")

                # NVE Varsom
                nve_ok = sjekk_api("https://api01.nve.no/hydrology/forecast/avalanche/v6.3.0/api/AvalancheWarningByRegion/Detail/3020/no/2026-01-01/2026-01-01")

                # Tensio
                tensio_ok = sjekk_api("https://kart.tensio.no/enterprise/rest/services/Hosted/StromstansTN/FeatureServer/0/query?where=1%3D1&outFields=objectid&returnGeometry=false&f=geojson")

                # Politilogg
                politilogg_ok = sjekk_api("https://www.politiet.no/politiloggen?distrikt=trondelag")

                # Resend
                try:
                    api_key = st.secrets["resend"]["api_key"]
                    resend_ok = bool(api_key)
                    resend_detalj = "Nøkkel konfigurert"
                except: resend_ok=False; resend_detalj="Mangler i Secrets"

            s1,s2,s3 = st.columns(3)
            with s1:
                st.markdown(lampe(gs_ok,    "Google Sheets", gs_detalj),    unsafe_allow_html=True)
                st.markdown(lampe(resend_ok, "Resend e-post", resend_detalj), unsafe_allow_html=True)
            with s2:
                st.markdown(lampe(met_ok,  "MET / Yr API"),    unsafe_allow_html=True)
                st.markdown(lampe(nve_ok,  "NVE Varsom API"),  unsafe_allow_html=True)
            with s3:
                st.markdown(lampe(tensio_ok,     "Tensio strøm API"),   unsafe_allow_html=True)
                st.markdown(lampe(politilogg_ok, "Politilogg (politiet.no)"), unsafe_allow_html=True)

        st.write("")
        adm_tabs = st.tabs(["📡 Beredskapsstatus","📋 Vaktinstruks","⚠️ Avvik","👥 Deltakelser"])

        # ── Tab 1: Beredskapsstatus ──────────────────────────────────────────
        with adm_tabs[0]:
            a1,a2 = st.columns(2)
            with a1:
                sv=["🟢 Normal Beredskap","🟡 Forhøyet Beredskap","🔴 Rød / Høy beredskap"]
                ns=st.selectbox("Beredskapsnivå",sv,index=sv.index(d['status']))
                nb=st.text_area("Beskjed til stab",value=d['beskjed'])
                kv=["Ingen","Daglig drift","Snøskred","Flom","Jordras","Ekom-bortfall","Isolasjon / Evakuering","Søk/Redning"]
                nk=st.selectbox("Tiltakskort",kv,index=kv.index(d['kort']))
            with a2:
                nl=st.text_input("Leder",value=d['leder'])
                nv=st.text_input("Vakt-tlf",value=d['vakt'])
                nlog=st.text_area("Operativ logg",value=d['logg'],height=130)
            st.write("**📡 Infrastruktur**")
            a3,a4=st.columns(2)
            with a3:
                ekv=["🟢 Normal drift","🟡 Redusert kapasitet/Utfall noen steder","🔴 Omfattende ekom-bortfall"]
                ne=st.selectbox("Ekom",ekv,index=ekv.index(d['ekom']))
            with a4:
                vev=["🟢 Veinett åpent","🟡 Lokale stengninger","🔴 Kritiske brudd / Isolerte bygder"]
                nve=st.selectbox("Vei",vev,index=vev.index(d['vei']))
            if st.button("💾 Lagre beredskapsstatus", type="primary"):
                gs_lagre_json("beredskap",FIL,{"status":ns,"beskjed":nb,"leder":nl,"vakt":nv,"kort":nk,"logg":nlog,"ekom":ne,"vei":nve})
                st.toast("✅ Lagret!",icon="💾"); st.rerun()

        # ── Tab 2: Vaktinstruks ──────────────────────────────────────────────
        with adm_tabs[1]:
            vchk1,vchk2=st.columns(2)
            with vchk1: va=st.checkbox("Aktiver vaktinstruks",value=vp.get("aktiv",False))
            with vchk2: vskjul=st.checkbox("Skjul på forsiden",value=vp.get("skjul_forside",False))
            vp1,vp2=st.columns(2)
            with vp1:
                vs=st.text_input("📍 Sted",value=vp.get("sted",""))
                vl=st.text_input("👷 Lagleder",value=vp.get("lagleder",""))
                vtg=st.text_input("📻 Talegruppe",value=vp.get("talegruppe",""))
                vlv=st.text_input("🏥 Legevakt",value=vp.get("legevakt",""))
                vsh=st.text_input("🏨 Sykehus",value=vp.get("sykehus",""))
            with vp2:
                vtf=st.text_input("🕐 Tid fra",value=vp.get("tid_fra",""),placeholder="08:00")
                vtt=st.text_input("🕑 Tid til",value=vp.get("tid_til",""),placeholder="16:00")
                rp=beregn_rig(vtf)
                if rp: st.caption(f"⏰ Ferdig rigget: **{rp}**")
                vm=st.text_area("👥 Mannskaper",value=vp.get("mannskaper",""),height=100,placeholder="Ett navn per linje")
                vu=st.text_area("🎒 Utstyr",value=vp.get("utstyr",""),height=100,placeholder="Ett element per linje")
            vn=st.text_area("📝 Notat",value=vp.get("notat",""),height=60)
            vba,vbb=st.columns(2)
            with vba:
                if st.button("💾 Lagre vaktinstruks",type="primary",use_container_width=True):
                    gs_lagre_json("vaktplan",VAKTPLAN_FIL,{"aktiv":va,"skjul_forside":vskjul,"sted":vs,"lagleder":vl,
                        "talegruppe":vtg,"legevakt":vlv,"sykehus":vsh,"tid_fra":vtf,"tid_til":vtt,
                        "mannskaper":vm,"utstyr":vu,"notat":vn})
                    st.toast("✅ Lagret!",icon="📋"); st.rerun()
            with vbb:
                if st.button("🗑️ Nullstill instruks",use_container_width=True):
                    gs_lagre_json("vaktplan",VAKTPLAN_FIL,dict(VP_DEFAULTS))
                    st.toast("🗑️ Nullstilt",icon="🗑️"); st.rerun()

        # ── Tab 3: Avvik ─────────────────────────────────────────────────────
        with adm_tabs[2]:
            åpne=[a for a in avvik_liste if not a.get("fulgt_opp")]
            lukkede=[a for a in avvik_liste if a.get("fulgt_opp")]
            st.caption(f"{len(åpne)} åpne · {len(lukkede)} lukket")
            if not avvik_liste:
                st.info("Ingen avvik registrert ennå.")
            else:
                endret=False
                for i,a in enumerate(avvik_liste):
                    fulgt=a.get("fulgt_opp",False); haster=a.get("umiddelbar_oppfolging",False) and not fulgt
                    brd="#dc3545" if haster else ("#28a745" if fulgt else "#ffc107")
                    bga="rgba(40,167,69,0.07)" if fulgt else ("rgba(220,53,69,0.07)" if haster else "rgba(255,193,7,0.07)")
                    ikon="✅ Lukket" if fulgt else ("⚡ Akutt" if haster else "🟡 Åpen")
                    st.markdown(f"""<div style='border-left:4px solid {brd};background:{bga};
                    border-radius:6px;padding:10px 14px;margin-bottom:6px;'>
                    <b>{a.get('navn','–')}</b> · <small style='opacity:0.6;'>{a.get('registrert','')}</small> · <b>{ikon}</b><br>
                    <span style='font-size:0.9rem;'>{a.get('hendelse','')}</span>
                    {f"<br><small><i>{a.get('konsekvens','')}</i></small>" if a.get('konsekvens') else ""}
                    {f"<br><small>📝 {a.get('oppfolging_notat','')}</small>" if a.get('oppfolging_notat') else ""}
                    </div>""", unsafe_allow_html=True)
                    if not fulgt:
                        ka,kb,kc=st.columns([3,1,1])
                        with ka: notat=st.text_input("Notat",key=f"an_{i}",placeholder="Beskriv tiltak som er gjort...",label_visibility="collapsed")
                        with kb: send_svar=st.checkbox("Send svar",key=f"svar_{i}",value=bool(a.get("epost")),
                                                        help=f"Sender e-post til {a.get('epost','–') or 'ingen e-post registrert'}")
                        with kc:
                            if st.button("✅ Lukk",key=f"al_{i}",use_container_width=True):
                                avvik_liste[i]["fulgt_opp"]=True; avvik_liste[i]["oppfolging_notat"]=notat; endret=True
                                if send_svar and a.get("epost"):
                                    ok,melding=send_avvik_kvittering(a, notat)
                                    if ok: st.toast(f"📧 {melding}",icon="✅")
                                    else:  st.toast(f"⚠️ {melding}",icon="⚠️")
                    else:
                        da1,da2=st.columns(2)
                        with da1:
                            if st.button("↩️ Gjenåpne",key=f"ag_{i}",use_container_width=True):
                                avvik_liste[i]["fulgt_opp"]=False; endret=True
                        with da2:
                            if st.button("🗑️ Slett",key=f"as_{i}",use_container_width=True):
                                avvik_liste.pop(i); gs_lagre_liste("avvik",AVVIK_FIL,avvik_liste,AVVIK_HDR); st.rerun()
                if endret: gs_lagre_liste("avvik",AVVIK_FIL,avvik_liste,AVVIK_HDR); st.rerun()

        # ── Tab 4: Deltakelser ───────────────────────────────────────────────
        with adm_tabs[3]:
            if del_liste:
                dfd=pd.DataFrame(del_liste)[["registrert","navn","oppdrag","tid_ut","tid_inn","utlegg_kr"]]
                dfd.columns=["Tidspunkt","Navn","Oppdrag","Tid ut","Tid inn","Utlegg (kr)"]
                st.dataframe(dfd,use_container_width=True,hide_index=True)
            else:
                st.info("Ingen deltakelser registrert ennå.")

