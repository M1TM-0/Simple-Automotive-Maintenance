(() => {
    /* T01 — Home: hero, busca, promoções ativas (da API; some se vazio/erro) e "Como funciona" */

    const { $, esc, I, reveal, IMG, ui } = SAM;

    const view = $('#view');

    /* ---- HOME ---- */

    function home(el) {
        el.innerHTML = `
            <section class="hero">
                <div class="hero__l">
                    <div class="tg">
                        <h1 class="ttl">
                            <span class="blk blk--1" style="--i:0">
                                SIMPLE AUTOMOTIVE
                            </span>

                            <span class="blk blk--2" style="--i:1">
                                MAINTENANCE
                            </span>

                            <span class="blk blk--s" style="--i:2">
                                YOUR CAR • YOUR CARE
                            </span>

                            <span class="blk blk--b">
                                SAM
                            </span>
                        </h1>

                        <p class="lead">
                            Find trusted workshops, compare automotive services and manage your vehicle maintenance — all in one place.
                        </p>
                    </div>

                    <form class="search hsearch" action="map.html" role="search">
                        ${I.s}

                        <input
                            name="q"
                            placeholder="Buscar oficina ou serviço"
                            aria-label="Buscar oficina ou serviço"
                            maxlength="100"
                        >

                        <button class="ib" aria-label="Buscar" title="Buscar">${I.send}</button>
                    </form>

                    <div class="row">
                        <a class="btn btn--solid" href="map.html">
                            Encontrar oficina
                        </a>

                        <a class="btn" href="register.html?role=oficina">
                            Sou oficina
                        </a>
                    </div>
                </div>

                <div class="hero__r">
                    <img
                        class="scene"
                        src="${IMG.hero}"
                        alt="Dois carros esportivos brancos em um túnel escuro com luz rosada"
                        fetchpriority="high"
                    >
                </div>
            </section>

            <div id="promos"></div>

            <section class="sec rv">
                <h2 class="h2">Como funciona</h2>

                <ol class="steps">
                    <li>
                        <b>Encontre a oficina</b>
                        <br>
                        <span class="muted">
                            Filtre por serviço e veja quem atende perto de você.
                        </span>
                    </li>

                    <li>
                        <b>Converse e aprove o orçamento</b>
                        <br>
                        <span class="muted">
                            Envie seu veículo pelo chat e aceite ou recuse o valor.
                        </span>
                    </li>

                    <li>
                        <b>Acompanhe o serviço</b>
                        <br>
                        <span class="muted">
                            Veja cada etapa até a entrega e guarde o histórico.
                        </span>
                    </li>
                </ol>
            </section>

            <div style="height:56px"></div>
        `;

        reveal(el);

        promos();
    }

    /* promoções e divulgações em execução; sem itens ou com erro: seção oculta, sem aviso */

    async function promos() {
        try {
            const r = await SAM.api.promotions.active();

            if (!r.results.length) return;

            $('#promos').innerHTML = `
                <section class="sec rv">
                    <h2 class="h2">Promoções ativas</h2>
                    <div class="cg" id="pcg">${r.results.map(p => ui.promoCard(p)).join('')}</div>
                </section>
            `;

            ui.bindReport($('#pcg'));
            reveal($('#promos'));
        } catch (e) {}
    }

    home(view);
    ui.title('HOME');
})();