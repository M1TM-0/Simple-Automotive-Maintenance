#!/usr/bin/env node
/*
 * BE-081 — roda os normalizadores REAIS do frontend (frontend/js/api.js) sobre
 * respostas REAIS da API, gravadas pelo teste de contrato.
 *
 * Uso: node normalizers.js <caminho/do/api.js> <jobs.json>
 *   jobs.json = [{ "name", "role", "call": "chats.list", "args": [...],
 *                  "responses": { "GET /api/chats/": <corpo JSON>, ... } }]
 * Saída (stdout): { "<name>": { "ok": true, "value": <resultado> } | { "ok": false, "error": "..." } }
 *
 * O api.js roda num contexto `vm` próprio por job, com `fetch` respondendo só o que
 * foi gravado (chamada não gravada = erro), DRIVER 'http' e o perfil do job em
 * SAM.auth.user() (usado por normMsg para calcular `mine`).
 */

'use strict';

const fs = require('fs');
const vm = require('vm');

const [apiPath, jobsPath] = process.argv.slice(2);
const source = fs.readFileSync(apiPath, 'utf8');
const jobs = JSON.parse(fs.readFileSync(jobsPath, 'utf8'));

function sandbox(job) {
    const ctx = {
        console, URL, URLSearchParams, FormData, Blob, setTimeout, clearTimeout,
        document: { cookie: 'csrftoken=contrato' },
        location: { pathname: '/pagina.html', search: '', replace() {} }
    };
    ctx.window = ctx;
    ctx.SAM = {
        config: { DRIVER: 'http', API_BASE: 'http://api.test' },
        auth: {
            user: () => ({ role: job.role }),
            setSession() {}, clearSession() {}, logout() {}
        },
        local: {
            err: (status, detail) => Object.assign(new Error(String(detail)), { status, detail })
        }
    };
    ctx.fetch = async (url, options) => {
        const u = new URL(url);
        const key = `${options.method} ${u.pathname}${u.search}`;
        if (!(key in job.responses)) throw new Error('chamada não gravada: ' + key);
        const body = job.responses[key];
        const status = body === null ? 204 : 200;
        return { status, ok: true, json: async () => body };
    };
    vm.createContext(ctx);
    vm.runInContext(source, ctx, { filename: 'api.js' });
    return ctx;
}

(async () => {
    const out = {};
    for (const job of jobs) {
        try {
            const ctx = sandbox(job);
            const fn = job.call.split('.').reduce((o, k) => o[k], ctx.SAM.api);
            const value = await fn(...(job.args || []));
            out[job.name] = { ok: true, value: JSON.parse(JSON.stringify(value === undefined ? null : value)) };
        } catch (e) {
            out[job.name] = { ok: false, error: String(e && e.stack || e) };
        }
    }
    process.stdout.write(JSON.stringify(out));
})();
