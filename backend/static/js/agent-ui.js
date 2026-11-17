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

    var THINK_SVG = '<svg class="agent-think-ico" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3 4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="12" cy="12" r="3.4" stroke="currentColor" stroke-width="1.7"/></svg>';
    var CHEV_SVG = '<svg class="agent-think-chev" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="m6 9 6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    function resultSummary(r) {
      if (!r) return '结果已取得';
      if (r.clauses) return '返回 ' + r.clauses.length + ' 条政策条款';
      if (r.plans) return '返回 ' + r.plans.length + ' 档方案';
      if (r.baseline) return '返回用电基线';
      return '结果已取得';
    }

    function renderAgentTrace(events, done, note, open) {
      var body = document.getElementById('aiExplainBody');
      var state = document.getElementById('aiExplainState');
      if (!body) return;
      // 保留已有折叠状态：用户手动开合后不被重渲染打回默认
      var prevWrap = body.querySelector('.agent-think');
      var isOpen = open !== undefined ? open
        : (prevWrap ? prevWrap.getAttribute('data-open') === '1' : !done);

      var steps = events.filter(function (e) { return e.kind === 'step'; });
      var tools = {};
      events.forEach(function (e) { if (e.kind === 'tool') tools[e.data.step] = e.data; });

      var inner = '';
      steps.forEach(function (ev, i) {
        var d = ev.data;
        var isFinish = d.tool === 'finish';
        var tr = tools[d.step];
        var stepCls = isFinish || tr ? 'done' : 'run';
        var chipCls = isFinish ? 'finish' : (tr ? 'done' : 'run');
        inner += '<div class="agent-step ' + stepCls + '">'
          + '<span class="agent-step-n">' + (isFinish || tr ? '✓' : d.step) + '</span>'
          + '<div class="agent-step-main">'
          + '<span class="tool-chip ' + chipCls + '"><span class="dot"></span>'
          + escHtml(TOOL_LABEL[d.tool] || d.tool) + '</span>'
          + (tr ? '<span class="tool-chip-result">' + escHtml(resultSummary(tr.result)) + '</span>' : '')
          + (d.thought ? '<span class="agent-step-thought">' + escHtml(d.thought) + '</span>' : '')
          + '</div></div>';
      });

      var doneCount = steps.filter(function (e) {
        return e.data.tool === 'finish' || tools[e.data.step];
      }).length;
      var mini = '<span class="agent-think-mini">' + steps.map(function (e, i) {
        return '<i class="' + (i < doneCount ? 'on' : '') + '"></i>';
      }).join('') + '</span>';

      var summary = done ? '推理已完成' : '正在推理';
      var html = '<div class="agent-think" data-open="' + (isOpen ? '1' : '0') + '">'
        + '<div class="agent-think-head" role="button" tabindex="0" aria-expanded="' + (isOpen ? 'true' : 'false') + '">'
        + THINK_SVG
        + '<span class="agent-think-sum">' + summary + '<em>工具调用轨迹</em></span>'
        + mini
        + '<span class="agent-think-count">' + steps.length + ' 步</span>'
        + CHEV_SVG
        + '</div>'
        + '<div class="agent-think-body"><div class="agent-think-inner"><div class="agent-think-pad">'
        + (inner || '<div class="agent-step run"><span class="agent-step-n">1</span><div class="agent-step-main"><span class="agent-step-thought">正在读取家庭条件…</span></div></div>')
        + '</div></div></div></div>';

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

      // 折叠交互：点击/回车切换
      var head = body.querySelector('.agent-think-head');
      var wrap = body.querySelector('.agent-think');
      if (head && wrap) {
        var toggle = function () {
          var now = wrap.getAttribute('data-open') === '1';
          wrap.setAttribute('data-open', now ? '0' : '1');
          head.setAttribute('aria-expanded', now ? 'false' : 'true');
        };
        head.addEventListener('click', toggle);
        head.addEventListener('keydown', function (e) {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
        });
      }
      if (state) state.textContent = note || 'Agent 已完成分析 · 数值来自规则与政策检索';
    }

    // 带耗时的加载态（Beautiful UI 01）
    function showLoading(body, state) {
      var t0 = Date.now();
      body.innerHTML = '<div class="loading-state"><span class="loading-dots"><i></i><i></i><i></i></span>'
        + '<span>Agent 正在规划并调用工具…</span><span class="loading-elapsed">0.0s</span></div>';
      if (state) state.textContent = 'Agent 工作中';
      var el = body.querySelector('.loading-elapsed');
      var timer = setInterval(function () {
        if (!el || !document.body.contains(el)) { clearInterval(timer); return; }
        el.textContent = ((Date.now() - t0) / 1000).toFixed(1) + 's';
      }, 100);
      return function stop() { clearInterval(timer); };
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
      var stopLoading = showLoading(body, state);
      var events = [];
      var firstPaint = true;
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
              if (firstPaint) { stopLoading(); firstPaint = false; }
              // 流式过程自动展开跟随（open=true）
              renderAgentTrace(events, null, 'Agent 正在调用工具…', true);
            } else if (eventName === 'done') {
              events.push({ kind: 'done', data: ev });
              if (firstPaint) { stopLoading(); firstPaint = false; }
              // 完成时默认折叠轨迹，把结论推到视线中心
              renderAgentTrace(events.filter(function (x) { return x.kind !== 'done'; }),
                ev.ai, ev.aiNote, false);
              done = true;
            } else if (eventName === 'fallback') {
              if (firstPaint) { stopLoading(); firstPaint = false; }
              renderAgentTrace([], ev.ai, ev.aiNote, false);
              done = true;
            } else if (eventName === 'end') {
              done = true;
            }
          }
        }
        stopLoading();
      } catch (err) {
        stopLoading();
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
