(() => {
    /*
     * UI compartilhada: helpers, ícones, toast, navegação
     */

    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => [...r.querySelectorAll(s)];

    const esc = s =>
        String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[c]));

    const fmt = d => d.split('-').reverse().join('/');

    const brl = n =>
        n.toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL'
        });

    const km = n => n.toLocaleString('pt-BR') + ' km';

    const toast = m => {
        const t = document.createElement('div');

        t.className = 'toast';
        t.textContent = m;

        $('#toasts').append(t);

        setTimeout(() => t.remove(), 2800);
    };

    const now = () =>
        new Date().toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit'
        });

    const car = (c = '#e9e6df', w = '') => `
        <svg
            viewBox="0 0 120 56"
            ${w}
            aria-hidden="true"
        >
            <path
                d="M6 38c0-8 6-10 14-12l14-12c4-3 8-4 14-4h22c8 0 14 5 20 12l12 4c6 2 8 5 8 12v4H6z"
                fill="${c}"
            />

            <path
                d="M40 16h22l14 12H34z"
                fill="#1c1c1c"
                opacity=".55"
            />

            <circle cx="32" cy="44" r="9" fill="#1c1c1c" />
            <circle cx="92" cy="44" r="9" fill="#1c1c1c" />
        </svg>
    `;

    const I = {
        s: `
            <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                aria-hidden="true"
            >
                <circle cx="11" cy="11" r="7" />
                <path d="M20 20l-4-4" />
            </svg>
        `,

        doc: `
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M6 2h8l4 4v16H6z" />
                <path d="M14 2v4h4" />
            </svg>
        `,

        car: `
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linejoin="round"
                aria-hidden="true"
            >
                <path d="M3 16v-4l2-5h14l2 5v4zM3 12h18" />
                <circle cx="7.5" cy="16" r="1.5" />
                <circle cx="16.5" cy="16" r="1.5" />
            </svg>
        `,

        send: `
            <svg
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden="true"
            >
                <path d="M3 20l18-8L3 4v6l11 2-11 2z" />
            </svg>
        `,

        clock: `
            <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                aria-hidden="true"
            >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
            </svg>
        `,

        pin: `
            <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                aria-hidden="true"
            >
                <path d="M12 22s7-6.5 7-12a7 7 0 10-14 0c0 5.500 7 12 7 12z" />
                <circle cx="12" cy="10" r="2.500" />
            </svg>
        `,

        tool: `
            <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                aria-hidden="true"
            >
                <path d="M14 6a4 4 0 005 5l-9 9-3-3 9-9a4 4 0 00-2-2z" />
            </svg>
        `
    };

    const reveal = el => {
        const io = new IntersectionObserver(
            es => es.forEach(x => {
                if (x.isIntersecting) {
                    x.target.classList.add('on');
                    io.unobserve(x.target);
                }
            }),
            {
                threshold: .15
            }
        );

        $$('.rv', el).forEach(n => io.observe(n));
    };

    function pill() {
        const n = $('#nav');
        const a = $('[aria-current=page]', n);

        if (!a) return;

        n.style.setProperty('--x', a.offsetLeft + 'px');
        n.style.setProperty('--w', a.offsetWidth + 'px');
    }

    addEventListener('load', () => {
        pill();

        document.fonts && document.fonts.ready.then(pill);
    });

    addEventListener('resize', pill);

    window.SAM = Object.assign(
        window.SAM || {},
        {
            $,
            $$,
            esc,
            fmt,
            brl,
            km,
            toast,
            now,
            car,
            I,
            reveal,
            pill
        }
    );
})();