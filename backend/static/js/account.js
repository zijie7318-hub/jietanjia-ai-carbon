/* 节碳家 · account.js — 账号登录注册与碳档案归档列表 */
function hpAuthMsg(text, ok) {
  hpAuthMsgEl.textContent = text || '';
  hpAuthMsgEl.classList.toggle('ok', !!ok);
}
function hpSaveMsg(text, ok) {
  hpSaveMsgEl.textContent = text || '';
  hpSaveMsgEl.classList.toggle('ok', !!ok);
}
function hpSetUser(user) {
  hpMe = user || null;
  document.getElementById('hpGuestRow').hidden = !!hpMe;
  document.getElementById('hpUserRow').hidden = !hpMe;
  document.getElementById('hpUserName').textContent = hpMe ? hpMe.username : '-';
  hpAuthBoxEl.hidden = true;
  hpAuthMsg('');
  if (hpMe) hpUserEl.value = hpMe.username;
}
async function hpAuthPost(path, body) {
  return requestJson(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, 15000);
}
async function hpDoAuth(kind) {
  const username = hpUserEl.value.trim(), password = hpPassEl.value;
  if (!username || !password) { hpAuthMsg('用户名和密码都要填。'); return; }
  const loginBtn = document.getElementById('hpLoginBtn');
  const regBtn = document.getElementById('hpRegBtn');
  loginBtn.disabled = regBtn.disabled = true;
  hpAuthMsg(kind === 'reg' ? '注册中…' : '登录中…', true);
  try {
    const data = await hpAuthPost(kind === 'reg' ? '/api/auth/register' : '/api/auth/login',
      { username, password });
    localStorage.setItem(HP_TOKEN_KEY, data.token);
    hpSetUser(data.user); hpPassEl.value = '';
    hpAuthMsg(kind === 'reg' ? '注册成功，已自动登录。' : '登录成功。', true);
    hpLoadList();
  } catch (err) { hpAuthMsg(hpErrText(err)); }
  finally { loginBtn.disabled = regBtn.disabled = false; }
}
const REC_WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
function recDateOf(item) {
  const d = new Date(item.createdAt);
  return isNaN(d.getTime()) ? null : d;
}
function recItemHtml(item, d) {
  const time = d ? pad(d.getHours()) + ':' + pad(d.getMinutes()) : '';
  const done = item.scene !== 'planned';
  const status = '<span class="rec-status ' + (done ? 'done' : '') + '">'
    + (done ? '已完成' : '计划执行') + '</span>';
  const from = item.inputText ? status + '「' + esc(item.inputText).slice(0, 90) + '」' : status;
  const markDone = done ? '' : '<button type="button" class="hp-link" data-act="done" data-id="' + item.id + '">标为已完成</button>';
  return '<div class="rec-item"><div class="rec-item-meta"><span>' + time + '</span><span>' + from + '</span></div>'
    + '<div class="rec-item-text">' + esc(item.content) + '</div>'
    + '<div class="rec-item-ops">' + markDone
    + '<button type="button" class="hp-link" data-act="copy" data-id="' + item.id + '">复制</button>'
    + '<button type="button" class="hp-link" data-act="del" data-id="' + item.id + '">删除</button></div></div>';
}
/** @param {JtcCarbonEntry[]} items */
function hpRenderList(items) {
  hpItems = (items || []).slice().sort((a, b) =>
    String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
  renderRecords();
}
function renderRecords() {
  if (!recTreeEl) return;
  const kw = (recSearchEl.value || '').trim();
  const day = (recDateEl.value || '').trim();
  let list = hpItems.slice();
  if (kw) list = list.filter(it => String(it.content || '').indexOf(kw) >= 0 || String(it.inputText || '').indexOf(kw) >= 0);
  if (day) list = list.filter(it => {
    const d = recDateOf(it); if (!d) return false;
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) === day;
  });
  recCountEl.textContent = hpItems.length ? '共 ' + hpItems.length + ' 条' + ((kw || day) ? '，筛出 ' + list.length + ' 条' : '') : '';
  if (!list.length) {
    recEmptyEl.hidden = false;
    recEmptyEl.textContent = hpItems.length ? '没有匹配的碳迹，换个关键词或日期试试。'
      : (hpMe ? '还没有保存的碳迹，去「碳迹日记」记录第一条。' : '登录后，保存过的碳迹会按日期显示在这里。');
    recTreeEl.innerHTML = ''; return;
  }
  recEmptyEl.hidden = true;
  const years = new Map();
  list.forEach(it => {
    const d = recDateOf(it); if (!d) return;
    const y = d.getFullYear(), m = d.getMonth() + 1, dd = d.getDate();
    if (!years.has(y)) years.set(y, { y, count: 0, months: new Map() });
    const yn = years.get(y); yn.count++;
    if (!yn.months.has(m)) yn.months.set(m, { m, count: 0, days: new Map() });
    const mn = yn.months.get(m); mn.count++;
    if (!mn.days.has(dd)) mn.days.set(dd, { dd, wd: d.getDay(), items: [] });
    mn.days.get(dd).items.push({ it, d });
  });
  const expandAll = !!(kw || day);
  const nowY = new Date().getFullYear(), nowM = new Date().getMonth() + 1;
  recTreeEl.innerHTML = [...years.values()].sort((a, b) => b.y - a.y).map(yn => {
    const months = [...yn.months.values()].sort((a, b) => b.m - a.m).map(mn => {
      const days = [...mn.days.values()].sort((a, b) => b.dd - a.dd).map(dn => {
        const items = dn.items.sort((a, b) => b.d - a.d).map(x => recItemHtml(x.it, x.d)).join('');
        return '<div class="rec-day"><div class="rec-day-head">' + mn.m + ' 月 ' + dn.dd + ' 日 · '
          + REC_WD[dn.wd] + '</div>' + items + '</div>';
      }).join('');
      return '<details class="rec-month"' + (expandAll || (yn.y === nowY && mn.m === nowM) ? ' open' : '')
        + '><summary>' + mn.m + ' 月 <span class="rec-n">' + mn.count + ' 条</span></summary>' + days + '</details>';
    }).join('');
    return '<details class="rec-year"' + (expandAll || yn.y === nowY ? ' open' : '') + '><summary>'
      + yn.y + ' 年 <span class="rec-n">' + yn.count + ' 条</span></summary>' + months + '</details>';
  }).join('');
}
async function hpLoadList() {
  const token = localStorage.getItem(HP_TOKEN_KEY);
  if (!token || !hpMe) { hpRenderList([]); return; }
  try {
    const data = await requestJson('/api/carbon-entries', { headers: { 'X-HT-Token': token } }, 12000);
    hpRenderList(data.items);
  } catch (err) {
    if (/401|登录/.test(err.message || '')) {
      localStorage.removeItem(HP_TOKEN_KEY); hpSetUser(null); hpRenderList([]);
    } else {
      recEmptyEl.hidden = false;
      recEmptyEl.textContent = '暂时读不到碳迹：' + hpErrText(err);
    }
  }
}
async function hpInit() {
  const token = localStorage.getItem(HP_TOKEN_KEY);
  if (!token) { hpSetUser(null); hpRenderList([]); return; }
  try {
    const data = await requestJson('/api/auth/me', { headers: { 'X-HT-Token': token } }, 10000);
    hpSetUser(data.user); hpLoadList();
  } catch (_) {
    localStorage.removeItem(HP_TOKEN_KEY); hpSetUser(null); hpRenderList([]);
  }
}
document.getElementById('hpLoginBtn').onclick = () => hpDoAuth('login');
document.getElementById('hpRegBtn').onclick = () => hpDoAuth('reg');
document.getElementById('hpLogoutBtn').onclick = async () => {
  const token = localStorage.getItem(HP_TOKEN_KEY) || '';
  localStorage.removeItem(HP_TOKEN_KEY); hpSetUser(null); hpRenderList([]);
  try { await fetch(apiUrl('/api/auth/logout'), { method: 'POST', headers: { 'X-HT-Token': token } }); } catch (_) {}
};
recSearchEl.oninput = renderRecords;
recDateEl.onchange = renderRecords;
document.getElementById('recClear').onclick = () => { recSearchEl.value = ''; recDateEl.value = ''; renderRecords(); };
document.getElementById('recRefresh').onclick = hpLoadList;
document.getElementById('hpGoRecords').onclick = () => switchTab('records');
recTreeEl.onclick = ev => {
  const btn = ev.target.closest('button[data-act]'); if (!btn) return;
  if (btn.dataset.act === 'del') { hpDelete(btn.dataset.id); return; }
  if (btn.dataset.act === 'done') { hpMarkDone(btn.dataset.id); return; }
  const text = btn.closest('.rec-item') && btn.closest('.rec-item').querySelector('.rec-item-text');
  if (text) copyText(text.textContent).then(ok => { if (ok) flashBtn(btn, '已复制'); });
};
