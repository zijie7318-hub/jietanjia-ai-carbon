/* 节碳家 · plans.js — 家庭条件表单、三档方案卡与政策卡渲染 */
const planForm = document.getElementById('planForm');
const planCardsEl = document.getElementById('planCards');
const policyListEl = document.getElementById('policyList');
const planResultEl = document.getElementById('planResult');
const planErrorEl = document.getElementById('planError');
const progressEl = document.getElementById('planProgress');
const genPlansBtn = document.getElementById('genPlansBtn');
let lastPlans = null;
function formValue(id) { return document.getElementById(id).value.trim(); }
function numberOrNull(id) {
  const raw = formValue(id);
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : NaN;
}
function setPlanError(message) {
  planErrorEl.textContent = message || '';
  planErrorEl.classList.toggle('on', !!message);
}
function setProgress(stage, done) {
  progressEl.querySelectorAll('.jt-progress-item').forEach(item => {
    const n = Number(item.dataset.stage);
    item.classList.toggle('done', done || n < stage);
    item.classList.toggle('active', !done && n === stage);
  });
}
function sampleInput(kind) {
  const samples = {
    rent: { city: '西安市', housing: 'rent', residents: 2, kwh: 170, bill: '', budget: 1200 },
    family: { city: '西安市', housing: 'own', residents: 3, kwh: 280, bill: '', budget: 8000 },
    elder: { city: '西安市', housing: 'own', residents: 4, kwh: 360, bill: '', budget: 12000 }
  };
  const s = samples[kind]; if (!s) return;
  document.getElementById('cityInput').value = s.city;
  document.getElementById('housingInput').value = s.housing;
  document.getElementById('residentsInput').value = s.residents;
  document.getElementById('monthlyKwhInput').value = s.kwh;
  document.getElementById('monthlyBillInput').value = s.bill;
  document.getElementById('budgetInput').value = s.budget;
  setPlanError('');
}
document.querySelectorAll('[data-sample]').forEach(btn => {
  btn.onclick = () => sampleInput(btn.dataset.sample);
});

