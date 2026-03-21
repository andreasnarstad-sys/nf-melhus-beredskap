import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
from datetime import datetime
from utils import (
    inject_css, vis_sidebar_status,
    last_data, lagre_data,
    last_vaktplan, lagre_vaktplan,
    last_liste, lagre_liste,
    last_epost_config, lagre_epost_config,
    send_avvik_epost,
    hent_alle_varsler, hent_lokal_vaer,
    beregn_rig_tid, generer_html_export,
    KART_KOORDINATER, STATUS_FARGER,
    DELTAKELSE_FIL, AVVIK_FIL, VAKTPLAN_FIL,
    EPOST_CONFIG_FIL
)

st.set_page_config(page_title="NF Operativ Tavle – Melhus/Orkland",
                   layout="wide", page_icon="🚑")
inject_css()

# --- DATA ---
d               = last_data()
vp              = last_vaktplan()
epost_cfg       = last_epost_config()
avvik_liste     = last_liste(AVVIK_FIL)
deltakelse_liste= last_liste(DELTAKELSE_FIL)
akutte          = [a for a in avvik_liste if a.get("umiddelbar_oppfolging") and not a.get("fulgt_opp")]

# --- SIDEMENY ---
with st.sidebar:
    if os.path.exists("nf_logo.png"):
        st.image("nf_logo.png", width=160)

    bg = STATUS_FARGER.get(d['status'], "#333")
    st.markdown(f"""
        <div style='background:{bg}; color:white; padding:10px 14px;
        border-radius:8px; font-weight:bold; margin-bottom:10px;'>
        {d['status']}
        </div>""", unsafe_allow_html=True)

    if akutte:
        st.error(f"⚡ {len(akutte)} avvik krever umiddelbar oppfølging!")

    st.markdown("---")
    m1, m2 = st.columns(2)
    m1.metric("Deltakelser", len(deltakelse_liste))
    m2.metric("Avvik", len(avvik_liste),
              delta=f"{len(akutte)} akutte" if akutte else None,
              delta_color="inverse")
    st.markdown("---")
    st.caption("Bruk menyen øverst til venstre for å navigere mellom sidene.")

# --- HEADER ---
st.markdown("<h2 style='text-align:center; color:#cc0000;'>🚑 Norsk Folkehjelp: Melhus & Orkland</h2>",
            unsafe_allow_html=True)

# STATUS-BANNER
bg = STATUS_FARGER.get(d['status'], "#333")
st.markdown(f"""
    <div style="background:{bg}; padding:20px; border-radius:15px;
    text-align:center; color:white; border:2px solid rgba(0,0,0,0.2);">
    <h1 style="margin:0; font-size:3.5rem;">{d['status']}</h1>
    <p style="font-size:1.5rem; margin-top:5px; font-weight:500;">{d['beskjed']}</p>
    </div>""", unsafe_allow_html=True)

st.write("")

# ALARMTONE VED RØD BEREDSKAP
if d['status'] == "🔴 Rød / Høy beredskap":
    if not st.session_state.get("alarm_spilt"):
        st.session_state["alarm_spilt"] = True
        components.html("""<script>
        const ctx=new(window.AudioContext||window.webkitAudioContext)();
        function pip(f,s,dur){const o=ctx.createOscillator(),g=ctx.createGain();
        o.connect(g);g.connect(ctx.destination);o.type='square';o.frequency.value=f;
        g.gain.setValueAtTime(0.4,ctx.currentTime+s);
        g.gain.exponentialRampToValueAtTime(0.001,ctx.currentTime+s+dur);
        o.start(ctx.currentTime+s);o.stop(ctx.currentTime+s+dur+0.05);}
        pip(880,0.0,0.15);pip(880,0.2,0.15);pip(880,0.4,0.15);pip(660,0.7,0.6);
        </script>""", height=0)
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
        st.markdown(f"<div class='nf-card'><b>📍 Melhus Sentrum:</b><br>"
                    f"<h2 style='margin:5px 0;color:#1f77b4;'>{t}°C &nbsp;|&nbsp; {v} m/s</h2>"
                    f"<small style='opacity:0.7;'>{prog_str}</small></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='nf-card'><b>📍 Melhus Sentrum:</b><br><br>"
                    "<small>⚠️ Værvarselet er ikke tilgjengelig.</small></div>", unsafe_allow_html=True)

