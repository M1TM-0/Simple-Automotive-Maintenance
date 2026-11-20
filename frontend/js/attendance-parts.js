(() => {
    /* Modais do atendimento: M01 (solicitar) aqui; M02 (avaliar) mais abaixo. */

    const { $, esc, fm, v: V, form, ui } = SAM;

    /* ---------- M01 — Solicitar atendimento ---------- */

    ui.requestAttendance = async w => {
        const m = ui.modal({
            title: 'Solicitar atendimento',
            body: '<p class="muted" role="status">Carregando seus veículos…</p>'
        });

        let list = [];

        try {
            let r = await SAM.api.vehicles.list();

            list = r.results;

            for (let i = 0; r.next && i < 20; i++) {
                r = await SAM.api.vehicles.list({ page: SAM.api.pageOf(r.next) });
                list = list.concat(r.results);
            }
        } catch (e) {
            m.body.innerHTML = `<p class="ferr" role="alert">${esc(SAM.api.isUnavailable(e) ? 'O servidor ainda não está disponível.' : e.detail)}</p>`;
            return;
        }

        if (!list.length) {
            m.body.innerHTML = `
                <p>Para solicitar atendimento você precisa de um veículo cadastrado.</p>
                <a class="btn btn--solid" href="vehicle-new.html">Cadastre um veículo</a>
            `;

            return;
        }

        m.body.innerHTML = `
            <form id="mf" novalidate>
                <p class="muted" style="font-size:.82rem">Oficina: <b>${esc(w.name_fantasy)}</b></p>

                ${form.fld({
                    id: 'id_vehicle',
                    label: 'Veículo',
                    req: 1,
                    select: '<option value="">Selecione</option>' + list.map(v =>
                        `<option value="${esc(v.id)}">${esc(v.brand + ' ' + v.model + ' · ' + fm.plate(v.plate))}</option>`).join('')
                })}

                ${form.fld({ id: 'mileage_km', label: 'Quilometragem atual (opcional)', attrs: 'inputmode="numeric"' })}

                ${form.fld({
                    id: 'observations',
                    label: 'Descreva o problema ou o serviço (opcional)',
                    rows: 4,
                    attrs: 'maxlength="1000"'
                })}

                <small class="muted" id="cnt" aria-live="off">0/1000</small>

                <p class="ferr" role="alert"></p>

                <button class="btn btn--solid">Enviar solicitação</button>
            </form>
        `;

        $('#observations', m.body).addEventListener('input', e => {
            $('#cnt', m.body).textContent = e.target.value.length + '/1000';
        });

        $('#id_vehicle', m.body).addEventListener('change', e => {
            const v = list.find(x => String(x.id) === e.target.value);

            if (v && v.mileage_km != null && !$('#mileage_km', m.body).value) {
                $('#mileage_km', m.body).value = v.mileage_km;
            }
        });

        form.wire($('#mf', m.body), async () => {
            const g = id => $('#' + id, m.body).value.trim(),
                km = g('mileage_km') ? V.int(g('mileage_km')) : null;

            const bad = [
                form.err('id_vehicle', g('id_vehicle') ? '' : 'Escolha o veículo.'),
                form.err('mileage_km', g('mileage_km') && !(km >= 0) ? 'Use só números (0 ou mais).' : ''),
                form.err('observations', g('observations').length > 1000 ? 'Use até 1000 caracteres.' : '')
            ];

            if (bad.some(Boolean)) {
                form.focusBad(m.body);
                return;
            }

            const body = { id_workshop: w.id, id_vehicle: isNaN(+g('id_vehicle')) ? g('id_vehicle') : +g('id_vehicle') };

            if (km != null) body.mileage_km = km;

            if (g('observations')) body.observations = g('observations');

            const r = await SAM.api.attendances.create(body);

            m.close();

            ui.toastLink('Solicitação enviada.', 'attendance.html?id=' + encodeURIComponent(r.id), 'Acompanhar');
        }, { busy: 'Enviando…' });
    };
})();

