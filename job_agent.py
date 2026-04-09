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
        def replace_text(paragraphs):
            for p in paragraphs:
                for key, value in data.items():
                    if key in p.text:
                        # Prøv run-by-run først for at bevare formatering
                        for run in p.runs:
                            if key in run.text:
                                run.text = run.text.replace(key, str(value))
                        # Fallback hvis tagget er splittet over flere runs
                        if key in p.text:
                            p.text = p.text.replace(key, str(value))

        replace_text(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    replace_text(cell.paragraphs)
        
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf
    except: return None

# --- APP FLOW ---
st.title("🚀 Job Agent Pro")
st.progress(st.session_state.step / 4)

if st.session_state.step == 1:
    st.header("1. Grundlaget")
    cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
    temp = st.file_uploader("Upload din Word-skabelon (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:")
    titl = c2.text_input("Hvilken stilling søger du?")
    contact = st.text_input("Kontaktperson (f.eks. Mette Jensen):")
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
    noter = st.text_area("Noter til AI'en:")
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
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    motivation_pos = st.radio("Hvor skal din motivation (hvorfor dig/hvorfor dem) placeres?", ["I starten (krogen)", "I bunden (opsamlingen)"], index=0)
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): prev_step(); st.rerun()
    if col2.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": motivation_pos}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Analyse & Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Kører ATS-analyse og skriver alt indhold..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS ANALYSE
                ats_p = f"Analysér jobopslag mod CV. 
                Giv mig et 'Match Score' i procent (f.eks. 85%) og en kort begrundelse.
                Find 3 vigtigste nøgleord.\nJob: {st.session_state.opslag[:2000]}\nCV: {st.session_state.cv_text[:2000]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                # HOVED PROMPT
                len_instr = "ca. 500 ord" if p['len'] == "Standard" else "ca. 300 ord" if p['len'] == "Kort" else "ca. 750 ord"
                
                main_prompt = f"""
                Du er en rekrutteringsekspert. Lav en pakke i JSON format.
                
                VIGTIG REGEL FOR MOTIVATION: 
                Brugeren har valgt at motivationen SKAL placeres: {p['mot_pos']}. 
                Hvis 'I starten', skal første afsnit forklare HVORFOR de søger netop dette job.
                Hvis 'I bunden', skal de faglige argumenter komme først, og motivationen gemmes til sidst.

                JSON NØGLER:
                1. 'ansogning': Skriv kun fyldig brødtekst (Længde: {len_instr}). Ingen hilsner/afsked. Fokus: {p['fokus']}. Strategi: {p['strat']}.
                2. 'pitch': En 3-4 sætningers besked til LinkedIn.
                3. 'interview': En liste med de 3 mest relevante spørgsmål og korte råd til svar.
                
                DATA:
                - CV: {st.session_state.cv_text}
                - JOB: {st.session_state.opslag}
                - ANALYSE: {st.session_state.ats_result}
                - NOTER: {st.session_state.noter}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du svarer altid i korrekt JSON format."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                
                st.session_state.final_res = json.loads(resp.choices[0].message.content)
                
                # Gem i arkiv
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (datetime.now().strftime("%Y-%m-%d %H:%M"), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
                
            except Exception as e:
                st.error(f"Fejl under generering: {e}")

    if "final_res" in st.session_state:
        st.info(f"📊 **ATS Analyse:**\n{st.session_state.ats_result}")
        res = st.session_state.final_res
        c_main, c_side = st.columns([2, 1])
        
        with c_main:
            st.subheader("📝 Ansøgning")
            st.write(res.get('ansogning', 'Fejl i ansøgning'))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_side:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch', 'Fejl i pitch'))
            st.subheader("🎤 Interview Prep")
            # Vi sikrer os at interview vises korrekt, uanset om det er liste eller tekst
            st.warning(res.get('interview', 'Fejl i interview prep'))
            
        if st.button("Start forfra 🔄"): reset(); st.rerun()
