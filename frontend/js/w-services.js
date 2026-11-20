(() => {
    /* T22 — Serviços da oficina (catálogo global e personalizados). Sem "Excluir". */

    const { $, esc, fm, lbl, v: V, form, ui, W } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('SERVIÇOS DA OFICINA');

    const view = $('#view');

    let items = [], cats = [], cf = '', sf = '';

    const catName = s => s.category_name ||
        (cats.find(c => String(c.id) === String(s.id_service_category ?? s.id_category ?? s.id_suggested_category)) || {}).name || '—';

    const origin = s => s.status_solicitation ? 'Personalizado' : 'Catálogo global';

    const rows = () => items.filter(s =>
        (!cf || String(s.id_service_category ?? s.id_category ?? s.id_suggested_category) === cf) &&
        (!sf || (sf === 'catalog' ? !s.status_solicitation : s.status_solicitation === sf))
    );

    function table() {
        const r = rows();

        $('#tb').innerHTML = r.length
            ? ui.table({
                caption: 'Serviços da oficina',
                rowHead: true,
                rows: r,
                cols: [
                    { h: 'Serviço', c: s => `${esc(s.name)}${s.description_local ? `<br><small class="muted">${esc(s.description_local)}</small>` : ''}` },
                    { h: 'Categoria', c: s => esc(catName(s)) },
                    { h: 'Preço base', cls: 'num', c: s => fm.money(s.price_base) },
                    { h: 'Duração', cls: 'num', c: s => esc(fm.dur(s.duration_estimate)) },
                    { h: 'Disponível', c: s => `
                        <div class="sw">
                            <button type="button" role="switch" data-sw="${esc(s.id)}" aria-checked="${!!s.disponibility}"
                                aria-label="Disponível: ${esc(s.name)}"></button>
                        </div>` },
                    { h: 'Origem', c: s => origin(s) },
                    { h: 'Situação', c: s => s.status_solicitation
                        ? ui.badge('status_solicitation', s.status_solicitation) +
                            (s.motivation_rejection ? `<br><small>Motivo: ${esc(s.motivation_rejection)}</small>` : '')
                        : '—' },
                    { h: 'Ações', c: s => `<button type="button" class="btn" data-ed="${esc(s.id)}">Editar</button>` }
                ]
            })
            : '<p class="empty">Nenhum serviço corresponde aos filtros.</p>';
    }

    async function reload() {
        items = (await SAM.api.workshop.services()).results;
        table();
    }

    /* ---------- modais ---------- */

    function addCatalog(from) {
        const m = ui.modal({
            title: 'Adicionar do catálogo',
            wide: true,
            body: '<div id="mc"></div><p class="ferr" id="mce" role="alert"></p><button class="btn btn--solid" id="mcb">Adicionar selecionados</button>'
        });

        let cw;

        W.catalog($('#mc', m.body), { taken: items.map(s => s.id_service).filter(Boolean) }).then(c => {
            cw = c;
        });

        $('#mcb', m.body).onclick = async e => {
            const c = cw.get(),
                err = $('#mce', m.body);

            err.textContent = '';

            if (!c.ok) return;

            if (!c.items.length) {
                err.textContent = 'Marque ao menos um serviço.';
                return;
            }

            const b = e.currentTarget,
                fails = [];

            form.busy(b, true, 'Adicionando…');

            for (const it of c.items) {
                try {
                    await SAM.api.workshop.addService(it);
                } catch (x) {
                    fails.push(x.detail);
                }
            }

            await reload();

            if (fails.length) {
                err.innerHTML = fails.map(esc).join('<br>');
                form.busy(b, false);
                return;
            }

            m.close();
            SAM.toast('Serviços adicionados.');
        };
    }

    function addCustom() {
        const m = ui.modal({
            title: 'Serviço personalizado',
            body: '<form id="cf2" novalidate><div id="cu"></div><p class="ferr" role="alert"></p><button class="btn btn--solid">Adicionar serviço</button></form>'
        });

        const cu = W.custom($('#cu', m.body), cats, 'cu-');

        form.wire($('#cf2', m.body), async () => {
            const c = cu.get();

            if (!c) return;

            await SAM.api.workshop.addService(c);
            await reload();
            m.close();
            SAM.toast('Serviço enviado para análise.');
        }, {
            busy: 'Adicionando…',
            alias: { name_local: 'cu-name_local', id_suggested_category: 'cu-id_suggested_category', price_base: 'cu-price_base', duration_estimate: 'cu-duration_estimate', description_local: 'cu-description_local' }
        });
    }

    function edit(s) {
        const custom = !!s.status_solicitation,
            m = ui.modal({
                title: 'Editar serviço',
                body: `
                    <form id="ef" novalidate>
                        <p><b>${esc(s.name)}</b></p>

                        <div class="fgrid">
                            ${form.fld({ id: 'price_base', label: 'Preço base (R$)', req: 1, value: fm.inMoney(fm.cents(s.price_base)), attrs: 'inputmode="decimal"' })}
                            ${form.fld({ id: 'duration_estimate', label: 'Duração (min)', req: 1, value: s.duration_estimate, attrs: 'inputmode="numeric"' })}
                        </div>

                        ${custom ? form.fld({ id: 'description_local', label: 'Descrição', rows: 3, value: s.description_local }) : ''}

                        <label class="chk1"><input type="checkbox" id="disponibility" ${s.disponibility ? 'checked' : ''}> Disponível</label>

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid">Salvar</button>
                    </form>
                `
            });

        form.wire($('#ef', m.body), async () => {
            const c = fm.cents($('#price_base').value),
                d = V.int($('#duration_estimate').value);

            const bad = [
                form.err('price_base', c >= 0 ? '' : 'Informe o preço base (0 ou mais).'),
                form.err('duration_estimate', d > 0 ? '' : 'Informe a duração em minutos (maior que 0).')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(m.body);
                return;
            }

            const body = { price_base: fm.outMoney(c), duration_estimate: d, disponibility: $('#disponibility').checked };

            if (custom) body.description_local = $('#description_local').value.trim();

            await SAM.api.workshop.updateService(s.id, body);
            await reload();
            m.close();
            SAM.toast('Serviço atualizado.');
        }, { busy: 'Salvando…' });
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap">
                ${ui.subnav('services')}

                <div class="hbar">
                    <h1 class="h1">Serviços da oficina</h1>

                    <div class="row">
                        <button type="button" class="btn btn--solid" id="ac">+ Adicionar do catálogo</button>
                        <button type="button" class="btn" id="ap">+ Serviço personalizado</button>
                    </div>
                </div>

                <p class="muted" style="font-size:.82rem;margin-bottom:14px">
                    Serviços usados em orçamentos não podem ser excluídos. Para parar de oferecer um serviço,
                    desative a opção “Disponível”.
                </p>

                <div class="row filt">
                    <div class="fld">
                        <label for="fc">Categoria</label>

                        <select id="fc">
                            <option value="">Todas</option>
                            ${cats.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}
                        </select>
                    </div>

                    <div class="fld">
                        <label for="fs">Situação</label>

                        <select id="fs">
                            <option value="">Todas</option>
                            <option value="catalog">Do catálogo global</option>
                            ${['pending', 'approved', 'rejected'].map(k => `<option value="${k}">${esc(lbl('status_solicitation', k))}</option>`).join('')}
                        </select>
                    </div>
                </div>

                ${items.length ? '' : '<p class="empty">Você ainda não tem serviços. Adicione do catálogo ou crie um personalizado.</p>'}

                <div id="tb" aria-live="polite"></div>
            </div>
        `;

        table();

        $('#fc').onchange = e => { cf = e.target.value; table(); };
        $('#fs').onchange = e => { sf = e.target.value; table(); };
        $('#ac').onclick = () => addCatalog();
        $('#ap').onclick = () => addCustom();

        $('#tb').addEventListener('click', async e => {
            const ed = e.target.closest('[data-ed]'),
                sw = e.target.closest('[data-sw]');

            if (ed) return edit(items.find(s => String(s.id) === ed.dataset.ed));

            if (sw) {
                const s = items.find(x => String(x.id) === sw.dataset.sw),
                    on = !s.disponibility;

                sw.disabled = true;

                try {
                    await SAM.api.workshop.updateService(s.id, { disponibility: on });
                    s.disponibility = on;
                    sw.setAttribute('aria-checked', on);
                } catch (x) {
                    SAM.toast(x.detail || 'Não foi possível alterar.');
                }

                sw.disabled = false;
            }
        });
    }

    ui.load(view, () => Promise.all([SAM.api.workshop.services(), SAM.api.catalog.categories()]), ([s, c]) => {
        items = s.results;
        cats = c.results;
        draw();
    });
})();
