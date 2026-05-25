<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Session;
use Illuminate\Validation\ValidationException;

class LdapAuthController extends Controller
{
    // ═══════════════════════════════════════════════════
    //  PAGES
    // ═══════════════════════════════════════════════════

    public function showLogin()
    {
        if (Auth::check()) {
            return redirect()->route('chat.index');
        }
        return view('auth.login');
    }

    // ═══════════════════════════════════════════════════
    //  LOGIN
    // ═══════════════════════════════════════════════════

    public function login(Request $request)
    {
        $request->validate([
            'username' => ['required', 'string', 'max:20', 'regex:/^son\d{5}$/i'],
            'password' => ['required', 'string'],
        ], [
            'username.regex' => 'Le code employé doit être au format son00000 (ex : son00001).',
        ]);

        $username = trim($request->input('username'));
        $password = $request->input('password');

        $ldapUser = $this->authenticateWithLdap($username, $password);

        if ($ldapUser === null) {
            Log::warning('Échec connexion LDAP', [
                'username' => $username,
                'ip'       => $request->ip(),
            ]);

            throw ValidationException::withMessages([
                'username' => 'Code employé ou mot de passe incorrect.',
            ]);
        }

        $user = $this->syncUserToDatabase($ldapUser);
        Auth::login($user, false);

        $groups     = isset($ldapUser['groups']) ? $ldapUser['groups'] : [];
        $adminGroup = strtolower((string) config('ldap.admin_group', 'admins'));
        $isAdmin    = in_array($adminGroup, $groups, true);

        // Stocke valeurs LDAP et valeurs stabilisées depuis la base (préférer le nom enregistré en base)
        Session::put('ldap_uid',      $ldapUser['uid']);
        Session::put('ldap_son_code', $ldapUser['employee_no']);
        // Utiliser le nom stocké en base (après sync) afin d'afficher prénom + nom
        // Stocker le nom d'affichage (prénom + nom si possible)
        Session::put('user_name',     $user->display_name ?? $user->name);
        Session::put('user_email',    $user->email ?? $this->coalesce($ldapUser, ['mail'], ''));
        Session::put('user_title',    $user->title ?? $this->coalesce($ldapUser, ['title'], ''));
        Session::put('user_dn',       $user->ldap_dn ?? $this->coalesce($ldapUser, ['dn'], ''));
        // Prendre le flag admin calculé (depuis LDAP ou base)
        Session::put('is_admin',      $user->is_admin ?? $isAdmin);

        Log::info('Connexion LDAP réussie', [
            'son_code' => $username,
            'uid'      => $ldapUser['uid'],
            'ip'       => $request->ip(),
            'is_admin' => $isAdmin,
        ]);

        // ── Redirection selon le rôle ──
        if ($isAdmin) {
            return redirect()->intended(route('admin.index'));
        }

        return redirect()->intended(route('chat.index'));
    }

    // ═══════════════════════════════════════════════════
    //  LOGOUT
    // ═══════════════════════════════════════════════════

    public function logout(Request $request)
    {
        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect()->route('login');
    }

    // ═══════════════════════════════════════════════════
    //  LDAP — AUTHENTIFICATION
    // ═══════════════════════════════════════════════════

