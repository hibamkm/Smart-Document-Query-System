# Smart Document Query System
### Retrieval-Augmented AI for Intelligent Document Querying

> MCA Final Year Project | University of Calicut | 2025-26

---

## 🎯 Project Overview

An intelligent document querying system that allows users to upload PDF/TXT documents and ask questions in natural language. The system uses **Retrieval-Augmented Generation (RAG)** - combining semantic search with NLP to provide accurate, context-based answers extracted directly from uploaded documents.

**Key Features**:
- 📄 Upload PDF and TXT documents
- 🔍 Semantic search (understands meaning, not just keywords)
- 🤖 AI-powered answer extraction using DistilBERT
- 📍 Source attribution with page numbers
- 💾 Multi-document support
- 🔒 User authentication and session management
- 📱 Clean, responsive web interface
- 🌐 Offline capability (after initial setup)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- 8GB RAM minimum
- Internet connection (first run only - to download AI models)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/WebWurx/Smart-Document-Query-System.git
cd Smart-Document-Query-System
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
# OR
venv\Scripts\activate  # Windows
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run the application**
```bash
python app.py
```

5. **Open in browser**
```
http://localhost:5001
```

### First Run
- AI models will download automatically (~330MB)
- Takes ~2 minutes on fast internet
- After first run, works completely offline!

---

## 📖 How It Works

### The RAG Pipeline

```
1. Document Upload
   ├── Extract text from PDF/TXT
   ├── Clean and process text
   ├── Chunk into ~150-word sections
   └── Generate vector embeddings

2. Query Processing
   ├── Convert question to embedding
   ├── Find similar sections (cosine similarity)
   ├── Retrieve top relevant chunks
   └── Extract answer using QA model

3. Answer Display
   ├── Format and polish answer
   ├── Show source document
   ├── Display page numbers
   └── Store in history
```

### Example Usage

**Upload your documents:**
- Computer Science textbooks
- Research papers
- Course notes
- Study materials

**Ask questions naturally:**
- "What is SSL?"
- "Define encryption"
- "What are the types of malware?"
- "List the steps in SDLC"

**Get precise answers with sources:**
```
Answer: SSL stands for Secure Sockets Layer. It is a
cryptographic protocol designed to provide secure
communication over a computer network.

Source: network_security.pdf · p. 47
```

---

## 🛠️ Technology Stack

### Backend
- **Python 3.12** - Core language
- **Flask 3.0** - Web framework
- **SQLite** - Database
- **PyPDF2** - PDF text extraction

### AI/ML
- **sentence-transformers** - Semantic embeddings
- **transformers (HuggingFace)** - QA model (DistilBERT)
- **PyTorch** - Deep learning framework
- **scikit-learn** - Cosine similarity
- **NumPy** - Vector operations

### Frontend
- **HTML5/CSS3** - Structure and styling
- **Bootstrap 5** - Responsive UI
- **JavaScript** - Interactivity

---

## 📊 System Architecture

```
┌─────────────────────────────────────┐
│     User Interface (Web Browser)     │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│        Flask Application             │
│  ┌──────────┐  ┌─────────────────┐ │
│  │ Routes & │  │ Document        │ │
│  │ Sessions │  │ Processing      │ │
│  └──────────┘  └─────────────────┘ │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│          RAG Engine                  │
│  ┌──────────────┐  ┌─────────────┐ │
│  │ Embeddings   │  │ QA Model    │ │
│  │ (MiniLM)     │  │ (DistilBERT)│ │
│  └──────────────┘  └─────────────┘ │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│      Database (SQLite)               │
│  ┌─────┐ ┌─────────┐ ┌──────────┐  │
│  │Users│ │Documents│ │Sections  │  │
│  └─────┘ └─────────┘ └──────────┘  │
└─────────────────────────────────────┘
```

---

## 📁 Project Structure

```
Smart-Document-Query-System/
├── app.py                    # Flask routes and controllers
├── config.py                 # Configuration
├── database.py               # Database operations
├── document_processor.py     # PDF/TXT processing
├── retrieval.py              # RAG engine
├── requirements.txt          # Dependencies
├── PROJECT_DOCUMENTATION.md  # Detailed technical docs
├── CODE_AUDIT.md            # Code analysis report
├── smart_doc.db             # SQLite database
├── uploads/                 # Document storage
├── static/                  # CSS, JS, images
└── templates/               # HTML templates
    ├── register.html
    ├── login.html
    ├── query.html
    └── answer.html
```

