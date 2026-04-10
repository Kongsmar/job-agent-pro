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

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent - Ansøgnings Pro", page_icon="📝", layout="wide")
db_path = "job_agent_arkiv.db"

def get_danish_time():
    return (datetime.utcnow() + timedelta(hours=2)).strftime("%d. %m. %Y, %H:%M")

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

def fill_docx(template, replacements):
    try:
        template.seek(0)
        doc = Document(template)
        for p in doc.paragraphs:
            for tag, content in replacements.items():
                if tag in p.text:
                    p.text = p.text.replace(tag, str(content))
        
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for tag, content in replacements.items():
                            if tag in p.text:
                                p.text = p.text.replace(tag, str(content))
        
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- APP FLOW ---
st.title("📝 Job Agent - Ansøgnings Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv_file = st.file_uploader("Upload dit CV (PDF) som reference", type="pdf")
    temp_ans = st.file_uploader("Upload din Word-skabelon (Ansøgning)", type="docx")
    
    col1, col2 = st.columns(2)
    comp = col1.text_input("Virksomhed:")
    titl = col2.text_input("Stilling:")
    contact = st.text_input("Kontaktperson (Navn):")
    
    if st.button("Næste →", disabled=not (cv_file and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv_file)
        st.session_state.temp_ans = temp_ans
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.contact = contact
        next_step(); st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobbet")
    url = st.text_input("Link til jobopslag:")
    if st.button("Hent tekst") and url:
        txt = get_text_from_url(url)
        if txt: st.session_state.fetched_txt = txt
    
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=300)
    noter = st.text_area("Hvad skal AI'en særligt lægge vægt på?")
    
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step(); st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi & Tone")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = c2.select_slider("Længde på ansøgningen:", ["Kort", "Standard", "Uddybende"], "Standard")
    
    h_type = c1.selectbox("Overskriftstype:", ["Værdiskabende", "Formel", "Catchy", "Spørgende"])
    strat = c2.selectbox("Strategisk vinkel:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    
    mot_pos = st.radio("Motivationens placering:", ["I starten (krogen)", "I bunden (opsamlingen)"], horizontal=True)
    
    if st.button("Generér Ansøgning ✨"):
        st.session_state.p = {"tone": tone, "len": length, "h_type": h_type, "strat": strat, "mot_pos": mot_pos}
        next_step(); st.rerun()

elif st.session_state.step == 4:
    st.header("4. Din færdige ansøgning")
    if "final_res" not in st.session_state:
        with st.spinner("Analyserer match og skriver din ansøgning..."):
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            p = st.session_state.p
            
            # ATS Match Analyse
            ats_p = f"Giv en Match Score i % og en kort professionel analyse af styrker og mangler.\nJob: {st.session_state.opslag}\nCV: {st.session_state.cv_text}"
            ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
            st.session_state.ats_result = ats_resp.choices[0].message.content

            # Ansøgningsgenerering
            kontakt = st.session_state.contact if st.session_state.contact else "Ansættelsesudvalget"
            main_prompt = f"""
            Lav en JSON pakke på dansk. Svar KUN med JSON.
            'ansogning': Skriv en komplet ansøgning adresseret til {kontakt}. Længde: {p['len']}. Tone: {p['tone']}. Strategi: {p['strat']}. Motivation skal være {p['mot_pos']}.
            'overskrift': Lav en overskrift af typen {p['h_type']}.
            'interview': 3 relevante spørgsmål og svar til samtalen. Brug #### til overskrifter og god luft mellem afsnit.
            
            DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, NOTER: {st.session_state.noter}
            """
            
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "Du er elite-rekrutteringskonsulent. Svar KUN i JSON format."}, {"role": "user", "content": main_prompt}],
                response_format={"type": "json_object"}
            )
            st.session_state.final_res = json.loads(resp.choices[0].message.content)

            # Arkiv
            conn = sqlite3.connect(db_path); c = conn.cursor()
            c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                      (get_danish_time(), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
            conn.commit(); conn.close()

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        st.subheader("📊 Match & Analyse")
        st.info(st.session_state.ats_result)
        
        col_main, col_side = st.columns([2, 1])
        with col_main:
            st.subheader("📄 Ansøgning")
            st.markdown(f"**{res.get('overskrift')}**")
            st.write(res.get('ansogning'))
            
            if st.session_state.temp_ans:
                replacements = {
                    "{{ANSOGNING}}": res.get('ansogning'),
                    "{{OVERSKRIFT}}": res.get('overskrift'),
                    "{{VIRKSOMHED}}": st.session_state.comp,
                    "{{JOBTITEL}}": st.session_state.titl,
                    "{{KONTAKTPERSON}}": st.session_state.contact if st.session_state.contact else "Ansættelsesudvalget",
                    "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
                }
                doc = fill_docx(st.session_state.temp_ans, replacements)
                st.download_button("Hent Ansøgning (.docx)", doc, f"Ansøgning_{st.session_state.comp}.docx")

        with col_side:
            st.subheader("🎤 Interviewforberedelse")
            st.markdown(res.get('interview'))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()
