// extract_world_map.mjs -- Natural Earth 世界地図（TopoJSON）を HTML 埋め込み用 SVG パスへ変換する。
//
// 入力: world-atlas パッケージの land-110m.json / countries-110m.json（Natural Earth 由来・パブリックドメイン）
// 出力: derived/world_land.json（投影パラメータ + 陸地パス + 国境パス）
//
// 投影は HTML の地理座標モードと同じメルカトル:
//   x = x0 + (lon - lon_min) * k
//   y = y_top + (merc_top_deg - mercYdeg(lat)) * k
//   mercYdeg(lat) = (180/π) * ln(tan(π/4 + lat*π/360))
// ノード配置（computeDynamicLayout の geoX/geoY）がこのパラメータを参照するため、
// 地図とノードは必ず一致する。
import { readFileSync, writeFileSync } from "node:fs";
import { feature } from "topojson-client";

const [landPath, countriesPath, outPath] = process.argv.slice(2);
if (!landPath || !countriesPath || !outPath) {
  console.error("usage: extract_world_map.mjs <land-110m.json> <countries-110m.json> <out.json>");
  process.exit(2);
}

// ---- 投影定数（HTML テンプレートの geoX/geoY と一致させること）----
const W = 1280, H = 940;
const PAD = { l: 196, r: 46, t: 28, b: 32 };
const lonMin = -25;
const x0 = PAD.l * 0.36;
const k = (W - PAD.l * 0.44 - 26) / 205; // 既存 geoX 式 ((lon+25)/205)*(W-PAD.l*0.44-26)+x0 と一致させる
const yTop = PAD.t;
const latBottom = -25;
const mercYdeg = (lat) => (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
const mercTopDeg = mercYdeg(latBottom) + (H - PAD.b - PAD.t) / k;

function proj(lon, lat) {
  const la = Math.max(-85, Math.min(85, lat));
  return [x0 + (lon - lonMin) * k, yTop + (mercTopDeg - mercYdeg(la)) * k];
}

// ---- 幾何ユーティリティ ----
function unwrapLons(ring) {
  // 反経線をまたぐ環の経度を連続化（隣接 Δlon < 180）する
  const out = [[ring[0][0], ring[0][1]]];
  for (let i = 1; i < ring.length; i++) {
    let lon = ring[i][0];
    const prev = out[i - 1][0];
    while (lon - prev > 180) lon -= 360;
    while (prev - lon > 180) lon += 360;
    out.push([lon, ring[i][1]]);
  }
  return out;
}

function splitAtJumps(pts) {
  // 投影後に |Δx| が大きい区間で分割（反経線またぎのストリーク防止）
  const pieces = [];
  let cur = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    if (Math.abs(pts[i][0] - pts[i - 1][0]) > 300) {
      pieces.push(cur);
      cur = [pts[i]];
    } else {
      cur.push(pts[i]);
    }
  }
  pieces.push(cur);
  return pieces;
}

function pieceInCanvas(pts) {
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const margin = 30;
  return !(maxX < -margin || minX > W + margin || maxY < -margin || minY > H + margin);
}