---

## 🎓 Key Features Explained

### 1. Semantic Search
Unlike Ctrl+F which matches exact keywords, our system understands **meaning**:
- "What is SSL?" matches "Secure Sockets Layer is a protocol..."
- Uses 384-dimensional vector embeddings
- Cosine similarity finds semantically related content

### 2. Answer Extraction
Uses DistilBERT QA model trained on SQuAD dataset:
- Understands question context
- Extracts precise answer spans
- Post-processing for clean formatting

### 3. Query Type Detection
Automatically detects and optimizes for:
- **Definitions**: "What is X?" → Returns concise definition
- **Lists**: "What are the types of X?" → Returns bullet points
- **General**: Other questions → Extracts relevant answer

### 4. Source Attribution
Every answer shows:
- Document name
- Page numbers where answer was found
- Builds trust and allows verification

---

## 📈 Performance

Tested on MacBook (8GB RAM):
- **PDF Upload (10 pages)**: ~3 seconds
- **Query Processing**: ~2 seconds
- **Model Initialization**: ~5 seconds (first run only)
- **Accuracy**: 84% on test set (50 questions)

---

## 🔐 Security Note

**Current Implementation**: Plain text password storage
- ⚠️ Suitable for local/demo use only
- ⚠️ NOT production-ready

**For Production**: Implement password hashing
```python
from werkzeug.security import generate_password_hash, check_password_hash
```

---

## 🎯 Use Cases

### Students
- Quick lookup in textbooks
- Exam preparation
- Research paper analysis

### Professionals
- Legal document search
- Technical documentation
- Business report analysis

### Researchers
- Literature review
- Cross-document comparison
- Citation finding

---

## 🚧 Future Enhancements

### Planned Features
- [ ] Multi-file upload (drag & drop)
- [ ] Password hashing
- [ ] Export Q&A as PDF
- [ ] Document preview
- [ ] Multi-language support
- [ ] Image/Table extraction (OCR)
- [ ] Conversation history (multi-turn)

### Long-term Vision
- [ ] Cloud deployment (AWS/Azure)
- [ ] Mobile app (React Native)
- [ ] Real-time collaboration
- [ ] Advanced analytics dashboard
- [ ] Custom model fine-tuning

---

## 🐛 Known Limitations

1. **PDF Tables**: Tables may not extract correctly (text-based PDFs work best)
2. **Images**: Images and diagrams are ignored (text only)
3. **Very large PDFs**: 100+ pages may be slow to process
4. **Scanned PDFs**: Require OCR (not currently implemented)
5. **Password-protected PDFs**: Not supported

---

## 📚 Documentation

- **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)** - Complete technical documentation (60+ pages)
  - Detailed algorithm explanations
  - Database schema with ER diagrams
  - Implementation details
  - Testing results
  - Academic references

- **[CODE_AUDIT.md](CODE_AUDIT.md)** - Code complexity analysis
  - File-by-file review
  - Simplification recommendations
  - Best practices

---

## 🤝 Contributing

This is an academic project for MCA coursework. Feedback and suggestions welcome!

### How to Report Issues
1. Check existing issues
2. Create new issue with:
   - Clear description
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots if applicable

---

## 📝 License

This project is part of academic coursework at University of Calicut.

For educational and personal use. Commercial use requires permission.

---

## 👤 Author

**Hiba**
MCA Student
University of Calicut
Academic Year: 2025-26

---

## 🙏 Acknowledgments

- **Project Guide**: For valuable guidance and feedback
- **MCA Faculty**: For comprehensive curriculum
- **Classmates**: For testing and feedback
- **Open Source Community**: For amazing libraries
  - Hugging Face Transformers
  - Sentence Transformers
  - Flask
  - PyPDF2

---

## 📞 Contact

For questions or feedback about this project:
- GitHub Issues: [Create an issue](https://github.com/WebWurx/Smart-Document-Query-System/issues)
- Email: [Your university email if you want to add]

---

## ⭐ References

1. Lewis et al. (2020) - "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"
2. Devlin et al. (2018) - "BERT: Pre-training of Deep Bidirectional Transformers"
3. Reimers & Gurevych (2019) - "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks"

---

**Made with ❤️ for MCA Final Year Project**

*Last Updated: June 2026*
