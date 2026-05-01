# Rapport d’évaluation – Modèle Qwen2.5 (7B, GGUF)

## Synthèse générale

Le modèle a été évalué sur un ensemble de 14 conversations simulant des requêtes utilisateur dans des contextes métiers variés : gestion de flotte automobile (PARC‑AUTO), gestion de projets (BDMEYE), bureautique (Word, Excel, Outlook), etc.  
Au total, **130 tours** ont été analysés, dont **106 jugés corrects (81,5%)** et **24 jugés incorrects (18,5%)**.

Le modèle montre de très bonnes capacités de compréhension des requêtes, même lorsqu’elles sont mal rédigées ou abrégées. Il exploite correctement les contextes RAG pour répondre avec des procédures exactes, des listes d’éléments ou des explications claires.

Les erreurs relevées se répartissent en plusieurs catégories récurrentes :

1. **Hallucinations** – ajout d’informations non présentes dans le contexte.
2. **Non‑respect du périmètre** – réponse hors domaine (ex. lettre de motivation, remerciements) au lieu du message standard.
3. **Réponses incomplètes ou hors sujet** – omission d’une partie de la question ou réponse déconnectée du bon contexte.
4. **Procédure incorrecte** – action recommandée non conforme à la documentation.

---

## Détail des erreurs par catégorie

### 🔮 Hallucinations (7 occurrences)

| Conversation | Turn | Query                                                         | Erreur                                                                                                                 |
| ------------ | ---- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| conv_2       | 10   | Ajouter carte grise – champs à renseigner                     | Le modèle invente des champs (« numéro de la carte grise, date d’expiration ») absents du contexte.                    |
| conv_3       | 11   | Ajouter un chauffeur comme personnel                          | Le modèle décrit une procédure détaillée (deux modules, cohérence des données) qui n’existe pas dans la documentation. |
| conv_4       | 15   | « on ne peut pas revoir utilisateur » (après suppression)     | Le modèle invoque une « fonction d’audit » inexistante.                                                                |
| conv_7       | 5    | Écrire une lettre de motivation                               | Le modèle génère une lettre complète alors qu’il doit répondre « Je ne peux pas répondre… ».                           |
| conv_12      | 12   | Publipostage partagé – perte des zéros + erreur table externe | La réponse commence par une procédure totalement hors propos (modification d’objet incorporé).                         |
| conv_13      | 2    | Utiliser des numéros de colonne après retour au style A1      | Invention de la syntaxe `=$1$1` (inexistante).                                                                         |
| conv_13      | 9    | Alternative à la désunion des cellules fusionnées             | Invention d’un « Trier en place » qui ne résout pas le problème (le contexte propose de fusionner uniformément).       |

### 🚫 Non‑respect du périmètre / OOD (3 occurrences)

| Conversation | Turn | Query                                 | Erreur                                                                     |
| ------------ | ---- | ------------------------------------- | -------------------------------------------------------------------------- |
| conv_4       | 8    | « oui ca marche » (affirmation vague) | Le modèle répond `"None"` au lieu du message standard.                     |
| conv_10      | 8    | « ahh ok c'est fais »                 | Le modèle répond « Avez-vous des questions… » au lieu du message standard. |
| conv_11      | 15   | « dcr merci »                         | Le modèle répond « De rien » au lieu du message standard.                  |

### 📝 Réponses incomplètes ou hors sujet (4 occurrences)

| Conversation | Turn | Query                                                  | Erreur                                                                                                         |
| ------------ | ---- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| conv_1       | 10   | Modification d’un utilisateur impossible               | Le modèle ne mentionne **pas** que les informations de base ne sont pas modifiables (restriction essentielle). |
| conv_2       | 12   | Création d’affectation « ne marche pas »               | Le modèle répète la procédure normale au lieu de proposer un diagnostic.                                       |
| conv_4       | 8    | « ou faire ca » (ajout d’utilisateur)                  | La question demande l’emplacement (« menu ») – le modèle répond « cliquer sur Ajouter ».                       |
| conv_4       | 14   | « je ne vois pas sa traçabilité » (désactivation)      | Le modèle répète la phrase du contexte sans expliquer où trouver l’historique.                                 |
| conv_12      | 5    | Word lent avec modifications suivies + fichier serveur | Le modèle ne traite que la cause réseau, ignore la solution pour les modifications suivies.                    |
| conv_14      | 8    | Problèmes de réunion (réponses + délégué)              | Le modèle répond sur Outlook Anywhere (hors sujet) alors que le contexte donne des causes précises.            |

### ❌ Procédure incorrecte (2 occurrences)

| Conversation | Turn | Query                              | Erreur                                                                                                                                            |
| ------------ | ---- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| conv_3       | 15   | Annuler une affectation            | Le modèle suggère de retourner au formulaire de création et de cliquer sur « Supprimer » – alors qu’il faut passer par la liste des affectations. |
| conv_6       | 7    | Ajouter un personnel depuis les RH | Le modèle répond « bouton Ajouter » (création manuelle) au lieu de « bouton Importer depuis Ressources humaines ».                                |

---

## Points forts

- **Précision dans les réponses RAG simples** : les procédures en étapes, les listes d’éléments, les définitions de champs sont presque toujours exactes.
- **Gestion des requêtes mal rédigées** : le modèle comprend bien les abréviations et fautes de frappe.
- **Gestion des follow‑up** : maintien du fil de la conversation, réponses adaptées à l’historique.
- **Comportement OOD correct la plupart du temps** : répond « Je ne peux pas répondre… » pour les sujets hors manuel (météo, recettes, code HTML, etc.).

---

## Recommandations

1. **Renforcer l’instruction systématique de ne jamais ajouter d’informations non présentes dans le contexte** pour lutter contre les hallucinations.
2. **Pour les FAQ hors domaine ou les remerciements**, forcer le modèle à retourner le message standard unique.
3. **Dans les cas de « ça ne marche pas »**, le modèle devrait d’abord énumérer les causes possibles issues du contexte plutôt que de répéter la procédure normale.
4. **Vérifier que le modèle ne « pioche » pas dans un contexte antérieur erroné** (exemple : catégories vignettes au lieu de catégories contrôle technique).

---

## Conclusion

Le modèle est globalement fiable pour un assistant de manuel technique. Il obtient un taux de succès de 81,5 % sur un ensemble de tests exigeants. Les erreurs identifiées sont typiques des modèles de cette taille et peuvent être significativement réduites par un prompt mieux contraint et une architecture de routage plus stricte entre RAG et OOD.
