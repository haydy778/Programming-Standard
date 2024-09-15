
from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import fitz  # PyMuPDF
import sqlite3
import os
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

app = Flask(__name__)
CORS(app)

DATABASE = 'pdf_texts.db'

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
        return readable_text
    except Exception as e:
        print(f"Error in pdf_to_text: {e}")
        return ""

def index_pdf(db, filename, content):
    """Insert PDF text into the database."""
    try:
        cursor = db.cursor()
        cursor.execute("INSERT INTO pdf_texts (filename, content) VALUES (?, ?)", (filename, content))
        db.commit()
    except Exception as e:
        print(f"Error in index_pdf: {e}")

def process_pdfs_in_directory():
    """Process all PDFs in the 'pdf_files' directory."""
    pdf_dir = 'pdf_files'
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)

    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(pdf_dir, filename)
            print(f"Processing {filename}...")
            readable_text = pdf_to_text(pdf_path)
            db = get_db()
            index_pdf(db, filename, readable_text)

@app.route('/')
def index():
    """Render the HTML page."""
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('query')
    if query:
        try:
            print(f"Received search query: {query}")  # Log the query

            db = get_db()
            print("Database connection established.")  # Log DB connection
            
            cursor = db.cursor()
            cursor.execute("SELECT filename, content FROM pdf_texts WHERE LOWER(content) LIKE ?", ('%' + query.lower() + '%',))
            results = cursor.fetchall()
            print(f"Search results: {results}")  # Log results fetched from DB

            search_results = {r[0]: r[1] for r in results}
            final_results = [{'filename': filename, 'content': content} for filename, content in search_results.items()]
            print(f"Final results: {final_results}")  # Log final results
            return jsonify(results=final_results)
        except Exception as e:
            print(f"Error during search: {e}")  # Log the exception
            return jsonify({'error': 'Error performing search'}), 500
    return jsonify(results=[])

def summarize_text(text, sentence_count=5):
    """Summarize the given text to a specified number of sentences."""
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary = summarizer(parser.document, sentence_count)
    return ' '.join(str(sentence) for sentence in summary)

if __name__ == '__main__':
    with app.app_context():
        init_db()  # Initialize the database
        process_pdfs_in_directory()  # Process and index all PDFs before starting the server
    app.run(debug=True)