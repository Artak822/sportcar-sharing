/* @ds-bundle: {"format":4,"namespace":"Pitlane","components":[{"name":"Button"},{"name":"Badge"},{"name":"Input"},{"name":"CarCard"},{"name":"SpecList"},{"name":"BookingSummary"},{"name":"AgentMessage"},{"name":"AgentAction"}]} */
(function () {
  var React = window.React, h = React.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function rub(n) { return n.toLocaleString('ru-RU') + ' ₽'; }
  function omit(o, keys) { var r = {}; for (var k in o) if (keys.indexOf(k) < 0) r[k] = o[k]; return r; }

  function Button(p) {
    var variant = p.variant || 'secondary', size = p.size || 'md';
    var rest = omit(p, ['variant', 'size', 'block', 'className', 'children']);
    return h('button', Object.assign({ type: 'button' }, rest, {
      className: cx('pl-btn', 'pl-btn-' + variant, size === 'lg' && 'pl-btn-lg', p.block && 'pl-btn-block', p.className)
    }), p.children);
  }

  var STATUS_TEXT = { available: 'Свободен', booked: 'Занят', service: 'На обслуживании' };
  function Badge(p) {
    var tone = p.tone || 'neutral';
    return h('span', { className: 'pl-badge pl-badge-' + tone }, p.children || STATUS_TEXT[tone]);
  }

  var uid = 0;
  function Input(p) {
    var idRef = React.useRef(p.id || 'pl-input-' + (++uid));
    var id = idRef.current;
    var rest = omit(p, ['label', 'hint', 'error', 'id', 'className']);
    var hint = p.error || p.hint;
    return h('div', { className: cx('pl-field', p.error && 'pl-field-error', p.className) },
      p.label && h('label', { className: 'pl-label', htmlFor: id }, p.label),
      h('input', Object.assign({ id: id, className: 'pl-input', 'aria-invalid': p.error ? true : undefined, 'aria-describedby': hint ? id + '-hint' : undefined }, rest)),
      hint && h('span', { id: id + '-hint', className: 'pl-hint' }, hint));
  }

  function CarCard(p) {
    var s = p.specs || {};
    var status = p.status || 'available';
    return h('article', { className: 'pl-car' },
      h('div', { className: 'pl-car-photo' },
        p.imageSrc ? h('img', { src: p.imageSrc, alt: p.name }) : h('span', null, 'фото 16:9'),
        h(Badge, { tone: status })),
      h('div', { className: 'pl-car-body' },
        h('h3', { className: 'pl-car-name' }, p.name),
        h('div', { className: 'pl-car-specs' },
          s.power != null && h('div', null, s.power + ' л.с.', h('small', null, 'мощность')),
          s.accel != null && h('div', null, String(s.accel).replace('.', ',') + ' с', h('small', null, '0–100 км/ч')),
          s.seats != null && h('div', null, s.seats, h('small', null, 'мест'))),
        h('div', { className: 'pl-car-foot' },
          h('div', { className: 'pl-price' }, rub(p.pricePerDay), h('small', null, ' /сутки')),
          h(Button, { variant: status === 'available' ? 'primary' : 'secondary', disabled: status !== 'available', onClick: p.onBook },
            status === 'available' ? 'Забронировать' : 'Недоступен'))));
  }

  function SpecList(p) {
    return h('div', { className: cx('pl-specs', p.dark && 'pl-specs-dark') },
      (p.items || []).map(function (it, i) {
        return h('div', { className: 'pl-spec', key: i },
          h('span', { className: 'pl-label' }, it.label),
          h('span', { className: 'pl-spec-value' }, it.value, it.unit && h('small', null, it.unit)));
      }));
  }

  function BookingSummary(p) {
    var base = p.pricePerDay * p.days;
    var extras = p.extras || [];
    var total = extras.reduce(function (a, e) { return a + e.price; }, base);
    return h('section', { className: 'pl-summary' },
      h('h3', null, p.car),
      h('div', { className: 'pl-summary-dates' },
        h('div', null, h('span', { className: 'pl-label' }, 'Забираете'), h('span', { className: 'pl-num' }, p.from)),
        h('div', null, h('span', { className: 'pl-label' }, 'Возвращаете'), h('span', { className: 'pl-num' }, p.to))),
      h('div', { className: 'pl-summary-lines' },
        h('div', { className: 'pl-summary-line' }, h('span', null, rub(p.pricePerDay) + ' × ' + p.days + ' сут.'), h('span', { className: 'pl-num' }, rub(base))),
        extras.map(function (e, i) { return h('div', { className: 'pl-summary-line', key: i }, h('span', null, e.label), h('span', { className: 'pl-num' }, rub(e.price))); }),
        p.deposit != null && h('div', { className: 'pl-summary-line' }, h('span', null, 'Депозит, вернём после сдачи'), h('span', { className: 'pl-num' }, rub(p.deposit)))),
      h('div', { className: 'pl-summary-total' }, h('span', { className: 'pl-label' }, 'Итого'), h('span', { className: 'pl-num' }, rub(total))),
      p.onConfirm && h(Button, { variant: 'primary', size: 'lg', block: true, onClick: p.onConfirm }, p.confirmLabel || 'Забронировать'));
  }

  function AgentMessage(p) {
    var role = p.role || 'agent';
    return h('div', { className: 'pl-msg pl-msg-' + role },
      role === 'agent' && h('div', { className: 'pl-avatar', 'aria-hidden': true }, 'AI'),
      h('div', { className: 'pl-bubble' }, p.children,
        p.time && h('span', { className: 'pl-msg-time' }, p.time)));
  }

  var ACTION_STATUS = { proposed: ['agent', 'Ждёт подтверждения'], running: ['agent', 'Выполняется'], done: ['available', 'Выполнено'], failed: ['booked', 'Не удалось'] };
  function AgentAction(p) {
    var status = p.status || 'proposed', st = ACTION_STATUS[status];
    return h('div', { className: cx('pl-action', status === 'done' && 'pl-action-done', status === 'failed' && 'pl-action-failed'), role: 'group', 'aria-label': p.title },
      h('div', { className: 'pl-action-head' }, h('span', { className: 'pl-tool' }, p.tool), h(Badge, { tone: st[0] }, st[1])),
      h('p', { className: 'pl-action-title' }, p.title),
      p.details && h('dl', { className: 'pl-action-details' }, p.details.map(function (d, i) {
        return [h('dt', { key: 'k' + i }, d.label), h('dd', { key: 'v' + i }, d.value)];
      })),
      p.note && h('p', { className: 'pl-action-note' }, p.note),
      status === 'proposed' && h('div', { className: 'pl-action-btns' },
        h(Button, { variant: 'agent', onClick: p.onConfirm }, p.confirmLabel || 'Подтвердить'),
        h(Button, { variant: 'ghost', onClick: p.onCancel }, 'Отменить')));
  }

  window.Pitlane = Object.assign(window.Pitlane || {}, {
    Button: Button, Badge: Badge, Input: Input, CarCard: CarCard, SpecList: SpecList,
    BookingSummary: BookingSummary, AgentMessage: AgentMessage, AgentAction: AgentAction
  });
})();
