/* Diff engine. Works on plain objects, so it does not care where the data came from.

   An object looks like:
     { type: 'Applet', name: 'Account List Applet',
       props: { 'Business Component': 'Account', ... },
       children: [ { type: 'Control', name: 'NewRecord', props: {...}, children: [...] }, ... ] }
*/
(function (root) {
  'use strict';

  var MAX_LINE_CELLS = 4000000; // beyond this the line-by-line table is too large to build

  function text(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  // Line-by-line comparison of two multi-line values (scripts, SQL, long expressions).
  function lineDiff(before, after) {
    var a = text(before).split(/\r?\n/);
    var b = text(after).split(/\r?\n/);
    var out = [];
    var i, j;
    if (a.length * b.length > MAX_LINE_CELLS) {
      a.forEach(function (line) { out.push({ op: 'del', text: line }); });
      b.forEach(function (line) { out.push({ op: 'add', text: line }); });
      return out;
    }
    var width = b.length + 1;
    var table = new Uint32Array((a.length + 1) * width);
    for (i = a.length - 1; i >= 0; i--) {
      for (j = b.length - 1; j >= 0; j--) {
        table[i * width + j] = a[i] === b[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
      }
    }
    i = 0;
    j = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        out.push({ op: 'same', text: a[i] });
        i++;
        j++;
      } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) {
        out.push({ op: 'del', text: a[i++] });
      } else {
        out.push({ op: 'add', text: b[j++] });
      }
    }
    while (i < a.length) { out.push({ op: 'del', text: a[i++] }); }
    while (j < b.length) { out.push({ op: 'add', text: b[j++] }); }
    return out;
  }

  // Every property from either side is kept, changed or not.
  function diffProps(before, after) {
    var names = Object.keys(before || {});
    Object.keys(after || {}).forEach(function (name) {
      if (names.indexOf(name) === -1) { names.push(name); }
    });
    return names.map(function (name) {
      var left = before && name in before ? before[name] : null;
      var right = after && name in after ? after[name] : null;
      return { name: name, before: left, after: right, changed: text(left) !== text(right) };
    });
  }

  // Pair up objects by their id when they have one (a renamed object is still the same object),
  // otherwise by type and name. Repeated names are told apart by their position.
  function pair(listA, listB) {
    var order = [];
    var slots = {};
    function add(list, side) {
      var seen = {};
      (list || []).forEach(function (item) {
        var base = item.id != null ? item.type + '\u0000#' + item.id : item.type + '\u0000' + item.name;
        seen[base] = (seen[base] || 0) + 1;
        var key = base + '\u0000' + seen[base];
        if (!slots[key]) {
          slots[key] = {};
          order.push(key);
        }
        slots[key][side] = item;
      });
    }
    add(listA, 'before');
    add(listB, 'after');
    return order.map(function (key) { return slots[key]; });
  }

  function diffObject(before, after) {
    var source = after || before;
    var props = diffProps(before && before.props, after && after.props);
    var children = pair(before && before.children, after && after.children).map(function (p) {
      return diffObject(p.before, p.after);
    });
    var status = !before ? 'added' : !after ? 'removed' : 'same';
    if (status === 'same') {
      var touched = props.some(function (p) { return p.changed; }) ||
        children.some(function (c) { return c.status !== 'same'; });
      if (touched) { status = 'changed'; }
    }
    var result = { type: source.type, name: source.name, status: status, props: props, children: children };
    // System columns are shown but never make an object count as changed.
    if ((before && before.system) || (after && after.system)) {
      result.system = diffProps(before && before.system, after && after.system);
    }
    if (before && after && before.name !== after.name) { result.renamedFrom = before.name; }
    return result;
  }

  function diffSets(listA, listB) {
    var objects = pair(listA, listB).map(function (p) { return diffObject(p.before, p.after); });
    var counts = { added: 0, removed: 0, changed: 0, same: 0 };
    objects.forEach(function (o) { counts[o.status]++; });
    return { objects: objects, counts: counts };
  }

  root.SiebDiff = { lineDiff: lineDiff, diffObject: diffObject, diffSets: diffSets };
})(this);
