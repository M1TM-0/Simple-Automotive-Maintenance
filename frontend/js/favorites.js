(() => {
    /* T15 — Oficinas favoritas */

    const { $, esc, car, fm, lbl, ui } = SAM;

    if (!SAM.auth.require('client')) return;

    ui.title('FAVORITOS');

    const view = $('#view');

    let items = [], next = null;

    const wk = f => Object.assign({}, f, f.workshop || {}, { id: (f.workshop && f.workshop.id) ?? f.id_workshop ?? f.id });

    const card = f => {
        const w = wk(f);

        return `
            <article class="cd fav" data-w="${esc(w.id)}">
                <div class="fav__p">${w.photo_profile ? `<img src="${ui.url(w.photo_profile)}" alt="Foto de ${esc(w.name_fantasy)}">` : car('#e9e6df')}</div>

                <h2>${esc(w.name_fantasy)}</h2>

                <p class="muted">
                    ${w.rating_avg ? '★ ' + fm.stars(w.rating_avg) : 'Sem avaliações'}
                    ${w.type ? ' · ' + esc(lbl('type_establishment', w.type)) : ''}
                </p>

                <div class="acts">
                    <a class="btn" href="shop.html?id=${encodeURIComponent(w.id)}">Ver perfil</a>
                    <button type="button" class="btn btn--solid" data-chat="${esc(w.id)}">CHAT</button>
                    <button type="button" class="btn btn--danger" data-rm="${esc(w.id)}" aria-label="Remover ${esc(w.name_fantasy)} dos favoritos">♥ Remover</button>
                </div>
            </article>
        `;
    };

    function draw() {
        view.innerHTML = items.length ? `
            <div class="wrap">
                <h1 class="h1" id="fh" tabindex="-1">Oficinas favoritas</h1>
                <div class="cg" id="fl" aria-live="polite">${items.map(card).join('')}</div>
                ${next ? ui.moreBtn() : ''}
            </div>
        ` : `
            <div class="wrap">
                ${ui.emptyHtml({
                    title: 'Você ainda não favoritou oficinas',
                    text: 'Favorite oficinas pelo perfil delas para voltar rápido.',
                    cta: { href: 'map.html', label: 'Encontrar oficina' }
                })}
            </div>
        `;

        const m = $('[data-more]', view);

        if (m) {
            m.onclick = async () => {
                m.disabled = true;

                try {
                    const r = await SAM.api.favorites.list({ page: SAM.api.pageOf(next) });

                    items = items.concat(r.results);
                    next = r.next;
                    draw();
                } catch (e) {
                    SAM.toast(e.detail || 'Não foi possível carregar mais.');
                    m.disabled = false;
                }
            };
        }
    }

    view.addEventListener('click', async e => {
        const c = e.target.closest('[data-chat]'),
            r = e.target.closest('[data-rm]');

        if (c) {
            try {
                const x = await SAM.api.chats.open(c.dataset.chat);

                location.href = 'chat.html?id=' + encodeURIComponent(x.id);
            } catch (x) {
                SAM.toast(x.detail || 'Não foi possível abrir a conversa.');
            }
        }

        if (r) {
            r.disabled = true;

            try {
                await SAM.api.favorites.remove(r.dataset.rm);
                items = items.filter(f => String(wk(f).id) !== r.dataset.rm);
                draw();
                SAM.toast('Removida dos favoritos');

                const h = $('#fh');

                if (h) h.focus();
            } catch (x) {
                SAM.toast(x.detail || 'Não foi possível remover.');
                r.disabled = false;
            }
        }
    });

    ui.load(view, () => SAM.api.favorites.list(), r => {
        items = r.results;
        next = r.next;
        draw();
    });
})();