    private function authenticateWithLdap(string $username, string $password)
    {
        // ── Lecture config ──
        $host         = config('ldap.host', 'localhost');
        $port         = (int) config('ldap.port', 389);
        $baseDn       = (string) config('ldap.base_dn', 'dc=sonatrach,dc=test');
        $usersOu      = (string) config('ldap.users_ou', "ou=people,{$baseDn}");
        $bindDn       = (string) config('ldap.bind_dn', '');
        $bindPassword = (string) config('ldap.bind_password', '');

        $normalizedLogin = $this->normalizeLoginIdentifier($username);
        $usersDn = (stripos($usersOu, $baseDn) !== false) ? $usersOu : "{$usersOu},{$baseDn}";

        Log::debug('LDAP: tentative connexion', [
            'host'      => $host,
            'port'      => $port,
            'son_code'  => $username,
            'baseDn'    => $baseDn,
        ]);

        // ── Connexion ──
        $conn = @ldap_connect("ldap://{$host}:{$port}");

        if ($conn === false) {
            Log::error('LDAP: ldap_connect() a échoué', [
                'host' => $host,
                'port' => $port,
            ]);
            return null;
        }

        ldap_set_option($conn, LDAP_OPT_PROTOCOL_VERSION, 3);
        ldap_set_option($conn, LDAP_OPT_REFERRALS, 0);
        ldap_set_option($conn, LDAP_OPT_NETWORK_TIMEOUT, config('ldap.timeout', 5));

        // ── Le login est un code SON → on ne peut pas construire un DN direct.
        //    On passe directement au fallback par recherche.
        //    Pour les autres formats (uid/cn), on tente d'abord le bind direct.
        $authenticatedDn  = null;
        $looksLikeSonCode = (bool) preg_match('/^son\d+$/i', $normalizedLogin);

        if (!$looksLikeSonCode) {
            // Tentative directe avec DN candidats uid= / cn=
            $candidateDns = [
                'uid=' . $this->ldapDnEscape($normalizedLogin) . ',' . $usersDn,
                'cn='  . $this->ldapDnEscape($normalizedLogin) . ',' . $usersDn,
            ];

            foreach ($candidateDns as $candidateDn) {
                if (@ldap_bind($conn, $candidateDn, $password)) {
                    $authenticatedDn = $candidateDn;
                    break;
                }
            }
        }

        // ── Fallback : recherche du DN réel par employeeNumber (ou uid/mail/cn)
        //    puis bind utilisateur avec ce DN résolu
        if ($authenticatedDn === null) {
            $serviceBound = false;

            if ($bindDn !== '') {
                $serviceBound = @ldap_bind($conn, $bindDn, $bindPassword);
            } else {
                $serviceBound = @ldap_bind($conn);
            }

            Log::debug('LDAP: service bind status', [
                'serviceBound' => $serviceBound,
                'bindDn'       => (!empty($bindDn) ? 'avec compte service' : 'anonyme'),
            ]);

            if ($serviceBound) {
                $searchFilter = $this->buildUserSearchFilter($username, $normalizedLogin);

                Log::debug('LDAP: recherche utilisateur (1ère tentative)', [
                    'searchBase' => $usersDn,
                    'filter'     => $searchFilter,
                ]);

                $search = @ldap_search($conn, $usersDn, $searchFilter, ['dn']);

                if ($search !== false) {
                    $entries = ldap_get_entries($conn, $search);
                } else {
                    $entries = null;
                    Log::debug('LDAP: recherche (1ère) échouée', [
                        'errno' => ldap_errno($conn),
                        'error' => ldap_error($conn),
                    ]);
                }

                Log::debug('LDAP: résultats de recherche', [
                    'count'    => (is_array($entries) && isset($entries['count'])) ? $entries['count'] : 'null/error',
                ]);

                // ── Si pas de résultats ET recherche dans OU au lieu de baseDn, réessayer en baseDn
                if (($entries === null || (isset($entries['count']) && (int) $entries['count'] === 0)) && $usersDn !== $baseDn) {
                    Log::debug('LDAP: tentative fallback en baseDn', [
                        'usersDn' => $usersDn,
                        'baseDn'  => $baseDn,
                    ]);

                    $search = @ldap_search($conn, $baseDn, $searchFilter, ['dn']);
                    if ($search !== false) {
                        $entries = ldap_get_entries($conn, $search);
                    } else {
                        $entries = null;
                        Log::debug('LDAP: recherche (fallback) échouée', [
                            'errno' => ldap_errno($conn),
                            'error' => ldap_error($conn),
                        ]);
                    }

                    Log::debug('LDAP: résultats de recherche (fallback)', [
                        'count' => (is_array($entries) && isset($entries['count'])) ? $entries['count'] : 'null/error',
                    ]);
                }

                if ($entries !== null && isset($entries['count']) && (int) $entries['count'] > 0 && isset($entries[0]['dn'])) {
                    $resolvedDn = (string) $entries[0]['dn'];

                    Log::debug('LDAP: tentative bind avec DN résolu', [
                        'resolvedDn' => $resolvedDn,
                    ]);

                    if (@ldap_bind($conn, $resolvedDn, $password)) {
                        $authenticatedDn = $resolvedDn;
                        Log::debug('LDAP: bind utilisateur réussi', [
                            'userDn' => $resolvedDn,
                        ]);
                    } else {
                        Log::debug('LDAP: bind utilisateur échoué', [
                            'userDn' => $resolvedDn,
                            'errno'  => ldap_errno($conn),
                            'error'  => ldap_error($conn),
                        ]);
                    }
                } else {
                    Log::debug('LDAP: DN non trouvé ou entries invalides', [
                        'entriesIsNull'    => $entries === null,
                        'hasCount'         => isset($entries['count']),
                        'countValue'       => (isset($entries['count'])) ? $entries['count'] : 'n/a',
                        'hasFirstEntry'    => (isset($entries[0])) ? true : false,
                        'hasFirstEntryDn'  => (isset($entries[0]['dn'])) ? true : false,
                    ]);
                }
            } else {
                Log::debug('LDAP: service bind échoué', [
                    'errno' => ldap_errno($conn),
                    'error' => ldap_error($conn),
                ]);
            }
        }

        if ($authenticatedDn === null) {
            Log::debug('LDAP: bind échoué', [
                'son_code'   => $username,
                'normalized' => $normalizedLogin,
                'errno'      => ldap_errno($conn),
                'error'      => ldap_error($conn),
            ]);

            @ldap_close($conn);
            return null;
        }

        // ── Recherche des attributs ──
        $attrs = [
            'uid', 'cn', 'sn', 'givenname', 'displayname',
            'mail', 'title', 'ou', 'departmentnumber',
            'employeenumber', 'memberof',
        ];

        $filter = $this->buildUserSearchFilter($username, $normalizedLogin);

        Log::debug('LDAP: recherche attributs (1ère tentative)', [
            'searchBase' => $usersDn,
            'filter'     => $filter,
        ]);

        $search = @ldap_search($conn, $usersDn, $filter, $attrs);

        if ($search !== false) {
            $entries = ldap_get_entries($conn, $search);
        } else {
            $entries = null;
            Log::debug('LDAP: recherche attributs (1ère) échouée', [
                'errno' => ldap_errno($conn),
                'error' => ldap_error($conn),
            ]);
        }

        Log::debug('LDAP: résultats recherche attributs', [
            'count' => (is_array($entries) && isset($entries['count'])) ? $entries['count'] : 'null/error',
        ]);

        // ── Si pas de résultats ET recherche dans OU au lieu de baseDn, réessayer en baseDn
        if (($entries === null || (isset($entries['count']) && (int) $entries['count'] === 0)) && $usersDn !== $baseDn) {
            Log::debug('LDAP: fallback recherche attributs en baseDn', [
                'usersDn' => $usersDn,
                'baseDn'  => $baseDn,
            ]);

            $search = @ldap_search($conn, $baseDn, $filter, $attrs);
            if ($search !== false) {
                $entries = ldap_get_entries($conn, $search);
            } else {
                $entries = null;
                Log::debug('LDAP: recherche attributs (fallback) échouée', [
                    'errno' => ldap_errno($conn),
                    'error' => ldap_error($conn),
                ]);
            }

            Log::debug('LDAP: résultats recherche attributs (fallback)', [
                'count' => (is_array($entries) && isset($entries['count'])) ? $entries['count'] : 'null/error',
            ]);
        }

        $userData = null;

        if ($entries !== null && isset($entries['count']) && (int) $entries['count'] > 0) {
            $entry    = $entries[0];
            $userData = [
                'dn'          => isset($entry['dn']) ? $entry['dn'] : $authenticatedDn,
                'uid'         => $this->ldapAttr($entry, 'uid',         $normalizedLogin),
                'cn'          => $this->ldapAttr($entry, 'cn',          $normalizedLogin),
                'sn'          => $this->ldapAttr($entry, 'sn',          ''),
                'givenname'   => $this->ldapAttr($entry, 'givenname',   ''),
                'displayname' => $this->ldapAttr($entry, 'displayname', $normalizedLogin),
                'mail'        => $this->ldapAttr($entry, 'mail',        "{$normalizedLogin}@sonatrach.dz"),
                'title'       => $this->ldapAttr($entry, 'title',       ''),
                'ou'          => $this->ldapAttr($entry, 'ou',          ''),
                'department'  => $this->ldapAttr($entry, 'departmentnumber', ''),
                'employee_no' => $this->ldapAttr($entry, 'employeenumber',   strtolower($normalizedLogin)),
                'groups'      => $this->ldapGroups($entry),
            ];

            Log::debug('LDAP: attributs récupérés', [
                'uid'         => $userData['uid'],
                'employee_no' => $userData['employee_no'],
                'mail'        => $userData['mail'],
                'groups'      => $userData['groups'],
            ]);
        } else {
            Log::warning('LDAP: utilisateur non trouvé après bind', [
                'son_code'    => $username,
                'filter'      => $filter,
                'search_base' => $usersDn,
            ]);
        }

        // ── Vérification groupe admin par recherche inversée (groupOfNames) ──
        $isAdminByGroup = $this->isUserInAdminGroup($conn, $authenticatedDn, $baseDn);

        @ldap_close($conn);

        // Bind réussi mais attributs non trouvés → retour minimal
        if ($userData === null) {
            // Essayer de retrouver l'utilisateur dans le fichier LDIF local (fallback)
            $ldifUser = $this->findUserInLdif(strtolower($normalizedLogin));
            if ($ldifUser !== null) {
                $userData = $ldifUser;
            } else {
                $userData = [
                    'dn'          => $authenticatedDn,
                    'uid'         => $normalizedLogin,
                    'cn'          => $normalizedLogin,
                    'sn'          => '',
                    'givenname'   => '',
                    'displayname' => $normalizedLogin,
                    'mail'        => "{$normalizedLogin}@sonatrach.dz",
                    'title'       => '',
                    'ou'          => '',
                    'department'  => '',
                    'employee_no' => strtolower($normalizedLogin),
                    'groups'      => [],
                ];
            }
        }

        // ── Injecte "admins" dans groups si trouvé par recherche inversée ──
        if ($isAdminByGroup && !in_array('admins', $userData['groups'], true)) {
            $userData['groups'][] = 'admins';
            Log::debug('LDAP: admin détecté par recherche inversée groupOfNames', [
                'userDn' => $authenticatedDn,
            ]);
        }

        return $userData;
    }

