(() => {
    /* T20 — Editor de orçamento (Oficina). O total é SEMPRE o total_price devolvido pela API. */

    const { $, $$, esc, fm, lbl, v: V, form, ui } = SAM,
        T = SAM.att;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('ORÇAMENTO');

    const id = new URLSearchParams(location.search).get('attendance'),
        view = $('#view');

    let a, bud, svcs = [], prods = [], rows = [], seq = 0;

    const money = c => isNaN(c) ? '—' : SAM.brl(c / 100);

    /* ---------- linhas ---------- */

    const fromItem = i => ({
        key: 'r' + (++seq),
        id: i.id,
        type: i.item_type,
        origin: i.id_workshop_service ? 's' + i.id_workshop_service : i.id_product ? 'p' + i.id_product : '',
        desc: i.description,
        qty: String(i.quantity).replace('.', ','),
        price: isNaN(fm.cents(i.unit_price)) ? '' : fm.inMoney(fm.cents(i.unit_price)),
        parent: i.id_service_item ? String(i.id_service_item) : '',
        st: 'ok',
        msg: 'Salvo'
    });

    const blank = () => ({ key: 'r' + (++seq), id: null, type: 'labor', origin: '', desc: '', qty: '1', price: '', parent: '', st: 'draft', msg: 'Não salvo' });

    const row = k => rows.find(r => r.key === k);

    const sub = r => {
        const q = fm.milli(r.qty),
            c = fm.cents(r.price);

        return isNaN(q) || isNaN(c) ? NaN : fm.sub(q, c);
    };

    const check = r => {
        const q = fm.milli(r.qty),
            c = fm.cents(r.price),
            e = {};

        if (!r.desc.trim()) e.desc = 'Descrição obrigatória.';
        else if (r.desc.trim().length > 255) e.desc = 'Use até 255 caracteres.';

        if (!(q > 0)) e.qty = 'Quantidade maior que 0 (até 3 casas).';

        if (!(c >= 0)) e.price = 'Valor 0 ou mais (2 casas).';

        return e;
    };

    const originOpts = r => r.type === 'service'
        ? '<option value="">Sem origem</option>' + svcs.filter(s => s.disponibility || ('s' + s.id) === r.origin).map(s => `<option value="s${esc(s.id)}" ${('s' + s.id) === r.origin ? 'selected' : ''}>${esc(s.name)}</option>`).join('')
        : r.type === 'product'
            ? '<option value="">Sem origem</option>' + prods.map(p => `<option value="p${esc(p.id)}" ${('p' + p.id) === r.origin ? 'selected' : ''}>${esc(p.name)}</option>`).join('')
            : '<option value="">—</option>';

    const parentOpts = r => '<option value="">Nenhum</option>' + rows
        .filter(x => x.type === 'service' && x.id)
        .map(x => `<option value="${esc(x.id)}" ${String(x.id) === r.parent ? 'selected' : ''}>${esc(x.desc)}</option>`).join('');

    function rowHtml(r) {
        const e = check(r),
            bad = f => (r.st === 'err' || r.st === 'draft') && e[f] && (r.touched || r.id) ? 'true' : 'false';

        return `
            <tr data-k="${r.key}">
                <td data-label="Tipo"><select data-f="type" aria-label="Tipo do item">${SAM.opts('item_type', r.type)}</select></td>
                <td data-label="Origem"><select data-f="origin" aria-label="Origem" ${['service', 'product'].includes(r.type) ? '' : 'disabled'}>${originOpts(r)}</select></td>
                <td data-label="Descrição"><input data-f="desc" aria-label="Descrição" maxlength="255" value="${esc(r.desc)}" aria-invalid="${bad('desc')}"></td>
                <td data-label="Qtd"><input data-f="qty" aria-label="Quantidade" inputmode="decimal" value="${esc(r.qty)}" aria-invalid="${bad('qty')}"></td>
                <td data-label="Valor unit. (R$)"><input data-f="price" aria-label="Valor unitário em reais" inputmode="decimal" value="${esc(r.price)}" aria-invalid="${bad('price')}"></td>
                <td data-label="Subtotal" class="num" data-sub>${money(sub(r))}</td>
                <td data-label="Pertence ao serviço">${r.type === 'product' ? `<select data-f="parent" aria-label="Pertence ao serviço">${parentOpts(r)}</select>` : '—'}</td>
                <td data-label="Ações">
                    <span class="rst ${r.st === 'err' ? 'rst--err' : ''}" role="status" data-rst>${esc(r.msg || '')}</span>
                    <button type="button" class="btn btn--danger" data-rm style="padding:.3rem .9rem;font-size:.7rem">Remover</button>
                    <div data-cf></div>
                </td>
            </tr>
        `;
    }

    function drawRows(focus) {
        $('#rows').innerHTML = rows.length
            ? rows.map(rowHtml).join('')
            : '<tr><td colspan="8" class="muted">Nenhum item. Use “Adicionar item”.</td></tr>';

        if (focus) {
            const f = $(`[data-k="${focus.k}"] [data-f="${focus.f}"]`);

            if (f) f.focus();
        }

        sendState();
    }

    const sendState = () => {
        const b = $('#send');

        if (!b) return;

        const ok = rows.length > 0 && rows.every(r => r.st === 'ok');

        b.disabled = !ok;
        $('#sendhint').textContent = ok ? '' : rows.length ? 'Salve ou corrija todos os itens para enviar.' : 'Adicione ao menos um item (peças e/ou mão de obra) com valores.';
    };

    /* ---------- gravação item a item ---------- */

    const rst = (r, st, msg) => {
        r.st = st;
        r.msg = msg;

        const el = $(`[data-k="${r.key}"] [data-rst]`);

        if (el) {
            el.textContent = msg;
            el.classList.toggle('rst--err', st === 'err');
        }

        sendState();
    };

    const total = async () => {
        const x = await SAM.api.workshop.attendance(id),
            b = T.split(x).cur;

        if (b) {
            $('#total').textContent = fm.money(b.total_price);

            (b.items || []).forEach(i => {
                const r = rows.find(q => q.id === i.id),
                    el = r && $(`[data-k="${r.key}"] [data-sub]`);

                if (el && i.subtotal != null) el.textContent = fm.money(i.subtotal);
            });
        }
    };

    function save(r) {
        const e = check(r);

        $$(`[data-k="${r.key}"] [data-f]`).forEach(c => {
            c.setAttribute('aria-invalid', e[c.dataset.f] ? 'true' : 'false');
        });

        if (Object.keys(e).length) {
            rst(r, r.id ? 'err' : 'draft', Object.values(e)[0]);
            return;
        }

        const body = {
            item_type: r.type,
            description: r.desc.trim(),
            quantity: fm.outQty(fm.milli(r.qty)),
            unit_price: fm.outMoney(fm.cents(r.price))
        };

        if (r.type === 'service' && r.origin.startsWith('s')) body.id_workshop_service = +r.origin.slice(1);

        if (r.type === 'product' && r.origin.startsWith('p')) body.id_product = +r.origin.slice(1);

        if (r.type === 'product' && r.parent) body.id_service_item = +r.parent;

        rst(r, 'saving', 'Salvando…');

        r.q = (r.q || Promise.resolve()).then(async () => {
            try {
                const x = r.id
                    ? await SAM.api.workshop.updateItem(bud.id, r.id, body)
                    : await SAM.api.workshop.addItem(bud.id, body);

                if (!r.id) {
                    r.id = x.id;

                    /* serviço recém-gravado passa a ser opção de "pertence ao serviço" */

                    $$('[data-f=parent]').forEach(s => {
                        const k = s.closest('tr').dataset.k;

                        s.innerHTML = parentOpts(row(k));
                    });
                }

                rst(r, 'ok', 'Salvo');
                await total();
            } catch (x) {
                rst(r, 'err', (x.detail || 'Erro ao salvar') + (Object.keys(x.fields || {}).length ? ' (' + Object.values(x.fields)[0] + ')' : ''));
            }
        });
    }

    /* ---------- página ---------- */

    function summary() {
        const c = a.client || {},
            v = a.vehicle || {};

        return `<p class="muted">${esc(c.name || 'Cliente')} · ${esc((v.brand || '') + ' ' + (v.model || ''))} <span class="plate">${esc(fm.plate(v.plate))}</span></p>`;
    }

    const pastHtml = past => past.length ? `
        <section aria-label="Orçamentos anteriores">
            <h2 class="h2" style="font-size:.95rem;margin-bottom:8px">Orçamentos anteriores</h2>
            ${past.map(b => `<details class="pastb"><summary>${esc(lbl('status_budget', b.status_budget))} · ${fm.money(b.total_price)}</summary>${T.table(b.items || [], false)}</details>`).join('')}
        </section>` : '';

    function readonly(cur, past, msg) {
        view.innerHTML = `
            <div class="wrap wrap--n ad">
                <a class="back-l" href="w-attendance.html?id=${encodeURIComponent(id)}">← Atendimento</a>
                <h1 class="h1">Orçamento</h1>
                ${summary()}

                <section class="sc">
                    ${msg ? `<p role="status"><b>${esc(msg)}</b></p>` : ''}
                    ${cur ? `<p>${ui.badge('status_budget', cur.status_budget)} <small class="muted">${esc(T.validity(cur))}</small></p>
                        ${T.table(cur.items || [], false)}
                        <div class="btot"><span>Total</span><b>${fm.money(cur.total_price)}</b></div>
                        ${cur.observations ? `<p class="muted">Observações: ${esc(cur.observations)}</p>` : ''}` : '<p class="muted">Não há orçamento em edição.</p>'}
                </section>

                ${pastHtml(past)}
            </div>
        `;
    }

    function editor(past) {
        const dv = bud.date_validity ? fm.inputDt(bud.date_validity) : fm.inputDt(new Date(Date.now() + 7 * 864e5).toISOString());

        view.innerHTML = `
            <div class="wrap wrap--n ad bed">
                <a class="back-l" href="w-attendance.html?id=${encodeURIComponent(id)}">← Atendimento</a>
                <h1 class="h1">Orçamento</h1>
                ${summary()}

                <form class="sc" id="hf" novalidate>
                    <h2>Dados do orçamento</h2>

                    <div class="fgrid">
                        ${form.fld({ id: 'date_validity', label: 'Validade', req: 1, type: 'datetime-local', value: dv })}
                    </div>

                    ${form.fld({ id: 'obs', name: 'observations', label: 'Observações (opcional)', rows: 3, value: bud.observations })}

                    <p class="ferr" role="alert"></p>
                    <button class="btn" id="hs">Salvar dados</button>
                </form>

                <section class="sc">
                    <h2>Itens</h2>

                    <div class="tbl-w">
                        <table class="tbl">
                            <caption class="sr">Itens do orçamento (editáveis)</caption>

                            <thead><tr>
                                <th scope="col">Tipo</th><th scope="col">Origem</th><th scope="col">Descrição</th>
                                <th scope="col">Qtd</th><th scope="col">Valor unit. (R$)</th><th scope="col">Subtotal</th>
                                <th scope="col">Pertence ao serviço</th><th scope="col">Ações</th>
                            </tr></thead>

                            <tbody id="rows" aria-live="polite"></tbody>
                        </table>
                    </div>

                    <div class="row" style="margin-top:12px">
                        <button type="button" class="btn" id="add">+ Adicionar item</button>
                    </div>

                    <div class="btot"><span>Total</span><b id="total">${fm.money(bud.total_price)}</b></div>
                </section>

                <section class="sc">
                    <button type="button" class="btn btn--solid" id="send" disabled>Enviar para o cliente</button>
                    <p class="muted" id="sendhint" role="status" style="font-size:.78rem;margin-top:6px"></p>
                    <div id="cfs" aria-live="polite"></div>
                </section>

                ${pastHtml(past)}
            </div>
        `;

        rows = (bud.items || []).map(fromItem);
        drawRows();

        const body = $('#rows');

        body.addEventListener('input', e => {
            const f = e.target.closest('[data-f]'),
                r = f && row(f.closest('tr').dataset.k);

            if (!r || !['desc', 'qty', 'price'].includes(f.dataset.f)) return;

            r[f.dataset.f] = f.value;
            r.touched = true;
            $(`[data-k="${r.key}"] [data-sub]`).textContent = money(sub(r));
        });

        body.addEventListener('change', e => {
            const f = e.target.closest('[data-f]'),
                r = f && row(f.closest('tr').dataset.k);

            if (!r) return;

            r.touched = true;

            const k = f.dataset.f;

            if (k === 'type') {
                r.type = f.value;
                r.origin = '';

                if (r.type !== 'product') r.parent = '';

                drawRows({ k: r.key, f: 'type' });
            } else if (k === 'origin') {
                r.origin = f.value;

                const src = f.value.startsWith('s') ? svcs.find(s => 's' + s.id === f.value) : prods.find(p => 'p' + p.id === f.value);

                if (src) {
                    r.desc = src.name;
                    r.price = fm.inMoney(fm.cents(src.price_base ?? src.price));
                    drawRows({ k: r.key, f: 'origin' });
                }
            } else if (k === 'parent') {
                r.parent = f.value;
            } else {
                r[k] = f.value;
            }

            save(r);
        });

        body.addEventListener('click', e => {
            const b = e.target.closest('[data-rm]');

            if (!b) return;

            const tr = b.closest('tr'),
                r = row(tr.dataset.k);

            ui.confirm($('[data-cf]', tr), {
                text: 'Remover este item?',
                yes: 'Sim, remover',
                back: b,
                onYes: async () => {
                    if (r.id) await SAM.api.workshop.removeItem(bud.id, r.id);

                    rows = rows.filter(x => x !== r);

                    if (r.id) await load(true);
                    else drawRows();

                    if (!r.id) $('#add').focus();
                }
            });
        });

        $('#add').onclick = () => {
            const r = blank();

            rows.push(r);
            drawRows({ k: r.key, f: 'desc' });
        };

        form.wire($('#hf'), () => saveHead(), { btn: '#hs', busy: 'Salvando…', alias: { date_validity: 'date_validity' } });

        $('#send').onclick = e => ui.confirm($('#cfs'), {
            text: 'Enviar o orçamento para o cliente? Depois do envio ele não poderá ser editado.',
            yes: 'Sim, enviar',
            danger: false,
            back: e.currentTarget,
            onYes: async () => {
                if (!(await saveHead(true))) throw { detail: 'Corrija a validade do orçamento.' };

                await SAM.api.workshop.sendBudget(bud.id);
                await load(true);
            }
        });
    }

    async function saveHead(silent) {
        const v = $('#date_validity').value;

        if (form.err('date_validity', !v ? 'Informe a validade.' : new Date(v) <= new Date() ? 'A validade deve ser uma data futura.' : '')) {
            form.focusBad($('#hf'));
            return false;
        }

        await SAM.api.workshop.updateBudget(bud.id, { date_validity: fm.isoDt(v), observations: $('#obs').value.trim() });

        if (!silent) SAM.toast('Dados do orçamento salvos.');

        return true;
    }

    async function load(redraw) {
        const x = await SAM.api.workshop.attendance(id);

        a = x;

        const { cur, past } = T.split(a),
            st = a.status_attendance;

        if (cur && cur.status_budget === 'pending' && st === 'budgeted') {
            bud = cur;
            editor(past);
            return;
        }

        if (!cur && ['requested', 'budgeted'].includes(st)) {
            view.innerHTML = `
                <div class="wrap wrap--n ad">
                    <a class="back-l" href="w-attendance.html?id=${encodeURIComponent(id)}">← Atendimento</a>
                    <h1 class="h1">Orçamento</h1>
                    ${summary()}

                    <section class="sc">
                        <p>Este atendimento ainda não tem um orçamento em edição.</p>
                        <button type="button" class="btn btn--solid" id="mk">Criar orçamento</button>
                        <p class="ferr" id="mke" role="alert"></p>
                    </section>

                    ${pastHtml(past)}
                </div>
            `;

            $('#mk').onclick = async e => {
                const btn = e.currentTarget;

                form.busy(btn, true, 'Criando…');

                try {
                    await SAM.api.workshop.createBudget(id);
                    await load(true);
                } catch (x) {
                    $('#mke').textContent = x.detail;
                    form.busy(btn, false);
                }
            };

            return;
        }

        readonly(cur, past, st === 'waiting_approval' ? 'Aguardando resposta do cliente' : cur ? '' : 'Este atendimento não permite editar orçamento.');
    }

    ui.load(view, async () => {
        const [at, s, p] = await Promise.all([
            SAM.api.workshop.attendance(id),
            SAM.api.workshop.services(),
            SAM.api.workshop.products()
        ]);

        svcs = s.results;
        prods = p.results.filter(x => x.active !== false);

        return at;
    }, () => load());
})();
