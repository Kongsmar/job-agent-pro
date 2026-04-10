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
st.set_page_config(page_title="Job Agent Pro - Master Suite", page_icon="🚀", layout="wide")
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
        text = "".join([p.extract_text() for p in reader.pages])
        return text
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
st.title("💼 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv_file = st.file_uploader("Upload Master-CV (PDF)", type="pdf")
    col_t1, col_t2 = st.columns(2)
    temp_ans = col_t1.file_uploader("Skabelon: Ansøgning", type="docx")
    temp_cv = col_t2.file_uploader("Skabelon: CV", type="docx")
    c1, c2, c3 = st.columns(3)
    comp = c1.text_input("Virksomhed:")
    titl = c2.text_input("Stilling:")
    name = c3.text_input("Dit Navn:")
    contact = st.text_input("Kontaktperson (Navn):")
    if st.button("Næste →", disabled=not (cv_file and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv_file)
        st.session_state.temp_ans = temp_ans
        st.session_state.temp_cv = temp_cv
        st.session_state.comp = comp
        st.session_state.titl = titl
        st.session_state.name = name
        st.session_state.contact = contact
        next_step(); st.rerun()

elif st.session_state.step == 2:
    st.header("2. Jobbet")
    url = st.text_input("Link til opslag:")
    if st.button("Hent tekst") and url:
        txt = get_text_from_url(url)
        if txt: st.session_state.fetched_txt = txt
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=250)
    noter = st.text_area("Noter:")
    if st.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step(); st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi & Tilpasning")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = c2.select_slider("Længde på ansøgning:", ["Kort", "Standard", "Uddybende"], "Standard")
    h_type = c1.selectbox("Overskrift:", ["Værdiskabende", "Formel", "Catchy"])
    strat = c2.selectbox("Strategi:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater"])
    if st.button("Generér Professionel Pakke ✨"):
        st.session_state.p = {"tone": tone, "len": length, "h_type": h_type, "strat": strat}
        next_step(); st.rerun()

elif st.session_state.step == 4:
    st.header("4. Analyse & Resultater")
    if "final_res" not in st.session_state:
        with st.spinner("AI udfører ATS-analyse og skriver dokumenter..."):
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            p = st.session_state.p
            
            # 1. DYB ATS ANALYSE
            ats_p = f"Lav en dyb ATS-analyse. Giv en Match Score i % og oplist de 5 vigtigste styrker og de 3 vigtigste mangler i forhold til jobbet.\nJob: {st.session_state.opslag}"
            ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
            st.session_state.ats_result = ats_resp.choices[0].message.content

            # 2. HOVEDGENERERING
            kontakt_navn = st.session_state.contact if st.session_state.contact else "Ansættelsesudvalget"
            main_prompt = f"""
            Lav en JSON pakke på dansk. 
            VIGTIGT: Alle felter skal være strenge (strings), IKKE lister/arrays.
            
            1. 'ansogning': En komplet ansøgning adresseret til {kontakt_navn}. Længde: {p['len']}. Tone: {p['tone']}. Strategi: {p['strat']}.
            2. 'overskrift': En stærk overskrift (type: {p['h_type']}).
            3. 'cv_profil': Målrettet profiltekst til CV'et (ca. 6 linjer).
            4. 'cv_erfaring': En komplet beskrivelse af erhvervserfaring fra Master-CV'et. For hver stilling skal der være 3-4 bullets. Hver stilling SKAL indeholde et afsnit kaldet 'Resultater og bedrifter', hvor du fremhæver målbare succeser.
            5. 'cv_uddannelse': Uddannelseshistorik.
            6. 'cv_kompetencer': Liste over faglige kompetencer.
            7. 'interview': 3 interviewspørgsmål og svar. Brug #### til overskrifter og dobbelt linjeskift.
            
            DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}
            """
            
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "Du er elite-rekrutteringskonsulent. Svar KUN i JSON format. Brug aldrig lister, kun tekststrenge."}, {"role": "user", "content": main_prompt}],
                response_format={"type": "json_object"}
            )
            st.session_state.final_res = json.loads(resp.choices[0].message.content)

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        st.subheader("📊 ATS Match & Analyse")
        st.info(st.session_state.ats_result)
        
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("📄 Ansøgning")
            st.markdown(f"**{res.get('overskrift')}**")
            st.write(res.get('ansogning'))
            if st.session_state.temp_ans:
                ans_data = {"{{ANSOGNING}}": res.get('ansogning'), "{{OVERSKRIFT}}": res.get('overskrift'), "{{VIRKSOMHED}}": st.session_state.comp, "{{JOBTITEL}}": st.session_state.titl, "{{KONTAKTPERSON}}": st.session_state.contact if st.session_state.contact else "Ansættelsesudvalget"}
                doc = fill_docx(st.session_state.temp_ans, ans_data)
                st.download_button("Hent Ansøgning (.docx)", doc, f"Ansøgning_{st.session_state.comp}.docx")

        with col_b:
            st.subheader("👤 CV Optimering")
            st.write(res.get('cv_erfaring'))
            if st.session_state.temp_cv:
                cv_data = {"{{NAVN}}": st.session_state.name, "{{CV_PROFIL}}": res.get('cv_profil'), "{{CV_ERFARING}}": res.get('cv_erfaring'), "{{CV_UDDANNELSE}}": res.get('cv_uddannelse'), "{{CV_KOMPETENCER}}": res.get('cv_kompetencer'), "{{JOBTITEL}}": st.session_state.titl}
                cv_doc = fill_docx(st.session_state.temp_cv, cv_data)
                st.download_button("Hent Optimeret CV (.docx)", cv_doc, f"CV_{st.session_state.comp}.docx")
        
        st.divider()
        st.subheader("🎤 Interviewforberedelse")
        st.markdown(res.get('interview'))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()