    // ═══════════════════════════════════════════════════
    //  LDAP — VÉRIFICATION GROUPE ADMIN (RECHERCHE INVERSÉE)
    // ═══════════════════════════════════════════════════

    /**
     * Vérifie si un DN utilisateur est membre du groupe admin.
     * Supporte le schéma groupOfNames où "member:" est sur le groupe.
     */
    private function isUserInAdminGroup(mixed $conn, string $userDn, string $baseDn): bool
    {
        $adminGroup = strtolower((string) config('ldap.admin_group', 'admins'));
        $groupsOu   = "ou=groups,{$baseDn}";

        // ── Rebind avec compte service pour pouvoir faire la recherche ──
        $bindDn       = (string) config('ldap.bind_dn', '');
        $bindPassword = (string) config('ldap.bind_password', '');

        if ($bindDn !== '') {
            @ldap_bind($conn, $bindDn, $bindPassword);
        } else {
            @ldap_bind($conn);
        }

        $escapedDn    = $this->ldapFilterEscape($userDn);
        $escapedGroup = $this->ldapFilterEscape($adminGroup);
        $filter       = "(&(objectClass=groupOfNames)(cn={$escapedGroup})(member={$escapedDn}))";

        $search = @ldap_search($conn, $groupsOu, $filter, ['cn']);

        if ($search === false) {
            $search = @ldap_search($conn, $baseDn, $filter, ['cn']);
        }

        if ($search === false) {
            Log::warning('LDAP: recherche groupe admin échouée', [
                'userDn'     => $userDn,
                'adminGroup' => $adminGroup,
            ]);
            return false;
        }

        $entries = ldap_get_entries($conn, $search);
        $found   = isset($entries['count']) && (int) $entries['count'] > 0;

        Log::debug('LDAP: vérification groupe admin', [
            'userDn'     => $userDn,
            'adminGroup' => $adminGroup,
            'found'      => $found,
        ]);

        return $found;
    }

