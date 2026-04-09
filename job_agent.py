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

def fill_docx(template, content, headline, company, title, contact_person):
    try:
        template.seek(0)
        doc = Document(template)
        formatted_headline = headline.strip().capitalize()
        data = {
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{OVERSKRIFT}}": formatted_headline,
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
    headline_type = c2.selectbox("Overskriftstype:", ["Formel (Ansøgning om...)", "Værdiskabende (Resultatorienteret)", "Kreativ/Catchy", "Spørgende/Nysgerrig"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mot_pos = st.radio("Motivationens placering:", ["I starten (krogen)", "I bunden (opsamlingen)"])
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": mot_pos, "headline_type": headline_type}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Udfører dybdegående ATS-analyse og skriver..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # --- DEDIKERET ATS ANALYSE ---
                ats_p = f"""Foretag en grundig ATS-analyse af CV vs Jobopslag. 
                Svaret skal indeholde:
                1. Match Score i % (f.eks. 85%).
                2. De 3 vigtigste nøgleord fundet i jobopslaget.
                3. Top 3 styrker i matchet.
                4. Top 3 mangler/huller (hvad skal forklares/kompenseres for).
                
                CV: {st.session_state.cv_text[:2000]}
                Job: {st.session_state.opslag[:2000]}"""
                
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # --- HOVED GENERERING ---
                main_prompt = f"""
                Lav en JSON pakke på dansk:
                'overskrift': En '{p['headline_type']}' overskrift (kun stort begyndelsesbogstav).
                'ansogning': En FYLDIG brødtekst (ca. 500 ord). Brug dobbelt linjeskift. Motivation: {p['mot_pos']}.
                'pitch': 3-4 sætninger til LinkedIn.
                'interview': 3 kritiske spørgsmål og strategiske svar-tips i punktform (-).
                
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, ANALYSE: {st.session_state.ats_result}
                """
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er en elite-rekrutteringskonsulent. Svar KUN i JSON format."}, {"role": "user", "content": main_prompt}],
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
        
        # VISNING AF DEN UDVIDEDE ANALYSE
        with st.expander("📊 Se udvidet ATS & Match Analyse", expanded=True):
            st.markdown(st.session_state.ats_result)
        
        c_m, c_s = st.columns([2, 1])
        with c_m:
            headline_final = res.get('overskrift', '').strip().capitalize()
            st.markdown(f"### {headline_final}")
            st.write(res.get('ansogning', ''))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), headline_final, st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_s:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch', ''))
            st.subheader("🎤 Interview Prep")
            st.warning(res.get('interview', ''))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Arkiv")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
    for _, row in df.head(10).iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
            st.write(row['ansogning'])
