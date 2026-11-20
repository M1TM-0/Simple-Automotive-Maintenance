(() => {
    /*
     * Formatadores (SAM.fm), validadores (SAM.v) e helpers de formulário (SAM.form).
     * A interface valida formato/obrigatoriedade; a API é a autoridade.
     */

    const { $, $$, esc, brl } = SAM,
        p2 = n => String(n).padStart(2, '0'),
        DONLY = /^\d{4}-\d{2}-\d{2}$/;

    /* ================= FORMATADORES ================= */

    const fm = {
        /* 'aaaa-mm-dd' não sofre conversão de fuso; ISO com fuso vira hora local */

        date(v) {
            if (!v) return '—';

            if (DONLY.test(v)) return v.split('-').reverse().join('/');

            const d = new Date(v);

            return isNaN(d) ? '—' : `${p2(d.getDate())}/${p2(d.getMonth() + 1)}/${d.getFullYear()}`;
        },

        time(v) {
            const d = new Date(v);

            return isNaN(d) ? '' : `${p2(d.getHours())}:${p2(d.getMinutes())}`;
        },

        dt: v => v ? fm.date(v) + ' ' + fm.time(v) : '—',

        /* "agora", "há 5 min", "há 3 h", "ontem" ou dd/mm/aaaa */

        rel(v) {
            const d = new Date(v);

            if (isNaN(d)) return '';

            const m = Math.round((Date.now() - d) / 60000);

            return m < 1 ? 'agora'
                : m < 60 ? `há ${m} min`
                : m < 1440 ? `há ${Math.floor(m / 60)} h`
                : m < 2880 ? 'ontem'
                : fm.date(v);
        },

        money: v => v == null || v === '' || isNaN(+v) ? '—' : brl(+v),

        /* minutos → "45 min", "1h30", "2h" */

        dur(min) {
            min = +min;

            if (!min) return '—';

            const h = Math.floor(min / 60),
                m = min % 60;

            return h ? (m ? `${h}h${p2(m)}` : `${h}h`) : `${m} min`;
        },

        plate(p) {
            const s = String(p || '').toUpperCase().replace(/[^A-Z0-9]/g, '');

            return s.length > 3 ? s.slice(0, 3) + '-' + s.slice(3) : s;
        },

        /* 00.000.000/0000-00 */

                /*
         * Formata CNPJ numérico ou alfanumérico.
         *
         * Estrutura:
         * 12 caracteres alfanuméricos + 2 dígitos verificadores.
         *
         * Exemplo:
         * 12ABC34501DE35 -> 12.ABC.345/01DE-35
         */
        cnpj(v) {
            const d = String(v || '')
                .toUpperCase()
                .replace(/[^0-9A-Z]/g, '')
                .slice(0, 14);

            let result = d.slice(0, 2);

            if (d.length > 2) {
                result += '.' + d.slice(2, 5);
            }

            if (d.length > 5) {
                result += '.' + d.slice(5, 8);
            }

            if (d.length > 8) {
                result += '/' + d.slice(8, 12);
            }

            if (d.length > 12) {
                result += '-' + d.slice(12, 14);
            }

            return result;
        },

        /* datetime-local ↔ ISO com fuso */

        inputDt(iso) {
            const d = new Date(iso);

            return isNaN(d)
                ? ''
                : `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}`;
        },

        isoDt: l => l ? new Date(l).toISOString() : '',

        /* dinheiro e quantidade em inteiros (nunca float para somar) */

        /* '1.234,56' | '89.9' | 89.9 → centavos; NaN se inválido */

        cents(s) {
            let t = String(s ?? '').replace(/[R$\s]/g, '');

            if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.');

            const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(t);

            return m ? +m[1] * 100 + +((m[2] || '') + '00').slice(0, 2) : NaN;
        },

        /* centavos → '89,90' (campo) e 89.9 (envio, 2 casas) */

        inMoney: c => (c / 100).toFixed(2).replace('.', ','),

        outMoney: c => Number((c / 100).toFixed(2)),

        /* '1,5' → 1500 (milésimos, até 3 casas); NaN se inválido */

        milli(s) {
            const t = String(s ?? '').trim().replace(',', '.'),
                m = /^(\d+)(?:\.(\d{1,3}))?$/.exec(t);

            return m ? +m[1] * 1000 + +((m[2] || '') + '000').slice(0, 3) : NaN;
        },

        /* subtotal = round(qtd × valor, 2), em centavos */

        sub: (milli, cents) => Math.floor((milli * cents + 500) / 1000),

        outQty: m => Number((m / 1000).toFixed(3)),

        /* fotos preenchidas de um veículo (photo_1..3) */

        photos: v => [v.photo_1, v.photo_2, v.photo_3].filter(Boolean),

        /* "20% OFF" | "R$ 30,00 OFF" */

        discount: (t, x) => t === 'percentage'
            ? Number(x).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '% OFF'
            : brl(Number(x)) + ' OFF',

        /* "até dd/mm" */

        until: v => 'até ' + fm.date(v).slice(0, 5),

        /* "1,2 km" */

        dist: d => String(Math.round(d * 10) / 10).replace('.', ',') + ' km',

        /* "4,5" */

        stars: r => (Math.round(r * 10) / 10).toFixed(1).replace('.', ',')
    };

    /* ================= VALIDADORES (retornam mensagem ou '') ================= */

    const v = {
        email: s => !s
            ? 'Informe seu e-mail.'
            : !/^\S+@\S+\.\S+$/.test(s) ? 'E-mail inválido.' : '',

        /* ≥ 8, com letras e números */

        password: s => s.length < 8
            ? 'A senha precisa ter ao menos 8 caracteres.'
            : !/\d/.test(s) || !/[a-zA-Z]/.test(s)
                ? 'Use letras e números na senha.'
                : '',

        confirm: (a, b) => a !== b ? 'As senhas não conferem.' : '',


        /*
         * Valida CNPJ numérico ou alfanumérico.
         *
         * Os 12 primeiros caracteres podem conter
         * números e letras de A a Z.
         *
         * Os dois últimos caracteres são dígitos verificadores.
         *
         * O cálculo segue a mesma regra implementada
         * no backend em apps/core/validators.py.
         */
        cnpj(s) {
            const d = String(s || '')
                .toUpperCase()
                .replace(/[^0-9A-Z]/g, '');

            // Verifica a estrutura dos 14 caracteres.
            if (!/^[0-9A-Z]{12}[0-9]{2}$/.test(d)) {
                return 'CNPJ deve conter 12 caracteres alfanuméricos e 2 dígitos verificadores.';
            }

            // Rejeita CNPJs compostos pelo mesmo caractere.
            if (new Set(d).size === 1) {
                return 'CNPJ inválido.';
            }

            const weights = [
                5, 4, 3, 2, 9, 8,
                7, 6, 5, 4, 3, 2
            ];

            // Calcula um dígito verificador.
            const calculateDigit = (value, multipliers) => {
                const sum = [...value].reduce(
                    (total, char, index) => {
                        return total +
                            (char.charCodeAt(0) - 48) *
                            multipliers[index];
                    },
                    0
                );

                const remainder = sum % 11;

                return remainder < 2 ? 0 : 11 - remainder;
            };

            const base = d.slice(0, 12);

            // Primeiro dígito verificador.
            const firstDigit = calculateDigit(base, weights);

            // Segundo dígito verificador.
            const secondDigit = calculateDigit(
                base + firstDigit,
                [6, ...weights]
            );

            // Compara os dígitos calculados com os informados.
            if (
                Number(d[12]) !== firstDigit ||
                Number(d[13]) !== secondDigit
            ) {
                return 'CNPJ inválido.';
            }

            return '';
        },

        /* inteiro ≥ 0 com pontos/espaços de milhar → número ou NaN */

        int(s) {
            const x = String(s ?? '').replace(/[.\s]/g, '');

            return /^\d+$/.test(x) ? +x : NaN;
        },

        /* colapsa espaços repetidos (nome de serviço personalizado) */

        clean: s => String(s ?? '').replace(/\s+/g, ' ').trim()
    };

    /* ================= FORMULÁRIOS ================= */

    const form = {
        /* mensagem sob o campo (#e-<id>) + aria-invalid; devolve true se há erro */

        err(id, msg) {
            const e = $('#e-' + id),
                i = $('#' + id);

            if (e) e.textContent = msg || '';

            if (i) i.setAttribute('aria-invalid', !!msg);

            return !!msg;
        },

        /* foca o primeiro inválido; devolve true se existir */

        focusBad(root = document) {
            const b = $('[aria-invalid=true]', root);

            if (b) b.focus();

            return !!b;
        },

        clear(root = document) {
            $$('.err', root).forEach(e => {
                e.textContent = '';
            });

            $$('[aria-invalid=true]', root).forEach(i =>
                i.setAttribute('aria-invalid', 'false')
            );
        },

        /* erros 400 da API → campos pelo nome; o resto vai para #ferr */

        apply(root, e, alias = {}) {
            let extra = e && e.detail && !Object.keys(e.fields || {}).length ? e.detail : '';

            Object.entries((e && e.fields) || {}).forEach(([k, m]) => {
                const id = alias[k] || k;

                if ($('#e-' + id, root)) form.err(id, m);
                else extra = extra || m;
            });

            const f = $('.ferr', root);

            if (f) f.textContent = extra;

            form.focusBad(root);

            return extra;
        },

        /* botão ocupado: "Salvar" → "Salvando…" (texto restaurado depois) */

        busy(btn, on, txt) {
            if (!btn) return;

            if (on) {
                btn.dataset.t = btn.textContent;
                btn.textContent = txt || 'Enviando…';
            } else if (btn.dataset.t) {
                btn.textContent = btn.dataset.t;
            }

            btn.disabled = on;
        },

        /*
         * Liga o submit: novalidate, sem duplo envio, botão ocupado.
         * fn(ev) devolve Promise; erros 400 vão para os campos.
         */

        wire(f, fn, o = {}) {
            f.noValidate = true;

            f.addEventListener('submit', async ev => {
                ev.preventDefault();

                if (f.dataset.busy) return;

                const b = $(o.btn || '[type=submit]', f);

                f.dataset.busy = '1';
                form.busy(b, true, o.busy);

                const fe = $('.ferr', f);

                if (fe) fe.textContent = '';

                try {
                    await fn(ev);
                } catch (e) {
                    if (!form.apply(f, e, o.alias) && e && e.code === 'API_UNAVAILABLE') {
                        if (fe) fe.textContent = e.detail;
                    }
                } finally {
                    delete f.dataset.busy;
                    form.busy(b, false);
                }
            });
        },

        /* HTML de um campo .fld (input, textarea ou select) */

        fld(o) {
            const id = o.id,
                at = `id="${id}" name="${o.name || id}" ${o.attrs || ''}`,
                ctl = o.select !== undefined
                    ? `<select ${at}>${o.select}</select>`
                    : o.rows
                        ? `<textarea ${at} rows="${o.rows}">${esc(o.value ?? '')}</textarea>`
                        : `<input ${at} type="${o.type || 'text'}" value="${esc(o.value ?? '')}">`;

            return `
                <div class="fld ${o.cls || ''}">
                    <label for="${id}">
                        ${esc(o.label)}${o.req ? ' <abbr title="obrigatório">*</abbr>' : ''}
                    </label>
                    ${ctl}
                    ${o.hint ? `<small class="muted">${esc(o.hint)}</small>` : ''}
                    <span class="err" id="e-${id}" role="alert"></span>
                </div>
            `;
        },

        /* campo de senha com botão mostrar/ocultar (ligar com pwToggles) */

        pw: (i, l, a) => `
            <div class="fld">
                <label for="${i}">${l}</label>

                <div class="pw">
                    <input id="${i}" type="password" autocomplete="${a}">

                    <button type="button" class="tg" data-for="${i}" aria-pressed="false" aria-controls="${i}">
                        Mostrar
                    </button>
                </div>

                <span class="err" id="e-${i}" role="alert"></span>
            </div>
        `,

        /* mostrar/ocultar senha (botões .tg com data-for) */

        pwToggles(root = document) {
            $$('.tg', root).forEach(b => {
                b.onclick = () => {
                    const i = $('#' + b.dataset.for, root),
                        s = i.type === 'password';

                    i.type = s ? 'text' : 'password';
                    b.setAttribute('aria-pressed', s);
                    b.textContent = s ? 'Ocultar' : 'Mostrar';
                };
            });
        }
    };

    /* ================= IMAGENS ================= */

    /* comprime por canvas e devolve Blob JPEG (envio por multipart) */

    const compress = (file, max = 900, q = .8) => new Promise((ok, no) => {
        const r = new FileReader();

        r.onerror = no;

        r.onload = () => {
            const i = new Image();

            i.onerror = no;

            i.onload = () => {
                const k = Math.min(1, max / Math.max(i.width, i.height)),
                    c = document.createElement('canvas');

                c.width = Math.round(i.width * k);
                c.height = Math.round(i.height * k);
                c.getContext('2d').drawImage(i, 0, 0, c.width, c.height);
                c.toBlob(b => b ? ok(b) : no(new Error('toBlob')), 'image/jpeg', q);
            };

            i.src = r.result;
        };

        r.readAsDataURL(file);
    });

    /*
     * Seletor de foto única na identidade visual (botão em pílula + miniatura).
     * form.photo({ id, label, url, rm, max }) → HTML · form.photoInit(root)
     * form.photoGet(root, id) → { blob, removed }
     */

    const PH = new WeakMap();

    form.photo = o => `
        <div class="fld ph1" data-ph="${o.id}" data-max="${o.max || 900}">
            <span class="ph1__l">${esc(o.label)}</span>

            <div class="ph1__r">
                <div class="ph1__pv" aria-live="polite">
                    ${o.url ? `<img src="${SAM.ui.url(o.url)}" alt="${esc(o.label)} atual">` : '<span class="muted">Sem foto</span>'}
                </div>

                <div class="acts">
                    <input type="file" class="sr" id="${o.id}" accept="image/*">
                    <label class="btn" for="${o.id}">Adicionar foto</label>

                    ${o.rm ? `<button type="button" class="btn btn--danger" data-prm ${o.url ? '' : 'hidden'}>Remover</button>` : ''}
                </div>
            </div>

            <span class="err" id="e-${o.id}" role="alert"></span>
        </div>
    `;

    form.photoInit = (root, cb) => {
        const st = PH.get(root) || {};

        PH.set(root, st);

        $$('.ph1', root).forEach(w => {
            const id = w.dataset.ph,
                pv = $('.ph1__pv', w),
                inp = $('input', w),
                rm = $('[data-prm]', w);

            st[id] = { blob: null, removed: false };

            inp.onchange = async () => {
                const f = inp.files[0];

                $('#e-' + id).textContent = '';

                if (!f) return;

                try {
                    const b = await compress(f, +w.dataset.max);

                    st[id] = { blob: b, removed: false };
                    if (cb) cb(id, b);
                    pv.innerHTML = `<img alt="Nova foto selecionada" src="${URL.createObjectURL(b)}">`;
                    if (rm) rm.hidden = false;
                } catch (e) {
                    $('#e-' + id).textContent = 'Não foi possível ler esta imagem.';
                }

                inp.value = '';
            };

            if (rm) {
                rm.onclick = () => {
                    st[id] = { blob: null, removed: true };
                    if (cb) cb(id, null);
                    pv.innerHTML = '<span class="muted">Sem foto</span>';
                    rm.hidden = true;
                };
            }
        });
    };

    form.photoGet = (root, id) => (PH.get(root) || {})[id] || { blob: null, removed: false };

    /* ================= TOAST COM LINK, DENÚNCIA (M03), CARTÃO DE PROMOÇÃO ================= */

    const ui = SAM.ui;

    ui.toastLink = (msg, href, label) => {
        const t = document.createElement('div');

        t.className = 'toast';
        t.append(msg + ' ');

        const a = document.createElement('a');

        a.href = href;
        a.textContent = label;
        a.className = 'toast__a';
        t.append(a);

        $('#toasts').append(t);

        setTimeout(() => t.remove(), 9000);
    };

    /* só Cliente logado denuncia (a denúncia tem id_client) */

    ui.canReport = () => {
        const u = SAM.auth.user();

        return !!u && u.role === 'client';
    };

    /* M03 — target_type: 'review' | 'promotion' | 'advertisement' */

    ui.report = (target_type, target_id) => {
        const m = ui.modal({
            title: 'Denunciar conteúdo',
            body: `
                <form id="rf" novalidate>
                    <fieldset class="fs fs--m">
                        <legend>Motivo <abbr title="obrigatório">*</abbr></legend>

                        ${SAM.list('reason').map((o, i) => `
                            <label class="chk1">
                                <input type="radio" name="reason" value="${esc(o.v)}" ${i ? '' : 'required'}>
                                ${esc(o.l)}
                            </label>
                        `).join('')}

                        <span class="err" id="e-reason" role="alert"></span>
                    </fieldset>

                    ${form.fld({ id: 'rdesc', name: 'description', label: 'Descrição', rows: 3, attrs: 'maxlength="500"', hint: 'Obrigatória se o motivo for “Outro”. Até 500 caracteres.' })}

                    <p class="ferr" role="alert"></p>

                    <button class="btn btn--solid">Enviar denúncia</button>
                </form>
            `
        });

        form.wire($('#rf', m.body), async () => {
            const r = $('input[name=reason]:checked', m.body),
                d = $('#rdesc', m.body).value.trim();

            const bad = [
                form.err('reason', r ? '' : 'Escolha um motivo.'),
                form.err('rdesc', r && r.value === 'other' && !d ? 'Descreva o motivo.' : '')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(m.body);
                return;
            }

            const body = { target_type, target_id, reason: r.value };

            if (d) body.description = d;

            try {
                await SAM.api.denunciations.create(body);
            } catch (e) {
                if (e.status === 409) {
                    $('.ferr', m.body).textContent = 'Você já denunciou este conteúdo e ele está em análise.';
                    return;
                }

                throw e;
            }

            m.close();
            SAM.toast('Denúncia enviada para moderação.');
        }, { busy: 'Enviando…', alias: { description: 'rdesc' } });
    };

    /* cartão de promoção (home, mapa e perfil da oficina) */

    ui.promoCard = (p, o = {}) => `
        <article class="pm">
            <a class="pm__i" href="shop.html?id=${encodeURIComponent(p.workshop_id ?? o.workshop_id ?? '')}" tabindex="-1" aria-hidden="true">
                ${p.image ? `<img loading="lazy" src="${ui.url(p.image)}" alt="">` : SAM.car('#e9e6df')}
            </a>

            <div class="pm__b">
                <b>${esc(p.title)}</b>
                ${p.workshop_name ? `<span class="muted">${esc(p.workshop_name)}</span>` : ''}
                <span class="pm__d">${esc(fm.discount(p.type_discount, p.discount_value))}</span>
                <small class="muted">${esc(fm.until(p.date_end))}</small>
            </div>

            <div class="acts">
                <a class="btn" href="shop.html?id=${encodeURIComponent(p.workshop_id ?? o.workshop_id ?? '')}">Ver oficina</a>
                ${ui.canReport() ? `<button type="button" class="btn" data-rep="${esc(p.kind)}:${esc(p.id)}">Denunciar</button>` : ''}
            </div>
        </article>
    `;

    /* delegação: clique em [data-rep="tipo:id"] abre M03 */

    ui.bindReport = root => root.addEventListener('click', e => {
        const b = e.target.closest('[data-rep]');

        if (b) {
            const [t, ...id] = b.dataset.rep.split(':');

            ui.report(t, id.join(':'));
        }
    });

    window.SAM = Object.assign(window.SAM || {}, { fm, v, form, compress });

})();
