// M.I.N.D's hologram engine: draws a scene of simple 3D shapes as a glowing hologram
// (broken light lines, sparkles, a projector beam and a scan sweep), like Jarvis's displays.
// The AI never writes drawing code: it only describes the scene (SCENE below, filled in by showcase.py),
// so every animation looks good. Plain canvas 2D, no libraries, works offline.
const SCENE = __SCENE__;

const COLOURS = {
  gold: [255, 170, 60], cyan: [70, 215, 255], blue: [80, 140, 255], red: [255, 80, 70],
  green: [90, 255, 150], purple: [190, 110, 255], white: [220, 235, 255], orange: [255, 130, 40],
};
const colourOf = (name) => COLOURS[name] || COLOURS[SCENE.colour] || COLOURS.gold;

const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');
let W = 0, H = 0;
function resize() {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  W = canvas.width = Math.floor(innerWidth * ratio);
  H = canvas.height = Math.floor(innerHeight * ratio);
}
addEventListener('resize', resize);
resize();

// ---------- Small 3D maths ----------
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
const len = (a) => Math.hypot(a[0], a[1], a[2]) || 1e-6;
const norm = (a) => mul(a, 1 / len(a));
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
function rotX(p, a) { const c = Math.cos(a), s = Math.sin(a); return [p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c]; }
function rotY(p, a) { const c = Math.cos(a), s = Math.sin(a); return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c]; }
function rotZ(p, a) { const c = Math.cos(a), s = Math.sin(a); return [p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2]]; }
function rotAll(p, r) { return r ? rotY(rotX(rotZ(p, r[2] || 0), r[0] || 0), r[1] || 0) : p; }
const num = (v, d) => (typeof v === 'number' && isFinite(v) ? v : d);
const vec = (v, d) => (Array.isArray(v) && v.length === 3 ? v.map((x, i) => num(x, d[i])) : d);

