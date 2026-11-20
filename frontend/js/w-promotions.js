(() => {
    /* T24 — Promoções e divulgações (P6: sem tela de pagamento; nunca "no ar" antes de is_running_now) */

    const { $, esc, fm, lbl, v: V, form, ui } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('PROMOÇÕES');

    const view = $('#view');

    let promos = [], svcs = [], prods = [], ads = [], tab = 'p', T;

    const target = p => p.target_name
        ? (p.id_workshop_service ? 'Serviço: ' : 'Produto: ') + p.target_name
        : 'Geral';

    const period = p => fm.date(p.date_start) + ' a ' + fm.date(p.date_end);

    /* ---------- formulário de promoção ---------- */

    function edit(p, from) {
        const d = p || from || {},
            ro = !!p && p.effective_status === 'expired',
            tg = d.id_workshop_service ? 's' : d.id_product ? 'p' : 'g',
            m = ui.modal({
                title: ro ? 'Promoção encerrada' : p ? 'Editar promoção' : from ? 'Nova promoção (a partir de outra)' : 'Nova promoção',
                wide: true,
                body: `
                    <form id="pf" novalidate>
                        <fieldset ${ro ? 'disabled' : ''} class="fs fs--m">
                            ${form.fld({ id: 'title', label: 'Título', req: 1, value: d.title, attrs: 'maxlength="255"' })}
                            ${form.fld({ id: 'description', label: 'Descrição', rows: 3, value: d.description })}

                            <fieldset class="fs fs--m">
                                <legend>Alvo da promoção <abbr title="obrigatório">*</abbr></legend>

                                <div class="row">
                                    <label class="chk1"><input type="radio" name="tg" value="g" ${tg === 'g' ? 'checked' : ''}> Geral</label>
                                    <label class="chk1"><input type="radio" name="tg" value="s" ${tg === 's' ? 'checked' : ''}> Serviço</label>
                                    <label class="chk1"><input type="radio" name="tg" value="p" ${tg === 'p' ? 'checked' : ''}> Produto</label>
                                </div>

                                ${form.fld({ id: 'tsel', label: 'Item', select: '' })}
                            </fieldset>

                            <fieldset class="fs fs--m">
                                <legend>Desconto <abbr title="obrigatório">*</abbr></legend>

                                <div class="row">
                                    <label class="chk1"><input type="radio" name="td" value="percentage" ${d.type_discount !== 'fixed' ? 'checked' : ''}> Percentual (%)</label>
                                    <label class="chk1"><input type="radio" name="td" value="fixed" ${d.type_discount === 'fixed' ? 'checked' : ''}> Valor fixo (R$)</label>
                                </div>

                                ${form.fld({ id: 'discount_value', label: 'Valor do desconto', req: 1, value: d.discount_value ? String(d.discount_value).replace('.', ',').replace(/,00$/, '') : '', attrs: 'inputmode="decimal"' })}
                            </fieldset>

                            <div class="fgrid">
                                ${form.fld({ id: 'date_start', label: 'Início', req: 1, type: 'datetime-local', value: fm.inputDt(p ? d.date_start : new Date().toISOString()) })}
                                ${form.fld({ id: 'date_end', label: 'Fim', req: 1, type: 'datetime-local', value: p ? fm.inputDt(d.date_end) : '' })}
                            </div>

                            ${form.photo({ id: 'image', label: 'Imagem', url: d.image_url, rm: 1, max: 1400 })}

                            <label class="chk1"><input type="checkbox" id="active" ${d.status_promotion !== 'inactive' ? 'checked' : ''}> Promoção ativa</label>
                        </fieldset>

                        <p class="muted" style="font-size:.78rem">Após a data final a promoção deixa de ser exibida automaticamente.</p>
                        <p class="ferr" role="alert"></p>

                        ${ro ? `<button type="button" class="btn btn--solid" id="nw">Criar nova a partir desta</button>` : '<button class="btn btn--solid">Salvar promoção</button>'}
                    </form>
                `
            });

        form.photoInit(m.body);

        const fill = () => {
            const k = $('input[name=tg]:checked', m.body).value,
                s = $('#tsel', m.body);

            s.disabled = k === 'g' || ro;
            s.innerHTML = k === 'g' ? '<option value="">—</option>'
                : '<option value="">Selecione</option>' + (k === 's' ? svcs : prods)
                    .map(x => `<option value="${esc(x.id)}" ${String(x.id) === String(k === 's' ? d.id_workshop_service : d.id_product) ? 'selected' : ''}>${esc(x.name)}</option>`).join('');
        };

        m.body.querySelectorAll('input[name=tg]').forEach(r => r.addEventListener('change', fill));
        fill();

        if (ro) {
            $('#nw', m.body).onclick = () => {
                m.close();
                edit(null, d);
            };

            return;
        }

        form.wire($('#pf', m.body), async () => {
            const g = id => $('#' + id, m.body).value.trim(),
                k = $('input[name=tg]:checked', m.body).value,
                t = $('input[name=td]:checked', m.body).value,
                dv = fm.cents(g('discount_value')),
                ds = g('date_start'),
                de = g('date_end');

            const bad = [
                form.err('title', g('title') ? '' : 'Informe o título.'),
                form.err('tsel', k !== 'g' && !g('tsel') ? 'Escolha o item da promoção.' : ''),
                form.err('discount_value', !(dv > 0) ? 'Informe um valor maior que zero.' : t === 'percentage' && dv > 10000 ? 'O percentual não pode passar de 100.' : ''),
                form.err('date_start', ds ? '' : 'Informe o início.'),
                form.err('date_end', !de ? 'Informe o fim.' : new Date(de) <= new Date(ds) ? 'O fim deve ser depois do início.' : new Date(de) <= new Date() ? 'O fim deve estar no futuro.' : '')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(m.body);
                return;
            }

            const fd = new FormData(),
                im = form.photoGet(m.body, 'image');

            fd.append('title', g('title'));
            fd.append('description', g('description'));
            fd.append('type_discount', t);
            fd.append('discount_value', fm.outMoney(dv));
            fd.append('date_start', fm.isoDt(ds));
            fd.append('date_end', fm.isoDt(de));
            fd.append('status_promotion', $('#active', m.body).checked ? 'active' : 'inactive');

            /* alvo exclusivo: o outro lado vai vazio */

            fd.append('id_workshop_service', k === 's' ? g('tsel') : '');
            fd.append('id_product', k === 'p' ? g('tsel') : '');

            if (im.blob) fd.append('image', im.blob, 'promo.jpg');
            else if (im.removed) fd.append('image', '');

            if (p) await SAM.api.workshop.updatePromotion(p.id, fd);
            else await SAM.api.workshop.addPromotion(fd);

            await reload();
            m.close();
            SAM.toast('Promoção salva.');
        }, { busy: 'Salvando…', alias: { tsel: 'tsel', id_workshop_service: 'tsel', id_product: 'tsel' } });
    }

    /* ---------- divulgação ---------- */

    function advertise(p) {
        const m = ui.modal({
            title: 'Divulgar no SAM',
            body: `
                <form id="af" novalidate>
                    <p class="muted" style="font-size:.82rem">Promoção: <b>${esc(p.title)}</b></p>

                    ${form.photo({ id: 'image', label: 'Imagem da divulgação *', max: 1600 })}

                    <div class="fgrid">
                        ${form.fld({ id: 'date_start', label: 'Início', req: 1, type: 'datetime-local', value: fm.inputDt(new Date().toISOString()) })}
                        ${form.fld({ id: 'date_end', label: 'Fim', req: 1, type: 'datetime-local' })}
                    </div>

                    <p class="note1">O valor é definido pela plataforma e aparece depois do envio. A plataforma ainda não processa pagamentos: a divulgação fica com pagamento pendente.</p>

                    <p class="ferr" role="alert"></p>
                    <button class="btn btn--solid">Solicitar divulgação</button>
                </form>
            `
        });

        form.photoInit(m.body);

        form.wire($('#af', m.body), async () => {
            const g = id => $('#' + id, m.body).value,
                im = form.photoGet(m.body, 'image');

            const bad = [
                form.err('image', im.blob ? '' : 'Envie a imagem da divulgação.'),
                form.err('date_start', g('date_start') ? '' : 'Informe o início.'),
                form.err('date_end', !g('date_end') ? 'Informe o fim.' : new Date(g('date_end')) <= new Date(g('date_start')) ? 'O fim deve ser depois do início.' : '')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(m.body);
                return;
            }

            const fd = new FormData();

            fd.append('image', im.blob, 'divulgacao.jpg');
            fd.append('date_start', fm.isoDt(g('date_start')));
            fd.append('date_end', fm.isoDt(g('date_end')));

            const a = await SAM.api.workshop.addAdvertisement(p.id, fd);

            m.close();
            SAM.toast(`Divulgação solicitada${a.advertising_price != null ? ' por ' + fm.money(a.advertising_price).replace('\xa0', ' ') : ''} — pagamento pendente.`);
            await reload();
            T.select('a');
        }, { busy: 'Enviando…' });
    }

    /* ---------- listas ---------- */

    const shownAd = a => a.status_advertisement === 'active' && a.is_running_now !== true ? 'pending' : a.status_advertisement;

    function listP() {
        $('#pn').innerHTML = promos.length ? ui.table({
            caption: 'Promoções da oficina',
            rowHead: true,
            rows: promos,
            cols: [
                { h: 'Promoção', c: p => esc(p.title) },
                { h: 'Alvo', c: p => esc(target(p)) },
                { h: 'Desconto', c: p => esc(fm.discount(p.type_discount, p.discount_value)) },
                { h: 'Período', c: p => esc(period(p)) },
                { h: 'Situação', c: p => ui.badge('effective_status', p.effective_status) },
                { h: 'Ações', c: p => `<div class="acts">
                    <button type="button" class="btn" data-e="${esc(p.id)}">${p.effective_status === 'expired' ? 'Ver' : 'Editar'}</button>
                    ${p.effective_status === 'active' ? `<button type="button" class="btn" data-ad="${esc(p.id)}">Divulgar no SAM</button>` : ''}
                </div>` }
            ]
        }) : '<p class="empty">Você ainda não criou promoções.</p>';
    }

    function listA() {
        $('#pn').innerHTML = `
            <p class="note1">Pagamento pendente — a plataforma ainda não processa pagamentos. Uma divulgação só aparece como “No ar” quando estiver de fato em exibição.</p>

            ${ads.length ? ui.table({
                caption: 'Divulgações',
                rowHead: true,
                rows: ads,
                cols: [
                    { h: 'Promoção', c: a => esc((promos.find(p => p.id === a.id_promotion) || {}).title || '—') },
                    { h: 'Imagem', c: a => a.image_url ? `<img class="pth" src="${ui.url(a.image_url)}" alt="Imagem da divulgação">` : '—' },
                    { h: 'Período', c: a => esc(period(a)) },
                    { h: 'Valor', cls: 'num', c: a => a.advertising_price != null ? fm.money(a.advertising_price) : '—' },
                    { h: 'Pagamento', c: a => ui.badge('payment_status', a.payment_status) },
                    { h: 'Situação', c: a => ui.badge('status_advertisement', shownAd(a)) }
                ]
            }) : '<p class="empty">Nenhuma divulgação ainda. Divulgue uma promoção que esteja no ar.</p>'}
        `;
    }

    function show(k) {
        tab = k;
        (k === 'p' ? listP : listA)();
        $('#pn').setAttribute('aria-labelledby', 'tb-' + k);
        $('#np').hidden = k !== 'p';
    }

    async function reload() {
        const r = await SAM.api.workshop.promotions();

        promos = r.results;
        ads = (await Promise.all(promos.slice(0, 30).map(p => SAM.api.workshop.advertisements(p.id).then(x => x.results).catch(() => [])))).flat();
        show(tab);
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap">
                ${ui.subnav('promotions')}

                <div class="hbar">
                    <h1 class="h1">Promoções e divulgações</h1>
                    <button type="button" class="btn btn--solid" id="np">+ Nova promoção</button>
                </div>

                <div class="tabs" role="tablist" aria-label="Seções">
                    <i></i>
                    <button role="tab" id="tb-p" data-tab="p" aria-selected="true" aria-controls="pn">Promoções</button>
                    <button role="tab" id="tb-a" data-tab="a" aria-selected="false" aria-controls="pn" tabindex="-1">Divulgações</button>
                </div>

                <div id="pn" role="tabpanel" aria-live="polite"></div>
            </div>
        `;

        T = ui.tabs($('.tabs', view), show);
        T.select('p');

        $('#np').onclick = () => edit(null);

        $('#pn').onclick = e => {
            const b = e.target.closest('[data-e]'),
                a = e.target.closest('[data-ad]');

            if (b) edit(promos.find(p => String(p.id) === b.dataset.e));

            if (a) advertise(promos.find(p => String(p.id) === a.dataset.ad));
        };
    }

    ui.load(view, async () => {
        const [p, s, pr] = await Promise.all([
            SAM.api.workshop.promotions(),
            SAM.api.workshop.services(),
            SAM.api.workshop.products()
        ]);

        svcs = s.results;
        prods = pr.results;

        const a = (await Promise.all(p.results.slice(0, 30).map(x => SAM.api.workshop.advertisements(x.id).then(y => y.results).catch(() => [])))).flat();

        return { p: p.results, a };
    }, r => {
        promos = r.p;
        ads = r.a;
        draw();
    });
})();
