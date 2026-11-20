(() => {
    /* T10 — Meus veículos */

    const { $, esc, km, car, I, lbl, fm, ui } = SAM;

    if (!SAM.auth.require('client')) return;

    ui.title('VEHICLE');

    const view = $('#view');

    let items = [],
        next = null,
        q = '';

    const card = (v, i) => {
        const ph = fm.photos(v)[0];

        return `
            <a
                class="vl"
                style="animation-delay:${Math.min(i, 8) * .06}s"
                href="vehicle.html?id=${encodeURIComponent(v.id)}"
            >
                <div class="vph">
                    ${ph ? `<img src="${ui.url(ph)}" alt="">` : car()}
                </div>

                <div>
                    <h2>${esc(v.brand + ' ' + v.model)}</h2>

                    <p class="muted" style="font-size:.78rem">
                        ${esc([v.version, v.motorization].filter(Boolean).join(' · ') || 'Sem versão informada')}
                    </p>

                    <ul class="facts">
                        <li>${v.year_fabrication}/${v.year_model}</li>
                        ${v.mileage_km != null ? `<li>${km(v.mileage_km)}</li>` : ''}
                        <li>${esc(lbl('fuel', v.fuel))}</li>
                        <li>${esc(lbl('exchange', v.exchange))}</li>
                    </ul>

                    <span class="plate">${esc(fm.plate(v.plate))}</span>
                </div>
            </a>
        `;
    };

    const draw = () => {
        const f = items.filter(v =>
            (v.brand + ' ' + v.model + ' ' + v.plate + ' ' + fm.plate(v.plate))
                .toLowerCase()
                .includes(q)
        );

        $('#vl').innerHTML = f.length
            ? f.map(card).join('')
            : `<p class="empty" style="grid-column:1/-1">Nenhum veículo corresponde à busca.</p>`;

        $('#more').innerHTML = next ? ui.moreBtn() : '';

        const b = $('[data-more]', view);

        if (b) b.onclick = more;
    };

    async function more() {
        const b = $('[data-more]', view);

        if (b) b.disabled = true;

        try {
            const r = await SAM.api.vehicles.list({ page: SAM.api.pageOf(next) });

            items = items.concat(r.results);
            next = r.next;
            draw();
        } catch (e) {
            SAM.toast(e.detail || 'Não foi possível carregar mais.');

            if (b) b.disabled = false;
        }
    }

    function render(r) {
        items = r.results;
        next = r.next;

        if (!items.length) {
            view.innerHTML = `
                <div class="wrap">
                    ${ui.emptyHtml({
                        title: 'Você ainda não cadastrou veículos',
                        text: 'Cadastre seu primeiro veículo para registrar manutenções, acompanhar prazos e compartilhar o histórico com oficinas.',
                        cta: { href: 'vehicle-new.html', label: 'Cadastrar veículo' }
                    })}
                </div>
            `;

            return;
        }

        view.innerHTML = `
            <div class="wrap">
                <div class="vbar">
                    <h1 class="h1" style="margin:0">Seus veículos</h1>

                    <label class="search">
                        <span class="sr">Buscar veículo</span>
                        ${I.s}
                        <input id="q" placeholder="Buscar por marca, modelo ou placa">
                    </label>

                    <a class="btn btn--solid" href="vehicle-new.html">+ Cadastrar veículo</a>
                </div>

                <div class="vls" id="vl" aria-live="polite"></div>
                <div id="more"></div>
            </div>
        `;

        $('#q').addEventListener('input', e => {
            q = e.target.value.trim().toLowerCase();
            draw();
        });

        draw();
    }

    ui.load(view, () => SAM.api.vehicles.list(), render);

    if (location.search.includes('deleted=1')) SAM.toast('Veículo excluído.');
})();
