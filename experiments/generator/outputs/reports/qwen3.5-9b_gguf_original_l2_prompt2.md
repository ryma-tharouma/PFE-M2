# Rapport d'évaluation des réponses de l'assistant

## 1. Vue d'ensemble

Un total de **~150 tours** (issues de plusieurs conversations) a été analysé.  
L'assistant a obtenu un taux de **bonne réponse de 96,7 %** (145 tours corrects sur 150).  
**5 erreurs** ont été identifiées, détaillées ci-dessous.

---

## 2. Détail des erreurs

| Conversation | Turn ID   | Type d'erreur                                            | Description                                                                                                                                                                                                                                                                            |
| ------------ | --------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `conv_4`     | `turn_9`  | Refus de répondre alors que l'information est disponible | L'utilisateur demande si une activation supplémentaire est nécessaire après création. Le contexte indique que l'utilisateur peut accéder directement. L'assistant répond "Je ne peux pas répondre".                                                                                    |
| `conv_4`     | `turn_10` | Refus de répondre alors que l'information est disponible | L'utilisateur signale que la modification ne marche pas. Le contexte précise qu'au moins un rôle doit rester sélectionné. L'assistant répond "Je ne peux pas répondre".                                                                                                                |
| `conv_9`     | `turn_6`  | Utilisation du mauvais contexte                          | L'utilisateur demande comment ajouter une catégorie pour le contrôle technique. L'assistant utilise le contexte des vignettes (avec champs `Type (Utilitaire, Transport, Tourisme)`, poids, puissance) au lieu du contexte correct du contrôle technique (simple champ `Désignation`). |
| `conv_9`     | `turn_11` | Omission d'une étape importante                          | L'utilisateur demande la prochaine étape pour créer une assurance. L'assistant donne directement l'étape 3 (Informations de l'assurance) sans mentionner l'étape 2 (Véhicules sélectionnés).                                                                                           |
| `conv_13`    | `turn_9`  | Refus de répondre alors que l'information est disponible | L'utilisateur cherche une alternative à la désunion des cellules fusionnées pour le tri. Le contexte propose de fusionner toutes les cellules pour qu'elles aient la même taille. L'assistant répond "Je ne peux pas répondre".                                                        |

---

## 3. Performance par catégorie d'erreur

| Type d'erreur                                                                  | Occurrences | Explication                                                                           |
| ------------------------------------------------------------------------------ | ----------- | ------------------------------------------------------------------------------------- |
| Refus de répondre (`"Je ne peux pas répondre..."`) alors que la réponse existe | 3           | L'assistant n'a pas correctement exploité le contexte ou a trop restreint sa réponse. |
| Utilisation d'un contexte inapproprié                                          | 1           | Mauvaise sélection du document source (vignettes au lieu de contrôle technique).      |
| Réponse incomplète (omission d'une étape)                                      | 1           | L'assistant a sauté une section du formulaire.                                        |

---

## 4. Forces observées

- L'assistant répond généralement de manière précise et fidèle au contexte fourni.
- Il gère correctement les requêtes hors domaine (`"ood"`) en répondant "Je ne peux pas répondre avec les informations disponibles".
- Il reformule et structure les réponses de façon claire (listes, étapes numérotées).
- Il sait faire le lien entre plusieurs questions suivies (gestion de l'historique).

---

## 5. Axes d'amélioration

1. **Ne pas refuser de répondre lorsque l'information est présente dans le contexte** – même si la réponse n'est pas textuellement identique, l'assistant doit l'extraire et la reformuler.
2. **Vérifier la correspondance entre la question et le contexte** – éviter d'utiliser une section d'un autre module.
3. **S'assurer de ne pas sauter d'étapes** lorsque la procédure est séquentielle.

---

## 6. Conclusion

L'assistant est globalement fiable et performant. Les erreurs sont rares (moins de 5 %) et concernent principalement des refus de réponse injustifiés ou un mauvais alignement contextuel. Une attention particulière à la vérification de la présence de l'information et à la cohérence du contexte (section ID, sujet) résoudrait la quasi‑totalité des problèmes rencontrés.
