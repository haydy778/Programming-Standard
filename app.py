# from flask import Flask, request, jsonify
# from flask_cors import CORS
# from pdf2image import convert_from_path
# from pytesseract import image_to_string
# import sqlite3
# import os
# os.environ['PATH'] += ':/opt/homebrew/bin'

# # Initialize the Flask application
# app = Flask(__name__)
# CORS(app)  # Enable CORS for all routes

# # Initialize SQLite Database
# conn = sqlite3.connect('pdf_texts.db', check_same_thread=False)
# c = conn.cursor()

# # Create a table if it doesn't exist
# c.execute('''
# CREATE TABLE IF NOT EXISTS pdf_texts (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     filename TEXT,
#     content TEXT
# )
# ''')
# conn.commit()

# def pdf_to_text(pdf_path):
#     pages = convert_from_path(pdf_path)
#     text = ""
    
#     for page in pages:
#         text += image_to_string(page)

#     # Replace multiple newlines with a single space
#     readable_text = text.replace('\n', ' ')
    
#     # Optionally, you can remove extra spaces as well
#     readable_text = ' '.join(readable_text.split())
    
#     return readable_text


# def index_pdf(filename, content):
#     """Insert the extracted text into the database."""
#     print(f"Indexing text for {filename}...")
#     print(f"Content: {content[:1000]}")  # Preview first 1000 characters
#     c.execute("INSERT INTO pdf_texts (filename, content) VALUES (?, ?)", (filename, content))
#     conn.commit()

# @app.route('/process_pdf')
# def process_pdf():
#     # Assuming the PDF is in the same directory as app.py
#     pdf_path = 'The_Southlandian_2019.pdf'
    
#     # Extract text from PDF
#     readable_text = pdf_to_text(pdf_path)
    
#     # Index the extracted text in the database
#     index_pdf(pdf_path, readable_text)
    
#     return jsonify({'message': 'PDF processed and text indexed successfully.'})

# @app.route('/search')
# def search():
#     query = request.args.get('query')
#     if query:
#         c.execute("SELECT filename, content FROM pdf_texts WHERE content LIKE ?", ('%' + query + '%',))
#         results = c.fetchall()
#         print(f"Searching for: {query}")
#         print(f"Search results: {results}")
#         return jsonify(results=[{'filename': r[0], 'content': r[1][:500] + '...'} for r in results])
#     return jsonify(results=[])

# if __name__ == '__main__':
#     app.run(debug=True)

from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
from pdf2image import convert_from_path
from pytesseract import image_to_string
import sqlite3
import os

# Set the PATH for Tesseract (adjust as needed for your environment)
os.environ['PATH'] += ':/opt/homebrew/bin'

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
    """Convert PDF pages to text."""
    try:
        pages = convert_from_path(pdf_path)
        text = ""
        for page in pages:
            text += image_to_string(page)
        
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

@app.route('/')
def index():
    """Render the HTML page."""
    return render_template('index.html')

@app.route('/process_pdf', methods=['POST'])
def process_pdf():
    """Handle PDF upload and processing."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected for uploading'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        pdf_path = os.path.join('uploads', file.filename)
        os.makedirs('uploads', exist_ok=True)
        file.save(pdf_path)

        readable_text = pdf_to_text(pdf_path)

        # Print the text to check if it includes the rugby information
        print(f"Extracted text from {file.filename}: {readable_text[:2000]}")  # Print first 2000 characters

        db = get_db()
        index_pdf(db, file.filename, readable_text)

        return jsonify({'message': f'PDF {file.filename} processed and text indexed successfully.'})

    except Exception as e:
        print(f"Error in process_pdf: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/search')
def search():
    """Search for content in the indexed PDFs and return a single paragraph without duplicates."""
    query = request.args.get('query')
    if query:
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT filename, content FROM pdf_texts WHERE content LIKE ?", ('%' + query + '%',))
            results = cursor.fetchall()

            combined_snippets = []
            for r in results:
                content = r[1].lower()
                query_lower = query.lower()
                start_index = 0

                # Find all occurrences of the query in the content
                while start_index < len(content):
                    start_index = content.find(query_lower, start_index)
                    if start_index == -1:
                        break
                    
                    # Define the range to extract a snippet around the occurrence of the query
                    snippet_start = max(start_index - 0, 0)  # Get 50 characters before the match
                    snippet_end = min(start_index + 1000 + len(query_lower), len(content))  # Get 50 characters after the match
                    snippet = r[1][snippet_start:snippet_end]

                    # Check if this snippet is already in the list to prevent duplicates
                    if snippet not in combined_snippets:
                        combined_snippets.append(snippet)

                    start_index += len(query_lower)  # Move to the next occurrence

            # Join all unique snippets into a single paragraph
            final_result = ' ... '.join(combined_snippets).strip()

            # Highlight the query term in the final result
            highlighted_text = final_result.replace(query, f"<mark>{query}</mark>")

            # Return as a single result
            return jsonify(results=[{'filename': results[0][0], 'content': '...' + highlighted_text + '...'}] if results else [])

        except Exception as e:
            print(f"Error in search: {e}")
            return jsonify({'error': 'Error performing search'}), 500

    return jsonify(results=[])


if __name__ == '__main__':
    app.run(debug=True)
