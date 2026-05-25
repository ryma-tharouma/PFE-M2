import json
import re
import os
import sys
from copy import deepcopy


# ══════════════════════════════════════════════════════════════════
#  ÉTAPE 1 — Réparer les bullets cassés par l'extracteur
#  Le bug : "• \n**Matricule : ...**"  ← bullet vide + contenu en gras sur ligne suivante
# ══════════════════════════════════════════════════════════════════

def _fix_broken_bullets(text: str) -> str:

    # Bullet niveau 1 vide (•) + saut de ligne + contenu optionnellement entouré de **
    text = re.sub(
        r'•[ \t]*\n[ \t]*\*{0,2}([^\n*]+?)\*{0,2}[ \t]*(?=\n|$)',
        lambda m: f'• {m.group(1).strip()}',
        text
    )
    # Bullet niveau 2 vide (o) + saut de ligne + contenu
    text = re.sub(
        r'([ \t]*o)[ \t]*\n[ \t]*\*{0,2}([^\n*]+?)\*{0,2}[ \t]*(?=\n|$)',
        lambda m: f'{m.group(1)} {m.group(2).strip()}',
        text
    )
    return text


# ══════════════════════════════════════════════════════════════════
#  ÉTAPE 2 — Réparer le gras coupé en milieu de phrase
#  Bug extracteur : "**texte de fin de ligne** suite de la phrase"
#  Cela vient d'un saut de ligne PDF à l'intérieur d'un span bold
# ══════════════════════════════════════════════════════════════════

def _fix_split_bold(text: str) -> str:
    """
    Avant : "**Le bouton ouvre un pop-up avec un formulaire de** recherche :"
    Après  : "Le bouton ouvre un pop-up avec un formulaire de recherche :"

    Règle : si ** se ferme ET est immédiatement suivi par un mot en minuscule
            → c'est une coupure de ligne PDF, on soude et on retire les **
    """
    return re.sub(
        r'\*\*([^*\n]+?)\*\*[ \t]+([a-zà-ùœæçéèêëîïôùûü0-9«"\(])',
        r'\1 \2',
        text
    )




def _strip_bold_markers(text: str) -> str:
    return re.sub(r'\*{1,2}', '', text)


# ══════════════════════════════════════════════════════════════════
#  ÉTAPE 4 — Éclater les sous-bullets inline
#  Bug extracteur : "Liste déroulante : o Tous o Permis expiré o Autres"
#  → doit devenir trois lignes séparées
# ══════════════════════════════════════════════════════════════════

def _split_inline_o_bullets(line: str) -> str:
    """
    Détecte les lignes contenant plusieurs "o <texte>" consécutifs et les éclate.

    Avant : "Liste déroulante : o Tous les chauffeurs o Permis expiré o Autres"
    Après  :
        "Liste déroulante :"
        "  o Tous les chauffeurs"
        "  o Permis expiré"
        "  o Autres"
    """
    # On cherche au moins 2 occurrences de " o <mot>" dans la ligne
    if len(re.findall(r'(?<!\w)o\s+\w', line)) < 2:
        return line

    # Découpe sur les frontières " o " (précédées d'un non-mot ou d'espace)
    parts = re.split(r'(?<!\w)\bo\s+', line)
    prefix = parts[0].rstrip(' :')
    items  = [p.strip() for p in parts[1:] if p.strip()]

    if not items:
        return line

    result = (prefix + ' :') if prefix else ''
    subs   = '\n'.join(f'  o {item}' for item in items)
    return (result + '\n' + subs) if result else subs


def _fix_inline_o_bullets(text: str) -> str:
    lines = text.split('\n')
    return '\n'.join(_split_inline_o_bullets(l) for l in lines)


# ══════════════════════════════════════════════════════════════════
#  ÉTAPE 5 — Nettoyages finaux
# ══════════════════════════════════════════════════════════════════

def _final_cleanup(text: str) -> str:
    # Dé-escaper les guillemets  \" → "
    text = text.replace('\\"', '"')

    # Supprimer les numéros de page isolés sur leur propre ligne
    text = re.sub(r'(?m)^\s*\d{1,3}\s*$', '', text)

    # Fusionner les lignes TOC restantes (.......... 12)
    text = re.sub(r'(?m)^.*?\.{3,}\s*\d+\s*$', '', text)

    # Réduire les sauts de ligne multiples (>2) → double saut
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Supprimer les espaces/tabulations en fin de ligne
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)

    # Supprimer les lignes vides en début / fin
    return text.strip()


# ══════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════

def clean_content(text: str) -> str:
    """
    Applique le pipeline de nettoyage dans l'ordre correct.
    Chaque étape dépend des précédentes.
    """
    if not text:
        return text

    text = _fix_broken_bullets(text)   # 1. Réparer les bullets cassés
    text = _fix_split_bold(text)       # 2. Souder le gras coupé en milieu de phrase
    text = _strip_bold_markers(text)   # 3. Enlever les ** restants
    text = _fix_inline_o_bullets(text) # 4. Éclater les sous-bullets inline
    text = _final_cleanup(text)        # 5. Nettoyages finaux

    return text


def clean_section(section: dict) -> dict:
    """Nettoie uniquement le champ 'content', laisse tout le reste intact."""
    cleaned = deepcopy(section)
    cleaned['content'] = clean_content(section.get('content', ''))
    return cleaned


# ══════════════════════════════════════════════════════════════════
#  I/O
# ══════════════════════════════════════════════════════════════════

def clean_json_file(input_path: str, output_path: str = None) -> str:
    if output_path is None:
        base, ext  = os.path.splitext(input_path)
        output_path = f"{base}_cleaned{ext}"

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if isinstance(data, list):
        cleaned_data = [clean_section(s) for s in data]
    elif isinstance(data, dict):
        cleaned_data = clean_section(data)
    else:
        raise ValueError("Format JSON non reconnu (ni liste ni dict)")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)

    n = len(cleaned_data) if isinstance(cleaned_data, list) else 1
    print(f"✅  {output_path}")
    print(f"    {n} section(s) nettoyée(s)")
    return output_path


def clean_directory(dir_path: str):
    """Traite tous les .json du dossier (hors fichiers déjà _cleaned)."""
    files = [
        f for f in os.listdir(dir_path)
        if f.endswith('_2levels.json') and '_2levels_cleaned' not in f
    ]
    if not files:
        print(f"Aucun fichier JSON trouvé dans {dir_path}")
        return
    for fname in files:
        inp = os.path.join(dir_path, fname)
        out = os.path.join(dir_path, fname.replace('_2levels.json', '_2levels_cleaned.json'))
        clean_json_file(inp, out)



# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)

        sys.exit(0)

    target = sys.argv[1]

    if os.path.isdir(target):
        clean_directory(target)
    elif os.path.isfile(target):
        out = sys.argv[2] if len(sys.argv) > 2 else None
        clean_json_file(target, out)
    else:
        print(f"Erreur : '{target}' n'est pas un fichier ou dossier valide.")
        sys.exit(1)