# 🚀 Guide d'installation et de configuration

## ✅ Étape 1 : Migrations exécutées

Les migrations ont été exécutées avec succès:
- ✅ `2026_07_02_000000_create_application_admins_and_users_tables`
- ✅ `2026_07_02_000001_add_admin_and_department_to_applications`

## 📝 Étape 2 : Configuration de base

### 2.1 Créer un Super Admin (optionnel, si pas déjà fait)

```bash
php artisan tinker

# Trouver un utilisateur existant
$user = User::first();

# Le promouvoir Super Admin
$user->update([
    'is_admin' => true,
    'admin_type' => 'super'
]);
```

### 2.2 Vérifier les relations

```bash
php artisan tinker

# Créer une application test
$app = Application::create([
    'name' => 'Test App',
    'admin_id' => 1,
    'department' => 'IT'
]);

# Ajouter un admin
$user = User::find(2);
$user->update(['is_admin' => true, 'admin_type' => 'app']);
$app->admins()->attach($user->id);

# Ajouter des users
$app->allowedUsers()->attach([3, 4, 5]);

# Vérifier
echo $app->admins()->count();  // 1
echo $app->allowedUsers()->count();  // 3
```

## 🎨 Étape 3 : Frontend - Implémentation des modals

### 3.1 Modal "Ajouter Application"

À implémenter dans `resources/views/admin/dashboard.blade.php`:

```html
<!-- Template pour Modal Ajouter Application -->
<template x-if="applicationModalOpen">
    <div class="fixed inset-0 z-50 flex items-center justify-center px-4" style="background:rgba(0,0,0,0.5)" @click.self="applicationModalOpen=false">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6">
            <div class="flex items-center justify-between mb-6">
                <h2 class="text-base font-semibold text-sonatrach-noir">Ajouter une application</h2>
                <button @click="applicationModalOpen=false" class="text-gray-400 hover:text-gray-600">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </div>

            <div class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-gray-700 mb-1.5">Nom de l'application *</label>
                    <input type="text" x-model="appForm.name" placeholder="BDM, SAP, Parc Auto..." class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl focus:outline-none focus:ring-2 focus:ring-sonatrach-orange">
                </div>

                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-semibold text-gray-700 mb-1.5">Administrateur *</label>
                        <select x-model="appForm.admin_id" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl">
                            <option value="">-- Choisir --</option>
                            <template x-for="admin in availableAdmins" :key="admin.id">
                                <option :value="admin.id" x-text="admin.name"></option>
                            </template>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-gray-700 mb-1.5">Département</label>
                        <select x-model="appForm.department" class="w-full px-3 py-2.5 text-sm border border-sonatrach-gris-bord rounded-xl">
                            <option value="">-- Choisir --</option>
                            <template x-for="dept in departments" :key="dept">
                                <option :value="dept" x-text="dept"></option>
                            </template>
                        </select>
                    </div>
                </div>

                <!-- Sélecteur utilisateurs -->
                <div class="border border-sonatrach-gris-bord rounded-xl p-4">
                    <div class="flex items-center gap-3 mb-3">
                        <input type="checkbox" x-model="appForm.allDeptUsers" id="allDeptUsers" class="w-4 h-4">
                        <label for="allDeptUsers" class="text-sm text-gray-700">Assigner tous les utilisateurs du département</label>
                    </div>
                    <template x-if="!appForm.allDeptUsers">
                        <div>
                            <label class="block text-xs font-semibold text-gray-700 mb-2">Sélectionner des utilisateurs spécifiques</label>
                            <div class="space-y-2 max-h-64 overflow-y-auto">
                                <template x-for="user in deptUsers" :key="user.id">
                                    <label class="flex items-center gap-2 p-2 rounded hover:bg-gray-50">
                                        <input type="checkbox" :value="user.id" x-model="appForm.user_ids" class="w-4 h-4">
                                        <span class="text-sm text-gray-700" x-text="user.name + ' (' + user.email + ')'"></span>
                                    </label>
                                </template>
                            </div>
                        </div>
                    </template>
                </div>
            </div>

            <div class="flex gap-3 mt-6">
                <button @click="applicationModalOpen=false" class="flex-1 py-2.5 rounded-xl text-sm font-medium border border-sonatrach-gris-bord">Annuler</button>
                <button @click="saveApplication()" class="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-sonatrach-orange text-white">Ajouter</button>
            </div>
        </div>
    </div>
</template>
```

### 3.2 Fonctions JavaScript

À ajouter dans le script Alpine.js du dashboard:

