// ---------------------------------------------------------------------------
// Mascotas en 3D (panda, león y ratón) con three.js.
//
// Cada mascota es un muñeco articulado: cadera → torso → cuello → cabeza,
// hombros → brazos → manos, piernas → patas y cola. Se anima sola (respira,
// parpadea, sigue el mouse con la cabeza, saluda) y tiene reacciones (salto,
// giro, baile, risa, sorpresa, mareo, corazones, confeti, celebrar). La ropa
// (app/utils/ropa_mascota.py) se arma en 3D y va pegada a la articulación
// que le toca (cabeza, cara, cuello o mano), ajustada a cada mascota.
//
// API (window.Mascota3D):
//   crear(contenedor, {tipo, ropa, interactiva}) -> vista
//   vista.reaccionar(nombre?)   vista.ponerRopa(ropa)   vista.destruir()
// ---------------------------------------------------------------------------
import * as THREE from "/static/vendor/three.module.min.js";

const TAU = Math.PI * 2;

// ---------- Materiales ----------
function pelo(color, brillo) {
  return new THREE.MeshPhysicalMaterial({
    color, roughness: 0.78, metalness: 0,
    sheen: 1, sheenRoughness: 0.5, sheenColor: new THREE.Color(brillo || color).lerp(new THREE.Color("#ffffff"), 0.35),
  });
}
function liso(color, rugosidad = 0.45, extra = {}) {
  return new THREE.MeshPhysicalMaterial(Object.assign({ color, roughness: rugosidad, metalness: 0, clearcoat: 0.25, clearcoatRoughness: 0.4 }, extra));
}
function metal(color, rugosidad = 0.25) {
  // Sin mapa de entorno, el metal puro sale negro: brillo de metal "pintado".
  return new THREE.MeshPhysicalMaterial({ color, metalness: 0.35, roughness: rugosidad, clearcoat: 1, clearcoatRoughness: 0.1,
    emissive: new THREE.Color(color).multiplyScalar(0.12) });
}
function vidrio(color, opacidad = 0.85) {
  return new THREE.MeshPhysicalMaterial({ color, roughness: 0.05, metalness: 0.2, clearcoat: 1, transparent: true, opacity: opacidad });
}
function tela(color) { return new THREE.MeshPhysicalMaterial({ color, roughness: 0.9, sheen: 0.8, sheenRoughness: 0.8, sheenColor: new THREE.Color(color).lerp(new THREE.Color("#fff"), 0.4) }); }

