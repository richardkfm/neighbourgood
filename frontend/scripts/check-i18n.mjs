#!/usr/bin/env node
// Verifies i18n integrity: locale files parse, share en.json's key set, and every
// statically referenced $t('key') exists in en.json. Lists dynamic keys for review.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const localeDir = path.join(root, 'src/lib/i18n/locales');
let errors = 0;
const fail = (m) => {
	errors++;
	console.error('ERROR ' + m);
};

function flatten(obj, prefix = '', out = {}) {
	for (const [k, v] of Object.entries(obj)) {
		const key = prefix ? `${prefix}.${k}` : k;
		if (v && typeof v === 'object') flatten(v, key, out);
		else out[key] = v;
	}
	return out;
}

const locales = {};
for (const f of fs.readdirSync(localeDir).filter((f) => f.endsWith('.json')).sort()) {
	try {
		locales[f.replace('.json', '')] = flatten(JSON.parse(fs.readFileSync(path.join(localeDir, f), 'utf8')));
	} catch (e) {
		fail(`${f} does not parse: ${e.message}`);
	}
}
const en = locales.en;
if (!en) {
	fail('en.json missing');
	process.exit(1);
}
const enKeys = new Set(Object.keys(en));

for (const [loc, flat] of Object.entries(locales)) {
	const keys = new Set(Object.keys(flat));
	const missing = [...enKeys].filter((k) => !keys.has(k));
	const extra = [...keys].filter((k) => !enKeys.has(k));
	console.log(`${loc}: ${keys.size} keys, missing ${missing.length}, extra ${extra.length}`);
	missing.slice(0, 5).forEach((k) => fail(`${loc} missing ${k}`));
	extra.slice(0, 5).forEach((k) => fail(`${loc} has extra ${k}`));
}

function walk(dir, out = []) {
	for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
		const p = path.join(dir, e.name);
		if (e.isDirectory()) walk(p, out);
		else if (/\.(svelte|ts|js)$/.test(e.name)) out.push(p);
	}
	return out;
}

const staticRe = /(?<![\w.])\$?(?:t|_|msg)\(\s*(['"])([a-zA-Z0-9_.]+)\1(\s*\+)?/g;
const dynRe = /(?<![\w.])\$?(?:t|_|msg)\(\s*`([^`]*\$\{[^`]*)`/g;
const dynamic = new Map();
let used = 0;
for (const file of walk(path.join(root, 'src'))) {
	const src = fs.readFileSync(file, 'utf8');
	const rel = path.relative(root, file);
	for (const m of src.matchAll(staticRe)) {
		if (m[3] || m[2].endsWith('.')) {
			const matches = [...enKeys].filter((k) => k.startsWith(m[2]));
			dynamic.set(`${rel}: '${m[2]}' + ...`, matches);
			if (!matches.length) fail(`${rel}: dynamic prefix '${m[2]}' matches nothing in en.json`);
			continue;
		}
		used++;
		if (!enKeys.has(m[2])) fail(`${rel}: unknown key '${m[2]}'`);
	}
	for (const m of src.matchAll(dynRe)) {
		const pattern = m[1];
		const re = new RegExp(
			'^' + pattern.replace(/[.*+?^()|[\]\\]/g, '\\$&').replace(/\$\{[^}]*\}/g, '[^.]+') + '$'
		);
		const matches = [...enKeys].filter((k) => re.test(k));
		dynamic.set(`${rel}: \`${pattern}\``, matches);
		if (!matches.length) fail(`${rel}: dynamic key \`${pattern}\` matches nothing in en.json`);
	}
}
console.log(`\n${used} static $t() key references checked`);
console.log(`${dynamic.size} dynamic key patterns (matching en.json keys listed; verify each possible value is covered):`);
for (const [k, v] of dynamic)
	console.log(`  ${k} -> ${v.length} keys: ${v.slice(0, 12).join(', ')}${v.length > 12 ? ', ...' : ''}`);
if (errors) {
	console.error(`\n${errors} error(s)`);
	process.exit(1);
}
console.log('\ni18n OK');
