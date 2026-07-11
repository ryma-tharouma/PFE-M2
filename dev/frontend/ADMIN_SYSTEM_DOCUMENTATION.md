# Système de Gestion des Admins et Applications - Documentation

## Résumé des modifications

### 1. Modèles (Models)

#### **User.php**
- Ajout du champ `admin_type` (enum: 'super', 'app', 'user')
- Relations:
  - `adminApplications()` : Applications où l'utilisateur est admin
  - `allowedApplications()` : Applications auxquelles l'utilisateur a accès

#### **Application.php**
- Ajout des champs `admin_id` et `department`
- Relations:
  - `admin()` : Administrateur responsable de l'application
  - `admins()` : Tous les admins de l'application
  - `allowedUsers()` : Utilisateurs autorisés à utiliser l'application

### 2. Migrations

#### **2026_07_02_000000_create_application_admins_and_users_tables.php**
- Table `application_admins`: Relation between admins and applications
- Table `application_users`: Relation between authorized users and applications
- Ajoute colonne `admin_type` à la table `users`

#### **2026_07_02_000001_add_admin_and_department_to_applications.php**
- Ajoute `admin_id` (foreign key vers users)
- Ajoute `department` (string pour le département)

### 3. Contrôleur (AdminController)

#### Endpoints pour les Admins
- `GET /admin/admins` : Lister tous les admins
- `POST /admin/admins` : Ajouter un admin
- `DELETE /admin/admins/{user_id}` : Retirer un admin

#### Endpoints pour les Applications
- `GET /admin/applications` : Lister toutes les applications
- `POST /admin/applications` : Créer une application
- `PUT /admin/applications/{app_id}` : Modifier une application
- `DELETE /admin/applications/{app_id}` : Supprimer une application

#### Endpoints pour les Utilisateurs d'Applications
- `GET /admin/applications/{app_id}/users` : Lister les utilisateurs d'une app
- `POST /admin/applications/{app_id}/users` : Ajouter des utilisateurs à une app
- `DELETE /admin/applications/{app_id}/users/{user_id}` : Retirer un utilisateur

#### Endpoints Utilitaires
- `GET /admin/available-admins` : Lister les admins disponibles
- `GET /admin/available-users` : Lister les users disponibles
- `GET /admin/departments` : Lister tous les départements
- `GET /admin/app-dashboard` : Dashboard personnalisé pour les admins d'applications

### 4. Routes

Ajoutées à `/routes/web.php`:
```php
// Admin Management
Route::get('/admins', [AdminController::class, 'getAdmins'])->name('getAdmins');
Route::post('/admins', [AdminController::class, 'addAdmin'])->name('addAdmin');
Route::delete('/admins/{user_id}', [AdminController::class, 'removeAdmin'])->name('removeAdmin');

// Application Management
Route::get('/applications', [AdminController::class, 'getApplications'])->name('getApplications');
Route::post('/applications', [AdminController::class, 'storeApplication'])->name('storeApplication');
Route::put('/applications/{app_id}', [AdminController::class, 'updateApplication'])->name('updateApplication');
Route::delete('/applications/{app_id}', [AdminController::class, 'destroyApplication'])->name('destroyApplication');

// Etc...
```

### 5. Vues

#### **resources/views/admin/dashboard.blade.php**
- Section "Administrateurs" : Tableau des admins avec actions
- Section "Applications" : Tableau des applications avec actions

#### **resources/views/admin/app-dashboard.blade.php**
- Nouvelle page pour les admins d'applications
- Affiche uniquement les applications assignées
- Vue simplifiée pour chaque admin

## Flux d'utilisation

### Scénario 1 : Super Admin gère les Applications

1. Super Admin va à Admin > Applications
2. Clique "Ajouter application"
3. Remplit le formulaire:
   - Nom de l'application
   - Sélectionne un admin responsable
   - Choisit un département
   - Sélectionne des utilisateurs (ou tout le département)
4. L'application est créée et sauvegardée en BD
5. Tous les manuels/FAQ de cette app sont automatiquement liés

### Scénario 2 : Super Admin crée des Admins

1. Super Admin va à Admin > Administrateurs
2. Clique "Ajouter admin"
3. Sélectionne un utilisateur depuis la liste
4. L'utilisateur est promu admin avec `admin_type = 'app'`
5. L'admin peut maintenant accéder à son dashboard personnalisé

### Scénario 3 : Admin d'Application utilise son Dashboard

1. Admin se connecte
2. Système le redirige vers `/admin/app-dashboard`
3. Voit uniquement ses applications
4. Peut gérer:
   - Tickets de ses applications
   - Manuels de ses applications
   - FAQ de ses applications
   - Utilisateurs de ses applications

## Structure des Données

### Table: application_admins
```
id | application_id | user_id | created_at | updated_at
```

### Table: application_users
```
id | application_id | user_id | created_at | updated_at
```

### Colonnes ajoutées à users:
```
admin_type (enum: 'super', 'app', 'user') - Default: 'user'
```

### Colonnes ajoutées à applications:
```
admin_id (FK vers users, nullable)
department (string, nullable)
```

## Logique métier

### Création d'Application
- Si l'admin assigné n'existe pas → Erreur
- S'il y a des utilisateurs/département assignés → Ils sont liés dans `application_users`
- Si l'option "tout le département" est choisie → Tous les users du département sont liés
- Les manuels/FAQ existants restent liés par leur application_id

### Suppression d'Application
- Supprime tous les manuels
- Supprime toutes les FAQ
- Supprime les fichiers JSON/images
- Supprime les liens admin/users
- Supprime les conversations/messages orphelins
- Supprime les collections Qdrant associées

### Promotion Admin
- User normal devient admin
- admin_type passe à 'app'
- Peut être assigné à des applications
- Peut accéder au dashboard personnalisé

### Rétrogradation Admin
- Admin devient user normal
- admin_type passe à 'user'
- Détaché de toutes les applications
- Pas de suppression de ses données

## Améliorations futures

1. **Interface de gestion des applications**
   - Modal pour créer/modifier applications
   - Sélecteur de département/utilisateurs
   - Preview des utilisateurs sélectionnés

2. **Dashboard admin amélioré**
   - Graphiques par application
   - Statistiques détaillées
   - Export de rapports

3. **Permissions granulaires**
   - Lecture/écriture/suppression par entité
   - Audit trail

4. **Multi-admin par application**
   - Plusieurs admins responsables
   - Niveaux de permission différents

## Commandes utiles

```bash
# Exécuter les migrations
php artisan migrate

# Créer un admin depuis la CLI
php artisan tinker
> $user = User::find(1);
> $user->update(['is_admin' => true, 'admin_type' => 'super']);

# Tester les endpoints
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/admin/applications
```

## Endpoints à implémenter côté frontend

- [ ] Modal "Ajouter application"
- [ ] Modal "Modifier application"
- [ ] Modal "Ajouter utilisateurs à application"
- [ ] Chargement dynamique des admins
- [ ] Chargement dynamique des applications
- [ ] Intégration Alpine.js pour les fonctions

