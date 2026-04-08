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
st.set_page_config(page_title="Job Agent Pro", page_icon="💼", layout="wide")
db_path = "job_archive_v6.db"

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
    except Exception as e:
        return f"Kunne ikke hente tekst fra linket: {e}"

def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    except:
        return None

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    # Håndtering af specialtegn til PDF (latin-1 dækker de fleste danske tegn)
    clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

def fill_word_template(template_file, content, company_name):
    try:
        doc = Document(template_file)
        data_map = {
            "{{ANSOGNING}}": content, 
            "{{VIRKSOMHED}}": company_name, 
            "{{DATO}}": datetime.now().strftime("%d. %m. %Y")
        }
        for p in doc.paragraphs:
            for key, value in data_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, value)
        target_stream = io.BytesIO()
        doc.save(target_stream)
        target_stream.seek(0)
        return target_stream
    except: return None

# --- TONE DEFINITIONER ---
tone_descriptions = {
    "Professionel": "afbalanceret, kompetent og målrettet. Brug et moderne forretningssprog.",
    "Formel": "meget høflig, respektfuld og traditionel. Brug vendinger som 'Jeg tillader mig at ansøge' og undgå forkortelser.",
    "Personlig": "varm, autentisk og fortællende. Fokusér på motivation og menneskelige værdier fremfor blot hårde kompetencer.",
    "Kreativ": "fangende, anderledes og modig. Brug en stærk overskrift og et legende sprog, der skiller sig ud.",
    "Humoristisk": "uformel, med glimt i øjet og masser af personlighed. Det skal være sjovt, men stadig seriøst omkring fagligheden."
}

# --- APP LAYOUT ---
st.title("💼 Din Personlige Job Agent")

tabs = st.tabs(["🚀 Ny Ansøgning", "📁 Permanent Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Din Profil")
        api_key = st.secrets.get("OPENAI_API_KEY")
        st.divider()
        uploaded_cv = st.file_uploader("1. Upload dit CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("2. Upload Word-skabelon (.docx)", type="docx")
        st.info("Husk koder i Word: {{ANSOGNING}}, {{VIRKSOMHED}}, {{DATO}}")

    st.subheader("Hvor er jobbet?")
    col1, col2, col3 = st.columns(3)
    with col1: 
        company = st.text_input("Virksomhedens navn:", placeholder="F.eks. Mærsk")
    with col2: 
        title = st.text_input("Jobtitel:", placeholder="F.eks. Marketing Manager")
    with col3: 
        selected_tone = st.selectbox("Ønsket sprog/tone:", list(tone_descriptions.keys()))
    
    st.divider()
    
    job_url = st.text_input("Link til jobopslag (valgfrit):", placeholder="Indsæt URL her...")
    job_desc_manual = st.text_area("Eller indsæt jobteksten her:", height=200, help="Hvis linket ikke virker, så kopier teksten herind.")

    if st.button("Generer & Arkiver ✨"):
        if not api_key:
            st.error("Indsæt venligst din OpenAI API-nøgle i Secrets.")
        elif not uploaded_cv or not company or (not job_url and not job_desc_manual):
            st.error("Udfyld venligst virksomhed, upload CV og angiv jobbeskrivelse.")
        else:
            try:
                # 1. Hent jobbeskrivelse
                final_job_text = ""
                if job_url:
                    with st.spinner("Henter tekst fra link..."):
                        fetched_text = get_text_from_url(job_url)
                        final_job_text = fetched_text if len(fetched_text) > 200 else job_desc_manual
                else:
                    final_job_text = job_desc_manual

                # 2. Læs CV
                cv_text = extract_text_from_pdf(uploaded_cv)
                
                # 3. Kald OpenAI
                client = OpenAI(api_key=api_key)
                with st.spinner(f"ChatGPT skriver en {selected_tone.lower()} ansøgning..."):
                    system_instruction = f"Du er en erfaren dansk karriererådgiver. Skriv en ansøgning, der er {tone_descriptions[selected_tone]}"
                    
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": f"Firma: {company}. Titel: {title}. CV info: {cv_text}. Jobopslag: {final_job_text}"}
                        ]
                    )
                    ans_text = response.choices[0].message.content
                    
                    # 4. Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag, tone) VALUES (?, ?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, final_job_text, selected_tone))
                    conn.commit()
                    conn.close()
                    
                    # 5. Vis resultat
                    st.divider()
                    st.success(f"Ansøgning genereret med en {selected_tone.lower()} tone!")
                    st.write(ans_text)
                    
                    # 6. Downloads
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if uploaded_template:
                            w_file = fill_word_template(uploaded_template, ans_text, company)
                            st.download_button("Hent Word-fil 📄", w_file, f"Ansogning_{company}.docx")
                        else:
                            st.warning("Upload skabelon for at hente Word-fil")
                    with c2:
                        st.download_button("Hent som ren tekst (.txt)", ans_text, f"Ansogning_{company}.txt")
                    with c3:
                        pdf_file = create_pdf(final_job_text)
                        st.download_button("Hent gemt opslag (PDF) 📄", pdf_file, f"Jobopslag_{company}.pdf")
            
            except Exception as e:
                st.error(f"Der opstod en fejl: {e}")

with tabs[1]:
    st.header("📁 Tidligere Ansøgninger")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
        conn.close()
        
        if df.empty:
            st.info("Arkivet er tomt endnu.")
        else:
            for i, row in df.iterrows():
                with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']}) - Tone: {row.get('tone', 'Standard')}"):
                    ca, cb = st.columns(2)
                    with ca:
                        st.subheader("Ansøgning")
                        st.write(row['ansogning'])
                        st.download_button("Download Tekst", row['ansogning'], f"Arkiv_{row['company']}.txt", key=f"a_{row['id']}")
                    with cb:
                        st.subheader("Originalt Opslag")
                        st.write(row['opslag'][:1000] + "..." if len(row['opslag']) > 1000 else row['opslag'])
                        pdf_arkiv = create_pdf(row['opslag'])
                        st.download_button("Download Opslag som PDF", pdf_arkiv, f"Arkiv_Opslag_{row['company']}.pdf", key=f"o_{row['id']}")
