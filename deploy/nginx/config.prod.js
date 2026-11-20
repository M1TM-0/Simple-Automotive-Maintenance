(() => {
    /*
     * CONFIGURAÇÃO DE PRODUÇÃO (BE-089) — substitui js/config.js na imagem do proxy.
     *
     * Frontend e API na MESMA ORIGEM atrás do Nginx (DP-21): a API fica em
     * <origem>/api/, sem CORS, e os cookies de sessão/CSRF valem sem exceções.
     * API_BASE = origem da própria página; a lógica do api.js não muda.
     *
     * MAP_TILES (opcional, BE-094): provedor de tiles; sem ele vale o OpenStreetMap
     * público (ver frontend/js/config.js). Trocar o provedor exige o host novo em img-src
     * de snippets/csp-frontend.conf.
     */

    window.SAM = Object.assign(window.SAM || {}, {
        config: {
            API_BASE: window.location.origin,
            DRIVER: 'http'
        }
    });
})();
