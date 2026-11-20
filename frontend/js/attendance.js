(() => {
    /* T14 — Detalhe do atendimento (Cliente): stepper, orçamento, aprovar/recusar, cancelar, avaliar */

    const { $, esc, fm, ui } = SAM,
        T = SAM.att;

    if (!SAM.auth.require('client')) return;

    ui.title('ATENDIMENTO');

    const id = new URLSearchParams(location.search).get('id'),
        view = $('#view');

    let a;

    const CANCELABLE = ['requested', 'budgeted', 'waiting_approval', 'approved', 'in_progress'];

    async function chat() {
        try {
            const c = await SAM.api.chats.open(a.workshop.id);

            location.href = 'chat.html?id=' + encodeURIComponent(c.id);
        } catch (e) {
            SAM.toast(e.detail || 'Não foi possível abrir a conversa.');
        }
    }

    const refresh = async () => {
        try {
            a = await SAM.api.attendances.get(id);
            draw();
        } catch (e) {
            SAM.toast(e.detail || 'Não foi possível atualizar.');
        }
    };

    function budgetHtml(cur) {
        if (!cur) {
            return `<p class="muted">${a.status_attendance === 'canceled'
                ? 'Este atendimento foi cancelado.'
                : 'A oficina ainda não enviou um orçamento.'}</p>`;
        }

        const exec = ['in_progress', 'completed', 'delivered'].includes(a.status_attendance);

        return `
            <p>${ui.badge('status_budget', cur.status_budget)}
                <small class="muted">${esc(T.validity(cur))}</small></p>

            ${T.table(cur.items || [], exec)}

            <div class="btot"><span>Total</span><b>${fm.money(cur.total_price)}</b></div>

            ${cur.observations ? `<p class="muted" style="margin-top:8px">Observações da oficina: ${esc(cur.observations)}</p>` : ''}
        `;
    }

    function draw() {
        const { cur, past } = T.split(a),
            canAnswer = a.status_attendance === 'waiting_approval' && cur && cur.status_budget === 'pending' && !T.expired(cur),
            w = a.workshop || {},
            v = a.vehicle || {};

        view.innerHTML = `
            <div class="wrap wrap--n ad">
                <a class="back-l" href="attendances.html">← Meus atendimentos</a>

                <section class="ad__h" aria-labelledby="ah">
                    <div class="hbar" style="margin:0">
                        <h1 id="ah"><a href="shop.html?id=${encodeURIComponent(w.id)}">${esc(w.name_fantasy || 'Oficina')}</a></h1>

                        <div class="row">
                            <button type="button" class="btn btn--solid" id="bc">CHAT</button>
                            <button type="button" class="btn" id="bu">Atualizar</button>
                        </div>
                    </div>

                    <dl class="dl2">
                        <div><dt>Veículo</dt><dd><a href="vehicle.html?id=${encodeURIComponent(v.id)}">${esc((v.brand || '') + ' ' + (v.model || ''))}</a> <span class="plate">${esc(fm.plate(v.plate))}</span></dd></div>
                        <div><dt>Data</dt><dd>${esc(fm.date(a.date_attendance))}</dd></div>
                        <div><dt>Quilometragem informada</dt><dd>${a.mileage_km != null ? esc(SAM.km(a.mileage_km)) : '—'}</dd></div>
                        <div><dt>Observações enviadas</dt><dd>${esc(a.observations || '—')}</dd></div>
                    </dl>

                    ${ui.stepper(a.status_attendance)}
                </section>

                <section class="sc">
                    <h2>Orçamento</h2>
                    ${budgetHtml(cur)}

                    ${canAnswer ? `
                        <div class="acts" style="margin-top:12px">
                            <button type="button" class="btn btn--solid" id="ba">Aprovar orçamento</button>
                            <button type="button" class="btn btn--danger" id="br">Recusar orçamento</button>
                        </div>
                    ` : ''}

                    <div id="cfa" aria-live="polite"></div>
                </section>

                ${past.length ? `
                    <section aria-label="Orçamentos anteriores">
                        <h2 class="h2" style="font-size:.95rem;margin-bottom:8px">Orçamentos anteriores</h2>

                        ${past.map(b => `
                            <details class="pastb">
                                <summary>${esc(SAM.lbl('status_budget', b.status_budget))} · ${fm.money(b.total_price)}</summary>
                                ${T.table(b.items || [], false)}
                            </details>
                        `).join('')}
                    </section>
                ` : ''}

                ${a.status_attendance === 'delivered' ? `
                    <section class="sc" id="rv">
                        <h2>Avaliação</h2>

                        ${a.review
                            ? `<p><span class="st" role="img" aria-label="${a.review.rating} de 5">${'★'.repeat(a.review.rating)}${'☆'.repeat(5 - a.review.rating)}</span></p>
                               ${a.review.comment ? `<p>${esc(a.review.comment)}</p>` : ''}
                               ${a.review.workshop_response ? `<blockquote class="cm"><b>Resposta da oficina:</b> ${esc(a.review.workshop_response)}</blockquote>` : ''}`
                            : '<button type="button" class="btn btn--solid" id="bv">Avaliar atendimento</button>'}
                    </section>
                ` : ''}

                <div class="acts">
                    <a class="btn" href="vehicle.html?id=${encodeURIComponent(v.id)}">Ver no histórico do veículo</a>
                    ${CANCELABLE.includes(a.status_attendance) ? '<button type="button" class="btn btn--danger" id="bx">Cancelar atendimento</button>' : ''}
                </div>

                <div id="cfx" aria-live="polite"></div>
            </div>
        `;

        $('#bc').onclick = chat;
        $('#bu').onclick = refresh;

        const ask = (host, text, yes, fn, back) => ui.confirm($(host), {
            text, yes, back,
            onYes: async () => {
                await fn();
                await refresh();
            }
        });

        if (canAnswer) {
            $('#ba').onclick = e => ask('#cfa', 'Aprovar este orçamento? A oficina poderá iniciar a manutenção.', 'Sim, aprovar', () => SAM.api.budgets.approve(cur.id), e.currentTarget);
            $('#br').onclick = e => ask('#cfa', 'Recusar este orçamento?', 'Sim, recusar', () => SAM.api.budgets.reject(cur.id), e.currentTarget);
        }

        const bx = $('#bx');

        if (bx) bx.onclick = e => ask('#cfx', 'Cancelar este atendimento? O orçamento também será cancelado.', 'Sim, cancelar', () => SAM.api.attendances.cancel(id), e.currentTarget);

        const bv = $('#bv');

        if (bv) bv.onclick = () => ui.reviewAttendance((T.split(a).cur || (a.budgets || []).find(b => b.status_budget === 'approved') || {}).id, refresh);
    }

    ui.load(view, () => SAM.api.attendances.get(id), r => {
        a = r;

        /* o orçamento aprovado fica no atendimento entregue: garante id_budget para M02 */

        draw();
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && a) refresh();
    });
})();
