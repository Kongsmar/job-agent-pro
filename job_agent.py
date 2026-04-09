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
from fpdf import FPDF
from PyPDF2 import PdfReader

# --- KONFIGURATION & DATABASE ---
st.set_page_config(page_title="Job Agent Pro - Ultra+", page_icon="🚀", layout="wide")
db_path = "job_agent_arkiv_v2.db"

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
def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        return soup.get_text(separator=' ', strip=True)
    except: return ""

def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except: return None

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    try:
        clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    except:
        clean_text = text.replace('–', '-').replace('—', '-')
    pdf.multi_cell(0, 8, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

def fill_word_template(template_file, content, company_name, job_title):
    try:
        doc = Document(template_file)
        today_str = datetime.now().strftime("%d. %B %Y")
        data_map = {"{{ANSOGNING}}": content, "{{VIRKSOMHED}}": company_name, "{{JOBTITEL}}": job_title, "{{DATO}}": today_str}
        for p in doc.paragraphs:
            for key, value in data_map.items():
                if key in p.text: p.text = p.text.replace(key, value)
        target_stream = io.BytesIO()
        doc.save(target_stream)
        target_stream.seek(0)
        return target_stream
    except: return None

# --- APP LAYOUT ---
st.title("🚀 Job Agent Pro - Ultra+")

tabs = st.tabs(["📄 Ny Ansøgning", "📂 Arkiv", "💡 Karriere Rådgiver"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Indstillinger")
        api_key = st.secrets.get("OPENAI_API_KEY")
        uploaded_cv = st.file_uploader("Upload CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")
        
        st.divider()
        st.subheader("🎯 Strategi")
        selected_tone = st.select_slider("Tone:", options=["Formel", "Professionel", "Balanceret", "Personlig", "Kreativ"], value="Balanceret")
        selected_length = st.select_slider("Længde:", options=["Kort", "Standard", "Uddybende"], value="Standard")
        
        mirror_language = st.toggle("Spejl virksomhedens sprogbrug", value=True)
        include_pitch = st.toggle("Generer LinkedIn Pitch", value=True)
        include_interview = st.toggle("Generer Interview Spørgsmål", value=True)

    st.subheader("Job Detaljer")
    c1, c2 = st.columns(2)
    with c1: company = st.text_input("Virksomhed:")
    with c2: title = st.text_input("Jobtitel:")
    
    job_url = st.text_input("Link til jobopslag:")
    job_desc_manual = st.text_area("Eller indsæt tekst:", height=100)
    
    personal_notes = st.text_area("Personlige noter (f.eks. 'Jeg talte med HR')", height=70)

    if st.button("Kør Fuldt Program ✨"):
        if not api_key or not uploaded_cv or (not job_url and not job_desc_manual):
            st.error("Udfyld venligst alle nødvendige felter.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cv_text = extract_text_from_pdf(uploaded_cv)
                job_text = job_desc_manual
                if job_url:
                    with st.spinner("Henter opslag..."):
                        fetched = get_text_from_url(job_url)
                        if len(fetched) > 150: job_text = fetched

                # --- GENERERING ---
                with st.spinner("Arbejder på din pakke..."):
                    # Samlet prompt for at spare tid og sikre rød tråd
                    main_prompt = f"""
                    Du er en elite karriererådgiver. Lav følgende for {title} hos {company}:
                    
                    1. En ansøgning (Brødtekst):
                       - Tone: {selected_tone}
                       - Længde: {selected_length}
                       - Strategi: {'Spejl deres sprogbrug' if mirror_language else 'Standard professionel'}
                       - Inkorporér noter: {personal_notes}
                    
                    2. En LinkedIn Pitch (3-4 sætninger):
                       - En fængende besked til en rekrutteringsansvarlig.
                    
                    3. Interview Prep:
                       - De 3 mest sandsynlige spørgsmål baseret på gaps mellem CV og jobopslag.
                    
                    CV: {cv_text[:3000]}
                    Job: {job_text[:3000]}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Svar i JSON format med nøglerne: 'ansogning', 'pitch', 'interview'."},
                                  {"role": "user", "content": main_prompt}],
                        response_format={ "type": "json_object" }
                    )
                    
                    import json
                    res_data = json.loads(response.choices[0].message.content)
                    ans_text = res_data['ansogning']
                    
                    # Gem i arkiv
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?, ?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, job_text, selected_tone))
                    conn.commit()
                    conn.close()

                    # VISUALISERING
                    st.success("Færdig! Her er din pakke:")
                    
                    col_left, col_right = st.columns([2, 1])
                    
                    with col_left:
                        st.subheader("📝 Ansøgning")
                        st.write(ans_text)
                        
                        d1, d2 = st.columns(2)
                        with d1:
                            if uploaded_template:
                                w_file = fill_word_template(uploaded_template, ans_text, company, title)
                                st.download_button("Hent Word 📄", w_file, f"Ansogning_{company}.docx")
                        with d2:
                            st.download_button("Hent PDF 📄", create_pdf(ans_text), f"Ansogning_{company}.pdf")

                    with col_right:
                        if include_pitch:
                            st.subheader("✉️ LinkedIn Pitch")
                            st.info(res_data['pitch'])
                        
                        if include_interview:
                            st.subheader("🎤 Interview Prep")
                            st.warning(res_data['interview'])

            except Exception as e:
                st.error(f"Fejl: {e}")

with tabs[1]:
    st.header("Arkiv")
    # (Samme arkiv logik som før)
