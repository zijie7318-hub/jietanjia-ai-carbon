const CATALOG = __CATALOG_JSON__;
const ACTIONS = CATALOG.actions.actions || [];
const POLICIES = CATALOG.policies.policies || [];
const FACTORS = CATALOG.factors;
const TIERS = [
  { id: 'light', name: '轻量起步', tagline: '低投入、租房友好，先做马上能做的' },
  { id: 'balanced', name: '均衡优选', tagline: '投入与节电更平衡，适合多数家庭' },
  { id: 'deep', name: '深度减碳', tagline: '适合自有住房和长期改善' }
];

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => '¥' + Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const num = (n, d) => Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: d == null ? 1 : d });
const pad = n => String(n).padStart(2, '0');
const round1 = n => Math.round((Number(n) + Number.EPSILON) * 10) / 10;
const round2 = n => Math.round((Number(n) + Number.EPSILON) * 100) / 100;

function present(obj, keys) {
  for (const key of keys) {
    if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') return obj[key];
  }
  return null;
}
function parseNumber(value, label, low, high, fallback) {
  if (value === null || value === '') {
    if (fallback !== undefined) return fallback;
    return null;
  }
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error(label + '必须是数字');
  if (n < low || n > high) throw new Error(label + '需在 ' + low + ' 到 ' + high + ' 之间');
  return n;
}
function normalizeRegion(value) {
  return String(value || '').replace(/\s+/g, '').replace(/(特别行政区|自治区|省|市)$/, '');
}
function normalizeInput(payload) {
  const city = String(payload.city || '西安市').trim().slice(0, 30);
  if (!city) throw new Error('请选择所在城市');
  const housing = payload.housing === 'own' ? 'own' : (payload.housing === 'rent' ? 'rent' : 'other');
  const residents = Math.round(parseNumber(payload.residents, '家庭人口', 1, 20, 3));
  const monthlyKwh = parseNumber(payload.monthlyKwh, '月用电量', 1, 10000);
  const monthlyBill = parseNumber(payload.monthlyBill, '月电费', 1, 50000);
  const budget = parseNumber(payload.budget, '前期预算', 0, 200000, Number(FACTORS.default_upfront_budget));
  return { city, housing, residents, monthlyKwh, monthlyBill, budget };
}
function buildBaseline(h) {
  const tariff = Number(FACTORS.default_tariff_yuan_per_kwh);
  let monthlyKwh, source, isDefault = false;
  if (h.monthlyKwh !== null) {
    monthlyKwh = h.monthlyKwh;
    source = '按你填写的月用电量计算';
  } else if (h.monthlyBill !== null) {
    monthlyKwh = h.monthlyBill / tariff;
    source = '按你填写的月电费除以 ' + tariff.toFixed(2) + ' 元/kWh 估算';
  } else {
    monthlyKwh = h.residents * Number(FACTORS.default_monthly_kwh_per_person);
    source = '未填用电量，按每人每月 ' + FACTORS.default_monthly_kwh_per_person + ' kWh 的演示基线估算';
    isDefault = true;
  }
  monthlyKwh = round1(monthlyKwh);
  return {
    monthlyKwh,
    annualKwh: round1(monthlyKwh * 12),
    tariff,
    monthlyBill: round2(monthlyKwh * tariff),
    source,
    isDefault
  };
}
function savingOf(action, baseline) {
  if (baseline.monthlyKwh < Number(action.min_monthly_kwh || 0)) return 0;
  return action.saving_type === 'percent'
    ? baseline.annualKwh * Number(action.saving_value || 0)
    : Number(action.saving_value || 0);
}
function eligible(action, household) {
  return !(action.requires_owner && household.housing !== 'own');
}
function actionCard(action, baseline) {
  const kwh = savingOf(action, baseline);
  const money = kwh * baseline.tariff;
  const upfront = Number(action.upfront_cost || 0);
  const payback = upfront === 0 ? 0 : (money > 0 ? round1(upfront / (money / 12)) : null);
  return {
    id: action.id, name: action.name, category: action.category,
    difficulty: action.difficulty, upfrontCost: round2(upfront),
    annualKwhSaved: round1(kwh), annualMoneySaved: round2(money),
    annualCo2eKg: round1(kwh * Number(FACTORS.kg_co2e_per_kwh)),
    paybackMonths: payback, requiresOwner: !!action.requires_owner,
    needsInstallation: !!action.needs_installation, assumption: action.assumption
  };
}
function trimToBudget(list, budget) {
  const out = list.slice();
  while (out.length && out.reduce((s, x) => s + Number(x.upfront_cost || 0), 0) > budget) {
    const paid = out.filter(x => Number(x.upfront_cost || 0) > 0);
    if (!paid.length) break;
    paid.sort((a, b) => Number(b.upfront_cost || 0) - Number(a.upfront_cost || 0));
    out.splice(out.indexOf(paid[0]), 1);
  }
  return out;
}
function buildPlan(tier, household, baseline) {
  let candidates = ACTIONS.filter(a => (a.tiers || []).includes(tier.id)
    && eligible(a, household)
    && Number(a.upfront_cost || 0) <= household.budget
    && savingOf(a, baseline) > 0);
  let selected = candidates.slice(0, 4);
  if (!selected.length) {
    selected = ACTIONS.filter(a => eligible(a, household) && savingOf(a, baseline) > 0).slice(0, 2);
  }
  selected = trimToBudget(selected, household.budget);
  const actions = selected.map(a => actionCard(a, baseline));
  const overlap = actions.length > 1 ? 0.9 : 1;
  const annualKwh = actions.reduce((s, x) => s + x.annualKwhSaved, 0) * overlap;
  const annualMoney = annualKwh * baseline.tariff;
  const upfront = actions.reduce((s, x) => s + x.upfrontCost, 0);
  const payback = upfront === 0 ? 0 : (annualMoney > 0 ? round1(upfront / (annualMoney / 12)) : null);
  const notes = [];
  if (actions.length > 1) notes.push('多项措施可能影响同一部分用电，合计已按 10% 重叠折减。');
  if (household.housing !== 'own') notes.push('已排除需要自有住房或固定施工的措施。');
  if (!actions.length) notes.push('当前家庭条件与预算下暂无合适措施，可调整预算或补充用电信息。');
  return {
    tier: tier.id, name: tier.name, tagline: tier.tagline, actions,
    actionIds: actions.map(a => a.id), estimated: true,
    upfrontCost: round2(upfront), annualKwhSaved: round1(annualKwh),
    annualMoneySaved: round2(annualMoney), monthlyMoneySaved: round2(annualMoney / 12),
    annualCo2eKg: round1(annualKwh * Number(FACTORS.kg_co2e_per_kwh)),
    paybackMonths: payback, withinBudget: upfront <= household.budget, notes
  };
}
function matchPolicies(household, actionIds) {
  const today = new Date().toISOString().slice(0, 10);
  const cityKey = normalizeRegion(household.city);
  const wanted = new Set(actionIds);
  return POLICIES.flatMap(policy => {
    if (normalizeRegion(policy.region) !== cityKey) return [];
    const related = (policy.action_ids || []).filter(id => wanted.has(id));
    if (!related.length) return [];
    const reasons = [];
    let ok = true;
    if (today < policy.valid_from || today > policy.valid_to) {
      ok = false; reasons.push('当前日期不在演示有效期内');
    } else {
      reasons.push('当前日期在演示有效期内');
    }
    if (policy.requires_owner && household.housing !== 'own') {
      ok = false; reasons.push('该演示政策要求自有住房');
    } else if (policy.requires_owner) {
      reasons.push('满足自有住房条件');
    }
    return [{
      id: policy.id, title: policy.title, region: policy.region,
      status: ok ? 'likely' : 'ineligible', eligible: ok, benefit: policy.benefit,
      requirements: policy.requirements || [], application: policy.application,
      actionIds: related, reasons, validFrom: policy.valid_from, validTo: policy.valid_to,
      isDemo: !!policy.is_demo, sourceName: policy.source_name,
      sourceUrl: policy.source_url || '', updatedAt: policy.updated_at
    }];
  });
}
function buildResponse(payload) {
  const household = normalizeInput(payload);
  const baseline = buildBaseline(household);
  const plans = TIERS.map(tier => buildPlan(tier, household, baseline));
  const allIds = [...new Set(plans.flatMap(p => p.actionIds))].sort();
  const policies = matchPolicies(household, allIds);
  plans.forEach(plan => {
    plan.policyIds = policies.filter(p => p.actionIds.some(id => plan.actionIds.includes(id))).map(p => p.id);
  });
  return {
    household, baseline, budget: household.budget, plans, policies,
    meta: {
      actionsVersion: CATALOG.actions.version,
      policiesVersion: CATALOG.policies.version,
      factorVersion: FACTORS.version,
      factorKgCo2ePerKwh: FACTORS.kg_co2e_per_kwh,
      factorSource: FACTORS.source,
      assumptions: [FACTORS.disclaimer, CATALOG.actions.disclaimer, CATALOG.policies.disclaimer]
    }
  };
}

