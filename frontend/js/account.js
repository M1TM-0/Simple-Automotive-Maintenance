(() => {
    /* T16 — Minha conta (Cliente): dados pessoais e acesso */

    const { $, esc, lbl, v, form, ui } = SAM;

    if (!SAM.auth.require('client')) return;

    ui.title('MINHA CONTA');

    const view = $('#view');

    const pwf = (i, l, a) => `
        <div class="fld">
            <label for="${i}">${l}</label>

            <div class="pw">
                <input id="${i}" type="password" autocomplete="${a}">

                <button type="button" class="tg" data-for="${i}" aria-pressed="false" aria-controls="${i}">
                    Mostrar
                </button>
            </div>

            <span class="err" id="e-${i}" role="alert"></span>
        </div>
    `;

    function draw(u) {
        view.innerHTML = `
            <div class="wrap wrap--n">
                <h1 class="h1">Minha conta</h1>

                <div class="tabs" role="tablist" aria-label="Seções da conta">
                    <i></i>
                    <button role="tab" id="tb-d" data-tab="d" aria-selected="true" aria-controls="p-d">Dados</button>
                    <button role="tab" id="tb-a" data-tab="a" aria-selected="false" aria-controls="p-a" tabindex="-1">Acesso</button>
                </div>

                <section id="p-d" role="tabpanel" aria-labelledby="tb-d">
                    <form id="fd" class="fs-f" novalidate>
                        <fieldset class="fs">
                            <legend>Dados pessoais</legend>

                            <div class="fgrid">
                                ${form.fld({ id: 'name', label: 'Nome completo', req: 1, value: u.name, attrs: 'autocomplete="name" maxlength="255"' })}
                                ${form.fld({ id: 'phone_number', label: 'Telefone (opcional)', type: 'tel', value: u.phone_number, attrs: 'autocomplete="tel" maxlength="255"' })}
                            </div>

                            <p>
                                <span class="muted">Situação da conta:</span>
                                <b>${esc(lbl('status_account', u.status || 'active'))}</b>
                            </p>

                            ${form.photo({ id: 'photo_profile', label: 'Foto de perfil', url: u.photo_profile, rm: 1, max: 600 })}
                        </fieldset>

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid" id="sd">Salvar dados</button>
                    </form>
                </section>

                <section id="p-a" role="tabpanel" aria-labelledby="tb-a" hidden>
                    <form id="fa" novalidate>
                        <fieldset class="fs">
                            <legend>Acesso</legend>

                            <div class="fld">
                                <label for="email">E-mail</label>
                                <input id="email" value="${esc(u.email || '')}" readonly>
                                <small class="muted">O e-mail não pode ser alterado por aqui.</small>
                            </div>

                            ${pwf('current_password', 'Senha atual', 'current-password')}
                            ${pwf('new_password', 'Nova senha (mín. 8, com letras e números)', 'new-password')}
                            ${pwf('new_password2', 'Confirmar nova senha', 'new-password')}
                        </fieldset>

                        <p class="ferr" role="alert"></p>
                        <button class="btn btn--solid" id="sa">Alterar senha</button>
                    </form>
                </section>
            </div>
        `;

        form.pwToggles(view);
        form.photoInit(view);

        const T = ui.tabs($('.tabs', view), k => {
            ['d', 'a'].forEach(x => {
                $('#p-' + x).hidden = x !== k;
            });
        });

        T.select('d');

        form.wire($('#fd'), async () => {
            const nm = $('#name').value.trim(),
                ph = $('#phone_number').value.trim(),
                pf = form.photoGet(view, 'photo_profile');

            if (form.err('name', nm.length < 3 ? 'Informe seu nome completo.' : '')) {
                form.focusBad();
                return;
            }

            let body = { name: nm, phone_number: ph };

            if (pf.blob || pf.removed) {
                body = new FormData();
                body.append('name', nm);
                body.append('phone_number', ph);

                if (pf.blob) body.append('photo_profile', pf.blob, 'perfil.jpg');
                else body.append('photo_profile', '');
            }

            await SAM.api.account.update(body);

            const s = SAM.auth.user();

            SAM.auth.setSession(Object.assign({}, s, { name: nm }));
            ui.header();
            SAM.toast('Dados salvos.');
        }, { btn: '#sd', busy: 'Salvando…' });

        form.wire($('#fa'), async () => {
            const cur = $('#current_password').value,
                nw = $('#new_password').value;

            const bad = [
                form.err('current_password', cur ? '' : 'Informe a senha atual.'),
                form.err('new_password', v.password(nw)),
                form.err('new_password2', v.confirm($('#new_password2').value, nw))
            ];

            if (bad.some(Boolean)) {
                form.focusBad();
                return;
            }

            await SAM.api.account.password({ current_password: cur, new_password: nw });

            $('#fa').reset();
            SAM.toast('Senha alterada.');
        }, { btn: '#sa', busy: 'Salvando…' });
    }

    ui.load(view, async () => {
        const u = await SAM.api.auth.me();

        return Object.assign({}, SAM.auth.user(), u);
    }, draw);
})();