with c_led:
    kort_stil = (
        "background:rgba(128,128,128,0.15);color:inherit;border:1px solid rgba(128,128,128,0.3);font-size:0.85rem;opacity:0.7;"
        if d['kort'] in ('Ingen','Daglig drift') else
        "background:#cc0000;color:white;border:2px solid #990000;box-shadow:0 2px 8px rgba(200,0,0,0.4);font-size:1rem;"
    )
    st.markdown(
        f"<div class='nf-card-blue'><b>📞 Operativ Ledelse:</b><br>"
        f"<span style='font-size:1.1rem;'>Leder: <b>{d['leder']}</b></span><br>"
        f"<span style='font-size:1.1rem;'>Vakt-tlf: <b>{d['vakt']}</b></span>"
        f"<br><br><div style='display:inline-block;{kort_stil}padding:4px 12px;border-radius:6px;font-weight:bold;'>"
        f"📋 {d['kort']}</div></div>", unsafe_allow_html=True)

with c_infra:
    infra_cls = ("nf-infra-err" if ("🔴" in d['ekom'] or "🔴" in d['vei'])
                 else "nf-infra-warn" if ("🟡" in d['ekom'] or "🟡" in d['vei'])
                 else "nf-infra-ok")
    st.markdown(
        f"<div class='nf-infra-base {infra_cls}'><b>📡 Kritisk Infrastruktur:</b><br><br>"
        f"<span style='font-weight:bold;'>EKOM:</span><br>"
        f"<span style='font-size:0.9rem;opacity:0.9;'>{d['ekom']}</span><br><br>"
        f"<span style='font-weight:bold;'>VEI / ISOLASJON:</span><br>"
        f"<span style='font-size:0.9rem;opacity:0.9;'>{d['vei']}</span></div>", unsafe_allow_html=True)

# KART OG VARSLER
st.write("---")
c_tittel, c_filter = st.columns([3, 1])
with c_tittel: st.subheader("🚨 Operativ Oversikt & Farevarsler")
with c_filter: valgt_region = st.selectbox("🌍 Velg område:", list(KART_KOORDINATER.keys()), index=0)

coords = KART_KOORDINATER.get(valgt_region, "lat=63.26&lon=10.15&zoom=8")
c_map, c_alerts = st.columns([1.5, 1])
with c_map:
    components.iframe(f"https://embed.windy.com/embed2.html?{coords}&overlay=wind&metricWind=m%2Fs", height=450)
with c_alerts:
    varsler = hent_alle_varsler(valgt_region)
    if varsler:
        df = pd.DataFrame(varsler).sort_values(by=["Nivå","Område"], ascending=[False,True])
        def style_row(row):
            c = {2:("#FFFF00","black"),3:("#FF9900","white"),4:("#FF0000","white")}.get(row.Nivå,("white","black"))
            return [f'background-color:{c[0]};color:{c[1]};font-weight:bold']*len(row)
        st.dataframe(df.style.apply(style_row, axis=1), use_container_width=True, height=450, hide_index=True)
    else:
        region_kort = valgt_region.split(" ")[0]
        st.markdown(f"""<div class='nf-ok-box'>
            <div style='font-size:3rem;'>✅</div>
            <div style='font-size:1.2rem;font-weight:bold;color:#28a745;margin-top:10px;'>Ingen aktive farevarsler</div>
            <div style='opacity:0.6;margin-top:6px;'>for {region_kort}</div>
            </div>""", unsafe_allow_html=True)

# OPERATIV LOGG
if d['logg']:
    st.write("---")
    st.subheader("📝 Operativ Logg")
    st.text_area("", value=d['logg'], height=120, disabled=True, label_visibility="collapsed")