let lastPlans = null;
const planForm = document.getElementById('planForm');
const planResultEl = document.getElementById('planResult');
const planCardsEl = document.getElementById('planCards');
const policyListEl = document.getElementById('policyList');
const planErrorEl = document.getElementById('planError');
const genPlansBtn = document.getElementById('genPlansBtn');
const progressEl = document.getElementById('planProgress');
const aiExplainBox = document.getElementById('aiExplainBox');
const aiExplainState = document.getElementById('aiExplainState');
const aiExplainStages = document.getElementById('aiExplainStages');
const aiExplainBody = document.getElementById('aiExplainBody');
const aiExplainNote = document.getElementById('aiExplainNote');

function setPlanError(text) {
  planErrorEl.textContent = text || '';
  planErrorEl.classList.toggle('on', !!text);
}
function setProgress(stage, done) {
  progressEl.querySelectorAll('.jt-progress-item').forEach(el => {
    const n = Number(el.dataset.stage);
    el.classList.toggle('done', done || n < stage);
    el.classList.toggle('active', !done && n === stage);
  });
}
function numberOrNull(id) {
  const raw = document.getElementById(id).value.trim();
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : NaN;
}
function paybackText(months) {
  if (months == null) return '—';
  return Number(months) === 0 ? '无需投入' : num(months, 1) + ' 个月';
}
function planCardHtml(plan, recommended) {
  const actionsHtml = plan.actions.map(action =>
    '<details class="jt-action"><summary><span>' + esc(action.name) + '</span><span>' + esc(action.category || '')
    + '</span></summary><div class="jt-action-body"><b>年节电</b> ' + num(action.annualKwhSaved)
    + ' kWh · <b>年节省</b> ' + fmt(action.annualMoneySaved) + ' · <b>投入</b> ' + fmt(action.upfrontCost)
    + ' · <b>回收</b> ' + paybackText(action.paybackMonths) + '<br>' + esc(action.assumption || '') + '</div></details>'
  ).join('');
  return '<article class="jt-plan' + (recommended ? ' recommended' : '') + '">'
    + '<div class="jt-plan-top"><div><div class="jt-plan-tier">' + esc(plan.tier.toUpperCase())
    + '</div><h3>' + esc(plan.name) + '</h3></div>' + (recommended ? '<span class="jt-rec">均衡参考</span>' : '')
    + '</div><p class="jt-plan-tagline">' + esc(plan.tagline) + '</p><div class="jt-metrics">'
    + '<div class="jt-metric"><span>前期投入</span><strong>' + fmt(plan.upfrontCost) + '</strong></div>'
    + '<div class="jt-metric"><span>月省电费</span><strong>' + fmt(plan.monthlyMoneySaved) + '</strong></div>'
    + '<div class="jt-metric"><span>年节电</span><strong>' + num(plan.annualKwhSaved) + '<small>kWh</small></strong></div>'
    + '<div class="jt-metric"><span>年减碳</span><strong>' + num(plan.annualCo2eKg) + '<small>kg CO₂e</small></strong></div>'
    + '</div><div class="jt-action-list">' + (actionsHtml || '<div class="jt-empty">当前条件下暂无合适措施</div>') + '</div>'
    + '<p class="jt-plan-note">回收周期 ' + paybackText(plan.paybackMonths) + '。' + esc(plan.notes.join(' ')) + '</p>'
    + '<button type="button" class="jt-plan-btn" data-record-tier="' + esc(plan.tier) + '"'
    + (plan.actions.length ? '' : ' disabled') + '>把方案带入碳迹日记</button></article>';
}
function policyCardHtml(policy) {
  const ok = !!policy.eligible;
  const sourceUrl = /^https?:\/\//i.test(policy.sourceUrl || '') ? policy.sourceUrl : '';
  return '<article class="jt-policy"><div class="jt-policy-head"><h4>' + esc(policy.title) + '</h4>'
    + '<span class="jt-status ' + (ok ? 'ok' : 'no') + '">' + (ok ? '初筛符合' : '未通过初筛') + '</span></div>'
    + '<p>' + esc(policy.benefit || '') + '</p><div class="jt-policy-meta"><span>' + esc(policy.region)
    + '</span><span>有效期 ' + esc(policy.validFrom + ' 至 ' + policy.validTo) + '</span></div>'
    + '<div class="jt-policy-reason"><b>判断依据：</b>' + esc(policy.reasons.join('；'))
    + (policy.requirements.length ? '<br><b>材料条件：</b>' + esc(policy.requirements.join('、')) : '') + '</div>'
    + '<div class="jt-policy-demo">演示政策，不构成申领依据。' + (sourceUrl
      ? '<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer">' + esc(policy.sourceName || '政策原文') + '</a>'
      : esc(policy.sourceName || '')) + '</div></article>';
}
function renderLocalExplanation(data) {
  const eligiblePolicies = data.policies.filter(p => p.eligible);
  aiExplainBox.hidden = false;
  aiExplainState.textContent = '离线规则说明 · 未调用 AI';
  aiExplainStages.querySelectorAll('span').forEach(el => el.classList.add('done'));
  aiExplainBody.innerHTML = '<p>已根据月用电基线 ' + num(data.baseline.monthlyKwh)
    + ' kWh 和当前住房、预算条件完成三档计算。' + esc(data.baseline.source) + '</p>'
    + data.plans.map(p => '<div class="jt-ai-tier"><b>' + esc(p.name) + '</b><span>包含 '
      + p.actions.length + ' 项措施，预计年节电约 ' + num(p.annualKwhSaved) + ' kWh，前期投入约 '
      + fmt(p.upfrontCost) + '。</span></div>').join('')
    + (eligiblePolicies.length ? '<p><b>政策初筛：</b>找到 ' + eligiblePolicies.length + ' 条演示政策，仍需按材料条件进一步确认。</p>' : '')
    + '<p><b>下一步：</b>比较前期投入和回收周期，选择能实际执行的措施，再记录到碳迹。</p>';
  aiExplainNote.textContent = '当前为离线演示：不调用 AI，不访问外部政策库。所有数值为估算，政策为演示数据。';
}
function renderPlans(data) {
  lastPlans = data;
  const base = data.baseline;
  document.getElementById('baselineSummary').innerHTML =
    '<span>月用电基线 <b>' + num(base.monthlyKwh) + ' kWh</b></span><span class="sep"></span>'
    + '<span>年用电基线 <b>' + num(base.annualKwh) + ' kWh</b></span><span class="sep"></span>'
    + '<span>前期预算 <b>' + fmt(data.budget) + '</b></span><span class="sep"></span><span>'
    + esc(base.source) + (base.isDefault ? '（演示基线）' : '') + '</span>';
  planCardsEl.innerHTML = data.plans.map((p, i) => planCardHtml(p, i === 1)).join('');
  policyListEl.innerHTML = data.policies.length ? data.policies.map(policyCardHtml).join('')
    : '<div class="jt-empty">当前城市或措施暂无匹配的演示政策。</div>';
  const meta = data.meta;
  document.getElementById('planMeta').innerHTML = '<b>数据版本：</b>措施 ' + esc(meta.actionsVersion)
    + ' · 政策 ' + esc(meta.policiesVersion) + ' · 排放因子 ' + esc(meta.factorVersion) + '（'
    + esc(meta.factorKgCo2ePerKwh) + ' kg CO₂e/kWh）<br><b>因子来源：</b>' + esc(meta.factorSource || '未提供')
    + '<br><b>计算与展示边界：</b><ul>' + meta.assumptions.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>';
  planResultEl.hidden = false;
  const balanced = data.plans[1] || data.plans[0];
  if (balanced) {
    document.getElementById('heroMoney').innerHTML = fmt(balanced.monthlyMoneySaved) + '<small>元</small>';
    document.getElementById('heroCo2').innerHTML = num(balanced.annualCo2eKg) + '<small>kg</small>';
    const heroPayback = paybackText(balanced.paybackMonths);
    document.getElementById('heroPayback').innerHTML = heroPayback === '无需投入'
      ? '无需投入' : heroPayback.replace(' 个月', '') + '<small>个月</small>';
    document.getElementById('heroPreviewHint').textContent = '最近一次：' + balanced.name;
  }
  renderLocalExplanation(data);
}
planForm.addEventListener('submit', ev => {
  ev.preventDefault();
  setPlanError('');
  const payload = {
    city: document.getElementById('cityInput').value.trim(),
    housing: document.getElementById('housingInput').value,
    residents: numberOrNull('residentsInput'),
    monthlyKwh: numberOrNull('monthlyKwhInput'),
    monthlyBill: numberOrNull('monthlyBillInput'),
    budget: numberOrNull('budgetInput')
  };
  if ([payload.residents, payload.monthlyKwh, payload.monthlyBill, payload.budget]
      .some(v => Number.isNaN(v))) { setPlanError('数字字段格式不正确，请检查后重试。'); return; }
  genPlansBtn.disabled = true; genPlansBtn.textContent = '正在计算…';
  planResultEl.hidden = true;
  setProgress(2, false);
  try {
    const data = buildResponse(payload);
    setProgress(3, true);
    renderPlans(data);
  } catch (err) {
    setPlanError(err.message || '方案生成失败。');
  } finally {
    genPlansBtn.disabled = false; genPlansBtn.textContent = '生成三档方案';
  }
});
planCardsEl.addEventListener('click', ev => {
  const btn = ev.target.closest('[data-record-tier]');
  if (!btn || !lastPlans) return;
  const plan = lastPlans.plans.find(p => p.tier === btn.dataset.recordTier);
  if (!plan) return;
  const text = ['计划采用「' + plan.name + '」节能方案：']
    .concat(plan.actions.map(a => '· ' + a.name))
    .concat(['预计年节电 ' + num(plan.annualKwhSaved) + ' kWh，年节省电费 ' + fmt(plan.annualMoneySaved)
      + '，年减碳约 ' + num(plan.annualCo2eKg) + ' kg CO₂e（估算）。']).join('\n');
  document.getElementById('hpInput').value = text;
  document.getElementById('entryType').value = 'planned';
  document.getElementById('hpFlowMsg').textContent = '方案摘要已按「计划执行」带入；完成后可在碳档案中标记为已完成。';
  switchTab('diary');
});
document.querySelectorAll('[data-sample]').forEach(btn => {
  btn.onclick = () => {
    const samples = {
      rent: ['租住', 2, 170, '', 1200],
      family: ['own', 3, 280, '', 8000],
      elder: ['own', 4, 360, '', 12000]
    };
    const s = samples[btn.dataset.sample];
    document.getElementById('cityInput').value = '西安市';
    document.getElementById('housingInput').value = s[0];
    document.getElementById('residentsInput').value = s[1];
    document.getElementById('monthlyKwhInput').value = s[2];
    document.getElementById('monthlyBillInput').value = s[3];
    document.getElementById('budgetInput').value = s[4];
    setPlanError('');
  };
});

