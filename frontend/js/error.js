(() => {
    /* T09 — Erro (404 / 403 / 500). Sem chamada à API. */

    const { $, esc } = SAM;

    const MSG = {
        403: ['Você não tem acesso a esta área', 'Esta página é de outro perfil de conta. Entre com a conta correta ou volte ao início.'],
        500: ['Algo deu errado', 'Tente de novo em instantes.'],
        404: ['Página não encontrada', 'O endereço pode estar incorreto ou a página não existe mais.']
    };

    const c = new URLSearchParams(location.search).get('code'),
        m = MSG[c] || MSG[404],
        u = SAM.auth.user();

    SAM.ui.title(m[0]);

    $('#view').innerHTML = `
        <div class="wrap">
            <div class="empty empty--big">
                <h1 class="h2">${esc(m[0])}</h1>
                <p>${esc(m[1])}</p>

                <div class="row">
                    <a class="btn btn--solid" href="index.html">Ir para o início</a>

                    ${u ? `
                        <a class="btn" href="${SAM.auth.role(u.role) === 'client' ? 'vehicles.html' : SAM.auth.home(u)}">
                            Ir para meu painel
                        </a>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
})();