    // ═══════════════════════════════════════════════════
    //  LDAP — HELPERS
    // ═══════════════════════════════════════════════════

    /**
     * Extrait une valeur d'une entrée LDAP.
     */
    private function ldapAttr(array $entry, string $attr, string $default = ''): string
    {
        $key = strtolower($attr);
        if (isset($entry[$key]) && isset($entry[$key][0]) && $entry[$key][0] !== '') {
            return (string) $entry[$key][0];
        }
        return $default;
    }

    /**
     * Extrait les groupes depuis l'attribut memberOf (schéma inetOrgPerson).
     * Complément de isUserInAdminGroup() pour les schémas groupOfNames.
     */
    private function ldapGroups(array $entry): array
    {
        $groups = [];

        if (!isset($entry['memberof'])) {
            return $groups;
        }

        $count = isset($entry['memberof']['count']) ? (int) $entry['memberof']['count'] : 0;

        for ($i = 0; $i < $count; $i++) {
            $dn = $entry['memberof'][$i];
            if (preg_match('/^cn=([^,]+)/i', $dn, $matches)) {
                $groups[] = strtolower($matches[1]);
            }
        }

        return $groups;
    }

    /**
     * Normalise les formats de login (DOMAIN\\user, user@domain, user).
     */
    private function normalizeLoginIdentifier(string $login): string
    {
        $value = trim($login);

        if (strpos($value, '\\') !== false) {
            $parts = explode('\\', $value);
            $value = end($parts);
        }

        if (strpos($value, '@') !== false) {
            $parts = explode('@', $value);
            $value = $parts[0];
        }

        return trim((string) $value);
    }

