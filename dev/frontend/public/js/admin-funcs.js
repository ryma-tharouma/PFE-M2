// Fonctions admin et applications
function setupAdminAndAppFunctions(context) {
    // ── Admins ──────────────────────────────────────────────────────────
    context.loadAdmins = async function () {
        try {
            const r = await fetch('/admin/admins', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const d = await r.json();
            this.admins = d.admins || [];
        } catch (e) {
            console.error('Error loading admins:', e);
            this.toast('Erreur chargement admins', false);
        }
    };

    // Choix admin : on liste TOUS les employés non-admins (200 importés LDAP)
    context.openAddAdminModal = function () {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4';
        modal.innerHTML = `
            <div class="bg-white rounded-2xl shadow-xl max-w-md w-full overflow-hidden">
                <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h3 class="text-lg font-semibold text-gray-900">Ajouter un administrateur</h3>
                    <button type="button" onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                </div>
                <div class="p-6 space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Sélectionner un utilisateur</label>
                        <select id="userSelect" class="w-full px-3 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange">
                            <option value="">-- Choisir un utilisateur --</option>
                        </select>
                        <p class="text-xs text-gray-400 mt-1">Liste complète des employés (non-admins) importés depuis LDAP.</p>
                    </div>
                </div>
                <div class="px-6 py-4 border-t border-gray-200 flex gap-3 justify-end">
                    <button type="button" onclick="this.closest('.fixed').remove()" class="px-4 py-2 rounded-lg text-sm border border-gray-300 text-gray-700 hover:bg-gray-50">Annuler</button>
                    <button type="button" onclick="window.adminAddSubmit()" class="px-4 py-2 rounded-lg text-sm font-semibold bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark">Ajouter</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        fetch('/admin/available-users?admin=0', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(d => {
                const select = document.getElementById('userSelect');
                (d.users || []).forEach(u => {
                    const opt = document.createElement('option');
                    opt.value = u.id;
                    opt.textContent = u.name + ' (' + u.email + ')' + (u.department ? ' — ' + u.department : '');
                    select.appendChild(opt);
                });
            })
            .catch(() => {
                this.toast('Erreur chargement utilisateurs', false);
                modal.remove();
            });

        window.adminAddSubmit = async () => {
            const userId = document.getElementById('userSelect').value;
            if (!userId) {
                this.toast('Veuillez sélectionner un utilisateur', false);
                return;
            }

            try {
                const r = await fetch('/admin/admins', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ user_id: userId })
                });
                const d = await r.json();
                if (!r.ok || !d.success) throw new Error(d.message || 'Erreur');

                await this.loadAdmins();
                this.toast('Admin ajouté avec succès');
                modal.remove();
            } catch (e) {
                this.toast(e.message, false);
            }
        };

        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    };

    context.removeAdmin = async function (adminId) {
        try {
            const r = await fetch('/admin/admins/' + adminId, {
                method: 'DELETE',
                headers: {
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            const d = await r.json();
            if (!r.ok || !d.success) throw new Error(d.message || 'Erreur');

            await this.loadAdmins();
            this.toast('Admin retiré avec succès');
        } catch (e) {
            this.toast(e.message, false);
        }
    };

    // ── Applications ─────────────────────────────────────────────────────
    context.loadApplications = async function () {
        try {
            const r = await fetch('/admin/applications', {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const d = await r.json();
            this.applications = d.applications || [];
        } catch (e) {
            console.error('Error loading applications:', e);
            this.toast('Erreur chargement applications', false);
        }
    };

    context.openAddAppModal = function () {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 overflow-y-auto';
        modal.innerHTML = `
            <div class="bg-white rounded-2xl shadow-xl max-w-2xl w-full my-8">
                <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h3 class="text-lg font-semibold text-gray-900">Ajouter une application</h3>
                    <button type="button" onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                </div>
                <form id="appForm" class="p-6 space-y-4">
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Nom de l'application *</label>
                            <input type="text" name="name" required class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange" placeholder="ex: Parc Auto">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Version</label>
                            <input type="text" name="version" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange" placeholder="1.0">
                        </div>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Administrateurs * (sélection multiple)</label>
                        <div id="adminList" class="max-h-48 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2 bg-gray-50">
                            <p class="text-xs text-gray-400">Chargement...</p>
                        </div>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Départements (sélection multiple)</label>
                        <div id="departmentList" class="max-h-40 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2 bg-gray-50">
                            <p class="text-xs text-gray-400">Chargement...</p>
                        </div>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Utilisateurs</label>
                        <div class="flex gap-4 mb-3">
                            <label class="flex items-center gap-2">
                                <input type="radio" name="userSelection" value="all" class="rounded" onchange="document.getElementById('userList').classList.add('hidden')">
                                <span class="text-sm text-gray-700">Tout le département</span>
                            </label>
                            <label class="flex items-center gap-2">
                                <input type="radio" name="userSelection" value="specific" class="rounded" onchange="document.getElementById('userList').classList.remove('hidden')">
                                <span class="text-sm text-gray-700">Spécifiques</span>
                            </label>
                        </div>
                        <div id="userList" class="hidden max-h-48 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2 bg-gray-50">
                            <p class="text-xs text-gray-400">Choisissez d'abord un département.</p>
                        </div>
                    </div>
                </form>

                <div class="px-6 py-4 border-t border-gray-200 flex gap-3 justify-end">
                    <button type="button" onclick="this.closest('.fixed').remove()" class="px-4 py-2 rounded-lg text-sm border border-gray-300 text-gray-700 hover:bg-gray-50">Annuler</button>
                    <button type="button" onclick="window.appAddSubmit()" class="px-4 py-2 rounded-lg text-sm font-semibold bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark">Ajouter</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Charge la liste des employés déjà admins (pour cocher plusieurs admins d'une même app)
        // + la liste des départements réels (issus des 200 users importés).
        Promise.all([
            fetch('/admin/available-users?admin=1', { headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(r => r.json()),
            fetch('/admin/departments', { headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(r => r.json())
        ])
            .then(([usersData, deptData]) => {
                const adminList = document.getElementById('adminList');
                adminList.innerHTML = '';
                const admins = usersData.users || [];
                if (admins.length === 0) {
                    adminList.innerHTML = '<p class="text-xs text-gray-400">Aucun administrateur disponible. Ajoutez-en un depuis l\'onglet Administrateurs.</p>';
                } else {
                    admins.forEach(u => {
                        const label = document.createElement('label');
                        label.className = 'flex items-center gap-2';
                        label.innerHTML = `
                            <input type="checkbox" value="${u.id}" class="rounded">
                            <span class="text-sm text-gray-700">${u.name} (${u.email})</span>
                        `;
                        adminList.appendChild(label);
                    });
                }

                const departmentList = document.getElementById('departmentList');
                departmentList.innerHTML = '';
                const depts = deptData.departments || [];
                if (depts.length === 0) {
                    departmentList.innerHTML = '<p class="text-xs text-gray-400">Aucun département disponible.</p>';
                } else {
                    depts.forEach(dept => {
                        const label = document.createElement('label');
                        label.className = 'flex items-center gap-2';
                        label.innerHTML = `
                            <input type="checkbox" value="${dept}" class="rounded dept-checkbox">
                            <span class="text-sm text-gray-700">${dept}</span>
                        `;
                        departmentList.appendChild(label);
                    });
                }
            })
            .catch(() => {
                this.toast('Erreur chargement données', false);
                modal.remove();
            });

        // ── Chargement des users des départements sélectionnés ───────────
        // Correction : on filtre UNIQUEMENT par département (pas par is_admin),
        // pour afficher tous les employés des départements parmi les 200 importés.
        const loadUsersForDepartment = async (depts) => {
            const userList = document.getElementById('userList');
            if (!depts.length) {
                userList.innerHTML = '<p class="text-xs text-gray-400">Choisissez d\'abord un ou plusieurs départements.</p>';
                return;
            }
            userList.innerHTML = '<p class="text-xs text-gray-400">Chargement...</p>';
            try {
                const params = depts.map(d => 'departments[]=' + encodeURIComponent(d)).join('&');
                const r = await fetch('/admin/available-users?' + params, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const d = await r.json();
                userList.innerHTML = '';
                const users = d.users || [];
                if (users.length === 0) {
                    userList.innerHTML = '<p class="text-xs text-gray-400">Aucun utilisateur dans ces départements.</p>';
                    return;
                }
                users.forEach(u => {
                    const label = document.createElement('label');
                    label.className = 'flex items-center gap-2';
                    label.innerHTML = `
                        <input type="checkbox" value="${u.id}" class="rounded">
                        <span class="text-sm text-gray-700">${u.name} (${u.email})</span>
                    `;
                    userList.appendChild(label);
                });
            } catch (e) {
                userList.innerHTML = '<p class="text-xs text-red-500">Erreur de chargement.</p>';
            }
        };

        // Un listener délégué sur le conteneur : à chaque case département
        // cochée/décochée, on recharge la liste des utilisateurs avec
        // l'ensemble des départements actuellement sélectionnés.
        document.getElementById('departmentList').addEventListener('change', (e) => {
            if (!e.target.classList.contains('dept-checkbox')) return;
            const selected = Array.from(document.querySelectorAll('#departmentList .dept-checkbox:checked')).map(cb => cb.value);
            loadUsersForDepartment(selected);
        });

        window.appAddSubmit = async () => {
            const form = document.getElementById('appForm');
            const formData = new FormData(form);

            const adminIds = [];
            document.querySelectorAll('#adminList input[type="checkbox"]:checked').forEach(cb => {
                adminIds.push(cb.value);
            });

            const departments = Array.from(document.querySelectorAll('#departmentList .dept-checkbox:checked')).map(cb => cb.value);

            const userSelection = document.querySelector('input[name="userSelection"]:checked')?.value;
            const userIds = [];

            if (userSelection === 'specific') {
                document.querySelectorAll('#userList input[type="checkbox"]:checked').forEach(cb => {
                    userIds.push(cb.value);
                });
            }

            const data = {
                name: formData.get('name'),
                version: formData.get('version'),
                admin_id: adminIds[0] || '',
                admin_ids: adminIds,
                departments: departments,
                user_ids: userIds,
                all_department_users: userSelection === 'all'
            };

            if (!data.name || adminIds.length === 0) {
                this.toast('Veuillez remplir les champs obligatoires et choisir au moins un administrateur', false);
                return;
            }

            try {
                const r = await fetch('/admin/applications', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(data)
                });
                const d = await r.json();
                if (!r.ok || !d.success) throw new Error(d.message || 'Erreur');

                await this.loadApplications();
                this.toast('Application ajoutée avec succès');
                modal.remove();
            } catch (e) {
                this.toast(e.message, false);
            }
        };

        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    };

    context.editApplication = async function (appId) {
        let appData;
        try {
            const r = await fetch('/admin/applications/' + appId, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            appData = await r.json();
        } catch (e) {
            this.toast('Erreur chargement application', false);
            return;
        }

        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 overflow-y-auto';
        modal.innerHTML = `
            <div class="bg-white rounded-2xl shadow-xl max-w-2xl w-full my-8">
                <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h3 class="text-lg font-semibold text-gray-900">Modifier l'application</h3>
                    <button type="button" onclick="this.closest('.fixed').remove()" class="text-gray-400 hover:text-gray-600">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                </div>
                <form id="editAppForm" class="p-6 space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Nom de l'application *</label>
                        <input type="text" name="name" required value="${this.escapeHtml(appData.name)}" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-sonatrach-orange">
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Administrateurs * (sélection multiple)</label>
                        <div id="editAdminList" class="max-h-48 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2 bg-gray-50">
                            <p class="text-xs text-gray-400">Chargement...</p>
                        </div>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Départements (sélection multiple)</label>
                        <div id="editDepartmentList" class="max-h-40 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2 bg-gray-50">
                            <p class="text-xs text-gray-400">Chargement...</p>
                        </div>
                    </div>

                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-2">Utilisateurs</label>
                        <div class="flex gap-4 mb-3">
                            <label class="flex items-center gap-2">
                                <input type="radio" name="editUserSelection" value="all" class="rounded" onchange="document.getElementById('editUserList').classList.add('hidden')">
                                <span class="text-sm text-gray-700">Tout le département</span>
                            </label>
                            <label class="flex items-center gap-2">
                                <input type="radio" name="editUserSelection" value="specific" class="rounded" checked onchange="document.getElementById('editUserList').classList.remove('hidden')">
                                <span class="text-sm text-gray-700">Spécifiques</span>
                            </label>
                        </div>
                        <div id="editUserList" class="max-h-48 overflow-y-auto border border-gray-300 rounded-lg p-3 space-y-2 bg-gray-50">
                            <p class="text-xs text-gray-400">Choisissez un département pour voir ses employés.</p>
                        </div>
                    </div>
                </form>

                <div class="px-6 py-4 border-t border-gray-200 flex gap-3 justify-end">
                    <button type="button" onclick="this.closest('.fixed').remove()" class="px-4 py-2 rounded-lg text-sm border border-gray-300 text-gray-700 hover:bg-gray-50">Annuler</button>
                    <button type="button" onclick="window.appEditSubmit()" class="px-4 py-2 rounded-lg text-sm font-semibold bg-sonatrach-orange text-white hover:bg-sonatrach-orange-dark">Enregistrer</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const currentAdminIds = (appData.admin_ids || []).map(String);
        const currentUserIds  = (appData.user_ids || []).map(String);
        const currentDepartments = (appData.departments || []).map(String);

        Promise.all([
            fetch('/admin/available-users?admin=1', { headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(r => r.json()),
            fetch('/admin/departments', { headers: { 'X-Requested-With': 'XMLHttpRequest' } }).then(r => r.json())
        ]).then(([usersData, deptData]) => {
            const adminList = document.getElementById('editAdminList');
            adminList.innerHTML = '';
            (usersData.users || []).forEach(u => {
                const checked = currentAdminIds.includes(String(u.id)) ? 'checked' : '';
                const label = document.createElement('label');
                label.className = 'flex items-center gap-2';
                label.innerHTML = `<input type="checkbox" value="${u.id}" class="rounded" ${checked}><span class="text-sm text-gray-700">${u.name} (${u.email})</span>`;
                adminList.appendChild(label);
            });

            const departmentList = document.getElementById('editDepartmentList');
            departmentList.innerHTML = '';
            const depts = deptData.departments || [];
            if (depts.length === 0) {
                departmentList.innerHTML = '<p class="text-xs text-gray-400">Aucun département disponible.</p>';
            } else {
                depts.forEach(dept => {
                    const checked = currentDepartments.includes(String(dept)) ? 'checked' : '';
                    const label = document.createElement('label');
                    label.className = 'flex items-center gap-2';
                    label.innerHTML = `<input type="checkbox" value="${dept}" class="rounded edit-dept-checkbox" ${checked}><span class="text-sm text-gray-700">${dept}</span>`;
                    departmentList.appendChild(label);
                });
            }

            if (currentDepartments.length) loadEditUsersForDepartment(currentDepartments);
        }).catch(() => this.toast('Erreur chargement données', false));

        const loadEditUsersForDepartment = async (depts) => {
            const userList = document.getElementById('editUserList');
            if (!depts.length) {
                userList.innerHTML = '<p class="text-xs text-gray-400">Choisissez un ou plusieurs départements pour voir leurs employés.</p>';
                return;
            }
            userList.innerHTML = '<p class="text-xs text-gray-400">Chargement...</p>';
            try {
                const params = depts.map(d => 'departments[]=' + encodeURIComponent(d)).join('&');
                const r = await fetch('/admin/available-users?' + params, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                const d = await r.json();
                userList.innerHTML = '';
                (d.users || []).forEach(u => {
                    const checked = currentUserIds.includes(String(u.id)) ? 'checked' : '';
                    const label = document.createElement('label');
                    label.className = 'flex items-center gap-2';
                    label.innerHTML = `<input type="checkbox" value="${u.id}" class="rounded" ${checked}><span class="text-sm text-gray-700">${u.name} (${u.email})</span>`;
                    userList.appendChild(label);
                });
            } catch (e) {
                userList.innerHTML = '<p class="text-xs text-red-500">Erreur de chargement.</p>';
            }
        };

        document.getElementById('editDepartmentList').addEventListener('change', (e) => {
            if (!e.target.classList.contains('edit-dept-checkbox')) return;
            const selected = Array.from(document.querySelectorAll('#editDepartmentList .edit-dept-checkbox:checked')).map(cb => cb.value);
            loadEditUsersForDepartment(selected);
        });

        window.appEditSubmit = async () => {
            const form = document.getElementById('editAppForm');
            const formData = new FormData(form);

            const adminIds = [];
            document.querySelectorAll('#editAdminList input[type="checkbox"]:checked').forEach(cb => adminIds.push(cb.value));

            const departments = Array.from(document.querySelectorAll('#editDepartmentList .edit-dept-checkbox:checked')).map(cb => cb.value);

            const userSelection = document.querySelector('input[name="editUserSelection"]:checked')?.value;
            const userIds = [];
            if (userSelection === 'specific') {
                document.querySelectorAll('#editUserList input[type="checkbox"]:checked').forEach(cb => userIds.push(cb.value));
            }

            if (!formData.get('name') || adminIds.length === 0) {
                this.toast('Nom et au moins un administrateur requis', false);
                return;
            }

            try {
                const r = await fetch('/admin/applications/' + appId, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        name: formData.get('name'),
                        admin_ids: adminIds,
                        departments: departments,
                        user_ids: userIds,
                        all_department_users: userSelection === 'all'
                    })
                });
                const d = await r.json();
                if (!r.ok || !d.success) throw new Error(d.message || 'Erreur');

                await this.loadApplications();
                this.toast('Application mise à jour avec succès');
                modal.remove();
            } catch (e) {
                this.toast(e.message, false);
            }
        };

        modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    };

    context.deleteApplication = async function (appId) {
        try {
            const r = await fetch('/admin/applications/' + appId, {
                method: 'DELETE',
                headers: {
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').content,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            const d = await r.json();
            if (!r.ok || !d.success) throw new Error(d.message || 'Erreur');

            await this.loadApplications();
            this.toast('Application supprimée avec succès');
        } catch (e) {
            this.toast(e.message, false);
        }
    };
}

if (typeof window !== 'undefined') {
    window.setupAdminAndAppFunctions = setupAdminAndAppFunctions;
}
