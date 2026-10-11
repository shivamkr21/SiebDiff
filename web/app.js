(function () {
  'use strict';

  var token = document.querySelector('meta[name="siebdiff-token"]').content;
  var $ = function (id) { return document.getElementById(id); };
  var mode = 'tns';

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
    ['connect-view', 'connected-view', 'stopped-view'].forEach(function (id) {
      $(id).hidden = id !== view;
    });
    var seen = false;
    Array.prototype.forEach.call($('steps').children, function (li) {
      var current = li.dataset.step === step;
      li.className = current ? 'current' : (!seen && step ? 'done' : '');
      if (current) { seen = true; }
    });
  }

  function setMode(next) {
    mode = next;
    $('tab-tns').setAttribute('aria-selected', String(mode === 'tns'));
    $('tab-basic').setAttribute('aria-selected', String(mode === 'basic'));
    $('mode-tns').hidden = mode !== 'tns';
    $('mode-basic').hidden = mode !== 'basic';
  }

  function renderTns(tns, selected) {
    var select = $('alias');
    select.textContent = '';
    tns.aliases.forEach(function (name) {
      var option = document.createElement('option');
      option.value = option.textContent = name;
      select.appendChild(option);
    });
    if (selected && tns.aliases.indexOf(selected) !== -1) { select.value = selected; }
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

  function message(text, owners) {
    var box = $('connect-msg');
    box.textContent = text || '';
    box.hidden = !text;
    // When the tables live under another owner, offer it as a one-click fix.
    (owners || []).forEach(function (name) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'link';
      button.textContent = 'Use ' + name;
      button.addEventListener('click', function () {
        $('owner').value = name;
        message('');
        $('password').focus();
      });
      box.appendChild(button);
    });
  }

  function renderConnected(info) {
    var facts = $('facts');
    facts.textContent = '';
    [
      ['Database', info.database + ' (' + info.target + ')'],
      ['Oracle version', info.version],
      ['Signed in as', info.user],
      ['Table owner', info.owner],
      ['Workspaces found', String(info.workspaces)]
    ].forEach(function (pair) {
      var dt = document.createElement('dt');
      var dd = document.createElement('dd');
      dt.textContent = pair[0];
      dd.textContent = pair[1];
      facts.appendChild(dt);
      facts.appendChild(dd);
    });
    show('connected-view', 'sides');
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
      renderConnected(state.connection);
    } else {
      show('connect-view', 'connect');
      $(cfg.user ? 'password' : 'user').focus();
    }
  }

  $('tab-tns').addEventListener('click', function () { setMode('tns'); });
  $('tab-basic').addEventListener('click', function () { setMode('basic'); });

  $('tns-change').addEventListener('click', function () {
    $('tns-edit').hidden = false;
    $('tns-input').focus();
  });

  $('tns-load').addEventListener('click', function () {
    api('POST', '/api/tns', { path: $('tns-input').value }).then(function (tns) {
      message('');
      renderTns(tns, '');
    }, function (err) { message(err.message); });
  });

  $('connect-form').addEventListener('submit', function (event) {
    event.preventDefault();
    var button = $('connect-btn');
    button.disabled = true;
    button.textContent = 'Connecting…';
    message('');
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
      renderConnected(data.connection);
    }, function (err) {
      message(err.message, err.data && err.data.owners);
    }).then(function () {
      button.disabled = false;
      button.textContent = 'Test and connect';
    });
  });

  $('disconnect-btn').addEventListener('click', function () {
    api('POST', '/api/disconnect').then(function () {
      show('connect-view', 'connect');
      $('password').focus();
    });
  });

  $('quit').addEventListener('click', function () {
    var stopped = function () {
      $('quit').hidden = true;
      show('stopped-view', '');
    };
    api('POST', '/api/quit').then(stopped, stopped);
  });

  api('GET', '/api/state').then(renderState, function (err) {
    show('connect-view', 'connect');
    message(err.message);
  });
})();