    /**
     * Construit un filtre LDAP sécurisé pour retrouver un utilisateur.
     * Inclut employeeNumber pour permettre la recherche par code SON.
     */
    private function buildUserSearchFilter(string $rawLogin, string $normalizedLogin): string
    {
        $values = array_unique(array_filter([$rawLogin, $normalizedLogin]));
        $parts  = [];

        foreach ($values as $value) {
            $safe    = $this->ldapFilterEscape($value);
            $parts[] = "(uid={$safe})";
            $parts[] = "(mail={$safe})";
            $parts[] = "(cn={$safe})";
            $parts[] = "(employeeNumber={$safe})";   // ← recherche par code SON
        }

        return '(|' . implode('', $parts) . ')';
    }

    private function ldapFilterEscape(string $value): string
    {
        if (function_exists('ldap_escape')) {
            return ldap_escape($value, '', LDAP_ESCAPE_FILTER);
        }

        return strtr($value, [
            '\\'  => '\\5c',
            '*'   => '\\2a',
            '('   => '\\28',
            ')'   => '\\29',
            "\0"  => '\\00',
        ]);
    }

    private function ldapDnEscape(string $value): string
    {
        if (function_exists('ldap_escape')) {
            return ldap_escape($value, '', LDAP_ESCAPE_DN);
        }

        return addcslashes($value, ',=+<>#;"\\');
    }

