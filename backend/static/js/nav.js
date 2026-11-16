/* 节碳家 · nav.js — 三个主入口的切换与 hash 路由 */
const TAB_NAMES = ['plans', 'diary', 'records'];
const tabsEl = document.getElementById('tabs');
function switchTab(name, opts) {
  if (TAB_NAMES.indexOf(name) < 0) name = 'plans';
  TAB_NAMES.forEach(t => {
    const panel = document.getElementById('panel-' + t);
    if (panel) panel.classList.toggle('active', t === name);
    const btn = tabsEl.querySelector('.tab[data-tab="' + t + '"]');
    if (btn) { btn.classList.toggle('active', t === name); btn.setAttribute('aria-selected', t === name ? 'true' : 'false'); }
  });
  if (!(opts && opts.silent)) history.replaceState(null, '', '#' + name);
  if (name === 'records') hpLoadList();
  if (!(opts && opts.noScroll)) {
    const target = document.getElementById('panel-' + name);
    if (target) window.scrollTo({ top: target.offsetTop - 76, behavior: 'smooth' });
  }
}
tabsEl.querySelectorAll('.tab').forEach(btn => { btn.onclick = () => switchTab(btn.dataset.tab); });
document.querySelectorAll('[data-goto]').forEach(el => {
  el.addEventListener('click', ev => { ev.preventDefault(); switchTab(el.dataset.goto); });
});
window.addEventListener('hashchange', () => {
  switchTab((location.hash || '#plans').slice(1), { noScroll: true, silent: true });
});
