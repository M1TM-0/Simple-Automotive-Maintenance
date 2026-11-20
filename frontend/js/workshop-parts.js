(() => {
    /*
     * Widgets compartilhados da área da oficina (T17, T21, T22):
     * editor de horários, busca/vínculo do ponto no mapa e seleção de serviços.
     * A interface valida o formato; as regras de negócio são da API.
     */

    const { $, $$, esc, fm, v: V, form, lbl } = SAM,
        W = {},
        DAYS = [1, 2, 3, 4, 5, 6, 7];

    /* ================= HORÁRIOS (OPERATION_HOUR) ================= */

    /*
     * W.hours(host, lista) → { validate(), data() }
     * data(): [{ day_of_week, opening_time, closing_time }] (PUT substitui a lista).
     * Regras: fechamento > abertura; sem sobreposição no mesmo dia
     * (08–12 e 12–18 consecutivos são permitidos).
     */

    W.hours = (host, list) => {
        const st = {};

        DAYS.forEach(d => {
            st[d] = [];
        });

        (list || []).forEach(h => {
            if (st[h.day_of_week]) {
                st[h.day_of_week].push({
                    o: String(h.opening_time).slice(0, 5),
                    c: String(h.closing_time).slice(0, 5)
                });
            }
        });

        const row = (d, x, i) => `
            <div class="hrs__r">
                <input type="time" data-d="${d}" data-i="${i}" data-k="o" value="${esc(x.o)}"
                    aria-label="Abertura, ${lbl('day_of_week', d)}, intervalo ${i + 1}">

                <span aria-hidden="true">às</span>

                <input type="time" data-d="${d}" data-i="${i}" data-k="c" value="${esc(x.c)}"
                    aria-label="Fechamento, ${lbl('day_of_week', d)}, intervalo ${i + 1}">

                <button type="button" class="ib" data-rm="${d}:${i}"
                    aria-label="Remover intervalo ${i + 1} de ${lbl('day_of_week', d)}"
                    title="Remover intervalo">×</button>
            </div>
        `;

        const draw = () => {
            host.innerHTML = `
                <div class="hrs">
                    ${DAYS.map(d => `
                        <fieldset class="hrs__d">
                            <legend>${lbl('day_of_week', d)}</legend>

                            ${st[d].length ? st[d].map((x, i) => row(d, x, i)).join('') : '<p class="muted hrs__c">Fechado</p>'}

                            <span class="err" id="e-h${d}" role="alert"></span>

                            <button type="button" class="btn" data-add="${d}">+ Intervalo</button>
                        </fieldset>
                    `).join('')}
                </div>

                <button type="button" class="btn" data-copy>
                    Copiar segunda para os dias úteis
                </button>
            `;
        };

        draw();

        host.addEventListener('input', e => {
            const t = e.target.closest('[data-k]');

            if (t) st[t.dataset.d][+t.dataset.i][t.dataset.k] = t.value;
        });

        host.addEventListener('click', e => {
            const a = e.target.closest('[data-add]'),
                r = e.target.closest('[data-rm]'),
                c = e.target.closest('[data-copy]');

            if (a) {
                const d = +a.dataset.add;

                st[d].push({ o: '', c: '' });
                draw();
                $(`[data-d="${d}"][data-i="${st[d].length - 1}"][data-k=o]`, host).focus();
            } else if (r) {
                const [d, i] = r.dataset.rm.split(':').map(Number);

                st[d].splice(i, 1);
                draw();
                $(`[data-add="${d}"]`, host).focus();
            } else if (c) {
                if (!st[1].length) {
                    SAM.toast('Defina primeiro os horários de segunda.');
                    return;
                }

                [2, 3, 4, 5].forEach(d => {
                    st[d] = st[1].map(x => Object.assign({}, x));
                });

                draw();
                SAM.toast('Horários copiados para terça a sexta.');
            }
        });

        return {
            validate() {
                let first = null;

                DAYS.forEach(d => {
                    let m = '';
                    const rows = st[d];

                    for (const x of rows) {
                        if (!x.o || !x.c) {
                            m = 'Preencha abertura e fechamento.';
                            break;
                        }

                        if (x.c <= x.o) {
                            m = 'O fechamento deve ser depois da abertura.';
                            break;
                        }
                    }

                    if (!m) {
                        const s = rows.slice().sort((a, b) => a.o.localeCompare(b.o));

                        for (let i = 1; i < s.length; i++) {
                            if (s[i].o < s[i - 1].c) {
                                m = 'Os intervalos não podem se sobrepor.';
                                break;
                            }
                        }
                    }

                    $('#e-h' + d, host).textContent = m;

                    $$(`[data-d="${d}"]`, host).forEach(i => i.setAttribute('aria-invalid', !!m));

                    if (m && !first) first = $(`[data-d="${d}"]`, host);
                });

                if (first) first.focus();

                return !first;
            },

            data: () => DAYS.flatMap(d => st[d].map(x => ({
                day_of_week: d,
                opening_time: x.o,
                closing_time: x.c
            })))
        };
    };

    /* ================= PONTO NO MAPA (P4: nunca vínculo automático) ================= */

    /*
     * W.point(host, { current, onLinked(ponto) })
     * Pesquisa pontos existentes e exige a confirmação explícita
     * "Este é o meu estabelecimento". "Não encontrei" só funciona se a API aceitar.
     */

    W.point = (host, o) => {
        let sel = null;

        host.innerHTML = `
            <div class="pt">
                <div class="pt__cur" aria-live="polite">
                    ${o.current
                        ? `<p>Ponto vinculado: <b>${esc(o.current.name)}</b><br><span class="muted">${esc(o.current.address || 'Endereço não informado')}</span></p>`
                        : '<p class="muted">Nenhum ponto vinculado: sua oficina não aparecerá no mapa.</p>'}
                </div>

                <form class="pt__s" novalidate>
                    <label class="search">
                        <span class="sr">Buscar seu estabelecimento</span>
                        ${SAM.I.s}
                        <input data-q placeholder="Nome ou endereço do seu estabelecimento">
                    </label>

                    <button class="btn" data-go>Buscar</button>
                </form>

                <ul class="pt__l" data-res aria-live="polite"></ul>

                <div class="pt__c" data-conf hidden>
                    <p data-sel></p>

                    <div class="fld">
                        <label>
                            <input type="checkbox" data-ok>
                            Este é o meu estabelecimento
                        </label>

                        <span class="err" data-err role="alert"></span>
                    </div>

                    <button type="button" class="btn btn--solid" data-link>Vincular este ponto</button>
                </div>

                <button type="button" class="btn" data-nf aria-expanded="false">Não encontrei meu estabelecimento</button>

                <form class="pt__n fgrid" data-new hidden novalidate>
                    ${form.fld({ id: 'pn-name', name: 'name', label: 'Nome', req: 1, attrs: 'maxlength="255"' })}
                    ${form.fld({ id: 'pn-type', name: 'type', label: 'Tipo', req: 1, select: SAM.opts('type_establishment', 'oficina') })}
                    ${form.fld({ id: 'pn-address', name: 'address', label: 'Endereço', req: 1 })}
                    ${form.fld({ id: 'pn-latitude', name: 'latitude', label: 'Latitude', req: 1, attrs: 'inputmode="decimal" placeholder="-5.089200"' })}
                    ${form.fld({ id: 'pn-longitude', name: 'longitude', label: 'Longitude', req: 1, attrs: 'inputmode="decimal" placeholder="-42.801900"' })}

                    <p class="ferr" data-nerr role="alert" style="grid-column:1/-1"></p>

                    <button class="btn btn--solid" data-nsave>Cadastrar ponto</button>
                </form>
            </div>
        `;

        const res = $('[data-res]', host),
            conf = $('[data-conf]', host);

        const linked = p => {
            o.current = p;

            $('.pt__cur', host).innerHTML = `<p>Ponto vinculado: <b>${esc(p.name)}</b><br><span class="muted">${esc(p.address || 'Endereço não informado')}</span></p>`;

            conf.hidden = true;
            res.innerHTML = '';
            sel = null;

            SAM.toast('Ponto vinculado à sua oficina.');

            if (o.onLinked) o.onLinked(p);
        };

        $('.pt__s', host).addEventListener('submit', async e => {
            e.preventDefault();

            const q = $('[data-q]', host).value.trim(),
                b = $('[data-go]', host);

            if (q.length < 2) {
                res.innerHTML = '<li class="muted">Digite ao menos 2 letras.</li>';
                return;
            }

            b.disabled = true;
            res.innerHTML = '<li class="muted">Buscando…</li>';

            try {
                const r = await SAM.api.workshop.searchPoints({ q });

                res.innerHTML = r.results.length
                    ? r.results.map(p => `
                        <li>
                            <span>
                                <b>${esc(p.name)}</b>
                                <small class="muted">${esc(lbl('type_establishment', p.type))} · ${esc(p.address || 'sem endereço')}</small>
                            </span>

                            <button type="button" class="btn" data-pick="${esc(p.id)}">Selecionar</button>
                        </li>
                    `).join('')
                    : '<li class="muted">Nenhum ponto encontrado. Tente outro nome ou use “Não encontrei”.</li>';

                res._items = r.results;
            } catch (x) {
                res.innerHTML = `<li class="ferr" role="alert">${esc(SAM.api.isUnavailable(x) ? 'O servidor ainda não está disponível.' : x.detail)}</li>`;
            }

            b.disabled = false;
        });

        res.addEventListener('click', e => {
            const b = e.target.closest('[data-pick]');

            if (!b) return;

            sel = (res._items || []).find(p => String(p.id) === b.dataset.pick);

            $('[data-sel]', host).innerHTML = `Selecionado: <b>${esc(sel.name)}</b> — ${esc(sel.address || 'sem endereço')}`;
            $('[data-ok]', host).checked = false;
            $('[data-err]', host).textContent = '';
            conf.hidden = false;
            $('[data-ok]', host).focus();
        });

        $('[data-link]', host).onclick = async e => {
            const ok = $('[data-ok]', host);

            if (!ok.checked) {
                $('[data-err]', host).textContent = 'Confirme que este é o seu estabelecimento.';
                ok.focus();
                return;
            }

            const b = e.currentTarget;

            form.busy(b, true, 'Vinculando…');

            try {
                await SAM.api.workshop.setPoint({ id_point_of_interest: sel.id });
                linked(sel);
            } catch (x) {
                $('[data-err]', host).textContent = x.detail;
            }

            form.busy(b, false);
        };

        $('[data-nf]', host).onclick = e => {
            const n = $('[data-new]', host),
                open = n.hidden;

            n.hidden = !open;
            e.currentTarget.setAttribute('aria-expanded', open);

            if (open) $('#pn-name', host).focus();
        };

        form.wire($('[data-new]', host), async () => {
            const g = id => $('#pn-' + id, host).value.trim(),
                lat = +g('latitude').replace(',', '.'),
                lng = +g('longitude').replace(',', '.');

            const bad = [
                form.err('pn-name', g('name') ? '' : 'Informe o nome.'),
                form.err('pn-address', g('address') ? '' : 'Informe o endereço.'),
                form.err('pn-latitude', g('latitude') && lat >= -90 && lat <= 90 ? '' : 'Latitude entre -90 e 90.'),
                form.err('pn-longitude', g('longitude') && lng >= -180 && lng <= 180 ? '' : 'Longitude entre -180 e 180.')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(host);
                return;
            }

            try {
                const p = await SAM.api.workshop.setPoint({
                    name: g('name'),
                    type: g('type'),
                    latitude: Number(lat.toFixed(6)),
                    longitude: Number(lng.toFixed(6)),
                    address: g('address')
                });

                linked(Object.assign({ name: g('name'), address: g('address') }, p));
            } catch (x) {
                /* a API pode não aceitar a criação de pontos (P4) */

                $('[data-nerr]', host).textContent = [404, 405, 501].includes(x.status)
                    ? 'O servidor não aceita novos pontos. Você pode seguir sem ponto: sua oficina não aparecerá no mapa.'
                    : x.detail;
            }
        }, { btn: '[data-nsave]', busy: 'Cadastrando…', alias: { name: 'pn-name', address: 'pn-address', latitude: 'pn-latitude', longitude: 'pn-longitude', type: 'pn-type' } });
    };

    /* ================= SERVIÇOS ================= */

    /* "89,90" → 8990 centavos; '' ou inválido → NaN */

    const money = s => fm.cents(s);

    /*
     * W.catalog(host, { taken }) → { get() }
     * Catálogo global agrupado por categoria, com busca. Para cada serviço marcado:
     * price_base ≥ 0 e duration_estimate inteiro > 0 (minutos).
     * get() → { ok, items: [{ id_service, price_base, duration_estimate, disponibility }] }
     */

    W.catalog = async (host, o = {}) => {
        const taken = new Set((o.taken || []).map(String)),
            pick = new Map();

        let svcs = [],
            cats = [],
            q = '';

        host.setAttribute('aria-busy', 'true');
        host.innerHTML = '<p class="muted" role="status">Carregando catálogo…</p>';

        try {
            [cats, svcs] = await Promise.all([
                SAM.api.catalog.categories().then(r => r.results),
                SAM.api.catalog.services().then(r => r.results)
            ]);
        } catch (e) {
            host.removeAttribute('aria-busy');
            host.innerHTML = SAM.ui.failHtml(e);
            $('[data-retry]', host).onclick = () => W.catalog(host, o);
            return { get: () => ({ ok: false, items: [] }) };
        }

        host.removeAttribute('aria-busy');

        host.innerHTML = `
            <label class="search">
                <span class="sr">Buscar serviço no catálogo</span>
                ${SAM.I.s}
                <input data-q placeholder="Buscar serviço">
            </label>

            <div data-list aria-live="polite"></div>
        `;

        const list = $('[data-list]', host);

        const draw = () => {
            const f = svcs.filter(s => s.name.toLowerCase().includes(q));

            list.innerHTML = f.length
                ? cats.map(c => {
                    const own = f.filter(s => String(s.id_category ?? s.id_service_category) === String(c.id));

                    return own.length ? `
                        <fieldset class="cat">
                            <legend>${esc(c.name)}</legend>

                            ${own.map(s => {
                                const p = pick.get(String(s.id)),
                                    off = taken.has(String(s.id));

                                return `
                                    <div class="cat__r">
                                        <label>
                                            <input type="checkbox" data-s="${esc(s.id)}" ${p ? 'checked' : ''} ${off ? 'disabled' : ''}>
                                            ${esc(s.name)}
                                            ${off ? '<small class="muted">(já adicionado)</small>' : ''}
                                        </label>

                                        ${p ? `
                                            <div class="cat__f">
                                                <label>Preço base (R$)
                                                    <input data-p="${esc(s.id)}" inputmode="decimal" value="${esc(p.p)}" aria-describedby="ce-${esc(s.id)}">
                                                </label>

                                                <label>Duração (min)
                                                    <input data-d="${esc(s.id)}" inputmode="numeric" value="${esc(p.d)}" aria-describedby="ce-${esc(s.id)}">
                                                </label>

                                                <span class="err" id="ce-${esc(s.id)}" role="alert"></span>
                                            </div>
                                        ` : ''}
                                    </div>
                                `;
                            }).join('')}
                        </fieldset>
                    ` : '';
                }).join('')
                : '<p class="empty">Nenhum serviço encontrado.</p>';
        };

        draw();

        host.addEventListener('input', e => {
            if (e.target.matches('[data-q]')) {
                q = e.target.value.trim().toLowerCase();
                draw();
                return;
            }

            const p = e.target.closest('[data-p]'),
                d = e.target.closest('[data-d]');

            if (p) pick.get(p.dataset.p).p = p.value;

            if (d) pick.get(d.dataset.d).d = d.value;
        });

        host.addEventListener('change', e => {
            const c = e.target.closest('[data-s]');

            if (!c) return;

            if (c.checked) pick.set(c.dataset.s, { p: '', d: '' });
            else pick.delete(c.dataset.s);

            draw();

            const f = $(`[data-p="${c.dataset.s}"]`, host);

            if (f) f.focus();
        });

        return {
            get() {
                let ok = true,
                    first = null;

                const items = [...pick.entries()].map(([id, x]) => {
                    const c = money(x.p),
                        d = V.int(x.d);

                    const m = !(c >= 0) ? 'Informe o preço base (0 ou mais).' : !(d > 0) ? 'Informe a duração em minutos (maior que 0).' : '';

                    const e = $('#ce-' + id, host);

                    if (e) e.textContent = m;

                    if (m) {
                        ok = false;
                        first = first || $(`[data-p="${id}"]`, host);
                    }

                    return { id_service: isNaN(+id) ? id : +id, price_base: fm.outMoney(c), duration_estimate: d, disponibility: true };
                });

                if (first) first.focus();

                return { ok, items };
            }
        };
    };

    /*
     * W.custom(host, cats, pre) → { get() }: serviço personalizado.
     * name_local com espaços colapsados e não vazio; entra "em análise".
     */

    W.custom = (host, cats, pre = '') => {
        host.innerHTML = `
            <div class="fgrid">
                ${form.fld({ id: pre + 'name_local', name: 'name_local', label: 'Nome do serviço', req: 1, attrs: 'maxlength="255"' })}
                ${form.fld({ id: pre + 'id_suggested_category', name: 'id_suggested_category', label: 'Categoria sugerida', req: 1, select: '<option value="">Selecione</option>' + cats.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('') })}
                ${form.fld({ id: pre + 'price_base', name: 'price_base', label: 'Preço base (R$)', req: 1, attrs: 'inputmode="decimal"' })}
                ${form.fld({ id: pre + 'duration_estimate', name: 'duration_estimate', label: 'Duração (min)', req: 1, attrs: 'inputmode="numeric"' })}
            </div>

            ${form.fld({ id: pre + 'description_local', name: 'description_local', label: 'Descrição (opcional)', rows: 3 })}

            <p class="muted" style="font-size:.78rem">
                Este serviço ficará disponível agora e será analisado para entrar no catálogo global.
            </p>
        `;

        return {
            get() {
                const g = id => $('#' + pre + id, host).value,
                    name = V.clean(g('name_local')),
                    c = money(g('price_base')),
                    d = V.int(g('duration_estimate'));

                const bad = [
                    form.err(pre + 'name_local', name ? '' : 'Informe o nome do serviço.'),
                    form.err(pre + 'id_suggested_category', g('id_suggested_category') ? '' : 'Escolha a categoria.'),
                    form.err(pre + 'price_base', c >= 0 ? '' : 'Informe o preço base (0 ou mais).'),
                    form.err(pre + 'duration_estimate', d > 0 ? '' : 'Informe a duração em minutos (maior que 0).')
                ];

                if (bad.some(Boolean)) {
                    form.focusBad(host);
                    return null;
                }

                const o = {
                    name_local: name,
                    id_suggested_category: +g('id_suggested_category'),
                    price_base: fm.outMoney(c),
                    duration_estimate: d,
                    disponibility: true
                };

                if (V.clean(g('description_local'))) o.description_local = g('description_local').trim();

                return o;
            }
        };
    };

    window.SAM = Object.assign(window.SAM || {}, { W });
})();