# VAKTINSTRUKS I DASHBOARD
if vp.get("aktiv") and (vp.get("sted") or vp.get("lagleder")):
    st.write("---")
    st.subheader("📋 Instruks for aktivitet/vakt")
    rig = beregn_rig_tid(vp["tid_fra"])
    vi1, vi2, vi3 = st.columns(3)
    with vi1:
        rig_html = f"<div class='nf-rig' style='margin-top:8px;'>⏰ Ferdig rigget: <b>{rig}</b></div>" if rig else ""
        st.markdown(f"<div class='nf-card' style='min-height:unset;'>"
                    f"<div class='nf-label'>📍 Sted</div><div class='nf-val' style='font-size:1.15rem;'>{vp['sted'] or '–'}</div>"
                    f"<div class='nf-label' style='margin-top:10px;'>🕐 Tid</div><div class='nf-val'>{vp['tid_fra'] or '–'} – {vp['tid_til'] or '–'}</div>"
                    f"{rig_html}</div>", unsafe_allow_html=True)
    with vi2:
        mv = "".join(f"<div class='nf-divider'>• {m.strip()}</div>" for m in vp["mannskaper"].splitlines() if m.strip()) or "<em style='opacity:0.4;'>Ikke oppgitt</em>"
        st.markdown(f"<div class='nf-card' style='min-height:unset;'>"
                    f"<div class='nf-label'>👷 Lagleder</div><div class='nf-val' style='margin-bottom:10px;'>{vp['lagleder'] or '–'}</div>"
                    f"<div class='nf-label'>👥 Mannskaper</div><div style='font-size:0.9rem;line-height:1.8;'>{mv}</div></div>", unsafe_allow_html=True)
    with vi3:
        uv = "".join(f"<div class='nf-divider'>• {u.strip()}</div>" for u in vp["utstyr"].splitlines() if u.strip()) or "<em style='opacity:0.4;'>Ikke oppgitt</em>"
        st.markdown(f"<div class='nf-card' style='min-height:unset;'>"
                    f"<div class='nf-label'>🎒 Utstyr</div><div style='font-size:0.9rem;line-height:1.8;'>{uv}</div></div>", unsafe_allow_html=True)
    vi4, vi5, vi6 = st.columns(3)
    with vi4: st.markdown(f"<div class='nf-card-danger'><div class='nf-label'>🏥 Legevakt</div><div class='nf-val'>{vp['legevakt'] or '–'}</div></div>", unsafe_allow_html=True)
    with vi5: st.markdown(f"<div class='nf-card-danger'><div class='nf-label'>🏨 Sykehus</div><div class='nf-val'>{vp['sykehus'] or '–'}</div></div>", unsafe_allow_html=True)
    with vi6: st.markdown(f"<div class='nf-card-info'><div class='nf-label'>📻 Talegruppe</div><div class='nf-val'>{vp['talegruppe'] or '–'}</div></div>", unsafe_allow_html=True)
    if vp.get("notat"): st.info(f"📝 {vp['notat']}")
    st.download_button("📥 Eksporter beredskapsplan",
                       data=generer_html_export(vp, d).encode("utf-8"),
                       file_name=f"beredskapsplan_{datetime.now().strftime('%Y%m%d_%H%M')}.html",
                       mime="text/html")

