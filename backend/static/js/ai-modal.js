/* 节碳家 · ai-modal.js — AI 配置弹窗与 Key 脱敏展示 */
const aiModal = document.getElementById('aiModal');
const aiOpts = document.getElementById('aiOpts');
const aiForm = document.getElementById('aiForm');
const aiPill = document.getElementById('aiPill');
const aiModelSel = document.getElementById('aiModelSel');
const aiKeyInput = document.getElementById('aiKey');
const aiBaseInput = document.getElementById('aiBase');
const aiModelNameInput = document.getElementById('aiModelName');
const aiCustom = document.getElementById('aiCustom');
const aiMsg = document.getElementById('aiMsg');
LLM_PRESETS.forEach(p => {
  const option = document.createElement('option'); option.value = p.id; option.textContent = p.label;
  aiModelSel.appendChild(option);
});
function syncAiUi() {
  const ready = aiReady();
  aiPill.textContent = ready ? 'AI 已开启' : '开启 AI';
  aiPill.classList.toggle('on', ready);
  aiPill.title = ready ? 'AI 已开启（' + currentLlm().model + ' · ' + maskKey(ai.key) + '）'
    : '配置 AI 用于生成反馈与解释；不配置也可使用规则模式';
  aiCustom.classList.toggle('on', aiModelSel.value === 'custom');
}
function renderKeyState() {
  const el = document.getElementById('aiKeyState');
  const btn = document.getElementById('aiClearKey');
  if (ai.key) {
    el.innerHTML = '当前：<code>' + esc(maskKey(ai.key)) + '</code>　'
      + (ai.remember ? '已记住（本设备）' : '仅本次会话');
    btn.hidden = false;
  } else { el.textContent = '当前：未填写'; btn.hidden = true; }
}
function openAiModal(showForm) {
  aiModelSel.value = ai.preset || 'deepseek';
  aiKeyInput.value = '';
  aiKeyInput.placeholder = ai.key ? '已保存 ' + maskKey(ai.key) + '，留空表示不修改' : 'sk-...';
  document.getElementById('aiRemember').checked = !!ai.remember;
  aiBaseInput.value = ai.baseUrl || '';
  aiModelNameInput.value = ai.model || '';
  aiMsg.textContent = ''; renderKeyState();
  const wantForm = showForm === undefined ? ai.mode === 'llm' : !!showForm;
  aiOpts.hidden = wantForm; aiForm.hidden = !wantForm; aiModal.hidden = false;
  syncAiUi(); if (wantForm) setTimeout(() => aiKeyInput.focus(), 80);
}
function closeAiModal() { aiModal.hidden = true; }
document.getElementById('aiChooseLlm').onclick = () => {
  aiOpts.hidden = true; aiForm.hidden = false;
  aiCustom.classList.toggle('on', aiModelSel.value === 'custom');
  setTimeout(() => aiKeyInput.focus(), 80);
};
document.getElementById('aiChooseLocal').onclick = () => {
  ai.mode = 'local'; persistAi(); syncAiUi(); closeAiModal();
};
document.getElementById('aiCancel').onclick = closeAiModal;
document.getElementById('aiClose').onclick = closeAiModal;
document.getElementById('aiMask').onclick = closeAiModal;
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && !aiModal.hidden) closeAiModal(); });
aiModelSel.onchange = () => { aiCustom.classList.toggle('on', aiModelSel.value === 'custom'); aiMsg.textContent = ''; };
document.getElementById('aiClearKey').onclick = () => {
  clearKey(); aiKeyInput.value = ''; aiKeyInput.placeholder = 'sk-...';
  renderKeyState(); aiMsg.textContent = '已清除本机保存的 Key。';
};
document.getElementById('aiSave').onclick = () => {
  const preset = aiModelSel.value;
  const p = LLM_PRESETS.find(x => x.id === preset) || LLM_PRESETS[0];
  const baseUrl = preset === 'custom' ? aiBaseInput.value.trim() : p.baseUrl;
  const model = preset === 'custom' ? aiModelNameInput.value.trim() : p.model;
  const typed = aiKeyInput.value.trim();
  const remember = !!document.getElementById('aiRemember').checked;
  if (!typed && !ai.key) { aiMsg.textContent = '请填写 API Key。'; return; }
  if (!baseUrl || !model) { aiMsg.textContent = '请填写接口地址和模型名称。'; return; }
  const key = typed || ai.key;
  writeKey(key, remember);
  ai = { mode: 'llm', preset, baseUrl, model, remember, key };
  persistAi(); syncAiUi(); closeAiModal();
};
aiPill.onclick = () => openAiModal();
if (!ai.mode) syncAiUi();