function texturaRayas(colores, ancho = 64, vertical = false) {
  const c = document.createElement("canvas");
  c.width = vertical ? 8 : ancho * colores.length; c.height = vertical ? ancho * colores.length : 8;
  const g = c.getContext("2d");
  colores.forEach((col, i) => { g.fillStyle = col; vertical ? g.fillRect(0, i * ancho, 8, ancho) : g.fillRect(i * ancho, 0, ancho, 8); });
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

function texturaIris(claro, oscuro) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 128; const g = c.getContext("2d");
  // Esfera: el frente (u = 0.5) queda al centro del lienzo.
  g.fillStyle = oscuro; g.fillRect(0, 0, 256, 128);
  const r = g.createRadialGradient(128, 64, 4, 128, 64, 64);
  r.addColorStop(0, oscuro); r.addColorStop(0.35, claro); r.addColorStop(0.75, claro); r.addColorStop(1, oscuro);
  g.fillStyle = r; g.fillRect(64, 0, 128, 128);
  const brillo = g.createLinearGradient(0, 64, 0, 128);
  brillo.addColorStop(0, "rgba(255,255,255,0)"); brillo.addColorStop(1, "rgba(255,255,255,.22)");
  g.fillStyle = brillo; g.fillRect(64, 64, 128, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// ---------- Geometrías ----------
const G = {
  esfera: new THREE.SphereGeometry(1, 48, 32),
  esferaB: new THREE.SphereGeometry(1, 24, 16),
  capsula: new THREE.CapsuleGeometry(1, 1, 12, 24),
};
function malla(geo, mat, pos, escala, rot) {
  const m = new THREE.Mesh(geo, mat);
  if (pos) m.position.set(pos[0], pos[1], pos[2]);
  if (escala) (typeof escala === "number") ? m.scale.setScalar(escala) : m.scale.set(escala[0], escala[1], escala[2]);
  if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
  m.castShadow = false;
  return m;
}
function grupo(pos, hijos) {
  const g = new THREE.Group();
  if (pos) g.position.set(pos[0], pos[1], pos[2]);
  (hijos || []).forEach((h) => g.add(h));
  return g;
}
function formaCorazon(t = 0.5) {
  const s = new THREE.Shape();
  s.moveTo(0, -0.9 * t);
  s.bezierCurveTo(-1.2 * t, -0.1 * t, -0.9 * t, 0.9 * t, 0, 0.45 * t);
  s.bezierCurveTo(0.9 * t, 0.9 * t, 1.2 * t, -0.1 * t, 0, -0.9 * t);
  return s;
}
function corazon(color, t = 0.5, prof = 0.12) {
  const geo = new THREE.ExtrudeGeometry(formaCorazon(t), { depth: prof, bevelEnabled: true, bevelSize: prof * 0.55, bevelThickness: prof * 0.6, bevelSegments: 12, curveSegments: 48 });
  geo.computeVertexNormals();
  geo.center();
  return new THREE.Mesh(geo, liso(color, 0.3, { clearcoat: 0.8 }));
}

// ---------- Personajes ----------
const PALETAS = {
  panda: { pelo: "#f6f3ec", oscuro: "#2a2a30", hocico: "#ffffff", nariz: "#1b1b1f", rosa: "#ffb3c4", orejaIn: "#3a3a42" },
  leon: { pelo: "#f0b03c", oscuro: "#b4561d", hocico: "#ffe6b8", nariz: "#4a2a1a", rosa: "#ffb0b0", orejaIn: "#ffcf9a", melena: "#a8461a" },
  raton: { pelo: "#c4cad6", oscuro: "#9aa2b2", hocico: "#eef1f6", nariz: "#ff8fa8", rosa: "#ffb6c8", orejaIn: "#ffb6c8" },
};

// Dónde va la ropa en cada mascota (sobre su articulación) y a qué escala.
const AJUSTE_ROPA = {
  panda: { cabeza: [0, 0, 0, 1.0], ojos: [0, 0, 0, 1.0], cuello: [0, 0, 0, 1.0], mano: [0, 0, 0, 1.0] },
  leon: { cabeza: [0, 0.06, 0, 1.08], ojos: [0, 0, 0.02, 1.0], cuello: [0, -0.1, 0.02, 1.0], mano: [0, 0, 0, 1.0] },
  raton: { cabeza: [0, 0, 0, 1.0], ojos: [0, 0, 0, 1.0], cuello: [0, 0, 0.03, 1.0], mano: [0, 0, 0, 1.0] },
};

function crearPersonaje(tipo) {
  const P = PALETAS[tipo] || PALETAS.panda;
  const mPelo = pelo(P.pelo);
  const mOscuro = pelo(P.oscuro);
  const mHocico = pelo(P.hocico);
  const mNariz = liso(P.nariz, 0.25, { clearcoat: 1 });
  const mRosa = liso(P.rosa, 0.6);
  const mBlanco = liso("#ffffff", 0.15, { clearcoat: 1 });
  const mPupila = liso("#0e0e12", 0.1, { clearcoat: 1, clearcoatRoughness: 0.05 });
  const mBrillo = new THREE.MeshBasicMaterial({ color: "#ffffff" });
  const mExtremidad = tipo === "panda" ? mOscuro : mPelo;
  const mPata = tipo === "raton" ? liso(P.rosa, 0.6) : pelo(tipo === "panda" ? "#3a3a42" : P.hocico);

  const raiz = new THREE.Group();        // se mueve entero (saltos, giros)
  const cadera = grupo([0, 0, 0]);       // squash & stretch
  raiz.add(cadera);

  // Torso
  const torso = grupo([0, 0.55, 0]);
  torso.add(malla(G.esfera, mPelo, [0, 0, 0], [0.8, 0.72, 0.7]));
  if (tipo === "panda") torso.add(malla(G.esfera, mOscuro, [0, 0.38, -0.02], [0.74, 0.3, 0.64])); // banda negra de hombros
  torso.add(malla(G.esfera, tipo === "panda" ? mPelo : mHocico, [0, -0.02, 0.36], [0.52, 0.55, 0.36])); // panza
  cadera.add(torso);

  // Piernas (sentado, patas hacia adelante)
  const piernas = [];
  [-1, 1].forEach((lado) => {
    const p = grupo([0.4 * lado, 0.2, 0.18]);
    p.add(malla(G.esfera, mExtremidad, [0, 0, 0.1], [0.3, 0.26, 0.38]));
    p.add(malla(G.esfera, mPata, [0, -0.02, 0.42], [0.18, 0.15, 0.06], [0.2, 0, 0]));
    [-0.1, 0, 0.1].forEach((dx) => p.add(malla(G.esferaB, mPata, [dx, 0.1, 0.42], [0.045, 0.045, 0.03])));
    cadera.add(p); piernas.push(p);
  });

  // Brazos: hombro (pivote) → brazo → mano
  const brazos = [];
  [-1, 1].forEach((lado) => {
    const hombro = grupo([0.62 * lado, 0.86, 0.05]);
    const brazo = malla(G.capsula, mExtremidad, [0, -0.28, 0], [0.17, 0.2, 0.17]);
    hombro.add(brazo);
    const mano = grupo([0, -0.56, 0.02]);
    mano.add(malla(G.esfera, mExtremidad, [0, 0, 0], [0.2, 0.19, 0.2]));
    mano.add(malla(G.esfera, mPata, [0, -0.02, 0.15], [0.11, 0.1, 0.06]));
    hombro.add(mano);
    hombro.rotation.z = 0.45 * lado;
    hombro.userData.lado = lado; hombro.userData.mano = mano;
    torso.parent.add(hombro); // colgado de la cadera para que no herede el respirar
    brazos.push(hombro);
  });

  // Cuello y cabeza
  const cuello = grupo([0, 1.02, 0]);
  cadera.add(cuello);
  const cabeza = grupo([0, 0.58, 0]);
  cuello.add(cabeza);
  cabeza.add(malla(G.esfera, mPelo, [0, 0, 0], [1, 0.93, 0.92]));

  // Orejas
  const orejas = [];
  [-1, 1].forEach((lado) => {
    let o;
    if (tipo === "raton") {
      o = grupo([0.72 * lado, 0.62, -0.12]);
      o.add(malla(G.esfera, mOscuro, [0, 0, 0], [0.5, 0.5, 0.1]));
      o.add(malla(G.esfera, mRosa, [0, 0, 0.05], [0.36, 0.36, 0.07]));
      o.rotation.set(0, 0.35 * lado, -0.35 * lado);
    } else {
      o = grupo([0.62 * lado, 0.68, -0.05]);
      o.add(malla(G.esfera, tipo === "panda" ? mOscuro : mPelo, [0, 0, 0], [0.3, 0.3, 0.16]));
      o.add(malla(G.esfera, tipo === "panda" ? pelo(P.orejaIn) : mRosa, [0, 0, 0.08], [0.17, 0.17, 0.08]));
      o.rotation.z = -0.4 * lado;
    }
    cabeza.add(o); orejas.push(o);
  });

  // Melena del león
  if (tipo === "leon") {
    const melena = grupo([0, -0.02, -0.18]);
    const mMel = pelo(P.melena, "#e07a2a");
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * TAU;
      const r = 1.02 + (i % 2) * 0.1;
      const m = malla(G.esfera, mMel, [Math.cos(a) * r, Math.sin(a) * r * 0.95, -0.05 - (i % 2) * 0.08], [0.36, 0.42, 0.3]);
      m.rotation.z = a - Math.PI / 2;
      melena.add(m);
    }
    melena.add(malla(G.esfera, mMel, [0, 0, -0.2], [1.25, 1.2, 0.6]));
    cabeza.add(melena);
  }

  // Manchas del panda
  const cara = grupo([0, 0, 0]); cara.scale.set(1, 0.93, 0.92); cabeza.add(cara);
  if (tipo === "panda") {
    [-1, 1].forEach((lado) => cabeza.add(malla(G.esfera, mOscuro, [0.34 * lado, 0.04, 0.74], [0.25, 0.32, 0.16], [0, 0, 0.45 * lado])));
  }

  // Hocico, nariz, boca
  cabeza.add(malla(G.esfera, mHocico, [0, -0.3, 0.78], tipo === "raton" ? [0.3, 0.22, 0.2] : [0.36, 0.26, 0.2]));
  cabeza.add(malla(G.esfera, mNariz, [0, -0.2, 0.97], tipo === "leon" ? [0.12, 0.08, 0.07] : [0.1, 0.07, 0.07]));
  const boca = grupo([0, -0.36, 0.95]);
  const sonrisa = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.016, 8, 24, Math.PI), liso("#2b211d", 0.5));
  sonrisa.rotation.z = Math.PI;
  boca.add(sonrisa);
  const bocaAbierta = malla(G.esfera, liso("#5a1e28", 0.5), [0, -0.03, 0], [0.11, 0.0001, 0.04]);
  bocaAbierta.add(malla(G.esferaB, liso("#ff7b93", 0.6), [0, -0.35, 0.2], [0.6, 0.45, 0.5]));
  boca.add(bocaAbierta);
  cabeza.add(boca);

  // Bigotes del ratón
  if (tipo === "raton") {
    const mB = liso("#555a66", 0.6);
    [-1, 1].forEach((lado) => [-0.08, 0, 0.08].forEach((dy, i) => {
      const b = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.5, 6), mB);
      b.position.set(0.32 * lado, -0.26 + dy, 0.9); b.rotation.z = Math.PI / 2 + (i - 1) * 0.18 * lado;
      cabeza.add(b);
    }));
  }

  // Cachetes
  [-1, 1].forEach((lado) => cabeza.add(malla(G.esferaB, new THREE.MeshPhysicalMaterial({ color: P.rosa, roughness: 0.8, transparent: true, opacity: 0.55 }),
    [0.52 * lado, -0.24, 0.7], [0.15, 0.09, 0.05], [0, 0.5 * lado, 0])));

  // Ojos negros brillantes (como al principio). Con las expresiones:
  // feliz = se cierran en arco, amor = pupilas de corazón, sorpresa = se
  // agrandan, mareo = las pupilas dan vueltas; y parpadean.
  const ojos = [], parpados = [];
  [-1, 1].forEach((lado) => {
    const ojo = grupo([0.33 * lado, 0.06, 0.8]);
    ojo.add(malla(G.esfera, mBlanco, [0, 0, 0], [0.17, 0.2, 0.12]));
    const pupila = grupo([0, -0.01, 0.09]);
    pupila.add(malla(G.esfera, mPupila, [0, 0, 0], [0.11, 0.13, 0.06]));
    pupila.add(malla(G.esferaB, mBrillo, [-0.035, 0.05, 0.05], 0.032));
    pupila.add(malla(G.esferaB, mBrillo, [0.03, -0.04, 0.05], 0.014));
    ojo.add(pupila);
    const corazonOjo = corazon("#e11d48", 0.12, 0.05); corazonOjo.position.set(0, 0, 0.11); corazonOjo.visible = false;
    ojo.add(corazonOjo);
    const parpado = malla(new THREE.SphereGeometry(1, 32, 16, 0, TAU, 0, Math.PI / 2), tipo === "panda" ? mOscuro : mPelo, [0, 0.0, 0.005], [0.185, 0.215, 0.135]);
    parpado.rotation.x = -Math.PI / 2;
    parpado.scale.y = 0.0001;
    ojo.add(parpado);
    // Ojo cerrado feliz (arco), dibujado aparte y escondido hasta que se ría
    const lienzo = document.createElement("canvas"); lienzo.width = lienzo.height = 256;
    const tex = new THREE.CanvasTexture(lienzo); tex.colorSpace = THREE.SRGBColorSpace;
    const feliz = { lado, lienzo, tex, clave: "", colores: { linea: "#1b1b22", cerrado: tipo === "panda" ? "#f4f1ea" : "#2b211d" } };
    feliz.malla = calcomania(tex, 1.075, 0.33 * lado, 0.07, 0.5, 0.5, 6);
    feliz.malla.visible = false;
    dibujarOjo(feliz, { estado: "feliz", cierre: 0, mx: 0, my: 0 });
    cara.add(feliz.malla);
    ojo.userData = { pupila, corazon: corazonOjo, feliz: feliz.malla };
    cabeza.add(ojo); ojos.push(ojo); parpados.push(parpado);
  });

  // Cola
  let cola = null;
  if (tipo === "raton" || tipo === "leon") {
    cola = grupo([0, 0.25, -0.6]);
    const puntos = tipo === "raton"
      ? [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0.35, -0.1, -0.35), new THREE.Vector3(0.75, 0.25, -0.4), new THREE.Vector3(0.9, 0.7, -0.2)]
      : [new THREE.Vector3(0, 0, 0), new THREE.Vector3(0.4, -0.1, -0.3), new THREE.Vector3(0.7, 0.2, -0.4), new THREE.Vector3(0.8, 0.55, -0.3)];
    const tubo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(puntos), 32, tipo === "raton" ? 0.045 : 0.06, 10);
    cola.add(new THREE.Mesh(tubo, tipo === "raton" ? liso(P.rosa, 0.6) : mPelo));
    if (tipo === "leon") cola.add(malla(G.esfera, pelo(P.melena), puntos[3].toArray(), [0.16, 0.2, 0.16]));
    cadera.add(cola);
  }

  // Anclas de la ropa
  const aj = AJUSTE_ROPA[tipo] || AJUSTE_ROPA.panda;
  const anclas = {
    cabeza: grupo([aj.cabeza[0], aj.cabeza[1], aj.cabeza[2]]),
    ojos: grupo([aj.ojos[0], aj.ojos[1] + 0.06, 0.97 + aj.ojos[2]]),  // delante de los ojos: los lentes nunca quedan detrás
    cuello: grupo([aj.cuello[0], -0.17 + aj.cuello[1], aj.cuello[2]]),
    mano: grupo([0.16, -0.05, 0.22]),  // un poco afuera y adelante: lo que sostiene no se mete en el cuerpo
  };
  ["cabeza", "ojos", "cuello", "mano"].forEach((k) => anclas[k].scale.setScalar(aj[k][3]));
  cabeza.add(anclas.cabeza); cabeza.add(anclas.ojos); cuello.add(anclas.cuello);
  brazos[1].userData.mano.add(anclas.mano);

  const flotante = grupo([0, 0, 0]); cadera.add(flotante);
  return { raiz, cadera, torso, cuello, cabeza, brazos, piernas, orejas, ojos, parpados, boca, bocaAbierta, sonrisa, cola, anclas, tipo, flotante };
}

