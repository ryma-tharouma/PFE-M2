## Rapport d'évaluation : Ministral 8B (avec prompt v2)

### Résumé global

| Métrique                     | Valeur          |
| ---------------------------- | --------------- |
| **Générations analysées**    | 153             |
| **Exactitude fonctionnelle** | 135/153 (88.2%) |
| **Conformité au prompt**     | 5/153 (3.3%)    |
| **Temps moyen**              | ~180 secondes   |

---

### ❌ Liste des échecs par catégorie

#### 1. Refus de répondre (10 occurrences) – info disponible dans contexte

| #   | Conversation | Query                                                       |
| --- | ------------ | ----------------------------------------------------------- |
| 1   | c3t11        | "est ce que je peux ajouter un chauffeur comme personnel"   |
| 2   | c4t10        | "la modification ne marche pas"                             |
| 3   | c5t9         | "affectation personnel contient ordres de mission ?"        |
| 4   | c6t6         | "ajouter chauffeur comme personnel ?"                       |
| 5   | c7t6         | "c'est quoi Compte analytique ?"                            |
| 6   | c8t13        | "pourquoi certaines vignettes non modifiables ?"            |
| 7   | c9t12        | "est ce que cbn" (inintelligible)                           |
| 8   | c11t10       | "ne plus voir élément listes déroulantes mais déjà affecté" |
| 9   | c13t2        | "formules numéros colonne après retour à A1"                |
| 10  | c13t13       | "problème arrondi graphiques courbes/colonnes ?"            |

#### 2. OOD non conforme (6 occurrences) – réponse inventée

| #   | Conversation | Query                                        | Comportement                                   |
| --- | ------------ | -------------------------------------------- | ---------------------------------------------- |
| 1   | c4t5         | "dcr cbn"                                    | A inventé "Vos identifiants AD sont : dcr cbn" |
| 2   | c4t6         | "oui ca marche"                              | Message perso "Erreur de contexte"             |
| 3   | c7t5         | "ecris moi une lettre de motivation"         | A généré lettre complète (353s)                |
| 4   | c10t8        | "ahh ok c'est fais"                          | A répété réponse sur identifiants AD           |
| 5   | c13t7        | "comment faire une capture d'écran ?"        | A donné procédure Windows/Mac                  |
| 6   | c14t2        | "recréer profil - perte signatures/règles ?" | A répondu "Non" + procédure inventée           |

#### 3. Erreur d'interprétation (2 occurrences)

| #   | Conversation | Query                            | Réponse                    | Attendu                                     |
| --- | ------------ | -------------------------------- | -------------------------- | ------------------------------------------- |
| 1   | c9t11        | "donne moi la prochaine etape ?" | "cliquer sur Ajouter"      | "Section 2 : Véhicules Sélectionnés"        |
| 2   | c9t14        | "et pour motif"                  | a répondu sur observations | "Motif de restitution : Sélection du motif" |

---

### ✅ Ce qui fonctionne correctement

- **Exactitude fonctionnelle ~88%** : la plupart des réponses sont factuellement correctes
- **OOD occasionnellement conforme** : c5t1, c5t8, c7t4, c8t8, c12t8, c12t14 (6/12 réussis)

---

### ⚠️ Problèmes majeurs

1. **Lenteur extrême** : jusqu'à 594 secondes (10 minutes) pour conv_11
2. **Non-conformité totale** : 96.7% des réponses ajoutent mises en forme, exemples, remarques
3. **Refus fréquent** : 10 occurrences où l'info était disponible
4. **OOD non fiable** : 50% d'échec (réponses inventées)

---

### Verdict

**Ministral 8B : ❌ INUTILISABLE EN PRODUCTION**

- Temps de réponse trop long
- Non-respect systématique du prompt
- Invente des réponses pour l'OOD
