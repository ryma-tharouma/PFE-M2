# 📋 Rapport d'Évaluation des Générations - Analyse des Erreurs

**Date :** 29 avril 2026  
**Modèle :** qwen3.5_4b_gguf_original_l2_prompt1  
**Total générations analysées :** 144  
**Taux de réussite :** 88.2% (127/144)  
**Total erreurs :** 12

---

## 📊 Résumé des erreurs par type

| Type d'erreur                                          | Nombre | Sévérité |
| ------------------------------------------------------ | ------ | -------- |
| Refus de répondre (alors que réponse disponible)       | 5      | Critique |
| Mauvaise séquence / Manque d'actualisation du contexte | 2      | Moyenne  |
| Réponse trop succincte                                 | 2      | Mineure  |
| Interprétation incorrecte                              | 1      | Moyenne  |
| Question inintelligible (non imputable au modèle)      | 1      | N/A      |
| Réponse incomplète                                     | 1      | Mineure  |

---

## ❌ Liste détaillée des erreurs

### 1. conv_2 turn 4 – "comment ajouter un véhicule ?"

|                   |                                                                                                                                                                                                                                                                                                                                                             |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Réponse trop succincte                                                                                                                                                                                                                                                                                                                                      |
| **Sévérité**      | Mineure                                                                                                                                                                                                                                                                                                                                                     |
| **Généré**        | _"Cliquez sur le bouton 'Ajouter un véhicule' situé dans la page principale de la liste des véhicules. Cela vous accèdera directement à la page de création où vous pourrez saisir les caractéristiques du véhicule (Marque, Modèle, Couleur, Carrosserie, Genre et autres attributs techniques) puis cliquer sur 'Enregistrer' pour valider la création."_ |
| **Attendu**       | Le formulaire de création complet avec les fonctionnalités avancées : marque avec bouton "+" pour création à la volée, modèle avec création à la volée, photos multiples, champs spécifiques                                                                                                                                                                |
| **Commentaire**   | La réponse est correcte mais trop simplifiée. Elle manque les détails importants sur les fonctionnalités avancées (bouton orange avec icône "+" pour créer une nouvelle marque/modèle).                                                                                                                                                                     |

---

### 2. conv_2 turn 5 – "est ce que je peut attacher plusieurs photo pour un seul véhicule ?"

|                   |                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Type d'erreur** | Réponse simplifiée                                                                                                       |
| **Sévérité**      | Mineure                                                                                                                  |
| **Généré**        | _"Oui, le formulaire de création permet d'attacher plusieurs photos du véhicule."_                                       |
| **Attendu**       | La citation textuelle exacte : _"Photos : Possibilité d'attacher plusieurs photos du véhicule"_                          |
| **Commentaire**   | La réponse est factuellement correcte mais le ground truth attendait une citation textuelle plutôt qu'une reformulation. |

---

### 3. conv_2 turn 13 – "jai choisis le mauvais véhicule comment je peux corriger cela"

|                   |                                                                                                                                                                                                                                |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Type d'erreur** | Refus de répondre                                                                                                                                                                                                              |
| **Sévérité**      | Critique                                                                                                                                                                                                                       |
| **Généré**        | _"Je ne peux pas répondre à cette question avec les informations disponibles."_                                                                                                                                                |
| **Attendu**       | La procédure de restitution complète (4 étapes avec formulaire détaillé : motif, date, observations, kilométrage, photos)                                                                                                      |
| **Commentaire**   | Le modèle a refusé de répondre alors que le contexte contient exactement la solution (restitution pour corriger une affectation erronée). Le modèle n'a pas fait le lien sémantique entre "mauvais véhicule" et "restitution". |

---

### 4. conv_3 turn 11 – "est ce que je peux ajouter un chauffeur comme personnel"

