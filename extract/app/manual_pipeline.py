#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sys
from pathlib import Path
import yaml
from clean_data import clean_json_file
from extractor_level_2 import extract_pdf_to_json


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _slugify(value: str) -> str:
    value = (value or '').strip().lower()
    out = []
    for ch in value:
        if ch.isalnum():
            out.append(ch)
        elif ch in (' ', '-', '.', '_'):
            out.append('_')
    slug = ''.join(out).strip('_')
    while '__' in slug:
        slug = slug.replace('__', '_')
    return slug or 'app'


def _index_cleaned_json(app_key: str, cleaned_json_path: Path, config_path: Path) -> dict:
    prod_dir = _project_root() / 'prod'
    sys.path.insert(0, str(prod_dir))
    from chunker import Chunker
    from embedder import Embedder
    from vector_store import get_vector_db

    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    with open(cleaned_json_path, 'r', encoding='utf-8') as f:
        sections = json.load(f)

    if not isinstance(sections, list) or not sections:
        raise ValueError(f'No sections to index in {cleaned_json_path}')

    chunker = Chunker(cfg)
    chunks = chunker.process_sections(sections)
    if not chunks:
        raise ValueError('Chunker returned no chunks.')

    embedder = Embedder(cfg)
    texts = [c.get('embed_text', '') for c in chunks]
    embeddings = embedder.encode(texts)
    dim = len(embeddings[0])

    db = get_vector_db(cfg)
    if db.collection_exists(app_key):
        db.drop_collection(app_key)
    db.create_collection(name=app_key, dim=dim)

    records = [
        {'id': c.get('id', f'ch_{i:06d}'), 'dense': vec, 'payload': c.copy()}
        for i, (c, vec) in enumerate(zip(chunks, embeddings), start=1)
    ]
    db.upsert(name=app_key, records=records)
    db.close()

    return {'chunks': len(chunks), 'collection': app_key, 'dim': dim}


def run_pipeline(pdf_path: Path, app_key: str, skip_index: bool = False) -> dict:
    project_root = _project_root()
    extract_dir  = project_root / 'extract' / 'app'
    json_dir     = extract_dir / 'json'
    json_dir.mkdir(parents=True, exist_ok=True)

    # Étape 1 — extraction → produit nom.json + nom_2levels.json
    raw_json = Path(extract_pdf_to_json(str(pdf_path)))

    # Étape 2 — on cible uniquement le fichier 2 niveaux pour le nettoyage
    two_levels_json = raw_json.parent / (raw_json.stem + '_2levels.json')
    if not two_levels_json.exists():
        raise FileNotFoundError(f'Fichier 2-levels introuvable : {two_levels_json}')

    # Étape 3 — nettoyage → produit nom_2levels_cleaned.json
    cleaned_json = Path(clean_json_file(str(two_levels_json)))

    # Étape 4 — copie sous le nom attendu par Laravel : app_key_cleaned.json
    alias_cleaned = json_dir / f'{_slugify(app_key)}_cleaned.json'
    shutil.copyfile(cleaned_json, alias_cleaned)

    result = {
        'pdf_path':          str(pdf_path),
        'raw_json':          str(raw_json),
        'two_levels_json':   str(two_levels_json),
        'cleaned_json':      str(cleaned_json),
        'alias_cleaned_json': str(alias_cleaned),
    }

    if not skip_index:
        cfg_path = project_root / 'prod' / 'config.yaml'
        result['indexing'] = _index_cleaned_json(_slugify(app_key), alias_cleaned, cfg_path)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Extract + clean + index manual PDF for one app.')
    parser.add_argument('--pdf',        required=True,        help='Absolute path to PDF')
    parser.add_argument('--app-key',    required=True,        help='Application key/slug')
    parser.add_argument('--skip-index', action='store_true',  help='Run extract+clean only')
    args = parser.parse_args()

    pdf = Path(args.pdf).resolve()
    if not pdf.exists() or not pdf.is_file():
        print(json.dumps({'ok': False, 'error': f'Invalid PDF path: {pdf}'}))
        return 2

    try:
        result = run_pipeline(pdf, args.app_key, skip_index=args.skip_index)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())