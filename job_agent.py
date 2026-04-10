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
st.set_page_config(page_title="Job Agent Pro - CV & Ansøgning", page_icon="🚀", layout="wide")
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
        
        # Data til almindelige tags
        data = {
            "{{VIRKSOMHED}}": company, 
            "{{JOBTITEL}}": title, 
            "{{KONTAKTPERSON}}": contact_person,
            "{{OVERSKRIFT}}": headline.strip().capitalize() if headline else "",
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }

        # Find ud af hvilket tag vi skal kigge efter til brødteksten
        main_tag = "{{CV_OPTIMERET}}" if is_cv else "{{ANSOGNING}}"

        for p in doc.paragraphs:
            # Erstat stamdata tags
            for key, value in data.items():
                if key in p.text:
                    p.text = p.text.replace(key, str(value))
            
            # Indsæt genereret indhold (afsnit for afsnit)
            if main_tag in p.text:
                p.text = p.text.replace(main_tag, "")
                paragraphs_content = str(content).split('\n')
                cursor = p
                for text in paragraphs_content:
                    if text.strip():
                        new_p = doc.add_paragraph(text.strip())
                        cursor._element.addnext(new_p._element)
                        cursor = new_p

        # Tjek tabeller for tags
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for key, value in data.items():
                            if key in p.text:
                                p.text = p.text.replace(key, str(value))
                                
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
    cv = st.file_uploader("Upload dit nuværende CV (PDF)", type="pdf")
    
    col_t1, col_t2 = st.columns(2)
    temp = col_t1.file_uploader("Word-skabelon: Ansøgning", type="docx")
    cv_temp = col_t2.file_uploader("Word-skabelon: CV", type="docx")
    
    c1, c2 = st.columns(2)
    comp = c1.text_input("Virksomhedens navn:")
    titl = c2.text_input("Hvilken stilling søger du?")
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
    headline_type = c2.selectbox("Overskriftstype:", ["Formel", "Værdiskabende", "Kreativ/Catchy", "Spørgende"])
    length = st.select_slider("Omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    
    if st.button("Generér Alt (Ansøgning + CV-optimering) ✨"):
        st.session_state.p = {"tone": tone, "len": length, "headline_type": headline_type}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("AI arbejder på både ansøgning og CV..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                main_prompt = f"""
                Lav en JSON pakke på dansk.
                1. 'ansogning': Skriv en komplet ansøgning (min. 5 afsnit). Ingen hilsner.
                2. 'overskrift': Lav en overskrift af typen '{p['headline_type']}'.
                3. 'cv_optimeret': Omskriv brugerens profiltekst og vigtigste erfaringer så de matcher jobopslaget. Brug bullets.
                4. 'pitch': 3-4 sætninger til LinkedIn.
                5. 'interview': 3 kritiske spørgsmål og svar.
                
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}
                """
                
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er karriereekspert. Svar KUN i JSON."}, 
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
        
        col_main, col_side = st.columns([2, 1])
        
        with col_main:
            # --- ANSØGNING ---
            st.subheader("📄 Din Ansøgning")
            h_final = res.get('overskrift', '').strip().capitalize()
            st.markdown(f"**Overskrift:** {h_final}")
            st.write(res.get('ansogning'))
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), h_final, st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Download Ansøgning (.docx)", doc, f"Ansøgning_{st.session_state.comp}.docx")
            
            st.divider()
            
            # --- CV OPTIMERING ---
            st.subheader("👤 Optimeret CV-indhold")
            st.success("Her er dit målrettede indhold til CV'et:")
            cv_content = res.get('cv_optimeret', '')
            st.write(cv_content)
            if st.session_state.cv_temp:
                cv_doc = fill_docx(st.session_state.cv_temp, cv_content, "", st.session_state.comp, st.session_state.titl, st.session_state.contact, is_cv=True)
                st.download_button("Download Optimeret CV (.docx)", cv_doc, f"CV_{st.session_state.comp}.docx")

        with col_side:
            st.subheader("✉️ LinkedIn")
            st.info(res.get('pitch'))
            st.subheader("🎤 Interview Prep")
            st.markdown(res.get('interview'))
        
        if st.button("Start forfra 🔄"): reset(); st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Arkiv")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path); df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn); conn.close()
    for index, row in df.head(10).iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
            st.write(row['ansogning'])
