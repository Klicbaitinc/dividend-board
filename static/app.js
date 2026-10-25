// Filtering, search and sorting for event tables. No dependencies.
document.querySelectorAll('.table-tools').forEach(function (tools) {
  var wrap = tools.nextElementSibling, table = wrap && wrap.querySelector('table');
  if (!table) return;
  var rows = Array.prototype.slice.call(table.tBodies[0].rows), type = 'all', q = '';
  var empty = wrap.nextElementSibling;
  function apply() {
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (type === 'all' || r.dataset.type === type) && (!q || r.dataset.q.indexOf(q) !== -1);
      r.hidden = !ok; if (ok) shown++;
    });
    if (empty && empty.classList.contains('empty-msg')) empty.hidden = shown > 0;
  }
  tools.querySelectorAll('.chip').forEach(function (c) {
    c.addEventListener('click', function () {
      tools.querySelectorAll('.chip').forEach(function (x) { x.classList.remove('on'); });
      c.classList.add('on'); type = c.dataset.filter; apply();
    });
  });
  var s = tools.querySelector('.search');
  if (s) s.addEventListener('input', function () { q = s.value.trim().toLowerCase(); apply(); });
  table.querySelectorAll('th[data-sort]').forEach(function (th, i) {
    var dir = -1;
    th.addEventListener('click', function () {
      dir = -dir; var kind = th.dataset.sort, idx = th.cellIndex;
      rows.sort(function (a, b) {
        var A = a.cells[idx].dataset.v || a.cells[idx].textContent.trim(), B = b.cells[idx].dataset.v || b.cells[idx].textContent.trim();
        if (kind === 'num') { A = A === '' ? -1e9 : +A; B = B === '' ? -1e9 : +B; return (A - B) * dir; }
        return A.localeCompare(B) * dir;
      });
      rows.forEach(function (r) { table.tBodies[0].appendChild(r); });
    });
  });
});
document.querySelectorAll('.search.solo').forEach(function (s) {
  var items = document.querySelectorAll(s.dataset.target);
  s.addEventListener('input', function () {
    var q = s.value.trim().toLowerCase();
    items.forEach(function (a) { a.hidden = q && a.dataset.q.indexOf(q) === -1; });
  });
});
