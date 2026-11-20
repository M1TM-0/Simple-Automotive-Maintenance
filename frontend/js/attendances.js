(() => {
    /* T13 — Meus atendimentos (Cliente) */

    const { $, $$, esc, I, fm, ui } = SAM;

    if (!SAM.auth.require('client')) return;

    ui.title('MEUS ATENDIMENTOS');

    const view = $('#view'),
        G = [['andamento', 'Em andamento'], ['entregues', 'Entregues'], ['cancelados', 'Cancelados']];

    let items = [], next = null, grp = 'andamento', q = '';

    const total = a => {
        const b = a.budget || ((a.budgets || []).find(x => ['pending', 'approved'].includes(x.status_budget)));

        return b && b.total_price != null ? fm.money(b.total_price) : '';
    };

    const card = a => `
        <a class="cd att" href="attendance.html?id=${encodeURIComponent(a.id)}">
            <div class="att__top">
                <h2>${esc((a.workshop && a.workshop.name_fantasy) || 'Oficina')}</h2>
                ${ui.badge('status_attendance', a.status_attendance)}
            </div>

            <p>
                ${esc(a.vehicle ? a.vehicle.brand + ' ' + a.vehicle.model : '')}
                ${a.vehicle ? `<span class="plate">${esc(fm.plate(a.vehicle.plate))}</span>` : ''}
            </p>

            <p class="muted">${esc(fm.date(a.date_attendance))}</p>

            ${ui.miniStepper(a.status_attendance)}

            ${total(a) ? `<p class="att__t">${total(a)}</p>` : ''}

            ${a.status_attendance === 'waiting_approval' ? '<p class="att__w" role="status">Orçamento aguardando sua resposta</p>' : ''}
        </a>
    `;

    const rows = () => items.filter(a =>
        SAM.GROUPS[grp].includes(a.status_attendance) &&
        ((a.workshop ? a.workshop.name_fantasy : '') + ' ' + (a.vehicle ? a.vehicle.plate + ' ' + fm.plate(a.vehicle.plate) : '')).toLowerCase().includes(q)
    );

    function list() {
        const r = rows();

        $('#al').innerHTML = r.length
            ? r.map(card).join('')
            : '<p class="empty" style="grid-column:1/-1">Nenhum atendimento nesta lista.</p>';

        $('#more').innerHTML = next ? ui.moreBtn() : '';

        const b = $('[data-more]', view);

        if (b) b.onclick = () => load(false);
    }

    /* o filtro por grupo vai para a API (status=a,b,c); a busca é local */

    async function load(reset) {
        const b = $('[data-more]', view);

        if (b) b.disabled = true;

        try {
            const r = await SAM.api.attendances.list({
                status: SAM.GROUPS[grp].join(','),
                page: reset ? 1 : SAM.api.pageOf(next)
            });

            items = reset ? r.results : items.concat(r.results);
            next = r.next;
            list();
        } catch (e) {
            if (reset) ui.fail($('#al'), e, () => load(true));
            else {
                SAM.toast(e.detail || 'Não foi possível carregar mais.');

                if (b) b.disabled = false;
            }
        }
    }

    async function first(r) {
        items = r.results;
        next = r.next;

        /* "em andamento" vazio não significa "nenhum atendimento": confere sem filtro de status */

        let any = items.length > 0;

        if (!any) {
            try {
                any = (await SAM.api.attendances.list({})).results.length > 0;
            } catch (e) {
                any = true;
            }
        }

        if (!any) {
            view.innerHTML = `<div class="wrap">${ui.emptyHtml({
                title: 'Você ainda não solicitou atendimentos',
                text: 'Encontre uma oficina e solicite um atendimento pelo perfil dela.',
                cta: { href: 'map.html', label: 'Encontrar oficina' }
            })}</div>`;

            return;
        }

        view.innerHTML = `
            <div class="wrap">
                <div class="hbar">
                    <h1 class="h1">Meus atendimentos</h1>
                    <a class="btn btn--solid" href="map.html">Novo atendimento</a>
                </div>

                <label class="search" style="max-width:420px">
                    <span class="sr">Buscar por oficina ou placa</span>
                    ${I.s}
                    <input id="q" placeholder="Buscar por oficina ou placa">
                </label>

                <div class="chips" role="group" aria-label="Filtrar atendimentos">
                    ${G.map(([k, l]) => `<button type="button" class="chip" data-g="${k}" aria-pressed="${k === grp}">${l}</button>`).join('')}
                </div>

                <div class="cg" id="al" aria-live="polite"></div>
                <div id="more"></div>
            </div>
        `;

        list();

        $('#q').oninput = e => {
            q = e.target.value.trim().toLowerCase();
            list();
        };

        $('.chips', view).onclick = e => {
            const c = e.target.closest('[data-g]');

            if (!c || c.dataset.g === grp) return;

            grp = c.dataset.g;
            $$('[data-g]', view).forEach(x => x.setAttribute('aria-pressed', x === c));
            ui.loading($('#al'), 2);
            load(true);
        };
    }

    ui.load(view, () => SAM.api.attendances.list({ status: SAM.GROUPS[grp].join(',') }), first);
})();