|                   |                                                                                                                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Interprétation incorrecte                                                                                                                                                                               |
| **Sévérité**      | Moyenne                                                                                                                                                                                                 |
| **Généré**        | _"Non, le module 'Gestion du Personnel' ne permet pas d'ajouter un chauffeur. Le module spécialisé 'Gestion des Chauffeurs' est dédié à la gestion des chauffeurs professionnels..."_                   |
| **Attendu**       | La présentation des deux modules distincts sans affirmation négative explicite                                                                                                                          |
| **Commentaire**   | Le modèle a affirmé "non" alors que le contexte ne dit pas explicitement qu'on ne peut pas. La bonne réponse aurait dû expliquer qu'il s'agit de deux modules distincts avec des finalités différentes. |

---

### 5. conv_4 turn 4 – "c'est quoi mes identifiants Active Directory"

|                   |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Refus de répondre                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Sévérité**      | Critique                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **Généré**        | _"Je ne peux pas répondre à cette question avec les informations disponibles."_                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Attendu**       | _"L'authentification à PARC-AUTO est intégrée avec le système Active Directory de Sonatrach. Cela signifie que vous pouvez vous connecter en utilisant le même nom d'utilisateur et mot de passe que ceux que vous utilisez pour accéder à votre session informatique au sein de l'entreprise. Nom d'utilisateur : Entrez le nom d'utilisateur que vous utilisez pour vous connecter à votre ordinateur professionnel. Mot de passe : Saisissez votre mot de passe Active Directory..."_ |
| **Commentaire**   | Le contexte contient explicitement la réponse. Le modèle a refusé de répondre alors que l'information était présente.                                                                                                                                                                                                                                                                                                                                                                    |

---

### 6. conv_4 turn 10 – "la modification ne marche pas"

|                   |                                                                                                                                                           |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Refus de répondre                                                                                                                                         |
| **Sévérité**      | Critique                                                                                                                                                  |
| **Généré**        | _"Je ne peux pas répondre à cette question avec les informations disponibles."_                                                                           |
| **Attendu**       | _"Rappel : Au moins un rôle doit rester sélectionné."_                                                                                                    |
| **Commentaire**   | Le modèle n'a pas fait le lien "modification ne marche pas" → "cause possible : plus aucun rôle sélectionné". La réponse était présente dans le contexte. |

---

### 7. conv_6 turn 6 – "est ce que je peux ajouter un chauffeur en tant que personnel ?"

|                   |                                                                                                                                                                             |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Refus de répondre                                                                                                                                                           |
| **Sévérité**      | Critique                                                                                                                                                                    |
| **Généré**        | _"Je ne peux pas répondre à cette question avec les informations disponibles."_                                                                                             |
| **Attendu**       | Les descriptions des sections sec_00023 (Personnel) et sec_00018 (Chauffeurs) comme deux modules distincts                                                                  |
| **Commentaire**   | Le modèle a refusé de répondre alors que le contexte permettait de comprendre qu'il s'agit de modules séparés avec des finalités différentes. Même pattern que l'erreur #4. |

---

### 8. conv_9 turn 6 – "je veux aussi pour categorie"

|                   |                                                                                                                                                                                                                                         |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Manque d'actualisation du contexte                                                                                                                                                                                                      |
| **Sévérité**      | Moyenne                                                                                                                                                                                                                                 |
| **Généré**        | _"Le formulaire comprend : •Désignation du type : Nom du type de contrôle technique"_                                                                                                                                                   |
| **Attendu**       | Informations sur la création d'une catégorie (dans le contexte des vignettes, section sec_00038)                                                                                                                                        |
| **Commentaire**   | Le modèle a répété la réponse précédente (sur les types de contrôle technique) au lieu de répondre sur les catégories de vignettes. Le contexte a changé entre les tours. La question "aussi pour" a déclenché une analogie incorrecte. |

---

### 9. conv_9 turn 11 – "donne moi la prochaine etape ?"

|                   |                                                                                                                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Mauvaise séquence                                                                                                                                  |
| **Sévérité**      | Moyenne                                                                                                                                            |
| **Généré**        | _"Après remplissage, cliquez sur 'Enregistrer' pour valider la création ou modification."_                                                         |
| **Attendu**       | _"Section 2 : Véhicules Sélectionnés (affichage dynamique de la liste des véhicules sélectionnés dans la première section)"_                       |
| **Commentaire**   | Le modèle a sauté l'étape intermédiaire (Section 2) et est allé directement à la fin du processus. N'a pas respecté l'ordre séquentiel des étapes. |

