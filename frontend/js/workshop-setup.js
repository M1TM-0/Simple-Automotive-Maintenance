(() => {
    /* T17 — Cadastro oficial da oficina (RN02), assistente em 4 passos */

    const { $, esc, fm, lbl, v: V, form, ui, W } = SAM;

    if (!SAM.auth.require('workshop')) return;

    ui.title('CADASTRO DA OFICINA');

    const view = $('#view'),
        user = SAM.auth.user(),
        KEY = 'w-setup-step:' + user.id,
        LABELS = ['Estabelecimento', 'Local', 'Horários', 'Serviços'];

    let me, svcs = [], hrs = [], step = 1, hoursW, catW, customs = [];

    const go = n => {
        step = n;
        SAM.store.set(KEY, Math.max(n, SAM.store.get(KEY, 1)));
        draw();
        $('#st-h').focus();
    };

    const nav = (prev, next) => `
        <div class="row" style="margin-top:6px">
            ${prev ? '<button type="button" class="btn" data-prev>Voltar</button>' : ''}
            ${next ? `<button type="button" class="btn btn--solid" data-next>${next}</button>` : ''}
        </div>
    `;

    /* ---------- passos ---------- */

    function s1() {
        $('#panel').innerHTML = `
            <form id="f1" novalidate>
                <fieldset class="fs">
                    <legend>Estabelecimento</legend>

                    <div class="fgrid">
                        ${form.fld({ id: 'name_fantasy', label: 'Nome fantasia', req: 1, value: me.name_fantasy, attrs: 'maxlength="255"' })}
                        ${form.fld({ id: 'name_responsible', label: 'Nome do responsável', req: 1, value: me.name_responsible, attrs: 'maxlength="255"' })}
                        ${form.fld({ id: 'phone_number', label: 'Telefone', type: 'tel', value: me.phone_number, attrs: 'maxlength="255"' })}

                        <div class="fld">
                            <label for="cnpj">CNPJ</label>
                            <input id="cnpj" value="${esc(fm.cnpj(me.cnpj))}" readonly>
                        </div>

                        <div class="fld">
                            <label for="email">E-mail</label>
                            <input id="email" value="${esc(me.email || '')}" readonly>
                        </div>
                    </div>
                </fieldset>

                <p class="ferr" id="ferr" role="alert"></p>
                <button class="btn btn--solid" id="b1">Salvar e avançar</button>
            </form>
        `;

        form.wire($('#f1'), async () => {
            const g = id => $('#' + id).value.trim();

            const bad = [
                form.err('name_fantasy', g('name_fantasy') ? '' : 'Informe o nome fantasia.'),
                form.err('name_responsible', g('name_responsible') ? '' : 'Informe o nome do responsável.')
            ];

            if (bad.some(Boolean)) {
                form.focusBad();
                return;
            }

            me = Object.assign(me, await SAM.api.workshop.updateMe({
                name_fantasy: g('name_fantasy'),
                name_responsible: g('name_responsible'),
                phone_number: g('phone_number')
            }));

            go(2);
        }, { btn: '#b1', busy: 'Salvando…' });
    }

    function s2() {
        $('#panel').innerHTML = `
            <section class="fs" aria-labelledby="l2">
                <h2 class="h2" id="l2" style="font-size:.95rem">Local no mapa</h2>

                <p class="muted" style="font-size:.82rem;margin-bottom:12px">
                    O endereço da oficina vem de um ponto do mapa. Pesquise o seu estabelecimento e confirme
                    que ele é seu; o vínculo nunca é feito automaticamente.
                </p>

                <div id="ptw"></div>
            </section>

            <p class="ferr" id="nopt" ${me.point ? 'hidden' : ''}>
                Sem um ponto, sua oficina funciona, mas não aparecerá no mapa.
            </p>

            ${nav(1, 'Avançar')}
        `;

        W.point($('#ptw'), {
            current: me.point,
            onLinked: p => {
                me.point = p;
                $('#nopt').hidden = true;
            }
        });
    }

    function s3() {
        $('#panel').innerHTML = `
            <section class="fs" aria-labelledby="l3">
                <h2 class="h2" id="l3" style="font-size:.95rem">Horários de funcionamento</h2>
                <p class="muted" style="font-size:.82rem;margin-bottom:12px">
                    Adicione um ou mais intervalos por dia. Dias sem intervalo aparecem como fechados.
                </p>
                <div id="hw"></div>
            </section>

            <p class="ferr" id="ferr" role="alert"></p>
            ${nav(1, 'Salvar e avançar')}
        `;

        hoursW = W.hours($('#hw'), hrs);
    }

    async function s4() {
        $('#panel').innerHTML = `
            <section class="fs" aria-labelledby="l4">
                <h2 class="h2" id="l4" style="font-size:.95rem">Serviços</h2>

                <p class="muted" style="font-size:.82rem;margin-bottom:12px">
                    Escolha serviços do catálogo e/ou crie um personalizado. É preciso ao menos 1 serviço para concluir.
                </p>

                <div id="have"></div>
                <div id="cw"></div>
            </section>

            <section class="fs" aria-labelledby="l4b">
                <h2 class="h2" id="l4b" style="font-size:.95rem">Serviço personalizado</h2>
                <div id="cu"></div>
                <button type="button" class="btn" id="cu-add" style="margin-top:10px">Adicionar à lista</button>
                <ul class="pt__l" id="cu-list" aria-live="polite"></ul>
            </section>

            <div id="s4err" class="ferr" role="alert"></div>
            ${nav(1, 'Concluir cadastro')}
        `;

        $('#have').innerHTML = svcs.length
            ? `<p style="font-size:.82rem"><b>Já adicionados:</b> ${svcs.map(s => esc(s.name)).join(', ')}</p>`
            : '';

        catW = await W.catalog($('#cw'), { taken: svcs.map(s => s.id_service).filter(Boolean) });

        let cats = [];

        try {
            cats = (await SAM.api.catalog.categories()).results;
        } catch (e) {}

        const cu = W.custom($('#cu'), cats, 'cu-');

        const list = () => {
            $('#cu-list').innerHTML = customs.map((c, i) => `
                <li>
                    <span><b>${esc(c.name_local)}</b> <small class="muted">${fm.money(c.price_base)} · ${fm.dur(c.duration_estimate)} · em análise</small></span>
                    <button type="button" class="btn btn--danger" data-rm="${i}">Remover</button>
                </li>
            `).join('');
        };

        list();

        $('#cu-add').onclick = () => {
            const c = cu.get();

            if (!c) return;

            customs.push(c);
            list();

            ['name_local', 'price_base', 'duration_estimate', 'description_local'].forEach(k => {
                $('#cu-' + k).value = '';
            });
        };

        $('#cu-list').onclick = e => {
            const b = e.target.closest('[data-rm]');

            if (b) {
                customs.splice(+b.dataset.rm, 1);
                list();
            }
        };
    }

    async function finish(btn) {
        const c = catW.get(),
            e = $('#s4err');

        e.textContent = '';

        if (!c.ok) return;

        const todo = c.items.concat(customs);

        if (!svcs.length && !todo.length) {
            e.textContent = 'Adicione ao menos 1 serviço para concluir o cadastro.';
            return;
        }

        form.busy(btn, true, 'Concluindo…');

        const fails = [];

        for (const it of todo) {
            try {
                await SAM.api.workshop.addService(it);
            } catch (x) {
                fails.push((it.name_local || 'Serviço do catálogo') + ': ' + x.detail);
                continue;
            }

            if (it.name_local) customs.splice(customs.indexOf(it), 1);
        }

        if (fails.length) {
            e.innerHTML = fails.map(f => esc(f)).join('<br>');
            svcs = (await SAM.api.workshop.services()).results;
            form.busy(btn, false);
            return;
        }

        try {
            const m = await SAM.api.workshop.me();

            if (m.setup_complete === false) {
                e.textContent = 'O servidor ainda considera o cadastro incompleto. Confira os passos anteriores.';
                form.busy(btn, false);
                return;
            }
        } catch (x) {}

        SAM.auth.setSession(Object.assign({}, SAM.auth.user(), { setup_complete: true }));
        location.href = 'w-attendances.html';
    }

    const STEP = { 1: s1, 2: s2, 3: s3, 4: s4 };

    function draw() {
        view.innerHTML = `
            <div class="wrap wrap--n">
                <h1 class="h1" id="st-h" tabindex="-1">Cadastro da oficina</h1>

                <ol class="stp stp--w" aria-label="Progresso do cadastro">
                    ${LABELS.map((l, i) => `
                        <li class="${i + 1 < step ? 'done' : i + 1 === step ? 'cur' : ''}" ${i + 1 === step ? 'aria-current="step"' : ''}>
                            ${i + 1 < step ? '<span class="sr">Concluído: </span>' : ''}${i + 1}. ${l}
                        </li>
                    `).join('')}
                </ol>

                <div id="panel"></div>
            </div>
        `;

        STEP[step]();

        const p = $('[data-prev]', view),
            n = $('[data-next]', view);

        if (p) p.onclick = () => go(step - 1);

        if (n) {
            n.onclick = async () => {
                if (step === 2) return go(3);

                if (step === 3) {
                    if (!hoursW.validate()) return;

                    form.busy(n, true, 'Salvando…');

                    try {
                        await SAM.api.workshop.setHours(hoursW.data());
                        hrs = hoursW.data();
                        go(4);
                    } catch (e) {
                        $('#ferr').textContent = e.detail;
                        form.busy(n, false);
                    }

                    return;
                }

                finish(n);
            };
        }
    }

    ui.load(view, () => Promise.all([
        SAM.api.workshop.me(),
        SAM.api.workshop.services(),
        SAM.api.workshop.hours()
    ]), ([m, s, h]) => {
        if (m.setup_complete === true) {
            SAM.auth.setSession(Object.assign({}, SAM.auth.user(), { setup_complete: true }));
            location.replace('w-attendances.html');
            return;
        }

        me = m;
        svcs = s.results;
        hrs = h.results;

        /* retoma de onde parou: dados do servidor + último passo salvo neste navegador */

        step = Math.max(hrs.length ? 4 : me.point ? 3 : 1, SAM.store.get(KEY, 1));

        draw();
    });
})();
