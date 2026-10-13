(function () {
  'use strict';

  var token = document.querySelector('meta[name="siebdiff-token"]').content;
  var $ = function (id) { return document.getElementById(id); };
  var VIEWS = ['connect-view', 'sides-view', 'objects-view', 'stopped-view'];
  var MAX_LISTED = 200;

  var mode = 'tns';
  var workspaces = [];
  var selected = null;      // the chosen workspace
  var versions = [];        // versions of the chosen workspace, newest first
  var parentBase = null;    // { latest, base } for the chosen workspace in "against its parent" mode
  var versionRequest = 0;   // guards against a slow reply for a workspace no longer selected
  var scanTimer = null;     // polls the search for changed objects
  var changed = null;       // result of that search
  var picked = {};          // object key -> true for the objects ticked for comparison

  function api(method, path, body) {
    return fetch(path, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-SiebDiff-Token': token },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error(data.error || 'Request failed');
          err.data = data;
          throw err;
        }
        return data;
      });
    }, function () {
      throw new Error('SiebDiff is not running. Start it again and reload this page.');
    });
  }

  function show(view, step) {
    VIEWS.forEach(function (id) { $(id).hidden = id !== view; });
    var seen = false;
    Array.prototype.forEach.call($('steps').children, function (li) {
      var current = li.dataset.step === step;
      li.className = current ? 'current' : (!seen && step ? 'done' : '');
      if (current) { seen = true; }
    });
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text != null) { node.textContent = text; }
    return node;
  }

  function facts(target, pairs) {
    target.textContent = '';
    pairs.forEach(function (pair) {
      target.appendChild(el('dt', '', pair[0]));
      target.appendChild(el('dd', '', pair[1]));
    });
  }

  function message(id, text) {
    var box = $(id);
    box.textContent = text || '';
    box.hidden = !text;
    return box;
  }

  // --- Connect ---------------------------------------------------------------

  function setMode(next) {
    mode = next;
    $('tab-tns').setAttribute('aria-selected', String(mode === 'tns'));
    $('tab-basic').setAttribute('aria-selected', String(mode === 'basic'));
    $('mode-tns').hidden = mode !== 'tns';
    $('mode-basic').hidden = mode !== 'basic';
  }

  function renderTns(tns, chosen) {
    var select = $('alias');
    select.textContent = '';
    tns.aliases.forEach(function (name) {
      var option = el('option', '', name);
      option.value = name;
      select.appendChild(option);
    });
    if (chosen && tns.aliases.indexOf(chosen) !== -1) { select.value = chosen; }
    select.disabled = !tns.aliases.length;
    if (!tns.path) {
      $('tns-path').textContent = 'No tnsnames.ora was found on this computer.';
    } else if (!tns.aliases.length) {
      $('tns-path').textContent = tns.path + ' has no database entries.';
    } else {
      $('tns-path').textContent = tns.path;
    }
    $('tns-edit').hidden = !!tns.aliases.length;
    $('tns-input').value = tns.path || '';
  }

  function connectMessage(text, owners) {
    var box = message('connect-msg', text);
    // When the tables live under another owner, offer it as a one-click fix.
    (owners || []).forEach(function (name) {
      var button = el('button', 'link', 'Use ' + name);
      button.type = 'button';
      button.addEventListener('click', function () {
        $('owner').value = name;
        connectMessage('');
        $('password').focus();
      });
      box.appendChild(button);
    });
  }

  function showConnect() {
    show('connect-view', 'connect');
    $($('user').value ? 'password' : 'user').focus();
  }

  function renderState(state) {
    var cfg = state.config;
    setMode(cfg.mode === 'basic' ? 'basic' : 'tns');
    renderTns(state.tns, cfg.alias);
    $('host').value = cfg.host || '';
    $('port').value = cfg.port || 1521;
    $('service').value = cfg.service || '';
    $('user').value = cfg.user || '';
    $('owner').value = cfg.owner || 'SIEBEL';
    if (state.connection) {
      openSides(state.connection);
    } else {
      showConnect();
    }
  }

  // --- Choose sides ----------------------------------------------------------

  function compareMode() {
    return $('mode-parent').checked ? 'parent' : 'versions';
  }

  function openSides(info) {
    $('conn-summary').textContent = info.database + ' (' + info.target + ') · ' + info.user +
      ' · owner ' + info.owner + ' · Oracle ' + info.version;
    workspaces = [];
    selected = null;
    versions = [];
    parentBase = null;
    $('ws-filter').value = '';
    message('sides-msg', '');
    renderWorkspaces('Loading workspaces…');
    renderSelection();
    show('sides-view', 'sides');
    api('GET', '/api/workspaces').then(function (data) {
      workspaces = data.workspaces;
      renderWorkspaces();
      $('ws-filter').focus();
    }, function (err) {
      renderWorkspaces('Workspaces could not be loaded.');
      message('sides-msg', err.message);
    });
  }

  function renderWorkspaces(placeholder) {
    var list = $('ws-list');
    var needParent = compareMode() === 'parent';
    var filter = $('ws-filter').value.trim().toUpperCase();
    list.textContent = '';
    if (placeholder) {
      list.appendChild(el('div', 'empty', placeholder));
      $('ws-count').textContent = '';
      return;
    }
    var matches = workspaces.filter(function (ws) {
      return (!needParent || ws.parent_id) && (!filter || (ws.name || '').toUpperCase().indexOf(filter) !== -1);
    });
    matches.slice(0, MAX_LISTED).forEach(function (ws) {
      var row = el('button');
      row.type = 'button';
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', String(!!selected && selected.id === ws.id));
      row.appendChild(el('span', 'ws-name', ws.name));
      row.appendChild(el('span', 'ws-status', ws.status || ''));
      if (ws.parent) { row.appendChild(el('span', 'ws-parent', 'Parent: ' + ws.parent)); }
      row.addEventListener('click', function () { selectWorkspace(ws); });
      list.appendChild(row);
    });
    if (!matches.length) {
      list.appendChild(el('div', 'empty', 'No workspaces match.'));
    }
    $('ws-count').textContent = matches.length > MAX_LISTED
      ? 'Showing the first ' + MAX_LISTED + ' of ' + matches.length + '. Type more of the name to narrow the list.'
      : matches.length + ' of ' + workspaces.length + ' workspaces';
  }

  function versionLabel(v) {
    var parts = ['v' + v.number];
    if (v.created) { parts.push(String(v.created).slice(0, 10)); }
    if (v.status) { parts.push(v.status); }
    if (v.comments) { parts.push(String(v.comments).slice(0, 60)); }
    return parts.join(' · ');
  }

  function fillVersions(select, value) {
    select.textContent = '';
    versions.forEach(function (v) {
      var option = el('option', '', versionLabel(v));
      option.value = String(v.number);
      select.appendChild(option);
    });
    select.value = String(value);
  }

  function selectWorkspace(ws) {
    selected = ws;
    versions = [];
    parentBase = null;
    message('sides-msg', '');
    renderWorkspaces();
    renderSelection();
    var request = ++versionRequest;
    if (compareMode() !== 'versions') {
      api('GET', '/api/parent-base?ws=' + encodeURIComponent(ws.id)).then(function (data) {
        if (request !== versionRequest) { return; }
        parentBase = data;
        // The version found must belong to the workspace recorded as the parent.
        if (!data.latest) {
          message('sides-msg', 'No versions were found for ' + ws.name + '.');
        } else if (!data.base || data.base.workspace_id !== ws.parent_id) {
          parentBase.base = null;
          message('sides-msg', 'The parent version that ' + ws.name + ' is based on could not be determined.');
        }
        renderSelection();
      }, function (err) {
        if (request === versionRequest) { message('sides-msg', err.message); }
      });
      return;
    }
    api('GET', '/api/versions?ws=' + encodeURIComponent(ws.id)).then(function (data) {
      if (request !== versionRequest) { return; }
      versions = data.versions;
      if (!versions.length) {
        message('sides-msg', 'No versions were found for ' + ws.name + '.');
      }
      renderSelection();
    }, function (err) {
      if (request === versionRequest) { message('sides-msg', err.message); }
    });
  }

  function renderSelection() {
    var byVersions = compareMode() === 'versions';
    var ready = false;
    $('version-fields').hidden = true;
    $('parent-fields').hidden = true;
    if (selected && byVersions && versions.length) {
      if (versions.length < 2) {
        message('sides-msg', selected.name + ' has only one version, so there is nothing to compare it with.');
      } else {
        // Default to the latest version against the one before it.
        fillVersions($('ver-to'), versions[0].number);
        fillVersions($('ver-from'), versions[1].number);
        $('version-fields').hidden = false;
        ready = true;
      }
    } else if (selected && !byVersions && parentBase && parentBase.latest) {
      $('parent-version').value = parentBase.base ? selected.parent + ' · ' + versionLabel(parentBase.base) : '';
      $('child-version').value = versionLabel(parentBase.latest);
      $('parent-fields').hidden = false;
      ready = !!parentBase.base;
    }
    $('sides-next').disabled = !ready;
  }

  function checkVersions() {
    var same = $('ver-from').value === $('ver-to').value;
    message('sides-msg', same ? 'Choose two different versions.' : '');
    $('sides-next').disabled = same;
  }

  function openObjects() {
    var pairs = [['Workspace', selected.name]];
    if (compareMode() === 'versions') {
      pairs.unshift(['Comparison', 'Two versions of one workspace']);
      pairs.push(['From version', $('ver-from').value], ['To version', $('ver-to').value]);
    } else {
      pairs.unshift(['Comparison', 'Workspace against its parent']);
      pairs.push(['Workspace version', String(parentBase.latest.number)],
        ['Parent', selected.parent], ['Parent version', String(parentBase.base.number)]);
    }
    facts($('selection'), pairs);
    show('objects-view', 'objects');
    startScan();
  }

  // --- Select objects --------------------------------------------------------

  function stopPolling() {
    if (scanTimer) { clearTimeout(scanTimer); scanTimer = null; }
  }

  function startScan() {
    var body = { ws: selected.id, mode: compareMode() };
    if (body.mode === 'versions') {
      body.from = $('ver-from').value;
      body.to = $('ver-to').value;
    }
    stopPolling();
    changed = null;
    picked = {};
    message('objects-msg', '');
    $('objects-panel').hidden = true;
    $('objects-next').disabled = true;
    $('scan-progress').hidden = false;
    scanProgress({ done: 0, total: 0, current: '' });
    api('POST', '/api/changes', body).then(scanUpdate, scanFailed);
  }

  function scanProgress(state) {
    $('scan-bar').style.width = (state.total ? Math.round(100 * state.done / state.total) : 0) + '%';
    $('scan-text').textContent = state.total
      ? 'Checking ' + state.current + ' (' + state.done + ' of ' + state.total + ' tables)'
      : 'Reading the repository structure…';
  }

  function scanFailed(err) {
    stopPolling();
    $('scan-progress').hidden = true;
    message('objects-msg', err.message);
  }

  function scanUpdate(state) {
    if ($('objects-view').hidden) { return; }
    if (state.status === 'running') {
      scanProgress(state);
      scanTimer = setTimeout(function () {
        api('GET', '/api/changes').then(scanUpdate, scanFailed);
      }, 600);
    } else if (state.status === 'done') {
      changed = state.result;
      changed.objects.forEach(function (obj) { picked[obj.key] = true; });
      $('scan-progress').hidden = true;
      $('obj-filter').value = '';
      $('objects-panel').hidden = false;
      renderNotes();
      renderObjects();
    } else if (state.status === 'error') {
      scanFailed(new Error(state.error));
    }
  }

  function renderNotes() {
    var box = $('obj-notes');
    box.textContent = '';
    changed.other.forEach(function (item) {
      var names = item.names.length ? ': ' + item.names.join(', ') + (item.count > item.names.length ? ', …' : '') : '';
      box.appendChild(el('p', '', item.count + ' changed row(s) in ' + item.table +
        ' could not be placed under an object' + names));
    });
    changed.warnings.forEach(function (text) { box.appendChild(el('p', '', text)); });
    box.hidden = !box.childNodes.length;
  }

  function visibleObjects() {
    var filter = $('obj-filter').value.trim().toUpperCase();
    return changed.objects.filter(function (obj) {
      return !filter || String(obj.name).toUpperCase().indexOf(filter) !== -1;
    });
  }

  function objectTag(obj) {
    if (obj.deleted) { return 'Deleted'; }
    var parts = [];
    if (obj.self_changed) { parts.push('properties'); }
    if (obj.changes.length) { parts.push(obj.changes.length + (obj.changes.length === 1 ? ' child' : ' children')); }
    return parts.join(' + ');
  }

  function renderObjects() {
    var tree = $('obj-tree');
    var groups = {};
    var order = [];
    tree.textContent = '';
    visibleObjects().forEach(function (obj) {
      if (!groups[obj.type]) { groups[obj.type] = []; order.push(obj.type); }
      groups[obj.type].push(obj);
    });
    order.forEach(function (type) {
      var group = el('div', 'obj-group');
      var head = el('label');
      var all = el('input');
      all.type = 'checkbox';
      all.checked = groups[type].every(function (obj) { return picked[obj.key]; });
      all.addEventListener('change', function () {
        groups[type].forEach(function (obj) { picked[obj.key] = all.checked; });
        renderObjects();
      });
      head.appendChild(all);
      head.appendChild(el('span', '', type + ' (' + groups[type].length + ')'));
      group.appendChild(head);
      groups[type].forEach(function (obj) { group.appendChild(objectRow(obj)); });
      tree.appendChild(group);
    });
    if (!order.length) {
      tree.appendChild(el('div', 'empty', changed.objects.length ? 'No objects match.' : 'No changed objects were found.'));
    }
    var count = changed.objects.filter(function (obj) { return picked[obj.key]; }).length;
    $('obj-count').textContent = count + ' of ' + changed.objects.length + ' objects selected · ' +
      changed.rows + ' changed rows found in ' + changed.tables + ' tables';
  }

  function objectRow(obj) {
    var row = el('div', 'obj-row');
    var head = el('div', 'obj-head');
    var label = el('label');
    var box = el('input');
    box.type = 'checkbox';
    box.checked = !!picked[obj.key];
    box.addEventListener('change', function () {
      picked[obj.key] = box.checked;
      renderObjects();
    });
    label.appendChild(box);
    label.appendChild(el('span', 'obj-name', obj.name));
    head.appendChild(label);
    head.appendChild(el('span', 'obj-tag' + (obj.deleted ? ' deleted' : ''), objectTag(obj)));
    row.appendChild(head);
    if (obj.changes.length) {
      var list = el('ul', 'obj-changes');
      obj.changes.forEach(function (change) {
        var item = el('li', '', change.type + ' ');
        item.appendChild(el('b', '', change.name));
        if (change.path) { item.appendChild(document.createTextNode(' in ' + change.path)); }
        if (change.deleted) { item.appendChild(document.createTextNode(' (deleted)')); }
        list.appendChild(item);
      });
      row.appendChild(list);
    }
    return row;
  }

  function setAllVisible(value) {
    visibleObjects().forEach(function (obj) { picked[obj.key] = value; });
    renderObjects();
  }

  // --- Events ----------------------------------------------------------------

  $('tab-tns').addEventListener('click', function () { setMode('tns'); });
  $('tab-basic').addEventListener('click', function () { setMode('basic'); });

  $('tns-change').addEventListener('click', function () {
    $('tns-edit').hidden = false;
    $('tns-input').focus();
  });

  $('tns-load').addEventListener('click', function () {
    api('POST', '/api/tns', { path: $('tns-input').value }).then(function (tns) {
      connectMessage('');
      renderTns(tns, '');
    }, function (err) { connectMessage(err.message); });
  });

  $('connect-form').addEventListener('submit', function (event) {
    event.preventDefault();
    var button = $('connect-btn');
    button.disabled = true;
    button.textContent = 'Connecting…';
    connectMessage('');
    api('POST', '/api/connect', {
      mode: mode,
      alias: $('alias').value,
      host: $('host').value,
      port: $('port').value,
      service: $('service').value,
      user: $('user').value,
      password: $('password').value,
      owner: $('owner').value
    }).then(function (data) {
      $('password').value = '';
      openSides(data.connection);
    }, function (err) {
      connectMessage(err.message, err.data && err.data.owners);
    }).then(function () {
      button.disabled = false;
      button.textContent = 'Test and connect';
    });
  });

  $('disconnect-btn').addEventListener('click', function () {
    api('POST', '/api/disconnect').then(showConnect);
  });

  $('mode-versions').addEventListener('change', function () {
    renderWorkspaces();
    if (selected) { selectWorkspace(selected); } else { renderSelection(); }
  });
  $('mode-parent').addEventListener('change', function () {
    if (selected && !selected.parent_id) { selected = null; }
    message('sides-msg', '');
    renderWorkspaces();
    if (selected) { selectWorkspace(selected); } else { renderSelection(); }
  });
  $('ws-filter').addEventListener('input', function () { renderWorkspaces(); });
  $('ver-from').addEventListener('change', checkVersions);
  $('ver-to').addEventListener('change', checkVersions);
  $('sides-next').addEventListener('click', openObjects);
  $('objects-back').addEventListener('click', function () {
    stopPolling();
    api('POST', '/api/changes/cancel').then(null, function () {});
    show('sides-view', 'sides');
  });
  $('obj-filter').addEventListener('input', function () { renderObjects(); });
  $('obj-all').addEventListener('click', function () { setAllVisible(true); });
  $('obj-none').addEventListener('click', function () { setAllVisible(false); });

  $('quit').addEventListener('click', function () {
    var stopped = function () {
      $('quit').hidden = true;
      show('stopped-view', '');
    };
    api('POST', '/api/quit').then(stopped, stopped);
  });

  api('GET', '/api/state').then(renderState, function (err) {
    show('connect-view', 'connect');
    connectMessage(err.message);
  });
})();
