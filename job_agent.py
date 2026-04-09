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
    noter = st.text_area("Hvad skal AI'en vide? (Noter):")
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
    length = st.select_slider("Ønsket omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mirror = st.toggle("Spejl sprogbrug", True)
    motivation = st.radio("Motivationens placering:", ["I starten", "I bunden"])
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér Komplet Pakke ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mirror": mirror, "mot": motivation}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Dit Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver en gennemarbejdet ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # Instruktioner der sikrer længde og dybde
                length_instruction = "Skriv ca. 450-600 ord fordelt på 4-5 afsnit." if p['len'] == "Standard" else "Skriv ca. 250-350 ord." if p['len'] == "Kort" else "Skriv ca. 700-800 ord med stor detaljegrad."
                
                prompt = f"""
                Du er en elite-rekrutteringskonsulent. Skriv en overbevisende og substantiel ansøgning til jobbet som {st.session_state.titl}.
                
                ANSØGNING (Nøgle: 'ansogning'):
                - OMFANG: {length_instruction}
                - STRUKTUR: Skriv KUN brødteksten. Start direkte med første afsnit. Ingen 'Kære...', ingen 'Med venlig hilsen'.
                - INDHOLD: Du SKAL uddybe specifikke erfaringer fra CV'et og koble dem direkte til kravene i jobopslaget. Gør det konkret.
                - STRATEGI: {p['strat']}. Fokusér på {p['fokus']}. Placér motivationen {p['mot']}.
                
                PITCH (Nøgle: 'pitch'):
                En stærk LinkedIn-besked.
                
                INTERVIEW (Nøgle: 'interview'):
                De 3 sværeste spørgsmål rekrutteringschefen vil stille baseret på CV/Opslag.
                
                DATA:
                CV: {st.session_state.cv_text[:4000]}
                JOB: {st.session_state.opslag[:4000]}
                NOTER: {st.session_state.noter}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o", # Bruger gpt-4o for højere kvalitet i tekst
                    messages=[{"role": "system", "content": "Svar i JSON: {'ansogning': '...', 'pitch': '...', 'interview': '...'}"}, {"role": "user", "content": prompt}],
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
            st.subheader("📝 Genereret Brødtekst")
            st.write(res.get('ansogning'))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent færdig Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_side:
            st.subheader("✉️ LinkedIn Pitch")
            st.info(res.get('pitch'))
            st.subheader("🎤 Interview Forberedelse")
            st.warning(res.get('interview'))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
with st.expander("📂 Arkiv"):
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
        for _, r in df.iterrows():
            with st.expander(f"📌 {r['company']} - {r['title']} ({r['date']})"):
                st.write(r['ansogning'])
