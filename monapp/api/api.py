"""
API FastAPI pour le modele de reconnaissance d'entites nommees (NER) SunuNER.
Sert le modele CamemBERT fine-tune (experimentation E3) pour l'extraction
d'entites nommees en francais contextualisees au Senegal.

Lancement :
    uvicorn api:app --reload --host 0.0.0.0 --port 8000

Variable d'environnement :
    MODEL_DIR : chemin vers le dossier du modele sauvegarde
                (par defaut "./model" -- voir README.md)
"""

import os
from contextlib import asynccontextmanager
from typing import List

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

MODEL_DIR = os.environ.get("MODEL_DIR", "./model")

ner_pipeline = None  # charge au demarrage (voir lifespan)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ner_pipeline
    if not os.path.isdir(MODEL_DIR):
        raise RuntimeError(
            f"Dossier du modele introuvable : {MODEL_DIR}. "
            "Definissez la variable d'environnement MODEL_DIR ou copiez le modele "
            "sauvegarde a cet emplacement (voir README.md)."
        )
    device = 0 if torch.cuda.is_available() else -1
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForTokenClassification.from_pretrained(MODEL_DIR)
    ner_pipeline = pipeline(
        "ner",
        model=model,
        tokenizer=tokenizer,
        aggregation_strategy="first",
        device=device,
    )
    print(f"Modele NER charge depuis {MODEL_DIR} (device={'GPU' if device == 0 else 'CPU'}).")
    yield
    ner_pipeline = None


app = FastAPI(
    title="SunuNER API",
    description="API de reconnaissance d'entites nommees en francais, contextualisee au Senegal.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS ouvert pour permettre a l'interface Streamlit (ou tout autre client local) d'appeler l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Texte en francais a analyser")


class BatchPredictRequest(BaseModel):
    texts: List[str] = Field(..., min_items=1, description="Liste de textes a analyser")


class Entity(BaseModel):
    text: str
    label: str
    start: int
    end: int
    score: float


class PredictResponse(BaseModel):
    text: str
    entities: List[Entity]


def _run_ner(text: str) -> List[Entity]:
    raw = ner_pipeline(text)
    entities = []
    for ent in raw:
        entities.append(Entity(
            #text=ent["word"],
            text=text[int(ent["start"]):int(ent["end"])],
            label=ent["entity_group"],
            start=int(ent["start"]),
            end=int(ent["end"]),
            score=float(ent["score"]),
        ))
    return entities


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": ner_pipeline is not None, "model_dir": MODEL_DIR}


@app.get("/labels")
def labels():
    if ner_pipeline is None:
        raise HTTPException(status_code=503, detail="Modele non charge.")
    id2label = ner_pipeline.model.config.id2label
    # Retire les prefixes BIO (B-/I-) et deduplique
    unique_labels = sorted({l.split("-", 1)[-1] for l in id2label.values() if l != "O"})
    return {"labels": unique_labels}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    if ner_pipeline is None:
        raise HTTPException(status_code=503, detail="Modele non charge.")
    entities = _run_ner(req.text)
    return PredictResponse(text=req.text, entities=entities)


@app.post("/predict_batch", response_model=List[PredictResponse])
def predict_batch(req: BatchPredictRequest):
    if ner_pipeline is None:
        raise HTTPException(status_code=503, detail="Modele non charge.")
    return [PredictResponse(text=t, entities=_run_ner(t)) for t in req.texts]