    /**
     * Retourne la première valeur non vide dans un tableau.
     */
    private function coalesce(array $data, array $keys, string $fallback = ''): string
    {
        foreach ($keys as $key) {
            if (isset($data[$key]) && $data[$key] !== '') {
                return (string) $data[$key];
            }
        }
        return $fallback;
    }

    /**
     * Fallback pour environnements de dev : recherche dans un fichier LDIF local
     * Renvoie un tableau d'attributs compatible avec la structure attendue par authenticateWithLdap()
     */
    private function findUserInLdif(string $employeeNo): ?array
    {
        // Chemin relatif au projet (ajustez si nécessaire)
        $path = base_path('../docker/openldap/ldif/users.ldif');
        if (!file_exists($path) || !is_readable($path)) {
            return null;
        }

        $content = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        if ($content === false) return null;

        $entry = [];
        foreach ($content as $line) {
            // Les blocs LDIF sont séparés par des lignes vides — mais nous avons utilisé FILE_SKIP_EMPTY_LINES
            // On détecte les débuts de dn: pour séparer les entrées
            if (stripos($line, 'dn:') === 0) {
                // nouvelle entrée → vider l'ancien si présent
                $entry = ['dn' => trim(substr($line, 3))];
                continue;
            }

            // Si pas d'entrée courante, continuer
            if (empty($entry)) continue;

            // Parse key: value
            if (preg_match('/^([a-zA-Z0-9-]+):\s*(.+)$/', $line, $m)) {
                $k = strtolower($m[1]);
                $v = trim($m[2]);
                // Certains attributs peuvent apparaître plusieurs fois (memberOf) — on ignore ici
                if (!isset($entry[$k])) $entry[$k] = $v;
                continue;
            }

            // Quand on rencontre un commentaire ou autre ligne, continuer
        }

        // Simple scan : relire le fichier en blocs (séparateur = ligne vide)
        $raw = file_get_contents($path);
        if ($raw === false) return null;

        $blocks = preg_split('/\R{2,}/', $raw);
        foreach ($blocks as $blk) {
            if (stripos($blk, "employeeNumber: {$employeeNo}") !== false
                || stripos($blk, "employeeNumber: {$employeeNo}\r") !== false) {
                // extraire attributs
                $lines = preg_split('/\R/', $blk);
                $out = [
                    'dn' => '', 'uid' => '', 'cn' => '', 'sn' => '', 'givenname' => '', 'displayname' => '',
                    'mail' => '', 'title' => '', 'ou' => '', 'department' => '', 'employee_no' => $employeeNo, 'groups' => [],
                ];
                foreach ($lines as $l) {
                    if (preg_match('/^dn:\s*(.+)$/i', $l, $m)) $out['dn'] = trim($m[1]);
                    if (preg_match('/^uid:\s*(.+)$/i', $l, $m)) $out['uid'] = trim($m[1]);
                    if (preg_match('/^cn:\s*(.+)$/i', $l, $m)) $out['cn'] = trim($m[1]);
                    if (preg_match('/^sn:\s*(.+)$/i', $l, $m)) $out['sn'] = trim($m[1]);
                    if (preg_match('/^givenName:\s*(.+)$/i', $l, $m)) $out['givenname'] = trim($m[1]);
                    if (preg_match('/^displayname:\s*(.+)$/i', $l, $m)) $out['displayname'] = trim($m[1]);
                    if (preg_match('/^mail:\s*(.+)$/i', $l, $m)) $out['mail'] = trim($m[1]);
                    if (preg_match('/^title:\s*(.+)$/i', $l, $m)) $out['title'] = trim($m[1]);
                    if (preg_match('/^ou:\s*(.+)$/i', $l, $m)) $out['ou'] = trim($m[1]);
                }
                // Ensure some defaults
                if (empty($out['displayname'])) $out['displayname'] = $out['cn'] ?: $out['uid'] ?: $employeeNo;
                if (empty($out['mail'])) $out['mail'] = ($out['uid'] ? $out['uid'] . '@sonatrach.dz' : $employeeNo . '@sonatrach.dz');
                return $out;
            }
        }

        return null;
    }