// Pedazo curvo de la misma esfera de la cara, centrado en (x, y) de la
// cara, con una textura encima (ojos, manchas). ancho/alto en unidades.
function calcomania(tex, radio, x, y, ancho, alto, orden) {
  const theta = Math.acos(THREE.MathUtils.clamp(y, -0.99, 0.99));
  const phi = Math.acos(THREE.MathUtils.clamp(-x / Math.sin(theta), -1, 1));
  const dPhi = ancho / Math.sin(theta), dTheta = alto;
  const geo = new THREE.SphereGeometry(radio, 24, 24, phi - dPhi / 2, dPhi, theta - dTheta / 2, dTheta);
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, toneMapped: false,
    polygonOffset: true, polygonOffsetFactor: -orden, polygonOffsetUnits: -orden });
  const m = new THREE.Mesh(geo, mat); m.renderOrder = orden;
  return m;
}

function texturaMancha(lado) {
  const c = document.createElement("canvas"); c.width = c.height = 256; const g = c.getContext("2d");
  g.translate(128, 132); g.rotate(-0.42 * lado);
  const r = g.createRadialGradient(0, 0, 60, 0, 0, 118);
  r.addColorStop(0, "rgba(38,38,44,1)"); r.addColorStop(0.86, "rgba(38,38,44,1)"); r.addColorStop(1, "rgba(38,38,44,0)");
  g.fillStyle = r; g.beginPath(); g.ellipse(0, 0, 100, 122, 0, 0, TAU); g.fill();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

// Dibuja un ojo estilo anime: borde oscuro grueso arriba, blanco con
// sombra rosada, iris grande con media luna clara abajo, pupila grande y
// destellos. Cambia de forma según la expresión.
function dibujarOjo(ojo, e) {
  const clave = [e.estado, Math.round(e.cierre * 10), Math.round(e.mx * 8), Math.round(e.my * 8)].join("|");
  if (clave === ojo.clave) return;
  ojo.clave = clave;
  const g = ojo.lienzo.getContext("2d"), C = ojo.colores, L = ojo.lado;
  g.clearRect(0, 0, 256, 256);
  g.save();
  g.translate(128, 132);
  if (L < 0) g.scale(-1, 1); // el lado de afuera queda hacia afuera
  const RX = 92, RY = 104;

  if (e.estado === "feliz" || e.cierre > 0.92) {
    // Ojo cerrado: feliz = arco hacia arriba; parpadeo = línea curva hacia abajo
    g.lineCap = "round"; g.strokeStyle = C.cerrado || C.linea; g.lineWidth = 16;
    g.beginPath();
    if (e.estado === "feliz") { g.moveTo(-70, 30); g.quadraticCurveTo(0, -62, 70, 30); }
    else { g.moveTo(-74, 6); g.quadraticCurveTo(0, 46, 74, 6); }
    g.stroke();
    g.lineWidth = 7; g.beginPath(); g.moveTo(68, e.estado === "feliz" ? 24 : 8); g.lineTo(94, e.estado === "feliz" ? 6 : -10); g.stroke();
    g.restore(); ojo.tex.needsUpdate = true; return;
  }
  const esc = e.estado === "sorpresa" ? 1.07 : 1;
  g.scale(esc, esc);

  // Contorno y blanco con sombra rosada
  g.fillStyle = C.linea; g.beginPath(); g.ellipse(0, 0, RX + 7, RY + 7, 0, 0, TAU); g.fill();
  const bl = g.createRadialGradient(0, 18, RX * 0.55, 0, 0, RX * 1.05);
  bl.addColorStop(0, "#ffffff"); bl.addColorStop(0.78, "#fff6f4"); bl.addColorStop(1, "#efc9cb");
  g.fillStyle = bl; g.beginPath(); g.ellipse(0, 0, RX, RY, 0, 0, TAU); g.fill();

  g.save(); g.beginPath(); g.ellipse(0, 0, RX, RY, 0, 0, TAU); g.clip();
  if (e.estado === "mareo") {
    g.strokeStyle = C.linea; g.lineWidth = 9; g.lineCap = "round"; g.beginPath();
    for (let t = 0; t < 5.2 * Math.PI; t += 0.1) { const r = 6 + t * 4.4; const x = Math.cos(t) * r, y = Math.sin(t) * r * 1.05 + 10; t === 0 ? g.moveTo(x, y) : g.lineTo(x, y); }
    g.stroke();
  } else {
    const ix = e.mx * 16, iy = 14 + e.my * 12;
    const rIris = e.estado === "sorpresa" ? 56 : 72;
    if (e.estado === "amor") {
      g.fillStyle = "#e11d48"; g.save(); g.translate(ix, iy - 4); g.scale(4.6, 4.6);
      g.beginPath(); g.moveTo(0, 12); g.bezierCurveTo(-16, 0, -12, -14, 0, -6); g.bezierCurveTo(12, -14, 16, 0, 0, 12); g.fill(); g.restore();
      g.fillStyle = "#fff"; g.beginPath(); g.ellipse(ix - 26, iy - 30, 16, 11, -0.4, 0, TAU); g.fill();
    } else {
      // Iris con degradado y media luna clara abajo
      const ir = g.createRadialGradient(ix, iy - 20, 10, ix, iy, rIris);
      ir.addColorStop(0, C.iris); ir.addColorStop(1, C.linea);
      g.fillStyle = ir; g.beginPath(); g.arc(ix, iy, rIris, 0, TAU); g.fill();
      g.save(); g.beginPath(); g.arc(ix, iy, rIris - 4, 0, TAU); g.clip();
      const cl = g.createLinearGradient(0, iy, 0, iy + rIris);
      cl.addColorStop(0, "rgba(255,255,255,0)"); cl.addColorStop(0.35, C.claro); cl.addColorStop(1, C.claro);
      g.fillStyle = cl; g.globalAlpha = 0.95; g.beginPath(); g.ellipse(ix, iy + rIris * 0.62, rIris * 0.92, rIris * 0.62, 0, 0, TAU); g.fill();
      g.globalAlpha = 0.35; g.strokeStyle = "#ffffff"; g.lineWidth = 2;
      for (let i = -3; i <= 3; i++) { g.beginPath(); g.moveTo(ix + i * 12, iy + rIris * 0.55); g.lineTo(ix + i * 14, iy + rIris * 0.85); g.stroke(); }
      g.restore(); g.globalAlpha = 1;
      // Pupila con aro
      const rp = e.estado === "sorpresa" ? 20 : 40;
      g.fillStyle = "#0e0818"; g.beginPath(); g.arc(ix, iy - 2, rp, 0, TAU); g.fill();
      g.strokeStyle = "rgba(255,255,255,.18)"; g.lineWidth = 3; g.beginPath(); g.arc(ix, iy - 2, rp + 4, 0, TAU); g.stroke();
      g.strokeStyle = C.linea; g.lineWidth = 4; g.beginPath(); g.arc(ix, iy, rIris, 0, TAU); g.stroke();
      // Destellos
      g.fillStyle = "#ffffff";
      g.beginPath(); g.ellipse(ix - 22, iy - 34, 24, 16, -0.25, 0, TAU); g.fill();
      [[-46, -2, 7], [32, -34, 5], [-30, 10, 3.5], [44, 2, 3]].forEach(([dx, dy, r]) => { g.beginPath(); g.arc(ix + dx, iy + dy, r, 0, TAU); g.fill(); });
      g.fillStyle = "#b9a6e0";
      [[12, 18, 7], [-8, 30, 5], [18, 30, 3]].forEach(([dx, dy, r]) => { g.beginPath(); g.arc(ix + dx, iy + dy, r, 0, TAU); g.fill(); });
    }
  }
  // Párpado que baja al parpadear
  if (e.cierre > 0.02) {
    const y = -RY + e.cierre * RY * 2.1;
    g.fillStyle = C.parpado; g.beginPath(); g.moveTo(-RX - 10, -RY - 10); g.lineTo(RX + 10, -RY - 10); g.lineTo(RX + 10, y - 10);
    g.quadraticCurveTo(0, y + 26, -RX - 10, y - 10); g.closePath(); g.fill();
    g.strokeStyle = C.linea; g.lineWidth = 6; g.beginPath(); g.moveTo(-RX, y - 6); g.quadraticCurveTo(0, y + 24, RX, y - 6); g.stroke();
  }
  g.restore(); // fin del recorte

  // Borde grueso de arriba (párpado) con su banda rosada
  g.lineCap = "round";
  g.strokeStyle = "#e9c3c6"; g.lineWidth = 10; g.beginPath(); g.ellipse(0, 4, RX - 8, RY - 6, 0, Math.PI * 1.08, Math.PI * 1.92); g.stroke();
  g.strokeStyle = C.linea; g.lineWidth = 20; g.beginPath(); g.ellipse(0, 0, RX + 2, RY + 2, 0, Math.PI * 1.02, Math.PI * 1.98); g.stroke();
  // Pestañas en la esquina de afuera (arriba y abajo)
  g.lineWidth = 6;
  [[RX * 0.86, -RY * 0.5, 30, -22], [RX * 0.97, -RY * 0.18, 30, -6]].forEach(([x, y, dx, dy]) => { g.beginPath(); g.moveTo(x, y); g.lineTo(x + dx, y + dy); g.stroke(); });
  g.lineWidth = 5;
  [[RX * 0.62, RY * 0.78, 14, 22], [RX * 0.8, RY * 0.6, 22, 14]].forEach(([x, y, dx, dy]) => { g.beginPath(); g.moveTo(x, y); g.lineTo(x + dx, y + dy); g.stroke(); });
  g.restore();
  ojo.tex.needsUpdate = true;
}

// ---------- Ropa 3D (las claves son las de ropa_mascota.py) ----------
const ROPA = {
  // Cabeza (el ancla es el centro de la cabeza; radio de la cabeza ≈ 1)
  gorra() {
    const g = new THREE.Group(), m = tela("#2563eb");
    g.add(gorroCabeza(m, 1.0, 1.05));
    const borde = bordeGorro(liso("#1d4ed8", 0.5), 1.0, 1.05, 0.05); g.add(borde);
    const r = 1.05 * Math.sin(1.0);
    const visera = malla(new THREE.CylinderGeometry(0.6, 0.6, 0.05, 40, 1, false, -Math.PI / 2, Math.PI), liso("#1d4ed8", 0.5),
      [0, 0.93 * 1.05 * Math.cos(1.0) - 0.02, 0.92 * r - 0.1], [1, 1, 0.9], [0.18, 0, 0]);
    g.add(visera);
    g.add(malla(G.esferaB, liso("#1e40af", 0.5), [0, 0.93 * 1.05 + 0.02, 0], 0.08));
    g.userData.tapaOrejas = true;
    return g;
  },
  lana() {
    const g = new THREE.Group();
    g.add(gorroCabeza(tela("#0ea5e9"), 1.12, 1.06));
    g.add(bordeGorro(tela("#0369a1"), 1.12, 1.06, 0.13));
    g.add(malla(G.esfera, tela("#e0f2fe"), [0, 0.93 * 1.06 + 0.14, 0], 0.22));
    g.userData.tapaOrejas = true;
    return g;
  },
  casco() {
    // Casco de obra: copa alta con su nervio al centro, visera al frente,
    // aro de ajuste y calcomanía con una llave.
    const g = new THREE.Group(), amarillo = liso("#facc15", 0.28, { clearcoat: 1, clearcoatRoughness: 0.15 });
    const copa = gorroCabeza(amarillo, 1.12, 1.1); copa.scale.y *= 1.12; g.add(copa);
    // Nervio central de adelante hacia atrás, siguiendo la copa (sin salirse del borde)
    const a0 = Math.PI / 2 - 1.12;
    const nervio = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.06, 14, 64, Math.PI - 2 * a0), amarillo);
    nervio.rotation.z = a0;
    const ejeNervio = new THREE.Group(); ejeNervio.add(nervio); ejeNervio.rotation.y = Math.PI / 2;
    ejeNervio.scale.set(1.11 * 0.92, 0.93 * 1.1 * 1.12 * 1.01, 1.11);
    g.add(ejeNervio);
    const yBorde = 0.93 * 1.1 * Math.cos(1.12);
    const aro = new THREE.Mesh(new THREE.TorusGeometry(Math.sin(1.12) * 1.1, 0.06, 14, 72), liso("#eab308", 0.3, { clearcoat: 0.8 }));
    aro.rotation.x = Math.PI / 2; aro.position.y = yBorde; aro.scale.set(1, 0.92, 1); g.add(aro);
    // visera: media luna al frente, inclinada hacia abajo
    const s2 = new THREE.Shape(); s2.absellipse(0, 0, 0.88, 0.5, 0, Math.PI, false);
    const visera = new THREE.Mesh(new THREE.ExtrudeGeometry(s2, { depth: 0.04, bevelEnabled: true, bevelSize: 0.02, bevelThickness: 0.02, bevelSegments: 3, curveSegments: 32 }), amarillo);
    visera.rotation.x = Math.PI / 2 + 0.2; visera.position.set(0, yBorde + 0.03, 0.66); g.add(visera);
    g.userData.tapaOrejas = true;
    return g;
  },
  vaquero() {
    // Ala de una pieza que se levanta a los lados + copa suave con su cinta.
    const g = new THREE.Group(), cafe = tela("#a16207"), copaM = tela("#ca8a04");
    const ala = new THREE.LatheGeometry([[0.7, -0.025], [1.42, -0.025], [1.44, 0], [1.42, 0.025], [0.7, 0.025]].map((q) => new THREE.Vector2(q[0], q[1])), 128);
    const pa = ala.attributes.position;
    for (let i = 0; i < pa.count; i++) {
      const x = pa.getX(i), z = pa.getZ(i), r = Math.hypot(x, z);
      const lados = Math.max(0, Math.abs(x) - 0.75) / 0.67;          // 0 cerca de la copa, 1 en la orilla
      pa.setY(i, pa.getY(i) + 0.32 * lados * lados - 0.03 * Math.max(0, r - 0.7));
    }
    ala.computeVertexNormals();
    const alaM = new THREE.Mesh(ala, cafe); alaM.material.side = THREE.DoubleSide; alaM.scale.z = 0.86; alaM.position.y = 0.7; g.add(alaM);
    const perfil = [[0, 0.62], [0.2, 0.6], [0.42, 0.66], [0.56, 0.6], [0.66, 0.3], [0.68, 0.02], [0.7, -0.02]]
      .reverse().map((p) => new THREE.Vector2(p[0], p[1]));
    const copa = new THREE.Mesh(new THREE.LatheGeometry(new THREE.SplineCurve(perfil).getPoints(40), 96), copaM);
    copa.position.y = 0.72; copa.scale.z = 0.86; g.add(copa);
    const cinta = new THREE.Mesh(new THREE.CylinderGeometry(0.685, 0.695, 0.13, 96, 1, true), tela("#78350f"));
    cinta.position.y = 0.8; cinta.scale.z = 0.86; g.add(cinta);
    g.rotation.z = -0.06;
    return g;
  },
  corona() {
    const g = new THREE.Group(), oro = metal("#f5c542", 0.2);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.66, 0.6, 0.3, 48, 1, true), oro);
    base.material.side = THREE.DoubleSide; base.position.y = 0.8; g.add(base);
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * TAU;
      const pico = malla(new THREE.ConeGeometry(0.11, 0.32, 16), oro, [Math.sin(a) * 0.64, 1.13, Math.cos(a) * 0.64]);
      g.add(pico);
      g.add(malla(G.esferaB, oro, [Math.sin(a) * 0.64, 1.31, Math.cos(a) * 0.64], 0.05));
    }
    [["#dc2626", 0], ["#2563eb", 1.2], ["#16a34a", -1.2]].forEach(([c, a]) => g.add(malla(G.esferaB, liso(c, 0.1, { clearcoat: 1 }), [Math.sin(a) * 0.67, 0.84, Math.cos(a) * 0.67], 0.075)));
    g.rotation.z = 0.08;
    return g;
  },
  mono() {
    // Lazo de dos pétalos, nudo y colitas, apoyado sobre la cabeza.
    const g = new THREE.Group(), m = tela("#ec4899"), m2 = tela("#db2777");
    const lazo = grupo([0.57, 0.8, 0.26]);
    [-1, 1].forEach((l) => {
      const petalo = malla(G.esfera, m, [0.17 * l, 0.02, 0], [0.19, 0.13, 0.09], [0, 0, 0.35 * l]);
      lazo.add(petalo);
      lazo.add(malla(G.esferaB, m2, [0.17 * l, 0.02, 0.05], [0.09, 0.05, 0.04], [0, 0, 0.35 * l]));
      lazo.add(malla(G.capsula, m, [0.06 * l, -0.14, 0], [0.035, 0.07, 0.03], [0, 0, 0.35 * l]));
    });
    lazo.add(malla(G.esfera, m2, [0, 0, 0.02], [0.08, 0.08, 0.07]));
    lazo.lookAt(new THREE.Vector3(0.57, 0.8, 0.26).multiplyScalar(3)); // de frente hacia afuera de la cabeza
    lazo.rotateZ(0.3);
    g.add(lazo);
    return g;
  },
  santa() {
    // UNA sola pieza de tela: sale del borde, cubre la cabeza siguiendo su
    // forma y sigue hasta la punta caída. Sin uniones ni piezas encimadas.
    const g = new THREE.Group(), rojo = tela("#dc2626"), blanco = tela("#ffffff");
    const curva = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0, 0.36, 0), new THREE.Vector3(0, 0.72, 0), new THREE.Vector3(0.04, 1.06, -0.02),
      new THREE.Vector3(0.28, 1.4, -0.06), new THREE.Vector3(0.6, 1.5, -0.07), new THREE.Vector3(0.88, 1.28, -0.05),
    ], false, "centripetal");
    const radio = (k) => {
      const p = curva.getPointAt(k);
      const cabeza = p.y < 0.98 ? Math.sqrt(Math.max(0, 1 - Math.pow(p.y / 0.93, 2))) + 0.07 : 0;
      return Math.max(cabeza, 0.62 * Math.pow(1 - k, 1.2) + 0.035);
    };
    const gorro = new THREE.Mesh(tuboAfinado(curva, radio, 72, 48), rojo);
    gorro.scale.z = 0.94; g.add(gorro);
    const aro = new THREE.Mesh(new THREE.TorusGeometry(0.98, 0.15, 18, 72), blanco);
    aro.rotation.x = Math.PI / 2; aro.position.y = 0.38; aro.scale.set(1, 1, 0.94); g.add(aro);
    const fin = curva.getPointAt(1);
    g.add(malla(G.esfera, blanco, [fin.x + 0.04, fin.y - 0.06, fin.z * 0.94], 0.15));
    g.userData.tapaOrejas = true;
    return g;
  },
  bruja() {
    const g = new THREE.Group(), m = tela("#3b0764");
    const ala = new THREE.Mesh(new THREE.LatheGeometry([[0.76, -0.025], [1.5, -0.025], [1.52, 0], [1.5, 0.025], [0.76, 0.025]].map((q) => new THREE.Vector2(q[0], q[1])), 96), tela("#24093f"));
    ala.material.side = THREE.DoubleSide;
    ala.position.y = 0.66; ala.scale.z = 0.88; g.add(ala);
    const cono = new THREE.Mesh(new THREE.ConeGeometry(0.72, 1.6, 64, 8, true), m); cono.material.side = THREE.DoubleSide;
    cono.position.set(0, 1.46, 0); g.add(cono);
    // La cinta y la hebilla van pegadas al cono (misma inclinación que él).
    const r = (y) => 0.72 * (0.8 - y) / 1.6 + 0.012;            // radio del cono a la altura y (local)
    const cinta = new THREE.Mesh(new THREE.CylinderGeometry(r(-0.56), r(-0.74), 0.18, 64, 1, true), tela("#f97316"));
    cinta.position.y = -0.65; cono.add(cinta);
    const hebilla = malla(new THREE.BoxGeometry(0.18, 0.14, 0.03), metal("#facc15"), [0, -0.65, r(-0.65) + 0.01]);
    hebilla.rotation.x = -Math.atan(0.72 / 1.6); cono.add(hebilla);
    const punta = cono; punta.rotation.z = 0.1;
    return g;
  },
  diadema_corazones() {
    const g = new THREE.Group();
    const arco = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.045, 10, 64, Math.PI), liso("#e11d48", 0.4));
    arco.scale.set(1.05, 1.03, 1); arco.rotation.x = -0.16; g.add(arco);
    [-1, 1].forEach((l) => {
      const tallo = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.3, 8), liso("#e11d48", 0.4));
      tallo.position.set(0.3 * l, 1.08, -0.12); tallo.rotation.z = -0.25 * l; g.add(tallo);
      const c = corazon("#f43f5e", 0.3, 0.08); c.position.set(0.36 * l, 1.28, -0.14); c.rotation.z = -0.2 * l; g.add(c);
    });
    return g;
  },
  // Ojos (ancla en la cara, a la altura de los ojos)
  sol() {
    // Cada lente sigue la curva de la cara (la de afuera va un poco hacia atrás).
    const g = new THREE.Group(), marco = liso("#111827", 0.3, { clearcoat: 1 });
    [-1, 1].forEach((l) => {
      const lado = grupo([0.33 * l, 0, 0.02]); lado.rotation.y = 0.22 * l;
      lado.add(malla(G.esfera, vidrio("#0b1220", 0.93), [0, 0, 0.0], [0.24, 0.19, 0.06]));
      const aro = new THREE.Mesh(new THREE.TorusGeometry(1, 0.12, 8, 40), marco);
      aro.scale.set(0.24, 0.19, 0.24); aro.position.z = 0.01; lado.add(aro);
      g.add(lado);
      const patilla = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.62, 8), marco); patilla.name = "patilla";
      patilla.position.set(0.6 * l, 0.03, -0.3); patilla.rotation.set(Math.PI / 2, 0, 0.42 * l); g.add(patilla);
    });
    g.add(malla(new THREE.CylinderGeometry(0.02, 0.02, 0.2, 8), marco, [0, 0.05, 0.06], null, [0, 0, Math.PI / 2]));
    return g;
  },
  nerd() {
    const g = new THREE.Group(), marco = liso("#1a1a1a", 0.35);
    [-1, 1].forEach((l) => {
      const lado = grupo([0.33 * l, 0, 0.02]); lado.rotation.y = 0.22 * l;
      lado.add(new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.035, 12, 40), marco));
      lado.add(malla(new THREE.CircleGeometry(0.21, 32), vidrio("#dbeafe", 0.18), [0, 0, -0.005]));
      g.add(lado);
      const patilla = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.62, 8), marco); patilla.name = "patilla";
      patilla.position.set(0.58 * l, 0.02, -0.3); patilla.rotation.set(Math.PI / 2, 0, 0.42 * l); g.add(patilla);
    });
    g.add(malla(new THREE.TorusGeometry(0.06, 0.025, 8, 16, Math.PI), marco, [0, 0.02, 0.05]));
    return g;
  },
  lentes3d() {
    const g = new THREE.Group();
    [-1, 1].forEach((l) => {
      const mitad = grupo([0.27 * l, 0, 0.05 - 0.02]); mitad.rotation.y = 0.32 * l;
      mitad.add(malla(new THREE.BoxGeometry(0.5, 0.34, 0.04), liso("#ffffff", 0.5), [0.0, 0, 0]));
      mitad.add(malla(new THREE.PlaneGeometry(0.34, 0.22), vidrio(l < 0 ? "#ef4444" : "#06b6d4", 0.85), [0.02 * l, 0, 0.021]));
      const patilla = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.04, 0.7), liso("#ffffff", 0.5)); patilla.name = "patilla";
      patilla.position.set(0.25 * l, 0.04, -0.33); mitad.add(patilla);
      g.add(mitad);
    });
    return g;
  },
  monoculo() {
    const g = new THREE.Group(), oro = metal("#d4a72c", 0.2);
    const aro = new THREE.Mesh(new THREE.TorusGeometry(0.23, 0.03, 12, 40), oro); aro.position.set(0.33, 0, 0.08); g.add(aro);
    g.add(malla(new THREE.CircleGeometry(0.22, 32), vidrio("#e0f2fe", 0.2), [0.33, 0, 0.075]));
    const cadena = new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(0.5, -0.12, 0.06), new THREE.Vector3(0.6, -0.5, 0.0), new THREE.Vector3(0.45, -0.9, -0.05)]), 20, 0.01, 6);
    g.add(new THREE.Mesh(cadena, oro));
    return g;
  },
  // Cuello (ancla donde se une la cabeza con el torso)
  bufanda() { return bufanda(tela("#7c3aed"), tela("#6d28d9")); },
  bufanda_navidad() {
    const t = texturaRayas(["#16a34a", "#dc2626", "#16a34a", "#f8fafc"], 32); t.repeat.set(6, 1);
    const m = new THREE.MeshPhysicalMaterial({ map: t, roughness: 0.9, sheen: 0.8 });
    const t2 = texturaRayas(["#16a34a", "#dc2626", "#f8fafc"], 32, true); t2.repeat.set(1, 2);
    return bufanda(m, new THREE.MeshPhysicalMaterial({ map: t2, roughness: 0.9, sheen: 0.8 }));
  },
  banda_patria() {
    const t = texturaRayas(["#18c3df", "#ffffff", "#18c3df"], 32, true);
    const m = new THREE.MeshPhysicalMaterial({ map: t, roughness: 0.85, sheen: 0.6 });
    const g = new THREE.Group();
    const anillo = anilloCuello(m, 0.11); g.add(anillo);
    g.add(malla(new THREE.SphereGeometry(0.06, 12, 8), liso("#18c3df", 0.4), [0, -0.02, 0.64]));
    return g;
  },
  corbatin() {
    const g = grupo([0, -0.06, 0.7]), m = liso("#111827", 0.4, { clearcoat: 0.6 });
    [-1, 1].forEach((l) => g.add(malla(new THREE.ConeGeometry(0.13, 0.26, 24), m, [0.13 * l, 0, 0], [1, 1, 0.5], [0, 0, Math.PI / 2 * l])));
    g.add(malla(G.esferaB, liso("#374151", 0.4), [0, 0, 0.02], 0.06));
    const r = new THREE.Group(); r.add(g); return r;
  },
  corbata() {
    const g = new THREE.Group(), m = liso("#2563eb", 0.45, { clearcoat: 0.4 });
    const s = new THREE.Shape(); s.moveTo(-0.05, 0); s.lineTo(0.05, 0); s.lineTo(0.12, -0.5); s.lineTo(0, -0.64); s.lineTo(-0.12, -0.5); s.closePath();
    const geo = new THREE.ExtrudeGeometry(s, { depth: 0.03, bevelEnabled: true, bevelSize: 0.012, bevelThickness: 0.012, bevelSegments: 2 });
    const tie = new THREE.Mesh(geo, m); tie.position.set(0, -0.08, 0.68); tie.rotation.x = -0.18; g.add(tie);
    g.add(malla(G.esferaB, liso("#1d4ed8", 0.45), [0, -0.06, 0.71], [0.07, 0.06, 0.05]));
    return g;
  },
  medalla() {
    const g = new THREE.Group(), cinta = tela("#2563eb");
    [-1, 1].forEach((l) => { const c = malla(new THREE.BoxGeometry(0.08, 0.42, 0.02), cinta, [0.11 * l, -0.16, 0.7], null, [-0.15, 0, 0.42 * l]); g.add(c); });
    const disco = malla(new THREE.CylinderGeometry(0.13, 0.13, 0.04, 40), metal("#f5c542", 0.2), [0, -0.4, 0.72], null, [Math.PI / 2 - 0.15, 0, 0]);
    g.add(disco);
    return g;
  },
  panuelo() {
    // Pañuelo: triángulo de tela al frente con bolitas, y su tira alrededor del cuello.
    const g = new THREE.Group(), m = tela("#ef4444");
    const t = new THREE.Shape(); t.moveTo(-0.42, 0); t.quadraticCurveTo(0, 0.05, 0.42, 0); t.lineTo(0, -0.46); t.closePath();
    const tri = new THREE.Mesh(new THREE.ExtrudeGeometry(t, { depth: 0.03, bevelEnabled: true, bevelSize: 0.015, bevelThickness: 0.015, bevelSegments: 3, curveSegments: 16 }), m);
    tri.position.set(0, 0.02, 0.66); tri.rotation.x = -0.28; g.add(tri);
    [[-0.18, -0.1], [0.18, -0.1], [0, -0.2], [0, -0.06], [-0.08, -0.32], [0.08, -0.32]].forEach(([x, y]) => {
      const d = malla(G.esferaB, tela("#ffffff"), [x, y, 0.05], [0.028, 0.028, 0.01]); tri.add(d);
    });
    const tira = anilloCuello(m, 0.05); g.add(tira);
    return g;
  },
  cuello_capa() {
    const g = new THREE.Group(), m = tela("#3b0764");
    [-1, 1].forEach((l) => g.add(malla(new THREE.ConeGeometry(0.26, 0.46, 3), m, [0.34 * l, -0.02, 0.6], [1, 1, 0.3], [Math.PI / 2 + 0.6, 0, 0.9 * l])));
    g.add(malla(G.esferaB, liso("#f97316", 0.3, { clearcoat: 1 }), [0, -0.04, 0.72], 0.07));
    // Capa: media falda detrás del cuerpo (solo la espalda), sin tapar el frente.
    const mCapa = tela("#2e1065"); mCapa.side = THREE.DoubleSide;
    const capa = new THREE.Mesh(new THREE.CylinderGeometry(0.82, 1.0, 0.85, 40, 1, true, Math.PI / 2 + 0.25, Math.PI - 0.5), mCapa);
    capa.position.set(0, -0.38, -0.06); g.add(capa);
    return g;
  },
  collar_corazon() {
    const g = new THREE.Group();
    const cadena = anilloCuello(metal("#fbcfe8", 0.3), 0.018); cadena.rotation.x -= 0.12; g.add(cadena);
    const c = corazon("#e11d48", 0.17, 0.06); c.position.set(0, -0.16, 0.74); g.add(c);
    return g;
  },
  // En la mano (ancla en la palma derecha)
  destornillador() {
    const g = new THREE.Group();
    g.add(malla(new THREE.CylinderGeometry(0.06, 0.07, 0.3, 16), liso("#ef4444", 0.35, { clearcoat: 0.8 }), [0, 0.05, 0]));
    g.add(malla(new THREE.CylinderGeometry(0.018, 0.018, 0.42, 8), metal("#cbd5e1", 0.2), [0, 0.4, 0]));
    g.rotation.set(0.3, 0, -0.5);
    return g;
  },
  cafe() {
    const g = new THREE.Group();
    const taza = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.11, 0.24, 32, 1, true), liso("#ffffff", 0.2, { clearcoat: 1 }));
    taza.material.side = THREE.DoubleSide; g.add(taza);
    g.add(malla(new THREE.CircleGeometry(0.12, 32), liso("#5b3416", 0.3), [0, 0.09, 0], null, [-Math.PI / 2, 0, 0]));
    g.add(malla(new THREE.CylinderGeometry(0.11, 0.11, 0.01, 32), liso("#ffffff", 0.2), [0, -0.12, 0]));
    const asa = new THREE.Mesh(new THREE.TorusGeometry(0.07, 0.02, 8, 20), liso("#ffffff", 0.2)); asa.position.set(0.15, 0, 0); g.add(asa);
    g.position.y = 0.12;
    return g;
  },
  celular() {
    const g = new THREE.Group();
    g.add(malla(new THREE.BoxGeometry(0.2, 0.38, 0.035), liso("#111827", 0.25, { clearcoat: 1 }), [0, 0.12, 0]));
    g.add(malla(new THREE.PlaneGeometry(0.17, 0.32), new THREE.MeshBasicMaterial({ color: "#38bdf8" }), [0, 0.12, 0.019]));
    g.rotation.set(-0.2, 0.3, -0.2);
    return g;
  },
  lupa() {
    const g = new THREE.Group();
    g.add(malla(new THREE.CylinderGeometry(0.035, 0.035, 0.28, 12), liso("#78350f", 0.5), [0, 0, 0]));
    const aro = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.03, 12, 40), metal("#64748b", 0.3)); aro.position.y = 0.3; g.add(aro);
    g.add(malla(new THREE.CircleGeometry(0.15, 32), vidrio("#e0f2fe", 0.35), [0, 0.3, 0]));
    g.rotation.z = -0.4;
    return g;
  },
  regalo() {
    const g = new THREE.Group();
    g.add(malla(new THREE.BoxGeometry(0.34, 0.3, 0.3), liso("#dc2626", 0.4, { clearcoat: 0.6 }), [0, 0.15, 0]));
    const cinta = liso("#facc15", 0.3, { clearcoat: 1 });
    g.add(malla(new THREE.BoxGeometry(0.07, 0.31, 0.31), cinta, [0, 0.15, 0]));
    g.add(malla(new THREE.BoxGeometry(0.35, 0.31, 0.07), cinta, [0, 0.15, 0]));
    [-1, 1].forEach((l) => g.add(malla(new THREE.TorusGeometry(0.07, 0.025, 8, 20), cinta, [0.06 * l, 0.34, 0], null, [0, 0, 0.6 * l])));
    return g;
  },
  calabaza() {
    const g = new THREE.Group(), m = liso("#f97316", 0.55);
    for (let i = 0; i < 6; i++) { const a = (i / 6) * TAU; g.add(malla(G.esfera, m, [Math.sin(a) * 0.08, 0.16, Math.cos(a) * 0.08], [0.13, 0.15, 0.13])); }
    g.add(malla(new THREE.CylinderGeometry(0.025, 0.035, 0.1, 8), liso("#166534", 0.6), [0, 0.33, 0]));
    return g;
  },
  globo_corazon() {
    // Globo de corazón: flota al lado de la mascota (lejos de la cabeza y del
    // gorro) amarrado a su mano. Se coloca respecto al cuerpo, no a la mano,
    // para que al mover los brazos nunca se le meta en la cara.
    const g = new THREE.Group();
    const mano = new THREE.Vector3(0.88, 0.34, 0.14), nudo = new THREE.Vector3(1.4, 1.74, 0.3);
    const hilo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3([mano, new THREE.Vector3(1.08, 0.85, 0.22), new THREE.Vector3(1.32, 1.35, 0.28), nudo]), 40, 0.008, 6);
    g.add(new THREE.Mesh(hilo, liso("#e5e7eb", 0.6)));
    const globo = corazon("#f43f5e", 0.4, 0.24); globo.position.copy(nudo).add(new THREE.Vector3(0.02, 0.4, 0)); globo.rotation.z = -0.12;
    globo.material = liso("#f43f5e", 0.12, { clearcoat: 1, clearcoatRoughness: 0.04 });
    g.add(globo);
    g.add(malla(new THREE.ConeGeometry(0.05, 0.08, 16), liso("#e11d48", 0.3), [nudo.x, nudo.y + 0.03, nudo.z], null, [Math.PI, 0, 0]));
    g.userData.globo = globo; g.userData.flotante = true;
    return g;
  },
  bandera() {
    const g = new THREE.Group();
    g.add(malla(new THREE.CylinderGeometry(0.015, 0.015, 0.8, 8), liso("#78350f", 0.6), [0, 0.3, 0]));
    const c = document.createElement("canvas"); c.width = 120; c.height = 80; const x = c.getContext("2d");
    x.fillStyle = "#18c3df"; x.fillRect(0, 0, 120, 80); x.fillStyle = "#fff"; x.fillRect(0, 27, 120, 26);
    x.fillStyle = "#18c3df"; [[60, 40], [48, 34], [72, 34], [48, 46], [72, 46]].forEach(([a, b]) => { x.beginPath(); x.arc(a, b, 3, 0, TAU); x.fill(); });
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    const tela_ = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.28, 12, 4), new THREE.MeshStandardMaterial({ map: t, side: THREE.DoubleSide, roughness: 0.8 }));
    tela_.position.set(0.21, 0.56, 0); g.add(tela_);
    g.userData.bandera = tela_;
    g.rotation.z = -0.25;
    return g;
  },
};
// Gorro con la misma forma de la cabeza (esfera 1 × 0.93 × 0.92), un poco
// más grande para que la cubra sin atravesarse; corte = hasta qué ángulo baja.
function gorroCabeza(mat, corte, holgura) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32, 0, TAU, 0, corte), mat);
  m.scale.set(holgura, 0.93 * holgura, 0.92 * holgura);
  return m;
}
// Borde (aro) justo donde termina el gorro, tapando la orilla.
function bordeGorro(mat, corte, holgura, grosor) {
  const aro = new THREE.Mesh(new THREE.TorusGeometry(Math.sin(corte) + grosor * 0.6 / holgura, grosor / holgura, 16, 72), mat);
  aro.rotation.x = Math.PI / 2;
  const g = new THREE.Group(); g.add(aro);
  g.position.y = 0.93 * holgura * Math.cos(corte);
  g.scale.set(holgura, holgura, 0.92 / 1 * holgura);
  return g;
}

