(() => {
    /* T19 — Detalhe do atendimento (Oficina). Só a oficina altera o status (RN09); a API valida a máquina de estados. */

    const { $, $$, esc, fm, lbl, v: V, form, ui } = SAM,
        T = SAM.att;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('ATENDIMENTO');

    const id = new URLSearchParams(location.search).get('id'),
        view = $('#view');

    let a;

    const CANCELABLE = ['requested', 'budgeted', 'waiting_approval', 'approved', 'in_progress'],
        LOCKED = ['delivered', 'canceled'];

    const reload = async () => {
        a = await SAM.api.workshop.attendance(id);
        draw();
    };

    async function go(status) {
        await SAM.api.workshop.transition(id, status);
        await reload();
    }

    const pending = () => {
        const b = T.split(a).cur;

        return b && b.status_budget === 'approved'
            ? (b.items || []).filter(i => ['service', 'product'].includes(i.item_type) && (i.execution_status || 'pending') === 'pending')
            : [];
    };

    function actions() {
        const s = a.status_attendance,
            bud = `w-budget.html?attendance=${encodeURIComponent(id)}`,
            p = pending();

        const b = (idn, l, cls = 'btn--solid', dis = false) => `<button type="button" class="btn ${cls}" id="${idn}" ${dis ? 'disabled' : ''}>${l}</button>`;

        const A = {
            requested: `<a class="btn btn--solid" href="${bud}">Criar orçamento</a>`,
            budgeted: `<a class="btn btn--solid" href="${bud}">Editar e enviar orçamento</a>`,
            waiting_approval: '<p class="muted" role="status">Aguardando a resposta do cliente ao orçamento.</p>',
            approved: b('bs', 'Iniciar manutenção'),
            in_progress: b('bd', 'Marcar como concluído', 'btn--solid', p.length > 0),
            completed: b('bv', 'Registrar entrega') + b('bo', 'Reabrir manutenção', ''),
            delivered: '<p class="muted">Atendimento entregue. Nenhuma ação disponível.</p>',
            canceled: '<p class="muted">Atendimento cancelado. Nenhuma ação disponível.</p>'
        };

        return `
            <div class="acts">${A[s] || ''}${CANCELABLE.includes(s) ? b('bx', 'Cancelar atendimento', 'btn--danger') : ''}</div>

            ${s === 'in_progress' && p.length ? `
                <p class="pend" role="status">
                    Para concluir, defina “Executado” ou “Não executado” em: ${p.map(i => esc(i.description)).join(', ')}.
                </p>
            ` : ''}

            <div id="cfs" aria-live="polite"></div>
        `;
    }

    function items() {
        const b = T.split(a).cur;

        if (!b || b.status_budget !== 'approved') {
            return '<p class="muted">Os itens aparecem aqui depois que o cliente aprovar o orçamento.</p>';
        }

        const edit = a.status_attendance === 'in_progress';

        return `
            ${ui.table({
                caption: 'Itens do orçamento aprovado',
                rows: T.order(b.items || []),
                cols: [
                    { h: 'Tipo', c: i => esc(lbl('item_type', i.item_type)) },
                    { h: 'Descrição', c: i => `<span class="${i.id_service_item ? 'ind' : ''}">${esc(i.description)}</span>` },
                    { h: 'Qtd', cls: 'num', c: i => esc(String(i.quantity).replace('.', ',')) },
                    { h: 'Situação', c: i => !['service', 'product'].includes(i.item_type) ? '—' : edit
                        ? `<span class="exe" role="group" aria-label="Execução de ${esc(i.description)}">
                              <button type="button" data-x="${esc(i.id)}:executed" aria-pressed="${i.execution_status === 'executed'}">Executado</button>
                              <button type="button" data-x="${esc(i.id)}:not_executed" aria-pressed="${i.execution_status === 'not_executed'}">Não executado</button>
                           </span>`
                        : ui.badge('execution_status', i.execution_status || 'pending') }
                ]
            })}

            <p class="muted" style="font-size:.78rem;margin-top:8px">
                Ao concluir ou entregar, o histórico do veículo é gerado com os itens executados.
            </p>
        `;
    }

    function draw() {
        const c = a.client || {},
            v = a.vehicle || {},
            locked = LOCKED.includes(a.status_attendance),
            dd = (l, x) => `<div><dt>${l}</dt><dd>${x || x === 0 ? esc(x) : '—'}</dd></div>`;

        view.innerHTML = `
            <div class="wrap wrap--n ad">
                <a class="back-l" href="w-attendances.html">← Atendimentos</a>

                <section class="ad__h" aria-labelledby="ah">
                    <div class="hbar" style="margin:0">
                        <h1 id="ah">${esc(c.name || 'Cliente')}</h1>
                        <button type="button" class="btn btn--solid" id="bc">CHAT</button>
                    </div>

                    <p class="muted">${c.phone_number ? 'Telefone: ' + esc(c.phone_number) + ' · ' : ''}${esc(fm.date(a.date_attendance))}</p>

                    ${ui.stepper(a.status_attendance)}
                </section>

                <section class="sc">
                    <h2>Status</h2>
                    ${actions()}
                </section>

                <section class="sc">
                    <h2>Veículo</h2>

                    <dl class="dl2">
                        ${dd('Marca e modelo', (v.brand || '') + ' ' + (v.model || ''))}
                        ${dd('Versão', v.version)}
                        ${dd('Ano fabricação/modelo', v.year_fabrication ? v.year_fabrication + '/' + v.year_model : '')}
                        ${dd('Placa', fm.plate(v.plate))}
                        ${dd('Combustível', lbl('fuel', v.fuel))}
                        ${dd('Câmbio', lbl('exchange', v.exchange))}
                        ${dd('Motorização', v.motorization)}
                        ${dd('Cor', v.color)}
                        ${dd('Observações do veículo', v.information)}
                    </dl>

                    ${fm.photos(v).length ? `<div class="gal2s" style="margin-top:12px">${fm.photos(v).map((p, i) => `<img loading="lazy" src="${ui.url(p)}" alt="Foto ${i + 1} do veículo">`).join('')}</div>` : ''}
                </section>

                <section class="sc">
                    <h2>Informações técnicas</h2>

                    <form id="tf" novalidate>
                        <div class="fgrid">
                            ${form.fld({ id: 'mileage_km', label: 'Quilometragem (km)', value: a.mileage_km ?? '', attrs: `inputmode="numeric" ${locked ? 'disabled' : ''}` })}
                        </div>

                        ${form.fld({ id: 'observations', label: 'Observações técnicas (iniciadas com o pedido do cliente)', rows: 4, value: a.observations, attrs: `maxlength="1000" ${locked ? 'disabled' : ''}` })}

                        <p class="ferr" role="alert"></p>

                        ${locked ? '<p class="muted">Edição bloqueada: atendimento encerrado.</p>' : '<button class="btn btn--solid" id="bt">Salvar</button>'}
                    </form>
                </section>

                <section class="sc" id="exs" aria-labelledby="hi">
                    <h2 id="hi">Execução dos itens</h2>
                    ${items()}
                </section>

                <details class="pastb" id="hd">
                    <summary>Histórico do veículo</summary>
                    <div id="hb" aria-live="polite"><p class="muted">Abra para carregar.</p></div>
                </details>
            </div>
        `;

        $('#bc').onclick = async () => {
            try {
                const x = await SAM.api.chats.open(c.id);

                location.href = 'chat.html?id=' + encodeURIComponent(x.id);
            } catch (e) {
                SAM.toast(e.detail || 'Não foi possível abrir a conversa.');
            }
        };

        const ask = (idn, text, yes, st, danger) => {
            const el = $('#' + idn);

            if (el) el.onclick = e => ui.confirm($('#cfs'), { text, yes, danger, back: e.currentTarget, onYes: () => go(st) });
        };

        const direct = (idn, st) => {
            const el = $('#' + idn);

            if (el) {
                el.onclick = async () => {
                    el.disabled = true;

                    try {
                        await go(st);
                    } catch (e) {
                        el.disabled = false;
                        $('#cfs').innerHTML = `<p class="ferr" role="alert">${esc(e.detail)}</p>`;
                    }
                };
            }
        };

        direct('bs', 'in_progress');
        direct('bo', 'in_progress');
        ask('bd', 'Marcar este atendimento como concluído?', 'Sim, concluir', 'completed', false);
        ask('bv', 'Registrar a entrega do veículo? Esta ação é final.', 'Sim, registrar entrega', 'delivered', false);
        ask('bx', 'Cancelar este atendimento? O orçamento também será cancelado.', 'Sim, cancelar', 'canceled');

        form.wire($('#tf'), async () => {
            const km = $('#mileage_km').value.trim() ? V.int($('#mileage_km').value) : null;

            if (form.err('mileage_km', $('#mileage_km').value.trim() && !(km >= 0) ? 'Use só números (0 ou mais).' : '')) {
                form.focusBad($('#tf'));
                return;
            }

            const body = { observations: $('#observations').value.trim() };

            if (km != null) body.mileage_km = km;

            Object.assign(a, await SAM.api.workshop.updateAttendance(id, body));
            SAM.toast('Informações salvas.');
        }, { btn: '#bt', busy: 'Salvando…' });

        $('#exs').onclick = async e => {
            const b = e.target.closest('[data-x]');

            if (!b) return;

            const [item, st] = b.dataset.x.split(':'),
                bud = T.split(a).cur;

            b.disabled = true;

            try {
                await SAM.api.workshop.setExecution(bud.id, item, st);
                await reload();
            } catch (x) {
                SAM.toast(x.detail || 'Não foi possível atualizar o item.');
                b.disabled = false;
            }
        };

        $('#hd').addEventListener('toggle', async e => {
            if (!e.target.open || e.target.dataset.done) return;

            e.target.dataset.done = '1';

            try {
                const r = await SAM.api.workshop.vehicleHistory(v.id);

                $('#hb').innerHTML = r.results.length
                    ? `<ul class="tl">${r.results.map(h => `<li><span class="sb">${h.record_type === 'part' ? 'Peça' : 'Serviço'}</span> <b>${esc(fm.date(h.date_maintenance))}</b> · ${esc(h.description)}${h.mileage_km != null ? ' · ' + esc(SAM.km(h.mileage_km)) : ''}</li>`).join('')}</ul>`
                    : '<p class="muted">Sem registros no histórico.</p>';
            } catch (x) {
                e.target.dataset.done = '';

                $('#hb').innerHTML = `<p class="muted">${esc(x.status === 403 ? 'O cliente não autorizou o compartilhamento do histórico.' : x.detail)}</p>`;
            }
        });
    }

    ui.load(view, () => SAM.api.workshop.attendance(id), r => {
        a = r;
        draw();
    });
})();