function simplify(points, tol) {
  if (points.length < 3) return points;
  const keep = new Array(points.length).fill(false);
  keep[0] = keep[points.length - 1] = true;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop();
    let maxD = 0, idx = -1;
    const [ax, ay] = points[a], [bx, by] = points[b];
    const dx = bx - ax, dy = by - ay;
    const den = dx * dx + dy * dy || 1;
    for (let i = a + 1; i < b; i++) {
      const t = ((points[i][0] - ax) * dx + (points[i][1] - ay) * dy) / den;
      const px = ax + t * dx, py = ay + t * dy;
      const d = (points[i][0] - px) ** 2 + (points[i][1] - py) ** 2;
      if (d > maxD) { maxD = d; idx = i; }
    }
    if (maxD > tol * tol && idx > 0) {
      keep[idx] = true;
      stack.push([a, idx], [idx, b]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

function ringToPath(ring) {
  // 経度ラップ: 全頂点が lon_min より西にある環は +360（ベーリング海側の切れ端を右端へ）
  ring = unwrapLons(ring);
  if (Math.max(...ring.map((p) => p[0])) < lonMin) ring = ring.map(([lo, la]) => [lo + 360, la]);
  const pts = ring.map(([lo, la]) => proj(lo, la));
  const pieces = splitAtJumps(pts.concat([pts[0]])); // 閉環の終点→始点も分割対象
  const rnd = (v) => Math.round(v * 10) / 10;
  const subs = [];
  for (const piece of pieces) {
    if (piece.length < 3 || !pieceInCanvas(piece)) continue;
    const simp = simplify(piece, 0.6);
    if (simp.length < 3) continue;
    subs.push("M" + simp.map(([x, y]) => `${rnd(x)},${rnd(y)}`).join("L") + "Z");
  }
  return subs.length ? subs.join("") : null;
}

function lineToPath(line) {
  line = unwrapLons(line);
  if (Math.max(...line.map((p) => p[0])) < lonMin) line = line.map(([lo, la]) => [lo + 360, la]);
  const pts = line.map(([lo, la]) => proj(lo, la));
  const pieces = splitAtJumps(pts);
  const rnd = (v) => Math.round(v * 10) / 10;
  const subs = [];
  for (const piece of pieces) {
    if (piece.length < 2 || !pieceInCanvas(piece)) continue;
    const simp = simplify(piece, 0.6);
    if (simp.length < 2) continue;
    subs.push("M" + simp.map(([x, y]) => `${rnd(x)},${rnd(y)}`).join("L"));
  }
  return subs.length ? subs.join("") : null;
}

function collectRings(geom, sink) {
  if (geom.type === "Polygon") geom.coordinates.forEach((r) => sink.push(r));
  else if (geom.type === "MultiPolygon") geom.coordinates.forEach((poly) => poly.forEach((r) => sink.push(r)));
  else if (geom.type === "LineString") sink.push(geom.coordinates);
  else if (geom.type === "MultiLineString") geom.coordinates.forEach((l) => sink.push(l));
}

const landTopo = JSON.parse(readFileSync(landPath, "utf-8"));
const landGeo = feature(landTopo, landTopo.objects.land);
const landRings = [];
if (landGeo.type === "FeatureCollection") {
  landGeo.features.forEach((f) => collectRings(f.geometry, landRings));
} else {
  collectRings(landGeo.geometry ?? landGeo, landRings);
}
const landPaths = landRings.map(ringToPath).filter(Boolean);

const countriesTopo = JSON.parse(readFileSync(countriesPath, "utf-8"));
const countriesGeo = feature(countriesTopo, countriesTopo.objects.countries);
const borderRings = [];
countriesGeo.features.forEach((f) => collectRings(f.geometry, borderRings));
const borderPaths = borderRings.map(lineToPath).filter(Boolean);

const out = {
  source: "world-atlas (Natural Earth 1:110m via npm world-atlas)",
  license: "Natural Earth public domain / world-atlas package",
  note: "地理座標モードの背景地図。投影は HTML のノード配置と同一（メルカトル）。src/extract_world_map.mjs で再生成。",
  projection: {
    w: W, h: H, pad: PAD, lon_min: lonMin, x0: x0,
    k: Math.round(k * 1e6) / 1e6, y_top: yTop,
    merc_top_deg: Math.round(mercTopDeg * 1e6) / 1e6,
  },
  land: landPaths,
  borders: borderPaths,
};
writeFileSync(outPath, JSON.stringify(out));
console.log("wrote", outPath);
console.log("  land paths:", landPaths.length, "border paths:", borderPaths.length);
console.log("  projection:", JSON.stringify(out.projection));
const bytes = Buffer.byteLength(JSON.stringify(out));
console.log("  bytes:", bytes);
