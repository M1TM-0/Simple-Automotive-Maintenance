(() => {
    /* T25 — Avaliações recebidas + M04 (responder). A oficina não denuncia avaliações. */

    const { $, esc, fm, form, ui } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('AVALIAÇÕES');

    const view = $('#view');

    let items = [], onlyOpen = false;

    const stars = n => `<span class="st" role="img" aria-label="${n} de 5">${'★'.repeat(n)}${'☆'.repeat(5 - n)}</span>`;

    /* média e distribuição só das publicadas */

    function summary() {
        const pub = items.filter(r => r.status_review === 'published'),
            n = pub.length,
            avg = n ? pub.reduce((a, r) => a + r.rating, 0) / n : 0;

        return `
            <section class="sc rsum" aria-label="Resumo das avaliações">
                <div>
                    <b class="rsum__n">${n ? fm.stars(avg) : '—'}</b>
                    <p class="muted">${n} ${n === 1 ? 'avaliação publicada' : 'avaliações publicadas'}</p>
                </div>

                <ul class="bars">
                    ${[5, 4, 3, 2, 1].map(k => {
                        const c = pub.filter(r => r.rating === k).length;

                        return `<li><span>${k} ★</span><div class="bar2" aria-hidden="true"><i style="--w:${n ? c / n * 100 : 0}%"></i></div><span>${c}</span></li>`;
                    }).join('')}
                </ul>
            </section>
        `;
    }

    const card = r => `
        <article class="cd rvw" id="r-${esc(r.id)}">
            <div class="att__top">
                <div>${stars(r.rating)} <small class="muted">${esc(r.client_name || 'Cliente')} · ${esc(fm.date(r.date_creation))}</small></div>
                ${r.status_review === 'published' ? '' : ui.badge('status_review', r.status_review)}
            </div>

            ${r.comment ? `<p>${esc(r.comment)}</p>` : '<p class="muted">Sem comentário.</p>'}

            ${r.workshop_response ? `<blockquote class="cm"><b>Sua resposta:</b> ${esc(r.workshop_response)}</blockquote>` : ''}

            ${r.status_review === 'published'
                ? `<div class="acts"><button type="button" class="btn" data-rs="${esc(r.id)}">${r.workshop_response ? 'Editar resposta' : 'Responder'}</button></div>`
                : '<p class="muted" style="font-size:.76rem">Esta avaliação não está pública: não é possível responder.</p>'}
        </article>
    `;

    function list() {
        const r = items.filter(x => !onlyOpen || (x.status_review === 'published' && !x.workshop_response));

        $('#rl').innerHTML = r.length ? r.map(card).join('') : '<p class="empty" style="grid-column:1/-1">Nenhuma avaliação nesta lista.</p>';
        $('#sm').innerHTML = summary();
    }

    function respond(r) {
        const m = ui.modal({
            title: r.workshop_response ? 'Editar resposta' : 'Responder avaliação',
            body: `
                <form id="rf" novalidate>
                    <p class="muted">${stars(r.rating)} ${esc(r.comment || 'Sem comentário.')}</p>

                    ${form.fld({ id: 'workshop_response', label: 'Sua resposta (pública)', req: 1, rows: 4, value: r.workshop_response, attrs: 'maxlength="1000"' })}

                    <p class="ferr" role="alert"></p>
                    <button class="btn btn--solid">Publicar resposta</button>
                </form>
            `
        });

        form.wire($('#rf', m.body), async () => {
            const t = $('#workshop_response', m.body).value.trim();

            if (form.err('workshop_response', !t ? 'Escreva a resposta.' : t.length > 1000 ? 'Use até 1000 caracteres.' : '')) {
                form.focusBad(m.body);
                return;
            }

            const x = await SAM.api.workshop.respond(r.id, t);

            Object.assign(r, x && x.workshop_response ? x : { workshop_response: t });
            m.close();
            list();
            SAM.toast('Resposta publicada.');
        }, { busy: 'Publicando…' });
    }

    function draw() {
        view.innerHTML = `
            <div class="wrap">
                ${ui.subnav('reviews')}

                <h1 class="h1">Avaliações recebidas</h1>

                <div id="sm"></div>

                <div class="chips" role="group" aria-label="Filtrar avaliações">
                    <button type="button" class="chip" id="fo" aria-pressed="false">Sem resposta</button>
                </div>

                <div class="cg" id="rl" aria-live="polite"></div>
            </div>
        `;

        list();

        $('#fo').onclick = e => {
            onlyOpen = !onlyOpen;
            e.currentTarget.setAttribute('aria-pressed', onlyOpen);
            list();
        };

        $('#rl').onclick = e => {
            const b = e.target.closest('[data-rs]');

            if (b) respond(items.find(r => String(r.id) === b.dataset.rs));
        };
    }

    ui.load(view, () => SAM.api.workshop.reviews(), r => {
        items = r.results;
        draw();
    });
})();