// Tubo que se va afinando a lo largo de una curva (radio(k), k de 0 a 1).
function tuboAfinado(curva, radio, tramos = 40, lados = 32) {
  const marcos = curva.computeFrenetFrames(tramos, false);
  const pos = [], uv = [], idx = [];
  for (let i = 0; i <= tramos; i++) {
    const k = i / tramos, p = curva.getPointAt(k), r = radio(k);
    for (let j = 0; j <= lados; j++) {
      const a = (j / lados) * TAU;
      const n = marcos.normals[i].clone().multiplyScalar(Math.cos(a)).add(marcos.binormals[i].clone().multiplyScalar(Math.sin(a)));
      pos.push(p.x + n.x * r, p.y + n.y * r, p.z + n.z * r); uv.push(j / lados, k);
    }
  }
  for (let i = 0; i < tramos; i++) for (let j = 0; j < lados; j++) {
    const a = i * (lados + 1) + j, b = a + lados + 1;
    idx.push(a, a + 1, b, b, a + 1, b + 1);  // caras hacia afuera
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx); geo.computeVertexNormals();
  return geo;
}

// Aro alrededor del cuello que descansa SOBRE el cuerpo (elíptico como el
// torso a esa altura: 0.77 de ancho y 0.67 de fondo), sin hundirse en él.
function anilloCuello(mat, grosor) {
  const aro = new THREE.Mesh(new THREE.TorusGeometry(1, grosor / 0.84, 16, 72), mat);
  aro.rotation.x = Math.PI / 2;
  aro.scale.set(0.77 + grosor * 0.95, 0.67 + grosor * 0.95, 0.84);
  return aro;
}

