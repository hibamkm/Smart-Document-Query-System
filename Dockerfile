FROM python:3.12-slim

# Hugging Face Spaces runs containers as UID 1000.
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    DATA_DIR=/home/user/data \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

# The default torch wheel bundles CUDA and runs to several GB. Spaces are
# CPU-only, so pull the CPU build first; it satisfies the pin in requirements.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.2.0 && \
    pip install --no-cache-dir -r requirements.txt

USER user

# Bake the models into the image. retrieval.py forces HuggingFace offline mode
# at import, so the weights must already be in HF_HOME before the app starts.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
from transformers import AutoTokenizer, AutoModelForQuestionAnswering; \
SentenceTransformer('all-MiniLM-L6-v2'); \
AutoTokenizer.from_pretrained('distilbert-base-cased-distilled-squad'); \
AutoModelForQuestionAnswering.from_pretrained('distilbert-base-cased-distilled-squad')"

COPY --chown=user:user . /app

RUN mkdir -p "$DATA_DIR"

EXPOSE 7860

# One worker only: each worker loads its own ~350MB copy of the model weights.
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "1", "--threads", "4", \
     "--timeout", "120", "--access-logfile", "-", "app:app"]
