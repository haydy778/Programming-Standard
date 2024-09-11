import requests
import json
import fitz  # PyMuPDF
import os

def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def find_relevant_sections(text, query):
    sections = []
    for line in text.split('\n'):
        if query.lower() in line.lower():
            sections.append(line)
    return sections

def summarize_text_with_groqcloud(text, num_sentences=100):
    api_url = "https://api.groq.com/openai/v1/models"  # Example URL, replace with the actual endpoint
    api_key = "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"  # Replace with your API key

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "text": text,
        "num_sentences": num_sentences
    }
    
    response = requests.post(api_url, headers=headers, data=json.dumps(payload))
    
    if response.status_code == 200:
        summary = response.json().get("summary")
        return summary
    else:
        raise Exception(f"API request failed with status code {response.status_code}: {response.text}")

def summarize_pdfs_in_directory(directory_path, query, num_sentences=100):
    summaries = {}
    for filename in os.listdir(directory_path):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(directory_path, filename)
            text = extract_text_from_pdf(pdf_path)
            relevant_sections = find_relevant_sections(text, query)
            summarized_text = summarize_text_with_groqcloud('\n'.join(relevant_sections), num_sentences=num_sentences)
            summaries[filename] = summarized_text
    return summaries

# Example usage
directory_path = 'pdf_files'
query = 'rugby'
pdf_summaries = summarize_pdfs_in_directory(directory_path, query)

for pdf_file, summary in pdf_summaries.items():
    print(f"Summary for {pdf_file}:\n{summary}\n")