function bufanda(m1, m2) {
  const g = new THREE.Group();
  const anillo = anilloCuello(m1, 0.14);
  g.add(anillo);
  const cola = malla(new THREE.BoxGeometry(0.22, 0.55, 0.08), m2, [0.32, -0.3, 0.8], null, [-0.32, 0.1, 0.15]);
  g.add(cola);
  return g;
}

// ---------- Vista (escena + animación) ----------
const vistas = new Set();
let pausado = false;
document.addEventListener("visibilitychange", () => { pausado = document.hidden; });
let mouse = { x: 0, y: 0, t: 0 };
window.addEventListener("pointermove", (e) => { mouse = { x: e.clientX, y: e.clientY, t: performance.now() }; }, { passive: true });

function sombraPiso() {
  const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d");
  const r = g.createRadialGradient(64, 64, 4, 64, 64, 64);
  r.addColorStop(0, "rgba(0,0,0,.45)"); r.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = r; g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 2.4), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; m.position.y = -0.04; m.scale.set(1, 0.55, 1);
  return m;
}

const REACCIONES = ["salto", "giro", "baile", "saludo", "sorpresa", "risa", "mareo", "corazones", "confeti", "celebrar"];
const DURACION = { salto: 0.8, giro: 0.9, baile: 1.2, saludo: 1.4, sorpresa: 0.9, risa: 1.0, mareo: 1.3, corazones: 1.4, confeti: 1.3, celebrar: 1.3 };