const STORE_KEY = 'jtc_offline_entries_v1';
let hpCurrent = null;
let hpEntries = [];
const hpInputEl = document.getElementById('hpInput');
const hpResultEl = document.getElementById('hpResult');
const hpTextEl = document.getElementById('hpText');
const hpLabelEl = document.getElementById('hpLabel');
const hpSrcEl = document.getElementById('hpSrc');
const hpSaveMsgEl = document.getElementById('hpSaveMsg');
const hpFlowMsgEl = document.getElementById('hpFlowMsg');
const recTreeEl = document.getElementById('recTree');
const recEmptyEl = document.getElementById('recEmpty');
const recCountEl = document.getElementById('recCount');
const recSearchEl = document.getElementById('recSearch');
const recDateEl = document.getElementById('recDate');
const REC_WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

function loadEntries() {
  try {
    const value = JSON.parse(localStorage.getItem(STORE_KEY) || '[]');
    return Array.isArray(value) ? value.filter(x => x && x.id && x.content) : [];
  } catch (_) { return []; }
}
function saveEntries() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(hpEntries)); } catch (_) {}
}
function composeFeedback(text, type) {
  const action = text.replace(/[。！!，,、；;：:？?～~\s]+$/g, '').trim().slice(0, 80);
  const done = [
    '今天你完成了「' + action + '」。这不是一句口号，而是一个已经发生的行动。把它留在这里，下一次评估时你会更清楚哪些改变真正适合自己。',
    '「' + action + '」已经写进今天的碳迹。单次行动看起来很小，但可回看的记录会帮你判断哪些习惯值得继续。',
    '今天的行动是「' + action + '」。先做能做的，再根据账单和实际体验调整，比追求一次到位更可靠。'
  ];
  const planned = [
    '你把「' + action + '」列入了下一步计划。先确认执行条件和时间，完成后再回来把状态改为已完成。',
    '「' + action + '」已作为计划行动保存。计划不等于已经产生的减碳结果，完成后记得补上实际执行记录。',
    '下一步计划是「' + action + '」。从一项能真正执行的措施开始，之后再用账单和体验复盘。'
  ];
  const arr = type === 'planned' ? planned : done;
  const idx = [...text].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % arr.length;
  return arr[idx];
}
function hpShow(content, source, inputText, type) {
  hpCurrent = { input: inputText, content, scene: type };
  hpLabelEl.textContent = type === 'planned' ? '碳迹计划 · 待执行' : '今日碳迹 · 已完成';
  hpTextEl.textContent = content;
  hpSrcEl.textContent = source;
  hpResultEl.hidden = false;
  hpSaveMsgEl.textContent = '';
}
function renderRecords() {
  const kw = recSearchEl.value.trim();
  const day = recDateEl.value.trim();
  let list = hpEntries.slice().sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  if (kw) list = list.filter(x => String(x.content).includes(kw) || String(x.inputText).includes(kw));
  if (day) list = list.filter(x => {
    const d = new Date(x.createdAt);
    return !isNaN(d) && d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) === day;
  });
  recCountEl.textContent = hpEntries.length ? '共 ' + hpEntries.length + ' 条'
    + ((kw || day) ? '，筛出 ' + list.length + ' 条' : '') : '';
  if (!list.length) {
    recEmptyEl.hidden = false;
    recEmptyEl.textContent = hpEntries.length ? '没有匹配的碳迹，换个关键词或日期试试。' : '还没有保存的碳迹';
    recTreeEl.innerHTML = ''; return;
  }
  recEmptyEl.hidden = true;
  const years = new Map();
  list.forEach(item => {
    const d = new Date(item.createdAt); if (isNaN(d)) return;
    const y = d.getFullYear(), m = d.getMonth() + 1, dd = d.getDate();
    if (!years.has(y)) years.set(y, { y, count: 0, months: new Map() });
    const yn = years.get(y); yn.count++;
    if (!yn.months.has(m)) yn.months.set(m, { m, count: 0, days: new Map() });
    const mn = yn.months.get(m); mn.count++;
    if (!mn.days.has(dd)) mn.days.set(dd, { dd, wd: d.getDay(), items: [] });
    mn.days.get(dd).items.push({ item, d });
  });
  const expand = !!(kw || day), now = new Date();
  recTreeEl.innerHTML = [...years.values()].sort((a, b) => b.y - a.y).map(yn => {
    const months = [...yn.months.values()].sort((a, b) => b.m - a.m).map(mn => {
      const days = [...mn.days.values()].sort((a, b) => b.dd - a.dd).map(dn => {
        const items = dn.items.sort((a, b) => b.d - a.d).map(({ item, d }) => {
          const done = item.scene !== 'planned';
          const mark = done ? '' : '<button type="button" class="hp-link" data-act="done" data-id="'
            + esc(item.id) + '">标为已完成</button>';
          return '<div class="rec-item"><div class="rec-item-meta"><span>' + pad(d.getHours()) + ':' + pad(d.getMinutes())
            + '</span><span><span class="rec-status ' + (done ? 'done' : '') + '">' + (done ? '已完成' : '计划执行')
            + '</span>「' + esc(item.inputText).slice(0, 90) + '」</span></div><div class="rec-item-text">'
            + esc(item.content) + '</div><div class="rec-item-ops">' + mark
            + '<button type="button" class="hp-link" data-act="copy" data-id="' + esc(item.id) + '">复制</button>'
            + '<button type="button" class="hp-link" data-act="del" data-id="' + esc(item.id) + '">删除</button>'
            + '</div></div>';
        }).join('');
        return '<div class="rec-day"><div class="rec-day-head">' + mn.m + ' 月 ' + dn.dd + ' 日 · '
          + REC_WD[dn.wd] + '</div>' + items + '</div>';
      }).join('');
      return '<details class="rec-month"' + (expand || (yn.y === now.getFullYear() && mn.m === now.getMonth() + 1) ? ' open' : '')
        + '><summary>' + mn.m + ' 月 <span class="rec-n">' + mn.count + ' 条</span></summary>' + days + '</details>';
    }).join('');
    return '<details class="rec-year"' + (expand || yn.y === now.getFullYear() ? ' open' : '')
      + '><summary>' + yn.y + ' 年 <span class="rec-n">' + yn.count + ' 条</span></summary>' + months + '</details>';
  }).join('');
}
function loadAndRender() {
  hpEntries = loadEntries();
  renderRecords();
}
document.querySelectorAll('#hpChips .chip').forEach(chip => {
  chip.onclick = () => { hpInputEl.value = chip.dataset.text || ''; hpInputEl.focus(); };
});
document.getElementById('hpGenBtn').onclick = () => {
  const text = hpInputEl.value.trim();
  if (!text) { hpFlowMsgEl.textContent = '先写下一件已经完成或准备执行的节能行动。'; hpInputEl.focus(); return; }
  const type = document.getElementById('entryType').value;
  hpFlowMsgEl.textContent = '';
  hpShow(composeFeedback(text, type), '离线模板 · 未调用 AI', text, type);
};
document.getElementById('hpCopyBtn').onclick = async ev => {
  if (!hpCurrent) return;
  try {
    await navigator.clipboard.writeText(hpCurrent.content);
  } catch (_) {
    const ta = document.createElement('textarea'); ta.value = hpCurrent.content; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy'); ta.remove();
  }
  ev.currentTarget.textContent = '已复制';
  setTimeout(() => { ev.currentTarget.textContent = '复制'; }, 1400);
};
document.getElementById('hpSaveBtn').onclick = () => {
  if (!hpCurrent) return;
  const item = {
    id: 'local-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7),
    inputText: hpCurrent.input.slice(0, 200), content: hpCurrent.content,
    scene: hpCurrent.scene, createdAt: new Date().toISOString()
  };
  hpEntries.unshift(item); saveEntries(); renderRecords();
  hpSaveMsgEl.textContent = '已保存到本机碳档案。';
  hpSaveMsgEl.classList.add('ok');
};
document.getElementById('hpClearBtn').onclick = () => {
  hpInputEl.value = ''; hpCurrent = null; hpResultEl.hidden = true;
  hpFlowMsgEl.textContent = ''; hpSaveMsgEl.textContent = '';
};
document.getElementById('hpGoRecords').onclick = () => switchTab('records');
recSearchEl.oninput = renderRecords;
recDateEl.onchange = renderRecords;
document.getElementById('recClear').onclick = () => { recSearchEl.value = ''; recDateEl.value = ''; renderRecords(); };
document.getElementById('recRefresh').onclick = loadAndRender;
recTreeEl.onclick = ev => {
  const btn = ev.target.closest('button[data-act]'); if (!btn) return;
  const id = btn.dataset.id;
  if (btn.dataset.act === 'del') {
    if (!confirm('删除这条碳迹？')) return;
    hpEntries = hpEntries.filter(x => x.id !== id); saveEntries(); renderRecords(); return;
  }
  if (btn.dataset.act === 'done') {
    hpEntries = hpEntries.map(x => x.id === id ? { ...x, scene: 'done' } : x);
    saveEntries(); renderRecords(); return;
  }
  const text = btn.closest('.rec-item').querySelector('.rec-item-text');
  if (!text) return;
  Promise.resolve(navigator.clipboard ? navigator.clipboard.writeText(text.textContent) : Promise.reject())
    .catch(() => { const ta = document.createElement('textarea'); ta.value = text.textContent; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); })
    .then(() => { btn.textContent = '已复制'; setTimeout(() => { btn.textContent = '复制'; }, 1400); });
};

