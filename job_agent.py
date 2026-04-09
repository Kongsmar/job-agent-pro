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
        template.seek(0)
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
                if k in p.text: p.text = p.text.replace(k, str(v))
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for k, v in data.items():
                            if k in p.text: p.text = p.text.replace(k, str(v))
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- APP FLOW ---
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:")
    titl = c2.text_input("Hvilken stilling søger du?")
    contact = st.text_input("Kontaktperson (f.eks. Mette Jensen):")
    if st.button("Fortsæt →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = contact
        next_step()
        st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobbet")
    url = st.text_input("Link til jobopslag:")
    if st.button("Hent tekst") and url:
        txt = get_text_from_url(url)
        if txt: st.session_state.fetched_txt = txt
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=250)
    noter = st.text_area("Noter:")
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Toneleje:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = c2.select_slider("Længde:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mirror = st.toggle("Spejl sprogbrug", True)
    motivation = st.radio("Motivationens placering:", ["I starten", "I bunden"])
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mirror": mirror, "mot": motivation}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skaber magien..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # Samlet system-prompt for at sikre alle 3 dele genereres
                sys_msg = "Du er en karriererådgiver. Svar i JSON-format med nøglerne: 'ansogning', 'pitch', 'interview'."
                
                prompt = f"""
                Lav en komplet pakke til jobbet som {st.session_state.titl}.
                
                1. ANSØGNING (Nøgle: 'ansogning'):
                Skriv KUN de midterste afsnit (brødteksten). 
                - Start direkte med første afsnit.
                - INGEN hilsen (Kære/Hej), INGEN 'Att:', INGEN afslutning (Med venlig hilsen/navn). 
                - Tone: {p['tone']}, Fokus: {p['fokus']}, Indledning: {p['strat']}.
                
                2. LINKEDIN PITCH (Nøgle: 'pitch'):
                Skriv en kort, fængende besked på 3-4 sætninger til en rekrutteringsansvarlig.
                
                3. INTERVIEW PREP (Nøgle: 'interview'):
                Find de 3 mest kritiske spørgsmål baseret på jobopslag vs. CV.
                
                DATA:
                CV: {st.session_state.cv_text[:3000]}
                Job: {st.session_state.opslag[:3000]}
                Noter: {st.session_state.noter}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
                
                # Arkivering
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
                
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        c_main, c_side = st.columns([2, 1])
        with c_main:
            st.subheader("📝 Brødtekst til Word")
            st.write(res.get('ansogning', 'Kunne ikke generere ansøgning'))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
                if doc: st.download_button("Hent Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_side:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch', 'Ingen pitch genereret'))
            st.subheader("🎤 Interview Prep")
            st.warning(res.get('interview', 'Ingen spørgsmål genereret'))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
with st.expander("📂 Arkiv"):
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
        for _, r in df.iterrows():
            with st.expander(f"📌 {r['company']} - {r['title']} ({r['date']})"):
                st.write(r['ansogning'])
