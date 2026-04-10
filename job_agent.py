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
st.set_page_config(page_title="Job Agent Pro - Master Edition", page_icon="🚀", layout="wide")
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
if 'step' not in st.session_state: 
    st.session_state.step = 1

def next_step(): 
    st.session_state.step += 1

def prev_step(): 
    st.session_state.step -= 1

def reset():
    for key in list(st.session_state.keys()): 
        del st.session_state[key]
    st.session_state.step = 1

# --- HJÆLPEFUNKTIONER ---
def get_text_from_url(url):
    """Henter tekst fra URL og bevarer overskrifter og lister."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.extract()

        output = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'li']):
            text = tag.get_text().strip()
            if text:
                if tag.name in ['h1', 'h2', 'h3']:
                    output.append(f"\n\n### {text}\n")
                elif tag.name == 'li':
                    output.append(f"* {text}")
                else:
                    output.append(f"{text}\n")
        
        return "\n".join(output)
    except Exception as e:
        return f"Kunne ikke hente teksten: {e}"

def extract_pdf(file):
    try:
        reader = PdfReader(file)
        return "".join([p.extract_text() for p in reader.pages])
    except: 
        return ""

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

        for p in doc.paragraphs:
            for key, value in data.items():
                if key in p.text:
                    p.text = p.text.replace(key, str(value))
            
            if "{{ANSOGNING}}" in p.text:
                p.text = p.text.replace("{{ANSOGNING}}", "")
                paragraphs_content = content.split('\n')
                cursor = p
                for text in paragraphs_content:
                    if text.strip():
                        new_p = doc.add_paragraph(text.strip())
                        cursor._element.addnext(new_p._element)
                        cursor = new_p

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
    except: 
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
    if st.button("Hent tekst fra link") and url:
        txt = get_text_from_url(url)
        if txt: 
            st.session_state.fetched_txt = txt
            
    opslag = st.text_area("Jobtekst:", value=st.session_state.get('fetched_txt', ""), height=300)
    noter = st.text_area("Særlige noter til AI'en:")
    
    col1, col2 = st.columns(2)
    if col1.button("← Tilbage"): 
        prev_step()
        st.rerun()
    if col2.button("Næste →", disabled=not opslag):
        st.session_state.opslag = opslag
        st.session_state.noter = noter
        next_step()
        st.rerun()

elif st.session_state.step == 3:
    st.header("3. Strategi & Tone")
    c1, c2 = st.columns(2)
    tone = c1.selectbox("Vælg tone:", ["Professionel", "Balanceret", "Personlig", "Kreativ", "Formel"])
    headline_type = c2.selectbox("Overskriftstype:", ["Formel (Ansøgning om...)", "Værdiskabende (Resultatorienteret)", "Kreativ/Catchy", "Spørgende/Nysgerrig"])
    length = st.select_slider("Ansøgningens omfang:", ["Kort", "Standard", "Uddybende"], "Standard")
    strat = st.selectbox("Strategisk indledning:", ["Problemknuser", "Værdi-baseret", "Direkte/Resultater", "Passioneret"])
    fokus = st.radio("Hovedfokus:", ["Faglige resultater", "Personlige kompetencer", "Balanceret"], horizontal=True)
    mot_pos = st.radio("Motivationens placering:", ["I starten (krogen)", "I bunden (opsamlingen)"])
    
    if st.button("Generér Alt ✨"):
        st.session_state.p = {"tone": tone, "len": length, "strat": strat, "fokus": fokus, "mot_pos": mot_pos, "headline_type": headline_type}
        next_step()
        st.rerun()

elif st.session_state.step == 4:
    st.header("4. Analyse & Resultat")
    if "final_res" not in st.session_state:
        with st.spinner("AI analyserer match og skriver din ansøgning..."):
            try:
                client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
                p = st.session_state.p
                
                # ATS ANALYSE
                ats_p = f"Analysér CV mod Jobopslag. Giv Match Score i % og top styrker/mangler.\nCV: {st.session_state.cv_text[:3000]}\nJob: {st.session_state.opslag}"
                ats_resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": ats_p}])
                st.session_state.ats_result = ats_resp.choices[0].message.content

                main_prompt = f"""
                Lav en JSON pakke på dansk.
                1. 'ansogning': Skriv en komplet ansøgning uden navne/hilsner. Længde: {p['len']}. Tone: {p['tone']}. Strategi: {p['strat']}. Motivation: {p['mot_pos']}.
                2. 'overskrift': Lav en overskrift af typen '{p['headline_type']}'. Kun stort begyndelsesbogstav.
                3. 'pitch': 3-4 sætninger til LinkedIn/Netværk.
                4. 'interview': 3 kritiske interviewspørgsmål og svar. Format: #### 1. Spørgsmål... Svarforslag...
                
                STRENG REGEL: Svar kun i JSON.
                DATA: CV: {st.session_state.cv_text}, JOB: {st.session_state.opslag}, ANALYSE: {st.session_state.ats_result}
                """
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "system", "content": "Du er karriererådgiver. Svar KUN i JSON."}, {"role": "user", "content": main_prompt}],
                    response_format={"type": "json_object"}
                )
                st.session_state.final_res = json.loads(resp.choices[0].message.content)

                # Arkiv
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?,?,?,?,?,?)",
                          (get_danish_time(), st.session_state.comp, st.session_state.titl, st.session_state.final_res['ansogning'], st.session_state.opslag, p['tone']))
                conn.commit()
                conn.close()
            except Exception as e:
                st.error(f"Fejl i generering: {e}")

    if "final_res" in st.session_state:
        res = st.session_state.final_res
        with st.expander("📊 ATS & Match Analyse", expanded=True):
            st.markdown(st.session_state.ats_result)
            
        c_m, c_s = st.columns([2, 1])
        with c_m:
            headline_final = res.get('overskrift', '').strip().capitalize()
            st.markdown(f"### {headline_final}")
            st.divider()
            st.subheader("📝 Ansøgning")
            st.write(res.get('ansogning', ''))
            
            if st.session_state.temp:
                doc = fill_docx(st.session_state.temp, res.get('ansogning'), headline_final, st.session_state.comp, st.session_state.titl, st.session_state.contact)
                st.download_button("Hent Word-fil 📄", doc, f"Ansøgning_{st.session_state.comp}.docx")
        
        with c_s:
            st.subheader("✉️ LinkedIn Pitch")
            st.success(res.get('pitch', ''))
            st.subheader("🎤 Interview Prep")
            st.markdown(res.get('interview', ''))
            
        if st.button("Start forfra 🔄"): 
            reset()
            st.rerun()

# --- ARKIV ---
st.divider()
st.subheader("📂 Tidligere ansøgninger")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
    conn.close()
    for index, row in df.head(10).iterrows():
        with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
            st.write(row['ansogning'])
