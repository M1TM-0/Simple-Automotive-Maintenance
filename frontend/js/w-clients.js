(() => {
    /* T26 — Clientes e veículos atendidos (somente leitura, RN03). Não cadastra clientes nem veículos. */

    const { $, esc, I, fm, ui } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('CLIENTES');

    const view = $('#view');

    let items = [], q = '';

    const rows = () => items.filter(c =>
        (c.name + ' ' + (c.vehicles || []).map(v => v.plate + ' ' + fm.plate(v.plate)).join(' ')).toLowerCase().includes(q)
    );

    function list() {
        const r = rows();

        $('#cl').innerHTML = r.length ? r.map(c => `
            <details class="pastb" data-c="${esc(c.id)}">
                <summary>
                    <b>${esc(c.name)}</b>
                    · ${c.attendance_count} ${c.attendance_count === 1 ? 'atendimento' : 'atendimentos'}
                    · último em ${esc(fm.date(c.last_attendance))}
                    <span class="muted"> — ${(c.vehicles || []).map(v => esc(v.model + ' ' + fm.plate(v.plate))).join(', ')}</span>
                </summary>

                <div data-b aria-live="polite"><p class="muted">Abra para ver os veículos.</p></div>
            </details>
        `).join('') : '<p class="empty">Nenhum cliente encontrado.</p>';
    }

    /* veículos de um cliente: atendimentos com a oficina e "Ver histórico" (403 → mensagem) */

    async function vehicles(d) {
        const box = $('[data-b]', d);

        box.innerHTML = '<p class="muted" role="status">Carregando…</p>';

        try {
            const r = await SAM.api.workshop.clientVehicles(d.dataset.c);

            d.dataset.done = '1';

            box.innerHTML = r.results.map(v => `
                <section class="cv" data-v="${esc(v.id)}">
                    <h3>${esc(v.brand + ' ' + v.model)} <span class="plate">${esc(fm.plate(v.plate))}</span></h3>

                    <ul class="tl">
                        ${(v.attendances || []).map(a => `
                            <li>${esc(fm.date(a.date_attendance))} · ${ui.badge('status_attendance', a.status_attendance)}
                                · <a href="w-attendance.html?id=${encodeURIComponent(a.id)}">Ver atendimento</a></li>
                        `).join('') || '<li class="muted">Sem atendimentos.</li>'}
                    </ul>

                    <button type="button" class="btn" data-h="${esc(v.id)}" aria-expanded="false">Ver histórico</button>
                    <div data-hb aria-live="polite"></div>
                </section>
            `).join('') || '<p class="muted">Nenhum veículo encontrado.</p>';
        } catch (e) {
            box.innerHTML = `<p class="ferr" role="alert">${esc(e.status === 403 ? 'O cliente não autorizou o compartilhamento do histórico.' : e.detail)}</p>`;
        }
    }

    async function history(b) {
        const host = b.parentElement.querySelector('[data-hb]'),
            open = b.getAttribute('aria-expanded') === 'true';

        if (open) {
            host.innerHTML = '';
            b.setAttribute('aria-expanded', 'false');
            return;
        }

        b.setAttribute('aria-expanded', 'true');
        host.innerHTML = '<p class="muted" role="status">Carregando…</p>';

        try {
            host.innerHTML = ui.historyList((await SAM.api.workshop.vehicleHistory(b.dataset.h)).results);
        } catch (e) {
            host.innerHTML = `<p class="ferr" role="alert">${esc(e.status === 403 ? 'O cliente não autorizou o compartilhamento do histórico.' : e.detail)}</p>`;
        }
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap">
                ${ui.subnav('clients')}

                <h1 class="h1">Clientes e veículos atendidos</h1>

                <p class="note1">Somente leitura: os clientes e veículos aparecem aqui a partir dos atendimentos da sua oficina.</p>

                <label class="search" style="max-width:420px">
                    <span class="sr">Buscar por nome ou placa</span>
                    ${I.s}
                    <input id="q" placeholder="Buscar por nome ou placa">
                </label>

                <div id="cl" style="margin-top:14px" aria-live="polite"></div>
            </div>
        `;

        if (!items.length) {
            $('#cl').innerHTML = '<p class="empty">Você ainda não tem clientes atendidos.</p>';
            return;
        }

        list();

        $('#q').oninput = e => {
            q = e.target.value.trim().toLowerCase();
            list();
        };

        $('#cl').addEventListener('toggle', e => {
            if (e.target.open && !e.target.dataset.done) vehicles(e.target);
        }, true);

        $('#cl').addEventListener('click', e => {
            const b = e.target.closest('[data-h]');

            if (b) history(b);
        });
    }

    ui.load(view, () => SAM.api.workshop.clients(), r => {
        items = r.results;
        draw();
    });
})();
