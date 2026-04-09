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

# --- KONFIGURATION ---
st.set_page_config(page_title="Job Agent Pro - Gold Edition", page_icon="🚀", layout="wide")
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

def clean_ai_text(text):
    """Fjerner hilsner og sikrer ren brødtekst."""
    if not text: return ""
    # Fjern JSON-rester hvis AI fejler
    text = re.sub(r'["{}]', '', text) if "ansogning" not in text else text
    lines = text.split('\n')
    bad_starts = ['kære', 'med venlig hilsen', 'venlig hilsen', 'mvh', 'hilsen', 'til ', 'emne:', 'vedrør:']
    cleaned = [l for l in lines if not any(l.lower().strip().startswith(bw) for bw in bad_starts)]
    return '\n'.join(cleaned).strip()

def fill_docx(template, content, headline, company, title, contact):
    """Ekstremt robust Word-fletning."""
    try:
        if not content: return None
        template.seek(0)
        doc = Document(template)
        
        # Sikr at alt er tekst
        clean_content = str(content)
        clean_headline = str(headline).strip().upper()
        
        replacements = {
            "{{VIRKSOMHED}}": str(company),
            "{{JOBTITEL}}": str(title),
            "{{KONTAKTPERSON}}": str(contact),
            "{{OVERSKRIFT}}": clean_headline,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }

        for p in doc.paragraphs:
            # Erstat placeholders i eksisterende linjer
            for key, val in replacements.items():
                if key in p.text:
                    p.text = p.text.replace(key, val)
            
            # Indsæt ansøgning med korrekt afsnitsdeling
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                parent = p._element.getparent()
                # Split tekst ved linjeskift og lav nye afsnit
                for line in clean_content.split('\n'):
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

# --- APP LOGIK ---
if 'step' not in st.session_state: st.session_state.step = 1

st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Upload & Info")
    cv_file = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    docx_file = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhed")
    titl = c2.text_input("Stilling")
    cont = st.text_input("Kontaktperson")
    
    if st.button("Næste →") and cv_file and comp:
        st.session_state.cv_text = extract_pdf_text(cv_file)
        st.session_state.temp = docx_file
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = cont
        st.session_state.step = 2
        st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobopslag")
    opslag_input = st.text_area("Indsæt jobteksten her", height=300)
    if st.button("Næste →") and opslag_input:
        st.session_state.opslag = opslag_input
        st.session_state.step = 3
        st.rerun()

elif st.session_state.step == 3:
    st.header("3. Indstillinger")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone", ["Professionel & Seriøs", "Personlig & Varm", "Kreativ & Modig"])
    length = c2.select_slider("Længde", ["Kort", "Standard", "Uddybende"], value="Standard")
    mot_pos = st.radio("Hvor skal motivationen stå?", ["I starten (fang dem med det samme)", "I slutningen (byg op til det)"])
    
    if st.button("Generér min ansøgning ✨"):
        st.session_state.p = {"tone": tone, "length": length, "mot": mot_pos}
        st.session_state.step = 4
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver en dybdegående ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                
                # Kraftfuld prompt for at undgå korte svar
                prompt = f"""
                Du er en elite-rekrutteringskonsulent. Skriv en fyldig, overbevisende og professionel ansøgning på dansk.
                
                KRAV TIL VOLUMEN:
                - Hvis længden er 'Standard' eller 'Uddybende', SKAL du skrive mindst 400-600 ord.
                - Brug mindst 4-5 tydelige afsnit med dobbelt linjeskift.
                - Motivationen SKAL placeres: {st.session_state.p['mot']}.
                
                STRUKTUR:
                - Ingen hilsner eller 'Med venlig hilsen'.
                - Gå direkte til substansen.
                - Brug data fra CV: {st.session_state.cv_text[:2000]}
                - Match med Job: {st.session_state.opslag[:2000]}
                
                SVAR KUN I JSON FORMAT:
                {{
                  "overskrift": "En fængende overskrift",
                  "ansogning": "Her skriver du den lange tekst med afsnit...",
                  "pitch": "LinkedIn pitch",
                  "interview": "#### ❓ Spørgsmål\\n**Svar:** ..."
                }}
                """
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er en professionel tekstforfatter. Svar altid i JSON."},
                              {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
                
                res = json.loads(response.choices[0].message.content)
                res['ansogning'] = clean_ai_text(res['ansogning'])
                st.session_state.final_res = res
                
                # Gem i arkiv
                conn = sqlite3.connect(db_path)
                conn.execute("INSERT INTO archive (date, company, title, ansogning, opslag) VALUES (?,?,?,?,?)",
                             (get_danish_time(), st.session_state.comp, st.session_state.titl, res['ansogning'], st.session_state.opslag))
                conn.commit()
                conn.close()
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        st.subheader(res.get('overskrift'))
        st.write(res.get('ansogning'))
        
        if st.session_state.temp:
            doc_file = fill_docx(st.session_state.temp, res.get('ansogning'), res.get('overskrift'), 
                                st.session_state.comp, st.session_state.titl, st.session_state.contact)
            if doc_file:
                st.download_button("Hent som Word (.docx) 📄", doc_file, f"Ansogning_{st.session_state.comp}.docx")
        
        st.divider()
        st.subheader("LinkedIn & Interview")
        st.info(res.get('pitch'))
        st.markdown(res.get('interview'))
        
        if st.button("Start forfra 🔄"):
            for key in ['final_res', 'cv_text', 'opslag', 'comp']:
                if key in st.session_state: del st.session_state[key]
            st.session_state.step = 1
            st.rerun()
