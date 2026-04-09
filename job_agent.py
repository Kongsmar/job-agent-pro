import streamlit as st
from openai import OpenAI
import io
import os
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from docx import Document
from PyPDF2 import PdfReader
import json

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Master Guided", page_icon="🚀", layout="wide")
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

# --- SESSION STATE ---
if 'step' not in st.session_state: st.session_state.step = 1
def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step -= 1
def reset(): 
    for key in list(st.session_state.keys()): del st.session_state[key]
    st.session_state.step = 1

# --- HJÆLPEFUNKTIONER ---
def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return ""

def extract_pdf(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def fill_docx(template, content, company, title, contact_person):
    try:
        doc = Document(template)
        data = {
            "{{ANSOGNING}}": content, 
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        for p in doc.paragraphs:
            for k, v in data.items():
                if k in p.text: p.text = p.text.replace(k, v)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- APP FLOW ---
st.title("💼 Job Agent Pro - Master Edition")
st.progress(st.session_state.step / 4)

# --- TRIN 1: FUNDAMENT ---
if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:")
    titl = c2.text_input("Hvilken stilling søger du?")
    
    contact = st.text_input("Kontaktperson (f.eks. 'Mette Jensen' eller 'Ansættelsesudvalget'):", placeholder="Hvem skal ansøgningen stiles til?")
    
    if st.button("Fortsæt til jobopslag →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = contact
        next_step()
        st.rerun()

# --- TRIN 2: JOBOPSLAGET ---
elif st.session_state.step == 2:
    st.header("2. Jobbet")
    url = st.text_input("Link til jobopslag (valgfrit):")
    if st.button("Hent tekst fra link") and url:
        txt = get_text_from_url(url)
        if txt: st.session_state.fetched_txt = txt
    
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=250)
    noter = st.text_area("Dine personlige noter/guldkorn til AI'en:", placeholder="F.eks. Jeg har brugt system X i 4 år...")
    
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

# --- TRIN 3: STRATEGI ---
elif st.session_state.step == 3:
    st.header("3. Din Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Toneleje:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = c2.select_slider("Længde på ansøgning:", ["Kort", "Standard", "Uddybende"], "Standard")
    
    s1, s2 = st.columns(2)
    strat = s1.selectbox("Indlednings-strategi:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = s2.radio("Hovedfokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    
    st.divider()
    m1, m2 = st.columns(2)
    mirror = m1.toggle("Spejl virksomhedens sprogbrug", True)
    motivation = m2.radio("Motivationens placering:", ["I starten (Krogen)", "I bunden (Opsamlingen)"])

    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Analysér & Generér ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mirror": mirror, "mot": motivation}
        next_step()
        st.rerun()

# --- TRIN 4: ANALYSE & RESULTAT ---
elif st.session_state.step == 4:
    st.header("4. Din færdige job-pakke")
    
    if "final_res" not in st.session_state:
        with st.spinner("Kører ATS-analyse og skriver ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                
                # ATS ANALYSE
                analysis_prompt = f"Analysér jobopslag mod CV. Find top 3 nøgleord og 1 kritisk gap.\nJob: {st.session_state.opslag[:2000]}\nCV: {st.session_state.cv_text[:2000]}"
                analysis_res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                ats_info = analysis_res.choices[0].message.content
                
                # HOVEDGENERERING
                p = st.session_state.p
                main_prompt = f"""
                Du er en ekspert i rekruttering. Skriv en målrettet ansøgning til {st.session_state.titl} hos {st.session_state.comp}.
                
                STIL:
                - Kontaktperson: {st.session_state.contact} (Stil ansøgningen direkte til denne person).
                - Tone: {p['tone']}
                - Længde: {p['len']}
                - Strategi: {p['strat']}
                - Fokus: {p['fokus']}
                - Motivation: {p['mot']}
                
                KONTEKST:
                - ATS Analyse: {ats_info}
                - Personlige noter: {st.session_state.noter}
                - CV: {st.session_state.cv_text}
                - Jobopslag: {st.session_state.opslag}
                
                REGLER:
                - Start med en professionel hilsen til {st.session_state.contact}.
                - Skriv en fyldestgørende ansøgning.
                - Ingen afsenderinfo i toppen.
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": "Svar i JSON format med nøglerne: 'ansogning', 'pitch', 'interview'."},
                              {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
                st.session_state.ats_info = ats_info
                
                # Gem i arkiv
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
                
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        st.info(f"📊 **ATS Analyse:** {st.session_state.ats_info}")
        
        col_main, col_side = st.columns([2, 1])
        with col_main:
            st.subheader("📝 Ansøgning")
            st.write(st.session_state.final_res['ansogning'])
            if st.session_state.temp:
                doc_file = fill_docx(st.session_state.temp, st.session_state.final_res['ansogning'], st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil 📄", doc_file, f"Ansøgning_{st.session_state.comp}.docx")
        
        with col_side:
            st.subheader("✉️ LinkedIn & Samtale")
            st.success("**Pitch:**\n" + st.session_state.final_res['pitch'])
            st.warning("**Interview Prep:**\n" + st.session_state.final_res['interview'])
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
with st.expander("📂 Se Arkiv"):
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
        for _, r in df.iterrows():
            with st.expander(f"📌 {r['company']} - {r['title']} ({r['date']})"):
                c1, c2 = st.columns(2)
                c1.write("**Ansøgning:**"); c1.write(r['ansogning'])
                c2.write("**Jobopslag:**"); c2.write(r['opslag'])
