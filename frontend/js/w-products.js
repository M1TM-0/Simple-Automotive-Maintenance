(() => {
    /* T23 — Produtos da oficina (catálogo INFORMATIVO). Sem excluir: use active=false. */

    const { $, esc, fm, form, ui } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('PRODUTOS DA OFICINA');

    const view = $('#view'),
        FILTERS = [
            ['all', 'Todos', () => true],
            ['on', 'Disponíveis', p => p.active && p.disponibility],
            ['off', 'Indisponíveis', p => p.active && !p.disponibility],
            ['inactive', 'Inativos', p => !p.active]
        ];

    let items = [], flt = 'all', q = '';

    const rows = () => {
        const f = FILTERS.find(x => x[0] === flt)[2];

        return items.filter(p =>
            f(p) &&
            (p.name + ' ' + (p.brand || '') + ' ' + (p.category || '')).toLowerCase().includes(q)
        );
    };

    function table() {
        const r = rows();

        $('#tb').innerHTML = r.length
            ? ui.table({
                caption: 'Produtos da oficina',
                rowHead: false,
                rows: r,
                cols: [
                    { h: 'Foto', c: p => p.photo ? `<img class="pth" src="${ui.url(p.photo)}" alt="Foto de ${esc(p.name)}">` : '<span class="muted">Sem foto</span>' },
                    { h: 'Produto', c: p => `<b>${esc(p.name)}</b>${p.description ? `<br><small class="muted">${esc(p.description)}</small>` : ''}` },
                    { h: 'Marca', c: p => esc(p.brand || '—') },
                    { h: 'Categoria', c: p => esc(p.category || '—') },
                    { h: 'Preço', cls: 'num', c: p => fm.money(p.price) },
                    { h: 'Disponibilidade', c: p => `<span class="sb ${p.disponibility ? 'sb--ok' : 'sb--warn'}">${p.disponibility ? 'Disponível' : 'Indisponível'}</span>` },
                    { h: 'Situação', c: p => `<span class="sb ${p.active ? '' : 'sb--bad'}">${p.active ? 'Ativo' : 'Inativo'}</span>` },
                    { h: 'Ações', c: p => `<button type="button" class="btn" data-ed="${esc(p.id)}">Editar</button>` }
                ]
            })
            : '<p class="empty">Nenhum produto corresponde aos filtros.</p>';
    }

    async function reload() {
        items = (await SAM.api.workshop.products()).results;
        table();
    }

    function edit(p) {
        const d = p || { disponibility: true, active: true },
            used = [...new Set(items.map(x => x.category).filter(Boolean))],
            m = ui.modal({
                title: p ? 'Editar produto' : 'Novo produto',
                wide: true,
                body: `
                    <form id="pf" novalidate>
                        <div class="fgrid">
                            ${form.fld({ id: 'name', label: 'Nome', req: 1, value: d.name, attrs: 'maxlength="255"' })}
                            ${form.fld({ id: 'brand', label: 'Marca', value: d.brand, attrs: 'maxlength="255"' })}
                            ${form.fld({ id: 'category', label: 'Categoria', value: d.category, attrs: 'maxlength="255" list="cl"' })}
                            ${form.fld({ id: 'price', label: 'Preço (R$)', req: 1, value: p ? fm.inMoney(fm.cents(d.price)) : '', attrs: 'inputmode="decimal"' })}
                        </div>

                        <datalist id="cl">${used.map(c => `<option value="${esc(c)}"></option>`).join('')}</datalist>

                        ${form.fld({ id: 'description', label: 'Descrição', rows: 3, value: d.description })}

                        <div class="row">
                            <label class="chk1"><input type="checkbox" id="disponibility" ${d.disponibility ? 'checked' : ''}> Disponível</label>
                            <label class="chk1"><input type="checkbox" id="active" ${d.active ? 'checked' : ''}> Ativo (aparece no perfil público)</label>
                        </div>

                        ${form.photo({ id: 'photo', label: 'Foto', url: d.photo, rm: 1, max: 900 })}

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid">Salvar produto</button>
                    </form>
                `
            });

        form.photoInit(m.body);

        form.wire($('#pf', m.body), async () => {
            const g = id => $('#' + id).value.trim(),
                c = fm.cents(g('price'));

            const bad = [
                form.err('name', g('name') ? '' : 'Informe o nome do produto.'),
                form.err('price', c >= 0 ? '' : 'Informe o preço (0 ou mais).')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(m.body);
                return;
            }

            const fd = new FormData(),
                ph = form.photoGet(m.body, 'photo');

            fd.append('name', g('name'));
            fd.append('description', g('description'));
            fd.append('category', g('category'));
            fd.append('brand', g('brand'));
            fd.append('price', fm.outMoney(c));
            fd.append('disponibility', $('#disponibility').checked);
            fd.append('active', $('#active').checked);

            if (ph.blob) fd.append('photo', ph.blob, 'produto.jpg');
            else if (ph.removed) fd.append('photo', '');

            if (p) await SAM.api.workshop.updateProduct(p.id, fd);
            else await SAM.api.workshop.addProduct(fd);

            await reload();
            m.close();
            SAM.toast('Produto salvo.');
        }, { busy: 'Salvando…' });
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap">
                ${ui.subnav('products')}

                <div class="hbar">
                    <h1 class="h1">Produtos da oficina</h1>
                    <button type="button" class="btn btn--solid" id="np">+ Novo produto</button>
                </div>

                <p class="note1">
                    Catálogo informativo. O SAM não vende nem processa pagamentos; a negociação é feita com o cliente pelo chat.
                </p>

                <label class="search" style="max-width:420px">
                    <span class="sr">Buscar produto</span>
                    ${SAM.I.s}
                    <input id="q" placeholder="Buscar por nome, marca ou categoria">
                </label>

                <div class="chips" role="group" aria-label="Filtrar produtos">
                    ${FILTERS.map(([k, l]) => `<button type="button" class="chip" data-f="${k}" aria-pressed="${k === flt}">${l}</button>`).join('')}
                </div>

                ${items.length ? '' : '<p class="empty">Você ainda não cadastrou produtos.</p>'}

                <div id="tb" aria-live="polite"></div>
            </div>
        `;

        table();

        $('#np').onclick = () => edit(null);

        $('#q').oninput = e => {
            q = e.target.value.trim().toLowerCase();
            table();
        };

        view.querySelector('.chips').onclick = e => {
            const b = e.target.closest('[data-f]');

            if (!b) return;

            flt = b.dataset.f;
            view.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', x === b));
            table();
        };

        $('#tb').onclick = e => {
            const b = e.target.closest('[data-ed]');

            if (b) edit(items.find(p => String(p.id) === b.dataset.ed));
        };
    }

    ui.load(view, () => SAM.api.workshop.products(), r => {
        items = r.results;
        draw();
    });
})();