/** @param {number|null} months @returns {string} */
function paybackText(months) {
  if (months == null) return '—';
  if (Number(months) === 0) return '无需投入';
  return num(months, 1) + ' 个月';
}
/** @param {JtcPlan} plan @param {boolean} recommended @returns {string} */
function planCardHtml(plan, recommended) {
  const actions = (plan.actions || []).map(action => {
    const range = Array.isArray(action.annualKwhRange) && action.annualKwhRange.length === 2
      ? '，参考区间 ' + num(action.annualKwhRange[0]) + '–' + num(action.annualKwhRange[1]) + ' kWh'
      : '';
    const sourceUrl = /^https?:\/\//i.test(action.sourceUrl || '') ? action.sourceUrl : '';
    const source = sourceUrl
      ? '<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer">' + esc(action.sourceName || '查看来源') + '</a>'
      : esc(action.sourceName || '工程假设');
    return '<details class="jt-action"><summary><span>' + esc(action.name)
      + '</span><span>' + esc(action.category || '') + '</span></summary>'
      + '<div class="jt-action-body"><b>年节电</b> ' + num(action.annualKwhSaved) + ' kWh · '
      + '<b>年节省</b> ' + fmt(action.annualMoneySaved) + ' · <b>投入</b> ' + fmt(action.upfrontCost)
      + ' · <b>回收</b> ' + paybackText(action.paybackMonths)
      + '<br>' + esc(action.assumption || '估算参数见数据说明。')
      + '<div class="jt-action-evidence"><b>依据等级：</b>' + esc(action.evidenceLabel || '工程估算')
      + range + '<br><b>依据：</b>' + source
      + (action.sourceNote ? '<br>' + esc(action.sourceNote) : '')
      + (action.costNote ? '<br><b>成本口径：</b>' + esc(action.costNote) : '') + '</div></div></details>';
  }).join('');
  return '<article class="jt-plan' + (recommended ? ' recommended' : '') + '">'
    + '<div class="jt-plan-top"><div><div class="jt-plan-tier">' + esc(plan.tier.toUpperCase()) + '</div>'
    + '<h3>' + esc(plan.name) + '</h3></div>'
    + (recommended ? '<span class="jt-rec">均衡参考</span>' : '') + '</div>'
    + '<p class="jt-plan-tagline">' + esc(plan.tagline) + '</p>'
    + '<div class="jt-metrics">'
    + '<div class="jt-metric"><span>前期投入</span><strong>' + fmt(plan.upfrontCost) + '</strong></div>'
    + '<div class="jt-metric"><span>月省电费</span><strong>' + fmt(plan.monthlyMoneySaved) + '</strong></div>'
    + '<div class="jt-metric"><span>年节电</span><strong>' + num(plan.annualKwhSaved) + '<small>kWh</small></strong></div>'
    + '<div class="jt-metric"><span>年减碳</span><strong>' + num(plan.annualCo2eKg) + '<small>kg CO₂e</small></strong></div>'
    + '</div>'
    + '<div class="jt-action-list">' + (actions || '<div class="jt-empty">当前条件下暂无合适措施</div>') + '</div>'
    + '<p class="jt-plan-note">回收周期 ' + paybackText(plan.paybackMonths) + '。'
    + esc((plan.notes || []).join(' ')) + '</p>'
    + '<button type="button" class="jt-plan-btn" data-record-tier="' + esc(plan.tier) + '"'
    + ((plan.actions || []).length ? '' : ' disabled') + '>把方案带入碳迹日记</button>'
    + '</article>';
}
/** @param {JtcPolicy} policy @returns {string} */
function policyCardHtml(policy) {
  const ok = !!policy.eligible;
  const sourceUrl = /^https?:\/\//i.test(policy.sourceUrl || '') ? policy.sourceUrl : '';
  const secondaryUrl = /^https?:\/\//i.test(policy.sourceSecondaryUrl || '') ? policy.sourceSecondaryUrl : '';
  const meta = [
    policy.validFrom && policy.validTo ? ('有效期 ' + policy.validFrom + ' 至 ' + policy.validTo) : '',
    policy.updatedAt ? ('核验 ' + policy.updatedAt) : ''
  ].filter(Boolean).map(t => '<span>' + esc(t) + '</span>').join('');
  return '<article class="jt-policy"><div class="jt-policy-head"><h4>' + esc(policy.title) + '</h4>'
    + '<span class="jt-status ' + (ok ? 'ok' : 'no') + '">'
    + esc(policy.statusLabel || (ok ? '条件待确认' : '当前不适用')) + '</span></div>'
    + '<p>' + esc(policy.benefit || '') + '</p>'
    + '<div class="jt-policy-meta"><span>' + esc(policy.region) + '</span>' + meta + '</div>'
    + '<div class="jt-policy-reason"><b>自动初筛：</b>' + esc((policy.reasons || []).join('；'))
    + (policy.manualChecks && policy.manualChecks.length ? '<br><b>仍需人工确认：</b>' + esc(policy.manualChecks.join('、')) : '')
    + (policy.requirements && policy.requirements.length ? '<br><b>材料条件：</b>' + esc(policy.requirements.join('、')) : '')
    + '<br><b>边界：</b>' + esc(policy.disclaimer || '不代表已获批或可申领。')
    + '</div>'
    + '<div class="jt-policy-demo">' + (policy.isDemo ? '演示政策。' : '政策来源：')
    + (sourceUrl
      ? '<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer">'
        + esc(policy.sourceName || '查看政策原文') + '</a>'
      : esc(policy.sourceName || '未提供链接'))
    + (secondaryUrl ? ' · <a href="' + esc(secondaryUrl) + '" target="_blank" rel="noopener noreferrer">实施公告</a>' : '')
    + (policy.sourceRetrievedAt ? ' · 检索于 ' + esc(policy.sourceRetrievedAt) : '')
    + '</div></article>';
}
/** @param {JtcEnergyResponse} data */
function renderPlans(data) {
  lastPlans = data;
  const base = data.baseline;
  document.getElementById('baselineSummary').innerHTML =
    '<span>月用电基线 <b>' + num(base.monthlyKwh) + ' kWh</b></span><span class="sep"></span>'
    + '<span>年用电基线 <b>' + num(base.annualKwh) + ' kWh</b></span><span class="sep"></span>'
    + '<span>综合电价 <b>' + Number(base.tariff || 0).toFixed(4) + ' 元/kWh</b></span><span class="sep"></span>'
    + '<span>前期预算 <b>' + fmt(data.budget) + '</b></span><span class="sep"></span>'
    + '<span>' + esc(base.source) + (base.isDefault ? '（工程基线）' : '') + '</span>';
  planCardsEl.innerHTML = (data.plans || []).map((plan, index) =>
    planCardHtml(plan, index === 1)).join('');
  const coverage = data.coverage || {};
  policyListEl.innerHTML = (data.policies || []).length
    ? data.policies.map(policyCardHtml).join('')
    : '<div class="jt-empty">' + esc(coverage.message || '当前方案没有匹配的已接入政策。') + '</div>';
  const meta = data.meta || {};
  const factorUrl = /^https?:\/\//i.test(meta.factorUrl || '') ? meta.factorUrl : '';
  const tariffUrl = /^https?:\/\//i.test(meta.tariffUrl || '') ? meta.tariffUrl : '';
  document.getElementById('planMeta').innerHTML =
    '<b>数据版本：</b>措施 ' + esc(meta.actionsVersion) + ' · 政策 ' + esc(meta.policiesVersion)
    + ' · 电力因子 ' + esc(meta.factorVersion) + '（' + esc(meta.factorKgCo2ePerKwh) + ' kg CO₂e/kWh）<br>'
    + '<b>电力因子：</b>' + esc(meta.factorScope || '') + '；'
    + (factorUrl ? '<a href="' + esc(factorUrl) + '" target="_blank" rel="noopener noreferrer">生态环境部公开附件</a>'
      : esc(meta.factorSource || '未提供')) + '<br>'
    + '<b>电价口径：</b>' + esc(base.tariffSource || '') + '；'
    + (tariffUrl ? '<a href="' + esc(tariffUrl) + '" target="_blank" rel="noopener noreferrer">陕西阶梯电价来源</a>'
      : '未提供来源') + '<br>'
    + '<b>政策覆盖：</b>' + esc((meta.policyCoverage || []).join('、') || '未接入地方政策')
    + '；' + esc(coverage.message || '') + '<br>'
    + '<b>计算与展示边界：</b><ul>' + (meta.assumptions || []).map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>';
  planResultEl.hidden = false;
  const balanced = (data.plans || [])[1] || (data.plans || [])[0];
  if (balanced) {
    document.getElementById('heroMoney').innerHTML = fmt(balanced.monthlyMoneySaved) + '<small>元</small>';
    document.getElementById('heroCo2').innerHTML = num(balanced.annualCo2eKg) + '<small>kg</small>';
    const heroPayback = paybackText(balanced.paybackMonths);
    document.getElementById('heroPayback').innerHTML = heroPayback === '无需投入'
      ? '无需投入' : heroPayback.replace(' 个月', '') + '<small>个月</small>';
    document.getElementById('heroPreviewHint').textContent = '最近一次：' + balanced.name;
  }
  document.getElementById('heroPreview').hidden = false;
  document.getElementById('jtHero').classList.remove('no-preview');
}
planForm.addEventListener('submit', async ev => {
  ev.preventDefault();
  setPlanError('');
  const payload = {
    city: formValue('cityInput'),
    housing: formValue('housingInput'),
    residents: numberOrNull('residentsInput'),
    monthlyKwh: numberOrNull('monthlyKwhInput'),
    monthlyBill: numberOrNull('monthlyBillInput'),
    budget: numberOrNull('budgetInput')
  };
  if (!payload.city) { setPlanError('请填写所在城市。'); return; }
  if ([payload.residents, payload.monthlyKwh, payload.monthlyBill, payload.budget]
      .some(v => Number.isNaN(v))) { setPlanError('数字字段格式不正确，请检查后重试。'); return; }
  genPlansBtn.disabled = true;
  genPlansBtn.textContent = '正在计算…';
  planResultEl.hidden = true;
  document.getElementById('heroPreview').hidden = true;
  document.getElementById('jtHero').classList.add('no-preview');
  resetAiExplain();
  setProgress(2, false);
  try {
    const data = await requestJson('/api/energy/plans', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
    }, 16000);
    setProgress(3, true);
    renderPlans(data);
    if (aiReady()) runAiExplanation(payload);
  } catch (err) {
    setProgress(1, false);
    setPlanError(err && err.name === 'AbortError' ? '计算超时，请稍后重试。' : (err.message || '方案生成失败。'));
  } finally {
    genPlansBtn.disabled = false;
    genPlansBtn.textContent = '生成三档方案';
  }
});
planCardsEl.addEventListener('click', ev => {
  const btn = ev.target.closest('[data-record-tier]'); if (!btn || !lastPlans) return;
  const plan = lastPlans.plans.find(p => p.tier === btn.dataset.recordTier); if (!plan) return;
  const lines = ['计划采用「' + plan.name + '」节能方案：']
    .concat(plan.actions.map(a => '· ' + a.name))
    .concat(['预计年节电 ' + num(plan.annualKwhSaved) + ' kWh，年节省电费 ' + fmt(plan.annualMoneySaved)
      + '，年减碳约 ' + num(plan.annualCo2eKg) + ' kg CO₂e（估算）。']);
  document.getElementById('hpInput').value = lines.join('\n');
  document.getElementById('entryType').value = 'planned';
  document.getElementById('hpFlowMsg').textContent = '方案摘要已按「计划执行」带入；完成后可改为「已完成」，再生成碳迹反馈。';
  switchTab('diary');
  setTimeout(() => document.getElementById('hpInput').focus(), 240);
});
