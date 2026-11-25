#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversion Label Studio -> CoNLL (BIO).
Typologie SunuNER v2 : PER, LOC, ORG, MISC (français uniquement).

Usage :
    python ls_to_conll.py convert --in export_ls.json --out corpus.conll

Entrée : export JSON de Label Studio (format standard "JSON", pas JSON-MIN),
avec la configuration d'étiquetage à 4 labels (label_config.xml v2).
"""

import argparse
import json
import re
from collections import Counter, defaultdict

TYPES_VALIDES = {"PER", "LOC", "ORG", "MISC"}

# Tokenisation avec offsets : clitiques élidés séparés (d', l', qu'...) | mots | nombres | ponctuation
TOKEN_RE = re.compile(
    r"[0-9]+(?:[.,][0-9]+)*"
    r"|[cdjlmnstCDJLMNST]['\u2019]|[qQ]u['\u2019]|[jJ]usqu['\u2019]|[lL]orsqu['\u2019]|[pP]uisqu['\u2019]"
    r"|[^\W\d_]+(?:['\u2019][^\W\d_]+)*"
    r"|[^\w\s]",
    re.UNICODE)


def tokeniser(texte: str):
    """Retourne [(token, debut, fin), ...]"""
    return [(m.group(), m.start(), m.end()) for m in TOKEN_RE.finditer(texte)]


def extraire_spans(task: dict):
    """Extrait les empans (start, end, label) d'une tâche Label Studio, filtrés
    sur la typologie PER/LOC/ORG/MISC (toute autre étiquette résiduelle d'une
    ancienne configuration est ignorée avec un avertissement)."""
    spans = []
    annotations = task.get("annotations") or task.get("completions") or []
    if not annotations:
        return spans
    for res in annotations[0].get("result", []):
        if res.get("type") != "labels":
            continue
        v = res["value"]
        label = v["labels"][0]
        if label not in TYPES_VALIDES:
            print(f"  [avertissement] étiquette inconnue '{label}' ignorée "
                  f"(tâche {task.get('id', '?')}) -- vérifiez la configuration Label Studio")
            continue
        spans.append((v["start"], v["end"], label))
    return sorted(spans)


def bio_tags(texte: str, spans):
    """Aligne les empans caractères sur les tokens -> liste (token, tag BIO)."""
    tokens = tokeniser(texte)
    tags = ["O"] * len(tokens)
    for (s, e, label) in spans:
        premier = True
        for i, (_, ts, te) in enumerate(tokens):
            if ts < e and te > s:
                tags[i] = ("B-" if premier else "I-") + label
                premier = False
    return [(tok, tag) for (tok, _, _), tag in zip(tokens, tags)]


def convert(in_file: str, out_file: str) -> None:
    with open(in_file, encoding="utf-8") as f:
        tasks = json.load(f)

    n_phrases, n_entites = 0, 0
    compteur = Counter()
    with open(out_file, "w", encoding="utf-8") as out:
        for task in tasks:
            texte = task["data"]["text"]
            spans = extraire_spans(task)
            source = task["data"].get("source", "?")
            out.write(f"# id = {task['data'].get('id', task.get('id', '?'))}\n")
            out.write(f"# source = {source}\n")
            for tok, tag in bio_tags(texte, spans):
                out.write(f"{tok}\t{tag}\n")
                if tag.startswith("B-"):
                    n_entites += 1
                    compteur[tag[2:]] += 1
            out.write("\n")
            n_phrases += 1

    print(f"[convert] {n_phrases} phrases, {n_entites} entités -> {out_file}")
    for label in sorted(TYPES_VALIDES):
        print(f"  {label:6s}: {compteur.get(label, 0)}")

def main():
    p = argparse.ArgumentParser(description="Label Studio -> CoNLL (PER/LOC/ORG/MISC)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("convert")
    pc.add_argument("--in", dest="infile", required=True)
    pc.add_argument("--out", required=True)

    args = p.parse_args()
    if args.cmd == "convert":
        convert(args.infile, args.out)


if __name__ == "__main__":
    main()
