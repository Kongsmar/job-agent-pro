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
db_path = "job_archive_v5.db"

def init_db():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS archive
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  date TEXT, company TEXT, title TEXT, 
                  ansogning TEXT, opslag TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- HJÆLPEFUNKTIONER ---
def get_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Fjerner scripts og styles
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
    # Håndtering af specialtegn til PDF
    clean_text = text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 8, txt=clean_text)
    return pdf.output(dest='S').encode('latin-1')

def fill_word_template(template_file, content, company_name):
    try:
        doc = Document(template_file)
        data_map = {"{{ANSOGNING}}": content, "{{VIRKSOMHED}}": company_name, "{{DATO}}": datetime.now().strftime("%d. %m. %Y")}
        for p in doc.paragraphs:
            for key, value in data_map.items():
                if key in p.text:
                    p.text = p.text.replace(key, value)
        target_stream = io.BytesIO()
        doc.save(target_stream)
        target_stream.seek(0)
        return target_stream
    except: return None

# --- APP LAYOUT ---
st.title("💼 Din Personlige Job Agent")

tabs = st.tabs(["🚀 Ny Ansøgning", "📁 Permanent Arkiv"])

with tabs[0]:
    with st.sidebar:
        st.header("⚙️ Din Profil")
        api_key = st.secrets.get("OPENAI_API_KEY")
        st.divider()
        uploaded_cv = st.file_uploader("Upload dit CV (PDF)", type="pdf")
        uploaded_template = st.file_uploader("Upload Word-skabelon (.docx)", type="docx")

    st.subheader("Hvor er jobbet?")
    col1, col2 = st.columns(2)
    with col1: company = st.text_input("Virksomhedens navn:")
    with col2: title = st.text_input("Jobtitel:")
    
    # NYT: Mulighed for link
    job_url = st.text_input("Link til jobopslag (valgfrit):", placeholder="https://...")
    job_desc_manual = st.text_area("Eller indsæt jobteksten her:", height=200)

    if st.button("Generer & Arkiver ✨"):
        if not api_key:
            st.error("Indsæt venligst din OpenAI API-nøgle i Secrets.")
        elif not uploaded_cv or not company or (not job_url and not job_desc_manual):
            st.error("Udfyld venligst virksomhed, CV og enten link eller jobtekst.")
        else:
            try:
                # Find den tekst vi skal bruge til AI'en
                final_job_text = ""
                if job_url:
                    with st.spinner("Henter tekst fra link..."):
                        final_job_text = get_text_from_url(job_url)
                else:
                    final_job_text = job_desc_manual

                cv_text = extract_text_from_pdf(uploaded_cv)
                
                client = OpenAI(api_key=api_key)
                with st.spinner("ChatGPT skriver din ansøgning..."):
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Du er en professionel dansk karriererådgiver. Skriv en målrettet ansøgning baseret på CV og jobopslag."},
                            {"role": "user", "content": f"Firma: {company}. Titel: {title}. CV: {cv_text}. Opslag: {final_job_text}"}
                        ]
                    )
                    ans_text = response.choices[0].message.content
                    
                    # Gem i database
                    conn = sqlite3.connect(db_path)
                    c = conn.cursor()
                    c.execute("INSERT INTO archive (date, company, title, ansogning, opslag) VALUES (?, ?, ?, ?, ?)",
                              (datetime.now().strftime("%Y-%m-%d %H:%M"), company, title, ans_text, final_job_text))
                    conn.commit()
                    conn.close()
                    
                    st.divider()
                    st.success("Færdig!")
                    st.write(ans_text)
                    
                    # Downloads
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        if uploaded_template:
                            w_file = fill_word_template(uploaded_template, ans_text, company)
                            st.download_button("Hent Word-fil 📄", w_file, f"Ansogning_{company}.docx")
                    with c2:
                        st.download_button("Hent Ansøgning (.txt)", ans_text, f"Ansogning_{company}.txt")
                    with c3:
                        # Her gemmes den tekst AI'en læste som PDF
                        pdf_file = create_pdf(final_job_text)
                        st.download_button("Hent Opslag (PDF) 📄", pdf_file, f"Jobopslag_{company}.pdf")
            
            except Exception as e:
                st.error(f"Der opstod en fejl: {e}")

with tabs[1]:
    st.header("Tidligere Ansøgninger")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM archive ORDER BY id DESC", conn)
        conn.close()
        
        for i, row in df.iterrows():
            with st.expander(f"📌 {row['company']} - {row['title']} ({row['date']})"):
                ca, cb = st.columns(2)
                with ca:
                    st.subheader("Ansøgning")
                    st.write(row['ansogning'])
                    st.download_button("Download Ansøgning", row['ansogning'], f"Arkiv_{row['company']}.txt", key=f"a_{row['id']}")
                with cb:
                    st.subheader("Opslag (Gemt fra link/tekst)")
                    st.write(row['opslag'][:500] + "...") # Viser kun de første 500 tegn
                    pdf_arkiv = create_pdf(row['opslag'])
                    st.download_button("Download Opslag som PDF", pdf_arkiv, f"Arkiv_Opslag_{row['company']}.pdf", key=f"o_{row['id']}")
