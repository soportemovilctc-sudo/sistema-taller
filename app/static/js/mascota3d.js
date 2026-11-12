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
  return new THREE.MeshStandardMaterial({ color, metalness: 1, roughness: rugosidad });
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
  const geo = new THREE.ExtrudeGeometry(formaCorazon(t), { depth: prof, bevelEnabled: true, bevelSize: prof * 0.5, bevelThickness: prof * 0.5, bevelSegments: 4, curveSegments: 18 });
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
  leon: { cabeza: [0, 0.06, 0, 1.08], ojos: [0, 0, 0.02, 1.0], cuello: [0, -0.1, 0.02, 1.04], mano: [0, 0, 0, 1.0] },
  raton: { cabeza: [0, -0.02, 0, 0.96], ojos: [0, 0, 0, 1.0], cuello: [0, 0, 0, 0.98], mano: [0, 0, 0, 1.0] },
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
  if (tipo === "panda") {
    [-1, 1].forEach((lado) => {
      const m = malla(G.esfera, mOscuro, [0.34 * lado, 0.04, 0.74], [0.25, 0.32, 0.16], [0, 0, 0.45 * lado]);
      cabeza.add(m);
    });
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

  // Ojos grandes estilo «kawaii»: iris de color con degradado, pupila
  // brillante y dos destellos grandes; párpado para parpadear.
  const IRIS = { panda: ["#5b3a26", "#1c120c"], leon: ["#b06a1c", "#3a1f08"], raton: ["#5a4a7a", "#1d1530"] }[tipo] || ["#4a3324", "#140d08"];
  const mIris = liso(IRIS[0], 0.2, { clearcoat: 1, clearcoatRoughness: 0.03 });
  const mIrisOsc = liso(IRIS[1], 0.2, { clearcoat: 1, clearcoatRoughness: 0.03 });
  const ojos = [], parpados = [];
  [-1, 1].forEach((lado) => {
    const ojo = grupo([0.32 * lado, 0.04, 0.8]);
    ojo.rotation.y = 0.18 * lado;
    ojo.add(malla(G.esfera, mBlanco, [0, 0, 0], [0.2, 0.24, 0.12]));
    const pupila = grupo([0, -0.015, 0.075]);
    pupila.add(malla(G.esfera, mIrisOsc, [0, 0, 0], [0.168, 0.2, 0.06]));         // borde oscuro del iris
    pupila.add(malla(G.esfera, mIris, [0, -0.012, 0.012], [0.145, 0.172, 0.055]));   // iris de color
    pupila.add(malla(G.esfera, mPupila, [0, 0.0, 0.026], [0.09, 0.11, 0.045]));      // pupila
    pupila.add(malla(G.esferaB, mBrillo, [-0.055, 0.07, 0.068], [0.056, 0.064, 0.012]));  // destello grande
    pupila.add(malla(G.esferaB, mBrillo, [0.058, -0.068, 0.062], [0.03, 0.03, 0.01]));    // destello chico
    pupila.add(malla(G.esferaB, mBrillo, [-0.09, -0.03, 0.052], [0.013, 0.013, 0.008])); // chispita
    ojo.add(pupila);
    // pestañitas
    const mPest = liso("#1d1a1a", 0.5);
    [0, 1].forEach((i) => {
      const pe = new THREE.Mesh(new THREE.CapsuleGeometry(0.012, 0.07, 4, 8), mPest);
      pe.position.set((0.17 + i * 0.035) * lado, 0.15 - i * 0.05, 0.03); pe.rotation.z = (-0.9 - i * 0.35) * lado;
      ojo.add(pe);
    });
    const parpado = malla(new THREE.SphereGeometry(1, 32, 16, 0, TAU, 0, Math.PI / 2), tipo === "panda" ? mOscuro : mPelo, [0, 0.0, 0.005], [0.212, 0.252, 0.135]);
    parpado.rotation.x = -Math.PI / 2;
    parpado.scale.y = 0.0001;
    ojo.add(parpado);
    ojo.userData.pupila = pupila;
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
    ojos: grupo([aj.ojos[0], aj.ojos[1] + 0.06, 0.88 + aj.ojos[2]]),
    cuello: grupo([aj.cuello[0], -0.06 + aj.cuello[1], aj.cuello[2]]),
    mano: grupo([0, -0.05, 0.12]),
  };
  ["cabeza", "ojos", "cuello", "mano"].forEach((k) => anclas[k].scale.setScalar(aj[k][3]));
  cabeza.add(anclas.cabeza); cabeza.add(anclas.ojos); cuello.add(anclas.cuello);
  brazos[1].userData.mano.add(anclas.mano);

  return { raiz, cadera, torso, cuello, cabeza, brazos, piernas, orejas, ojos, parpados, boca, bocaAbierta, sonrisa, cola, anclas, tipo };
}

// ---------- Ropa 3D (las claves son las de ropa_mascota.py) ----------
const ROPA = {
  // Cabeza (el ancla es el centro de la cabeza; radio de la cabeza ≈ 1)
  gorra() {
    const g = new THREE.Group(), m = tela("#2563eb");
    g.add(malla(new THREE.SphereGeometry(1.03, 48, 24, 0, TAU, 0, 1.05), m, [0, 0.02, 0]));
    const visera = malla(new THREE.CylinderGeometry(0.62, 0.62, 0.05, 40, 1, false, -Math.PI / 2, Math.PI), liso("#1d4ed8", 0.5), [0, 0.5, 0.62], null, [0.25, 0, 0]);
    g.add(visera);
    g.add(malla(G.esferaB, liso("#1e40af", 0.5), [0, 1.04, 0], 0.08));
    return g;
  },
  lana() {
    const g = new THREE.Group();
    g.add(malla(new THREE.SphereGeometry(1.06, 48, 24, 0, TAU, 0, 1.12), tela("#0ea5e9"), [0, 0, 0]));
    const borde = new THREE.Mesh(new THREE.TorusGeometry(0.96, 0.12, 16, 64), tela("#0369a1"));
    borde.position.y = 0.46; borde.rotation.x = Math.PI / 2; g.add(borde);
    g.add(malla(G.esfera, tela("#e0f2fe"), [0, 1.18, 0], 0.22));
    return g;
  },
  casco() {
    const g = new THREE.Group(), m = liso("#facc15", 0.3, { clearcoat: 1 });
    g.add(malla(new THREE.SphereGeometry(1.08, 48, 24, 0, TAU, 0, 1.08), m, [0, 0, 0]));
    const ala = new THREE.Mesh(new THREE.TorusGeometry(0.98, 0.07, 12, 64), liso("#eab308", 0.35));
    ala.position.y = 0.5; ala.rotation.x = Math.PI / 2; g.add(ala);
    g.add(malla(new THREE.BoxGeometry(0.16, 0.1, 1.5), liso("#fde047", 0.3), [0, 1.04, 0], null, [0, 0, 0]));
    return g;
  },
  vaquero() {
    const g = new THREE.Group(), cafe = tela("#a16207");
    const perfil = [[0, 0], [0.62, 0], [0.66, 0.3], [0.6, 0.62], [0.3, 0.7], [0.1, 0.62], [0, 0.66]].map((p) => new THREE.Vector2(p[0], p[1]));
    const copa = new THREE.Mesh(new THREE.LatheGeometry(perfil, 48), tela("#ca8a04"));
    copa.position.y = 0.72; g.add(copa);
    const ala = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.05, 64), cafe);
    ala.position.y = 0.76; ala.scale.z = 0.85; g.add(ala);
    [-1, 1].forEach((l) => { const r = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.06, 8, 32, Math.PI), cafe); r.position.set(1.2 * l, 0.9, 0); r.rotation.set(0, Math.PI / 2, l > 0 ? 0 : Math.PI); g.add(r); });
    const banda = new THREE.Mesh(new THREE.CylinderGeometry(0.665, 0.665, 0.12, 48, 1, true), tela("#78350f"));
    banda.position.y = 0.86; g.add(banda);
    g.rotation.z = -0.08;
    return g;
  },
  corona() {
    const g = new THREE.Group(), oro = metal("#f5c542", 0.2);
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.56, 0.52, 0.28, 48, 1, true), oro);
    base.material.side = THREE.DoubleSide; base.position.y = 0.98; g.add(base);
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * TAU;
      const pico = malla(new THREE.ConeGeometry(0.11, 0.32, 16), oro, [Math.sin(a) * 0.54, 1.27, Math.cos(a) * 0.54]);
      g.add(pico);
      g.add(malla(G.esferaB, oro, [Math.sin(a) * 0.54, 1.45, Math.cos(a) * 0.54], 0.05));
    }
    [["#dc2626", 0], ["#2563eb", 1.2], ["#16a34a", -1.2]].forEach(([c, a]) => g.add(malla(G.esferaB, liso(c, 0.1, { clearcoat: 1 }), [Math.sin(a) * 0.57, 0.98, Math.cos(a) * 0.57], 0.075)));
    g.rotation.z = 0.08;
    return g;
  },
  mono() {
    const g = new THREE.Group(), m = tela("#ec4899");
    const lazo = grupo([0.62, 0.78, 0.25]);
    [-1, 1].forEach((l) => lazo.add(malla(new THREE.ConeGeometry(0.2, 0.36, 24), m, [0.18 * l, 0, 0], null, [0, 0, -Math.PI / 2 * l])));
    lazo.add(malla(G.esferaB, tela("#db2777"), [0, 0, 0], 0.1));
    lazo.rotation.set(0.2, 0.4, 0.5);
    g.add(lazo);
    return g;
  },
  santa() {
    const g = new THREE.Group(), rojo = tela("#dc2626"), blanco = tela("#ffffff");
    const borde = new THREE.Mesh(new THREE.TorusGeometry(0.74, 0.13, 16, 64), blanco);
    borde.position.set(0, 0.6, 0.06); borde.rotation.x = Math.PI / 2 - 0.22; borde.scale.set(1.08, 1.08, 1); g.add(borde);
    const base = malla(new THREE.SphereGeometry(1.0, 40, 20, 0, TAU, 0, 0.95), rojo, [0, 0.04, 0], [1, 1.02, 1]);
    g.add(base);
    const cono = new THREE.Mesh(new THREE.ConeGeometry(0.52, 1.0, 40, 8), rojo);
    cono.position.set(0.2, 1.3, -0.08); cono.rotation.z = -0.85; g.add(cono);
    g.add(malla(G.esfera, blanco, [0.62, 1.52, -0.08], 0.16));
    return g;
  },
  bruja() {
    const g = new THREE.Group(), m = tela("#3b0764");
    const ala = new THREE.Mesh(new THREE.CylinderGeometry(1.55, 1.55, 0.05, 64), tela("#2e1065"));
    ala.position.y = 0.72; g.add(ala);
    const cono = new THREE.Mesh(new THREE.ConeGeometry(0.7, 1.6, 40, 6), m);
    cono.position.set(0, 1.5, 0); cono.rotation.z = 0.12; g.add(cono);
    const banda = new THREE.Mesh(new THREE.CylinderGeometry(0.68, 0.7, 0.18, 40, 1, true), tela("#f97316"));
    banda.position.y = 0.86; g.add(banda);
    g.add(malla(new THREE.BoxGeometry(0.2, 0.16, 0.04), metal("#facc15"), [0, 0.86, 0.69]));
    return g;
  },
  diadema_corazones() {
    const g = new THREE.Group();
    const arco = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.04, 8, 48, Math.PI), liso("#e11d48", 0.4));
    arco.position.set(0, 0.05, -0.1); arco.rotation.y = Math.PI / 2 - 0.0; arco.rotation.x = 0.0; arco.rotation.order = "YXZ";
    arco.rotation.set(-0.25, Math.PI / 2, 0);
    g.add(arco);
    [-1, 1].forEach((l) => { const c = corazon("#f43f5e", 0.32, 0.08); c.position.set(0.38 * l, 1.12, 0.05); c.rotation.z = -0.2 * l; g.add(c); });
    return g;
  },
  // Ojos (ancla en la cara, a la altura de los ojos)
  sol() {
    const g = new THREE.Group(), marco = liso("#111827", 0.3, { clearcoat: 1 });
    [-1, 1].forEach((l) => {
      const lente = malla(G.esfera, vidrio("#0b1220", 0.93), [0.33 * l, 0, 0.06], [0.24, 0.19, 0.06]);
      g.add(lente);
      const aro = new THREE.Mesh(new THREE.TorusGeometry(1, 0.12, 8, 40), marco);
      aro.scale.set(0.24, 0.19, 0.24); aro.position.set(0.33 * l, 0, 0.07); g.add(aro);
      const patilla = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.8, 8), marco);
      patilla.position.set(0.6 * l, 0.03, -0.32); patilla.rotation.set(Math.PI / 2, 0, 0.5 * l); g.add(patilla);
    });
    g.add(malla(new THREE.CylinderGeometry(0.02, 0.02, 0.2, 8), marco, [0, 0.05, 0.1], null, [0, 0, Math.PI / 2]));
    return g;
  },
  nerd() {
    const g = new THREE.Group(), marco = liso("#1a1a1a", 0.35);
    [-1, 1].forEach((l) => {
      const aro = new THREE.Mesh(new THREE.TorusGeometry(0.22, 0.035, 12, 40), marco); aro.position.set(0.33 * l, 0, 0.08); g.add(aro);
      g.add(malla(new THREE.CircleGeometry(0.21, 32), vidrio("#dbeafe", 0.18), [0.33 * l, 0, 0.075]));
      const patilla = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.8, 8), marco);
      patilla.position.set(0.58 * l, 0.02, -0.3); patilla.rotation.set(Math.PI / 2, 0, 0.5 * l); g.add(patilla);
    });
    g.add(malla(new THREE.TorusGeometry(0.06, 0.025, 8, 16, Math.PI), marco, [0, 0.02, 0.1]));
    return g;
  },
  lentes3d() {
    const g = new THREE.Group();
    g.add(malla(new THREE.BoxGeometry(1.0, 0.36, 0.05), liso("#ffffff", 0.5), [0, 0, 0.06]));
    g.add(malla(new THREE.PlaneGeometry(0.36, 0.24), vidrio("#ef4444", 0.85), [-0.25, 0, 0.09]));
    g.add(malla(new THREE.PlaneGeometry(0.36, 0.24), vidrio("#06b6d4", 0.85), [0.25, 0, 0.09]));
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
    const anillo = new THREE.Mesh(new THREE.TorusGeometry(0.64, 0.12, 16, 64), m); anillo.rotation.x = Math.PI / 2; anillo.scale.set(1, 1, 0.9); g.add(anillo);
    g.add(malla(new THREE.SphereGeometry(0.06, 12, 8), liso("#18c3df", 0.4), [0, -0.02, 0.66]));
    return g;
  },
  corbatin() {
    const g = grupo([0, -0.02, 0.62]), m = liso("#111827", 0.4, { clearcoat: 0.6 });
    [-1, 1].forEach((l) => g.add(malla(new THREE.ConeGeometry(0.13, 0.26, 24), m, [0.13 * l, 0, 0], [1, 1, 0.5], [0, 0, Math.PI / 2 * l])));
    g.add(malla(G.esferaB, liso("#374151", 0.4), [0, 0, 0.02], 0.06));
    const r = new THREE.Group(); r.add(g); return r;
  },
  corbata() {
    const g = new THREE.Group(), m = liso("#2563eb", 0.45, { clearcoat: 0.4 });
    const s = new THREE.Shape(); s.moveTo(-0.05, 0); s.lineTo(0.05, 0); s.lineTo(0.12, -0.5); s.lineTo(0, -0.64); s.lineTo(-0.12, -0.5); s.closePath();
    const geo = new THREE.ExtrudeGeometry(s, { depth: 0.03, bevelEnabled: true, bevelSize: 0.012, bevelThickness: 0.012, bevelSegments: 2 });
    const tie = new THREE.Mesh(geo, m); tie.position.set(0, -0.06, 0.62); tie.rotation.x = -0.32; g.add(tie);
    g.add(malla(G.esferaB, liso("#1d4ed8", 0.45), [0, -0.04, 0.64], [0.07, 0.06, 0.05]));
    return g;
  },
  medalla() {
    const g = new THREE.Group(), cinta = tela("#2563eb");
    [-1, 1].forEach((l) => { const c = malla(new THREE.BoxGeometry(0.08, 0.5, 0.02), cinta, [0.13 * l, -0.18, 0.62], null, [-0.3, 0, 0.45 * l]); g.add(c); });
    const disco = malla(new THREE.CylinderGeometry(0.14, 0.14, 0.04, 40), metal("#f5c542", 0.2), [0, -0.46, 0.66], null, [Math.PI / 2 - 0.3, 0, 0]);
    g.add(disco);
    return g;
  },
  panuelo() {
    const g = new THREE.Group();
    const geo = new THREE.ConeGeometry(0.45, 0.6, 3, 1); const m = tela("#ef4444");
    const t = malla(geo, m, [0, -0.2, 0.55], [1, 1, 0.35], [Math.PI, 0, 0]); t.rotation.x = Math.PI - 0.3; g.add(t);
    const anillo = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.06, 10, 48), m); anillo.rotation.x = Math.PI / 2; g.add(anillo);
    return g;
  },
  cuello_capa() {
    const g = new THREE.Group(), m = tela("#3b0764");
    [-1, 1].forEach((l) => g.add(malla(new THREE.ConeGeometry(0.28, 0.5, 3), m, [0.32 * l, -0.05, 0.45], [1, 1, 0.3], [Math.PI / 2 + 0.6, 0, 0.9 * l])));
    g.add(malla(G.esferaB, liso("#f97316", 0.3, { clearcoat: 1 }), [0, -0.02, 0.62], 0.07));
    // Capa: media falda detrás del cuerpo (solo la espalda), sin tapar el frente.
    const mCapa = tela("#2e1065"); mCapa.side = THREE.DoubleSide;
    const capa = new THREE.Mesh(new THREE.CylinderGeometry(0.66, 0.98, 1.05, 40, 1, true, Math.PI / 2 + 0.25, Math.PI - 0.5), mCapa);
    capa.position.set(0, -0.5, -0.04); g.add(capa);
    return g;
  },
  collar_corazon() {
    const g = new THREE.Group();
    const cadena = new THREE.Mesh(new THREE.TorusGeometry(0.64, 0.015, 8, 64), metal("#fbcfe8", 0.3)); cadena.rotation.x = Math.PI / 2 - 0.25; g.add(cadena);
    const c = corazon("#e11d48", 0.17, 0.06); c.position.set(0, -0.2, 0.64); g.add(c);
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
    const g = new THREE.Group();
    const hilo = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0, 0), new THREE.Vector3(-0.05, 0.3, 0), new THREE.Vector3(0.02, 0.6, 0)]), 16, 0.006, 6), liso("#64748b", 0.6));
    g.add(hilo);
    const c = corazon("#f43f5e", 0.3, 0.12); c.position.y = 0.82; g.add(c);
    g.userData.globo = c;
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
function bufanda(m1, m2) {
  const g = new THREE.Group();
  const anillo = new THREE.Mesh(new THREE.TorusGeometry(0.64, 0.16, 16, 64), m1);
  anillo.rotation.x = Math.PI / 2 - 0.1; anillo.scale.set(1, 1, 0.85); g.add(anillo);
  const cola = malla(new THREE.BoxGeometry(0.22, 0.55, 0.08), m2, [0.32, -0.32, 0.56], null, [-0.25, 0.1, 0.15]);
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
      const clave = ropaActual[parte];
      if (clave && ROPA[clave]) ancla.add(ROPA[clave]());
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
    pj.ojos.forEach((o) => { o.userData.pupila.position.x = mirar.x * 0.06; o.userData.pupila.position.y = -0.01 - mirar.y * 0.05; });

    // Parpadeo
    if (ahora > proxParpadeo) { parpadeo0 = ahora; proxParpadeo = ahora + 2500 + Math.random() * 3500; }
    const fp = (ahora - parpadeo0) / 160;
    const cierre = fp >= 0 && fp <= 1 ? Math.sin(fp * Math.PI) : 0;
    pj.parpados.forEach((p) => { p.scale.y = Math.max(0.0001, cierre * 0.22); });

    // Saludo de vez en cuando
    if (!reaccion && ahora > proxSaludo) { reaccion = { nombre: "saludo", t0: t, suave: true }; proxSaludo = ahora + 9000 + Math.random() * 7000; }

    // Boca normal
    pj.bocaAbierta.scale.y = 0.0001; pj.sonrisa.visible = true;
    pj.ojos.forEach((o) => o.scale.set(1, 1, 1));

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
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 1.6) * b.userData.lado; });
            break;
          }
          case "giro": pj.raiz.rotation.y = THREE.MathUtils.smootherstep(k, 0, 1) * TAU; pj.raiz.position.y = e * 0.25; break;
          case "baile":
            pj.raiz.rotation.z = Math.sin(k * TAU * 3) * 0.18; pj.raiz.position.y = Math.abs(Math.sin(k * TAU * 3)) * 0.15;
            pj.brazos.forEach((b) => { b.rotation.z = (1.2 + Math.sin(k * TAU * 3 + b.userData.lado) * 0.8) * b.userData.lado; });
            pj.cuello.rotation.z = Math.sin(k * TAU * 3) * 0.2; break;
          case "saludo": {
            const b = pj.brazos[0];
            b.rotation.z = -(2.5 + Math.sin(k * TAU * 3) * 0.35) * (reaccion.suave ? THREE.MathUtils.smoothstep(e, 0, 0.35) : 1);
            b.rotation.x = -0.2;
            break;
          }
          case "sorpresa":
            pj.ojos.forEach((o) => o.scale.setScalar(1 + e * 0.45)); pj.raiz.position.y = e * 0.15;
            pj.bocaAbierta.scale.set(0.8, 0.9 * e, 1); pj.sonrisa.visible = false;
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 1.0) * b.userData.lado; }); break;
          case "risa":
            pj.raiz.rotation.z = Math.sin(k * TAU * 7) * 0.08 * e; pj.cuello.rotation.x = -0.2 * e;
            pj.bocaAbierta.scale.set(1, 1.1 * e, 1); pj.sonrisa.visible = false;
            pj.parpados.forEach((p) => { p.scale.y = 0.14 * e; }); break;
          case "mareo":
            pj.cabeza.rotation.z += Math.sin(k * TAU * 2.5) * 0.35 * e; pj.cabeza.rotation.x += Math.cos(k * TAU * 2.5) * 0.15 * e;
            pj.raiz.rotation.z = Math.sin(k * TAU * 1.5) * 0.12 * e;
            pj.ojos.forEach((o) => { o.userData.pupila.position.x = Math.cos(k * TAU * 4) * 0.05; o.userData.pupila.position.y = Math.sin(k * TAU * 4) * 0.05; }); break;
          case "corazones":
            pj.parpados.forEach((p) => { p.scale.y = 0.12 * e; }); pj.cuello.rotation.z = Math.sin(k * TAU) * 0.15;
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 0.5) * b.userData.lado; b.rotation.x = -0.9 * e; }); break;
          case "confeti":
          case "celebrar":
            pj.raiz.position.y = Math.abs(Math.sin(k * TAU * 2)) * 0.35;
            pj.brazos.forEach((b) => { b.rotation.z = (0.45 + e * 2.3) * b.userData.lado; });
            pj.bocaAbierta.scale.set(0.9, 0.8 * e, 1); pj.sonrisa.visible = false; break;
        }
      }
    }

    // Bandera y globo se mueven con el aire
    const mano = pj.anclas.mano.children[0];
    if (mano && mano.userData.bandera) mano.userData.bandera.rotation.y = Math.sin(t * 3) * 0.25;
    if (mano && mano.userData.globo) mano.userData.globo.rotation.z = Math.sin(t * 1.5) * 0.15;

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