```javascript
// Données pour applications
applicationModalOpen: false,
appForm: {
    name: '',
    admin_id: '',
    department: '',
    allDeptUsers: false,
    user_ids: []
},
availableAdmins: [],
departments: [],
deptUsers: [],

// Charger les données initiales
async initApplications() {
    await this.loadAdmins();
    await this.loadApplications();
    await this.loadDepartments();
},

// Charger admins
async loadAdmins() {
    try {
        const r = await fetch('/admin/available-admins', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const d = await r.json();
        this.availableAdmins = d.admins || [];
    } catch (e) {
        console.error('Error loading admins:', e);
    }
},

// Charger départements
async loadDepartments() {
    try {
        const r = await fetch('/admin/departments', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const d = await r.json();
        this.departments = d.departments || [];
    } catch (e) {
        console.error('Error loading departments:', e);
    }
},

// Charger users du département
async loadDeptUsers() {
    if (!this.appForm.department) return;
    try {
        const r = await fetch('/admin/available-users?department=' + this.appForm.department, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const d = await r.json();
        this.deptUsers = d.users || [];
    } catch (e) {
        console.error('Error loading users:', e);
    }
},

// Sauvegarder application
async saveApplication() {
    if (!this.appForm.name || !this.appForm.admin_id) {
        this.toast('Remplissez les champs obligatoires', false);
        return;
    }

    const payload = {
        name: this.appForm.name,
        admin_id: this.appForm.admin_id,
        department: this.appForm.department || null,
        all_department_users: this.appForm.allDeptUsers,
        user_ids: this.appForm.allDeptUsers ? [] : this.appForm.user_ids
    };

    try {
        const r = await fetch('/admin/applications', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(payload)
        });
        const d = await r.json();
        if (!r.ok || !d.success) throw new Error(d.message || 'Erreur');

        await this.loadApplications();
        this.applicationModalOpen = false;
        this.toast('Application créée avec succès');
    } catch (e) {
        this.toast(e.message, false);
    }
}
```

## 🔒 Étape 4 : Sécurité - Ajouter les middlewares

Créer `app/Http/Middleware/EnsureIsAppAdmin.php`:

```php
<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;

class EnsureIsAppAdmin
{
    public function handle(Request $request, Closure $next)
    {
        $user = auth()->user();

        // Super admin a toujours accès
        if ($user && $user->is_admin && $user->admin_type === 'super') {
            return $next($request);
        }

        // Admin d'app peut accéder à son dashboard
        if ($user && $user->is_admin && $user->admin_type === 'app') {
            // Vérifier que les applications requises appartiennent à l'admin
            if ($request->route('app_id')) {
                $app = \App\Models\Application::find($request->route('app_id'));
                if ($app && !$user->adminApplications()->where('application_id', $app->id)->exists()) {
                    abort(403, 'Unauthorized');
                }
            }
            return $next($request);
        }

        abort(403, 'Unauthorized');
    }
}
```

Enregistrer dans `app/Http/Kernel.php`:
```php
protected $routeMiddleware = [
    // ...
    'is_app_admin' => \App\Http\Middleware\EnsureIsAppAdmin::class,
];
```

Utiliser dans les routes:
```php
Route::middleware('is_app_admin')->group(function () {
    // Routes protégées
});
```

## 🧪 Étape 5 : Tests

Tester manuellement dans le navigateur:

1. **Login as Super Admin**
   - Aller à `/admin`
   - Voir la section "Administrateurs"
   - Voir la section "Applications"

2. **Ajouter une application**
   - Cliquer "Ajouter application"
   - Remplir le formulaire
   - Cliquer "Ajouter"
   - Vérifier que l'app apparaît dans la liste

3. **Ajouter un admin**
   - Cliquer "Ajouter admin" dans la section Administrateurs
   - Choisir un user
   - Vérifier que c'est maintenant un admin

4. **Login as App Admin**
   - Logout depuis Super Admin
   - Login comme l'admin créé
   - Vérifier qu'il voit la page `/admin/app-dashboard`
   - Vérifier qu'il voit uniquement ses applications

## 📊 Vérifier la BD

```sql
-- Vérifier les admins
SELECT id, name, is_admin, admin_type FROM users WHERE is_admin = true;

-- Vérifier les applications
SELECT id, name, admin_id, department FROM applications;

-- Vérifier les relations admin-app
SELECT * FROM application_admins;

-- Vérifier les relations user-app
SELECT * FROM application_users;
```

## 🎯 Points clés à retenir

✅ Les migrations ont été exécutées  
✅ Les endpoints API sont prêts  
✅ La page dashboard a les sections admin/applications  
✅ La page app-dashboard existe pour les admins d'app  
⏳ À implémenter: Modals et JavaScript frontend  
⏳ À ajouter: Middlewares de sécurité  
⏳ À créer: Tests unitaires  

## 📞 Troubleshooting

### "Middleware not found"
→ Vérifier que le middleware est enregistré dans `Kernel.php`

### "Application not showing in admin view"
→ Vérifier que `admin_id` est correctement défini

### "Can't see app users"
→ Vérifier que `application_users` a les bons enregistrements

### "CSRF token error"
→ Vérifier que le token est présent dans la requête

