(() => {
    /* T03 — Criar conta (Cliente ou Oficina). Endereço, horários e serviços ficam em T17. */

    const { $, $$, v, fm, form } = SAM,
        A = SAM.auth;

    if (A.user()) {
        location.replace(A.home());
        return;
    }

    if (SAM.config.DRIVER !== 'http') $('#note').hidden = false;

    const role = () => $('input[name=role]:checked').value,
        sync = () => {
            const w = role() === 'workshop';

            $('#cf-w').hidden = !w;
            $('#cf-c').hidden = w;
            form.clear($('#f'));
        };

    $$('input[name=role]').forEach(r => r.addEventListener('change', sync));

    const q = new URLSearchParams(location.search).get('role');

    if (q === 'oficina' || q === 'workshop') {
        $('input[name=role][value=workshop]').checked = true;
    }

    sync();
    form.pwToggles();

    $('#cnpj').addEventListener('input', e => {
        e.target.value = fm.cnpj(e.target.value);
    });

    form.wire($('#f'), async () => {
        const g = id => $('#' + id).value.trim(),
            w = role() === 'workshop',
            pw = $('#pw').value;

        const bad = [
            w
                ? form.err('name_fantasy', g('name_fantasy').length < 3 ? 'Informe o nome fantasia.' : '')
                : form.err('name', g('name').length < 3 ? 'Informe seu nome completo.' : ''),
            w && form.err('name_responsible', g('name_responsible').length < 3 ? 'Informe o nome do responsável.' : ''),
            w && form.err('cnpj', v.cnpj(g('cnpj'))),
            form.err('email', v.email(g('email'))),
            form.err('pw', v.password(pw)),
            form.err('pw2', v.confirm($('#pw2').value, pw))
        ];

        if (bad.some(Boolean)) {
            form.focusBad();
            return;
        }

        const d = {
            role: role(),
            email: g('email'),
            password: pw
        };

        if (g('phone_number')) d.phone_number = g('phone_number');

        if (w) {
            d.name_fantasy = g('name_fantasy');
            d.name_responsible = g('name_responsible');

            // Preserva letras e números do CNPJ.
            // O backend realiza a normalização e validação definitiva.
            d.cnpj = g('cnpj').toUpperCase();
        } else {
            d.name = g('name');
        }

        await SAM.api.auth.register(d);

        location.href = w ? 'workshop-setup.html' : 'vehicles.html';
    }, {
        busy: 'Criando conta…',
        alias: { password: 'pw' }
    });
})();
