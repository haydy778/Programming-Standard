from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import fitz  # PyMuPDF
import sqlite3
import os

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
    """Search for content in the indexed PDFs."""
    query = request.args.get('query')
    if query:
        try:
            db = get_db()
            cursor = db.cursor()
            
            # Fetch all PDFs containing the query (case-insensitive search)
            cursor.execute("SELECT filename, content FROM pdf_texts WHERE LOWER(content) LIKE ?", ('%' + query.lower() + '%',))
            results = cursor.fetchall()

            search_results = {}
            query_lower = query.lower()  # Convert the query to lowercase once for reuse

            for r in results:
                original_content = r[1]  # Original content for highlighting and snippet extraction
                lower_content = original_content.lower()  # Lowercase content for case-insensitive matching
                start_index = 0
                snippets = []  # Use a list to maintain order

                # Find all occurrences of the query in the content
                while start_index < len(lower_content):
                    start_index = lower_content.find(query_lower, start_index)
                    if start_index == -1:
                        break

                    # Create a snippet of text around the match (50 characters before and after)
                    snippet_start = max(start_index - 0, 0)
                    snippet_end = min(start_index + 2000 + len(query_lower), len(original_content))
                    snippet = original_content[snippet_start:snippet_end]

                    # Highlight the query in the snippet (case-insensitive matching)
                    snippet_highlighted = snippet.replace(original_content[start_index:start_index + len(query)], f"<mark>{original_content[start_index:start_index + len(query)]}</mark>", 1)

                    # Add the snippet to the list if it's not already there
                    if snippet_highlighted not in snippets:
                        snippets.append('...' + snippet_highlighted + '...')

                    # Move to the next occurrence of the query
                    start_index += len(query_lower)

                # Combine all unique snippets into one paragraph for each PDF
                if snippets:
                    if r[0] in search_results:
                        search_results[r[0]] += ' '.join(snippets)
                    else:
                        search_results[r[0]] = ' '.join(snippets)

            # Format the final output for JSON response
            final_results = [{'filename': filename, 'content': content} for filename, content in search_results.items()]
            return jsonify(results=final_results)

        except Exception as e:
            print(f"Error in search: {e}")
            return jsonify({'error': 'Error performing search'}), 500
    return jsonify(results=[])



if __name__ == '__main__':
    with app.app_context():
        process_pdfs_in_directory()  # Process and index all PDFs before starting the server
    app.run(debug=True)
