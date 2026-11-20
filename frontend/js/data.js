(() => {
    /*
     * DADOS LOCAIS (DRIVER 'local'): só o que o usuário cadastra, no localStorage.
     * Nenhum dado fictício. Com DRIVER 'http' nada daqui é usado: api.js
     * conversa com o servidor.
     *
     * SAM.local.vehicles e SAM.local.chats têm a MESMA interface de
     * SAM.api.vehicles/chats (formas já normalizadas), por isso as telas não
     * sabem qual driver está ativo.
     */

    const store = {
        get(k, d) {
            try {
                const v = localStorage.getItem('sam:v1:' + k);
                return v ? JSON.parse(v) : d;
            } catch (e) {
                return d;
            }
        },

        set(k, v) {
            try {
                localStorage.setItem('sam:v1:' + k, JSON.stringify(v));
                return true;
            } catch (e) {
                return false;
            }
        }
    };

    const u = () => 'u:' + ((SAM.auth.user() || {}).id || 'anon') + ':';

    const TODAY = new Date().toISOString().slice(0, 10),
        IMG = {
            hero: 'assets/img/hero-racing.png'
        };

    const V = store.get(u() + 'vehicles', []),
        convs = store.get(u() + 'convs', []),
        shops = store.get('workshops', []);

    const vn = v =>
        `${v.brand} ${v.model}${(v.year_model || v.yearModel) ? ' ' + String(v.year_model || v.yearModel).slice(2) : ''}`;

    const save = () =>
        store.set(u() + 'convs', convs) &&
        store.set(u() + 'vehicles', V);

    const newConv = id => {
        const s = shops.find(x => x.id == id),
            c = {
                id: s.id,
                n: s.n,
                time: '',
                unread: 0,
                status: null,
                msgs: []
            };

        convs.push(c);

        return c;
    };

    /* ---- erros no mesmo formato da API ---- */

    const nf = (status, detail, fields) =>
        Object.assign(new Error(detail), {
            status,
            code: 'LOCAL_' + status,
            detail,
            fields: fields || {}
        });

    const page = r => ({
        count: r.length,
        next: null,
        previous: null,
        results: r
    });

    const QUOTA = 'Sem espaço no navegador. Remova fotos e tente de novo.';

    /* ---- veículos ---- */

    const nz = s => String(s || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .trim();

    const code = (name, label) => {
        const n = nz(label);

        if (n === 'cvt') return 'variavel';

        const hit = SAM.list(name)
            .find(o => o.v === n || nz(o.l) === n);

        return hit ? hit.v : 'outro';
    };

    /* formato antigo do protótipo → formato da API (idempotente) */

    const mig = v => {
        if (v.year_fabrication !== undefined) return v;

        const ph = v.photos || [];

        return {
            id: v.id,
            brand: v.brand,
            model: v.model,
            year_fabrication: v.yearMade,
            year_model: v.yearModel,
            plate: String(v.plate || '').replace(/[^A-Za-z0-9]/g, '').toUpperCase(),
            fuel: code('fuel', v.fuel),
            exchange: code('exchange', v.gearbox),
            version: v.version || '',
            motorization: v.engine || '',
            color: v.color || '',
            information: v.notes || '',
            mileage_km: v.km,
            photo_1: ph[0] || null,
            photo_2: ph[1] || null,
            photo_3: ph[2] || null,
            history: (v.history || []).map(h => ({
                id: h.id,
                record_type: 'service',
                description: h.type,
                date_maintenance: h.date,
                mileage_km: h.km,
                observations: h.notes || '',
                interval_km: h.interval || null
            })),
            history_shared: !!v.auth
        };
    };

    const LV = () => {
        V.forEach((v, i) => {
            if (v.year_fabrication === undefined) V[i] = mig(v);
        });

        return V;
    };

    const toData = b => new Promise((ok, no) => {
        const r = new FileReader();

        r.onload = () => ok(r.result);
        r.onerror = no;
        r.readAsDataURL(b);
    });

    const lvGet = id => {
        const v = LV().find(x => String(x.id) === String(id));

        if (!v) throw nf(404, 'Veículo não encontrado.');

        return v;
    };

    /* `photos` = 3 posições: null | {url} | {blob} */

    async function lvSave(old, fields, photos) {
        const o = Object.assign({}, fields);

        if (o.plate) {
            o.plate = String(o.plate).replace(/[^A-Za-z0-9]/g, '').toUpperCase();
        }

        if (photos) {
            for (let i = 0; i < 3; i++) {
                const s = photos[i];

                o['photo_' + (i + 1)] = s
                    ? s.blob ? await toData(s.blob) : s.url
                    : null;
            }
        }

        const dup = LV().find(x =>
            x.plate === (o.plate || (old || {}).plate) &&
            (!old || x.id !== old.id)
        );

        if (dup) {
            throw nf(400, 'Já existe um veículo com esta placa.', {
                plate: 'Já existe um veículo com esta placa'
            });
        }

        if (old) {
            const bak = JSON.parse(JSON.stringify(old));

            Object.assign(old, o);

            if (!save()) {
                Object.assign(old, bak);
                throw nf(507, QUOTA);
            }

            return old;
        }

        const v = Object.assign(
            {
                id: 'v' + Date.now().toString(36),
                history: [],
                history_shared: false
            },
            o
        );

        V.push(v);

        if (!save()) {
            V.pop();
            throw nf(507, QUOTA);
        }

        return v;
    }

    const vehicles = {
        list: async () => page(LV().slice()),

        get: async id => lvGet(id),

        create: async p => lvSave(null, p.fields, p.photos),

        update: async (id, p) => lvSave(lvGet(id), p.fields, p.photos),

        /* sem histórico: pode excluir (RN05: histórico nunca é apagado) */

        async remove(id) {
            const v = lvGet(id);

            if ((v.history || []).length) {
                throw nf(409, 'Veículos com atendimentos ou histórico não podem ser excluídos.');
            }

            V.splice(V.indexOf(v), 1);
            save();

            return null;
        },

        history: async id => page(
            (lvGet(id).history || [])
                .slice()
                .sort((a, b) => b.date_maintenance.localeCompare(a.date_maintenance))
        ),

        async addHistory(id, d) {
            const v = lvGet(id),
                h = {
                    id: 'h' + Date.now().toString(36),
                    record_type: 'service',
                    description: d.service_name,
                    date_maintenance: d.date_maintenance,
                    mileage_km: d.mileage_km,
                    observations: d.observations || '',
                    interval_km: d.interval_km || null
                },
                old = v.mileage_km;

            v.history.push(h);

            if (h.mileage_km > (v.mileage_km || 0)) v.mileage_km = h.mileage_km;

            if (!save()) {
                v.history.pop();
                v.mileage_km = old;
                throw nf(507, 'Não foi possível salvar neste navegador.');
            }

            return h;
        },

        async setShared(id, on) {
            lvGet(id).history_shared = on;
            save();

            return null;
        }
    };

    /* ---- conversas do cliente (formato antigo { id, n, time, unread, msgs }) ---- */

    const legacyText = m =>
        m.t ?? (
            m.k === 'car'
                ? 'Veículo compartilhado (versão antiga do protótipo)'
                : m.k === 'doc'
                    ? 'Histórico compartilhado (versão antiga do protótipo)'
                    : m.k === 'quote'
                        ? 'Orçamento (versão antiga do protótipo)'
                        : ''
        );

    const lcSum = c => {
        const m = c.msgs[c.msgs.length - 1];

        return {
            id: c.id,
            name: c.n,
            photo: null,
            workshop_id: c.id,
            last_message: m ? legacyText(m) : '',
            last_at: m && m.at ? m.at : null,
            last_label: c.time || '',
            unread: c.unread || 0,
            open_attendance: null
        };
    };

    const lcGet = id => {
        const c = convs.find(x => String(x.id) === String(id));

        if (!c) throw nf(404, 'Conversa não encontrada.');

        return c;
    };

    const chats = {
        list: async () => page(convs.map(lcSum)),

        /* idempotente: devolve a conversa existente ou cria a primeira */

        async open(workshopId) {
            const c = convs.find(x => String(x.id) === String(workshopId));

            if (c) return lcSum(c);

            if (!shops.some(s => String(s.id) === String(workshopId) && s.reg)) {
                throw nf(404, 'Oficina não encontrada.');
            }

            const n = newConv(workshopId);

            save();

            return lcSum(n);
        },

        get: async id => lcSum(lcGet(id)),

        messages: async id => page(
            lcGet(id).msgs.map((m, i) => ({
                id: i,
                content: legacyText(m),
                at: m.at || null,
                label: m.h || '',
                status: null,
                mine: m.w === 'me'
            }))
        ),

        async send(id, content) {
            const c = lcGet(id),
                h = SAM.now();

            c.msgs.push({
                w: 'me',
                t: content,
                h,
                at: new Date().toISOString()
            });

            c.time = h;

            if (!save()) {
                c.msgs.pop();
                throw nf(507, 'Não foi possível salvar neste navegador.');
            }

            return {
                id: c.msgs.length - 1,
                content,
                at: c.msgs[c.msgs.length - 1].at,
                label: h,
                status: null,
                mine: true
            };
        },

        async read(id) {
            lcGet(id).unread = 0;
            save();

            return null;
        }
    };

    window.SAM = Object.assign(window.SAM || {}, {
        store,
        save,
        TODAY,
        IMG,
        shops,
        V,
        convs,
        vn,
        newConv,
        local: {
            err: nf,
            vehicles,
            chats
        }
    });
})();
