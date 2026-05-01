# Rapport d'évaluation des performances de Llama

## 1. Vue d’ensemble

L’assistant **Llama** (modèle `llama_8b_gguf_original_l2_prompt2`) a été évalué sur **147 tours** de conversation couvrant plusieurs applications (manuel_parc_auto, manuel_bdm, Word, Excel, Outlook).  
**113 tours** ont été jugés corrects, **34 tours** comportaient une erreur, soit un taux de réussite de **76,9 %**.

---

## 2. Détail des erreurs par conversation

| Conversation | Tours évalués | Erreurs | Taux de réussite |
| ------------ | ------------- | ------- | ---------------- |
| conv_1       | 6             | 1       | 83,3 %           |
| conv_2       | 12            | 3       | 75,0 %           |
| conv_3       | 8             | 2       | 75,0 %           |
| conv_4       | 13            | 4       | 69,2 %           |
| conv_5       | 14            | 3       | 78,6 %           |
| conv_6       | 13            | 2       | 84,6 %           |
| conv_7       | 11            | 3       | 72,7 %           |
| conv_8       | 13            | 3       | 76,9 %           |
| conv_9       | 16            | 4       | 75,0 %           |
| conv_10      | 14            | 2       | 85,7 %           |
| conv_11      | 14            | 1       | 92,9 %           |
| conv_12      | 5             | 1       | 80,0 %           |
| conv_13      | 5             | 3       | 40,0 %           |
| conv_14      | 3             | 2       | 33,3 %           |
| **Total**    | **147**       | **34**  | **76,9 %**       |

---

## 3. Typologie des erreurs

Les 34 erreurs se répartissent en plusieurs catégories :

| Type d’erreur                                                | Nombre | Exemples                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------ | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Refus de répondre alors que l’information est disponible** | 16     | conv_4_turn_8, conv_4_turn_9, conv_4_turn_15, conv_5_turn_13, conv_5_turn_16, conv_6_turn_3, conv_6_turn_6, conv_7_turn_6, conv_7_turn_11, conv_8_turn_2, conv_8_turn_10, conv_8_turn_13, conv_9_turn_13, conv_9_turn_15, conv_10_turn_7, conv_10_turn_16 |
| **Hallucination (réponse inventée hors contexte)**           | 10     | conv_2_turn_13, conv_3_turn_11, conv_3_turn_15, conv_4_turn_6, conv_5_turn_1, conv_7_turn_5, conv_13_turn_2, conv_13_turn_7, conv_14_turn_2, conv_14_turn_10                                                                                              |
| **Réponse incomplète**                                       | 3      | conv_2_turn_6, conv_11_turn_6, conv_12_turn_5                                                                                                                                                                                                             |
| **Utilisation d’un contexte inapproprié**                    | 1      | conv_9_turn_6 (catégories de vignettes au lieu de catégories de contrôle technique)                                                                                                                                                                       |
| **Procédure incorrecte ou solution inefficace**              | 4      | conv_9_turn_5, conv_13_turn_9, (autres cas d’invention erronée)                                                                                                                                                                                           |

---

## 4. Analyse des forces et faiblesses

### Forces

- Réponses souvent conformes au contexte lorsque celui‑ci est simple et direct.
- Bonne gestion des requêtes hors domaine lorsque la réponse standard `"Je ne peux pas répondre avec les informations disponibles"` est utilisée (environ 70 % des OOD traités correctement).
- Structure claire des réponses (listes, étapes numérotées).

### Faiblesses principales

1. **Refus de répondre injustifié (47 % des erreurs)**  
   L’assistant répond `"Je ne peux pas répondre"` alors que la réponse existe explicitement dans le contexte.  
   _Exemples_ : demandes sur les identifiants Active Directory, les champs `Désignation`, la modification des utilisateurs, etc.

2. **Hallucination (29 % des erreurs)**  
   L’assistant invente des réponses détaillées sans aucun support contextuel, en particulier sur les sujets OOD (recette de cuisine, lettre de motivation, capture d’écran, partage OneDrive) et sur quelques questions internes (annulation d’affectation, correction de références croisées).

3. **Incomplétude ou procédure erronée**  
   Parfois l’assistant ne fournit qu’une partie de la solution (ex. omet l’étape 2 de la création d’assurance) ou propose une procédure qui ne résout pas le problème (ex. tri personnalisé avec cellules fusionnées).

4. **Confusion entre modules**  
   Utilisation d’un contexte de vignettes pour répondre à une question sur le contrôle technique.

---

## 5. Comparaison avec l’autre modèle (Qwen)

Le modèle **Qwen** (évalué sur 150 tours) affichait un taux de réussite de **96,7 %** avec seulement 5 erreurs, principalement des refus de répondre ou des omissions.  
Llama obtient un score nettement inférieur (76,9 %). Les principales différences :

| Critère                 | Qwen   | Llama                     |
| ----------------------- | ------ | ------------------------- |
| Refus injustifiés       | rare   | fréquent (16 occurrences) |
| Hallucinations          | aucune | 10 occurrences            |
| Réponses incomplètes    | 1      | 3                         |
| Taux de réussite global | ~97 %  | ~77 %                     |

---

## 6. Recommandations pour améliorer Llama

1. **Réduire les refus de répondre**  
   – Entraîner / paramétrer le modèle pour qu’il extraie systématiquement l’information du contexte, même si la formulation n’est pas textuellement identique.

2. **Éliminer les hallucinations**  
   – Renforcer la consigne OOD : ne jamais inventer une réponse. Utiliser strictement `"Je ne peux pas répondre avec les informations disponibles"` pour toute question non couverte par le contexte.

3. **Améliorer la complétude**  
   – Lorsqu’une procédure comporte plusieurs étapes (sections, onglets), s’assurer que toutes sont listées.

4. **Vérifier la correspondance contexte/question**  
   – Valider que le `context_sections` référencé correspond bien au module demandé (éviter les confusions entre vignettes et contrôle technique).

---

## 7. Conclusion

Llama est fonctionnel mais présente une fiabilité limitée (environ 3 tours sur 4 corrects). Les refus de répondre et les hallucinations constituent la majeure partie des erreurs. Pour une utilisation en production, des ajustements ou un changement de modèle (vers Qwen, par exemple) seraient nécessaires. Sans correction, Llama risque de frustrer les utilisateurs par des réponses inutilement vagues ou, au contraire, par des inventions dangereuses.
