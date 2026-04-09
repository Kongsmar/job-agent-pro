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
st.set_page_config(page_title="Job Agent Pro - Master Edition", page_icon="🚀", layout="wide")
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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
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
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        
        # Håndtering af placeholders (undtagen selve ansøgningen)
        def replace_placeholders(paragraphs):
            for p in paragraphs:
                for key, value in data.items():
                    if key in p.text:
                        for run in p.runs:
                            if key in run.text:
                                run.text = run.text.replace(key, str(value))
                        if key in p.text:
                            p.text = p.text.replace(key, str(value))

        replace_placeholders(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    replace_placeholders(cell.paragraphs)

        # Speciel håndtering af {{ANSOGNING}} for at bevare afsnit
        for p in doc.paragraphs:
            if "{{ANSOGNING}}" in p.text:
                # Split indholdet ved linjeskift
                paragraphs_content = content.split('\n')
                p.text = p.text.replace("{{ANSOGNING}}", "") # Rens tagget
                parent = p._element.getparent()
                
                for text in paragraphs_content:
                    if text.strip(): # Tilføj kun hvis der er tekst
                        new_p = doc.add_paragraph(text.strip())
                        p._element.addnext(new_p._element)
                        p = new_p # Flyt markøren så rækkefølgen passer

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except Exception as e:
        st.error(f"Word-fejl: {e}")
        return None

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
    contact = st.text_input("Kontaktperson:")
    if st.button("Næste →", disabled=not (cv and comp and titl)):
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
    tone = c1.selectbox("Tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mot_pos = st.radio("Placering af motivation:", ["I starten (krogen)", "I bunden (opsamlingen)"])
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": mot_pos}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Analyse & Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS PROMPT
                ats_p = f"Giv en Match Score i % og 3 nøgleord.\nJob: {st.session_state.opslag[:2000]}\nCV: {st.session_state.cv_text[:2000]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # HOVED PROMPT
                main_prompt = f"""
                Skriv en pakke i JSON. 
                VIGTIGT: Brug dobbelt linjeskift (\\n\\n) mellem afsnit i 'ansogning'.
                
                'ansogning': Skriv KUN brødtekst (4-5 afsnit). Ingen hilsen/afsked. Motivation skal være {p['mot_pos']}.
                'pitch': LinkedIn besked.
                'interview': 3 spørgsmål.
                
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, ANALYSE: {st.session_state.ats_result}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Svar i JSON format. Brug \\n\\n for nye afsnit."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        st.info(st.session_state.ats_result)
        res = st.session_state.final_res
        st.subheader("📝 Ansøgning")
        st.write(res.get('ansogning').replace('\n', '\n\n')) # Sikrer visning i Streamlit
        
        if st.session_state.temp:
            doc = fill_docx(st.session_state.temp, res.get('ansogning'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
            st.download_button("Hent Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()