# --- ADMIN ---
st.write("---")
st.markdown("<div style='text-align:right;color:#999;font-size:0.85rem;margin-bottom:-20px;'>⚙️ Administrasjon tilgjengelig nedenfor</div>", unsafe_allow_html=True)

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

        # Beredskapsstatus
        a1, a2 = st.columns(2)
        with a1:
            status_valg = ["🟢 Normal Beredskap","🟡 Forhøyet Beredskap","🔴 Rød / Høy beredskap"]
            n_stat = st.selectbox("Nivå:", status_valg, index=status_valg.index(d['status']))
            n_besk = st.text_area("Beskjed:", value=d['beskjed'])
            kort_valg = ["Ingen","Daglig drift","Snøskred","Flom","Jordras","Ekom-bortfall","Isolasjon / Evakuering","Søk/Redning"]
            n_kort = st.selectbox("Tiltakskort:", kort_valg, index=kort_valg.index(d['kort']))
        with a2:
            n_led  = st.text_input("Leder:", value=d['leder'])
            n_vak  = st.text_input("Vakt-tlf:", value=d['vakt'])
            n_logg = st.text_area("Logg:", value=d['logg'], height=150)

        st.write("**Infrastruktur-status**")
        a3, a4 = st.columns(2)
        with a3:
            ekom_valg = ["🟢 Normal drift","🟡 Redusert kapasitet/Utfall noen steder","🔴 Omfattende ekom-bortfall"]
            n_ekom = st.selectbox("Ekom:", ekom_valg, index=ekom_valg.index(d['ekom']))
        with a4:
            vei_valg = ["🟢 Veinett åpent","🟡 Lokale stengninger","🔴 Kritiske brudd / Isolerte bygder"]
            n_vei = st.selectbox("Vei:", vei_valg, index=vei_valg.index(d['vei']))

        if st.button("💾 Lagre beredskapsstatus", type="primary"):
            lagre_data({"status":n_stat,"beskjed":n_besk,"leder":n_led,"vakt":n_vak,"kort":n_kort,"logg":n_logg,"ekom":n_ekom,"vei":n_vei})
            st.toast("✅ Lagret!", icon="💾"); st.rerun()

        # Vaktinstruks
        st.markdown("---")
        st.write("**📋 Instruks for aktivitet/vakt**")
        vp_aktiv = st.checkbox("✅ Aktiver vaktinstruks", value=vp.get("aktiv", False))
        vp1, vp2 = st.columns(2)
        with vp1:
            vp_sted      = st.text_input("📍 Sted", value=vp.get("sted",""))
            vp_lagleder  = st.text_input("👷 Lagleder", value=vp.get("lagleder",""))
            vp_talegruppe= st.text_input("📻 Talegruppe", value=vp.get("talegruppe",""))
            vp_legevakt  = st.text_input("🏥 Legevakt", value=vp.get("legevakt",""))
            vp_sykehus   = st.text_input("🏨 Sykehus", value=vp.get("sykehus",""))
        with vp2:
            vp_tid_fra   = st.text_input("🕐 Tid fra", value=vp.get("tid_fra",""), placeholder="08:00")
            vp_tid_til   = st.text_input("🕑 Tid til", value=vp.get("tid_til",""), placeholder="16:00")
            rig_p = beregn_rig_tid(vp_tid_fra)
            if rig_p: st.caption(f"⏰ Ferdig rigget: **{rig_p}**")
            vp_mannskaper= st.text_area("👥 Mannskaper (ett per linje)", value=vp.get("mannskaper",""), height=100)
            vp_utstyr    = st.text_area("🎒 Utstyr (ett per linje)", value=vp.get("utstyr",""), height=100)
        vp_notat = st.text_area("📝 Notat", value=vp.get("notat",""), height=60)
        if st.button("💾 Lagre vaktinstruks", type="primary"):
            lagre_vaktplan({"aktiv":vp_aktiv,"sted":vp_sted,"lagleder":vp_lagleder,
                            "talegruppe":vp_talegruppe,"legevakt":vp_legevakt,"sykehus":vp_sykehus,
                            "tid_fra":vp_tid_fra,"tid_til":vp_tid_til,
                            "mannskaper":vp_mannskaper,"utstyr":vp_utstyr,"notat":vp_notat})
            st.toast("✅ Vaktinstruks lagret!", icon="📋"); st.rerun()

        # Avvik
        st.markdown("---")
        åpne   = [a for a in avvik_liste if not a.get("fulgt_opp")]
        lukkede= [a for a in avvik_liste if a.get("fulgt_opp")]
        st.write(f"**⚠️ Avvik – {len(åpne)} åpne / {len(lukkede)} lukket**")
        if not avvik_liste:
            st.caption("Ingen avvik registrert ennå.")
        else:
            avvik_endret = False
            for i, a in enumerate(avvik_liste):
                fulgt  = a.get("fulgt_opp", False)
                haster = a.get("umiddelbar_oppfolging", False) and not fulgt
                border = "#dc3545" if haster else ("#28a745" if fulgt else "#ffc107")
                bg_a   = "rgba(40,167,69,0.07)" if fulgt else ("rgba(220,53,69,0.07)" if haster else "rgba(255,193,7,0.07)")
                ikon   = "✅ Lukket" if fulgt else ("⚡ Akutt" if haster else "🟡 Åpen")
                st.markdown(f"""<div style='border-left:4px solid {border};background:{bg_a};
                border-radius:6px;padding:10px 14px;margin-bottom:6px;'>
                <b>{a.get('navn','–')}</b> · <small style='opacity:0.7;'>{a.get('registrert','')}</small> · <b>{ikon}</b><br>
                <span style='font-size:0.9rem;'>{a.get('hendelse','')}</span>
                {f"<br><small><i>{a.get('konsekvens','')}</i></small>" if a.get('konsekvens') else ""}
                {f"<br><small>📝 {a.get('oppfolging_notat','')}</small>" if a.get('oppfolging_notat') else ""}
                </div>""", unsafe_allow_html=True)
                if not fulgt:
                    ka, kb = st.columns([2,1])
                    with ka: notat = st.text_input("Notat", key=f"notat_{i}", placeholder="Tiltak / kommentar...", label_visibility="collapsed")
                    with kb:
                        if st.button("✅ Marker lukket", key=f"lukk_{i}", use_container_width=True):
                            avvik_liste[i]["fulgt_opp"] = True
                            avvik_liste[i]["oppfolging_notat"] = notat
                            avvik_endret = True
                else:
                    if st.button("↩️ Gjenåpne", key=f"aapne_{i}"):
                        avvik_liste[i]["fulgt_opp"] = False; avvik_endret = True
            if avvik_endret:
                lagre_liste(AVVIK_FIL, avvik_liste); st.rerun()

        # Deltakelser
        st.markdown("---")
        st.write("**📋 Registrerte deltakelser**")
        if deltakelse_liste:
            df_d = pd.DataFrame(deltakelse_liste)[["registrert","navn","oppdrag","tid_ut","tid_inn","utlegg_kr"]]
            df_d.columns = ["Tidspunkt","Navn","Oppdrag","Tid ut","Tid inn","Utlegg (kr)"]
            st.dataframe(df_d, use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen deltakelser registrert ennå.")

        # E-postkonfig
        st.markdown("---")
        st.write("**📧 E-postkonfigurasjon**")
        st.caption("Avvik sendes automatisk til oppgitt adresse.")
        ep1, ep2 = st.columns(2)
        with ep1:
            ep_server = st.text_input("SMTP-server",  value=epost_cfg.get("smtp_server",""), placeholder="smtp.gmail.com")
            ep_port   = st.text_input("Port",         value=epost_cfg.get("smtp_port","587"))
            ep_bruker = st.text_input("SMTP-bruker",  value=epost_cfg.get("smtp_bruker",""))
        with ep2:
            ep_passord= st.text_input("SMTP-passord", value=epost_cfg.get("smtp_passord",""), type="password")
            ep_fra    = st.text_input("Fra-adresse",  value=epost_cfg.get("fra",""))
            ep_til    = st.text_input("Send til",     value=epost_cfg.get("til",""))
        ec1, ec2 = st.columns(2)
        with ec1:
            if st.button("💾 Lagre e-postkonfig", use_container_width=True):
                lagre_epost_config({"smtp_server":ep_server,"smtp_port":ep_port,"smtp_bruker":ep_bruker,
                                    "smtp_passord":ep_passord,"fra":ep_fra,"til":ep_til})
                st.toast("✅ E-postkonfig lagret!", icon="📧"); st.rerun()
        with ec2:
            if st.button("📤 Send testmelding", use_container_width=True):
                test = {"registrert":datetime.now().strftime('%d.%m.%Y %H:%M'),"navn":"Test","epost":"",
                        "hendelse":"Testmelding fra NF Operativ Tavle.","konsekvens":"","umiddelbar_oppfolging":False}
                ok, m = send_avvik_epost(test, {"smtp_server":ep_server,"smtp_port":ep_port,
                    "smtp_bruker":ep_bruker,"smtp_passord":ep_passord,"fra":ep_fra,"til":ep_til})
                st.success(f"✅ {m}") if ok else st.error(m)

st.markdown(f"<div style='text-align:right;color:#aaa;'><small>Sist lastet: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</small></div>",
            unsafe_allow_html=True)
