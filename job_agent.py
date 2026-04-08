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
st.set_page_config(page_title="Job Agent Pro - Master", page_icon="💼", layout="wide")
db_path = "job_archive_final.db"

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
    clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

def fill_word_template(template_file, content, company_name):
    try:
        doc = Document(template_file)
        # Sørger for at datoen altid er i dagens format
        today_str = datetime.now().strftime("%d. %B %Y")
        
        data_map = {
            "{{ANSOGNING}}": content, 
            "{{VIRKSOMHED}}": company_name, 
            "{{DATO}}": today_str
        }
        
        # Gennemgå alle afsnit og erstat koder
        for p in doc.paragraphs:
            for key, value in data_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, value)
        
        target_stream = io.BytesIO()
        doc.save(target_stream)
        target_stream.seek(0)
        return target_stream
    except Exception as e:
        st.error(f"Fejl ved udfyldning af Word: {e}")
        return None

# --- APP LAYOUT ---
st.title("💼 Job Agent Pro")
st.caption("AI-drevet ansøgningsværktøj | ATS & HR-Robot Optimeret")

tabs = st.tabs(["🚀 Generer Ansøgning", "📁 Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Indstillinger")
        api_key = st.secrets.get("OPENAI_API_KEY")
        uploaded_cv = st.file_uploader("1. Upload dit CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("2. Upload Word-skabelon (.docx)", type="docx")
        
        st.divider()
        st.subheader("🎭 Toneleje")
        tone_options = ["Meget Formel", "Professionel", "Balanceret", "Personlig", "Kreativ"]
        selected_tone = st.select_slider(
            "Vælg stil:", 
            options=tone_options, 
            value="Balanceret"
        )
        
        tone_prompts = {
            "Meget Formel": "meget formel, korrekt og konservativ. Brug et højtideligt sprog.",
            "Professionel": "saglig, forretningsorienteret og kompetent. Moderne erhvervssprog.",
            "Balanceret": "professionel men imødekommende. God blanding af personlighed og fag.",
            "Personlig": "varm, autentisk og fortællende. Fokus på værdier og motivation.",
            "Kreativ": "modig, sprudlende og unik. Brug en stærk krog i indledningen."
        }

    st.subheader("Job Detaljer")
    c1, c2 = st.columns(2)
    with c1: company = st.text_input("Virksomhedens navn:")
    with c2: title = st.text_input("Jobtitel:")
    
    job_url = st.text_input("Link til jobopslag (URL):")
    job_desc_manual = st.text_area("Eller indsæt jobtekst her:", height=150)

    if st.button("Analysér & Generér Ansøgning ✨"):
        if not api_key:
            st.error("OpenAI API-nøgle mangler i Streamlit Secrets.")
        elif not uploaded_cv or not company or (not job_url and not job_desc_manual):
            st.error("Husk at uploade CV og udfylde jobdetaljer.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cv_text = extract_text_from_pdf(uploaded_cv)
                
                job_text = job_desc_manual
                if job_url:
                    with st.spinner("Henter tekst fra jobopslag..."):
                        fetched = get_text_from_url(job_url)
                        if len(fetched) > 150: job_text = fetched

                # --- TRIN 1: ATS ANALYSE ---
                with st.spinner("Kører ATS-scanning og match-analyse..."):
                    analysis_prompt = f"""
                    Analysér jobopslaget og CV'et som en HR-robot (ATS):
                    1. List de 5 vigtigste nøgleord (kompetencer/software/metoder).
                    2. Identificér mangler (gaps) i CV'et ift. jobbet.
                    3. Giv en kort vurdering af matchet.
                    
                    Job: {job_text[:2500]}
                    CV: {cv_text[:2500]}
                    """
                    analysis_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en ATS-ekspert."},
                                  {"role": "user", "content": analysis_prompt}]
                    )
                    analysis_content = analysis_res.choices[0].message.content
                    st.info("📊 **ATS Match Analyse:**\n\n" + analysis_content)

                # --- TRIN 2: GENERERING ---
                with st.spinner("Skriver din optimerede ansøgning..."):
                    tone_desc = tone_prompts[selected_tone]
                    ans_prompt = f"""
                    Skriv en målrettet ansøgning til {title} hos {company}.
                    
                    TONE: {tone_desc}
                    
                    ATS-STRATEGI:
                    - Inkorporér nøgleord naturligt fra analysen.
                    - Adressér proaktivt eventuelle mangler i CV'et ved at fokusere på motivation eller lignende kompetencer.
                    
                    Analyse: {analysis_content}
                    CV: {cv_text}
                    Jobopslag: {job_text}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en professionel karriererådgiver."},
                                  {"role": "user", "content": ans_prompt}]
                    )
                    ans_text = response.choices[0].message.content
                    
                    # Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?, ?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, job_text, selected_tone))
                    conn.commit()
                    conn.close()
                    
                    st.divider()
                    st.subheader("📝 Resultat")
                    st.write(ans_text)
                    
                    # DOWNLOAD SEKTION
                    st.divider()
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        if uploaded_template:
                            w_file = fill_word_template(uploaded_template, ans_text, company)
                            if w_file:
                                st.download_button("Hent Word-fil 📄", w_file, f"Ansogning_{company}.docx")
                        else:
                            st.warning("Upload skabelon for Word-fil")
                    with d2:
