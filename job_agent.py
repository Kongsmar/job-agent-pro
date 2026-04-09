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

# --- 1. KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Stabil Version", page_icon="🚀", layout="wide")
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

# --- 2. HJÆLPEFUNKTIONER ---
def get_danish_time():
    return (datetime.utcnow() + timedelta(hours=2)).strftime("%d. %m. %Y, %H:%M")

def extract_pdf_text(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: return ""

def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        for s in soup(["script", "style"]): s.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return "Kunne ikke hente tekst."

def clean_ai_text(text):
    if not text: return ""
    lines = text.split('\n')
    bad_starts = ['kære', 'med venlig hilsen', 'venlig hilsen', 'mvh', 'hilsen', 'til ', 'emne:', 'vedrør:']
    cleaned = [l for l in lines if not any(l.lower().strip().startswith(bw) for bw in bad_starts)]
    return '\n'.join(cleaned).strip()

def fill_docx(template, content, headline, company, title, contact):
    try:
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
            for key, val in replacements.items():
                if key in p.text:
                    p.text = p.text.replace(key, val)
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                for line in str(content).split('\n'):
                    if line.strip():
                        new_p = doc.add_paragraph(line.strip(), style=p.style)
                        p._element.addnext(new_p._element)
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except Exception as e:
        st.error(f"Word-fejl: {e}")
        return None

# --- 3. APP FLOW ---
if 'step' not in st.session_state: st.session_state.step = 1

st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

# STEP 1: GRUNDLAG
if st.session_state.step == 1:
    st.header("1. Grundlag")
    cv_f = st.file_uploader("Upload CV (PDF)", type="pdf")
    docx_f = st.file_uploader("Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    st.session_state.comp = c1.text_input("Virksomhed", value=st.session_state.get('comp', ""))
    st.session_state.titl = c2.text_input("Stilling", value=st.session_state.get('titl', ""))
    st.session_state.contact = st.text_input("Kontaktperson", value=st.session_state.get('contact', ""))
    if st.button("Næste →") and cv_f and st.session_state.comp:
        st.session_state.cv_text = extract_pdf_text(cv_f)
        st.session_state.temp = docx_f
        st.session_state.step = 2
        st.rerun()

# STEP 2: JOBOPSLAG (INKL LINK)
elif st.session_state.step == 2:
    st.header("2. Jobopslaget")
    col1, col2 = st.columns([3, 1])
    url = col1.text_input("Indsæt link:")
    if col2.button("Hent tekst"):
        st.session_state.fetched_txt = get_text_from_url(url)
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=300)
    if st.button("Næste →") and opslag:
        st.session_state.opslag = opslag
        st.session_state.step = 3
        st.rerun()

# STEP 3: STRATEGI
elif st.session_state.step == 3:
    st.header("3. Strategi & Valg")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone", ["Professionel", "Personlig", "Kreativ"])
    h_type = c2.selectbox("Overskrift", ["Værdiskabende", "Catchy", "Formel"])
    length = st.select_slider("Længde", ["Kort", "Standard", "Uddybende"], value="Standard")
    mot = st.radio("Motivation", ["I starten", "I slutningen"], horizontal=True)
    if st.button("Generér ✨"):
        st.session_state.p = {"tone": tone, "length": length, "mot": mot, "h_type": h_type}
        st.session_state.step = 4
        st.rerun()

# STEP 4: RESULTAT
elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                prompt = f"Skriv en dansk ansøgning som JSON. Længde: {p['length']}, Tone: {p['tone']}, Overskrift: {p['h_type']}, Motivation: {p['mot']}. Ingen hilsner. CV: {st.session_state.cv_text[:2000]} Job: {st.session_state.opslag[:2000]}"
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Svar kun i JSON: {\"overskrift\":\"\",\"ansogning\":\"\",\"pitch\":\"\",\"interview\":\"\"}"}, {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                res = json.loads(resp.choices[0].message.content)
                res['ansogning'] = clean_ai_text(res['ansogning'])
                st.session_state.final_res = res
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
            doc = fill_docx(st.session_state.temp, res.get('ansogning'), res.get('overskrift'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
            st.download_button("Hent Word 📄", doc, f"Ansogning_{st.session_state.comp}.docx")
        st.divider()
        st.info(res.get('pitch'))
        st.markdown(res.get('interview'))
        if st.button("Start forfra"):
            for k in ['final_res', 'fetched_txt']: 
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
        with st.expander(f"{row['company']} - {row['title']} ({row['date']})"):
            st.write(row['ansogning'])
            st.download_button("Hent ansøgning", row['ansogning'], f"A_{i}.txt", key=f"a_{i}")
            st.download_button("Hent opslag", row['opslag'], f"J_{i}.txt", key=f"j_{i}")
