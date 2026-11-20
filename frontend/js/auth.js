(() => {
    /*
     * AUTENTICAÇÃO
     *
     * DRIVER 'local' (config.js): contas e sessão só neste navegador
     * (senha com PBKDF2 via Web Crypto; NÃO equivale a segurança de produção).
     * DRIVER 'http': a sessão real é o cookie do Django; aqui fica apenas um
     * cache de "quem sou eu" (sem credenciais) para guardas e cabeçalho.
     * A API é sempre a autoridade: um 401 apaga o cache (ver api.js).
     *
     * Contrato (PROPOSTO, ver api.js e PENDENCIAS-API.md):
     * POST /api/auth/register/ · POST /api/auth/login/ · POST /api/auth/logout/
     * GET /api/auth/me/
     */

    const K = k => 'sam:v1:' + k,
        NOC = 'Este endereço não permite criptografia no navegador. Abra o projeto por http://localhost (python -m http.server).';

    const st = {
        get(k, d) {
            try {
                const v = localStorage.getItem(K(k));
                return v ? JSON.parse(v) : d;
            } catch (e) {
                return d;
            }
        },

        set(k, v) {
            try {
                localStorage.setItem(K(k), JSON.stringify(v));
                return true;
            } catch (e) {
                return false;
            }
        },

        del(k) {
            try {
                localStorage.removeItem(K(k));
            } catch (e) {}
        }
    };

    /* papéis: aceita os valores antigos do protótipo ('cliente', 'oficina') */

    const ROLES = {
        client: 'client',
        cliente: 'client',
        workshop: 'workshop',
        oficina: 'workshop',
        admin: 'admin'
    };

    const role = r => ROLES[r] || 'client';

    const b64 = b =>
        btoa(String.fromCharCode(...new Uint8Array(b))),
        unb = s =>
            Uint8Array.from(atob(s), c => c.charCodeAt(0));

    const can = () => !!(window.crypto && crypto.subtle);

    async function hash(pw, salt) {
        const k = await crypto.subtle.importKey(
            'raw',
            new TextEncoder().encode(pw),
            'PBKDF2',
            false,
            ['deriveBits']
        );

        return b64(
            await crypto.subtle.deriveBits(
                {
                    name: 'PBKDF2',
                    salt,
                    iterations: 100000,
                    hash: 'SHA-256'
                },
                k,
                256
            )
        );
    }

    /* o que vai para a sessão (nunca senha, sal ou hash) */

    const pub = a => ({
        id: a.id,
        name: a.name || a.name_fantasy || '',
        email: a.email,
        role: role(a.role),
        setup_complete: a.setup_complete
    });

    /* link seguro de retorno (?next=): só páginas .html do projeto */

    const SAFE = /^[a-z-]+\.html(\?[\w=&.-]*)?$/;

    const HOME = {
        client: 'vehicles.html',
        workshop: 'w-attendances.html',
        admin: 'index.html'
    };

    const A = {
        st,
        role,
        NOC,

        user() {
            const u = st.get('session', null);

            return u ? Object.assign({}, u, { role: role(u.role) }) : null;
        },

        setSession: u => st.set('session', pub(u)),

        clearSession: () => st.del('session'),

        /* ?next= validado; `def` quando ausente ou inseguro */

        next(def) {
            const n = new URLSearchParams(location.search).get('next') || '';

            return SAFE.test(n) ? n : def;
        },

        /* página inicial de cada perfil depois do login/cadastro */

        home(u) {
            u = u || A.user();

            if (!u) return 'login.html';

            return u.role === 'workshop' && u.setup_complete === false
                ? 'workshop-setup.html'
                : HOME[u.role] || 'index.html';
        },

        /*
         * Guarda de página.
         * require()                 → qualquer perfil logado
         * require('client')         → só Cliente (perfil errado → 404.html?code=403)
         * require('workshop', true) → Oficina com cadastro concluído; sem ele
         *                             vai para workshop-setup.html
         */
        require(r, needSetup) {
            const u = A.user();

            if (!u) {
                location.replace(
                    'login.html?next=' +
                    encodeURIComponent(
                        location.pathname.split('/').pop() + location.search
                    )
                );

                return false;
            }

            if (r && u.role !== r) {
                location.replace('404.html?code=403');

                return false;
            }

            if (needSetup && u.role === 'workshop' && u.setup_complete === false) {
                location.replace('workshop-setup.html');

                return false;
            }

            return true;
        },

        /* ---- driver local ---- */

        async register(d) {
            if (!can()) {
                return {
                    ok: false,
                    error: NOC
                };
            }

            const all = st.get('accounts', []),
                email = d.email.toLowerCase(),
                r = role(d.role);

            /* o mesmo e-mail pode existir como Cliente e como Oficina (RN01) */

            if (all.some(a => a.email === email && role(a.role) === r)) {
                return {
                    ok: false,
                    error: 'Já existe uma conta com este e-mail.',
                    fields: {
                        email: 'Já existe uma conta com este e-mail.'
                    }
                };
            }

            const salt = crypto.getRandomValues(new Uint8Array(16)),
                a = Object.assign(
                    {},
                    d.extra || {},
                    {
                        id: 'u' + Date.now().toString(36) + r[0],
                        name: d.name,
                        email,
                        role: r,
                        setup_complete: r === 'workshop' ? false : undefined,
                        salt: b64(salt),
                        hash: await hash(d.password, salt)
                    }
                );

            all.push(a);

            if (!st.set('accounts', all)) {
                return {
                    ok: false,
                    error: 'Não foi possível salvar a conta neste navegador.'
                };
            }

            A.setSession(a);

            return {
                ok: true,
                user: pub(a)
            };
        },

        async login(email, pw, r) {
            if (!can()) {
                return {
                    ok: false,
                    error: NOC
                };
            }

            const a = st.get('accounts', [])
                .find(x =>
                    x.email === email.toLowerCase() &&
                    role(x.role) === role(r)
                );

            if (!a || await hash(pw, unb(a.salt)) !== a.hash) {
                return {
                    ok: false,
                    error: 'E-mail ou senha incorretos.'
                };
            }

            A.setSession(a);

            return {
                ok: true,
                user: pub(a)
            };
        },

        /* logout só limpa o cache; o fluxo completo (API + redirect) é api.auth.logout */

        logout() {
            st.del('session');
            location.href = 'index.html';
        }
    };

    window.SAM = Object.assign(window.SAM || {}, {
        auth: A
    });
})();
