(() => {
    /* T08 — Notificações (Cliente e Oficina). Sem links, a menos que a API devolva `url`. */

    const { $, esc, fm, ui } = SAM;

    if (!SAM.auth.require()) return;

    ui.title('NOTIFICAÇÕES');

    const view = $('#view');

    let items = [], next = null, only = false;

    /* link só se a API mandar `url` e for uma página do projeto (mesmo filtro do ?next=) */

    const target = n => /^[a-z-]+\.html(\?[\w=&.-]*)?$/.test(n.url || '') ? n.url : '';

    const item = n => `
        <li class="${n.read_status ? '' : 'is-new'}">
            <button type="button" class="nt" data-id="${esc(n.id)}" data-u="${esc(target(n))}">
                ${n.read_status ? '' : '<span class="nt__d" aria-hidden="true"></span><span class="sr">Não lida. </span>'}
                <b>${esc(n.title)}</b>
                <span>${esc(n.message)}</span>
                <small class="muted">${esc(fm.rel(n.date_creation))}</small>
            </button>
        </li>
    `;

    function list() {
        $('#nl').innerHTML = items.length
            ? items.map(item).join('')
            : `<li class="empty">${only ? 'Você não tem notificações não lidas.' : 'Você não tem notificações'}</li>`;

        $('#more').innerHTML = next ? ui.moreBtn() : '';

        const b = $('[data-more]', view);

        if (b) b.onclick = () => load(false);
    }

    async function load(reset) {
        const b = $('[data-more]', view);

        if (b) b.disabled = true;

        try {
            const r = await SAM.api.notifications.list({ unread: only ? true : '', page: reset ? 1 : SAM.api.pageOf(next) });

            items = reset ? r.results : items.concat(r.results);
            next = r.next;
            list();
        } catch (e) {
            if (reset) ui.fail($('#nl'), e, () => load(true));
            else {
                SAM.toast(e.detail || 'Não foi possível carregar mais.');

                if (b) b.disabled = false;
            }
        }
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap wrap--n">
                <div class="hbar">
                    <h1 class="h1">Notificações</h1>
                    <button type="button" class="btn" id="ra">Marcar todas como lidas</button>
                </div>

                <div class="chips" role="group" aria-label="Filtrar notificações">
                    <button type="button" class="chip" data-f="all" aria-pressed="${!only}">Todas</button>
                    <button type="button" class="chip" data-f="unread" aria-pressed="${only}">Não lidas</button>
                </div>

                <ul class="nl" id="nl" aria-live="polite"></ul>
                <div id="more"></div>
            </div>
        `;

        list();

        $('.chips', view).onclick = e => {
            const c = e.target.closest('[data-f]');

            if (!c) return;

            only = c.dataset.f === 'unread';
            view.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', x === c));
            ui.loading($('#nl'), 2);
            load(true);
        };

        $('#ra').onclick = async e => {
            const btn = e.currentTarget;

            btn.disabled = true;

            try {
                await SAM.api.notifications.readAll();
                await load(true);
                ui.bellRefresh();
                SAM.toast('Todas marcadas como lidas.');
            } catch (x) {
                SAM.toast(x.detail || 'Não foi possível concluir.');
            }

            btn.disabled = false;
        };

        $('#nl').onclick = async e => {
            const b = e.target.closest('[data-id]');

            if (!b) return;

            const n = items.find(x => String(x.id) === b.dataset.id);

            if (n && !n.read_status) {
                try {
                    await SAM.api.notifications.read(n.id);
                    n.read_status = true;
                    b.closest('li').classList.remove('is-new');
                    b.querySelectorAll('.nt__d, .sr').forEach(x => x.remove());
                    ui.bellRefresh();
                } catch (x) {
                    SAM.toast(x.detail || 'Não foi possível marcar como lida.');
                    return;
                }
            }

            if (b.dataset.u) location.href = b.dataset.u;
        };
    }

    ui.load(view, () => SAM.api.notifications.list({}), r => {
        items = r.results;
        next = r.next;
        draw();
    });
})();
