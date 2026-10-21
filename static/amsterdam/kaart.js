/* Amsterdam report maps. Progressive enhancement: the static PNG in each
   <figure class="ams-kaart-fig"> stays visible unless MapLibre and WebGL work.
   All data comes from /amsterdam/data/ on this site; no tiles, fonts or other
   third-party requests. */
(function () {
  'use strict';

  function webgl() {
    try {
      var c = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
    } catch (e) {
      return false;
    }
  }
  if (!window.maplibregl || !webgl()) return;

  var nf = new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 0 });
  var nf1 = new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  function eur(v) { return '€' + nf.format(v); }
  function sgn(v) { return (v > 0 ? '+' : v < 0 ? '−' : '') + nf1.format(Math.abs(v)) + '%'; }
  function mln(v) { return '€' + nf.format(Math.round(v / 1e5) / 10) + ' mln'; }

  var BOUNDS = [[4.72, 52.27], [5.11, 52.43]];

  var LAYERS = {
    gw: {
      title: 'Grondwaarde per m² woonoppervlak',
      prop: 'gw', ramp: 'seq', breaks: 'gw', unit: eur,
      nodata: 'geen eigen schatting'
    },
    gp: {
      title: 'Grondprijs per m² perceel (bij huidige bebouwing)',
      prop: 'gp', ramp: 'seq', breaks: 'gp', unit: eur,
      nodata: 'geen eigen schatting'
    },
    oz: {
      title: 'OZB-verandering typische woning, alleen grond belast',
      prop: 'oz', ramp: 'div', breaks: 'oz',
      unit: function (v) { return (v > 0 ? '+' : v < 0 ? '−' : '') + nf.format(Math.abs(v)) + '%'; },
      nodata: 'niet berekend'
    }
  };

  function stepExpr(prop, breaks, colors) {
    var e = ['step', ['to-number', ['get', prop]], colors[0]];
    for (var i = 0; i < breaks.length; i++) e.push(breaks[i], colors[i + 1]);
    return e;
  }

  function hatch(color) {
    var size = 8, data = new Uint8Array(size * size * 4);
    var bg = [0xef, 0xed, 0xe8], fg = [0xd2, 0xce, 0xc5];
    for (var y = 0; y < size; y++) {
      for (var x = 0; x < size; x++) {
        var on = (x + y) % size === 0 || (x + y) % size === size - 1;
        var c = on ? fg : bg, o = (y * size + x) * 4;
        data[o] = c[0]; data[o + 1] = c[1]; data[o + 2] = c[2]; data[o + 3] = 255;
      }
    }
    return { width: size, height: size, data: data };
  }

  function legend(el, def, breaks, colors, extra) {
    el.textContent = '';
    var h = document.createElement('div');
    h.className = 'ams-legenda-titel';
    h.textContent = def.title;
    el.appendChild(h);
    var list = document.createElement('ul');
    for (var i = 0; i < colors.length; i++) {
      var lo = i === 0 ? null : breaks[i - 1], hi = i < breaks.length ? breaks[i] : null;
      var txt = lo === null ? 'minder dan ' + def.unit(hi) : hi === null ? def.unit(lo) + ' of meer' :
        def.unit(lo) + ' tot ' + def.unit(hi);
      list.appendChild(item(colors[i], txt));
    }
    list.appendChild(item(null, def.nodata, true));
    (extra || []).forEach(function (x) { list.appendChild(item(x[0], x[1])); });
    el.appendChild(list);
  }

  function item(color, text, hatched) {
    var li = document.createElement('li');
    var sw = document.createElement('span');
    sw.className = 'ams-swatch' + (hatched ? ' ams-swatch-geen' : '');
    if (color) sw.style.background = color;
    li.appendChild(sw);
    li.appendChild(document.createTextNode(text));
    return li;
  }

  function row(dl, k, v) {
    var dt = document.createElement('dt'); dt.textContent = k;
    var dd = document.createElement('dd'); dd.textContent = v;
    dl.appendChild(dt); dl.appendChild(dd);
  }

  function buurtPopup(p) {
    var box = document.createElement('div');
    var h = document.createElement('strong'); h.textContent = p.n + ' (' + p.s + ')';
    box.appendChild(h);
    var dl = document.createElement('dl');
    if (p.gw != null) {
      row(dl, 'Grond per m² woonopp.', eur(p.gw) + ' (' + eur(p.gwl) + '–' + eur(p.gwh) + ')');
      row(dl, 'Grond per m² perceel', eur(p.gp) + ' (' + eur(p.gpl) + '–' + eur(p.gph) + ')');
      row(dl, 'Grondaandeel WOZ', p.ga + '%');
    } else {
      row(dl, 'Grondwaarde', p.b === 'wijk' ? 'te weinig woningen of afwijkende WOZ; geen eigen schatting' : 'geen schatting');
    }
    if (p.woz != null) row(dl, 'Gem. WOZ (CBS, 2024)', eur(p.woz));
    if (p.oz != null) row(dl, 'OZB typische woning', sgn(p.oz) + ' (' + (p.ozd > 0 ? '+' : p.ozd < 0 ? '−' : '') + eur(Math.abs(p.ozd)) + ' per jaar)');
    if (p.pt) row(dl, 'Parkeerterrein', nf.format(p.pt) + ' m²' + (p.pv ? ', ' + mln(p.pv) : ''));
    box.appendChild(dl);
    var s = document.createElement('p'); s.className = 'ams-klein'; s.textContent = 'Schatting, geen officiële waarde.';
    box.appendChild(s);
    return box;
  }

  function lotPopup(p) {
    var box = document.createElement('div');
    var h = document.createElement('strong'); h.textContent = p.l;
    box.appendChild(h);
    var dl = document.createElement('dl');
    row(dl, 'Onbebouwd oppervlak', nf.format(p.m) + ' m²');
    if (p.b === 'buurt') row(dl, 'Grondwaarde (schatting)', mln(p.v) + ' (' + mln(p.vl) + '–' + mln(p.vh) + ')');
    else row(dl, 'Grondwaarde', 'niet geschat: ligt in een buurt zonder eigen schatting');
    box.appendChild(dl);
    var s = document.createElement('p'); s.className = 'ams-klein'; s.textContent = 'Eigenaar onbekend; vaak gemeentegrond of erfpacht.';
    box.appendChild(s);
    return box;
  }

  function init(fig) {
    var soort = fig.getAttribute('data-soort');
    var breaks = JSON.parse(fig.getAttribute('data-breaks'));
    var ramps = { seq: JSON.parse(fig.getAttribute('data-seq')), div: JSON.parse(fig.getAttribute('data-div')) };
    var navy = fig.getAttribute('data-navy');
    var el = fig.querySelector('.ams-kaart');
    var leg = fig.querySelector('.ams-legenda');
    fig.classList.add('ams-js');

    var map = new maplibregl.Map({
      container: el,
      style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#edeae3' } }] },
      bounds: BOUNDS,
      maxBounds: [[4.55, 52.18], [5.3, 52.52]],
      attributionControl: false,
      cooperativeGestures: true,
      dragRotate: false,
      pitchWithRotate: false,
      locale: {
        'CooperativeGesturesHandler.WindowsHelpText': 'Gebruik Ctrl + scrollen om in te zoomen',
        'CooperativeGesturesHandler.MacHelpText': 'Gebruik ⌘ + scrollen om in te zoomen',
        'CooperativeGesturesHandler.MobileHelpText': 'Gebruik twee vingers om de kaart te verplaatsen',
        'NavigationControl.ZoomIn': 'Inzoomen', 'NavigationControl.ZoomOut': 'Uitzoomen'
      }
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution: 'Schatting wonenisteduur.nl · CBS, Kadaster/PDOK (CC BY 4.0), BAG, BGT' +
        (soort === 'parkeren' ? ', © OpenStreetMap-bijdragers (ODbL)' : '')
    }));

    map.on('load', function () {
      map.addImage('arcering', hatch());
      map.addSource('buurten', { type: 'geojson', data: '/amsterdam/data/buurten.geojson', promoteId: 'c' });
      map.addLayer({ id: 'geen', type: 'fill', source: 'buurten', paint: { 'fill-pattern': 'arcering' } });
      map.addLayer({ id: 'vlak', type: 'fill', source: 'buurten', paint: { 'fill-color': '#ffffff', 'fill-opacity': soort === 'parkeren' ? 0.75 : 1 } });
      map.addLayer({ id: 'rand', type: 'line', source: 'buurten', paint: { 'line-color': '#ffffff', 'line-width': 0.6 } });
      map.addLayer({
        id: 'hover', type: 'line', source: 'buurten',
        paint: { 'line-color': navy, 'line-width': ['case', ['boolean', ['feature-state', 'hover'], false], 2, 0] }
      });

      function show(key) {
        var def = LAYERS[key], colors = ramps[def.ramp], br = breaks[def.breaks];
        map.setFilter('vlak', ['!=', ['get', def.prop], null]);
        map.setPaintProperty('vlak', 'fill-color', stepExpr(def.prop, br, colors));
        legend(leg, def, br, colors, soort === 'parkeren' ? [[navy, 'parkeerterrein (bovengronds)']] : null);
      }
      show('gw');

      var knoppen = fig.querySelector('.ams-kaart-knoppen');
      if (knoppen) {
        knoppen.hidden = false;
        knoppen.addEventListener('change', function (e) { if (e.target.value) show(e.target.value); });
      }

      var popup = new maplibregl.Popup({ closeButton: true, maxWidth: '300px' });
      var hovered = null;

      if (soort === 'parkeren') {
        map.addSource('park', { type: 'geojson', data: '/amsterdam/data/parkeerterreinen.geojson' });
        map.addLayer({
          id: 'park-vlak', type: 'fill', source: 'park', minzoom: 13,
          filter: ['==', ['geometry-type'], 'Polygon'],
          paint: { 'fill-color': navy, 'fill-opacity': 0.9 }
        });
        map.addLayer({
          id: 'park-punt', type: 'circle', source: 'park', maxzoom: 13,
          filter: ['==', ['geometry-type'], 'Point'],
          paint: {
            'circle-color': navy, 'circle-opacity': 0.85,
            'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.75,
            'circle-radius': ['interpolate', ['linear'], ['sqrt', ['get', 'm']], 20, 1.8, 140, 6]
          }
        });
        ['park-vlak', 'park-punt'].forEach(function (id) {
          map.on('click', id, function (e) {
            popup.setLngLat(e.lngLat).setDOMContent(lotPopup(e.features[0].properties)).addTo(map);
            e.preventDefault();
          });
          map.on('mouseenter', id, function () { map.getCanvas().style.cursor = 'pointer'; });
          map.on('mouseleave', id, function () { map.getCanvas().style.cursor = ''; });
        });
      }

      map.on('mousemove', 'vlak', function (e) {
        if (!e.features.length) return;
        if (hovered !== null) map.setFeatureState({ source: 'buurten', id: hovered }, { hover: false });
        hovered = e.features[0].id;
        map.setFeatureState({ source: 'buurten', id: hovered }, { hover: true });
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'vlak', function () {
        if (hovered !== null) map.setFeatureState({ source: 'buurten', id: hovered }, { hover: false });
        hovered = null;
        map.getCanvas().style.cursor = '';
      });
      map.on('click', function (e) {
        if (e.defaultPrevented) return;
        var f = map.queryRenderedFeatures(e.point, { layers: ['vlak', 'geen'] });
        if (f.length) popup.setLngLat(e.lngLat).setDOMContent(buurtPopup(f[0].properties)).addTo(map);
      });
    });
  }

  document.querySelectorAll('.ams-kaart-fig').forEach(init);
})();
