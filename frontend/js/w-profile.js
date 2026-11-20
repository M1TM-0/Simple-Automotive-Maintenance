(() => {
    /* T21 — Perfil e conta da oficina: Dados · Página pública · Horários · Local · Acesso */

    const { $, esc, fm, lbl, v, form, ui, W } = SAM;

    if (!SAM.auth.require('workshop', true)) return;

    ui.title('PERFIL DA OFICINA');

    const view = $('#view'),
        TABS = [['d', 'Dados'], ['p', 'Página pública'], ['h', 'Horários'], ['l', 'Local'], ['a', 'Acesso']];

    let me, hoursW, pv = {};

    const prev = () => `
        <div class="pv" aria-label="Pré-visualização da página pública">
            <div class="pv__c">
                ${pv.banner ? `<img src="${pv.banner}" alt="Banner da oficina">` : ''}
            </div>

            <div class="pv__b">
                <div class="pv__a">
                    ${pv.avatar ? `<img src="${pv.avatar}" alt="Foto de perfil da oficina">` : SAM.car('#e9e6df')}
                </div>

                <div>
                    <b>${esc(me.name_fantasy)}</b>
                    <p class="muted" id="pv-d">${esc(pv.desc || 'Sem descrição ainda.')}</p>
                </div>
            </div>
        </div>
    `;

    function draw(m, h) {
        me = m;
        pv = {
            banner: ui.url(m.page && m.page.photo_banner),
            avatar: ui.url(m.page && m.page.photo_profile),
            desc: (m.page && m.page.description) || ''
        };

        view.innerHTML = `
            <div class="wrap wrap--n">
                ${ui.subnav('profile')}

                <div class="hbar">
                    <h1 class="h1">Perfil da oficina</h1>
                    <a class="btn" href="shop.html?id=${encodeURIComponent(m.id)}">Ver como cliente</a>
                </div>

                <div class="tabs" role="tablist" aria-label="Seções do perfil">
                    <i></i>
                    ${TABS.map(([k, l], i) => `<button role="tab" id="tb-${k}" data-tab="${k}" aria-selected="${!i}" aria-controls="p-${k}" ${i ? 'tabindex="-1"' : ''}>${l}</button>`).join('')}
                </div>

                <section id="p-d" role="tabpanel" aria-labelledby="tb-d">
                    <form id="fd" novalidate>
                        <fieldset class="fs">
                            <legend>Dados da oficina</legend>

                            <div class="fgrid">
                                ${form.fld({ id: 'name_fantasy', label: 'Nome fantasia', req: 1, value: m.name_fantasy, attrs: 'maxlength="255"' })}
                                ${form.fld({ id: 'name_responsible', label: 'Nome do responsável', req: 1, value: m.name_responsible, attrs: 'maxlength="255"' })}
                                ${form.fld({ id: 'phone_number', label: 'Telefone', type: 'tel', value: m.phone_number, attrs: 'maxlength="255"' })}

                                <div class="fld">
                                    <label for="cnpj">CNPJ</label>
                                    <input id="cnpj" value="${esc(fm.cnpj(m.cnpj))}" readonly>
                                </div>
                            </div>

                            <p><span class="muted">Situação da conta:</span> <b>${esc(lbl('status_account', m.status || 'active'))}</b></p>
                        </fieldset>

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid" id="bd">Salvar dados</button>
                    </form>
                </section>

                <section id="p-p" role="tabpanel" aria-labelledby="tb-p" hidden>
                    <form id="fp" novalidate>
                        <fieldset class="fs">
                            <legend>Página pública</legend>

                            ${form.fld({ id: 'description', label: 'Descrição', rows: 4, value: pv.desc, attrs: 'maxlength="1000"' })}

                            <div class="fgrid" style="margin-top:12px">
                                ${form.photo({ id: 'photo_profile', label: 'Foto de perfil', url: m.page && m.page.photo_profile, rm: 1, max: 600 })}
                                ${form.photo({ id: 'photo_banner', label: 'Banner', url: m.page && m.page.photo_banner, rm: 1, max: 1600 })}
                            </div>
                        </fieldset>

                        <div id="pvw">${prev()}</div>

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid" id="bp" style="margin-top:12px">Salvar página</button>
                    </form>
                </section>

                <section id="p-h" role="tabpanel" aria-labelledby="tb-h" hidden>
                    <div class="fs">
                        <h2 class="h2" style="font-size:.95rem">Horários de funcionamento</h2>
                        <div id="hw"></div>
                    </div>

                    <p class="ferr" id="eh" role="alert"></p>
                    <button class="btn btn--solid" id="bh">Salvar horários</button>
                </section>

                <section id="p-l" role="tabpanel" aria-labelledby="tb-l" hidden>
                    <div class="fs">
                        <h2 class="h2" style="font-size:.95rem">Local no mapa</h2>
                        <div id="ptw"></div>
                    </div>
                </section>

                <section id="p-a" role="tabpanel" aria-labelledby="tb-a" hidden>
                    <form id="fa" novalidate>
                        <fieldset class="fs">
                            <legend>Acesso</legend>

                            <div class="fld">
                                <label for="email">E-mail</label>
                                <input id="email" value="${esc(m.email || '')}" readonly>
                                <small class="muted">O e-mail não pode ser alterado por aqui.</small>
                            </div>

                            ${form.pw('current_password', 'Senha atual', 'current-password')}
                            ${form.pw('new_password', 'Nova senha (mín. 8, com letras e números)', 'new-password')}
                            ${form.pw('new_password2', 'Confirmar nova senha', 'new-password')}
                        </fieldset>

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid" id="ba">Alterar senha</button>
                    </form>
                </section>
            </div>
        `;

        form.pwToggles(view);

        form.photoInit(view, (id, blob) => {
            const k = id === 'photo_banner' ? 'banner' : 'avatar';

            pv[k] = blob ? URL.createObjectURL(blob) : '';
            $('#pvw').innerHTML = prev();
        });

        $('#description').addEventListener('input', e => {
            pv.desc = e.target.value;
            $('#pv-d').textContent = pv.desc || 'Sem descrição ainda.';
        });

        hoursW = W.hours($('#hw'), h);

        W.point($('#ptw'), { current: m.point, onLinked: p => { me.point = p; } });

        const T = ui.tabs($('.tabs', view), k => {
            TABS.forEach(([x]) => {
                $('#p-' + x).hidden = x !== k;
            });
        });

        T.select('d');

        form.wire($('#fd'), async () => {
            const g = id => $('#' + id).value.trim();

            const bad = [
                form.err('name_fantasy', g('name_fantasy') ? '' : 'Informe o nome fantasia.'),
                form.err('name_responsible', g('name_responsible') ? '' : 'Informe o nome do responsável.')
            ];

            if (bad.some(Boolean)) {
                form.focusBad($('#fd'));
                return;
            }

            Object.assign(me, await SAM.api.workshop.updateMe({
                name_fantasy: g('name_fantasy'),
                name_responsible: g('name_responsible'),
                phone_number: g('phone_number')
            }));

            SAM.auth.setSession(Object.assign({}, SAM.auth.user(), { name: me.name_fantasy }));
            ui.header();
            SAM.toast('Dados salvos.');
        }, { btn: '#bd', busy: 'Salvando…' });

        form.wire($('#fp'), async () => {
            const fd = new FormData(),
                a = form.photoGet(view, 'photo_profile'),
                b = form.photoGet(view, 'photo_banner');

            fd.append('description', $('#description').value.trim());

            if (a.blob) fd.append('photo_profile', a.blob, 'perfil.jpg');
            else if (a.removed) fd.append('photo_profile', '');

            if (b.blob) fd.append('photo_banner', b.blob, 'banner.jpg');
            else if (b.removed) fd.append('photo_banner', '');

            await SAM.api.workshop.page(fd);
            SAM.toast('Página pública salva.');
        }, { btn: '#bp', busy: 'Salvando…' });

        $('#bh').onclick = async e => {
            if (!hoursW.validate()) return;

            const b = e.currentTarget;

            form.busy(b, true, 'Salvando…');
            $('#eh').textContent = '';

            try {
                await SAM.api.workshop.setHours(hoursW.data());
                SAM.toast('Horários salvos.');
            } catch (x) {
                $('#eh').textContent = x.detail;
            }

            form.busy(b, false);
        };

        form.wire($('#fa'), async () => {
            const cur = $('#current_password').value,
                nw = $('#new_password').value;

            const bad = [
                form.err('current_password', cur ? '' : 'Informe a senha atual.'),
                form.err('new_password', v.password(nw)),
                form.err('new_password2', v.confirm($('#new_password2').value, nw))
            ];

            if (bad.some(Boolean)) {
                form.focusBad($('#fa'));
                return;
            }

            await SAM.api.account.password({ current_password: cur, new_password: nw });

            $('#fa').reset();
            SAM.toast('Senha alterada.');
        }, { btn: '#ba', busy: 'Salvando…' });
    }

    ui.load(view, () => Promise.all([SAM.api.workshop.me(), SAM.api.workshop.hours()]), ([m, h]) => draw(m, h.results));
})();
