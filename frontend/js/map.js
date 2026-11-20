(() => {
    /* T05 — Mapa e busca (Leaflet 1.9.4 + OpenStreetMap). Sem coordenadas: mapa neutro com aviso.
     *
     * Duas fontes de pontos (BE-094, ADR 0024):
     *   1. SAM  — oficinas cadastradas e pontos de interesse (`api.map.points`): lista ao
     *             lado + pinos em gota; só a oficina tem perfil, chat, favorito e atendimento.
     *   2. OSM  — postos, borracharias, oficinas… do OpenStreetMap ainda não cadastrados
     *             (`api.map.external`, Overpass pelo backend, com cache): só pinos em
     *             losango e um popup com link para o OSM. Pedido só com zoom ≥ EXT_MIN_ZOOM,
     *             para a área visível; se falhar, o mapa do SAM continua igual.
     *
     * Tiles: SAM.config.MAP_TILES ({ url, attribution, maxZoom }) troca o provedor; o padrão
     * é o OSM público (política: atribuição visível, Referer válido, sem download em massa —
     * a página usa `Referrer-Policy: same-origin`, então os tiles pedem só a origem).
     */

    const { $, $$, esc, I, car, fm, lbl, ui } = SAM;

    const qs = new URLSearchParams(location.search),
        view = $('#view'),
        hasL = !!window.L;

    const S = {
        q: qs.get('q') || '',
        category: qs.get('category') || '',
        type: '',
        open: false,
        radius: 10,
        lat: null,
        lng: null
    };

    const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
        TILES = Object.assign(
            { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', attribution: OSM_ATTR, maxZoom: 19 },
            (SAM.config && SAM.config.MAP_TILES) || {}
        ),
        EXT_MIN_ZOOM = 13;

    let map, layer, ext, me, seq = 0, results = [], cats = [], tm,
        eseq = 0, etm, extRes = [], extMsg = '', extState = 'idle'; /* idle | loading | done */

    S.ext = true;

    const markers = new Map(),
        key = p => p.kind + '-' + p.id,
        filtered = () => !!(S.q || S.category || S.type || S.open || S.lat != null);

    /* ---------- mapa ---------- */

    function initMap() {
        const mb = $('#mb');

        if (!hasL) {
            mb.innerHTML = '<p class="muted map__off">Não foi possível carregar o mapa. A lista ao lado continua funcionando.</p>';
            return;
        }

        map = L.map(mb).setView([-14.2, -51.9], 4);

        L.tileLayer(TILES.url, {
            maxZoom: TILES.maxZoom,
            attribution: TILES.attribution,
            referrerPolicy: 'strict-origin-when-cross-origin'
        }).addTo(map);

        /* os estabelecimentos externos também são dados do OSM (ODbL): com outro provedor
           de tiles a atribuição do OSM continua no mapa (texto igual não se repete) */
        map.attributionControl.addAttribution(OSM_ATTR);

        ext = L.layerGroup().addTo(map);
        layer = L.layerGroup().addTo(map);

        map.on('moveend', () => {
            clearTimeout(etm);
            etm = setTimeout(external, 500);
        });

        addEventListener('resize', () => map.invalidateSize());
    }

    /* conteúdo do popup em DOM (nada de HTML com dado da API) */

    function popup(p) {
        const d = document.createElement('div');

        d.className = 'pop';

        const b = document.createElement('b');

        b.textContent = p.name;
        d.append(b);

        if (p.kind === 'workshop') {
            const a = document.createElement('a');

            a.href = 'shop.html?id=' + encodeURIComponent(p.id);
            a.textContent = 'Ver perfil';
            d.append(document.createElement('br'), a);
        } else {
            const s = document.createElement('span');

            s.textContent = 'Sem perfil no SAM';
            d.append(document.createElement('br'), s);
        }

        return d;
    }

    function hi(k, on) {
        $$(`[data-k="${k}"]`, view).forEach(n => n.classList.toggle('is-on', on));

        const m = markers.get(k),
            e = m && m.getElement();

        if (e) e.classList.toggle('is-on', on);
    }

    function pins(list) {
        if (!map) return;

        layer.clearLayers();
        markers.clear();

        const pts = list.filter(p => p.lat != null && p.lng != null),
            bounds = [];

        pts.forEach(p => {
            const mk = L.marker([p.lat, p.lng], {
                icon: L.divIcon({
                    className: 'lpin-w',
                    html: `<span class="lpin ${p.kind === 'poi' ? 'lpin--poi' : ''}"></span>`,
                    iconSize: [30, 38],
                    iconAnchor: [15, 36],
                    popupAnchor: [0, -34]
                }),
                title: p.name,
                alt: p.name
            }).bindPopup(popup(p));

            mk.on('mouseover', () => hi(key(p), true));
            mk.on('mouseout', () => hi(key(p), false));
            mk.addTo(layer);
            markers.set(key(p), mk);
            bounds.push([p.lat, p.lng]);
        });

        if (me) me.remove();

        if (S.lat != null) {
            me = L.circleMarker([S.lat, S.lng], { radius: 8, className: 'lpin-me' })
                .bindTooltip('Você está aqui')
                .addTo(map);

            bounds.push([S.lat, S.lng]);
        }

        $('#mapn').hidden = !!pts.length;

        if (bounds.length) {
            map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
        } else {
            map.setView([-14.2, -51.9], 4);
        }
    }

    /* ---------- estabelecimentos do OpenStreetMap (não cadastrados) ---------- */

    const plain = t => String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

    function extPopup(p) {
        const d = document.createElement('div'),
            b = document.createElement('b'),
            t = document.createElement('span'),
            src = document.createElement('small');

        d.className = 'pop';
        b.textContent = p.name;
        t.textContent = lbl('type_establishment', p.type) + ' · não cadastrado no SAM';
        d.append(b, document.createElement('br'), t);

        if (p.address) {
            const a = document.createElement('span');

            a.textContent = p.address;
            d.append(document.createElement('br'), a);
        }

        src.className = 'pop__src';
        src.append('Dados © ');

        if (/^https:\/\/www\.openstreetmap\.org\/(node|way|relation)\/\d+$/.test(p.osm_url || '')) {
            const a = document.createElement('a');

            a.href = p.osm_url;
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
            a.textContent = 'OpenStreetMap';
            src.append(a);
        } else {
            src.append('OpenStreetMap');
        }

        src.append(' contributors (ODbL)');
        d.append(document.createElement('br'), src);

        return d;
    }

    /* desenha os externos já recebidos com os filtros atuais e atualiza o aviso */

    function drawExt() {
        const st = $('#extst');

        if (!map) return;

        ext.clearLayers();

        let msg = extMsg;

        if (!S.ext || extState === 'idle') {
            msg = '';
        } else if (S.category || S.open) {
            msg = 'Categoria e "Aberto agora" valem só para as oficinas cadastradas no SAM.';
        } else {
            const q = plain(S.q),
                list = extRes.filter(p => (!S.type || p.type === S.type) && (!q || plain(p.name).includes(q)));

            list.forEach(p => {
                L.marker([p.lat, p.lng], {
                    icon: L.divIcon({
                        className: 'lpin-w',
                        html: '<span class="lpin lpin--osm"></span>',
                        iconSize: [20, 20],
                        iconAnchor: [10, 10],
                        popupAnchor: [0, -10]
                    }),
                    title: p.name + ' (OpenStreetMap)',
                    alt: p.name + ' (OpenStreetMap, não cadastrado no SAM)',
                    zIndexOffset: -500
                }).bindPopup(extPopup(p)).addTo(ext);
            });

            if (extState === 'loading') {
                msg = 'Buscando postos, borracharias e oficinas do OpenStreetMap…';
            } else if (!msg) {
                msg = list.length
                    ? `${list.length} ${list.length === 1 ? 'estabelecimento' : 'estabelecimentos'} do OpenStreetMap na área visível (não cadastrados no SAM).`
                    : extRes.length
                        ? 'Nenhum estabelecimento do OpenStreetMap com esses filtros nesta área.'
                        : 'Nenhum estabelecimento do OpenStreetMap nesta área.';
            }
        }

        if (st) st.textContent = msg;
    }

    /* busca a área visível (o backend guarda em cache e protege a Overpass) */

    async function external() {
        const my = ++eseq;

        if (!map || !S.ext) {
            drawExt();
            return;
        }

        if (map.getZoom() < EXT_MIN_ZOOM) {
            extRes = [];
            extMsg = 'Aproxime o mapa para ver postos, borracharias e oficinas do OpenStreetMap.';
            extState = 'done';
            drawExt();
            return;
        }

        const b = map.getBounds(),
            fx = n => n.toFixed(5);

        /* até a resposta: aviso de busca (nunca "nenhum" antes de saber) */
        extState = 'loading';
        extMsg = '';
        drawExt();

        try {
            const r = await SAM.api.map.external({
                south: fx(Math.max(-90, b.getSouth())),
                west: fx(Math.max(-180, b.getWest())),
                north: fx(Math.min(90, b.getNorth())),
                east: fx(Math.min(180, b.getEast()))
            });

            if (my !== eseq) return;

            extRes = Array.isArray(r && r.results) ? r.results : [];
            extMsg = (r && r.status !== 'ok' && r.detail) || '';
        } catch (e) {
            if (my !== eseq) return;

            extRes = [];
            extMsg = 'Os estabelecimentos do OpenStreetMap estão indisponíveis no momento. As oficinas cadastradas no SAM continuam no mapa.';
        }

        extState = 'done';
        drawExt();
    }

    /* ---------- lista ---------- */

    const card = (p, i) => {
        const body = `
            <div class="thumb">${car('#e9e6df')}</div>

            <div>
                <b>${esc(p.name)}</b>

                <span>
                    ${p.rating_avg ? '★ ' + fm.stars(p.rating_avg) : 'Sem avaliações'}
                    ${p.distance_km != null ? ' · ' + fm.dist(p.distance_km) : ''}
                    ${typeof p.is_open_now === 'boolean' ? ' · ' + (p.is_open_now ? 'Aberto' : 'Fechado') : ''}
                </span>

                <br>

                <span class="tag">${esc(lbl('type_establishment', p.type || 'oficina'))}</span>
                ${p.kind === 'poi' ? '<span class="tag tag--poi">Sem perfil no SAM</span>' : ''}
            </div>
        `;

        return `
            <li>
                ${p.kind === 'workshop'
                    ? `<a class="shopc" href="shop.html?id=${encodeURIComponent(p.id)}" data-k="${esc(key(p))}" style="--d:${Math.min(i, 10) * .05}s">${body}</a>`
                    : `<div class="shopc" data-k="${esc(key(p))}" style="--d:${Math.min(i, 10) * .05}s">${body}</div>`}
            </li>
        `;
    };

    function draw() {
        const l = $('#list');

        l.removeAttribute('aria-busy');

        l.innerHTML = results.length
            ? results.map(card).join('')
            : filtered()
                ? `
                    <li class="empty">
                        Nenhuma oficina encontrada. Limpe os filtros ou tente outro termo.
                        <br><button type="button" class="btn" id="clr" style="margin-top:10px">Limpar filtros</button>
                    </li>
                `
                : `
                    <li class="empty empty--big">
                        <h2>Nenhuma oficina cadastrada ainda</h2>
                        <p>As oficinas aparecem aqui assim que se cadastrarem no SAM.</p>
                        <a class="btn btn--solid" href="register.html?role=oficina">Cadastrar minha oficina</a>
                    </li>
                `;

        pins(results);
        drawExt();
    }

    async function search() {
        const my = ++seq,
            l = $('#list');

        l.setAttribute('aria-busy', 'true');
        l.innerHTML = '<li class="sk"></li><li class="sk"></li><li class="sk"></li>';

        try {
            const r = await SAM.api.map.points({
                q: S.q,
                category: S.category,
                type: S.type,
                open_now: S.open ? true : '',
                lat: S.lat ?? '',
                lng: S.lng ?? '',
                radius_km: S.lat != null ? S.radius : ''
            });

            if (my !== seq) return;

            results = r.results.slice().sort((a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9));
            draw();
        } catch (e) {
            if (my !== seq) return;

            l.removeAttribute('aria-busy');
            l.innerHTML = `<li>${ui.failHtml(e)}</li>`;
            $('[data-retry]', l).onclick = search;
            pins([]);
        }
    }

    /* ---------- promoções (carrossel abaixo do mapa) ---------- */

    async function promos() {
        try {
            const r = (await SAM.api.promotions.active()).results.filter(p => p.image);

            if (!r.length) return;

            $('#pbox').innerHTML = `
                <div class="promo" id="promo" role="group" aria-label="Promoções">
                    ${r.map((p, i) => `
                        <a class="${i ? '' : 'on'}" href="shop.html?id=${encodeURIComponent(p.workshop_id)}">
                            <img src="${ui.url(p.image)}" alt="${esc(p.title + ' — ' + p.workshop_name + ', ' + fm.discount(p.type_discount, p.discount_value))}">
                        </a>
                    `).join('')}
                </div>
            `;

            const sl = $$('#promo a');

            if (sl.length < 2 || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

            let i = 0,
                paused = false;

            const go = n => {
                sl[i].classList.remove('on');
                i = n;
                sl[i].classList.add('on');
            };

            const box = $('#promo');

            box.addEventListener('mouseenter', () => { paused = true; });
            box.addEventListener('mouseleave', () => { paused = false; });
            box.addEventListener('focusin', e => { paused = true; go(sl.indexOf(e.target.closest('a'))); });
            box.addEventListener('focusout', () => { paused = false; });

            setInterval(() => {
                if (!paused && document.visibilityState === 'visible') go((i + 1) % sl.length);
            }, 4000);
        } catch (e) {}
    }

    /* ---------- página ---------- */

    function render() {
        view.innerHTML = `
            <div class="wrap">
                <h1 class="sr">Mapa de oficinas</h1>

                <div class="mtool">
                    <label class="search">
                        <span class="sr">Buscar oficina ou serviço</span>
                        ${I.s}
                        <input id="q" placeholder="Buscar oficina ou serviço" value="${esc(S.q)}" maxlength="100">
                    </label>

                    <div class="fld">
                        <label for="ft" class="sr">Tipo de estabelecimento</label>
                        <select id="ft">${SAM.opts('type_establishment', S.type, 'Todos os tipos')}</select>
                    </div>

                    <button type="button" class="chip" id="fo" aria-pressed="false">Aberto agora</button>

                    <div class="fld">
                        <label for="fr" class="sr">Raio de busca</label>

                        <select id="fr" disabled aria-describedby="geo">
                            ${[1, 2, 5, 10, 20, 50].map(k => `<option value="${k}" ${k === S.radius ? 'selected' : ''}>${k} km</option>`).join('')}
                        </select>
                    </div>

                    <button type="button" class="btn" id="gb">Usar minha localização</button>
                </div>

                <p class="muted" id="geo" role="status" style="font-size:.78rem;min-height:1.2em"></p>

                <div class="chips chips--h" role="group" aria-label="Filtrar por categoria de serviço" id="cats"></div>

                <div class="mg">
                    <div>
                        <div class="mapbox" id="mb"></div>

                        <p class="muted" id="mapn" hidden style="font-size:.78rem;margin-top:6px">
                            Sem posição para mostrar: o mapa fica neutro até haver resultados com localização.
                        </p>

                        <div class="mleg">
                            <p class="mleg__k" aria-label="Legenda do mapa">
                                <span><i class="lpin lpin--key" aria-hidden="true"></i>Oficina cadastrada no SAM</span>
                                <span><i class="lpin lpin--poi lpin--key" aria-hidden="true"></i>Ponto de interesse do SAM</span>
                                <span><i class="lpin lpin--osm lpin--key" aria-hidden="true"></i>OpenStreetMap (não cadastrado)</span>
                            </p>

                            <label class="mleg__t">
                                <input type="checkbox" id="fx" checked>
                                Mostrar postos, borracharias e oficinas do OpenStreetMap
                            </label>

                            <p class="muted mleg__s" id="extst" role="status"></p>

                            <p class="muted mleg__s">
                                Mapa e estabelecimentos externos: dados &copy;
                                <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>,
                                licença ODbL.
                            </p>
                        </div>

                        <div id="pbox"></div>
                    </div>

                    <div>
                        <h2 class="rule"><span>Oficinas próximas</span></h2>
                        <ul id="list" aria-live="polite"></ul>
                    </div>
                </div>
            </div>
        `;

        initMap();

        const go = () => {
            clearTimeout(tm);
            search();
        };

        $('#q').addEventListener('input', e => {
            S.q = e.target.value.trim();
            drawExt();
            clearTimeout(tm);
            tm = setTimeout(search, 300);
        });

        $('#q').addEventListener('keydown', e => {
            if (e.key === 'Enter') e.preventDefault();
        });

        $('#ft').onchange = e => { S.type = e.target.value; go(); };

        $('#fo').onclick = e => {
            S.open = !S.open;
            e.currentTarget.setAttribute('aria-pressed', S.open);
            go();
        };

        $('#fr').onchange = e => { S.radius = +e.target.value; go(); };

        $('#fx').onchange = e => {
            S.ext = e.target.checked;
            external();
        };

        $('#gb').onclick = () => {
            const g = $('#geo');

            if (!navigator.geolocation) {
                g.textContent = 'Seu navegador não permite localização. Continue buscando por texto.';
                return;
            }

            g.textContent = 'Obtendo sua localização…';

            navigator.geolocation.getCurrentPosition(p => {
                S.lat = +p.coords.latitude.toFixed(6);
                S.lng = +p.coords.longitude.toFixed(6);
                $('#fr').disabled = false;
                g.textContent = 'Usando sua localização. Ajuste o raio se precisar.';
                go();
            }, () => {
                g.textContent = 'Não foi possível obter sua localização (permissão negada ou indisponível). Continue buscando por texto.';
            }, { timeout: 10000 });
        };

        view.addEventListener('click', e => {
            if (e.target.id === 'clr') {
                Object.assign(S, { q: '', category: '', type: '', open: false, lat: null, lng: null });
                $('#q').value = '';
                $('#ft').value = '';
                $('#fo').setAttribute('aria-pressed', 'false');
                $('#fr').disabled = true;
                $('#geo').textContent = '';
                $$('#cats .chip').forEach(c => c.setAttribute('aria-pressed', 'false'));
                go();
            }
        });

        view.addEventListener('mouseover', e => {
            const t = e.target.closest('.shopc[data-k]');

            if (t) hi(t.dataset.k, true);
        });

        view.addEventListener('mouseout', e => {
            const t = e.target.closest('.shopc[data-k]');

            if (t) hi(t.dataset.k, false);
        });

        view.addEventListener('focusin', e => {
            const t = e.target.closest('.shopc[data-k]');

            if (t) hi(t.dataset.k, true);
        });

        view.addEventListener('focusout', e => {
            const t = e.target.closest('.shopc[data-k]');

            if (t) hi(t.dataset.k, false);
        });

        /* categorias carregadas da API (substituem os 4 chips fixos) */

        SAM.api.catalog.categories().then(r => {
            cats = r.results;

            $('#cats').innerHTML = cats.map(c => `
                <button type="button" class="chip" data-c="${esc(c.id)}" aria-pressed="${String(c.id) === S.category}">${esc(c.name)}</button>
            `).join('');
        }).catch(() => {});

        $('#cats').addEventListener('click', e => {
            const c = e.target.closest('[data-c]');

            if (!c) return;

            S.category = S.category === c.dataset.c ? '' : c.dataset.c;
            $$('#cats .chip').forEach(x => x.setAttribute('aria-pressed', x === c && !!S.category));
            go();
        });

        search();
        promos();
    }

    ui.title('MAP');
    render();
})();