// ---------- Shapes -> lines (each line is a list of points) and sparkle points ----------
const SEG = 28;
function ring(center, u, v, ru, rv, n = SEG) {
  const line = [];
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    line.push(add(center, add(mul(u, Math.cos(a) * ru), mul(v, Math.sin(a) * rv))));
  }
  return line;
}
function ellipsoid(at, r) {
  const lines = [];
  for (let k = 1; k < 7; k++) {  // rings around (latitude)
    const a = -Math.PI / 2 + (k / 7) * Math.PI, y = Math.sin(a) * r[1], s = Math.cos(a);
    lines.push(ring([at[0], at[1] + y, at[2]], [1, 0, 0], [0, 0, 1], r[0] * s, r[2] * s));
  }
  for (let k = 0; k < 6; k++) {  // meridians
    const a = (k / 6) * Math.PI;
    lines.push(ring(at, [Math.cos(a), 0, Math.sin(a)], [0, 1, 0],
      Math.hypot(Math.cos(a) * r[0], Math.sin(a) * r[2]), r[1]));
  }
  return lines;
}
function tube(from, to, r1, r2) {
  // A cylinder (r1 = r2) or a cone (r2 = 0) from one point to another
  const axis = sub(to, from), dir = norm(axis);
  const helper = Math.abs(dir[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
  const u = norm(cross(dir, helper)), v = cross(dir, u);
  const lines = [];
  for (let k = 0; k <= 4; k++) {
    const t = k / 4, r = r1 + (r2 - r1) * t;
    if (r > 0.01) lines.push(ring(add(from, mul(axis, t)), u, v, r, r, 18));
  }
  for (let k = 0; k < 8; k++) {
    const a = (k / 8) * Math.PI * 2, side = add(mul(u, Math.cos(a)), mul(v, Math.sin(a)));
    lines.push([add(from, mul(side, r1)), add(to, mul(side, r2))]);
  }
  return lines;
}
function torus(at, big, small) {
  const lines = [];
  for (let k = 0; k < 3; k++) lines.push(ring([at[0], at[1] + (k - 1) * small, at[2]], [1, 0, 0], [0, 0, 1],
    big + (k === 1 ? small : 0), big + (k === 1 ? small : 0), 40));
  for (let k = 0; k < 14; k++) {
    const a = (k / 14) * Math.PI * 2, c = [at[0] + Math.cos(a) * big, at[1], at[2] + Math.sin(a) * big];
    lines.push(ring(c, [Math.cos(a), 0, Math.sin(a)], [0, 1, 0], small, small, 12));
  }
  return lines;
}
function box(at, s) {
  const [x, y, z] = mul(s, 0.5), c = (dx, dy, dz) => add(at, [dx * x, dy * y, dz * z]);
  const e = [[-1, -1, -1, 1, -1, -1], [-1, 1, -1, 1, 1, -1], [-1, -1, 1, 1, -1, 1], [-1, 1, 1, 1, 1, 1],
    [-1, -1, -1, -1, 1, -1], [1, -1, -1, 1, 1, -1], [-1, -1, 1, -1, 1, 1], [1, -1, 1, 1, 1, 1],
    [-1, -1, -1, -1, -1, 1], [1, -1, -1, 1, -1, 1], [-1, 1, -1, -1, 1, 1], [1, 1, -1, 1, 1, 1]];
  const lines = e.map((q) => [c(q[0], q[1], q[2]), c(q[3], q[4], q[5])]);
  for (let k = 1; k < 4; k++) {  // a light grid on the faces
    const t = -1 + k / 2;
    lines.push([c(t, -1, 1), c(t, 1, 1)], [c(-1, t, 1), c(1, t, 1)], [c(1, t, -1), c(1, t, 1)]);
  }
  return lines;
}
function smooth(points, steps = 6) {
  // Catmull-Rom: a few control points -> a smooth curve (snakes, tails, necks)
  if (points.length < 3) return points;
  const out = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(i - 1, 0)], p1 = points[i], p2 = points[i + 1], p3 = points[Math.min(i + 2, points.length - 1)];
    for (let s = 0; s < steps; s++) {
      const t = s / steps, t2 = t * t, t3 = t2 * t;
      out.push([0, 1, 2].map((k) => 0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t
        + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)));
    }
  }
  out.push(points[points.length - 1]);
  return out;
}

