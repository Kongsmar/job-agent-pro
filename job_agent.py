import streamlit as st
from openai import OpenAI
import io
import os
import sqlite3
import pandas as pd
from datetime import datetime
from docx import Document
from PyPDF2 import PdfReader
import json

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Guided", page_icon="🚀", layout="centered")
db_path = "job_agent_arkiv.db"

def init_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, company TEXT, title TEXT, 
                  ansogning TEXT, opslag TEXT, tone TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- SESSION STATE (HUSKER DINE TRIN) ---
if 'step' not in st.session_state: st.session_state.step = 1
def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1
def reset(): st.session_state.step = 1

# --- HJÆLPEFUNKTIONER ---
def extract_pdf(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def fill_docx(template, content, company, title):
    try:
        doc = Document(template)
        data = {"{{ANSOGNING}}": content, "{{VIRKSOMHED}}": company, "{{JOBTITEL}}": title, "{{DATO}}": datetime.now().strftime("%d. %m. %Y")}
        for p in doc.paragraphs:
            for k, v in data.items():
                if k in p.text: p.text = p.text.replace(k, v)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- APP NAVIGATION ---
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

# --- TRIN 1: FILER & BASIS ---
if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhed:")
    titl = c2.text_input("Jobtitel:")
    
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.comp = comp
        st.session_state.titl = titl
        next_step()
        st.rerun()

# --- TRIN 2: OPSLAG & NOTER ---
elif st.session_state.step == 2:
    st.header("2. Jobbet")
    opslag = st.text_area("Indsæt jobopslaget her:", height=250)
    noter = st.text_area("Personlige noter (Valgfrit):", placeholder="Noget AI'en skal fremhæve?", height=100)
    
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

# --- TRIN 3: STRATEGI ---
elif st.session_state.step == 3:
    st.header("3. Strategi")
    t1, t2 = st.columns(2)
    tone = t1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = t2.select_slider("Længde:", ["Kort", "Standard", "Uddybende"], "Standard")
    
    strat = st.selectbox("Strategi:", ["Direkte", "Værdi-baseret", "Problemknuser", "Motiveret"])
    fokus = st.radio("Hovedfokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    
    st.divider()
    c1, c2, c3 = st.columns(3)
    pitch = c1.toggle("LinkedIn Pitch", True)
    prep = c2.toggle("Interview Prep", True)
    mirror = c3.toggle("Spejl sprog", True)

    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generer nu ✨"):
        st.session_state.params = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "pitch": pitch, "prep": prep, "mirror": mirror}
        next_step()
        st.rerun()

# --- TRIN 4: RESULTAT ---
elif st.session_state.step == 4:
    st.header("4. Resultat")
    with st.spinner("AI-agenten analyserer og skriver..."):
        try:
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            p = st.session_state.params
            prompt = f"""Lav pakke for {st.session_state.titl} hos {st.session_state.comp}.
            Ansøgning: Tone {p['tone']}, Længde {p['len']}, Strategi {p['strat']}, Fokus {p['fokus']}.
            LinkedIn Pitch & Interview Prep: Ja. Noter: {st.session_state.noter}.
            CV: {st.session_state.cv_text[:3000]}. Job: {st.session_state.opslag[:3000]}."""
            
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "Svar i JSON: {'ansogning': '...', 'pitch': '...', 'interview': '...'}"}],
                response_format={"type": "json_object"}
            )
            res = json.loads(resp.choices[0].message.content)
            
            # Gem i arkiv
            conn = sqlite3.connect(db_path); c = conn.cursor()
            c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                      (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.comp, st.session_state.titl, res['ansogning'], st.session_state.opslag, p['tone']))
            conn.commit(); conn.close()

            st.success("Ansøgning genereret og gemt!")
            st.subheader("📝 Ansøgning")
            st.write(res['ansogning'])
            
            if st.session_state.temp:
                w_file = fill_docx(st.session_state.temp, res['ansogning'], st.session_state.comp, st.session_state.titl)
                st.download_button("Hent Word-fil 📄", w_file, f"Ansøgning_{st.session_state.comp}.docx")
            
            ca, cb = st.columns(2)
            if p['pitch']: ca.info("**LinkedIn Pitch:**\n" + res['pitch'])
            if p['prep']: cb.warning("**Interview Prep:**\n" + res['interview'])

        except Exception as e:
            st.error(f"Fejl: {e}")
    
    if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV SEKTION (Nu med fuldt jobopslag) ---
st.divider()
st.header("📂 Arkiv")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    conn.close()
    
    if df.empty:
        st.info("Arkivet er tomt.")
    else:
        for _, r in df.iterrows():
            with st.expander(f"📌 {r['company']} - {r['title']} ({r['date']})"):
                col_ans, col_ops = st.columns(2)
                with col_ans:
                    st.subheader("Din Ansøgning")
                    st.write(r['ansogning'])
                    st.download_button("Hent som tekst", r['ansogning'], f"Ansøgning_{r['company']}_{r['id']}.txt", key=f"ans_{r['id']}")
                with col_ops:
                    st.subheader("Oprindeligt Jobopslag")
                    st.write(r['opslag'])
