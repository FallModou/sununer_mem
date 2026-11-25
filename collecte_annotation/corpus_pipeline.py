#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pipeline de collecte et nettoyage de corpus SunuNER
(français uniquement — entités du contexte sénégalais).

Usage :
    python corpus_pipeline.py collect --urls urls.txt --out raw.jsonl
    python corpus_pipeline.py clean   --in raw.jsonl --out corpus_pretraite.jsonl
    python corpus_pipeline.py stats   --in corpus_pretraite.jsonl

Sortie : JSONL, une phrase par ligne :
    {"id": "...", "text": "...", "source": "seneweb.com",
     "url": "...", "date_collecte": "..."}

Ce fichier alimente ensuite Label Studio pour l'annotation PER/LOC/ORG/MISC
(cf. guide_annotation_v2.docx), puis ls_to_conll.py pour l'export CoNLL.
"""

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# 1. COLLECTE
# ---------------------------------------------------------------------------

def collect(urls_file: str, out_file: str, delay: float = 2.0) -> None:
    """Télécharge et extrait le texte principal de chaque URL avec trafilatura."""
    import trafilatura

    urls = [u.strip() for u in Path(urls_file).read_text(encoding="utf-8").splitlines()
            if u.strip() and not u.strip().startswith("#")]
    print(f"[collecte] {len(urls)} URLs à traiter")

    n_ok, n_fail = 0, 0
    with open(out_file, "a", encoding="utf-8") as f:
        for i, url in enumerate(urls, 1):
            try:
                html = trafilatura.fetch_url(url)
                if html is None:
                    raise RuntimeError("téléchargement échoué")
                text = trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=False,
                    favor_precision=True,
                )
                if not text or len(text) < 200:
                    raise RuntimeError("texte trop court ou vide")
                doc = {
                    "url": url,
                    "source": urlparse(url).netloc.replace("www.", ""),
                    "date_collecte": date.today().isoformat(),
                    "text": text,
                }
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
                n_ok += 1
                print(f"  [{i}/{len(urls)}] OK   {url}")
            except Exception as e:
                n_fail += 1
                print(f"  [{i}/{len(urls)}] ECHEC {url} ({e})")
            time.sleep(delay)

    print(f"[collecte] terminé : {n_ok} OK, {n_fail} échecs -> {out_file}")


# ---------------------------------------------------------------------------
# 2. NETTOYAGE + SEGMENTATION
# ---------------------------------------------------------------------------

# Abréviations fréquentes dans la presse sénégalaise (évite les fausses coupures)
ABREVIATIONS = {
    "M.", "Mme", "Mlle", "Dr", "Pr", "S.E.", "El", "Hadj", "St", "Ste",
    "art.", "cf.", "etc.", "ex.", "n°", "p.", "vol.",
}


def normaliser(texte: str) -> str:
    """Normalisation Unicode + espaces + ponctuation typographique."""
    texte = unicodedata.normalize("NFC", texte)
    texte = texte.replace("\u2019", "'").replace("\u2018", "'")
    texte = texte.replace("\u00ab", '"').replace("\u00bb", '"')
    texte = texte.replace("\u201c", '"').replace("\u201d", '"')
    texte = re.sub(r"[ \t\u00a0\u202f]+", " ", texte)
    texte = re.sub(r"\n{2,}", "\n", texte)
    return texte.strip()


def est_bruit(ligne: str) -> bool:
    """Filtre les lignes de navigation, mentions légales, etc."""
    l = ligne.strip().lower()
    if len(l) < 15:
        return True
    motifs_bruit = (
        "cookies", "abonnez-vous", "newsletter", "copyright", "tous droits",
        "lire aussi", "à lire aussi", "publié le", "mis à jour", "partager",
        "commentaires", "suivez-nous", "cliquez ici", "javascript",
    )
    return any(m in l for m in motifs_bruit)


def segmenter(texte: str) -> list:
    """Segmentation en phrases, robuste aux abréviations de la presse sénégalaise."""
    phrases = []
    for ligne in texte.split("\n"):
        if est_bruit(ligne):
            continue
        brut = re.split(r"(?<=[.!?\u2026])\s+(?=[A-ZÀ-ÖØ-Þ0-9\"'])", ligne.strip())
        buffer = ""
        for seg in brut:
            candidat = (buffer + " " + seg).strip() if buffer else seg
            dernier_mot = candidat.split()[-1] if candidat.split() else ""
            if dernier_mot in ABREVIATIONS:
                buffer = candidat
                continue
            buffer = ""
            phrases.append(candidat)
        if buffer:
            phrases.append(buffer)
    return [p for p in phrases if 4 <= len(p.split()) <= 80]


def dedup_key(phrase: str) -> str:
    """Clé de déduplication insensible à la casse/ponctuation."""
    p = re.sub(r"[^a-z0-9]+", "", phrase.lower())
    return hashlib.md5(p.encode("utf-8")).hexdigest()


def clean(in_file: str, out_file: str) -> None:
    """Nettoie, segmente et déduplique les documents collectés."""
    vus = set()
    n_docs, n_phrases, n_dupl = 0, 0, 0

    with open(in_file, encoding="utf-8") as fin, \
         open(out_file, "w", encoding="utf-8") as fout:
        for ligne in fin:
            doc = json.loads(ligne)
            n_docs += 1
            texte = normaliser(doc["text"])
            for phrase in segmenter(texte):
                cle = dedup_key(phrase)
                if cle in vus:
                    n_dupl += 1
                    continue
                vus.add(cle)
                n_phrases += 1
                rec = {
                    "id": f"{doc.get('source','?')}_{cle[:10]}",
                    "text": phrase,
                    "source": doc.get("source", ""),
                    "url": doc.get("url", ""),
                    "date_collecte": doc.get("date_collecte", ""),
                }
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[nettoyage] {n_docs} documents -> {n_phrases} phrases uniques "
          f"({n_dupl} doublons éliminés)")
    print(f"[nettoyage] écrit -> {out_file}")


# ---------------------------------------------------------------------------
# 3. STATISTIQUES
# ---------------------------------------------------------------------------

def stats(in_file: str) -> None:
    """Statistiques du corpus : par source, longueurs de phrases."""
    from collections import Counter
    sources, longueurs = Counter(), []
    with open(in_file, encoding="utf-8") as f:
        for ligne in f:
            rec = json.loads(ligne)
            sources[rec["source"]] += 1
            longueurs.append(len(rec["text"].split()))
    total = sum(sources.values())
    print(f"=== {total} phrases ===")
    print("\nPar source :")
    for k, v in sources.most_common(15):
        print(f"  {k:30s}: {v} ({100*v/total:.1f}%)")
    if longueurs:
        longueurs.sort()
        print(f"\nLongueur (tokens) : min={longueurs[0]}, "
              f"médiane={longueurs[len(longueurs)//2]}, max={longueurs[-1]}, "
              f"moyenne={sum(longueurs)/len(longueurs):.1f}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Pipeline corpus SunuNER (français)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("collect", help="Télécharger les articles")
    pc.add_argument("--urls", required=True, help="Fichier texte, une URL par ligne")
    pc.add_argument("--out", required=True, help="Sortie JSONL (documents bruts)")
    pc.add_argument("--delay", type=float, default=2.0, help="Pause entre requêtes (s)")

    pn = sub.add_parser("clean", help="Nettoyer, segmenter, dédupliquer")
    pn.add_argument("--in", dest="infile", required=True)
    pn.add_argument("--out", required=True)

    ps = sub.add_parser("stats", help="Statistiques du corpus nettoyé")
    ps.add_argument("--in", dest="infile", required=True)

    args = ap.parse_args()
    if args.cmd == "collect":
        collect(args.urls, args.out, args.delay)
    elif args.cmd == "clean":
        clean(args.infile, args.out)
    elif args.cmd == "stats":
        stats(args.infile)


if __name__ == "__main__":
    main()