const TAB_NAMES = ['plans', 'diary', 'records'];
const tabsEl = document.getElementById('tabs');
function switchTab(name, opts) {
  if (!TAB_NAMES.includes(name)) name = 'plans';
  TAB_NAMES.forEach(t => {
    document.getElementById('panel-' + t).classList.toggle('active', t === name);
    const btn = tabsEl.querySelector('[data-tab="' + t + '"]');
    btn.classList.toggle('active', t === name);
    btn.setAttribute('aria-selected', t === name ? 'true' : 'false');
  });
  if (!(opts && opts.silent)) {
    try { history.replaceState(null, '', '#' + name); } catch (_) {}
  }
  if (!(opts && opts.noScroll)) {
    const target = document.getElementById('panel-' + name);
    window.scrollTo({ top: target.offsetTop - 76, behavior: 'smooth' });
  }
}
tabsEl.querySelectorAll('.tab').forEach(btn => { btn.onclick = () => switchTab(btn.dataset.tab); });
document.querySelectorAll('[data-goto]').forEach(el => {
  el.addEventListener('click', ev => { ev.preventDefault(); switchTab(el.dataset.goto); });
});
document.getElementById('dataVersionTag').textContent = ACTIONS.length + ' 项措施 · ' + POLICIES.length + ' 条演示政策';
loadAndRender();
switchTab((location.hash || '#plans').slice(1), { noScroll: true, silent: true });