function crear(contenedor, opciones) {
  const op = Object.assign({ tipo: "panda", ropa: {}, interactiva: true, encuadre: "flotante" }, opciones || {});
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  } catch (e) { return null; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.domElement.className = "m3d-lienzo";
  contenedor.appendChild(renderer.domElement);

  const escena = new THREE.Scene();
  escena.add(new THREE.HemisphereLight("#ffffff", "#7a8699", 1.25));
  const sol = new THREE.DirectionalLight("#fff6ea", 2.4); sol.position.set(2.5, 4, 5); escena.add(sol);
  const relleno = new THREE.DirectionalLight("#cfe3ff", 0.7); relleno.position.set(-4, 1.5, 3); escena.add(relleno);
  const contraluz = new THREE.DirectionalLight("#ffffff", 1.6); contraluz.position.set(-2, 3, -4); escena.add(contraluz);

  const camara = new THREE.PerspectiveCamera(26, 1, 0.1, 50);
  const encuadres = { flotante: [0, 1.32, 9.6, 1.3], tarjeta: [0, 1.32, 9.2, 1.3], grande: [0, 1.32, 8.6, 1.28] };
  const [cx, cy, cz, mira] = encuadres[op.encuadre] || encuadres.flotante;
  camara.position.set(cx, cy, cz); camara.lookAt(0, mira, 0);

  let pj = crearPersonaje(op.tipo);
  escena.add(pj.raiz); escena.add(sombraPiso());
  const particulas = [];
  let ropaActual = {};

  function ponerRopa(ropa) {
    ropaActual = Object.assign({}, ropa || {});
    ["cabeza", "ojos", "cuello", "mano"].forEach((parte) => {
      const ancla = pj.anclas[parte];
      while (ancla.children.length) ancla.remove(ancla.children[0]);
      if (parte === "mano") { while (pj.flotante.children.length) pj.flotante.remove(pj.flotante.children[0]); }
      const clave = ropaActual[parte];
      if (clave && ROPA[clave]) {
        const pieza = ROPA[clave]();
        // Corbatas, medallas y collares van un poco más abajo que las bufandas.
        if (parte === "cuello" && !/^(bufanda|bufanda_navidad|banda_patria)$/.test(clave)) pieza.position.y -= 0.07;
        (pieza.userData.flotante ? pj.flotante : ancla).add(pieza);
      }
      if (parte === "cabeza") {
        // Con gorro o casco las orejas salen por fuera (como por dos agujeros):
        // se empujan un poco hacia afuera para que se vean completas.
        const tapa = !!(ancla.children[0] && ancla.children[0].userData.tapaOrejas);
        pj.orejas.forEach((o) => {
          if (!o.userData.base) o.userData.base = { p: o.position.clone(), s: o.scale.clone() };
          const b = o.userData.base;
          o.visible = true;
          o.position.copy(b.p); o.scale.copy(b.s);
          if (tapa) { o.position.multiplyScalar(1.13); o.position.y += 0.06; o.scale.multiplyScalar(1.08); }
        });
      }
    });
  }
  ponerRopa(op.ropa);

  function ajustar() {
    const w = contenedor.clientWidth || 64, h = contenedor.clientHeight || 74;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camara.aspect = w / h; camara.updateProjectionMatrix();
  }
  ajustar();
  const ro = new ResizeObserver(ajustar); ro.observe(contenedor);

  // Estado de animación
  let reaccion = null; // {nombre, t0}
  let proxParpadeo = performance.now() + 1500 + Math.random() * 2500, parpadeo0 = 0;
  let proxSaludo = performance.now() + 4000 + Math.random() * 4000;
  const mirar = { x: 0, y: 0 };
  const reloj = new THREE.Clock();

  function lanzarParticulas(tipo) {
    const n = tipo === "corazones" ? 5 : 14;
    for (let i = 0; i < n; i++) {
      let m;
      if (tipo === "corazones") { m = corazon(["#f43f5e", "#ec4899", "#ef4444"][i % 3], 0.16, 0.05); }
      else { m = malla(new THREE.BoxGeometry(0.08, 0.12, 0.01), liso(["#f43f5e", "#facc15", "#22c55e", "#3b82f6", "#a855f7"][i % 5], 0.4)); }
      m.position.set((Math.random() - 0.5) * 0.6, 2.2, 0.4);
      m.userData.v = new THREE.Vector3((Math.random() - 0.5) * (tipo === "corazones" ? 0.8 : 2.6), tipo === "corazones" ? 1.2 + Math.random() * 0.6 : 2 + Math.random() * 1.5, (Math.random() - 0.2) * 0.8);
      m.userData.vida = tipo === "corazones" ? 1.4 : 1.2; m.userData.edad = 0; m.userData.giro = (Math.random() - 0.5) * 12;
      m.userData.tipo = tipo;
      escena.add(m); particulas.push(m);
    }
  }

  function reaccionar(nombre) {
    nombre = REACCIONES.indexOf(nombre) >= 0 ? nombre : REACCIONES[Math.floor(Math.random() * REACCIONES.length)];
    reaccion = { nombre, t0: reloj.getElapsedTime() };
    if (nombre === "corazones" || nombre === "confeti" || nombre === "celebrar") lanzarParticulas(nombre === "corazones" ? "corazones" : "confeti");
    return nombre;
  }

  function tick() {
    if (!vistas.has(vista)) return;
    requestAnimationFrame(tick);
    if (pausado) return;
    const t = reloj.getElapsedTime(), dt = Math.min(reloj.getDelta ? 0.033 : 0.033, 0.05);
    const ahora = performance.now();

    // Reposo: respira, mira, parpadea, mueve la cola
    const respira = Math.sin(t * 2.2);
    pj.torso.scale.set(1 + respira * 0.012, 1 + respira * 0.02, 1 + respira * 0.012);
    pj.raiz.position.set(0, 0, 0); pj.raiz.rotation.set(0, 0, 0);
    pj.cadera.scale.set(1, 1, 1); pj.cadera.position.set(0, 0, 0);
    pj.cuello.rotation.set(0, 0, 0);
    pj.brazos.forEach((b) => { b.rotation.set(0, 0, 0.45 * b.userData.lado + Math.sin(t * 2.2 + b.userData.lado) * 0.03); });
    if (pj.cola) pj.cola.rotation.set(0, Math.sin(t * 1.6) * 0.35, Math.sin(t * 2.1) * 0.12);
    pj.orejas.forEach((o, i) => { o.rotation.x = Math.sin(t * 3 + i) * 0.03; });

    // Seguir el mouse con la cabeza (solo cerca y si se movió hace poco)
    let objetivoX = Math.sin(t * 0.5) * 0.12, objetivoY = Math.sin(t * 0.37) * 0.05;
    if (op.interactiva && ahora - mouse.t < 4000) {
      const r = contenedor.getBoundingClientRect();
      const dx = (mouse.x - (r.left + r.width / 2)) / Math.max(window.innerWidth, 1);
      const dy = (mouse.y - (r.top + r.height * 0.35)) / Math.max(window.innerHeight, 1);
      objetivoX = THREE.MathUtils.clamp(dx * 2.2, -0.6, 0.6); objetivoY = THREE.MathUtils.clamp(dy * 1.6, -0.35, 0.35);
    }
    mirar.x += (objetivoX - mirar.x) * 0.08; mirar.y += (objetivoY - mirar.y) * 0.08;
    pj.cabeza.rotation.set(mirar.y, mirar.x, -mirar.x * 0.15);
    let estadoOjos = "normal";
    pj.ojos.forEach((o) => { o.scale.set(1, 1, 1); o.userData.pupila.position.set(mirar.x * 0.06, -0.01 - mirar.y * 0.05, 0.09); });

    // Parpadeo
    if (ahora > proxParpadeo) { parpadeo0 = ahora; proxParpadeo = ahora + 2500 + Math.random() * 3500; }
    const fp = (ahora - parpadeo0) / 160;
    const cierre = fp >= 0 && fp <= 1 ? Math.sin(fp * Math.PI) : 0;
    let cierreOjos = cierre;

    // Saludo de vez en cuando
    if (!reaccion && ahora > proxSaludo) { reaccion = { nombre: "saludo", t0: t, suave: true }; proxSaludo = ahora + 9000 + Math.random() * 7000; }

    // Boca normal
    pj.bocaAbierta.scale.set(0.11, 0.0001, 0.04); pj.sonrisa.visible = true;

    // Reacciones
    if (reaccion) {
      const d = DURACION[reaccion.nombre] || 1;
      const k = (t - reaccion.t0) / d;
      if (k >= 1) reaccion = null;
      else {
        const e = Math.sin(k * Math.PI);
        switch (reaccion.nombre) {
          case "salto": {
            const salto = k < 0.15 ? -0.08 * Math.sin(k / 0.15 * Math.PI) : Math.sin((k - 0.15) / 0.85 * Math.PI) * 0.9;
            pj.raiz.position.y = Math.max(salto, -0.08);
            const sq = k < 0.15 ? 1 - 0.18 * Math.sin(k / 0.15 * Math.PI) : 1 + 0.08 * Math.sin((k - 0.15) / 0.85 * Math.PI);
            pj.cadera.scale.set(2 - sq, sq, 2 - sq);
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 1.3) * b.userData.lado; });
            if (k > 0.2 && k < 0.85) estadoOjos = "feliz";
            break;
          }
          case "giro": pj.raiz.rotation.y = THREE.MathUtils.smootherstep(k, 0, 1) * TAU; pj.raiz.position.y = e * 0.25; break;
          case "baile":
            pj.raiz.rotation.z = Math.sin(k * TAU * 3) * 0.18; pj.raiz.position.y = Math.abs(Math.sin(k * TAU * 3)) * 0.15;
            pj.brazos.forEach((b) => { b.rotation.z = (1.0 + Math.sin(k * TAU * 3 + b.userData.lado) * 0.6) * b.userData.lado; });
            pj.cuello.rotation.z = Math.sin(k * TAU * 3) * 0.2; break;
          case "saludo": {
            const b = pj.brazos[0];
            b.rotation.z = -(0.45 + (1.3 + Math.sin(k * TAU * 3) * 0.2) * (reaccion.suave ? THREE.MathUtils.smoothstep(e, 0, 0.35) : 1));
            b.rotation.x = -0.2;
            break;
          }
          case "sorpresa":
            estadoOjos = "sorpresa"; pj.raiz.position.y = e * 0.15;
            pj.bocaAbierta.scale.set(0.09, 0.1 * e + 0.0001, 0.04); pj.sonrisa.visible = false;
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 1.0) * b.userData.lado; }); break;
          case "risa":
            pj.raiz.rotation.z = Math.sin(k * TAU * 7) * 0.08 * e; pj.cuello.rotation.x = -0.2 * e;
            pj.bocaAbierta.scale.set(0.12, 0.11 * e + 0.0001, 0.045); pj.sonrisa.visible = false;
            estadoOjos = "feliz"; break;
          case "mareo":
            pj.cabeza.rotation.z += Math.sin(k * TAU * 2.5) * 0.35 * e; pj.cabeza.rotation.x += Math.cos(k * TAU * 2.5) * 0.15 * e;
            pj.raiz.rotation.z = Math.sin(k * TAU * 1.5) * 0.12 * e;
            estadoOjos = "mareo"; break;
          case "corazones":
            estadoOjos = "amor"; pj.cuello.rotation.z = Math.sin(k * TAU) * 0.15;
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 0.35) * b.userData.lado; b.rotation.x = -0.45 * e; }); break;
          case "confeti":
          case "celebrar":
            pj.raiz.position.y = Math.abs(Math.sin(k * TAU * 2)) * 0.35;
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 1.5) * b.userData.lado; }); estadoOjos = "feliz";
            pj.bocaAbierta.scale.set(0.11, 0.09 * e + 0.0001, 0.04); pj.sonrisa.visible = false; break;
        }
      }
    }

    pj.ojos.forEach((o) => {
      const feliz = estadoOjos === "feliz";
      o.children.forEach((h) => { if (h !== o.userData.corazon) h.visible = !feliz; });
      o.userData.feliz.visible = feliz;
      o.userData.corazon.visible = estadoOjos === "amor";
      o.userData.pupila.visible = !feliz && estadoOjos !== "amor";
      if (estadoOjos === "sorpresa") o.scale.setScalar(pj.anclas.ojos.children.length ? 1.06 : 1.3);
      if (estadoOjos === "mareo") { const a = t * 14; o.userData.pupila.position.x = Math.cos(a) * 0.05; o.userData.pupila.position.y = Math.sin(a) * 0.05; }
      if (estadoOjos === "amor") o.userData.corazon.scale.setScalar(1 + Math.sin(t * 12) * 0.12);
    });
    pj.parpados.forEach((p) => { p.scale.y = Math.max(0.0001, (estadoOjos === "normal" ? cierreOjos : 0) * 0.22); });

    // Lo que sostiene en la mano se queda derecho aunque mueva el brazo.
    const brazoDer = pj.brazos[1];
    pj.anclas.mano.rotation.set(-brazoDer.rotation.x, -brazoDer.rotation.y, -brazoDer.rotation.z);

    // Bandera y globo se mueven con el aire
    const mano = pj.anclas.mano.children[0];
    if (mano && mano.userData.bandera) mano.userData.bandera.rotation.y = Math.sin(t * 3) * 0.25;
    const flot = pj.flotante.children[0];
    if (flot && flot.userData.globo) { flot.userData.globo.rotation.z = -0.12 + Math.sin(t * 1.5) * 0.08; flot.userData.globo.position.y = 2.12 + Math.sin(t * 1.2) * 0.03; }

    // Partículas
    for (let i = particulas.length - 1; i >= 0; i--) {
      const p = particulas[i];
      p.userData.edad += dt;
      p.userData.v.y -= (p.userData.tipo === "corazones" ? 0.4 : 4.5) * dt;
      p.position.addScaledVector(p.userData.v, dt);
      p.rotation.z += p.userData.giro * dt; p.rotation.y += p.userData.giro * 0.5 * dt;
      const vida = 1 - p.userData.edad / p.userData.vida;
      p.scale.setScalar(Math.max(vida, 0.001));
      if (vida <= 0) { escena.remove(p); particulas.splice(i, 1); }
    }

    renderer.render(escena, camara);
  }

  // Arrastrar para girarla (vistas previas: orbitar=true)
  let angulo = 0, arrastre = null;
  if (op.orbitar) {
    const el = renderer.domElement; el.style.cursor = "grab"; el.style.touchAction = "none";
    el.addEventListener("pointerdown", (e) => { arrastre = { x: e.clientX, a: angulo }; el.setPointerCapture(e.pointerId); el.style.cursor = "grabbing"; });
    el.addEventListener("pointermove", (e) => { if (arrastre) angulo = arrastre.a + (e.clientX - arrastre.x) * 0.012; });
    const soltar = () => { arrastre = null; el.style.cursor = "grab"; };
    el.addEventListener("pointerup", soltar); el.addEventListener("pointercancel", soltar);
  }
  const _render = renderer.render.bind(renderer);
  renderer.render = (esc, cam) => { pj.raiz.rotation.y += angulo; _render(esc, cam); pj.raiz.rotation.y -= angulo; };

  const vista = {
    reaccionar, ponerRopa,
    girar(a) { angulo = a; },
    get personaje() { return pj; },
    get escena() { return escena; },
    cambiarTipo(tipo) { escena.remove(pj.raiz); pj = crearPersonaje(tipo); escena.add(pj.raiz); ponerRopa(ropaActual); },
    destruir() { vistas.delete(vista); ro.disconnect(); renderer.dispose(); renderer.domElement.remove(); },
  };
  vistas.add(vista);
  requestAnimationFrame(tick);
  return vista;
}

window.Mascota3D = { crear, REACCIONES };

// Mascota flotante del sistema (base.html): se arma sola.
(function iniciarFlotante() {
  const caja = document.getElementById("pandaCajaMascota");
  if (!caja || !caja.classList.contains("mascota-3d") || caja.classList.contains("mascota-oculta")) return;
  let ropa = {};
  try { ropa = JSON.parse(caja.dataset.ropa || "{}"); } catch (e) { ropa = {}; }
  const vista = crear(caja, { tipo: caja.dataset.mascota || "panda", ropa, interactiva: true, encuadre: "flotante" });
  if (vista) { caja.classList.add("m3d-lista"); window.mascotaFlotante = vista; }
})();
window.dispatchEvent(new Event("mascota3d-lista"));
