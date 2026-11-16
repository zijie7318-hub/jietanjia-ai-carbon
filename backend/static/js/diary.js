/* 节碳家 · diary.js — 碳迹日记的生成、带入与保存 */
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
const hpAuthMsgEl = document.getElementById('hpAuthMsg');
const hpAuthBoxEl = document.getElementById('hpAuthBox');
const hpUserEl = document.getElementById('hpUser');
const hpPassEl = document.getElementById('hpPass');
const hpGenBtn = document.getElementById('hpGenBtn');
const HP_TOKEN_KEY = 'jtc_token';
let hpMe = null, hpCurrent = null, hpItems = [];

function friendlyErr(msg) {
  const m = String(msg || '');
  if (/429|限流|太频繁/i.test(m)) return '请求有点频繁，请稍等片刻再试。';
  if (/超时|timeout|AbortError/i.test(m)) return '请求超时，请检查网络后重试。';
  if (/Failed to fetch|NetworkError|Load failed/i.test(m)) return '网络连接中断，请稍后重试。';
  if (/401|403|登录|令牌/i.test(m)) return '登录状态已失效，请重新登录。';
  return m || '操作失败，请稍后重试。';
}
function hpErrText(e) {
  const m = e && e.message ? e.message : '';
  return /Failed to fetch|NetworkError|Load failed|fetch/i.test(m) ? '账号服务暂时不可用，请稍后重试。' : m;
}
/** @param {string} text @param {string} entryType @returns {string} */
function composeFeedback(text, entryType) {
  const action = text.replace(/[。！!，,、；;：:？?～~\s]+$/g, '').trim().slice(0, 80);
  const doneTemplates = [
    '今天你完成了「' + action + '」。这不是一句口号，而是一个已经发生的行动。把它留在这里，下一次评估时你会更清楚哪些改变真正适合自己。',
    '「' + action + '」已经写进今天的碳迹。单次行动看起来很小，但可回看的记录会帮你判断哪些习惯值得继续。',
    '今天的行动是「' + action + '」。先做能做的，再根据账单和实际体验调整，比追求一次到位更可靠。'
  ];
  const plannedTemplates = [
    '你把「' + action + '」列入了下一步计划。先确认执行条件和时间，完成后再回来把状态改为已完成。',
    '「' + action + '」已作为计划行动保存。计划不等于已经产生的减碳结果，完成后记得补上实际执行记录。',
    '下一步计划是「' + action + '」。从一项能真正执行的措施开始，之后再用账单和体验复盘。'
  ];
  const templates = entryType === 'planned' ? plannedTemplates : doneTemplates;
  const idx = [...text].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % templates.length;
  return templates[idx];
}
/**
 * @param {string} content
 * @param {string} source
 * @param {string} inputText
 * @param {string} entryType
 */
function hpShow(content, source, inputText, entryType) {
  hpCurrent = { input: inputText, content, scene: entryType };
  hpLabelEl.textContent = entryType === 'planned' ? '碳迹计划 · 待执行' : '今日碳迹 · 已完成';
  hpTextEl.textContent = content;
  hpSrcEl.textContent = source;
  hpResultEl.hidden = false;
  hpSaveMsg('');
}
async function hpRun() {
  const text = hpInputEl.value.trim();
  if (!text) { hpFlowMsgEl.textContent = '先写下一件已经完成或准备执行的节能行动。'; hpInputEl.focus(); return; }
  hpFlowMsgEl.textContent = '';
  const entryType = document.getElementById('entryType').value;
  const sceneLabel = entryType === 'planned' ? '计划执行' : '已完成';
  const old = hpGenBtn.textContent;
  hpGenBtn.disabled = true; hpGenBtn.textContent = '生成中…';
  try {
    if (aiReady()) {
      try {
        const data = await requestJson('/api/llm/carbon-feedback', {
          method: 'POST', headers: aiJsonHeaders(),
          body: JSON.stringify({ text, scene: sceneLabel, ...aiPair() })
        }, 22000);
        hpShow(data.content, 'AI 生成 · ' + currentLlm().model, text, entryType);
      } catch (err) {
        hpShow(composeFeedback(text, entryType), 'AI 失败，已使用本地模板', text, entryType);
        hpFlowMsgEl.textContent = 'AI 调用失败，已自动降级：' + friendlyErr(err.message);
      }
    } else {
      hpShow(composeFeedback(text, entryType), '本地模板 · 规则模式', text, entryType);
    }
  } finally { hpGenBtn.disabled = false; hpGenBtn.textContent = old; }
}
async function hpSave() {
  if (!hpCurrent) return;
  if (!hpMe) {
    hpSaveMsg('登录后才能保存，换设备登录同一账号也能看到。', false);
    hpAuthBoxEl.hidden = false; hpUserEl.focus(); return;
  }
  const btn = document.getElementById('hpSaveBtn');
  btn.disabled = true; hpSaveMsg('保存中…', true);
  try {
    const token = localStorage.getItem(HP_TOKEN_KEY) || '';
    await requestJson('/api/carbon-entries', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-HT-Token': token },
      body: JSON.stringify({ inputText: hpCurrent.input, content: hpCurrent.content, scene: hpCurrent.scene })
    }, 15000);
    hpSaveMsg('已保存到碳档案。', true);
    hpLoadList();
  } catch (err) {
    hpSaveMsg('保存失败：' + hpErrText(err), false);
  } finally { btn.disabled = false; }
}
async function hpDelete(id) {
  const token = localStorage.getItem(HP_TOKEN_KEY) || '';
  try {
    await requestJson('/api/carbon-entries/' + id, { method: 'DELETE', headers: { 'X-HT-Token': token } }, 12000);
    hpLoadList();
  } catch (err) {
    recEmptyEl.hidden = false; recEmptyEl.textContent = '删除失败：' + hpErrText(err);
  }
}
async function hpMarkDone(id) {
  const token = localStorage.getItem(HP_TOKEN_KEY) || '';
  try {
    await requestJson('/api/carbon-entries/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-HT-Token': token },
      body: JSON.stringify({ status: 'done' })
    }, 12000);
    hpLoadList();
  } catch (err) {
    recEmptyEl.hidden = false; recEmptyEl.textContent = '更新失败：' + hpErrText(err);
  }
}
document.querySelectorAll('#hpChips .chip').forEach(chip => {
  chip.onclick = () => { hpInputEl.value = chip.dataset.text || ''; hpInputEl.focus(); };
});
hpGenBtn.onclick = hpRun;
document.getElementById('hpCopyBtn').onclick = async ev => {
  if (hpCurrent && await copyText(hpCurrent.content)) flashBtn(ev.currentTarget, '已复制');
};
document.getElementById('hpSaveBtn').onclick = hpSave;
document.getElementById('hpClearBtn').onclick = () => {
  hpInputEl.value = ''; hpCurrent = null; hpResultEl.hidden = true;
  hpSaveMsg(''); hpFlowMsgEl.textContent = ''; hpInputEl.focus();
};
document.getElementById('hpToggleAuth').onclick = () => {
  hpAuthBoxEl.hidden = !hpAuthBoxEl.hidden;
  if (!hpAuthBoxEl.hidden) hpUserEl.focus();
};
