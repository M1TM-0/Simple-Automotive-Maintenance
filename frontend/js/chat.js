(() => {
    /* T07 — Chat (Cliente e Oficina): só texto, polling a cada 5 s (P7). Orçamento NÃO se aprova aqui. */

    const { $, $$, esc, I, car, fm, lbl, ui } = SAM;

    if (!SAM.auth.require()) return;

    ui.title('CHAT');

    const user = SAM.auth.user(),
        isW = user.role === 'workshop',
        local = SAM.config.DRIVER !== 'http',
        qs = new URLSearchParams(location.search),
        view = $('#view');

    let chats = [], cur = null, msgs = [], stop = null, sending = false;

    const av = c => `
        <span class="avs ${c && c.photo ? '' : 'avs--a'}" aria-hidden="true">
            ${c && c.photo ? `<img src="${ui.url(c.photo)}" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%">` : '<svg viewBox="0 0 24 24"><circle cx="12" cy="9" r="4"/><path d="M4 21c0-4.5 3.6-7 8-7s8 2.5 8 7z"/></svg>'}
        </span>
    `;

    const when = m => m.at ? fm.time(m.at) : (m.label || '');

    const listTime = c => {
        if (!c.last_at) return c.last_label || '';

        return new Date(c.last_at).toDateString() === new Date().toDateString() ? fm.time(c.last_at) : fm.date(c.last_at).slice(0, 5);
    };

    /* ---------- lista ---------- */

    function side(f = '') {
        $('#cl').innerHTML = chats
            .filter(x => x.name.toLowerCase().includes(f))
            .map(x => `
                <li>
                    <a class="conv ${cur && x.id === cur.id ? 'is-on' : ''}" href="chat.html?id=${encodeURIComponent(x.id)}">
                        ${av(x)}

                        <span class="tx">
                            <b>${esc(x.name)}</b>
                            <small>${esc(x.last_message || 'Nova conversa')}</small>
                        </span>

                        <time>${esc(listTime(x))}</time>

                        ${x.unread ? `<span class="bdg"><span class="sr">${x.unread} não lidas</span><span aria-hidden="true">${x.unread}</span></span>` : ''}
                    </a>
                </li>
            `).join('') || '<li class="empty">Nenhuma conversa encontrada.</li>';
    }

    /* ---------- mensagens ---------- */

    const bubble = m => `
        <div class="m ${m.mine ? 'm--me' : ''}">
            ${esc(m.content).replace(/\n/g, '<br>')}
            <time ${m.at ? `datetime="${esc(m.at)}" title="${esc(fm.dt(m.at))}"` : ''}>
                ${esc(when(m))}${m.mine && m.status ? ` · <span>${esc(lbl('status_message', m.status))}</span>` : ''}
            </time>
        </div>
    `;

    function draw(anim) {
        const box = $('#msgs'),
            near = box.scrollHeight - box.scrollTop - box.clientHeight < 80;

        box.innerHTML = msgs.length
            ? msgs.map(bubble).join('')
            : '<p class="empty">Envie a primeira mensagem para iniciar a conversa.</p>';

        if (anim && box.lastElementChild) box.lastElementChild.classList.add('new');

        if (anim || near) box.scrollTop = box.scrollHeight;
    }

    /* cabeçalho: stepper, link do atendimento e avisos (o orçamento é respondido em T14) */

    function head() {
        const o = cur.open_attendance;

        $('#stp').innerHTML = o ? ui.stepper(o.status_attendance) : '';

        $('#hl').innerHTML = o
            ? `<a class="btn" href="${isW ? 'w-attendance.html' : 'attendance.html'}?id=${encodeURIComponent(o.id)}">Ver atendimento</a>`
            : '';

        $('#cn').innerHTML = !o ? ''
            : !isW && o.status_attendance === 'waiting_approval'
                ? `<p class="note chat__n" role="status">A oficina enviou um orçamento. <a href="attendance.html?id=${encodeURIComponent(o.id)}">Ver e responder</a></p>`
                : isW && ['requested', 'budgeted'].includes(o.status_attendance)
                    ? `<p class="note chat__n"><a class="btn btn--solid" href="w-budget.html?attendance=${encodeURIComponent(o.id)}">Criar orçamento</a></p>`
                    : '';
    }

    /* ---------- atalhos (viram TEXTO editável no campo) ---------- */

    function insert(t) {
        const i = $('#mi');

        i.value = (i.value ? i.value + '\n' : '') + t;
        i.focus();
        grow();
        $('#pop').hidden = true;
    }

    async function shortcuts() {
        if (isW) return;

        try {
            let r = await SAM.api.vehicles.list(),
                vs = r.results;

            for (let i = 0; r.next && i < 10; i++) {
                r = await SAM.api.vehicles.list({ page: SAM.api.pageOf(r.next) });
                vs = vs.concat(r.results);
            }

            if (!vs.length) return;

            const hs = (await Promise.all(vs.slice(0, 5).map(v =>
                SAM.api.vehicles.history(v.id).then(h => h.results.map(x => ({ x, v }))).catch(() => [])
            ))).flat().sort((a, b) => String(b.x.date_maintenance).localeCompare(String(a.x.date_maintenance)));

            const pop = $('#pop'),
                car1 = $('[data-pop=car]'),
                hist = $('[data-pop=hist]');

            car1.hidden = false;
            car1.onclick = () => {
                pop.innerHTML = '<h3>Enviar veículo</h3>' + vs.map(v => `<button type="button" data-v="${esc(v.id)}">${esc(v.brand + ' ' + v.model)} · ${esc(fm.plate(v.plate))}</button>`).join('');
                pop.hidden = !pop.hidden;
            };

            if (hs.length) {
                hist.hidden = false;
                hist.onclick = () => {
                    pop.innerHTML = '<h3>Compartilhar histórico</h3>' + hs.slice(0, 6).map((h, i) => `<button type="button" data-h="${i}">${esc(fm.date(h.x.date_maintenance))} · ${esc(h.x.description)}</button>`).join('');
                    pop.hidden = !pop.hidden;
                };
            }

            pop.onclick = e => {
                const b = e.target.closest('button');

                if (!b) return;

                if (b.dataset.v) {
                    const v = vs.find(x => String(x.id) === b.dataset.v);

                    insert(`Veículo: ${v.brand} ${v.model} ${v.year_model} · ${fm.plate(v.plate)}${v.mileage_km != null ? ' · ' + SAM.km(v.mileage_km) : ''}`);
                } else {
                    const h = hs[+b.dataset.h];

                    insert(`Histórico: ${fm.date(h.x.date_maintenance)} · ${h.x.description} (${h.v.brand} ${h.v.model})`);
                }
            };
        } catch (e) {}
    }

    /* ---------- polling ---------- */

    async function pull() {
        if (!cur) return;

        /* busca a partir da mais antiga das minhas mensagens ainda não lidas (atualiza Enviada → Entregue → Lida) */

        const last = msgs[msgs.length - 1],
            pend = msgs.find(m => m.mine && m.status !== 'read' && m.at),
            since = pend ? new Date(Date.parse(pend.at) - 1).toISOString() : last && last.at,
            r = await SAM.api.chats.messages(cur.id, since);

        let changed = false,
            fresh = false;

        r.results.forEach(m => {
            const i = msgs.findIndex(x => String(x.id) === String(m.id));

            if (i < 0) {
                msgs.push(m);
                changed = true;
                fresh = fresh || !m.mine;
            } else if (msgs[i].status !== m.status) {
                msgs[i] = m;
                changed = true;
            }
        });

        if (changed) draw(fresh);

        if (fresh) SAM.api.chats.read(cur.id).catch(() => {});

        const c = await SAM.api.chats.get(cur.id);

        cur = Object.assign(cur, c, { unread: 0 });
        head();

        const l = await SAM.api.chats.list();

        chats = l.results.map(x => (cur && x.id === cur.id ? Object.assign(x, { unread: 0 }) : x));
        side($('#cq').value.trim().toLowerCase());
    }

    /* ---------- campo de texto ---------- */

    function grow() {
        const i = $('#mi');

        i.style.height = 'auto';
        i.style.height = Math.min(i.scrollHeight, 120) + 'px';
    }

    async function send() {
        const i = $('#mi'),
            t = i.value.trim(),
            e = $('#me');

        e.textContent = '';

        if (!t) {
            e.textContent = 'Escreva uma mensagem antes de enviar.';
            i.focus();
            return;
        }

        if (t.length > 2000) {
            e.textContent = 'A mensagem pode ter até 2000 caracteres.';
            return;
        }

        if (sending) return;

        sending = true;
        $('#sb').disabled = true;

        try {
            const m = await SAM.api.chats.send(cur.id, t);

            msgs.push(m);
            i.value = '';
            grow();
            draw(true);

            cur.last_message = t;
            cur.last_at = m.at;
            cur.last_label = m.label;
            side($('#cq').value.trim().toLowerCase());
        } catch (x) {
            e.textContent = x.detail || 'Não foi possível enviar. Tente de novo.';
        }

        sending = false;
        $('#sb').disabled = false;
        i.focus();
    }

    /* ---------- página ---------- */

    function empty() {
        view.innerHTML = `<div class="wrap">${ui.emptyHtml(isW
            ? { title: 'Nenhuma conversa ainda', text: 'As conversas aparecem quando um cliente entrar em contato.' }
            : { title: 'Nenhuma conversa ainda', text: 'Encontre uma oficina no mapa e toque em CHAT para iniciar um atendimento.', cta: { href: 'map.html', label: 'Encontrar oficina' } })}</div>`;
    }

    async function open(c) {
        cur = c;

        view.innerHTML = `
            <h1 class="sr">Conversas</h1>

            <div class="chat ${qs.get('id') ? 'chat--open' : ''}">
                <aside class="chat__side">
                    <label class="search search--s">
                        ${I.s}
                        <input id="cq" placeholder="Buscar conversa" aria-label="Buscar conversa">
                    </label>

                    <ul id="cl"></ul>
                </aside>

                <section class="chat__main">
                    <header class="chat__h">
                        <a class="back" href="chat.html" aria-label="Voltar às conversas">‹</a>
                        ${av(c)}
                        <div><b>${esc(c.name)}</b></div>
                        <span id="hl" style="margin-left:auto"></span>
                    </header>

                    <div id="stp"></div>
                    <div id="cn"></div>

                    <div class="msgs" id="msgs" role="log" aria-live="polite" aria-label="Mensagens"></div>

                    <div class="pop" id="pop" hidden></div>

                    <p class="ferr chat__e" id="me" role="alert"></p>

                    <form class="bar" id="bar" novalidate>
                        <textarea id="mi" rows="1" maxlength="2000" placeholder="Escreva uma mensagem" aria-label="Mensagem" autocomplete="off"></textarea>

                        ${isW ? '' : `
                            <button type="button" class="ib" data-pop="hist" hidden aria-label="Compartilhar histórico de manutenção" title="Compartilhar histórico">${I.doc}</button>
                            <button type="button" class="ib" data-pop="car" hidden aria-label="Enviar um dos seus veículos" title="Enviar veículo">${I.car}</button>
                        `}

                        <button class="ib" id="sb" aria-label="Enviar mensagem" title="Enviar">${I.send}</button>
                    </form>
                </section>
            </div>
        `;

        side();
        head();

        $('#cq').addEventListener('input', e => side(e.target.value.trim().toLowerCase()));

        $('#bar').addEventListener('submit', e => {
            e.preventDefault();
            send();
        });

        $('#mi').addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
            }
        });

        $('#mi').addEventListener('input', grow);

        const ask = qs.get('ask');

        if (ask) {
            $('#mi').value = `Olá! Gostaria de saber sobre: ${ask}`;
            grow();
        }

        shortcuts();

        try {
            const r = await SAM.api.chats.messages(c.id);

            msgs = r.results;
        } catch (e) {
            $('#msgs').innerHTML = `<p class="ferr" role="alert">${esc(e.detail || 'Não foi possível carregar as mensagens.')}</p>`;
            return;
        }

        draw();
        SAM.api.chats.read(c.id).catch(() => {});

        c.unread = 0;
        side();

        if (!local) stop = ui.poll(pull, 5000, { wait: true });
    }

    ui.load(view, () => SAM.api.chats.list(), async r => {
        chats = r.results;

        const id = qs.get('id');

        let c = id ? chats.find(x => String(x.id) === String(id)) : chats[0];

        if (!c && id) {
            try {
                c = await SAM.api.chats.get(id);
                chats.unshift(c);
            } catch (e) {
                ui.fail(view, e, () => location.reload());
                return;
            }
        }

        if (!c) return empty();

        await open(c);
    });
})();
