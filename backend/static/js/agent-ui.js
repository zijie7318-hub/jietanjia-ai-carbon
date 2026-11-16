/* 节碳家 · agent-ui.js — 工具型 Agent 前端（独立脚本，不改既有 AI 逻辑）
 * 在 AI 解释区注入「Agent 模式」开关；开启后拦截 runAiExplanation，
 * 改调 /api/energy/agent 并实时渲染「思考 → 调用工具 → 结论」轨迹。
 * 关闭时完全走原有解释链路，零影响。
 */
(function () {
  'use strict';

  var STATE_KEY = 'jtc_agent_mode';
  function agentOn() { try { return localStorage.getItem(STATE_KEY) === '1'; } catch (e) { return false; } }
  function setAgentOn(v) { try { localStorage.setItem(STATE_KEY, v ? '1' : '0'); } catch (e) {} }

  // 等 DOM 与外部脚本就绪
  function init() {
    var box = document.getElementById('aiExplainBox');
    var head = box && box.querySelector('.jt-ai-head');
    var wfTrack = document.getElementById('wfTrack');
    if (!box || !head) return;

    // Agent 模式开关（放在朗读按钮前）
    var label = document.createElement('label');
    label.className = 'agent-toggle';
    label.title = '开启后由 AI Agent 自主调用工具完成分析；数值仍由规则计算';
    label.innerHTML = '<input type="checkbox" id="agentModeChk"><span>Agent 模式</span>';
    // 插到 .jt-ai-head 的子元素最前（b 之后、工具栏之前也可）
    var actions = head.querySelector('div');
    if (actions) actions.insertBefore(label, actions.firstChild);
    else head.appendChild(label);

    var chk = label.querySelector('input');
    chk.checked = agentOn();
    chk.addEventListener('change', function () { setAgentOn(chk.checked); });

    // 覆盖全局解释函数：开启时走 Agent，否则调用保存的原函数
    var original = (typeof window.runAiExplanation === 'function')
      ? window.runAiExplanation : (typeof runAiExplanation === 'function' ? runAiExplanation : null);

    var TOOL_LABEL = {
      get_baseline: '读取用电基线', get_plans: '获取三档方案',
      retrieve_policies: '检索政策条款', finish: '提交解释'
    };

    function renderAgentTrace(events, done, note) {
      var body = document.getElementById('aiExplainBody');
      var state = document.getElementById('aiExplainState');
      if (!body) return;
      var html = '<div class="agent-trace">';
      events.forEach(function (ev) {
        if (ev.kind === 'step') {
          html += '<div class="agent-ev step"><span class="agent-tag">思考 ' + ev.data.step + '</span>'
            + '<span>' + escHtml(ev.data.thought || '') + '</span></div>';
          html += '<div class="agent-ev call"><span class="agent-tag">' + escHtml(TOOL_LABEL[ev.data.tool] || ev.data.tool) + '</span>'
            + '<span class="agent-args">' + escHtml(JSON.stringify(ev.data.args || {})) + '</span></div>';
        } else if (ev.kind === 'tool') {
          var r = ev.data.result || {};
          var summary = r.clauses ? ('返回 ' + r.clauses.length + ' 条政策条款')
            : (r.plans ? ('返回 ' + r.plans.length + ' 档方案') : (r.baseline ? '返回用电基线' : '结果已取得'));
          html += '<div class="agent-ev result"><span class="agent-tag">工具结果</span><span>' + escHtml(summary) + '</span></div>';
        }
      });
      html += '</div>';
      if (done) {
        var tierHtml = (done.tierNotes || []).map(function (x) {
          return '<div class="jt-ai-tier"><b>' + escHtml(x.tierName || x.tier) + '</b><span>' + escHtml(x.note) + '</span></div>';
        }).join('');
        html += '<p>' + escHtml(done.intro || '') + '</p>' + tierHtml;
        if ((done.policyNotes || []).length) {
          html += '<p><b>政策说明</b></p><ul>' + (done.policyNotes || []).map(function (x) {
            return '<li><b>' + escHtml(x.title || x.policyId) + '：</b>' + escHtml(x.note) + '</li>';
          }).join('') + '</ul>';
        }
        if (done.nextStep) html += '<p><b>下一步：</b>' + escHtml(done.nextStep) + '</p>';
      }
      body.innerHTML = html;
      if (state) state.textContent = note || 'Agent 已完成分析 · 数值来自规则与政策检索';
    }

    function escHtml(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
      });
    }

    window.__agentRun = async function (payload) {
      var box2 = document.getElementById('aiExplainBox');
      var state = document.getElementById('aiExplainState');
      var body = document.getElementById('aiExplainBody');
      box2.hidden = false;
      body.innerHTML = '<div class="jt-ai-placeholder"><i></i><span>Agent 正在规划并调用工具…</span></div>';
      if (state) state.textContent = 'Agent 工作中';
      var events = [];
      try {
        var resp = await fetch(apiUrl('/api/energy/agent'), {
          method: 'POST',
          headers: Object.assign({ 'Accept': 'text/event-stream' }, aiJsonHeaders()),
          body: JSON.stringify(Object.assign({}, payload, aiPair(), { stream: 1 }))
        });
        if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);
        var reader = resp.body.getReader(), decoder = new TextDecoder(), buffer = '', done = false;
        while (!done) {
          var step = await reader.read();
          if (step.done) break;
          buffer += decoder.decode(step.value, { stream: true });
          var cut;
          while ((cut = buffer.indexOf('\n\n')) >= 0) {
            var block = buffer.slice(0, cut); buffer = buffer.slice(cut + 2);
            var ev = {}, eventName = 'message';
            block.split('\n').forEach(function (line) {
              if (line.indexOf('event:') === 0) eventName = line.slice(6).trim();
              else if (line.indexOf('data:') === 0) { try { ev = JSON.parse(line.slice(5).trim()); } catch (e) {} }
            });
            if (eventName === 'agent_start') {
              events.push({ kind: 'agent_start', data: ev });
            } else if (eventName === 'step' || eventName === 'tool') {
              events.push({ kind: eventName, data: ev });
              renderAgentTrace(events, null, 'Agent 正在调用工具…');
            } else if (eventName === 'done') {
              events.push({ kind: 'done', data: ev });
              renderAgentTrace(events.filter(function (x) { return x.kind !== 'done'; }), ev.ai, ev.aiNote);
              done = true;
            } else if (eventName === 'fallback') {
              renderAgentTrace([], ev.ai, ev.aiNote);
              done = true;
            } else if (eventName === 'end') {
              done = true;
            }
          }
        }
      } catch (err) {
        if (state) state.textContent = 'Agent 暂不可用';
        body.innerHTML = '<p>Agent 调用失败，规则方案不受影响。' + escHtml(err && err.message || '') + '</p>';
      }
    };

    // 覆盖 runAiExplanation：Agent 开启时拦截（外部脚本用函数声明，需挂到 window）
    if (original) {
      window.runAiExplanation = function (payload) {
        if (agentOn()) { return window.__agentRun(payload); }
        return original(payload);
      };
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(init, 60); });
  else setTimeout(init, 60);
})();