---

### 10. conv_9 turn 12 – "est ce que cbn"

|                   |                                                                                                                                                                                                                                           |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Question inintelligible                                                                                                                                                                                                                   |
| **Sévérité**      | N/A (non imputable au modèle)                                                                                                                                                                                                             |
| **Généré**        | _"Je ne peux pas répondre à cette question avec les informations disponibles."_                                                                                                                                                           |
| **Attendu**       | Section 3 : Informations de l'Assurance                                                                                                                                                                                                   |
| **Commentaire**   | La requête "cbn" est probablement une abréviation de "c'est bon" ou une question tronquée. Le modèle a fait le choix sécuritaire de répondre "je ne peux pas répondre". La réponse est défendable mais ne correspond pas au ground truth. |

---

### 11. conv_13 turn 9 – "trop de cellules fusionnées, les désunir toutes va me faire perdre la mise en forme. Y a pas une autre astuce ?"

|                   |                                                                                                                                                                                                                                                                   |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | A ignoré la solution alternative du contexte                                                                                                                                                                                                                      |
| **Sévérité**      | Mineure                                                                                                                                                                                                                                                           |
| **Généré**        | Procédure de désunion des cellules fusionnées                                                                                                                                                                                                                     |
| **Attendu**       | Fusionner **toutes** les cellules à la même taille pour qu'elles soient uniformes (exemple : fusionner C1-D1, C2-D2, C3-D3)                                                                                                                                       |
| **Commentaire**   | La question demande explicitement une alternative à la désunion. Le contexte proposait la solution "fusionnez-les toutes de manière à ce que les cellules fusionnées aient la même taille". Le modèle a ignoré cette solution et répété la procédure de désunion. |

---

### 12. conv_14 turn 10 – "fichier sur OneDrive pour que tout le monde puisse le voir sans se connecter"

|                   |                                                                                                                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Type d'erreur** | Réponse incomplète                                                                                                                                                                    |
| **Sévérité**      | Mineure                                                                                                                                                                               |
| **Généré**        | _"Vous pouvez charger l'élément Outlook dans fichiers dans le groupe Microsoft 365 ou dans OneDrive Entreprise, puis inclure un lien dans le corps de la réunion ou du rendez-vous."_ |
| **Attendu**       | L'option **"Créer un lien"** avec **"Toute personne disposant du lien"** comme type de partage                                                                                        |
| **Commentaire**   | Le modèle a omis l'étape clé pour le partage sans authentification. La réponse est partiellement correcte mais manque le détail critique.                                             |

---

## 📈 Synthèse

| Métrique          | Valeur    |
| ----------------- | --------- |
| Total générations | 144       |
| Correctes         | 127       |
| Erreurs           | 12        |
| Taux de réussite  | **88.2%** |
| BERT F1           | **0.854** |

### Répartition des erreurs par conversation

| Conversation | Nombre d'erreurs |
| ------------ | ---------------- |
| conv_2       | 3                |
| conv_3       | 1                |
| conv_4       | 2                |
| conv_6       | 1                |
| conv_9       | 3                |
| conv_13      | 1                |
| conv_14      | 1                |

---

## 🔧 Recommandations

1. **Refus de répondre** (5 occurrences) : Ajouter dans le prompt "Ne répondez JAMAIS 'je ne peux pas répondre' si le contexte contient une information directement pertinente."

2. **Inférence problème → solution** : Former le modèle à chercher dans le contexte les causes possibles ou les procédures de correction lorsque l'utilisateur signale un problème.

3. **Mise à jour du contexte** : Ajouter une instruction pour que le modèle vérifie le contexte à chaque tour, même si l'utilisateur dit "aussi" ou "pareil".

4. **Séquences d'étapes** : Demander au modèle de suivre l'ordre séquentiel des procédures.

5. **Questions ambiguës** : Demander une clarification au lieu de répondre "je ne peux pas répondre".

---

**Fin du rapport**
