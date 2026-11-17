/* 节碳家 · core.js — 配置、同源请求、超时与格式化工具（无业务状态） */
const DEFAULT_API_BASE = location.protocol === 'file:' ? 'http://localhost:5000' : location.origin;
const qs = new URLSearchParams(location.search);
const API_BASE = DEFAULT_API_BASE;
const SHARE_CODE = qs.get('sharecode') || localStorage.getItem('jtc_sharecode') || '';
if (qs.get('sharecode')) localStorage.setItem('jtc_sharecode', qs.get('sharecode'));

/** @param {string} path @returns {string} 带上分享码的接口地址 */
function apiUrl(path) {
  const base = API_BASE.replace(/\/+$/, '');
  if (!SHARE_CODE) return base + path;
  return base + path + (path.indexOf('?') >= 0 ? '&' : '?') + 'sharecode=' + encodeURIComponent(SHARE_CODE);
}
async function fetchWithTimeout(url, opts, ms) {
  if (typeof AbortController === 'undefined') return fetch(url, opts);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms || 20000);
  try {
    return await fetch(url, Object.assign({}, opts, { signal: ctrl.signal }));
  } finally { clearTimeout(timer); }
}
/**
 * 发起同源 JSON 请求；非 2xx 或 success=false 一律抛出带后端文案的错误。
 * @param {string} path
 * @param {RequestInit} [options]
 * @param {number} [timeout]
 * @returns {Promise<any>}
 */
async function requestJson(path, options, timeout) {
  const r = await fetchWithTimeout(apiUrl(path), options, timeout);
  const j = await r.json().catch(() => null);
  if (!r.ok || !j || !j.success) throw new Error((j && j.error) || ('HTTP ' + r.status));
  return j;
}
/** @param {unknown} s @returns {string} */
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
/**
 * 金额/数值格式化：优先委托给 TypeScript 编译产物（src/ts/format.ts），
 * 保证全站数值口径单一来源；产物未加载时回退到本地等价实现。
 * @param {number} n
 * @returns {string}
 */
const fmt = n => (globalThis.JtcFormat
  ? globalThis.JtcFormat.money(n)
  : '¥' + Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
/** @param {number} n @param {number} [d] @returns {string} */
const num = (n, d) => (globalThis.JtcFormat
  ? globalThis.JtcFormat.num(n, d == null ? 1 : d)
  : Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: d == null ? 1 : d }));
const pad = n => String(n).padStart(2, '0');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function copyText(text) {
  if (!text) return false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text); return true;
    }
  } catch (_) {}
  try {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select(); document.execCommand('copy');
    document.body.removeChild(ta); return true;
  } catch (_) { return false; }
}
function flashBtn(btn, text) {
  const old = btn.textContent; btn.textContent = text;
  setTimeout(() => { btn.textContent = old; }, 1500);
}
