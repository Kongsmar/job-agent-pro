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
st.set_page_config(page_title="Job Agent Pro - ATS Optimized", page_icon="💼", layout="wide")
db_path = "job_archive_v9.db"

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

# --- APP LAYOUT ---
st.title("💼 Job Agent Pro")
st.caption("Optimeret til at passere ATS-systemer og HR-robotter")

tabs = st.tabs(["🚀 Analyse & Ansøgning", "📁 Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Konfiguration")
        api_key = st.secrets.get("OPENAI_API_KEY")
        uploaded_cv = st.file_uploader("1. Upload dit CV (PDF)", type="pdf")
        
        st.divider()
        st.subheader("🎭 Personligheds-filter")
        tone_options = ["Meget Formel", "Professionel", "Balanceret", "Personlig", "Kreativ"]
        selected_tone = st.select_slider("Vælg toneleje:", options=tone_options, value="Balanceret")
        
        tone_prompts = {
            "Meget Formel": "meget formel, korrekt og konservativ.",
            "Professionel": "saglig, forretningsorienteret og kompetent.",
            "Balanceret": "professionel men imødekommende og balanceret.",
            "Personlig": "varm, autentisk og fortællende.",
            "Kreativ": "modig, sprudlende og unik."
        }

    st.subheader("Job Detaljer")
    c1, c2 = st.columns(2)
    with c1: company = st.text_input("Virksomhed:")
    with c2: title = st.text_input("Jobtitel:")
    
    job_url = st.text_input("Link til jobopslag:")
    job_desc_manual = st.text_area("Eller indsæt jobtekst her:", height=150)

    if st.button("Kør ATS-Analyse & Skriv Ansøgning ✨"):
        if not api_key or not uploaded_cv or (not job_url and not job_desc_manual):
            st.error("Udfyld venligst alle felter.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cv_text = extract_text_from_pdf(uploaded_cv)
                job_text = job_desc_manual
                if job_url:
                    with st.spinner("Henter jobbeskrivelse..."):
                        url_text = get_text_from_url(job_url)
                        if len(url_text) > 100: job_text = url_text

                # --- TRIN 1: ATS & MATCH ANALYSE ---
                st.divider()
                with st.spinner("Udfører ATS-scanning..."):
                    analysis_prompt = f"""
                    Du er en ATS-optimeringsmaskine (HR-robot). Analyser følgende:
                    1. Identificer de 5 vigtigste nøgleord (hard skills/teknologier) fra jobopslaget.
                    2. Hvilke 'bløde' kompetencer efterspørges mest?
                    3. Find de største 'gaps' mellem CV og jobopslag.
                    
                    Job: {job_text[:2500]}
                    CV: {cv_text[:2500]}
                    """
                    
                    analysis_res = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en ekspert i HR-teknologi og ATS-screening."},
                                  {"role": "user", "content": analysis_prompt}]
                    )
                    st.subheader("📊 ATS Match Analyse")
                    st.info(analysis_res.choices[0].message.content)

                # --- TRIN 2: ATS-OPTIMERET ANSØGNING ---
                with st.spinner("Skriver ansøgning..."):
                    tone_desc = tone_prompts[selected_tone]
                    ans_prompt = f"""
                    Skriv en ansøgning til {title} hos {company}. 
                    
                    REGLER FOR ATS-OPTIMERING:
                    1. Implementér naturligt de vigtigste nøgleord fundet i analysen: {analysis_res.choices[0].message.content}.
                    2. Tone: {tone_desc}.
                    3. Struktur: Sørg for at adressere 'gaps' ved at fokusere på hurtig indlæring eller overførbare evner.
                    4. Sørg for at sproget er menneskeligt og fængende, selvom nøgleordene er med.
                    
                    CV: {cv_text}
                    Jobopslag: {job_text}
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": "Du er en professionel dansk karriererådgiver specialiseret i at omgå screening-robotter."},
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
                    
                    st.subheader("📝 Din ATS-Optimerede Ansøgning")
                    st.write(ans_text)
                    st.download_button("Hent som PDF 📄", create_pdf(ans_text), f"Ansogning_{company}.pdf")
            
            except Exception as e:
                st.error(f"Fejl: {e}")