    // ═══════════════════════════════════════════════════
    //  BASE DE DONNÉES — SYNCHRONISATION
    // ═══════════════════════════════════════════════════

    private function syncUserToDatabase(array $ldapUser): User
    {
        $uid        = $ldapUser['uid'];
        $employeeNo = $ldapUser['employee_no'];
        $email      = ($ldapUser['mail'] !== '') ? $ldapUser['mail'] : "{$uid}@sonatrach.dz";

        // Construire un nom lisible : privilégier givenName + sn, puis displayName/cn,
        // puis fallback LDIF local si le résultat ressemble encore à un code SON.
        $name = $this->resolveDisplayName($ldapUser, $uid, $employeeNo);

        $groups     = isset($ldapUser['groups']) ? $ldapUser['groups'] : [];
        $adminGroup = strtolower((string) config('ldap.admin_group', 'admins'));
        $isAdmin    = in_array($adminGroup, $groups, true);

        $dept = ($ldapUser['department'] !== '')
            ? $ldapUser['department']
            : $ldapUser['ou'];

        $user = User::firstOrNew(['ldap_uid' => $uid]);
        $user->forceFill([
            'name'          => $name,
            'email'         => $email,
            'employee_no'   => $employeeNo,
            'title'         => $ldapUser['title'],
            'department'    => $dept,
            'is_admin'      => $isAdmin,
            'password'      => '*',
            'last_login_at' => now(),
        ]);
        $user->save();

        return $user;
    }

    /**
     * Résout un nom d'affichage lisible à partir de LDAP/LDIF.
     * Évite de laisser passer un code SON comme "son00003" quand le LDIF
     * contient déjà un cn/givenName/sn plus parlant.
     */
    private function resolveDisplayName(array $ldapUser, string $uid, string $employeeNo): string
    {
        $given = $this->coalesce($ldapUser, ['givenname'], '');
        $sn    = $this->coalesce($ldapUser, ['sn'], '');

        if ($given !== '' || $sn !== '') {
            $candidate = trim(($given ?: '') . ' ' . ($sn ?: ''));
        } else {
            $candidate = $this->coalesce($ldapUser, ['displayname', 'cn'], '');
        }

        if ($candidate === '' || preg_match('/^son\d{5}$/i', $candidate) || $candidate === $uid || $candidate === $employeeNo) {
            $ldifUser = $this->findUserInLdif($employeeNo);

            if (is_array($ldifUser)) {
                $ldifGiven = $this->coalesce($ldifUser, ['givenname'], '');
                $ldifSn    = $this->coalesce($ldifUser, ['sn'], '');

                if ($ldifGiven !== '' || $ldifSn !== '') {
                    $ldifCandidate = trim(($ldifGiven ?: '') . ' ' . ($ldifSn ?: ''));
                    if ($ldifCandidate !== '') {
                        return $ldifCandidate;
                    }
                }

                $ldifCandidate = $this->coalesce($ldifUser, ['displayname', 'cn'], '');
                if ($ldifCandidate !== '') {
                    return $ldifCandidate;
                }
            }
        }

        if ($candidate !== '') {
            return $candidate;
        }

        return $uid;
    }
}