(() => {
    /* Auxiliares de atendimento/orçamento + M02 (avaliar). */

    const { $, esc, fm, form, ui } = SAM;

    const A = {};

    /* orçamento vigente (pending/approved) e anteriores (rejected/expired/cancelled) */

    A.split = a => {
        const all = a.budgets || (a.budget ? [a.budget] : []),
            cur = all.find(b => b.status_budget === 'pending' || b.status_budget === 'approved') || null;

        return { cur, past: all.filter(b => b !== cur) };
    };

    A.expired = b => !!b && !!b.date_validity && new Date(b.date_validity) < new Date();

    A.validity = b => {
        if (!b || !b.date_validity) return '';

        if (A.expired(b)) return 'Expirado';

        const d = Math.ceil((new Date(b.date_validity) - Date.now()) / 86400000);

        return d <= 0 ? 'vence hoje' : d === 1 ? 'vence em 1 dia' : `vence em ${d} dias`;
    };

    /* peça ligada a um serviço (id_service_item) fica logo abaixo dele */

    A.order = items => {
        const kids = {},
            top = [];

        items.forEach(i => {
            if (i.id_service_item) (kids[i.id_service_item] = kids[i.id_service_item] || []).push(i);
            else top.push(i);
        });

        return top.flatMap(i => [i].concat(kids[i.id] || []))
            .concat(items.filter(i => i.id_service_item && !top.some(t => t.id === i.id_service_item)));
    };

    const sub = i => i.subtotal != null
        ? Number(i.subtotal)
        : fm.sub(fm.milli(i.quantity), fm.cents(i.unit_price)) / 100;

    /* tabela somente leitura; showExec mostra a coluna "Situação" (depois do in_progress) */

    A.table = (items, showExec) => ui.table({
        caption: 'Itens do orçamento',
        rows: A.order(items),
        cols: [
            { h: 'Tipo', c: i => esc(SAM.lbl('item_type', i.item_type)) },
            { h: 'Descrição', c: i => `<span class="${i.id_service_item ? 'ind' : ''}">${esc(i.description)}</span>` },
            { h: 'Qtd', cls: 'num', c: i => esc(String(i.quantity).replace('.', ',')) },
            { h: 'Valor unitário', cls: 'num', c: i => fm.money(i.unit_price) },
            { h: 'Subtotal', cls: 'num', c: i => fm.money(sub(i)) }
        ].concat(showExec ? [{ h: 'Situação', c: i => ['service', 'product'].includes(i.item_type) ? ui.badge('execution_status', i.execution_status || 'pending') : '—' }] : [])
    });

    /* ---------- M02 — Avaliar atendimento ---------- */

    ui.reviewAttendance = (idBudget, done) => {
        const m = ui.modal({
            title: 'Avaliar atendimento',
            body: `
                <form id="vf" novalidate>
                    <fieldset class="fs fs--m rate">
                        <legend>Nota <abbr title="obrigatório">*</abbr></legend>

                        <div class="rate__s" role="radiogroup" aria-label="Nota de 1 a 5">
                            ${[5, 4, 3, 2, 1].map(n => `
                                <input type="radio" name="rating" id="rt${n}" value="${n}">
                                <label for="rt${n}" title="${n} de 5"><span class="sr">${n} de 5</span>★</label>
                            `).join('')}
                        </div>

                        <span class="err" id="e-rating" role="alert"></span>
                    </fieldset>

                    ${form.fld({ id: 'comment', label: 'Comentário (opcional)', rows: 4, attrs: 'maxlength="500"' })}

                    <p class="ferr" role="alert"></p>

                    <button class="btn btn--solid">Enviar avaliação</button>
                </form>
            `
        });

        form.wire($('#vf', m.body), async () => {
            const r = $('input[name=rating]:checked', m.body),
                c = $('#comment', m.body).value.trim();

            if (form.err('rating', r ? '' : 'Escolha uma nota de 1 a 5.')) {
                $('input[name=rating]', m.body).focus();
                return;
            }

            const body = { id_budget: idBudget, rating: +r.value };

            if (c) body.comment = c;

            try {
                await SAM.api.reviews.create(body);
            } catch (e) {
                if (e.status === 409) {
                    $('.ferr', m.body).textContent = 'Você já avaliou este atendimento.';
                    return;
                }

                throw e;
            }

            m.close();
            SAM.toast('Avaliação enviada. Obrigado!');

            if (done) done();
        }, { busy: 'Enviando…' });
    };

    /* linha do tempo do histórico (somente leitura): T19 e T26 */

    ui.historyList = rows => rows.length
        ? `<ul class="tl">${rows.map(h => `
            <li>
                <span class="sb">${h.record_type === 'part' ? 'Peça' : 'Serviço'}</span>
                <b>${esc(fm.date(h.date_maintenance))}</b>
                · ${esc(h.description)}
                ${h.mileage_km != null ? '· ' + esc(SAM.km(h.mileage_km)) : ''}
                ${h.record_type === 'part' && h.quantity != null ? `· ${esc(String(h.quantity).replace('.', ','))} × ${fm.money(h.unit_price)}` : ''}
            </li>`).join('')}</ul>`
        : '<p class="muted">Sem registros no histórico.</p>';

    SAM.att = A;
})();