// ---------- Build the scene once ----------
const things = (SCENE.things || []).map((thing, index) => {
  const parts = (thing.parts || []).map((p) => {
    const shape = p.shape, at = vec(p.at, [0, 0, 0]);
    let lines = [], pivot = at;
    if (shape === 'sphere') { const r = num(Array.isArray(p.size) ? p.size[0] : p.size, 1); lines = ellipsoid(at, [r, r, r]); }
    else if (shape === 'ellipsoid') lines = ellipsoid(at, vec(p.size, [1, 1, 1]));
    else if (shape === 'cylinder' || shape === 'cone') {
      const from = vec(p.from, [0, 0, 0]), to = vec(p.to, [0, 1, 0]), r = num(p.radius, 0.3);
      lines = tube(from, to, r, shape === 'cone' ? 0 : num(p.radius2, r)); pivot = from;
    } else if (shape === 'torus') { const s = Array.isArray(p.size) ? p.size : [1, 0.25]; lines = torus(at, num(s[0], 1), num(s[1], 0.25)); }
    else if (shape === 'box') lines = box(at, vec(p.size, [1, 1, 1]));
    else if (shape === 'curve' && Array.isArray(p.points) && p.points.length > 1) {
      const pts = smooth(p.points.map((q) => vec(q, [0, 0, 0])));
      lines = [pts]; pivot = pts[0];
      const r = num(p.radius, 0);
      if (r > 0) for (let i = 0; i < pts.length; i += 2) {  // a tube around it (a snake's body)
        const next = pts[Math.min(i + 1, pts.length - 1)], dir = norm(sub(next, pts[Math.max(i - 1, 0)]));
        const helper = Math.abs(dir[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0], u = norm(cross(dir, helper));
        lines.push(ring(pts[i], u, cross(dir, u), r * (1 - 0.6 * i / pts.length), r * (1 - 0.6 * i / pts.length), 10));
      }
    }
    if (p.rot) lines = lines.map((l) => l.map((q) => add(at, rotAll(sub(q, at), p.rot))));
    const sparks = [];
    lines.forEach((l) => l.forEach((q, i) => { if (i % 5 === 0) sparks.push(q); }));
    return { lines, sparks, pivot, swing: p.swing, wave: p.wave, colour: p.colour || thing.colour };
  });
  return { name: thing.name || 'thing', at: vec(thing.at, [0, 0, 0]), scale: num(thing.scale, 1),
    move: thing.move || {}, parts, index };
});

// Circles to walk on stay close to the creatures' own size (a wide circle made them tiny on screen)
things.forEach((t) => {
  let size = 0.5;
  t.parts.forEach((p) => p.lines.forEach((l) => l.forEach((q) => { size = Math.max(size, Math.hypot(q[0], q[2]) * t.scale); })));
  if (['orbit', 'chase', 'pace'].includes(t.move.type)) t.move.radius = Math.min(num(t.move.radius, 4), size * 0.75);
});

// Fit everything on screen: the biggest distance from the middle (plus how far things travel)
let reach = 1;
things.forEach((t) => {
  const travel = ['orbit', 'chase'].includes(t.move.type) ? num(t.move.radius, 4) : 0;
  t.parts.forEach((p) => p.lines.forEach((l) => l.forEach((q) => {
    reach = Math.max(reach, Math.hypot(q[0] * t.scale, q[2] * t.scale) + Math.hypot(t.at[0], t.at[2]) + travel);
  })));
});
// ...and from the lowest to the highest point (a dragon high above a castle: both stay in view)
let lowY = Infinity, highY = -Infinity;
things.forEach((t) => t.parts.forEach((p) => p.lines.forEach((l) => l.forEach((q) => {
  const y = q[1] * t.scale + t.at[1];
  if (isFinite(y)) { lowY = Math.min(lowY, y); highY = Math.max(highY, y); }
}))));
if (!isFinite(lowY)) { lowY = 0; highY = 1; }
const middleY = (lowY + highY) / 2;
reach = Math.max(reach, (highY - lowY) * 0.6);
if (!isFinite(reach) || reach <= 0) reach = 5;

// ---------- Moving things ----------
function placeOf(thing, time) {
  const m = thing.move, speed = num(m.speed, 1);
  let pos = thing.at, face = 0;
  if (m.type === 'orbit' || m.type === 'chase') {
    const r = num(m.radius, 4), a = time * 0.6 * speed + num(m.offset, 0);
    pos = [Math.cos(a) * r, thing.at[1], Math.sin(a) * r];
    face = -a;  // looks the way it travels
  } else if (m.type === 'pace') {  // walks back and forth
    const d = num(m.radius, 3), x = Math.sin(time * 0.5 * speed) * d;
    pos = [thing.at[0] + x, thing.at[1], thing.at[2]];
    face = Math.cos(time * 0.5 * speed) >= 0 ? 0 : Math.PI;
  }
  let y = pos[1];
  if (m.type === 'bob') y += Math.sin(time * 2 * speed) * 0.3;
  if (m.type === 'hop' || m.hop) y += Math.abs(Math.sin(time * 3 * speed)) * num(m.height, 0.8);
  const spin = m.type === 'spin' ? time * speed : 0;
  return { pos: [pos[0], y, pos[2]], turn: face + spin + num(thing.move.facing, 0) };
}
function movePoint(q, part, time) {
  let p = q;
  if (part.wave) {  // a ripple along it (snakes, tails, flags)
    const w = part.wave, along = q[0] + q[2];
    p = [p[0], p[1] + Math.sin(time * num(w.speed, 3) + along * 1.5) * num(w.amount, 0.3) * 0.5,
      p[2] + Math.sin(time * num(w.speed, 3) + along * 1.5) * num(w.amount, 0.3)];
  }
  if (part.swing) {  // legs walking, a tail wagging, wings flapping: turns around its pivot
    const s = part.swing, a = Math.sin(time * num(s.speed, 3) + num(s.phase, 0)) * num(s.amount, 0.5);
    const d = sub(p, part.pivot);
    const r = s.axis === 'x' ? rotX(d, a) : s.axis === 'y' ? rotY(d, a) : rotZ(d, a);
    p = add(part.pivot, r);
  }
  return p;
}

// ---------- Drawing ----------
const dust = Array.from({ length: 160 }, () => ({ a: Math.random() * 6.3, r: Math.random(), y: Math.random(), s: 0.2 + Math.random() }));
let start = performance.now();

// One frame. If something goes wrong in a frame, the next one still comes (a blank, frozen hologram
// was seen once), and the problem is told to the HUD, which writes it in M.I.N.D's log.
let told = false;
function frame(now) {
  try {
    if (W > 0 && H > 0) draw(now);
  } catch (error) {
    if (!told) {
      told = true;
      parent.postMessage({ hologramProblem: String(error && error.stack || error).slice(0, 300) }, '*');
    }
  }
  requestAnimationFrame(frame);
}

function draw(now) {
  const time = (now - start) / 1000;
  const base = colourOf();
  const unit = Math.min(W, H) * 0.5 / reach;  // world -> screen size
  const cx = W / 2, cy = H * 0.52;
  const camTurn = time * 0.25, tilt = 0.32;
  const scanY = middleY + Math.sin(time * 0.9) * reach * 0.7;

  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = 'rgba(2,5,10,0.55)';  // a short trail: lines leave a faint afterglow
  ctx.fillRect(0, 0, W, H);
  ctx.globalCompositeOperation = 'lighter';

  const project = (p) => {
    let q = rotY([p[0], p[1] - middleY, p[2]], camTurn);
    q = rotX(q, tilt);
    const depth = 1 / Math.max(0.3, 1 + q[2] / (reach * 5));  // (never a giant point right at the camera)
    return [cx + q[0] * unit * depth, cy - q[1] * unit * depth, depth];
  };

  // The projector: rings on the floor and a beam of light going up
  const floor = (things.length ? Math.min(...things.map((t) => t.at[1])) : 0) - 0.2;
  for (let k = 0; k < 4; k++) {
    const r = reach * (0.35 + k * 0.22);
    ctx.beginPath();
    for (let i = 0; i <= 64; i++) {
      if ((i + k * 3 + Math.floor(time * 4)) % 9 === 0) continue;  // gaps, like a dial
      const a = (i / 64) * Math.PI * 2 + time * (k % 2 ? -0.3 : 0.2);
      const [x, y] = project([Math.cos(a) * r, floor, Math.sin(a) * r]);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.strokeStyle = `rgba(${base},${0.25 - k * 0.04})`;
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }
  const [bx, by] = project([0, floor, 0]);
  const beam = ctx.createRadialGradient(bx, by, 0, bx, by, reach * unit * 1.5);
  beam.addColorStop(0, `rgba(${base},0.08)`);
  beam.addColorStop(1, `rgba(${base},0)`);
  ctx.fillStyle = beam;
  ctx.beginPath();
  ctx.moveTo(bx - reach * unit * 0.2, by);
  ctx.lineTo(bx + reach * unit * 0.2, by);
  ctx.lineTo(bx + reach * unit * 1.0, by - reach * unit * 1.5);
  ctx.lineTo(bx - reach * unit * 1.0, by - reach * unit * 1.5);
  ctx.fill();

  // Swirling broken rings around the hologram (like Jarvis's globe of light)
  for (let k = 0; k < 3; k++) {
    const r = reach * (0.75 + k * 0.12), tiltK = 0.5 + k * 0.45, spin = time * (0.4 + k * 0.17) * (k % 2 ? -1 : 1);
    ctx.beginPath();
    for (let i = 0; i <= 90; i++) {
      const a = (i / 90) * Math.PI * 2 + spin;
      let q = [Math.cos(a) * r, 0, Math.sin(a) * r];
      q = rotZ(rotX(q, tiltK), k * 1.1);
      const [x, y] = project([q[0], q[1] + middleY, q[2]]);
      // gaps that travel around the ring (made by hand: Chrome's own dashed lines hung on some scenes)
      (i === 0 || (i + Math.floor(time * 12 * (k + 1))) % 7 < 2) ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.lineWidth = 1.2 * (W / 1400 + 0.5);
    ctx.strokeStyle = `rgba(${base},0.32)`;
    ctx.stroke();
  }

  // The things themselves: every line twice (a wide soft glow, then a thin bright core),
  // broken into dashes that drift, so it looks like light fragments rather than solid drawing
  things.forEach((thing) => {
    const place = placeOf(thing, time);
    thing.parts.forEach((part, pi) => {
      const c = colourOf(part.colour);
      const flicker = 0.85 + 0.15 * Math.sin(time * 13 + pi * 7 + thing.index);
      const points = part.lines.map((line) => line.map((q) => {
        const moved = movePoint(q, part, time);
        const world = add(rotY(mul(moved, thing.scale), place.turn), place.pos);
        return [...project(world), world[1]];
      }));
      for (const [width, alpha, broken] of [[5, 0.1, false], [1.5, 0.75, true]]) {
        ctx.lineWidth = width * (W / 1400 + 0.5);
        ctx.strokeStyle = `rgba(${c},${alpha * flicker})`;
        ctx.beginPath();
        const shift = Math.floor(time * 10) + pi * 3;
        points.forEach((line) => {
          let pen = false;
          line.forEach(([x, y], i) => {
            if (!isFinite(x) || !isFinite(y) || Math.abs(x) > W * 3 || Math.abs(y) > H * 3) { pen = false; return; }
            // the bright core is broken into light fragments with gaps that drift along the lines
            if (broken && (i + shift) % 5 === 0) { pen = false; return; }
            pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
            pen = true;
          });
        });
        ctx.stroke();
      }
      // Sparkles, brighter where the scan line passes
      part.sparks.forEach((q, i) => {
        if ((i + Math.floor(time * 6)) % 3) return;
        const world = add(rotY(mul(movePoint(q, part, time), thing.scale), place.turn), place.pos);
        const [x, y, d] = project(world);
        const near = Math.max(0, 1 - Math.abs(world[1] - scanY) / (reach * 0.12));
        const size = (1 + near * 1.6) * d * (W / 1400 + 0.5);
        ctx.fillStyle = near > 0.1 ? `rgba(255,255,240,${0.4 + near * 0.6})` : `rgba(${c},0.8)`;
        ctx.fillRect(x - size / 2, y - size / 2, size, size);
      });
    });
  });

  // The scan sweep: a thin bright band moving up and down
  const [, sy] = project([0, scanY, 0]);
  const glowBand = ctx.createRadialGradient(cx, sy, 0, cx, sy, reach * unit);
  glowBand.addColorStop(0, `rgba(${base},0.10)`);
  glowBand.addColorStop(1, `rgba(${base},0)`);
  ctx.fillStyle = glowBand;
  ctx.fillRect(cx - reach * unit, sy - 3, reach * unit * 2, 6);

  // Light dust rising out of the projector
  dust.forEach((p) => {
    p.y = (p.y + 0.0025 * p.s) % 1;
    const r = reach * 0.9 * p.r, a = p.a + time * 0.2;
    const [x, y] = project([Math.cos(a) * r, floor + p.y * reach * 1.8, Math.sin(a) * r]);
    ctx.fillStyle = `rgba(${base},${0.5 * (1 - p.y)})`;
    ctx.fillRect(x, y, 2, 2);
  });
}
ctx.fillStyle = '#02050a';
ctx.fillRect(0, 0, W, H);
requestAnimationFrame(frame);
