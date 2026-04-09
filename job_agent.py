import streamlit as st
from openai import OpenAI
import io
import os
import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from docx import Document
from PyPDF2 import PdfReader
import json
import urllib.parse
import re

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Full Master", page_icon="🚀", layout="wide")
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

# --- HJÆLPEFUNKTIONER ---
def get_danish_time():
    return (datetime.utcnow() + timedelta(hours=2)).strftime("%d. %m. %Y, %H:%M")

def extract_pdf_text(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return "Kunne ikke hente tekst fra linket."

def clean_ai_text(text):
    if not text: return ""
    lines = text.split('\n')
    bad_starts = ['kære', 'med venlig hilsen', 'venlig hilsen', 'mvh', 'hilsen', 'til ', 'emne:', 'vedrør:']
    cleaned = [l for l in lines if not any(l.lower().strip().startswith(bw) for bw in bad_starts)]
    return '\n'.join(cleaned).strip()

def fill_docx(template, content, headline, company, title, contact):
    try:
        if not content: return None
        template.seek(0)
        doc = Document(template)
        
        replacements = {
            "{{VIRKSOMHED}}": str(company),
            "{{JOBTITEL}}": str(title),
            "{{KONTAKTPERSON}}": str(contact),
            "{{OVERSKRIFT}}": str(headline).upper(),
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }

        for p in doc.paragraphs:
            # Erstat tags i eksisterende linjer
            for key, val in replacements.items():
                if key in p.text:
                    p.text = p.text.replace(key, val)
            
            # Indsæt ansøgning ved placeholder
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                for line in str(content).split('\n'):
                    if line.strip():
                        new_p = doc.add_paragraph(line.strip(), style=p.style)
                        p._element.addnext(new_p._element)
        
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        st.error(f"Word Fejl: {e}")
        return None

# --- APP FLOW ---
if 'step' not in st.session_state: st.session_state.step = 1

st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

# STEP 1: CV OG SKABELON
if st.session_state.step == 1:
    st.header("1. Grundlag")
    cv_file = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    docx_file = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    st.session_state.comp = c1.text_input("Virksomhed", value=st.session_state.get('comp', ""))
    st.session_state.titl = c2.text_input("Stilling", value=st.session_state.get('titl', ""))
    st.session_state.contact = st.text_input("Kontaktperson", value=st.session_state.get('contact', ""))
    
    if st.button("Næste →") and cv_file and st.session_state.comp:
        st.session_state.cv_text = extract_pdf_text(cv_file)
        st.session_state.temp = docx_file
        st.session_state.step = 2
        st.rerun()

# STEP 2: JOBOPSLAG OG LINK-SCRAPER
elif st.session_state.step == 2:
    st.header("2. Jobopslaget")
    col_l1, col_l2 = st.columns([3, 1])
    job_url = col_l1.text_input("Indsæt link til jobopslag:")
    if col_l2.button("Hent tekst 📥"):
        if job_url:
            st.session_state.fetched_txt = get_text_from_url(job_url)
    
    opslag_final = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=300)
    
    c_back, c_next = st.columns(2)
    if c_back.button("← Tilbage"): st.session_state.step = 1; st.rerun()
    if c_next.button("Næste →") and opslag_final:
        st.session_state.opslag = opslag_final
        st.session_state.step = 3
        st.rerun()

# STEP 3: STRATEGI, LÆNGDE OG OVERSKRIFT
elif st.session_state.step == 3:
    st.header("3. Strategi & Valg")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone", ["Professionel & Seriøs", "Personlig & Varm", "Kreativ & Modig"])
    head_type = c2.selectbox("Overskriftstype", ["Værdiskabende", "Catchy", "Formel", "Spørgende"])
    
    length = st.select_slider("Længde på ansøgning", ["Kort", "Standard", "Uddybende"], value="Standard")
    mot = st.radio("Motivationens placering", ["I starten", "I slutningen"], horizontal=True)
    
    if st.button("Generér min ansøgning ✨"):
        st.session_state.p = {"tone": tone, "length": length, "mot": mot, "head_type": head_type}
        st.session_state.step = 4
        st.rerun()

# STEP 4: RESULTAT
elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver en stærk ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                prompt = f"""
                Skriv en DYBDEGÅENDE dansk ansøgning som JSON. 
                VIGTIGT: Skriv mindst 5-6 fyldige afsnit hvis 'Standard' eller 'Uddybende'. 
                Overskriftstype: {p['head_type']}.
                Regler: Ingen hilsner (Kære/Hilsen). Ingen flettekoder. 
                Motivation: {p['mot']}. Tone: {p['tone']}.
                Format: {{ "overskrift": "...", "ansogning": "...", "pitch": "...", "interview": "..." }}
                CV: {st.session_state.cv_text[:2000]} | Job: {st.session_state.opslag[:2000]}
                """
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er elite-tekstforfatter. Svar kun i JSON."},
                              {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                res = json.loads(resp.choices[0].message.content)
                res['ansogning'] = clean_ai_text(res['ansogning'])
                st.session_state.final_res = res
                
                # Arkivér
                conn = sqlite3.connect(db_path)
                conn.execute("INSERT INTO archive (date, company, title, ansogning, opslag) VALUES (?,?,?,?,?)",
                             (get_danish_time(), st.session_state.comp, st.session_state.titl, res['ansogning'], st.session_state.opslag))
                conn.commit(); conn.close()
            except Exception as e: st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        st.subheader(res.get('overskrift'))
        st.write(res.get('ansogning'))
        
        if st.session_state.temp:
            doc = fill_docx(st.session_state.temp, res.get('ansogning'), res.get('overskrift'), 
                            st.session_state.comp, st.session_state.titl, st.session_state.contact)
            if doc: st.download_button("Hent Word (.docx) 📄", doc, f"Ansogning_{st.session_state.comp}.docx")
        
        st.divider()
        st.subheader("LinkedIn & Interview")
        st.info(res.get('pitch'))
        st.markdown(res.get('interview'))
        
        if st.button("Start forfra 🔄"):
            for k in ['final_res', 'fetched_txt', 'opslag']: 
                if k in st.session_state: del st.session_state[k]
            st.session_state.step = 1; st.rerun()

# ARKIV
st.divider()
st.subheader("📂 Arkiv")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC LIMIT 5", conn)
    conn.close()
    for i, row in df.iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
            st.write(row['ansogning'])
