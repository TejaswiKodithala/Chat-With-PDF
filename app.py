import os
import re
from flask import Flask, request, jsonify, render_template
import pdfplumber
import PyPDF2
from sentence_transformers import SentenceTransformer, util

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Global variables
text_chunks = []
embeddings = None
model = SentenceTransformer('all-MiniLM-L6-v2')  # Semantic embedding model

# Function to extract text from PDF
def extract_text_from_pdf(pdf_path):
    text = []
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                paragraphs = page_text.split('\n\n')  # Split into paragraphs
                text.extend([p.strip() for p in paragraphs if p.strip()])
    return text

# Function to extract tables from PDF
def extract_tables_from_pdf(pdf_path, page_number):
    with pdfplumber.open(pdf_path) as pdf:
        if page_number <= len(pdf.pages):
            page = pdf.pages[page_number - 1]
            tables = page.extract_tables()
            if tables:
                return tables
    return []

# Function to extract page number from query
def extract_page_number(query):
    match = re.search(r'page\s*(\d+)', query.lower())
    if match:
        return int(match.group(1))
    return None

# Route: Home page
@app.route('/')
def home():
    return render_template('index.html')

# Route: Upload PDF
@app.route('/upload', methods=['POST'])
def upload_pdf():
    global text_chunks, embeddings
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Save uploaded PDF
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], "uploaded.pdf")
    file.save(file_path)

    # Extract text from PDF
    text_chunks = extract_text_from_pdf(file_path)
    if not text_chunks or all(chunk.strip() == '' for chunk in text_chunks):
        return jsonify({'error': 'No text found in PDF'}), 400

    # Generate embeddings
    embeddings = model.encode(text_chunks, convert_to_tensor=True)

    return jsonify({'message': 'PDF uploaded and processed successfully'})

# Route: Query PDF
@app.route('/query', methods=['POST'])
def query_pdf():
    global text_chunks, embeddings
    if not text_chunks or embeddings is None:
        return jsonify({'error': 'No PDF processed yet'}), 400

    query = request.json.get('query', '').lower()
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    # Check for table queries
    if "table" in query or "tabular" in query:
        page_number = extract_page_number(query)
        if page_number is None:
            return jsonify({'error': 'No valid page number found in query.'})
        
        try:
            tables = extract_tables_from_pdf(os.path.join(app.config['UPLOAD_FOLDER'], "uploaded.pdf"), page_number)
            if tables:
                # Return tables as structured JSON
                structured_tables = [{'row': row} for row in tables[0]]  # First table
                return jsonify({'response': structured_tables})
            else:
                return jsonify({'response': 'No tables found on the specified page.'})
        except Exception as e:
            return jsonify({'error': f'Error processing table query: {e}'})

     #Semantic search
    query_embedding = model.encode(query, convert_to_tensor=True)
    similarities = util.pytorch_cos_sim(query_embedding, embeddings).squeeze()

    # Get the best match
    best_match_idx = similarities.argmax().item()
    best_score = similarities[best_match_idx].item()

    # Set a threshold for similarity (adjust as needed)
    similarity_threshold = 0.2

    if best_score < similarity_threshold:
        return jsonify({
            'response': f'No exact match found for your query: "{query}". Please try rephrasing or provide more specific details.'
        })

    response = text_chunks[best_match_idx]
    return jsonify({
        'response': response,
        'query': query
    })


if __name__ == '__main__':
    app.run(debug=True)
