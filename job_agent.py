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
st.set_page_config(page_title="Job Agent Pro - Professional Edition", page_icon="🚀", layout="wide")
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

def fill_docx(template, content, headline, company, title, contact_person, is_cv=False):
    try:
        template.seek(0)
        doc = Document(template)
        data = {
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{OVERSKRIFT}}": headline.strip().capitalize() if headline else "",
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        main_tag = "{{CV_OPTIMERET}}" if is_cv else "{{ANSOGNING}}"

        for p in doc.paragraphs:
            for key, value in data.items():
                if key in p.text:
                    p.text = p.text.replace(key, str(value))
            
            if main_tag in p.text:
                p.text = p.text.replace(main_tag, "")
                cursor = p
                # VIGTIGT: Vi tvinger indholdet til at være en streng og fjerner eventuelle array-tegn
                clean_content = str(content).replace("['", "").replace("']", "").replace("', '", "\n")
                for text in clean_content.split('\n'):
                    if text.strip():
                        new_p = doc.add_paragraph(text.strip())
                        new_p.style = p.style
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
    cv = st.file_uploader("Upload CV (PDF)", type="pdf")
    col_t1, col_t2 = st.columns(2)
    temp = col_t1.file_uploader("Skabelon: Ansøgning (.docx)", type="docx")
    cv_temp = col_t2.file_uploader("Skabelon: CV (.docx)", type="docx")
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhed:")
    titl = c2.text_input("Stilling:")
    contact = st.text_input("Kontaktperson:")
    if st.button("Næste →", disabled=not (cv and comp and titl)):
        st.session_state.cv_text = extract_pdf(cv)
        st.session_state.temp = temp
        st.session_state.cv_temp = cv_temp
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
    noter = st.text_area("Noter til fokus:")
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
    h_type = c2.selectbox("Overskriftstype:", ["Formel", "Værdiskabende", "Catchy", "Spørgende"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Strategi:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    f1, f2 = st.columns(2)
    fokus = f1.radio("Fokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mot_pos = f2.radio("Motivation:", ["I starten", "I bunden"])
    if st.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "h_type": h_type, "strat": strat, "fokus": fokus, "mot_pos": mot_pos}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("Skriver og optimerer..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS Analyse
                ats_p = f"Analysér CV mod Jobopslag. Giv Match Score i % og top styrker/mangler.\nCV: {st.session_state.cv_text[:2000]}\nJob: {st.session_state.opslag[:2000]}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                main_prompt = f"""
                Lav en JSON pakke på dansk. 
                VIGTIGT: Alt indhold skal være på dansk. Tone: {p['tone']}.
                
                1. 'ansogning': Skriv en DYBDEGÅENDE og argumenterende ansøgning (min. 6 fyldige afsnit). Brug dobbelt linjeskift mellem afsnit. Fokus: {p['fokus']}. Strategi: {p['strat']}. Motivation: {p['mot_pos']}.
                2. 'overskrift': En stærk overskrift (type: {p['h_type']}).
                3. 'cv_komplet': Opbyg et KOMPLET CV i REN TEKST (ingen arrays/lister). 
                   Strukturen SKAL være:
                   - NAVN & TITEL
                   - KONTAKTINFORMATION
                   - PROFIL (Fyldig tekst, målrettet jobbet)
                   - KOMPETENCER (Opdelt i faglige og personlige)
                   - ANSÆTTELSESHISTORIK (For hver stilling: Beskriv arbejdsopgaver og ansvar i detaljer med bullets)
                   - UDDANNELSE & KURSER
                   BRUG STORE BOGSTAVER TIL OVERSKRIFTER. Beskriv hver stilling grundigt.
                4. 'pitch': LinkedIn pitch.
                5. 'interview': 3 kritiske spørgsmål og svar i REN MARKDOWN (brug #### til spørgsmål).

                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, ANALYSE: {st.session_state.ats_result}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er elite-rekrutteringskonsulent. Svar KUN i JSON. Alle felter skal være strenge (strings), aldrig arrays."}, 
                             {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)

                # Arkiv
                conn = sqlite3.connect(db_path); c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (get_danish_time(), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit(); conn.close()
            except Exception as e:
                st.error(f"Fejl: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        st.markdown(f"### Match Score & Analyse")
        st.info(st.session_state.ats_result)
        
        col_main, col_side = st.columns([2, 1])
        with col_main:
            st.subheader("📄 Ansøgning")
            st.markdown(f"**{res.get('overskrift')}**")
            st.write(res.get('ansogning'))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), res.get('overskrift'), st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Ansøgning (.docx)", doc, f"Ansøgning_{st.session_state.comp}.docx")
            
            st.divider()
            st.subheader("👤 Det Komplette CV")
            st.write(res.get('cv_komplet'))
            if st.session_state.cv_temp:
                cv_doc = fill_docx(st.session_state.cv_temp, res.get('cv_komplet'), "", st.session_state.comp, st.session_state.titl, st.session_state.contact, is_cv=True)
                st.download_button("Hent Det Nye CV (.docx)", cv_doc, f"CV_{st.session_state.comp}.docx")

        with col_side:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch'))
            st.subheader("🎤 Interview Prep")
            st.markdown(res.get('interview'))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Arkiv")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC LIMIT 5", conn); conn.close()
    for i, row in df.iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']}"):
            st.write(row['ansogning'])
