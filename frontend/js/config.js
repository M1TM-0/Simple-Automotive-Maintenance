(() => {
    /*
     * CONFIGURAÇÃO ÚNICA DA INTERFACE
     *
     * DRIVER 'local' → autenticação, veículos e conversas do cliente ficam no
     *                  localStorage (comportamento original, sem servidor).
     *                  Domínios novos (oficina, atendimentos, orçamentos…)
     *                  respondem API_UNAVAILABLE: não há dados fictícios.
     * DRIVER 'http'  → tudo passa pela API REST (Django + DRF).
     *
     * API_BASE: origem do servidor, sem barra final (ex.: 'http://localhost:8000').
     * Com DRIVER 'http' e API_BASE vazio a interface mostra
     * "O servidor ainda não está disponível".
     *
     * MAP_TILES (opcional, BE-094): provedor de tiles do mapa. Sem ele vale o OpenStreetMap
     * público (https://tile.openstreetmap.org/{z}/{x}/{y}.png, atribuição
     * "© OpenStreetMap contributors"). Para trocar, informe { url, attribution, maxZoom }
     * e acrescente o host em img-src de deploy/nginx/snippets/csp-frontend.conf.
     */

    window.SAM = Object.assign(window.SAM || {}, {
        config: {
            API_BASE: 'http://localhost:8000',
            DRIVER: 'http'
        }
    });
})();
