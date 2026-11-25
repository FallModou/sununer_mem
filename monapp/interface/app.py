"""
Interface Streamlit pour le modele SunuNER (reconnaissance d'entites nommees
en francais contextualisees au Senegal).

Lancement :
    streamlit run app.py

Variable d'environnement (optionnelle) :
    SUNUNER_API_URL : URL de l'API FastAPI (par defaut http://localhost:8000)
"""

import os
import html

import requests
import streamlit as st
import pandas as pd

DEFAULT_API_URL = os.environ.get("SUNUNER_API_URL", "http://localhost:8000")

st.set_page_config(page_title="SunuNER", page_icon="🇸🇳", layout="wide")

# Palette de couleurs par type d'entite (les types non listes recoivent une couleur de secours)
COLOR_PALETTE = {
    "PER": "#FFADAD",
    "LOC": "#9BF6FF",
    "ORG": "#FFD6A5",
    "MISC": "#CAFFBF",
    "ETH": "#BDB2FF",
    "REL": "#FFC6FF",
    "ADMIN": "#FDFFB6",
    "LANG": "#A0C4FF",
}
FALLBACK_COLORS = ["#E0E0E0", "#D0F4DE", "#F4D0D0", "#D0E4F4"]


def color_for_label(label: str, cache: dict) -> str:
    if label in COLOR_PALETTE:
        return COLOR_PALETTE[label]
    if label not in cache:
        cache[label] = FALLBACK_COLORS[len(cache) % len(FALLBACK_COLORS)]
    return cache[label]


def render_highlighted_text(text: str, entities: list) -> str:
    """Construit du HTML avec les entites surlignees, a afficher via st.markdown."""
    entities_sorted = sorted(entities, key=lambda e: e["start"])
    color_cache = {}
    out = []
    cursor = 0
    for ent in entities_sorted:
        start, end, label = ent["start"], ent["end"], ent["label"]
        if start < cursor:
            continue  # ignore les chevauchements eventuels
        out.append(html.escape(text[cursor:start]))
        color = color_for_label(label, color_cache)
        entity_text = html.escape(text[start:end])
        out.append(
            f'<mark style="background-color:{color}; padding:2px 4px; border-radius:4px; '
            f'margin:0 1px;">{entity_text}'
            f'<span style="font-size:0.7em; font-weight:bold; margin-left:4px; '
            f'text-transform:uppercase;">{label}</span></mark>'
        )
        cursor = end
    out.append(html.escape(text[cursor:]))
    return "".join(out)


st.title("🇸🇳 SunuNER — Reconnaissance d'entités nommées")
st.caption(
    "Extraction d'entités nommées en français, contextualisées aux entités sénégalaises "
    "(personnalités, lieux, organisations, institutions...)."
)

with st.sidebar:
    st.header("Configuration")
    api_url = st.text_input("URL de l'API", value=DEFAULT_API_URL)
    st.markdown("---")
    try:
        health_resp = requests.get(f"{api_url}/health", timeout=3).json()
        if health_resp.get("model_loaded"):
            st.success("API connectée — modèle chargé ✅")
        else:
            st.warning("API connectée, mais le modèle n'est pas chargé.")
    except requests.exceptions.RequestException:
        st.error(
            "Impossible de joindre l'API. Vérifiez qu'elle est bien lancée "
            "(`uvicorn api:app --port 8000`)."
        )

    st.markdown("---")
    st.subheader("Exemples")
    examples = [
        "Le BNDE a signé un partenariat avec l'ANSD ",
        "Modou Ndiaye, Saliou Diop et Khadim Faye sont venus à Touba pour célébrer le Magal ",
        "La cérémonie s'est tenue en présence de représentants de la "
        "CEDEAO et du maire de Saint-Louis.",
    ]
    for i, ex in enumerate(examples):
        if st.button(f"Exemple {i + 1}", key=f"ex_{i}"):
            st.session_state["text_input"] = ex

if "text_input" not in st.session_state:
    st.session_state["text_input"] = ""

text = st.text_area(
    "Texte à analyser",
    key="text_input",
    height=150,
    placeholder="Collez ou saisissez un texte en français ici...",
)

analyze = st.button("Analyser", type="primary")

if analyze:
    if not text.strip():
        st.warning("Veuillez saisir un texte à analyser.")
    else:
        try:
            with st.spinner("Analyse en cours..."):
                response = requests.post(f"{api_url}/predict", json={"text": text}, timeout=30)
            response.raise_for_status()
            result = response.json()
            entities = result["entities"]

            st.subheader("Texte annoté")
            if entities:
                st.markdown(render_highlighted_text(text, entities), unsafe_allow_html=True)
            else:
                st.info("Aucune entité détectée dans ce texte.")
                st.write(text)

            if entities:
                st.subheader(f"Entités détectées ({len(entities)})")
                df = pd.DataFrame(entities)[["text", "label", "start", "end", "score"]]
                df.columns = ["Entité", "Type", "Début", "Fin", "Confiance"]
                df["Confiance"] = (df["Confiance"] * 100).round(1).astype(str) + " %"
                st.dataframe(df, use_container_width=True, hide_index=True)

                st.subheader("Répartition par type")
                counts = pd.Series([e["label"] for e in entities]).value_counts()
                st.bar_chart(counts)

        except requests.exceptions.RequestException as e:
            st.error(f"Erreur lors de l'appel à l'API : {e}")
