import re
from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import fitz  # PyMuPDF
import sqlite3
import os
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
import logging

app = Flask(__name__)
CORS(app)

DATABASE = 'pdf_texts.db'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def get_db():
    """Open a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db

def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

app.teardown_appcontext(close_db)

def init_db():
    """Initialize the database with the necessary tables."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pdf_texts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            content TEXT NOT NULL
        )
    ''')
    db.commit()

def pdf_to_text(pdf_path):
    """Convert PDF pages to text using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text += page.get_text()

        readable_text = ' '.join(text.replace('\n', ' ').split())
        print(f"Extracted text for {pdf_path}: {readable_text[:500]}...")  # Print first 500 characters
        return readable_text
    except Exception as e:
        print(f"Error in pdf_to_text: {e}")
        return ""

def index_pdf(db, filename, content):
    """Insert PDF text into the database if not already present."""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM pdf_texts WHERE filename = ? AND content = ?", (filename, content))
        exists = cursor.fetchone()[0]
        if not exists:
            cursor.execute("INSERT INTO pdf_texts (filename, content) VALUES (?, ?)", (filename, content))
            db.commit()
        else:
            logger.info(f"Duplicate entry for {filename} detected, skipping insertion.")
    except Exception as e:
        logger.error(f"Error in index_pdf: {e}")

def process_pdfs_in_directory():
    """Process all PDFs in the 'pdf_files' directory."""
    pdf_dir = 'pdf_files'
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)

    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith('.pdf'):
            try:
                pdf_path = os.path.join(pdf_dir, filename)
                logger.info(f"Processing {filename}...")
                readable_text = pdf_to_text(pdf_path)
                db = get_db()
                index_pdf(db, filename, readable_text)
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")

@app.route('/')
def index():
    """Render the HTML page."""
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('query')
    if query:
        try:
            logger.debug(f"Received search query: {query}")

            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT filename, content FROM pdf_texts WHERE LOWER(content) LIKE ?", ('%' + query.lower() + '%',))
            results = cursor.fetchall()
            logger.debug(f"Search results: {results}")

            final_results = []
            seen_summaries = set()  # Track seen summaries

            for filename, content in results:
                relevant_content = extract_relevant_text(content, query)
                
                if relevant_content:
                    summary = summarize_text(relevant_content)
                    summary_hash = hash(summary)  # Create a hash of the summary

                    if summary_hash not in seen_summaries:
                        seen_summaries.add(summary_hash)
                        final_results.append({
                            'filename': filename,
                            'relevant_content': relevant_content,
                            'summary': summary
                        })
            
            logger.debug(f"Final results: {final_results}")
            return jsonify(results=final_results)
        except Exception as e:
            logger.error(f"Error during search: {e}", exc_info=True)
            return jsonify({'error': 'Error performing search'}), 500
    return jsonify(results=[])

def extract_relevant_text(content, query, window_size=100):
    """
    Extracts and merges relevant sections of the content where the query appears.
    Merges overlapping sections to avoid duplicates.
    """
    query = query.lower()
    content = content.lower()

    matches = [m.start() for m in re.finditer(query, content)]

    if not matches:
        return "No relevant content found for the query"

    relevant_texts = []
    current_start = max(0, matches[0] - window_size)
    current_end = min(len(content), matches[0] + window_size)

    for match in matches[1:]:
        start = max(0, match - window_size)
        end = min(len(content), match + window_size)

        if start <= current_end + 20:  # Allow a small gap to merge close ranges
            current_end = max(current_end, end)
        else:
            relevant_texts.append(content[current_start:current_end])
            current_start = start
            current_end = end

    relevant_texts.append(content[current_start:current_end])
    merged_text = ' ... '.join(relevant_texts)

    return merged_text if relevant_texts else "No relevant content found"

def summarize_text(text, sentence_count=5):
    """Summarize the given text to a specified number of sentences."""
    if len(text.strip()) < 100:
        return "Content too short to summarize"

    print(f"Text to summarize: {text[:500]}...")  # Print first 500 characters for verification
    
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary = summarizer(parser.document, sentence_count)
    return ' '.join(str(sentence) for sentence in summary)

if __name__ == '__main__':
    with app.app_context():
        init_db()
        process_pdfs_in_directory()
    app.run(debug=True)
