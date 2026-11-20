(() => {
    /* T18 — Atendimentos da oficina: contadores-filtro, Quadro e Lista. Sem arrastar-e-soltar. */

    const { $, $$, esc, I, fm, ui } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('ATENDIMENTOS');

    const view = $('#view');

    const CNT = [
        ['new', 'Novas solicitações', ['requested']],
        ['wait', 'Aguardando aprovação', ['waiting_approval']],
        ['work', 'Em manutenção', ['approved', 'in_progress']],
        ['ready', 'Prontos para entrega', ['completed']]
    ];

    const COLS = [
        ['Solicitados', ['requested', 'budgeted']],
        ['Aguardando aprovação', ['waiting_approval']],
        ['Aprovados e em manutenção', ['approved', 'in_progress']],
        ['Concluídos', ['completed']],
        ['Entregues', ['delivered']]
    ];

    let items = [], cnt = '', q = '', tab = 'b', sig = '';

    const total = a => {
        const b = a.budget || (a.budgets || []).find(x => ['pending', 'approved'].includes(x.status_budget));

        return a.total_price != null ? a.total_price : b ? b.total_price : null;
    };

    const vl = a => a.vehicle ? `${a.vehicle.brand} ${a.vehicle.model} · ${fm.plate(a.vehicle.plate)}` : '';

    const shown = () => {
        const c = CNT.find(x => x[0] === cnt);

        return items.filter(a =>
            (!c || c[2].includes(a.status_attendance)) &&
            ((a.client ? a.client.name : '') + ' ' + (a.vehicle ? a.vehicle.plate + ' ' + fm.plate(a.vehicle.plate) : '')).toLowerCase().includes(q)
        );
    };

    const kc = a => `
        <a class="kc" href="w-attendance.html?id=${encodeURIComponent(a.id)}">
            <b>${esc(a.client ? a.client.name : 'Cliente')}</b>
            <span>${esc(vl(a))}</span>
            <span class="muted">${esc(fm.date(a.date_attendance))}</span>
            <span>${ui.badge('status_attendance', a.status_attendance)}</span>
            ${total(a) != null ? `<span class="att__t">${fm.money(total(a))}</span>` : ''}
        </a>
    `;

    function body() {
        const r = shown();

        if (tab === 'b') {
            $('#pn').innerHTML = `
                <div class="board">
                    ${COLS.map(([t, st]) => {
                        const l = r.filter(a => st.includes(a.status_attendance));

                        return `
                            <section class="col" aria-label="${esc(t)}">
                                <h2><span>${esc(t)}</span><span>${l.length}<span class="sr"> atendimentos</span></span></h2>
                                ${l.length ? l.map(kc).join('') : '<p class="kc kc--0">Nenhum atendimento aqui</p>'}
                            </section>
                        `;
                    }).join('')}
                </div>
            `;
        } else {
            $('#pn').innerHTML = r.length ? ui.table({
                caption: 'Atendimentos da oficina',
                rowHead: true,
                rows: r,
                cols: [
                    { h: 'Cliente', c: a => `<a href="w-attendance.html?id=${encodeURIComponent(a.id)}">${esc(a.client ? a.client.name : 'Cliente')}</a>` },
                    { h: 'Veículo', c: a => esc(vl(a)) },
                    { h: 'Data', c: a => esc(fm.date(a.date_attendance)) },
                    { h: 'Status', c: a => ui.badge('status_attendance', a.status_attendance) },
                    { h: 'Total', cls: 'num', c: a => total(a) != null ? fm.money(total(a)) : '—' }
                ]
            }) : '<p class="empty">Nenhum atendimento aqui</p>';
        }

        CNT.forEach(([k, , st]) => {
            const n = $(`[data-c="${k}"] b`, view);

            if (n) n.textContent = items.filter(a => st.includes(a.status_attendance)).length;
        });
    }

    async function load() {
        const r = await SAM.api.workshop.attendances();

        /* só redesenha se algo mudou (polling a cada 30 s) */

        const s = JSON.stringify(r.results.map(a => [a.id, a.status_attendance, total(a)]));

        if (s === sig) return;

        sig = s;
        items = r.results;

        if ($('#pn')) body();
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap">
                <h1 class="h1">Atendimentos</h1>

                <div class="cnts" role="group" aria-label="Filtrar por situação">
                    ${CNT.map(([k, l]) => `
                        <button type="button" class="cnt" data-c="${k}" aria-pressed="${k === cnt}">
                            <b>0</b><span>${l}</span>
                        </button>
                    `).join('')}
                </div>

                <label class="search" style="max-width:420px">
                    <span class="sr">Buscar por cliente ou placa</span>
                    ${I.s}
                    <input id="q" placeholder="Buscar por cliente ou placa">
                </label>

                <div class="tabs" role="tablist" aria-label="Visualização">
                    <i></i>
                    <button role="tab" id="tb-b" data-tab="b" aria-selected="true" aria-controls="pn">Quadro</button>
                    <button role="tab" id="tb-l" data-tab="l" aria-selected="false" aria-controls="pn" tabindex="-1">Lista</button>
                </div>

                <div id="pn" role="tabpanel" aria-live="polite"></div>
            </div>
        `;

        body();

        $('.cnts', view).onclick = e => {
            const b = e.target.closest('[data-c]');

            if (!b) return;

            cnt = cnt === b.dataset.c ? '' : b.dataset.c;
            $$('[data-c]', view).forEach(x => x.setAttribute('aria-pressed', x.dataset.c === cnt));
            body();
        };

        $('#q').oninput = e => {
            q = e.target.value.trim().toLowerCase();
            body();
        };

        ui.tabs($('.tabs', view), k => {
            tab = k;
            $('#pn').setAttribute('aria-labelledby', 'tb-' + k);
            body();
        }).select(tab);
    }

    ui.load(view, () => SAM.api.workshop.attendances(), r => {
        items = r.results;
        sig = JSON.stringify(items.map(a => [a.id, a.status_attendance, total(a)]));
        draw();

        ui.poll(load, 30000, { wait: true });
    });
})();
