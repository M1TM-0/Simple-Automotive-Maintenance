(() => {
    /*
     * ENUMS: rótulos pt-BR dos valores do banco (init.sql).
     * Único lugar com esses textos: as páginas usam SAM.lbl / SAM.opts.
     */

    const L = {
        status_attendance: {
            requested: 'Solicitado',
            budgeted: 'Orçamento em elaboração',
            waiting_approval: 'Aguardando aprovação',
            approved: 'Aprovado',
            in_progress: 'Em manutenção',
            completed: 'Concluído',
            delivered: 'Entregue',
            canceled: 'Cancelado'
        },
        status_budget: {
            pending: 'Pendente',
            approved: 'Aprovado',
            rejected: 'Recusado',
            cancelled: 'Cancelado',
            expired: 'Expirado'
        },
        item_type: {
            service: 'Serviço',
            product: 'Peça/produto',
            labor: 'Mão de obra',
            other: 'Outro'
        },
        execution_status: {
            pending: 'Pendente',
            executed: 'Executado',
            not_executed: 'Não executado'
        },
        fuel: {
            gasolina: 'Gasolina',
            etanol: 'Etanol',
            diesel: 'Diesel',
            flex: 'Flex',
            eletrico: 'Elétrico',
            hibrido: 'Híbrido',
            gnv: 'GNV',
            outro: 'Outro'
        },
        exchange: {
            manual: 'Manual',
            automatico: 'Automático',
            automatizado: 'Automatizado',
            dupla_embreagem: 'Dupla embreagem',
            variavel: 'Variável (CVT)',
            outro: 'Outro'
        },
        type_establishment: {
            oficina: 'Oficina',
            borracharia: 'Borracharia',
            posto_combustivel: 'Posto de combustível',
            loja_autopecas: 'Loja de autopeças',
            centro_automotivo: 'Centro automotivo',
            concessionaria: 'Concessionária',
            lava_jato: 'Lava-jato',
            outro: 'Outro'
        },
        reason: {
            inappropriate_content: 'Conteúdo inadequado',
            offensive_language: 'Linguagem ofensiva',
            harassment: 'Assédio',
            spam: 'Spam',
            false_information: 'Informação falsa',
            fraud: 'Fraude',
            other: 'Outro (descrição obrigatória)'
        },
        effective_status: {
            active: 'No ar',
            scheduled: 'Agendada',
            inactive: 'Desativada',
            expired: 'Encerrada'
        },
        status_solicitation: {
            pending: 'Em análise',
            approved: 'Aprovado no catálogo global',
            rejected: 'Rejeitado'
        },
        day_of_week: {
            1: 'Segunda',
            2: 'Terça',
            3: 'Quarta',
            4: 'Quinta',
            5: 'Sexta',
            6: 'Sábado',
            7: 'Domingo'
        },
        status_account: {
            active: 'Ativa',
            inactive: 'Inativa',
            blocked: 'Bloqueada'
        },
        status_review: {
            published: 'Publicada',
            hidden: 'Oculta',
            under_review: 'Em análise'
        },
        payment_status: {
            pending: 'Pendente',
            paid: 'Pago',
            failed: 'Falhou',
            refunded: 'Reembolsado'
        },
        status_advertisement: {
            pending: 'Pendente',
            active: 'No ar',
            completed: 'Concluída',
            cancelled: 'Cancelada',
            canceled: 'Cancelada'
        },
        status_denunciation: {
            pending: 'Pendente',
            in_review: 'Em análise',
            upheld: 'Procedente',
            dismissed: 'Improcedente'
        },
        target_type: {
            review: 'Avaliação',
            promotion: 'Promoção',
            advertisement: 'Divulgação'
        },
        type_discount: {
            percentage: 'Percentual',
            fixed: 'Valor fixo'
        },
        status_message: {
            sent: 'Enviada',
            delivered: 'Entregue',
            read: 'Lida'
        }
    };

    /* Stepper de 5 etapas (C04). "Aguardando peça" não existe no banco. */

    const STEPPER = [
        'Orçamento',
        'Aguardando aprovação',
        'Em manutenção',
        'Concluído',
        'Entregue'
    ];

    const STEP_OF = {
        requested: 0,
        budgeted: 0,
        waiting_approval: 1,
        approved: 2,
        in_progress: 2,
        completed: 3,
        delivered: 4
    };

    /* Grupos usados nos filtros de T13 e nos contadores de T18 */

    const GROUPS = {
        andamento: [
            'requested',
            'budgeted',
            'waiting_approval',
            'approved',
            'in_progress',
            'completed'
        ],
        entregues: ['delivered'],
        cancelados: ['canceled']
    };

    const esc = SAM.esc;

    /* rótulo de um valor; devolve o próprio valor se for desconhecido */

    const lbl = (name, v) =>
        v == null || v === ''
            ? '—'
            : (L[name] && L[name][v]) || String(v);

    /* [{v, l}] na ordem de declaração */

    const list = name =>
        Object.entries(L[name] || {}).map(([v, l]) => ({ v, l }));

    /* <option> escapados; `ph` cria a opção vazia ("Selecione") */

    const opts = (name, sel, ph) =>
        (ph === undefined ? '' : `<option value="">${esc(ph)}</option>`) +
        list(name)
            .map(o => `
                <option
                    value="${esc(o.v)}"
                    ${String(o.v) === String(sel) ? 'selected' : ''}
                >${esc(o.l)}</option>
            `)
            .join('');

    window.SAM = Object.assign(window.SAM || {}, {
        enums: L,
        STEPPER,
        STEP_OF,
        GROUPS,
        lbl,
        list,
        opts
    });
})();
