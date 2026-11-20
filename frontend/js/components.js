(() => {
    /*
     * COMPONENTES COMPARTILHADOS
     * C01 cabeçalho por perfil (+ sino) · C02 estados · modal · stepper C04
     * tabela responsiva · abas · confirmação inline · polling.
     * Formatadores e helpers de formulário: components-parts.js.
     */

    const { $, $$, esc, I } = SAM,
        A = SAM.auth,
        PAGE = location.pathname.split('/').pop() || 'index.html';

    /* ================= C01 — CABEÇALHO ================= */

    const NAV = {
        client: [
            ['home', 'HOME', 'index.html'],
            ['map', 'MAP', 'map.html'],
            ['chat', 'CHAT', 'chat.html'],
            ['vehicles', 'VEHICLE', 'vehicles.html']
        ],
        workshop: [
            ['home', 'HOME', 'index.html'],
            ['chat', 'CHAT', 'chat.html'],
            ['attendance', 'ATTENDANCE', 'w-attendances.html'],
            ['shop', 'SHOP', 'w-profile.html']
        ],
        /* P5: telas de moderação (T27/T28) só existem se o projeto confirmar o perfil admin */
        admin: [
            ['home', 'HOME', 'index.html']
        ]
    };

    /* página → item ativo do menu, por perfil */

    const CUR = {
        client: {
            'index.html': 'home',
            'map.html': 'map',
            'shop.html': 'map',
            'chat.html': 'chat',
            'vehicles.html': 'vehicles',
            'vehicle.html': 'vehicles',
            'vehicle-new.html': 'vehicles'
        },
        workshop: {
            'index.html': 'home',
            'chat.html': 'chat',
            'w-attendances.html': 'attendance',
            'w-attendance.html': 'attendance',
            'w-budget.html': 'attendance',
            'shop.html': 'shop',
            'w-profile.html': 'shop',
            'w-services.html': 'shop',
            'w-products.html': 'shop',
            'w-promotions.html': 'shop',
            'w-reviews.html': 'shop',
            'w-clients.html': 'shop'
        },
        admin: {
            'index.html': 'home'
        }
    };

    const MENU = {
        client: [
            ['Meus atendimentos', 'attendances.html'],
            ['Favoritos', 'favorites.html'],
            ['Notificações', 'notifications.html'],
            ['Minha conta', 'account.html']
        ],
        workshop: [['Notificações', 'notifications.html']],
        admin: []
    };

    const BELL = `
        <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
        >
            <path d="M6 9a6 6 0 0112 0c0 6 2 7 2 7H4s2-1 2-7" />
            <path d="M10 20a2 2 0 004 0" />
        </svg>
    `;

    function acct(u) {
        if (!u) {
            return '<a class="acct__b" href="login.html">Entrar</a>';
        }

        const items = (MENU[u.role] || [])
            .map(([l, h]) => `
                <li role="none">
                    <a role="menuitem" href="${h}">${esc(l)}</a>
                </li>
            `)
            .join('');

        return `
            ${u.role === 'admin' ? '' : `
                <div class="pop-w">
                    <button
                        type="button"
                        class="bell"
                        id="bell"
                        aria-expanded="false"
                        aria-controls="bellp"
                        aria-label="Notificações"
                        title="Notificações"
                    >
                        ${BELL}
                        <span class="bell__n" id="belln" hidden></span>
                    </button>

                    <div
                        class="menu menu--bell"
                        id="bellp"
                        role="region"
                        aria-label="Notificações recentes"
                        hidden
                    ></div>
                </div>
            `}

            <div class="pop-w">
                <button
                    type="button"
                    class="acct__b acct__u"
                    id="um"
                    aria-haspopup="menu"
                    aria-expanded="false"
                    aria-controls="umenu"
                >
                    ${esc((u.name || 'Conta').split(' ')[0])} ▾
                </button>

                <ul class="menu" id="umenu" role="menu" hidden>
                    ${items}

                    <li role="none">
                        <button type="button" role="menuitem" id="lo">
                            Sair
                        </button>
                    </li>
                </ul>
            </div>
        `;
    }

    /* abre/fecha um popover; Esc e clique fora fecham; foco volta ao botão */

    const ITEMS = '[role=menuitem],.menu__a';

    function popover(btn, pop, onOpen) {
        const close = back => {
            pop.hidden = true;
            btn.setAttribute('aria-expanded', 'false');

            if (back) btn.focus();
        };

        btn.addEventListener('click', () => {
            const open = pop.hidden;

            $$('.menu').forEach(m => {
                if (m !== pop) {
                    m.hidden = true;

                    const b = m.parentElement.querySelector('[aria-expanded]');

                    if (b) b.setAttribute('aria-expanded', 'false');
                }
            });

            pop.hidden = !open;
            btn.setAttribute('aria-expanded', open);

            if (open) {
                if (onOpen) onOpen();

                const f = $(ITEMS, pop);

                if (f) f.focus();
            }
        });

        btn.addEventListener('keydown', e => {
            if (e.key === 'Escape' && !pop.hidden) close(true);
        });

        pop.addEventListener('keydown', e => {
            const it = $$(ITEMS, pop),
                i = it.indexOf(document.activeElement);

            if (e.key === 'Escape') {
                e.stopPropagation();
                close(true);
            } else if (it.length && /^(ArrowDown|ArrowUp|Home|End)$/.test(e.key)) {
                e.preventDefault();

                const n = e.key === 'Home'
                    ? 0
                    : e.key === 'End'
                        ? it.length - 1
                        : (i + (e.key === 'ArrowDown' ? 1 : -1) + it.length) % it.length;

                it[n].focus();
            }
        });

        document.addEventListener('click', e => {
            if (!pop.hidden && !pop.parentElement.contains(e.target)) close();
        });

        return close;
    }

    /* conteúdo do sino: 5 mais recentes + "Ver todas" */

    async function bellOpen(box) {
        box.innerHTML = '<p class="muted menu__s" role="status">Carregando…</p>';

        try {
            const r = await SAM.api.notifications.list({ page: 1 }),
                top = r.results.slice(0, 5);

            box.innerHTML = `
                <h2 class="menu__h">Notificações</h2>

                ${top.length ? `
                    <ul class="nl nl--s">
                        ${top.map(n => `
                            <li class="${n.read_status ? '' : 'is-new'}">
                                <b>${esc(n.title)}</b>
                                <span>${esc(n.message)}</span>
                                <small class="muted">
                                    ${esc(SAM.fm.rel(n.date_creation))}
                                    ${n.read_status ? '' : '· <span>não lida</span>'}
                                </small>
                            </li>
                        `).join('')}
                    </ul>
                ` : '<p class="muted menu__s">Você não tem notificações.</p>'}

                <a class="menu__a" href="notifications.html">
                    Ver todas
                </a>
            `;
        } catch (e) {
            box.innerHTML = `
                <p class="menu__s">
                    ${SAM.api.isUnavailable(e)
                        ? 'O servidor ainda não está disponível.'
                        : esc(e.detail || 'Não foi possível carregar.')}
                </p>

                <a class="menu__a" href="notifications.html">
                    Ver todas
                </a>
            `;
        }
    }

    function header() {
        const el = $('#hdr');

        if (!el) return;

        if (SAM.stopBell) SAM.stopBell();

        const u = A.user(),
            r = u ? u.role : 'client',
            cur = (CUR[r] || CUR.client)[PAGE];

        el.innerHTML = `
            <a
                class="brand"
                href="index.html"
                aria-label="SAM — página inicial"
            >
                <img
                    src="assets/img/logo-sam.png"
                    alt="SAM — Simple Auto Maintenance"
                >
            </a>

            <nav class="nav" id="nav" aria-label="Principal">
                <i class="nav__pill" aria-hidden="true"></i>

                ${(NAV[r] || NAV.client).map(([k, l, h]) => `
                    <a
                        href="${h}"
                        data-r="${k}"
                        ${k === cur ? 'aria-current="page"' : ''}
                    >${l}</a>
                `).join('')}
            </nav>

            <div class="acct" id="acct">${acct(u)}</div>
        `;

        if (u) {
            $('#lo').onclick = () => SAM.api.auth.logout();

            popover($('#um'), $('#umenu'));

            if (u.role !== 'admin') {
                popover($('#bell'), $('#bellp'), () => bellOpen($('#bellp')));

                /* contador de não lidas a cada 60 s (aba visível) */

                const refresh = async () => {
                    const n = await SAM.api.notifications.unreadCount(),
                        b = $('#belln');

                    if (!b) return;

                    b.hidden = !n;
                    b.textContent = n > 99 ? '99+' : n;

                    $('#bell').setAttribute(
                        'aria-label',
                        n ? `Notificações, ${n} não lidas` : 'Notificações'
                    );
                };

                ui.bellRefresh = () => refresh().catch(() => {});

                const stop = ui.poll(refresh, 60000);

                SAM.stopBell = stop;
            }
        }

        SAM.pill();

        if (document.fonts) document.fonts.ready.then(SAM.pill);
    }

    /* ================= C02 — ESTADOS ================= */

    const ui = {};

    ui.loading = (el, n = 3) => {
        el.setAttribute('aria-busy', 'true');

        el.innerHTML = `
            <p class="sr" role="status">Carregando…</p>
            ${'<div class="sk" aria-hidden="true"></div>'.repeat(n)}
        `;
    };

    ui.emptyHtml = o => `
        <div class="empty empty--big">
            <h2>${esc(o.title)}</h2>
            ${o.text ? `<p>${esc(o.text)}</p>` : ''}
            ${o.cta ? `
                <a class="btn btn--solid" href="${esc(o.cta.href)}">
                    ${esc(o.cta.label)}
                </a>
            ` : ''}
        </div>
    `;

    ui.failHtml = e => {
        const off = SAM.api.isUnavailable(e);

        if (e && e.status === 404) {
            return `
                <div class="empty empty--big" role="alert">
                    <h2>${esc(e.title || 'Não encontrado')}</h2>
                    <p>${esc(e.detail || 'O item pode ter sido removido.')}</p>
                    <a class="btn btn--solid" href="index.html">Ir para o início</a>
                </div>
            `;
        }

        return `
            <div class="empty empty--big" role="alert">
                <h2>
                    ${off
                        ? 'O servidor ainda não está disponível'
                        : 'Não foi possível carregar'}
                </h2>

                <p>
                    ${esc(off
                        ? 'Esta tela mostra dados reais e funciona quando o servidor estiver no ar.'
                        : (e && e.detail) || 'Tente de novo em instantes.')}
                </p>

                <button type="button" class="btn btn--solid" data-retry>
                    Tentar de novo
                </button>
            </div>
        `;
    };

    ui.fail = (el, e, retry) => {
        el.removeAttribute('aria-busy');
        el.innerHTML = ui.failHtml(e);

        const b = $('[data-retry]', el);

        if (b && retry) b.onclick = retry;
    };

    /* carregando → task() → draw(resultado) | erro com "Tentar de novo" */

    ui.load = async (el, task, draw) => {
        ui.loading(el);

        try {
            const r = await task();

            el.removeAttribute('aria-busy');
            draw(r);
        } catch (e) {
            ui.fail(el, e, () => ui.load(el, task, draw));
        }
    };

    /* URL de imagem vinda da API: só http(s), caminho relativo ou data:image */

    ui.url = u => {
        if (!u || !/^(https?:\/\/|\/|data:image\/|[\w.-]+\/)/i.test(u)) return '';

        const b = (SAM.config.API_BASE || '').replace(/\/+$/, '');

        return esc(/^\//.test(u) && b ? b + u : u);
    };

    /* ================= STEPPER (C04), BADGE, TABELA ================= */

    ui.stepper = status => {
        if (status === 'canceled') {
            return '<p class="stp stp--no" role="status">Atendimento cancelado</p>';
        }

        const i = SAM.STEP_OF[status];

        if (i === undefined) return '';

        return `
            <ol class="stp" aria-label="Status do atendimento" tabindex="0">
                ${SAM.STEPPER.map((s, j) => `
                    <li
                        class="${j < i ? 'done' : j === i ? 'cur' : ''}"
                        ${j === i ? 'aria-current="step"' : ''}
                    >
                        ${j < i ? '<span class="sr">Concluída: </span>' : ''}
                        ${esc(s)}
                        ${j === 2 && status === 'approved'
                            ? '<small class="stp__sub">Aprovado, aguardando início</small>'
                            : ''}
                    </li>
                `).join('')}
            </ol>
        `;
    };

    /* progresso compacto (cartões de lista): 5 pontos + texto acessível */

    ui.miniStepper = status => {
        if (status === 'canceled') return '<span class="mst mst--no">Cancelado</span>';

        const i = SAM.STEP_OF[status];

        if (i === undefined) return '';

        return `
            <span class="mst" role="img" aria-label="Etapa ${i + 1} de 5: ${esc(SAM.STEPPER[i])}">
                ${SAM.STEPPER.map((s, j) => `<i class="${j <= i ? 'on' : ''}"></i>`).join('')}
            </span>
        `;
    };

    const TONE = {
        status_attendance: {
            requested: 'info',
            budgeted: 'info',
            waiting_approval: 'warn',
            approved: 'ok',
            in_progress: 'ok',
            completed: 'ok',
            delivered: 'done',
            canceled: 'bad'
        },
        status_budget: {
            pending: 'warn',
            approved: 'ok',
            rejected: 'bad',
            cancelled: 'bad',
            expired: 'bad'
        },
        execution_status: {
            pending: 'warn',
            executed: 'ok',
            not_executed: 'bad'
        },
        effective_status: {
            active: 'ok',
            scheduled: 'info',
            inactive: 'info',
            expired: 'done'
        },
        status_solicitation: {
            pending: 'warn',
            approved: 'ok',
            rejected: 'bad'
        },
        status_review: {
            published: 'ok',
            hidden: 'bad',
            under_review: 'warn'
        },
        payment_status: {
            pending: 'warn',
            paid: 'ok',
            failed: 'bad',
            refunded: 'info'
        },
        status_advertisement: {
            pending: 'warn',
            active: 'ok',
            completed: 'done',
            cancelled: 'bad',
            canceled: 'bad'
        },
        status_denunciation: {
            pending: 'warn',
            in_review: 'info',
            upheld: 'ok',
            dismissed: 'done'
        }
    };

    /* selo sempre com TEXTO (nada depende só de cor) */

    ui.badge = (name, v) => `
        <span class="sb sb--${(TONE[name] || {})[v] || 'info'}">
            ${esc(SAM.lbl(name, v))}
        </span>
    `;

    /* tabela de dados; abaixo de 640 px cada linha vira cartão (data-label) */

    ui.table = ({ caption, cols, rows, rowHead }) => `
        <div class="tbl-w">
            <table class="tbl">
                <caption class="sr">${esc(caption)}</caption>

                <thead>
                    <tr>
                        ${cols.map(c => `<th scope="col">${esc(c.h)}</th>`).join('')}
                    </tr>
                </thead>

                <tbody>
                    ${rows.map(r => `
                        <tr>
                            ${cols.map((c, i) => {
                                const t = rowHead && i === 0 ? 'th' : 'td';

                                return `
                                    <${t}
                                        ${t === 'th' ? 'scope="row"' : ''}
                                        data-label="${esc(c.h)}"
                                        class="${c.cls || ''}"
                                    >${c.c(r)}</${t}>
                                `;
                            }).join('')}
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;

    /* subnavegação da área da oficina (T21–T26) */

    ui.subnav = cur => `
        <nav class="subnav" aria-label="Área da oficina">
            ${[
                ['profile', 'Perfil', 'w-profile.html'],
                ['services', 'Serviços', 'w-services.html'],
                ['products', 'Produtos', 'w-products.html'],
                ['promotions', 'Promoções', 'w-promotions.html'],
                ['reviews', 'Avaliações', 'w-reviews.html'],
                ['clients', 'Clientes', 'w-clients.html']
            ].map(([k, l, h]) => `
                <a
                    href="${h}"
                    ${k === cur ? 'aria-current="page"' : ''}
                >${l}</a>
            `).join('')}
        </nav>
    `;

    ui.moreBtn = () => `
        <div class="more">
            <button type="button" class="btn" data-more>Carregar mais</button>
        </div>
    `;

    /* ================= ABAS (role=tablist, setas do teclado) ================= */

    /*
     * root: .tabs com <button role="tab" data-tab="chave">.
     * Devolve { select(chave) }. `cb(chave)` desenha o painel.
     */

    ui.tabs = (root, cb) => {
        const all = () => $$('[role=tab]', root);

        const sel = (b, focus) => {
            all().forEach(t => {
                t.setAttribute('aria-selected', t === b);
                t.tabIndex = t === b ? 0 : -1;
            });

            root.style.setProperty('--x', b.offsetLeft + 'px');
            root.style.setProperty('--w', b.offsetWidth + 'px');

            if (focus) b.focus();

            cb(b.dataset.tab, b);
        };

        root.addEventListener('click', e => {
            const b = e.target.closest('[role=tab]');

            if (b) sel(b);
        });

        root.addEventListener('keydown', e => {
            const t = all(),
                i = t.indexOf(document.activeElement);

            if (i < 0 || !/^(ArrowRight|ArrowLeft|Home|End)$/.test(e.key)) return;

            e.preventDefault();

            sel(
                t[
                    e.key === 'Home'
                        ? 0
                        : e.key === 'End'
                            ? t.length - 1
                            : (i + (e.key === 'ArrowRight' ? 1 : -1) + t.length) % t.length
                ],
                true
            );
        });

        const api = {
            select: k => {
                const b = all().find(t => t.dataset.tab === k) || all()[0];

                if (b) sel(b);
            }
        };

        addEventListener('resize', () => {
            const b = all().find(t => t.getAttribute('aria-selected') === 'true');

            if (b) {
                root.style.setProperty('--x', b.offsetLeft + 'px');
                root.style.setProperty('--w', b.offsetWidth + 'px');
            }
        });

        return api;
    };

    /* ================= MODAL ================= */

    const stack = [];

    /*
     * ui.modal({ title, body, wide }) → { box, body, close }
     * role=dialog + aria-modal, foco preso, Esc fecha, foco volta à origem.
     */

    ui.modal = o => {
        const from = document.activeElement,
            id = 'mt' + Date.now().toString(36) + stack.length,
            bk = document.createElement('div');

        bk.className = 'modal';

        bk.innerHTML = `
            <div
                class="modal__box ${o.wide ? 'modal__box--w' : ''}"
                role="dialog"
                aria-modal="true"
                aria-labelledby="${id}"
            >
                <header class="modal__h">
                    <h2 id="${id}">${esc(o.title)}</h2>

                    <button
                        type="button"
                        class="ib"
                        data-x
                        aria-label="Fechar"
                        title="Fechar"
                    >×</button>
                </header>

                <div class="modal__b">${o.body || ''}</div>
            </div>
        `;

        document.body.append(bk);

        const bg = ['#hdr', '#view'].map(s => $(s)).filter(Boolean);

        bg.forEach(n => n.setAttribute('inert', ''));
        document.documentElement.classList.add('modal-open');

        const box = $('.modal__box', bk),
            m = { box, body: $('.modal__b', bk), el: bk };

        const foc = () => $$(
            'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
            box
        ).filter(n => !n.closest('[hidden]'));

        m.close = () => {
            if (!bk.isConnected) return;

            bk.remove();
            stack.splice(stack.indexOf(m), 1);

            if (!stack.length) {
                bg.forEach(n => n.removeAttribute('inert'));
                document.documentElement.classList.remove('modal-open');
            }

            if (from && from.isConnected) from.focus();

            if (o.onClose) o.onClose();
        };

        bk.addEventListener('keydown', e => {
            if (stack[stack.length - 1] !== m) return;

            if (e.key === 'Escape') {
                e.stopPropagation();
                m.close();
            } else if (e.key === 'Tab') {
                const f = foc();

                if (!f.length) return;

                const a = f[0],
                    z = f[f.length - 1];

                if (e.shiftKey && document.activeElement === a) {
                    e.preventDefault();
                    z.focus();
                } else if (!e.shiftKey && document.activeElement === z) {
                    e.preventDefault();
                    a.focus();
                }
            }
        });

        bk.addEventListener('mousedown', e => {
            if (e.target === bk) m.close();
        });

        $('[data-x]', bk).onclick = m.close;

        stack.push(m);

        const f = foc().filter(n => !n.hasAttribute('data-x'))[0] || $('[data-x]', bk);

        if (f) f.focus();

        return m;
    };

    /* ================= CONFIRMAÇÃO INLINE (.cf, role=alertdialog) ================= */

    /*
     * ui.confirm(host, { text, yes, no, onYes })
     * onYes pode ser async; se rejeitar mostra e.detail dentro do .cf.
     */

    ui.confirm = (host, o) => {
        host.innerHTML = `
            <div
                class="cf"
                role="alertdialog"
                aria-label="${esc(o.label || 'Confirmar')}"
            >
                <span>${esc(o.text)}</span>

                <p class="err" role="alert" data-cerr></p>

                <div class="acts">
                    <button
                        class="btn ${o.danger === false ? 'btn--solid' : 'btn--danger'}"
                        type="button"
                        data-yes
                    >${esc(o.yes || 'Confirmar')}</button>

                    <button class="btn" type="button" data-no>
                        ${esc(o.no || 'Cancelar')}
                    </button>
                </div>
            </div>
        `;

        const yes = $('[data-yes]', host),
            no = $('[data-no]', host),
            out = $('[data-cerr]', host);

        no.onclick = () => {
            host.innerHTML = '';

            if (o.back) o.back.focus();
        };

        yes.onclick = async () => {
            yes.disabled = true;
            no.disabled = true;
            out.textContent = '';

            try {
                await o.onYes();
            } catch (e) {
                out.textContent = (e && e.detail) || 'Não foi possível concluir.';
                yes.disabled = false;
                no.disabled = false;
            }
        };

        no.focus();
    };

    /* ================= POLLING (só com a aba visível, recuo em erro) ================= */

    ui.poll = (fn, ms, o = {}) => {
        let t,
            fails = 0,
            off = false;

        const stop = () => {
            off = true;
            clearTimeout(t);
            document.removeEventListener('visibilitychange', vis);
        };

        const tick = async () => {
            if (off) return;

            if (document.visibilityState === 'visible') {
                try {
                    await fn();
                    fails = 0;
                } catch (e) {
                    if (SAM.api.isUnavailable(e)) return stop();

                    fails++;
                }
            }

            if (!off) t = setTimeout(tick, ms * Math.min(8, 2 ** fails));
        };

        function vis() {
            if (document.visibilityState === 'visible' && !off) {
                clearTimeout(t);
                tick();
            }
        }

        document.addEventListener('visibilitychange', vis);

        if (o.wait) t = setTimeout(tick, ms);
        else tick();

        return stop;
    };

    ui.title = t => {
        document.title = 'SAM — ' + t;
    };

    ui.header = header;

    window.SAM = Object.assign(window.SAM || {}, { ui });

    header();
})();
