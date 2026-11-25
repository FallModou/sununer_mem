
# Image Python officielle
FROM python:3.11-slim

# Répertoire de travail
WORKDIR /api

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MODEL_DIR=/api/model

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Installation des dépendances Python
# Mise à jour de pip
RUN pip install --no-cache-dir --upgrade pip

# Installation de PyTorch CPU
RUN pip install --no-cache-dir torch \
    --index-url https://download.pytorch.org/whl/cpu

# Installation des autres dépendances
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


# Copie du code de l'API
COPY api.py .

# Copie du modèle CamemBERT
COPY model/ ./model

# Port de l'API
EXPOSE 8000

# Lancement de FastAPI
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
