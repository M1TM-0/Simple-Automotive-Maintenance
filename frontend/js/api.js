(() => {
    /*
     * API: ÚNICA porta de entrada para dados.
     *
     * Todos os endpoints abaixo são PROPOSTOS (inspirados no CLAUDE.md e nas
     * colunas do init.sql). Se o backend divergir, o ajuste fica só aqui.
     * Contrato completo e campos sem coluna: PENDENCIAS-API.md.
     *
     * Regras:
     * - DRIVER 'local' só atende auth, veículos e conversas do cliente
     *   (localStorage). Todo o resto responde API_UNAVAILABLE: sem dado fictício.
     * - Erros viram { status, code, detail, fields }.
     * - 401 → login.html?next=… · 403 → 404.html?code=403 (exceto soft)
     * - Listas voltam sempre como { count, next, previous, results }.
     */

    const C = SAM.config,
        A = SAM.auth;

    /* erros no formato { status, code, detail, fields } (definição única, em data.js) */

    const mk = o => Object.assign(
        SAM.local.err(o.status, o.detail || o.code || 'Erro'),
        o
    );

    const UNAVAIL = () => mk({
        status: 0,
        code: 'API_UNAVAILABLE',
        detail: 'O servidor ainda não está disponível.'
    });

    const isLocal = () => C.DRIVER !== 'http';

    const cookie = n => {
        const m = document.cookie.match(
            new RegExp('(?:^|; )' + n + '=([^;]*)')
        );

        return m ? decodeURIComponent(m[1]) : '';
    };

    /* primeira mensagem de um erro DRF (string, lista ou objeto aninhado) */

    const first = v =>
        Array.isArray(v)
            ? first(v[0])
            : v && typeof v === 'object'
                ? first(Object.values(v)[0])
                : v;

    const DEF = {
        400: 'Confira os dados informados.',
        404: 'Não encontrado.',
        409: 'A operação conflita com o estado atual.',
        500: 'Algo deu errado no servidor. Tente de novo.'
    };

    function norm(status, body) {
        const fields = {};
        let detail = '';

        if (body && typeof body === 'object' && !Array.isArray(body)) {
            Object.entries(body).forEach(([k, v]) => {
                if (k === 'detail' || k === 'non_field_errors') {
                    detail = detail || String(first(v) ?? '');
                } else if (k !== 'code') {
                    fields[k] = String(first(v) ?? '');
                }
            });
        } else if (Array.isArray(body)) {
            detail = String(first(body) ?? '');
        }

        detail = detail ||
            Object.values(fields)[0] ||
            DEF[status] ||
            'Não foi possível concluir a operação.';

        return mk({
            status,
            code: (body && body.code) || 'HTTP_' + status,
            detail,
            fields
        });
    }

    /* ---- HTTP ---- */

    let primed = false;

    async function req(method, path, o = {}) {
        if (isLocal() || !C.API_BASE) throw UNAVAIL();

        const q = new URLSearchParams();

        Object.entries(o.query || {}).forEach(([k, v]) => {
            if (v !== undefined && v !== null && v !== '') q.append(k, v);
        });

        const url = C.API_BASE.replace(/\/+$/, '') + '/api' + path +
            (q.toString() ? '?' + q : '');

        const h = { Accept: 'application/json' };
        let body;

        if (o.body instanceof FormData) {
            body = o.body;
        } else if (o.body !== undefined) {
            h['Content-Type'] = 'application/json';
            body = JSON.stringify(o.body);
        }

        if (method !== 'GET') {
            let t = cookie('csrftoken');

            /* sem cookie ainda (1º POST da página): um GET seguro o define (P8) */

            if (!t && !primed) {
                primed = true;

                try {
                    await G('/auth/me/', undefined, { quiet: true });
                } catch (e) {}

                t = cookie('csrftoken');
            }

            if (t) h['X-CSRFToken'] = t;
        }

        let r;

        try {
            r = await fetch(url, {
                method,
                headers: h,
                body,
                credentials: 'include'
            });
        } catch (e) {
            throw UNAVAIL();
        }

        if (r.status === 204) return null;

        let data = null;

        try {
            data = await r.json();
        } catch (e) {}

        if (r.ok) return data;

        const err = norm(r.status, data);

        if (r.status === 401 && !o.quiet) {
            A.clearSession();

            if (!/login\.html$/.test(location.pathname)) {
                location.replace(
                    'login.html?next=' +
                    encodeURIComponent(
                        location.pathname.split('/').pop() + location.search
                    )
                );
            }
        }

        if (r.status === 403 && !o.soft && !o.quiet) {
            location.replace('404.html?code=403');
        }

        throw err;
    }

    const G = (p, q, o) => req('GET', p, Object.assign({ query: q }, o)),
        P = (p, b, o) => req('POST', p, Object.assign({ body: b }, o)),
        PA = (p, b, o) => req('PATCH', p, Object.assign({ body: b }, o)),
        PU = (p, b, o) => req('PUT', p, Object.assign({ body: b }, o)),
        D = (p, o) => req('DELETE', p, o);

    const paged = r =>
        Array.isArray(r)
            ? { count: r.length, next: null, previous: null, results: r }
            : r && Array.isArray(r.results)
                ? r
                : { count: 0, next: null, previous: null, results: [] };

    const L = async (p, q, o) => paged(await G(p, q, o));

    /* número da página a partir do `next` do DRF */

    const pageOf = next => {
        try {
            return +new URL(next, 'http://x').searchParams.get('page') || null;
        } catch (e) {
            return null;
        }
    };

    /* junta todas as páginas (catálogos pequenos: categorias, serviços…) */

    async function all(path, q, o) {
        let out = [],
            page = 1;

        for (let i = 0; i < 30; i++) {
            const r = await L(path, Object.assign({}, q, { page }), o);

            out = out.concat(r.results);

            if (!r.next) break;

            page = pageOf(r.next) || page + 1;
        }

        return { count: out.length, next: null, previous: null, results: out };
    }

    const LO = SAM.local;

    /* leitura pública (visitante): um 401/403 não pode jogar o visitante no login */

    const Q = { quiet: true };

    /* FormData do veículo (multipart) — `photos` = 3 posições: null | {url} | {blob} */

    function vForm(fields, photos, clear) {
        const fd = new FormData();

        Object.entries(fields).forEach(([k, v]) => {
            if (v !== undefined && v !== null) fd.append(k, v);
        });

        (photos || []).forEach((s, i) => {
            if (s && s.blob) fd.append('photo_' + (i + 1), s.blob, 'foto' + (i + 1) + '.jpg');
            else if (!s && clear) fd.append('photo_' + (i + 1), '');
        });

        return fd;
    }

    /* ---- conversas: normalização (uma forma só para as telas) ---- */

    const ROLE = () => (A.user() || {}).role;

    const normChat = c => ({
        id: c.id ?? c.id_chat,
        name: (c.workshop && c.workshop.name_fantasy) ||
            (c.client && c.client.name) ||
            c.name ||
            'Conversa',
        photo: (c.workshop && c.workshop.photo_profile) ||
            (c.client && c.client.photo_profile) ||
            null,
        workshop_id: c.workshop ? c.workshop.id_workshop ?? c.workshop.id : c.id_workshop,
        last_message: c.last_message
            ? (c.last_message.content ?? c.last_message)
            : '',
        last_at: c.last_message && c.last_message.date_sent
            ? c.last_message.date_sent
            : c.last_at || null,
        last_label: c.last_label || '',
        unread: c.unread_count || 0,
        open_attendance: c.open_attendance || null
    });

    const normMsg = m => {
        const from = m.sender || (m.id_client != null ? 'client' : 'workshop');

        return {
            id: m.id ?? m.id_message,
            content: m.content,
            at: m.date_sent || m.at || null,
            label: m.label || '',
            status: m.status_message || m.status || null,
            mine: m.mine !== undefined ? !!m.mine : from === ROLE()
        };
    };

    /*
     * promoções e divulgações em execução → uma forma só.
     * kind: 'promotion' | 'advertisement' (alvo da denúncia, M03).
     */

    const normPromo = p => ({
        id: p.id,
        kind: p.kind || 'promotion',
        title: p.title || 'Promoção',
        description: p.description || '',
        image: p.image_url || p.image || null,
        workshop_id: p.workshop ? p.workshop.id : p.id_workshop,
        workshop_name: p.workshop ? p.workshop.name_fantasy : (p.workshop_name || ''),
        type_discount: p.type_discount,
        discount_value: p.discount_value,
        date_end: p.date_end,
        valid: p.is_valid_now !== false && p.is_running_now !== false
    });

    /* oficina pública: aceita campos planos ou aninhados (page.*, point.*) */

    const normWorkshop = w => {
        const pg = w.page || {},
            pt = w.point || {};

        return Object.assign({}, w, {
            description: w.description ?? pg.description ?? '',
            photo_profile: w.photo_profile ?? pg.photo_profile ?? null,
            photo_banner: w.photo_banner ?? pg.photo_banner ?? null,
            address: w.address ?? pt.address ?? '',
            latitude: w.latitude ?? pt.latitude ?? null,
            longitude: w.longitude ?? pt.longitude ?? null,
            type: w.type ?? pt.type ?? null,
            operation_hours: w.operation_hours || [],
            services: w.services || [],
            gallery: w.gallery || w.photos || []
        });
    };

    /*
     * atendimento visto pela oficina (T19). O backend guarda o pedido do cliente
     * em `observations` e as notas da oficina em `technical_notes` (DP-13).
     * A tela edita "Observações técnicas (iniciadas com o pedido do cliente)"
     * lendo `observations`: aqui ela recebe as notas técnicas (ou, enquanto
     * não houver, o pedido do cliente) e o pedido original fica em
     * `client_observations`. O PATCH continua enviando `observations`
     * (sinônimo de `technical_notes` no backend).
     */

    const normWAtt = a => a && typeof a === 'object'
        ? Object.assign({}, a, {
            client_observations: a.observations ?? null,
            observations: a.technical_notes || a.observations || ''
        })
        : a;

    const vehicles = {
        list: q => isLocal() ? LO.vehicles.list() : L('/vehicles/', q),

        get: id => isLocal() ? LO.vehicles.get(id) : G('/vehicles/' + id + '/'),

        /* p = { fields, photos: [3 posições: null | {url} | {blob}] } */

        create: p => isLocal()
            ? LO.vehicles.create(p)
            : P('/vehicles/', vForm(p.fields, p.photos)),

        update: (id, p) => isLocal()
            ? LO.vehicles.update(id, p)
            : PA('/vehicles/' + id + '/', vForm(p.fields, p.photos, true)),

        /* 409 se houver histórico ou atendimento */

        remove: id => isLocal()
            ? LO.vehicles.remove(id)
            : D('/vehicles/' + id + '/'),

        history: (id, q) => isLocal()
            ? LO.vehicles.history(id)
            : L('/vehicles/' + id + '/history/', q),

        /* manual: sem PATCH/DELETE (o histórico só cresce) */

        addHistory: (id, d) => isLocal()
            ? LO.vehicles.addHistory(id, d)
            : P('/vehicles/' + id + '/history/', d),

        /* próximas manutenções calculadas pelo servidor (BE-077); só HTTP —
           no driver local a tela calcula a partir do histórico */

        upcoming: id => L('/vehicles/' + id + '/upcoming-maintenance/'),

        /* chave "oficinas podem consultar o histórico" (P2: sem coluna) */

        setShared: (id, on) => isLocal()
            ? LO.vehicles.setShared(id, on)
            : PA('/vehicles/' + id + '/', { history_shared: on })
    };

    const chats = {
        async list() {
            if (isLocal()) return LO.chats.list();

            const r = await L('/chats/');

            r.results = r.results.map(normChat);

            return r;
        },

        /* idempotente: devolve a conversa existente ou cria a primeira */

        async open(workshopId) {
            return isLocal()
                ? LO.chats.open(workshopId)
                : normChat(await P('/chats/' + workshopId + '/open/'));
        },

        async get(id) {
            return isLocal()
                ? LO.chats.get(id)
                : normChat(await G('/chats/' + id + '/'));
        },

        async messages(id, after) {
            if (isLocal()) return LO.chats.messages(id);

            const r = await L('/chats/' + id + '/messages/', { after });

            r.results = r.results.map(normMsg);

            return r;
        },

        async send(id, content) {
            return isLocal()
                ? LO.chats.send(id, content)
                : normMsg(await P('/chats/' + id + '/messages/', { content }));
        },

        read: id => isLocal() ? LO.chats.read(id) : P('/chats/' + id + '/read/')
    };

    
    /* ---- auth ---- */

    const auth = {
        /* d = { role, email, password } → usuário */

        async login(d) {
            if (isLocal()) {
                const r = await A.login(d.email, d.password, d.role);

                if (!r.ok) {
                    throw mk({
                        status: r.error === A.NOC ? 0 : 401,
                        code: r.error === A.NOC ? 'NO_CRYPTO' : 'INVALID_CREDENTIALS',
                        detail: r.error
                    });
                }

                return r.user;
            }

            const r = await P('/auth/login/', d, { quiet: true });

            A.setSession(r.user);

            return r.user;
        },

        /*
         * d = { role, name?, name_fantasy?, name_responsible?, cnpj?,
         *       email, password, phone_number? }
         */

        async register(d) {
            if (isLocal()) {
                const r = await A.register({
                    role: d.role,
                    name: d.name || d.name_fantasy,
                    email: d.email,
                    password: d.password,
                    extra: {
                        phone_number: d.phone_number,
                        name_fantasy: d.name_fantasy,
                        name_responsible: d.name_responsible,
                        cnpj: d.cnpj
                    }
                });

                if (!r.ok) {
                    throw mk({
                        status: 400,
                        code: 'INVALID',
                        detail: r.error,
                        fields: r.fields || {}
                    });
                }

                return r.user;
            }

            const r = await P('/auth/register/', d, { quiet: true });

            A.setSession(r.user);

            return r.user;
        },

        async logout() {
            if (!isLocal() && C.API_BASE) {
                try {
                    await P('/auth/logout/', undefined, { quiet: true });
                } catch (e) {}
            }

            A.logout();
        },

        me: async () => {
            const r = await G('/auth/me/');

            return (r && r.user) || r;
        },

        requestReset: d => P('/auth/password-reset/', d, { quiet: true }),

        confirmReset: d => P('/auth/password-reset/confirm/', d, { quiet: true })
    };

    /* ---- domínios novos: SOMENTE HTTP (local → API_UNAVAILABLE) ---- */

    const W = '/workshop/';

    const api = {
        auth,
        vehicles,
        chats,

        account: {
            update: d => PA('/me/', d),
            password: d => P('/me/password/', d)
        },

        catalog: {
            categories: () => all('/service-categories/', undefined, Q),
            services: q => all('/services/', q, Q)
        },

        map: {
            points: q => L('/map/points/', q, Q),
            /* BE-094: estabelecimentos do OpenStreetMap na área visível (não paginado;
               `status` ok|partial|unavailable|too_large|disabled, sempre 200) */
            external: q => G('/map/external-points/', q, Q)
        },

        promotions: {
            async active() {
                const r = await L('/promotions/', { active: true }, Q);

                r.results = r.results.map(normPromo).filter(p => p.valid);

                return r;
            }
        },

        workshops: {
            async get(id) {
                return normWorkshop(await G('/workshops/' + id + '/', undefined, Q));
            },

            products: id => L('/workshops/' + id + '/products/', undefined, Q),

            async promotions(id) {
                const r = await L('/workshops/' + id + '/promotions/', undefined, Q);

                r.results = r.results.map(normPromo).filter(p => p.valid);

                return r;
            },

            reviews: (id, q) => L('/workshops/' + id + '/reviews/', q, Q)
        },

        favorites: {
            list: q => L('/favorites/', q),
            add: id => P('/favorites/', { id_workshop: id }),
            remove: id => D('/favorites/' + id + '/')
        },

        attendances: {
            create: d => P('/attendances/', d),
            list: q => L('/attendances/', q),
            get: id => G('/attendances/' + id + '/'),
            cancel: id => P('/attendances/' + id + '/cancel/')
        },

        budgets: {
            approve: id => P('/budgets/' + id + '/approve/'),
            reject: id => P('/budgets/' + id + '/reject/')
        },

        reviews: {
            create: d => P('/reviews/', d)
        },

        denunciations: {
            create: d => P('/denunciations/', d)
        },

        notifications: {
            list: q => L('/notifications/', q),
            read: id => P('/notifications/' + id + '/read/'),
            readAll: () => P('/notifications/read-all/'),

            async unreadCount() {
                const r = await G('/notifications/unread-count/');

                return +(
                    r && typeof r === 'object'
                        ? r.count ?? r.unread_count ?? 0
                        : r
                ) || 0;
            }
        },

        workshop: {
            me: () => G(W + 'me/'),
            updateMe: d => PA(W + 'me/', d),
            page: fd => PA(W + 'page/', fd),
            hours: () => all(W + 'operation-hours/'),
            setHours: list => PU(W + 'operation-hours/', list),
            searchPoints: q => L('/points-of-interest/', q),
            setPoint: d => P(W + 'point/', d),

            services: q => all(W + 'services/', q),
            addService: d => P(W + 'services/', d),
            updateService: (id, d) => PA(W + 'services/' + id + '/', d),

            products: q => all(W + 'products/', q),
            addProduct: fd => P(W + 'products/', fd),
            updateProduct: (id, fd) => PA(W + 'products/' + id + '/', fd),

            attendances: q => all(W + 'attendances/', q),
            attendance: async id => normWAtt(await G(W + 'attendances/' + id + '/')),
            updateAttendance: async (id, d) => normWAtt(await PA(W + 'attendances/' + id + '/', d)),
            transition: (id, status) =>
                P(W + 'attendances/' + id + '/transition/', { status }),

            createBudget: id => P(W + 'attendances/' + id + '/budget/', {}),
            updateBudget: (id, d) => PA(W + 'budgets/' + id + '/', d),
            addItem: (b, d) => P(W + 'budgets/' + b + '/items/', d),
            updateItem: (b, i, d) => PA(W + 'budgets/' + b + '/items/' + i + '/', d),
            removeItem: (b, i) => D(W + 'budgets/' + b + '/items/' + i + '/'),
            sendBudget: id => P(W + 'budgets/' + id + '/send/'),
            setExecution: (b, i, s) =>
                PA(W + 'budgets/' + b + '/items/' + i + '/execution/', { execution_status: s }),

            promotions: q => L(W + 'promotions/', q),
            addPromotion: fd => P(W + 'promotions/', fd),
            updatePromotion: (id, fd) => PA(W + 'promotions/' + id + '/', fd),
            advertisements: id => L(W + 'promotions/' + id + '/advertisements/'),
            addAdvertisement: (id, fd) =>
                P(W + 'promotions/' + id + '/advertisements/', fd),

            reviews: q => all(W + 'reviews/', q),
            respond: (id, text) =>
                P(W + 'reviews/' + id + '/response/', { workshop_response: text }),

            clients: q => all(W + 'clients/', q),
            clientVehicles: id =>
                L(W + 'clients/' + id + '/vehicles/', undefined, { soft: true }),
            vehicleHistory: id =>
                L(W + 'vehicles/' + id + '/history/', undefined, { soft: true })
        },

        admin: {
            denunciations: q => L('/admin/denunciations/', q),
            decide: (id, d) => PA('/admin/denunciations/' + id + '/', d),
            hideReview: id => P('/admin/reviews/' + id + '/hide/'),
            serviceRequests: q => L('/admin/service-requests/', q),
            approveService: (id, d) =>
                P('/admin/service-requests/' + id + '/approve/', d),
            rejectService: (id, motivation) =>
                P('/admin/service-requests/' + id + '/reject/', { motivation })
        },

        all,
        pageOf,
        paged,
        isUnavailable: e => !!e && e.code === 'API_UNAVAILABLE'
    };

    window.SAM = Object.assign(window.SAM || {}, { api });
})();
