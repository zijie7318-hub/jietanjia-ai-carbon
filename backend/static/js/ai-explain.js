/* 节碳家 · ai-explain.js — AI 解释区：SSE 流式渲染、请求序号与降级展示 */
const aiExplainBox = document.getElementById('aiExplainBox');
const aiExplainState = document.getElementById('aiExplainState');
const aiExplainStages = document.getElementById('aiExplainStages');
const aiExplainBody = document.getElementById('aiExplainBody');
const aiExplainNote = document.getElementById('aiExplainNote');
let aiRequestSeq = 0;
function resetAiExplain() {
  aiRequestSeq += 1;
  aiExplainBox.hidden = true;
  aiExplainState.textContent = '';
  aiExplainBody.innerHTML = '';
  aiExplainNote.textContent = '';
  aiExplainStages.querySelectorAll('span').forEach(x => x.classList.remove('done'));
}
function markAiStages(count) {
  aiExplainStages.querySelectorAll('span').forEach(el => {
    el.classList.toggle('done', Number(el.dataset.aiStage) <= count);
  });
}

/** 把服务端校验后的解释渲染成结构化区块。 */
function renderAiExplanation(aiData, noteText) {
  aiData = aiData || {};
  markAiStages(3);
  aiExplainState.textContent = aiData.mode === 'llm'
    ? 'AI 解释已生成 · 数值仍来自规则计算'
    : 'AI 暂不可用 · 已展示规则解释';
  const tierHtml = (aiData.tierNotes || []).map(item =>
    '<div class="jt-ai-tier"><b>' + esc(item.tierName || item.tier) + '</b><span>' + esc(item.note) + '</span></div>'
  ).join('');
  const policyHtml = (aiData.policyNotes || []).map(item =>
    '<li><b>' + esc(item.title || item.policyId) + '：</b>' + esc(item.note) + '</li>'
  ).join('');
  aiExplainBody.innerHTML =
    (aiData.intro ? '<p>' + esc(aiData.intro) + '</p>' : '')
    + tierHtml
    + (policyHtml ? '<p><b>政策说明</b></p><ul>' + policyHtml + '</ul>' : '')
    + (aiData.nextStep ? '<p><b>下一步：</b>' + esc(aiData.nextStep) + '</p>' : '');
  aiExplainNote.textContent = noteText || '';
}

/** 从还没生成完的 JSON 文本里取出正在增长的 intro，用于逐字预览。 */
function partialIntro(rawText) {
  const m = rawText.match(/"intro"\s*:\s*"((?:[^"\\]|\\.)*)/);
  if (!m) return '';
  try { return JSON.parse('"' + m[1] + '"'); } catch (_) { return m[1]; }
}

/** 解析一个 SSE 事件块，返回 { event, data }。 */
function parseSseBlock(block) {
  let event = 'message';
  let data = '';
  block.split('\n').forEach(line => {
    if (line.indexOf('event:') === 0) event = line.slice(6).trim();
    else if (line.indexOf('data:') === 0) data += line.slice(5).trim();
  });
  if (!data) return null;
  try { return { event: event, data: JSON.parse(data) }; } catch (_) { return null; }
}

/**
 * 流式解释：start/stage → delta 逐字 → done 或 fallback。
 * 返回 true 表示流式路径已被服务端认可并完成；返回 false 时调用方走一次性接口。
 */
async function streamAiExplanation(householdPayload, requestId) {
  const ctrl = typeof AbortController === 'undefined' ? null : new AbortController();
  const timer = setTimeout(() => { if (ctrl) ctrl.abort(); }, 45000);
  try {
    const resp = await fetch(apiUrl('/api/energy/explain'), {
      method: 'POST',
      headers: Object.assign({ 'Accept': 'text/event-stream' }, aiJsonHeaders()),
      body: JSON.stringify(Object.assign({}, householdPayload, aiPair(), { stream: 1 })),
      signal: ctrl ? ctrl.signal : undefined
    });
    if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let raw = '';
    let done = false;
    while (!done) {
      const step = await reader.read();
      if (step.done) break;
      buffer += decoder.decode(step.value, { stream: true });
      let cut = buffer.indexOf('\n\n');
      while (cut >= 0) {
        const parsed = parseSseBlock(buffer.slice(0, cut));
        buffer = buffer.slice(cut + 2);
        cut = buffer.indexOf('\n\n');
        if (!parsed) continue;
        if (requestId !== aiRequestSeq) return true;
        if (parsed.event === 'stage') {
          markAiStages(Number(parsed.data.stage) || 2);
        } else if (parsed.event === 'delta') {
          raw += parsed.data.text || '';
          const intro = partialIntro(raw);
          if (intro) {
            aiExplainBody.innerHTML = '<p>' + esc(intro)
              + '<span class="ai-cursor" aria-hidden="true"></span></p>';
            aiExplainState.textContent = '正在逐字生成解释 · 数值已由服务端算好';
          }
        } else if (parsed.event === 'done' || parsed.event === 'fallback') {
          const retrieval = parsed.data.retrieval || {};
          renderAiExplanation(parsed.data.ai || {}, (parsed.data.aiNote || '')
            + (retrieval.clauseCount ? ' 已检索 ' + retrieval.clauseCount + ' 个政策条款片段，仅使用已接入的西安政策。' : ''));
          done = true;
        } else if (parsed.event === 'end') {
          done = true;
        }
      }
    }
    return done;
  } finally {
    clearTimeout(timer);
  }
}

/** 一次性接口：服务端不支持流式或流式中断时仍能拿到同样的校验结果。 */
async function fetchAiExplanation(householdPayload, requestId) {
  const data = await requestJson('/api/energy/explain', {
    method: 'POST', headers: aiJsonHeaders(),
    body: JSON.stringify(Object.assign({}, householdPayload, aiPair()))
  }, 32000);
  if (requestId !== aiRequestSeq) return;
  const retrieval = data.retrieval || {};
  renderAiExplanation(data.ai || {}, (data.aiNote || '')
    + (retrieval.clauseCount ? ' 已检索 ' + retrieval.clauseCount + ' 个政策条款片段，仅使用已接入的西安政策。' : ''));
}

async function runAiExplanation(householdPayload) {
  if (!aiReady()) { resetAiExplain(); return; }
  const requestId = ++aiRequestSeq;
  aiExplainBox.hidden = false;
  markAiStages(1);
  aiExplainState.textContent = '正在请求服务端重算方案、检索政策条款并生成解释…';
  aiExplainBody.innerHTML = '<div class="jt-ai-placeholder"><i></i><span>AI 解释生成中，方案卡片已可正常查看。</span></div>';
  aiExplainNote.textContent = 'AI 只组织说明，不参与节电量、费用、减碳量和政策资格计算。';
  const canStream = typeof fetch === 'function' && !!window.ReadableStream && !!window.TextDecoder;
  try {
    if (canStream && await streamAiExplanation(householdPayload, requestId)) return;
    await fetchAiExplanation(householdPayload, requestId);
  } catch (err) {
    if (requestId !== aiRequestSeq) return;
    markAiStages(1);
    aiExplainState.textContent = 'AI 解释暂不可用';
    aiExplainBody.innerHTML = '<p>规则方案和全部数值不受影响，可继续比较方案。'
      + esc(err && err.name === 'AbortError' ? '解释请求超时。' : (err.message || '')) + '</p>';
    aiExplainNote.textContent = '即使没有 AI，核心评估、方案计算与政策初筛仍可正常使用。';
  }
}
