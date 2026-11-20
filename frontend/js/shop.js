(() => {
    /* T06 — Perfil público da oficina (?id=). Avaliações: somente leitura (nascem em M02). */

    const { $, $$, esc, I, car, fm, lbl, ui } = SAM;

    const id = new URLSearchParams(location.search).get('id'),
        view = $('#view'),
        user = SAM.auth.user(),
        isClient = !!user && user.role === 'client',
        here = 'shop.html?id=' + encodeURIComponent(id || ''),
        login = 'login.html?next=' + encodeURIComponent(here);

    let w;

    const stars = n => `<span class="st" role="img" aria-label="${n} de 5">${'★'.repeat(n)}${'☆'.repeat(5 - n)}</span>`;

    /* ---------- horário e "aberto agora" ---------- */

    const hhmm = t => String(t).slice(0, 5);

    function hoursHtml() {
        const by = {};

        w.operation_hours.forEach(h => {
            (by[h.day_of_week] = by[h.day_of_week] || []).push(hhmm(h.opening_time) + '–' + hhmm(h.closing_time));
        });

        if (!w.operation_hours.length) return 'Não informado';

        return `<ul class="hl">${[1, 2, 3, 4, 5, 6, 7].map(d => `
            <li><span>${esc(lbl('day_of_week', d).slice(0, 3))}</span> ${by[d] ? esc(by[d].join(', ')) : 'Fechado'}</li>
        `).join('')}</ul>`;
    }

    function openNow() {
        if (typeof w.is_open_now === 'boolean') return w.is_open_now;

        if (!w.operation_hours.length) return null;

        const d = new Date(),
            iso = d.getDay() === 0 ? 7 : d.getDay(),
            t = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');

        return w.operation_hours.some(h => h.day_of_week === iso && hhmm(h.opening_time) <= t && t < hhmm(h.closing_time));
    }

    /* ---------- ações ---------- */

    async function chat(ask) {
        try {
            const c = await SAM.api.chats.open(w.id);

            location.href = 'chat.html?id=' + encodeURIComponent(c.id) + (ask ? '&ask=' + encodeURIComponent(ask) : '');
        } catch (e) {
            SAM.toast(e.detail || 'Não foi possível abrir a conversa.');
        }
    }

    const owner = () => !!user && user.role === 'workshop' && (w.is_owner === true || String(user.id) === String(w.id));

    function actions() {
        const route = w.latitude != null && w.longitude != null
            ? w.latitude + ',' + w.longitude
            : w.address;

        const rt = route ? `
            <a class="btn" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(route)}">ROTA</a>
        ` : '';

        if (owner()) {
            return `${rt}<a class="btn btn--solid" href="w-profile.html">Editar perfil</a>`;
        }

        if (!user) {
            return `
                ${rt}
                <a class="btn btn--solid" href="${login}">CHAT</a>
                <a class="btn" href="${login}">SOLICITAR ATENDIMENTO</a>
                <a class="btn" href="${login}">♥ Favoritar</a>
            `;
        }

        if (!isClient) return rt;

        return `
            ${rt}
            <button type="button" class="btn btn--solid" id="bc">CHAT</button>
            <button type="button" class="btn" id="br">SOLICITAR ATENDIMENTO</button>
            <button type="button" class="btn" id="bf" aria-pressed="${!!w.is_favorite}">
                ${w.is_favorite ? '♥ Favoritado' : '♡ Favoritar'}
            </button>
        `;
    }

    /* ---------- abas ---------- */

    const TAB = {
        s() {
            const l = w.services.filter(s => s.disponibility !== false);

            $('#tp').innerHTML = l.length
                ? `<div class="parts">${l.map(s => `
                    <article class="part">
                        <b>${esc(s.name)}</b>
                        ${s.description ? `<span class="muted" style="font-size:.78rem">${esc(s.description)}</span>` : ''}
                        <em>a partir de ${fm.money(s.price_base)}${s.duration_estimate ? ' · ' + esc(fm.dur(s.duration_estimate)) : ''}</em>
                    </article>`).join('')}</div>`
                : '<p class="empty">Esta oficina ainda não divulgou serviços.</p>';
        },

        p() {
            ui.load($('#tp'), () => SAM.api.workshops.promotions(w.id), r => {
                $('#tp').innerHTML = r.results.length
                    ? `<div class="cg">${r.results.map(p => ui.promoCard(p, { workshop_id: w.id })).join('')}</div>`
                    : '<p class="empty">Nenhuma promoção vigente.</p>';
            });
        },

        r() {
            ui.load($('#tp'), () => SAM.api.workshops.reviews(w.id), r => {
                $('#tp').innerHTML = `
                    <p class="muted" style="font-size:.75rem;margin:0 4px 8px">
                        A avaliação é liberada depois de um atendimento entregue.
                    </p>

                    ${r.results.length ? r.results.map(c => `
                        <div class="cm">
                            ${ui.canReport() ? `<button type="button" data-rep="review:${esc(c.id)}">Denunciar</button>` : ''}
                            <b>${esc(c.client_name || 'Cliente')}</b>
                            ${stars(c.rating)}
                            <small class="muted">${esc(fm.date(c.date_creation))}</small>
                            ${c.comment ? `<p>${esc(c.comment)}</p>` : ''}
                            ${c.workshop_response ? `<blockquote><b>Resposta da oficina:</b> ${esc(c.workshop_response)}</blockquote>` : ''}
                        </div>
                    `).join('') : '<p class="empty">Ainda não há avaliações nesta oficina.</p>'}
                `;
            });
        },

        l() {
            ui.load($('#tp'), () => SAM.api.workshops.products(w.id), r => {
                const l = r.results.filter(p => p.active !== false);

                $('#tp').innerHTML = `
                    <p class="note">
                        Catálogo informativo: estes itens estão disponíveis na própria oficina.
                        A compra é combinada pelo chat, não pelo SAM.
                    </p>

                    ${l.length ? `<div class="parts">${l.map(p => `
                        <article class="part">
                            ${p.photo ? `<img class="part__i" loading="lazy" src="${ui.url(p.photo)}" alt="Foto de ${esc(p.name)}">` : ''}
                            <b>${esc(p.name)}</b>
                            <span class="muted" style="font-size:.76rem">${esc([p.brand, p.category].filter(Boolean).join(' · '))}</span>
                            <em>${fm.money(p.price)} · ${p.disponibility ? 'Disponível' : 'Indisponível'}</em>
                            ${isClient ? `<button class="btn" data-ask="${esc(p.name)}">Perguntar no chat</button>` : !user ? `<a class="btn" href="${login}">Perguntar no chat</a>` : ''}
                        </article>`).join('')}</div>`
                        : '<p class="empty">Esta oficina ainda não cadastrou itens no catálogo.</p>'}
                `;
            });
        },

        g() {
            $('#tp').innerHTML = `<div class="gal2s">${w.gallery.map((g, i) =>
                `<img loading="lazy" src="${ui.url(g.url || g)}" alt="Foto ${i + 1} de ${esc(w.name_fantasy)}">`).join('')}</div>`;
        }
    };

    function draw() {
        const rc = w.rating_count || 0,
            op = openNow(),
            cats = [...new Set(w.services.map(s => s.category_name).filter(Boolean))],
            tabs = [['s', 'Serviços'], ['p', 'Promoções'], ['r', 'Avaliações'], ['l', 'Shop local']];

        if (w.gallery.length) tabs.push(['g', 'Galeria']);

        ui.title(w.name_fantasy);

        view.innerHTML = `
            <div class="cover">
                ${w.photo_banner ? `<img src="${ui.url(w.photo_banner)}" alt="Banner de ${esc(w.name_fantasy)}">` : car('#d9d4c8')}
            </div>

            <div class="sh">
                <div class="av">
                    ${w.photo_profile ? `<img src="${ui.url(w.photo_profile)}" alt="Foto de ${esc(w.name_fantasy)}">` : car('#e9e6df')}
                </div>

                <div>
                    <div class="top">
                        <div>
                            <h1>${esc(w.name_fantasy)}</h1>

                            <p style="font-style:italic">
                                ${w.rating_avg ? `★ ${fm.stars(w.rating_avg)} (${rc} ${rc === 1 ? 'avaliação' : 'avaliações'})` : 'Sem avaliações ainda'}
                            </p>
                        </div>

                        <div class="row" id="acts">${actions()}</div>
                    </div>

                    <p class="muted" style="margin-top:8px;max-width:70ch;font-size:.85rem">
                        ${esc(w.description || 'Peça um orçamento ou agende pelo chat.')}
                    </p>
                </div>

                <dl class="info">
                    <div>
                        <dt>${I.clock}Horário</dt>
                        <dd>
                            ${op === null ? '' : `<b>${op ? 'Aberto agora' : 'Fechado agora'}</b>`}
                            ${hoursHtml()}
                        </dd>
                    </div>

                    <div>
                        <dt>${I.pin}Endereço</dt>
                        <dd>${esc(w.address || 'Não informado')}</dd>
                    </div>

                    <div>
                        <dt><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2"/></svg>Telefone</dt>
                        <dd>${esc(w.phone_number || 'Não informado')}</dd>
                    </div>

                    <div>
                        <dt>${I.tool}Serviços</dt>
                        <dd>${esc(cats.join(', ') || 'Não informado')}</dd>
                    </div>
                </dl>

                <div>
                    <div class="tabs" role="tablist" aria-label="Seções da oficina">
                        <i></i>
                        ${tabs.map(([k, l]) => `<button role="tab" id="t-${k}" data-tab="${k}" aria-selected="false" aria-controls="tp" tabindex="-1">${l}</button>`).join('')}
                    </div>

                    <div id="tp" role="tabpanel" aria-live="polite"></div>
                </div>
            </div>
        `;

        const T = ui.tabs($('.tabs', view), (k, b) => {
            $('#tp').setAttribute('aria-labelledby', b.id);
            TAB[k]();
        });

        T.select('s');

        ui.bindReport($('#tp'));

        $('#tp').addEventListener('click', e => {
            const a = e.target.closest('[data-ask]');

            if (a) chat(a.dataset.ask);
        });

        if (isClient) {
            $('#bc').onclick = () => chat();
            $('#br').onclick = () => ui.requestAttendance(w);

            $('#bf').onclick = async e => {
                const b = e.currentTarget,
                    on = !w.is_favorite;

                b.disabled = true;

                try {
                    await (on ? SAM.api.favorites.add(w.id) : SAM.api.favorites.remove(w.id));
                    w.is_favorite = on;
                    b.setAttribute('aria-pressed', on);
                    b.textContent = on ? '♥ Favoritado' : '♡ Favoritar';
                    SAM.toast(on ? 'Adicionada aos favoritos.' : 'Removida dos favoritos.');
                } catch (x) {
                    SAM.toast(x.detail || 'Não foi possível atualizar os favoritos.');
                }

                b.disabled = false;
            };
        }
    }

    ui.load(view, async () => {
        if (!id) {
            throw Object.assign(new Error('Oficina não encontrada.'), { status: 404, detail: 'Oficina não encontrada.', title: 'Oficina não encontrada' });
        }

        try {
            return await SAM.api.workshops.get(id);
        } catch (e) {
            if (e.status === 404) {
                e.title = 'Oficina não encontrada';
                e.detail = 'Esta oficina não existe ou foi removida.';
            }

            throw e;
        }
    }, r => {
        w = r;
        draw();
    });
})();
