#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_to_labelstudio.py — Convertit le clean.json (JSONL) produit par
corpus_pipeline.py en fichiers de tâches importables dans Label Studio.

Usage :
    python convert_to_labelstudio.py --in clean.json --out-dir tasks/ --batch-size 500

Chaque phrase du JSONL devient une tâche Label Studio :
    {
      "data": {
        "text": "...",
        "source": "seneweb.com",
        "lang": "fr",
        "url": "https://...",
        "corpus_id": "seneweb.com_ab12cd34ef"
      }
    }

Le split en plusieurs fichiers (batch-size) évite d'importer un unique
fichier de plusieurs milliers de tâches d'un coup, ce que Label Studio
gère mal au-delà de quelques milliers d'entrées.

Un tri optionnel (--sort-by-lang) place les phrases "mixte" en tête de
fichier, pour prioriser leur annotation en premier — ce sont les
phrases les plus rares et les plus importantes pour ta thèse.
"""

import argparse
import json
from pathlib import Path


def load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[WARN] ligne {line_no} ignorée (JSON invalide) : {e}")
    return records


def to_task(record: dict) -> dict:
    return {
        "data": {
            "text": record.get("text", ""),
            "source": record.get("source", ""),
            "url": record.get("url", ""),
            "corpus_id": record.get("id", ""),
            "date_collecte": record.get("date_collecte", ""),
        }
    }


def convert(in_file: str, out_dir: str, batch_size: int) -> None:
    records = load_jsonl(in_file)
    print(f"[conversion] {len(records)} phrases lues depuis {in_file}")

    

    tasks = [to_task(r) for r in records]

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    n_files = 0
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        file_path = out_path / f"tasks_batch_{i // batch_size + 1:03d}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, ensure_ascii=False, indent=2)
        n_files += 1
        print(f"  -> {file_path} ({len(batch)} tâches)")

    print(f"[conversion] terminé : {n_files} fichier(s) dans {out_dir}")
    print("Import dans Label Studio : Project > Import > glisser les fichiers "
          "tasks_batch_*.json (un import par fichier, ou tous en une fois).")


def main():
    parser = argparse.ArgumentParser(description="Convertit clean.json en tâches Label Studio")
    parser.add_argument("--in", dest="in_file", required=True, help="Fichier clean.json (JSONL)")
    parser.add_argument("--out-dir", default="tasks", help="Dossier de sortie pour les fichiers de tâches")
    parser.add_argument("--batch-size", type=int, default=500, help="Nombre de tâches par fichier")
    args = parser.parse_args()
    convert(args.in_file, args.out_dir, args.batch_size)


if __name__ == "__main__":
    main()
