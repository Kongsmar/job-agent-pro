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
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        
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

        for p in doc.paragraphs:
            if "{{ANSOGNING}}" in p.text:
                paragraphs_content = content.split('\n')
                p.text = p.text.replace("{{ANSOGNING}}", "")
                cursor = p
                for text in paragraphs_content:
                    if text.strip():
                        new_p = doc.add_paragraph(text.strip())
                        cursor._element.addnext(new_p._element)
                        cursor = new_p
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
    mot_pos = st.radio("Motivationens placering:", ["I starten (krogen)", "I bunden (opsamlingen)"])
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": mot_pos}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver en fyldig ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS
                ats_p = f"Giv Match Score i % og 3 nøgleord.\nJob: {st.session_state.opslag[:1500]}\nCV: {st.session_state.cv_text[:1500]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # DYBDE INSTRUKTION
                length_map = {
                    "Kort": "ca. 250-300 ord. Fokus på de vigtigste pointer.",
                    "Standard": "ca. 450-550 ord. Gå i dybden med mindst 3 konkrete eksempler fra CV'et.",
                    "Uddybende": "ca. 700+ ord. Meget detaljeret kobling mellem alle jobkrav og ansøgerens profil."
                }
                
                main_prompt = f"""
                Lav en JSON pakke:
                'ansogning': Skriv en FYLDIG brødtekst (Længde: {length_map[p['len']]}). 
                Brug dobbelt linjeskift (\\n\\n) mellem afsnit (mindst 4-5 afsnit). 
                Ingen hilsen/afsked. Start direkte. Motivation skal placeres {p['mot_pos']}.
                Uddyb konkrete resultater og erfaringer fra CV'et og kobl dem direkte til opgaverne i jobbet.
                
                'pitch': Kort LinkedIn besked til en rekrutteringsansvarlig.
                'interview': De 3 vigtigste spørgsmål og strategiske svarforslag (som én tekststreng).
                
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, NOTER: {st.session_state.noter}
                """
                resp = client.chat.completions.create(
                    model="gpt-4o", # Vi bruger den store model for bedre kvalitet og længde
                    messages=[{"role": "system", "content": "Du er en ekspert i karriererådgivning. Svar KUN i JSON format. 'interview' skal være en simpel tekststreng."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        st.info(f"📊 **Analyse:** {st.session_state.ats_result}")
        
        c_m, c_s = st.columns([2, 1])
        with c_m:
            st.subheader("📝 Ansøgning")
            st.write(res.get('ansogning', ''))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_s:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch', 'Ingen pitch genereret'))
            st.subheader("🎤 Interview Prep")
            i_text = res.get('interview', 'Ingen interview prep genereret')
            if isinstance(i_text, list): i_text = "\n\n".join(i_text)
            st.warning(i_text)
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()
