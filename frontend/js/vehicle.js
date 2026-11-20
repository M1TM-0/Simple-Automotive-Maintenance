(() => {
    /* T12 — Detalhe do veículo: dados, atendimentos, histórico acumulativo, P1–P3 */

    const { $, $$, esc, km, car, lbl, fm, ui, form, v: V } = SAM;

    if (!SAM.auth.require('client')) return;

    const id = new URLSearchParams(location.search).get('id'),
        view = $('#view'),
        local = SAM.config.DRIVER !== 'http',
        today = new Date().toLocaleDateString('sv-SE');

    /* tipos fixos só no driver local (T12: "mantenha os 6 tipos atuais") */

    const TYPES = ['Troca de óleo', 'Pastilhas de freio', 'Pneus', 'Bateria', 'Revisão geral', 'Outro'];

    let v, ph = 0, hist = [], flt = 'all';

    const dd = (l, x) => `<div><dt>${l}</dt><dd>${x || x === 0 ? esc(x) : '—'}</dd></div>`;

    /* ---------- seção: atendimentos deste veículo ---------- */

    async function atts() {
        const box = $('#attb');

        try {
            const r = await SAM.api.attendances.list({ vehicle: id });

            box.innerHTML = r.results.length
                ? `<ul class="tl">${r.results.map(a => `
                    <li>
                        <b>${fm.date(a.date_attendance)}</b>
                        · ${esc((a.workshop && a.workshop.name_fantasy) || 'Oficina')}
                        · ${ui.badge('status_attendance', a.status_attendance)}
                        · <a href="attendance.html?id=${encodeURIComponent(a.id)}">Ver atendimento</a>
                    </li>`).join('')}</ul>`
                : '<p class="muted">Nenhum atendimento para este veículo ainda.</p>';
        } catch (e) {
            box.innerHTML = `<p class="muted">${SAM.api.isUnavailable(e)
                ? 'Os atendimentos aparecem aqui quando o servidor estiver disponível.'
                : esc(e.detail || 'Não foi possível carregar os atendimentos.')}</p>`;
        }
    }

    /* ---------- seção: próximas manutenções ----------
       http: calculadas pelo servidor (BE-077, GET /vehicles/{id}/upcoming-maintenance/);
       local: calculadas aqui a partir do histórico */

    const NO_DUE = '<p class="muted">Registre uma manutenção com intervalo em km para acompanhar o prazo da próxima.</p>';

    const dueItem = (name, left, p, warn) => `
        <li>
            <small>
                <span>${esc(name)}</span>
                <span>${left > 0 ? 'faltam ' + km(left) : left === 0 ? 'vence agora' : 'vencida há ' + km(-left)}</span>
            </small>

            <div class="bar2"><i class="${warn ? 'low' : ''}" style="--w:${p}%"></i></div>
        </li>
    `;

    async function loadDue() {
        const d = $('#due');

        if (!d) return;

        try {
            const r = await SAM.api.vehicles.upcoming(id);

            d.innerHTML = r.results.length
                ? `<ul class="due">${r.results.map(u =>
                    dueItem(u.service_name, u.remaining_km, u.progress_percent, u.status !== 'ok')).join('')}</ul>`
                : NO_DUE;
        } catch (e) {
            d.innerHTML = `<p class="muted">${esc(e.detail || 'Não foi possível calcular as próximas manutenções.')}</p>`;
        }
    }

    const due = () => {
        const last = {};

        hist.forEach(h => {
            if (h.interval_km && (!last[h.description] || h.date_maintenance >= last[h.description].date_maintenance)) {
                last[h.description] = h;
            }
        });

        return Object.values(last).map(h => {
            const used = (v.mileage_km || 0) - h.mileage_km,
                p = Math.max(0, Math.min(100, used / h.interval_km * 100)),
                left = h.interval_km - used;

            return dueItem(h.description, left, p, p > 85);
        }).join('');
    };

    /* ---------- seção: histórico (linha do tempo unificada) ---------- */

    function drawHist() {
        const rows = hist.filter(h => flt === 'all' || h.record_type === flt);

        $('#tl').innerHTML = rows.length
            ? rows.map(h => `
                <li>
                    <span class="sb">${h.record_type === 'part' ? 'Peça' : 'Serviço'}</span>
                    <b>${fm.date(h.date_maintenance)}</b>
                    · ${esc(h.description)}
                    ${h.mileage_km != null ? '· ' + km(h.mileage_km) : ''}
                    ${h.record_type === 'part' && h.quantity != null
                        ? `· ${esc(String(h.quantity).replace('.', ','))} × ${fm.money(h.unit_price)}`
                        : ''}
                    ${h.id_workshop || h.workshop_name
                        ? `<br><span class="muted">Registrado por oficina${h.workshop_name ? ': ' + esc(h.workshop_name) : ''}</span>`
                        : ''}
                    ${h.observations ? `<br><span class="muted">${esc(h.observations)}</span>` : ''}
                </li>
            `).join('')
            : '<li class="muted">Nenhuma manutenção registrada.</li>';

        $$('[data-f]').forEach(b => b.setAttribute('aria-pressed', b.dataset.f === flt));

        const d = $('#due');

        if (d && local) {
            const x = due();

            d.innerHTML = x ? `<ul class="due">${x}</ul>` : NO_DUE;
        }
    }

    async function loadHist() {
        try {
            let r = await SAM.api.vehicles.history(id),
                out = r.results;

            for (let i = 0; r.next && i < 30; i++) {
                r = await SAM.api.vehicles.history(id, { page: SAM.api.pageOf(r.next) });
                out = out.concat(r.results);
            }

            hist = out;
            drawHist();
        } catch (e) {
            $('#tl').innerHTML = `<li class="muted">${esc(e.detail || 'Não foi possível carregar o histórico.')}</li>`;
        }
    }

    /* ---------- página ---------- */

    function render() {
        const phs = fm.photos(v),
            hasKm = v.mileage_km != null,
            shared = v.history_shared !== undefined;

        view.innerHTML = `
            <div class="wrap">
                <a class="back-l" href="vehicles.html">← Voltar à listagem</a>

                <div class="dh">
                    <div class="gal2">
                        <div class="mainp">
                            ${phs[ph]
                                ? `<img src="${ui.url(phs[ph])}" alt="Foto ${ph + 1} de ${esc(SAM.vn(v))}">`
                                : car()}
                        </div>

                        ${phs.length > 1 ? `
                            <div class="thumbs">
                                ${phs.map((p, i) => `
                                    <button type="button" data-p="${i}" aria-pressed="${i === ph}" aria-label="Ver foto ${i + 1}">
                                        <img src="${ui.url(p)}" alt="">
                                    </button>
                                `).join('')}
                            </div>
                        ` : ''}

                        ${phs.length ? '' : `
                            <p class="muted" style="font-size:.78rem;margin-top:8px">
                                Sem fotos.
                                <a href="vehicle-new.html?id=${encodeURIComponent(id)}">Adicionar fotos</a>
                            </p>
                        `}
                    </div>

                    <div>
                        <h1>${esc(v.brand + ' ' + v.model)}</h1>
                        <p class="ver">${esc([v.version, v.motorization].filter(Boolean).join(' · '))}</p>
                        <span class="plate">${esc(fm.plate(v.plate))}</span>

                        <div class="keys">
                            <div><small>Ano</small><b>${v.year_fabrication}/${v.year_model}</b></div>
                            ${hasKm ? `<div><small>Quilometragem</small><b>${km(v.mileage_km)}</b></div>` : ''}
                            <div><small>Combustível</small><b>${esc(lbl('fuel', v.fuel))}</b></div>
                            <div><small>Câmbio</small><b>${esc(lbl('exchange', v.exchange))}</b></div>
                        </div>

                        <div class="acts">
                            <a class="btn btn--solid" href="vehicle-new.html?id=${encodeURIComponent(id)}">Editar</a>
                            <button class="btn btn--danger" id="del" type="button">Excluir</button>
                        </div>

                        <div id="cf" aria-live="polite"></div>
                    </div>
                </div>

                <section class="sc">
                    <h2>Identificação</h2>

                    <dl class="dl2">
                        ${dd('Placa', fm.plate(v.plate))}
                        ${dd('Ano de fabricação', v.year_fabrication)}
                        ${dd('Ano-modelo', v.year_model)}
                        ${dd('Versão', v.version)}
                        ${dd('Cor', v.color)}
                    </dl>
                </section>

                <section class="sc">
                    <h2>Mecânica</h2>

                    <dl class="dl2">
                        ${dd('Motorização', v.motorization)}
                        ${dd('Combustível', lbl('fuel', v.fuel))}
                        ${dd('Câmbio', lbl('exchange', v.exchange))}
                        ${hasKm ? dd('Quilometragem', km(v.mileage_km)) : ''}
                    </dl>
                </section>

                ${v.information ? `<section class="sc"><h2>Observações</h2><p>${esc(v.information)}</p></section>` : ''}

                <section class="sc" aria-live="polite">
                    <h2>Atendimentos deste veículo</h2>
                    <div id="attb"><p class="muted">Carregando…</p></div>
                </section>

                <section class="sc" aria-live="polite">
                    <h2>Próximas manutenções</h2>
                    <div id="due">${local ? '' : '<p class="muted">Carregando…</p>'}</div>
                </section>

                <section class="sc">
                    <h2>Histórico de manutenção</h2>

                    <p class="muted" style="font-size:.78rem;margin-bottom:12px">
                        O histórico só cresce: registros não podem ser editados nem apagados.
                    </p>

                    <form id="hf" novalidate>
                        <div class="fgrid">
                            ${local
                                ? form.fld({ id: 'hs', label: 'Serviço', req: 1, select: TYPES.map(t => `<option>${esc(t)}</option>`).join('') })
                                : form.fld({ id: 'hs', label: 'Serviço', req: 1, attrs: 'list="svl" maxlength="255" autocomplete="off"' }) + '<datalist id="svl"></datalist>'}

                            ${form.fld({ id: 'hd', label: 'Data', req: 1, type: 'date', value: today, attrs: `max="${today}"` })}
                            ${form.fld({ id: 'hk', label: 'Quilometragem', attrs: 'inputmode="numeric"', value: hasKm ? v.mileage_km : '' })}
                            ${form.fld({ id: 'hi', label: 'Próxima troca em (km, opcional)', attrs: 'inputmode="numeric" placeholder="ex.: 10000"' })}
                        </div>

                        ${form.fld({ id: 'hn', label: 'Observações (opcional)', attrs: 'maxlength="200"', cls: 'hn' })}

                        <p class="ferr" id="ferr" role="alert"></p>

                        <button class="btn btn--solid" id="hb" style="width:auto">Registrar manutenção</button>
                    </form>

                    <div class="chips" role="group" aria-label="Filtrar histórico">
                        ${[['all', 'Todos'], ['service', 'Serviços'], ['part', 'Peças']].map(([k, l]) =>
                            `<button type="button" class="chip" data-f="${k}" aria-pressed="${k === flt}">${l}</button>`).join('')}
                    </div>

                    <ul class="tl" id="tl" aria-live="polite"><li class="muted">Carregando…</li></ul>
                </section>

                <section class="sc">
                    <div class="sw">
                        <button type="button" role="switch" id="sw" aria-checked="${!!v.history_shared}"
                            aria-label="Autorizar oficinas a ver o histórico" ${shared ? '' : 'disabled'}></button>

                        <span>Oficinas podem consultar o histórico deste veículo</span>
                    </div>

                    ${shared ? '' : '<p class="muted" style="font-size:.75rem;margin-top:8px">Disponível em breve: o servidor ainda não guarda esta autorização.</p>'}
                </section>
            </div>
        `;

        bind();
        atts();
        loadHist();

        if (!local) loadDue();
    }

    function bind() {
        $$('[data-p]').forEach(b => {
            b.onclick = () => {
                ph = +b.dataset.p;
                render();
            };
        });

        $$('[data-f]').forEach(b => {
            b.onclick = () => {
                flt = b.dataset.f;
                drawHist();
            };
        });

        $('#del').onclick = e => ui.confirm($('#cf'), {
            label: 'Confirmar exclusão',
            text: 'Excluir este veículo? Veículos com atendimentos ou histórico não podem ser excluídos.',
            yes: 'Sim, excluir',
            back: e.currentTarget,
            onYes: async () => {
                await SAM.api.vehicles.remove(id);
                location.href = 'vehicles.html?deleted=1';
            }
        });

        const sw = $('#sw');

        sw.onclick = async () => {
            const on = sw.getAttribute('aria-checked') !== 'true';

            sw.disabled = true;

            try {
                await SAM.api.vehicles.setShared(id, on);
                sw.setAttribute('aria-checked', on);
                SAM.toast(on ? 'Oficinas agora podem ver o histórico.' : 'Histórico visível só para você.');
            } catch (e) {
                SAM.toast(e.detail || 'Não foi possível salvar.');
            }

            sw.disabled = false;
        };

        /* sugestões do catálogo (http): GET /services/?q= */

        if (!local) {
            let t;

            $('#hs').addEventListener('input', e => {
                clearTimeout(t);

                t = setTimeout(async () => {
                    const q = e.target.value.trim();

                    if (q.length < 2) return;

                    try {
                        const r = await SAM.api.catalog.services({ q });

                        $('#svl').innerHTML = r.results.slice(0, 20)
                            .map(s => `<option value="${esc(s.name)}"></option>`).join('');

                        SAM.svc = r.results;
                    } catch (x) {}
                }, 250);
            });
        }

        form.wire($('#hf'), addHist, { btn: '#hb', busy: 'Registrando…' });
    }

    async function addHist() {
        const g = n => ($('#' + n) ? $('#' + n).value.trim() : ''),
            km0 = g('hk') ? V.int(g('hk')) : null,
            itv = g('hi') ? V.int(g('hi')) : null;

        const bad = [
            form.err('hs', g('hs') ? '' : 'Informe o serviço.'),
            form.err('hd', !g('hd') || g('hd') > today ? 'Informe uma data que não seja futura.' : ''),
            form.err('hk', g('hk') && !(km0 >= 0) ? 'Use só números.' : ''),
            $('#hi') ? form.err('hi', g('hi') && !(itv > 0) ? 'Use só números maiores que zero.' : '') : false
        ];

        if (bad.some(Boolean)) {
            form.focusBad();
            return;
        }

        const hit = (SAM.svc || []).find(s => s.name.toLowerCase() === g('hs').toLowerCase()),
            d = {
                service_name: g('hs'),
                date_maintenance: local ? g('hd') : fm.isoDt(g('hd') + 'T12:00')
            };

        if (hit) d.id_service = hit.id;

        if (km0 != null) d.mileage_km = km0;

        if (g('hn')) d.observations = g('hn');

        if (itv) d.interval_km = itv;

        await SAM.api.vehicles.addHistory(id, d);

        SAM.toast('Manutenção registrada.');

        if (local) v = await SAM.api.vehicles.get(id);

        await loadHist();

        if (!local) loadDue();

        if (local && $('.keys')) render();
    }

    ui.title('VEÍCULO');

    ui.load(view, () => SAM.api.vehicles.get(id), r => {
        v = r;
        render();

        if (location.search.includes('saved=1')) SAM.toast('Veículo salvo com sucesso.');
    });
})();
