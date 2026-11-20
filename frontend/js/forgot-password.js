(() => {
    /* T04 — Recuperar senha. Endpoints PROPOSTOS (não há tabela de tokens no banco). */

    const { $, esc, v, form } = SAM;

    const token = new URLSearchParams(location.search).get('token'),
        view = $('#view');

    const shell = inner => `
        <section class="acard" aria-labelledby="t">
            <img class="authlogo" src="assets/img/logo-sam.png" alt="SAM — Simple Auto Maintenance">
            ${inner}
        </section>
    `;

    const pwf = (i, l) => `
        <div class="fld">
            <label for="${i}">${l}</label>

            <div class="pw">
                <input id="${i}" type="password" autocomplete="new-password">

                <button type="button" class="tg" data-for="${i}" aria-pressed="false" aria-controls="${i}">
                    Mostrar
                </button>
            </div>

            <span class="err" id="e-${i}" role="alert"></span>
        </div>
    `;

    SAM.ui.title('RECUPERAR SENHA');

    if (token === null) {
        /* (a) pedir o link */

        view.innerHTML = shell(`
            <h1 id="t">Esqueci minha senha</h1>
            <p class="sub">Informe o perfil e o e-mail da conta.</p>

            <form id="f" novalidate>
                <fieldset class="roles">
                    <legend class="sr">Tipo de conta</legend>

                    <label>
                        <input type="radio" name="role" value="client" checked>
                        Cliente
                    </label>

                    <label>
                        <input type="radio" name="role" value="workshop">
                        Oficina
                    </label>
                </fieldset>

                <div class="fld">
                    <label for="email">E-mail</label>
                    <input id="email" type="email" autocomplete="email">
                    <span class="err" id="e-email" role="alert"></span>
                </div>

                <p class="ferr" id="ferr" role="alert"></p>

                <button class="btn btn--solid" id="sb">Enviar instruções</button>
            </form>

            <p class="alt"><a href="login.html">Voltar para entrar</a></p>
        `);

        form.wire($('#f'), async () => {
            const em = $('#email').value.trim();

            if (form.err('email', v.email(em))) {
                form.focusBad();
                return;
            }

            try {
                await SAM.api.auth.requestReset({
                    role: $('input[name=role]:checked').value,
                    email: em
                });
            } catch (e) {
                /* 404/422 não podem revelar se o e-mail existe */

                if (e.status !== 404 && e.status !== 400) throw e;

                if (e.status === 400 && e.fields && e.fields.email) throw e;
            }

            const ok = document.createElement('p');

            ok.setAttribute('role', 'status');
            ok.tabIndex = -1;
            ok.textContent = 'Se o e-mail estiver cadastrado, enviaremos as instruções.';

            $('#f').replaceWith(ok);
            ok.focus();
        }, { busy: 'Enviando…' });
    } else {
        /* (b) nova senha com ?token= */

        view.innerHTML = shell(`
            <h1 id="t">Criar nova senha</h1>

            <form id="f" novalidate>
                ${pwf('pw', 'Nova senha (mín. 8, com letras e números)')}
                ${pwf('pw2', 'Confirmar nova senha')}

                <p class="ferr" id="ferr" role="alert"></p>

                <button class="btn btn--solid" id="sb">Salvar nova senha</button>
            </form>
        `);

        form.pwToggles(view);

        form.wire($('#f'), async () => {
            const pw = $('#pw').value;

            const bad = [
                form.err('pw', v.password(pw)),
                form.err('pw2', v.confirm($('#pw2').value, pw))
            ];

            if (bad.some(Boolean)) {
                form.focusBad();
                return;
            }

            try {
                await SAM.api.auth.confirmReset({ token, password: pw });
            } catch (e) {
                if (SAM.api.isUnavailable(e) || e.status >= 500) throw e;

                $('#f').innerHTML = `
                    <p class="ferr" role="alert">
                        ${esc(e.fields && e.fields.password ? e.fields.password : 'Este link é inválido ou expirou.')}
                    </p>

                    <a class="btn btn--solid" href="forgot-password.html">Pedir outro link</a>
                `;

                return;
            }

            $('#f').innerHTML = `
                <p role="status">Senha alterada com sucesso.</p>
                <a class="btn btn--solid" href="login.html">Entrar</a>
            `;
        }, { busy: 'Salvando…', alias: { password: 'pw' } });
    }
})();
