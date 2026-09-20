# ============================================================================
# Dockerfile — package CareRAG to run anywhere as one container.
#
# It runs the Streamlit chat UI (ui/streamlit_direct.py), which calls the RAG
# logic in-process — so a single container is the whole app. The database
# (Supabase) and AI (Gemini) are remote services configured via env vars.
#
# BUILD:  docker build -t carerag .
# RUN:    docker run -p 8501:8501 \
#             -e DATABASE_URL="<your supabase pooler uri>" \
#             -e GEMINI_API_KEY_1="<your gemini key>" \
#             -e SIMILARITY_THRESHOLD=0.8 \
#             carerag
# Then open http://localhost:8501
# ============================================================================

# Python 3.11 slim — small image, matches our runtime.txt.
FROM python:3.11-slim

# Set the working directory inside the container.
WORKDIR /app

# Install Python dependencies first (this layer is cached unless requirements
# change, so rebuilds are faster).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project into the image.
COPY . .

# Streamlit serves on 8501 by default.
EXPOSE 8501

# Create the database tables (safe to run repeatedly), then start the UI.
# --server.address 0.0.0.0 makes it reachable from outside the container.
CMD python -m app.database && \
    streamlit run ui/streamlit_direct.py \
    --server.port 8501 --server.address 0.0.0.0
