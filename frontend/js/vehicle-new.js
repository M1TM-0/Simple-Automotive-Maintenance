(() => {
    /* T11 — Cadastro/edição de veículo (campos e limites do init.sql) */

    const { $, esc, opts, v: V, fm, form, ui } = SAM;

    if (!SAM.auth.require('client')) return;

    const eid = new URLSearchParams(location.search).get('id'),
        view = $('#view'),
        Y = new Date().getFullYear();

    let cur = null;

    /* 3 posições fixas (null | {url} | {blob, preview}): a API grava photo_1..3 */

    let slots = [null, null, null];

    const back = () => eid ? 'vehicle.html?id=' + encodeURIComponent(eid) : 'vehicles.html';

    function drawPhotos() {
        $('#pv').innerHTML = slots.map((s, i) => !s ? '' : `
            <figure>
                <img src="${s.blob ? s.preview : ui.url(s.url)}" alt="Foto ${i + 1}">

                <button type="button" data-r="${i}" aria-label="Remover foto ${i + 1}" title="Remover foto ${i + 1}">
                    ×
                </button>
            </figure>
        `).join('');

        $('#phl').classList.toggle('is-off', slots.every(Boolean));
    }

    function draw() {
        const d = cur || {},
            f = (id, label, o = {}) => form.fld(Object.assign({ id, label, value: d[id] }, o));

        view.innerHTML = `
            <div class="wrap wrap--n">
                <a class="back-l" href="${back()}">← Voltar</a>

                <h1 class="h1">${cur ? 'Editar veículo' : 'Cadastrar veículo'}</h1>

                <form id="f" novalidate>
                    <fieldset class="fs">
                        <legend>Informações essenciais</legend>

                        <div class="fgrid">
                            ${f('brand', 'Marca', { req: 1, attrs: 'maxlength="255"' })}
                            ${f('model', 'Modelo', { req: 1, attrs: 'maxlength="255"' })}
                            ${f('year_fabrication', 'Ano de fabricação', { req: 1, attrs: 'inputmode="numeric" maxlength="4"' })}
                            ${f('year_model', 'Ano-modelo', { req: 1, attrs: 'inputmode="numeric" maxlength="4"' })}
                            ${f('mileage_km', 'Quilometragem (km)', { req: 1, attrs: 'inputmode="numeric"' })}
                            ${f('plate', 'Placa', { req: 1, value: fm.plate(d.plate), attrs: 'maxlength="8" placeholder="ABC-1D23" autocapitalize="characters"' })}
                        </div>
                    </fieldset>

                    <fieldset class="fs">
                        <legend>Mecânica e aparência</legend>

                        <div class="fgrid">
                            ${f('fuel', 'Combustível', { req: 1, select: opts('fuel', d.fuel, 'Selecione') })}
                            ${f('exchange', 'Câmbio', { req: 1, select: opts('exchange', d.exchange, 'Selecione') })}
                            ${f('version', 'Versão', { attrs: 'maxlength="255"' })}
                            ${f('motorization', 'Motorização (ex.: 1.6)', { attrs: 'maxlength="255"' })}
                            ${f('color', 'Cor', { attrs: 'maxlength="20"' })}
                        </div>
                    </fieldset>

                    <fieldset class="fs">
                        <legend>Informações complementares</legend>

                        ${f('information', 'Observações', { rows: 4, attrs: 'maxlength="600"' })}

                        <div class="fld" style="margin-top:14px">
                            <span>Fotos (até 3)</span>

                            <div class="ph" id="pv" aria-live="polite"></div>

                            <div class="acts">
                                <input type="file" class="sr" id="ph" accept="image/*" multiple>
                                <label class="btn" id="phl" for="ph">Adicionar foto</label>
                            </div>

                            <span class="err" id="e-ph" role="alert"></span>
                        </div>
                    </fieldset>

                    <p class="ferr" id="ferr" role="alert"></p>

                    <div class="row">
                        <button class="btn btn--solid" id="sv">Salvar veículo</button>
                        <a class="btn" href="${back()}">Cancelar</a>
                    </div>
                </form>
            </div>
        `;

        slots = [d.photo_1, d.photo_2, d.photo_3].map(u => u ? { url: u } : null);
        drawPhotos();

        $('#pv').addEventListener('click', e => {
            const b = e.target.closest('[data-r]');

            if (b) {
                slots[+b.dataset.r] = null;
                drawPhotos();
                $('#ph').focus();
            }
        });

        $('#ph').addEventListener('change', async e => {
            $('#e-ph').textContent = '';

            for (const file of e.target.files) {
                const i = slots.indexOf(null);

                if (i < 0) {
                    $('#e-ph').textContent = 'Limite de 3 fotos.';
                    break;
                }

                try {
                    const blob = await SAM.compress(file);

                    slots[i] = { blob, preview: URL.createObjectURL(blob) };
                } catch (x) {
                    $('#e-ph').textContent = 'Não foi possível ler "' + file.name + '".';
                }
            }

            e.target.value = '';
            drawPhotos();
        });

        $('#plate').addEventListener('input', e => {
            e.target.value = fm.plate(e.target.value).slice(0, 8);
        });

        form.wire($('#f'), submit, { btn: '#sv', busy: 'Salvando…' });
    }

    async function submit() {
        const g = n => ($('#' + n).value || '').trim(),
            yf = V.int(g('year_fabrication')),
            ym = V.int(g('year_model')),
            km = V.int(g('mileage_km')),
            plate = g('plate').toUpperCase().replace(/[^A-Z0-9]/g, '');

        const bad = [
            form.err('brand', g('brand') ? '' : 'Informe a marca.'),
            form.err('model', g('model') ? '' : 'Informe o modelo.'),
            form.err('year_fabrication', yf >= 1900 && yf <= Y + 1 ? '' : `Use um ano entre 1900 e ${Y + 1}.`),
            form.err(
                'year_model',
                !(ym >= 1900 && ym <= Y + 2)
                    ? `Use um ano entre 1900 e ${Y + 2}.`
                    : yf <= Y + 1 && ym < yf ? 'O ano-modelo não pode ser anterior ao de fabricação.' : ''
            ),
            form.err('mileage_km', km >= 0 ? '' : 'Informe a quilometragem usando só números.'),
            form.err('plate', /^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$/.test(plate) ? '' : 'Use o formato ABC-1D23 ou ABC-1234.'),
            form.err('fuel', g('fuel') ? '' : 'Selecione o combustível.'),
            form.err('exchange', g('exchange') ? '' : 'Selecione o câmbio.')
        ];

        if (bad.some(Boolean)) {
            form.focusBad();
            return;
        }

        const fields = {
            brand: g('brand'),
            model: g('model'),
            year_fabrication: yf,
            year_model: ym,
            mileage_km: km,
            plate,
            fuel: g('fuel'),
            exchange: g('exchange'),
            version: g('version'),
            motorization: g('motorization'),
            color: g('color'),
            information: g('information')
        };

        /* na criação não envia opcionais vazios; na edição '' limpa o campo */

        if (!cur) {
            ['version', 'motorization', 'color', 'information'].forEach(k => {
                if (!fields[k]) delete fields[k];
            });
        }

        const p = { fields, photos: slots };

        try {
            const r = cur
                ? await SAM.api.vehicles.update(eid, p)
                : await SAM.api.vehicles.create(p);

            location.href = 'vehicle.html?id=' + encodeURIComponent(r.id ?? eid) + '&saved=1';
        } catch (e) {
            /* placa repetida pode vir como 409 ou como erro geral do unique_together */

            if (e.status === 409 || (!Object.keys(e.fields || {}).length && /placa|plate|unique|único/i.test(e.detail || ''))) {
                form.err('plate', 'Já existe um veículo com esta placa');
                form.focusBad();
                return;
            }

            throw e;
        }
    }

    ui.title(eid ? 'EDITAR VEÍCULO' : 'CADASTRO DE VEÍCULO');

    if (!eid) {
        draw();
    } else {
        ui.load(view, () => SAM.api.vehicles.get(eid), v => {
            cur = v;
            draw();
        });
    }
})();
