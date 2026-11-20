(() => {
    /* T02 — Login (Cliente ou Oficina) */

    const { $, v, form } = SAM,
        A = SAM.auth,
        local = SAM.config.DRIVER !== 'http';

    /* ÚNICO dado de demonstração: só com DRIVER 'local' e rotulado na tela */

    const DEMO = {
        id: 'demo',
        name: 'Usuário Demonstração',
        email: 'demo@sam.app',
        password: 'demo1234',
        role: 'client'
    };

    /* destino pós-login por perfil (?next= só em páginas do projeto) */

    const dest = u => {
        const n = A.next('');

        if (u.role === 'workshop' && u.setup_complete === false) {
            return 'workshop-setup.html';
        }

        return n || A.home(u);
    };

    if (A.user()) {
        location.replace(dest(A.user()));
        return;
    }

    if (local) $('#demo').hidden = false;

    const role = () => $('input[name=role]:checked').value;

    $('#demo-fill').onclick = () => {
        $('input[name=role][value=client]').checked = true;
        $('#email').value = DEMO.email;
        $('#pw').value = DEMO.password;
        $('#sb').focus();
    };

    form.pwToggles();

    form.wire($('#f'), async () => {
        const em = $('#email').value.trim(),
            pw = $('#pw').value;

        const bad = [
            form.err('email', v.email(em)),
            form.err('pw', pw ? '' : 'Informe sua senha.')
        ];

        if (bad.some(Boolean)) {
            form.focusBad();
            return;
        }

        let u;

        try {
            if (local && em.toLowerCase() === DEMO.email && pw === DEMO.password) {
                A.setSession(DEMO);
                u = DEMO;
            } else {
                u = await SAM.api.auth.login({
                    role: role(),
                    email: em,
                    password: pw
                });
            }
        } catch (e) {
            /* 400/401: não diz qual dos dois está errado */

            $('#ferr').textContent = e.status === 400 || e.status === 401
                ? 'E-mail ou senha incorretos.'
                : e.detail;

            return;
        }

        location.href = dest(u);
    }, { busy: 'Entrando…' });
})();
