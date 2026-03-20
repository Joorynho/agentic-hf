'use strict';

// Shared state (accessible from motion.js and dashboard.js)
var pods = {};
var navHistory = [];
var riskAlerts = [];
var executedTrades = [];
var governanceDecisions = [];
var navChart = null;
var iterCount = 0;
var researchSignals = [];
var researchPolyConf = 0.5;
var researchMacroScore = null;
var researchMomentum = null;
var researchHistoryChart = null;
var researchFredSnapshot = {};
var researchFredScore = 0;
var researchPolySentiment = 0;
var researchSocialScore = 0;
var researchXFeed = [];
var researchXTweetCount = 0;
var newsLastRefresh = null;
var newsLastRefresh = null;
var agentActivity = {};
var activityFeed = [];
var _symbolAlerts = {};  // symbol -> [{headline, sentiment, ts, pod_id}]
var podNavSpark = {};
var ddChart = null;
var initialCapital = 0;
var pnlHistory = [];
var chartTimeframeMinutes = 0;
var orderBook = {};
var podPnlHistory = {};
var execFilter = 'all';
var sessionActive = false;
var currentFloor = 0;
var isScrolling = false;
var scrollTimeout = null;
var hoveredFloor = null;
var lastHoveredFloor = null;
var hoveredPod = null;
var govLightLines = [];

const MAX_HISTORY = 100;
const FLOOR_H = 3.6;
const FLOOR_W = 13;
const FLOOR_D = 7;
const SLAB_T = 0.08;

const TIMING = {
  HOVER_IN: 0.16,
  HOVER_OUT: 0.14,
  BUTTON: 0.14,
  PANEL_SWITCH: 0.28,
  KPI_PULSE: 0.20,
  DRAWER: 0.30,
  FLOOR_FOCUS: 0.78,
  DRILL_IN: 0.95,
  RETURN_OVERVIEW: 0.82,
  CROSS_FLOOR: 0.70,
};
const EASE = {
  HOVER: 'power2.out',
  PANEL: 'power2.inOut',
  CAMERA: 'power3.inOut',
};

const canvas = document.getElementById('viewport');
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x1a2332, 0.003);
scene.background = new THREE.Color(0x1a2332);

const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 300);
camera.position.set(0, 7, 30);
camera.lookAt(0, 4, 0);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

function onResize() {
  const lp = document.getElementById('left-panel');
  const w = lp.clientWidth, h = lp.clientHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', onResize);
onResize();

scene.add(new THREE.AmbientLight(0x0a1520, 2.2));

const sun = new THREE.DirectionalLight(0xd0e8ff, 0.8);
sun.position.set(10, 24, 14);
sun.castShadow = true;
sun.shadow.mapSize.width = sun.shadow.mapSize.height = 1024;
scene.add(sun);

const fill = new THREE.DirectionalLight(0x002244, 0.5);
fill.position.set(-6, -4, 18);
scene.add(fill);

const FLOORS = [
  { id:'equities',   name:'EQUITIES',   y: -9, accent:0x00c888, hex:'#00c888', label:'STOCKS · ETFs · SECTORS', screens:3 },
  { id:'fx',         name:'FX',         y: -4, accent:0x00cfe8, hex:'#00cfe8', label:'CURRENCIES · PAIRS',      screens:3 },
  { id:'crypto',     name:'CRYPTO',     y:  1, accent:0x7c5cfc, hex:'#7c5cfc', label:'BTC · ETH · ALTS',        screens:2 },
  { id:'commodities',name:'COMMODITIES', y:  6, accent:0xf0a030, hex:'#f0a030', label:'GOLD · OIL · INFLATION',  screens:2 },
  { id:'governance', name:'GOVERNANCE', y: 11, accent:0xd0e4f0, hex:'#d0e4f0', label:'APPROVALS · AUDIT · CTRL', screens:2 },
];

const matSlab = new THREE.MeshStandardMaterial({ color:0x1e2d3d, metalness:0, roughness:0.9 });
const matWall = new THREE.MeshStandardMaterial({ color:0x2c3e50, metalness:0, roughness:0.92 });
const matCol  = new THREE.MeshStandardMaterial({ color:0x253545, metalness:0, roughness:0.88 });
const matDesk = new THREE.MeshStandardMaterial({ color:0x384858, metalness:0.1, roughness:0.8 });
const matFurn = new THREE.MeshStandardMaterial({ color:0x2e3e4e, metalness:0.05, roughness:0.85 });
const matGlass = new THREE.MeshStandardMaterial({
  color: 0x4a6a8a, transparent: true, opacity: 0.12,
  roughness: 0.0, metalness: 0.9, side: THREE.DoubleSide,
});

const podStatusMaterials = {
  ACTIVE: new THREE.MeshStandardMaterial({
    color: 0x00c888, metalness: 0.7, roughness: 0.3,
    emissive: 0x003322, emissiveIntensity: 0.2,
  }),
  HALTED: new THREE.MeshStandardMaterial({
    color: 0xf0a030, metalness: 0.7, roughness: 0.3,
    emissive: 0x664400, emissiveIntensity: 0.15,
  }),
  IDLE: new THREE.MeshStandardMaterial({
    color: 0x555555, metalness: 0.7, roughness: 0.3,
    emissive: 0x222222, emissiveIntensity: 0.1,
  }),
};

const podFloorMap = {
  equities: 0,
  fx: 1,
  crypto: 2,
  commodities: 3,
};

const podStrategyNames = {
  equities: ['EQUITIES', 'Stocks / ETFs'],
  fx: ['FX', 'Currencies'],
  crypto: ['CRYPTO', 'Digital Assets'],
  commodities: ['COMMODITIES', 'Macro'],
};

const podAgentRoles = {
  equities: ['Trader', 'Ops', 'PM', 'Researcher', 'Risk', 'Signal'],
  fx: ['Trader', 'Ops', 'PM', 'Researcher', 'Risk', 'Signal'],
  crypto: ['Trader', 'Ops', 'PM', 'Researcher', 'Risk', 'Signal'],
  commodities: ['Trader', 'Ops', 'PM', 'Researcher', 'Risk', 'Signal'],
};

const govAgents = [
  { id: 'CEO', label: ['CEO', 'Strategy'], accent: '#00cfe8' },
  { id: 'CIO', label: ['CIO', 'Allocation'], accent: '#00c888' },
  { id: 'CRO', label: ['CRO', 'Risk Ctrl'], accent: '#f0a030' },
];

const floorAnimState = {};

const cameraTweenState = { baseY: 7, baseZ: 30, lookY: 4 };

// ================================================================
//  STAGING BLUEPRINTS — updated Z to avoid furniture clipping
//  Desk zone ~ z=-0.2, so seated agents at z=-0.8 (behind desk)
// ================================================================

const TRADING_FLOOR_STAGING = [
  { role:'Trader',     x: -2.2,  z: -0.8,  rotY: Math.PI,        posture: 'seated' },
  { role:'Ops',        x:  2.0,  z: -0.8,  rotY: Math.PI,        posture: 'seated' },
  { role:'PM',         x:  0.0,  z:  1.8,  rotY: Math.PI * 0.92, posture: 'observing' },
  { role:'Researcher', x: -4.8,  z: -1.6,  rotY: Math.PI * 0.7,  posture: 'leaning' },
  { role:'Risk',       x:  4.6,  z:  1.0,  rotY: Math.PI * 1.2,  posture: 'standing' },
  { role:'Signal',     x: -0.4,  z: -1.0,  rotY: Math.PI * 0.95, posture: 'seated' },
];

const GOVERNANCE_STAGING = [
  { id:'CEO', x:  0.0, z:  1.4,  rotY: Math.PI * 0.95, posture: 'standing' },
  { id:'CIO', x: -2.8, z:  0.3,  rotY: Math.PI * 0.8,  posture: 'conversing' },
  { id:'CRO', x:  3.0, z: -0.2,  rotY: Math.PI * 1.15, posture: 'observing' },
];

// ================================================================
//  FLOOR WALL TINTING
// ================================================================

function tintWallMaterial(accentHex) {
  const base = new THREE.Color(0x2c3e50);
  const accent = new THREE.Color(accentHex);
  base.lerp(accent, 0.15);
  return new THREE.MeshStandardMaterial({ color: base, metalness: 0, roughness: 0.92 });
}

// ================================================================
//  FURNITURE HELPER FUNCTIONS
// ================================================================

function nrc(m) { m.raycast = function() {}; return m; }

function addDesk(g, x, y, z, w, d, mat) {
  const top = nrc(new THREE.Mesh(new THREE.BoxGeometry(w, 0.05, d), mat.clone()));
  top.position.set(x, y, z);
  top.castShadow = true;
  g.add(top);
  const legH = y - 0.025;
  const legGeo = new THREE.BoxGeometry(0.06, legH, 0.06);
  [[-w/2+0.08, -d/2+0.08], [w/2-0.08, -d/2+0.08], [-w/2+0.08, d/2-0.08], [w/2-0.08, d/2-0.08]].forEach(([lx,lz]) => {
    const leg = nrc(new THREE.Mesh(legGeo, mat.clone()));
    leg.position.set(x+lx, legH/2, z+lz);
    g.add(leg);
  });
}

function addChair(g, x, z, rotY, mat) {
  const seat = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.04, 0.28), mat.clone()));
  seat.position.set(x, 0.42, z);
  g.add(seat);
  const back = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.32, 0.04), mat.clone()));
  back.position.set(x, 0.60, z - 0.12);
  back.rotation.y = rotY || 0;
  g.add(back);
}

function addMonitorBank(g, x, y, z, count, acc) {
  const mw = 0.32, mh = 0.22, gap = 0.04;
  const totalW = count * mw + (count-1) * gap;
  const monMat = new THREE.MeshStandardMaterial({
    color: 0x060d13, emissive: new THREE.Color(acc), emissiveIntensity: 0.35,
  });
  for (let i = 0; i < count; i++) {
    const mx = x - totalW/2 + mw/2 + i * (mw + gap);
    const mon = nrc(new THREE.Mesh(new THREE.BoxGeometry(mw, mh, 0.03), monMat.clone()));
    mon.position.set(mx, y, z);
    g.add(mon);
  }
}

function addPartition(g, x, z, height, width) {
  const pane = nrc(new THREE.Mesh(
    new THREE.BoxGeometry(width, height, 0.03), matGlass.clone()
  ));
  pane.position.set(x, height/2, z);
  g.add(pane);
}

function addRailing(g, x1, x2, z, y) {
  const w = Math.abs(x2 - x1);
  const rail = nrc(new THREE.Mesh(
    new THREE.BoxGeometry(w, 0.04, 0.04), matCol.clone()
  ));
  rail.position.set((x1+x2)/2, y, z);
  g.add(rail);
  const postGeo = new THREE.BoxGeometry(0.04, y, 0.04);
  [x1, x2].forEach(px => {
    const post = nrc(new THREE.Mesh(postGeo, matCol.clone()));
    post.position.set(px, y/2, z);
    g.add(post);
  });
}

function addCabinet(g, x, z, w, d, h, mat) {
  const cab = nrc(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat.clone()));
  cab.position.set(x, h/2, z);
  cab.castShadow = true;
  g.add(cab);
}

function addWallDisplay(g, x, y, z, w, h, acc) {
  const dm = new THREE.MeshStandardMaterial({
    color: 0x060d13, emissive: new THREE.Color(acc), emissiveIntensity: 0.4,
  });
  const disp = nrc(new THREE.Mesh(new THREE.BoxGeometry(w, h, 0.03), dm));
  disp.position.set(x, y, z);
  g.add(disp);
  const frameMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color(acc), emissive: new THREE.Color(acc), emissiveIntensity: 0.15,
  });
  const fr = nrc(new THREE.Mesh(new THREE.BoxGeometry(w+0.06, h+0.05, 0.02), frameMat));
  fr.position.set(x, y, z - 0.01);
  g.add(fr);
}

// ================================================================
//  PER-FLOOR FURNITURE BUILDERS
// ================================================================

function buildEquitiesFurniture(g, acc) {
  // L-shaped trading desk: main bank + side wing
  addDesk(g, -1.0, 0.78, -0.2, 5.5, 1.2, matDesk);
  addDesk(g, -4.2, 0.78, -1.0, 1.8, 0.9, matDesk);

  // Monitor banks on desk
  addMonitorBank(g, -2.2, 1.05, -0.4, 3, acc);
  addMonitorBank(g,  2.0, 1.05, -0.4, 3, acc);
  addMonitorBank(g, -4.2, 1.05, -1.2, 2, acc);

  // Standing-height side console at far left
  addDesk(g, -5.2, 1.0, -0.5, 1.0, 0.6, matFurn);
  addMonitorBank(g, -5.2, 1.28, -0.6, 1, acc);

  // Low railing separating front from desk zone
  addRailing(g, -3.5, 3.5, 0.6, 0.65);

  // LED ticker strip along upper rear wall
  const tickerMat = new THREE.MeshStandardMaterial({
    color: 0x000000, emissive: new THREE.Color(acc), emissiveIntensity: 0.55,
  });
  const ticker = nrc(new THREE.Mesh(new THREE.BoxGeometry(FLOOR_W - 1.0, 0.12, 0.03), tickerMat));
  ticker.position.set(0, FLOOR_H * 0.88, -(FLOOR_D * 0.5) + 0.12);
  g.add(ticker);

  // Chairs behind desk
  addChair(g, -2.2, -1.1, Math.PI, matFurn);
  addChair(g,  2.0, -1.1, Math.PI, matFurn);
  addChair(g, -0.4, -1.3, Math.PI, matFurn);
}

function buildFxFurniture(g, acc) {
  // V-shaped desk arrangement: two angled segments
  const deskL = nrc(new THREE.Mesh(new THREE.BoxGeometry(4.0, 0.05, 1.0), matDesk.clone()));
  deskL.position.set(-2.0, 0.78, -0.1);
  deskL.rotation.y = 0.15;
  deskL.castShadow = true;
  g.add(deskL);

  const deskR = nrc(new THREE.Mesh(new THREE.BoxGeometry(4.0, 0.05, 1.0), matDesk.clone()));
  deskR.position.set(2.0, 0.78, -0.1);
  deskR.rotation.y = -0.15;
  deskR.castShadow = true;
  g.add(deskR);

  // Desk legs for V-desks
  [[-3.8, -0.3], [-0.5, 0.1], [0.5, 0.1], [3.8, -0.3]].forEach(([lx, lz]) => {
    const leg = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.75, 0.06), matDesk.clone()));
    leg.position.set(lx, 0.375, lz);
    g.add(leg);
  });

  // Dual-monitor pairs at each desk position
  addMonitorBank(g, -2.2, 1.05, -0.3, 2, acc);
  addMonitorBank(g,  2.0, 1.05, -0.3, 2, acc);
  addMonitorBank(g, -0.4, 1.05, -0.2, 2, acc);

  // World clock panel: 3 small emissive squares above rear screens
  [-3.0, 0.0, 3.0].forEach(wx => {
    addWallDisplay(g, wx, FLOOR_H * 0.88, -(FLOOR_D*0.5) + 0.12, 0.6, 0.4, acc);
  });

  // Glass partition between desk clusters
  addPartition(g, 0, -0.1, 1.8, 0.04);

  // Side cabinet at right wall
  addCabinet(g, FLOOR_W * 0.5 - 0.5, -1.5, 1.6, 0.5, 0.7, matFurn);

  // Chairs
  addChair(g, -2.2, -1.1, Math.PI, matFurn);
  addChair(g,  2.0, -1.1, Math.PI, matFurn);
  addChair(g, -0.4, -1.3, Math.PI, matFurn);
}

function buildCryptoFurniture(g, acc) {
  // U-shaped desk: center + two wings
  addDesk(g, 0, 0.78, -0.2, 4.5, 1.0, matDesk);
  addDesk(g, -3.0, 0.78, -0.8, 1.2, 1.8, matDesk);
  addDesk(g,  3.0, 0.78, -0.8, 1.2, 1.8, matDesk);

  // Monitor banks on U-desk
  addMonitorBank(g, -1.5, 1.05, -0.4, 2, acc);
  addMonitorBank(g,  1.5, 1.05, -0.4, 2, acc);

  // Tall standing desk at far right for Risk agent
  addDesk(g, 4.8, 1.0, 0.8, 1.0, 0.6, matFurn);
  addMonitorBank(g, 4.8, 1.28, 0.7, 1, acc);

  // Server rack against left wall
  const rackMat = matCol.clone();
  const rack = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.5, 2.2, 0.8), rackMat));
  rack.position.set(-FLOOR_W * 0.5 + 0.55, 1.1, -1.5);
  rack.castShadow = true;
  g.add(rack);
  // Emissive LED strips on rack
  [0.4, 0.8, 1.2, 1.6, 2.0].forEach(ry => {
    const led = nrc(new THREE.Mesh(
      new THREE.BoxGeometry(0.4, 0.04, 0.02),
      new THREE.MeshStandardMaterial({ color: 0x000000, emissive: new THREE.Color(acc), emissiveIntensity: 0.5 })
    ));
    led.position.set(-FLOOR_W * 0.5 + 0.55, ry, -1.1);
    g.add(led);
  });

  // Extra display on left side wall
  addWallDisplay(g, -FLOOR_W * 0.5 + 0.12, FLOOR_H * 0.55, -0.5, 0.03, 1.0, acc);

  // Low coffee table in foreground
  addDesk(g, 1.5, 0.4, 1.5, 0.9, 0.5, matFurn);

  // Chairs
  addChair(g, -1.5, -1.1, Math.PI, matFurn);
  addChair(g,  1.5, -1.1, Math.PI, matFurn);
}

function buildCommoditiesFurniture(g, acc) {
  // Standard desk bank
  addDesk(g, -1.0, 0.78, -0.2, 5.0, 1.0, matDesk);

  // Monitor banks
  addMonitorBank(g, -2.2, 1.05, -0.4, 2, acc);
  addMonitorBank(g,  0.8, 1.05, -0.4, 2, acc);

  // Meeting table (round — approximated with flattened cylinder)
  const tableMat = matDesk.clone();
  const table = nrc(new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.7, 0.05, 16), tableMat));
  table.position.set(3.8, 0.72, 1.0);
  table.castShadow = true;
  g.add(table);
  const tableLeg = nrc(new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.7, 6), matCol.clone()));
  tableLeg.position.set(3.8, 0.35, 1.0);
  g.add(tableLeg);

  // Two chairs at meeting table
  addChair(g, 3.2, 1.0, Math.PI * 0.5, matFurn);
  addChair(g, 4.4, 1.0, -Math.PI * 0.5, matFurn);

  // Bookshelf / data panel against right wall
  const shelfBack = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.4, 1.8), matFurn.clone()));
  shelfBack.position.set(FLOOR_W * 0.5 - 0.34, 1.2, -1.2);
  shelfBack.castShadow = true;
  g.add(shelfBack);
  [0.4, 0.85, 1.3, 1.75, 2.2].forEach(sy => {
    const shelf = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.03, 1.7), matDesk.clone()));
    shelf.position.set(FLOOR_W * 0.5 - 0.42, sy, -1.2);
    g.add(shelf);
  });

  // Map/chart board on left side wall
  addWallDisplay(g, -FLOOR_W * 0.5 + 0.12, FLOOR_H * 0.5, -0.8, 0.03, 1.4, acc);

  // Desk lamp: cylinder + sphere on desk edge
  const lampPost = nrc(new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.3, 6), matCol.clone()));
  lampPost.position.set(-3.0, 0.95, -0.2);
  g.add(lampPost);
  const lampHead = nrc(new THREE.Mesh(
    new THREE.SphereGeometry(0.06, 8, 6),
    new THREE.MeshStandardMaterial({ color: 0xffe8c0, emissive: 0xffe8c0, emissiveIntensity: 0.6 })
  ));
  lampHead.position.set(-3.0, 1.12, -0.2);
  g.add(lampHead);

  // Chairs behind desk
  addChair(g, -2.2, -1.1, Math.PI, matFurn);
  addChair(g,  0.8, -1.1, Math.PI, matFurn);
}

function buildGovernanceFurniture(g, acc) {
  // Formal conference table
  const confTable = nrc(new THREE.Mesh(new THREE.BoxGeometry(5.0, 0.06, 1.4), matDesk.clone()));
  confTable.position.set(0, 0.72, 0.5);
  confTable.castShadow = true;
  g.add(confTable);
  // Table legs
  [[-2.2, 0.0], [2.2, 0.0], [-2.2, 1.0], [2.2, 1.0]].forEach(([lx, lz]) => {
    const leg = nrc(new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.7, 0.08), matCol.clone()));
    leg.position.set(lx, 0.35, lz);
    g.add(leg);
  });

  // 3 executive chairs behind table
  addChair(g, -1.5, -0.3, Math.PI, matFurn);
  addChair(g,  0.0, -0.3, Math.PI, matFurn);
  addChair(g,  1.5, -0.3, Math.PI, matFurn);

  // Glass partitions creating boardroom feel
  addPartition(g, -4.0, 0.5, 2.4, 0.04);
  addPartition(g,  4.0, 0.5, 2.4, 0.04);

  // Presentation screen on rear wall (compact, above table sightline)
  addWallDisplay(g, 0, FLOOR_H * 0.6, -(FLOOR_D * 0.5) + 0.12, 2.4, 0.9, acc);

  // Low credenza along rear wall sides
  addCabinet(g, -4.5, -(FLOOR_D * 0.5) + 0.5, 2.0, 0.5, 0.6, matFurn);
  addCabinet(g,  4.5, -(FLOOR_D * 0.5) + 0.5, 2.0, 0.5, 0.6, matFurn);

  // Front railing
  addRailing(g, -3.5, 3.5, 2.2, 0.65);
}

// ================================================================
//  AGENT MESH BUILDER
//  Children: [0]=head, [1]=neck, [2]=torso, [3]=shoulders,
//            [4]=hips, [5]=legL, [6]=legR, [7]=armL, [8]=armR,
//            [9]=accentStripe
// ================================================================

function createAgentMesh(accentColor, role, posture) {
  const group = new THREE.Group();

  const isExec = (role === 'PM' || role === 'CEO');
  const isAnalyst = (role === 'Researcher' || role === 'Signal');
  const isRisk = (role === 'Risk' || role === 'CRO');
  const isSeated = (posture === 'seated');

  const heightScale = isExec ? 1.06 : isRisk ? 1.02 : 1.0;
  const shoulderW = isExec ? 0.22 : isAnalyst ? 0.17 : 0.19;

  const accentC = new THREE.Color(accentColor);
  const bodyColor = accentC.clone().multiplyScalar(0.7);
  const headColor = accentC.clone().multiplyScalar(0.85);

  const bodyMat = new THREE.MeshStandardMaterial({
    color: bodyColor, metalness: 0.15, roughness: 0.65,
    emissive: accentC.clone(), emissiveIntensity: 0.12,
  });
  const headMat = new THREE.MeshStandardMaterial({
    color: headColor, metalness: 0.1, roughness: 0.7,
    emissive: accentC.clone(), emissiveIntensity: 0.08,
  });
  const accentMat = new THREE.MeshStandardMaterial({
    color: accentC.clone(), metalness: 0.3, roughness: 0.4,
    emissive: accentC.clone(), emissiveIntensity: 0.35,
  });

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.11, 14, 10), headMat);
  head.position.y = 1.12 * heightScale;
  head.castShadow = true;
  group.add(head);

  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.08, 8), bodyMat.clone());
  neck.position.y = 1.0 * heightScale;
  neck.castShadow = true;
  group.add(neck);

  const torsoH = 0.48 * heightScale;
  const torso = new THREE.Mesh(new THREE.BoxGeometry(shoulderW * 1.6, torsoH, 0.14), bodyMat.clone());
  torso.position.y = 0.72 * heightScale;
  torso.castShadow = true;
  group.add(torso);

  const shoulderGeo = new THREE.BoxGeometry(shoulderW * 2.1, 0.06, 0.15);
  const shoulders = new THREE.Mesh(shoulderGeo, bodyMat.clone());
  shoulders.position.y = 0.94 * heightScale;
  shoulders.castShadow = true;
  group.add(shoulders);

  const hips = new THREE.Mesh(new THREE.BoxGeometry(shoulderW * 1.2, 0.1, 0.12), bodyMat.clone());
  hips.position.y = 0.44 * heightScale;
  group.add(hips);

  const legGeo = new THREE.CylinderGeometry(0.04, 0.035, 0.42 * heightScale, 6);
  const legL = new THREE.Mesh(legGeo, bodyMat.clone());
  legL.position.set(-0.055, 0.21 * heightScale, 0);
  legL.castShadow = true;
  legL.visible = !isSeated;
  group.add(legL);

  const legR = new THREE.Mesh(legGeo, bodyMat.clone());
  legR.position.set(0.055, 0.21 * heightScale, 0);
  legR.castShadow = true;
  legR.visible = !isSeated;
  group.add(legR);

  const armGeo = new THREE.CylinderGeometry(0.03, 0.025, 0.38 * heightScale, 6);

  const armL = new THREE.Mesh(armGeo, bodyMat.clone());
  armL.position.set(-shoulderW * 1.05, 0.72 * heightScale, 0);
  armL.castShadow = true;
  group.add(armL);

  const armR = new THREE.Mesh(armGeo, bodyMat.clone());
  armR.position.set(shoulderW * 1.05, 0.72 * heightScale, 0);
  armR.castShadow = true;
  group.add(armR);

  if (posture === 'seated') {
    armL.rotation.x = -Math.PI / 4;
    armR.rotation.x = -Math.PI / 4;
    armL.rotation.z = Math.PI / 20;
    armR.rotation.z = -Math.PI / 20;
    armL.position.y = 0.62 * heightScale;
    armR.position.y = 0.62 * heightScale;
    armL.position.z = -0.08;
    armR.position.z = -0.08;
    group.userData._seatDrop = 0.12;
  } else if (posture === 'leaning') {
    armL.rotation.x = -Math.PI / 3;
    armL.rotation.z = Math.PI / 16;
    armR.rotation.z = -Math.PI / 24;
    torso.rotation.x = -0.08;
  } else if (posture === 'observing') {
    armL.rotation.z = Math.PI / 24;
    armR.rotation.z = -Math.PI / 24;
  } else if (posture === 'conversing') {
    armL.rotation.z = Math.PI / 14;
    armR.rotation.z = -Math.PI / 20;
    armR.rotation.x = -0.15;
  } else {
    armL.rotation.z = Math.PI / 22;
    armR.rotation.z = -Math.PI / 22;
  }

  const stripe = new THREE.Mesh(new THREE.BoxGeometry(shoulderW * 2.0, 0.018, 0.16), accentMat);
  stripe.position.y = 0.96 * heightScale;
  group.add(stripe);

  return group;
}

// ================================================================
//  AGENT LABEL
// ================================================================

function createAgentLabel(lines, accentColor) {
  const cvs = document.createElement('canvas');
  cvs.width = 256; cvs.height = 128;
  const ctx = cvs.getContext('2d');
  ctx.clearRect(0, 0, 256, 128);

  ctx.fillStyle = 'rgba(30,41,64,0.85)';
  roundRect(ctx, 12, 10, 232, 108, 8);
  ctx.fill();

  ctx.strokeStyle = accentColor;
  ctx.lineWidth = 1.5;
  roundRect(ctx, 12, 10, 232, 108, 8);
  ctx.stroke();

  ctx.fillStyle = '#f0f4fa';
  ctx.font = 'bold 30px monospace';
  ctx.textAlign = 'center';
  ctx.fillText(lines[0], 128, 52);

  ctx.font = '24px monospace';
  ctx.fillStyle = accentColor;
  ctx.fillText(lines[1] || '', 128, 86);

  const texture = new THREE.CanvasTexture(cvs);
  const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(0.7, 0.35, 1);
  sprite.position.y = 1.25;
  sprite.visible = true;
  return sprite;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// ================================================================
//  BUILD FLOOR
// ================================================================

function buildFloor(fd, idx) {
  const g = new THREE.Group();
  g.userData = { floorIndex: idx };
  const acc = fd.accent;
  const screenMats = [];

  const floorWallMat = tintWallMaterial(acc);

  // Slab
  const slab = new THREE.Mesh(new THREE.BoxGeometry(FLOOR_W, SLAB_T, FLOOR_D + 0.4), matSlab.clone());
  slab.receiveShadow = true;
  g.add(slab);

  // Emissive trim strip
  const trimMat = new THREE.MeshStandardMaterial({
    color: 0x000000, emissive: new THREE.Color(acc), emissiveIntensity: 0.45,
  });
  const trim = new THREE.Mesh(new THREE.BoxGeometry(FLOOR_W + 0.08, 0.045, FLOOR_D + 0.5), trimMat);
  trim.position.y = -(SLAB_T * 0.5 + 0.015);
  g.add(trim);

  // Rear wall
  const rear = new THREE.Mesh(new THREE.BoxGeometry(FLOOR_W, FLOOR_H, 0.1), floorWallMat.clone());
  rear.position.set(0, FLOOR_H * 0.5, -(FLOOR_D * 0.5));
  rear.castShadow = rear.receiveShadow = true;
  g.add(rear);

  // Side walls
  const sideGeo = new THREE.BoxGeometry(0.1, FLOOR_H, FLOOR_D);
  [-FLOOR_W * 0.5, FLOOR_W * 0.5].forEach(x => {
    const s = new THREE.Mesh(sideGeo, floorWallMat.clone());
    s.position.set(x, FLOOR_H * 0.5, 0);
    g.add(s);
  });

  // Columns
  const colGeo = new THREE.BoxGeometry(0.22, FLOOR_H, 0.22);
  [[-FLOOR_W*0.5+0.28, -FLOOR_D*0.47],
   [ FLOOR_W*0.5-0.28, -FLOOR_D*0.47],
   [-FLOOR_W*0.5+0.28,  FLOOR_D*0.22],
   [ FLOOR_W*0.5-0.28,  FLOOR_D*0.22]].forEach(([cx, cz]) => {
    const c = new THREE.Mesh(colGeo, matCol.clone());
    c.position.set(cx, FLOOR_H * 0.5, cz);
    c.castShadow = true;
    c.raycast = function() {};
    g.add(c);
  });

  // Glass front panel
  const frontGlass = new THREE.Mesh(
    new THREE.BoxGeometry(FLOOR_W - 0.35, FLOOR_H - 0.08, 0.04),
    new THREE.MeshStandardMaterial({
      color: 0x1a3852, transparent: true, opacity: 0.06,
      roughness: 0.0, metalness: 0.96, side: THREE.DoubleSide,
    })
  );
  frontGlass.position.set(0, FLOOR_H * 0.5, FLOOR_D * 0.5);
  frontGlass.raycast = function() {};
  g.add(frontGlass);

  // Rear wall screens (shared across all floors)
  const sw = 2.15, sh = 1.22;
  const ncols = fd.screens;
  const spacing = (FLOOR_W - 1.5) / ncols;
  for (let s = 0; s < ncols; s++) {
    const sm = new THREE.MeshStandardMaterial({
      color: 0x010508, emissive: new THREE.Color(acc), emissiveIntensity: 0.65,
    });
    screenMats.push(sm);
    const screen = new THREE.Mesh(new THREE.BoxGeometry(sw, sh, 0.03), sm);
    const sx = -FLOOR_W * 0.5 + 0.75 + spacing * (s + 0.5);
    screen.position.set(sx, FLOOR_H * 0.65, -(FLOOR_D * 0.5) + 0.12);
    g.add(screen);
    const frameMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(acc), emissive: new THREE.Color(acc), emissiveIntensity: 0.2,
    });
    const fr = new THREE.Mesh(new THREE.BoxGeometry(sw + 0.09, sh + 0.07, 0.02), frameMat);
    fr.position.copy(screen.position);
    fr.position.z -= 0.01;
    g.add(fr);
  }

  // Per-floor point light
  const pt = new THREE.PointLight(acc, 1.8, 12, 2.0);
  pt.position.set(0, FLOOR_H * 0.65, 0);
  g.add(pt);

  // Rim accent light
  const rimLight = new THREE.PointLight(acc, 0.6, 6.0, 2.0);
  rimLight.position.set(0, 0.2, FLOOR_D * 0.45);
  g.add(rimLight);

  // Overhead spot
  const overheadSpot = new THREE.SpotLight(0xd0e8ff, 0.5, 6, Math.PI / 4, 0.6, 1.5);
  overheadSpot.position.set(0, FLOOR_H * 0.95, -0.2);
  overheadSpot.target.position.set(0, 0, -0.2);
  overheadSpot.castShadow = true;
  overheadSpot.shadow.mapSize.width = overheadSpot.shadow.mapSize.height = 512;
  g.add(overheadSpot);
  g.add(overheadSpot.target);

  // ---- PER-FLOOR FURNITURE ----
  if (idx === 0) buildEquitiesFurniture(g, acc);
  else if (idx === 1) buildFxFurniture(g, acc);
  else if (idx === 2) buildCryptoFurniture(g, acc);
  else if (idx === 3) buildCommoditiesFurniture(g, acc);
  else if (idx === 4) buildGovernanceFurniture(g, acc);

  // ---- AGENT STAGING ----
  const podSilhouettes = {};
  const podsOnFloor = Object.entries(podFloorMap)
    .filter(([_, floorIdx]) => floorIdx === idx)
    .map(([podId]) => podId);

  podsOnFloor.forEach((podId) => {
    const roles = podAgentRoles[podId] || [];

    roles.forEach((role, roleIdx) => {
      const staging = TRADING_FLOOR_STAGING[roleIdx] || TRADING_FLOOR_STAGING[0];
      const posture = staging.posture;

      const agent = createAgentMesh(acc, role, posture);

      const seatDrop = agent.userData._seatDrop || 0;
      agent.position.set(staging.x, SLAB_T * 0.5 - seatDrop, staging.z);
      agent.rotation.y = staging.rotY;

      const uniqueId = `${podId}_${roleIdx}`;
      agent.userData = Object.assign(agent.userData || {}, {
        podId: uniqueId, basePodId: podId, floorIndex: idx,
        baseY: SLAB_T * 0.5 - seatDrop, baseZ: staging.z,
        status: 'ACTIVE', role, posture,
        idlePhase: Math.random() * Math.PI * 2,
        headScanFreq: 0.03 + Math.random() * 0.02,
        headScanAmp: 0.08 + Math.random() * 0.06,
        weightShiftFreq: 0.06 + Math.random() * 0.04,
        weightShiftAmp: 0.008 + Math.random() * 0.006,
        typingFreq: 2.5 + Math.random() * 1.0,
        typingAmp: 0.012 + Math.random() * 0.008,
        gestureTimer: 30 + Math.random() * 15,
        gestureCountdown: 30 + Math.random() * 15,
        pauseTimer: 0,
        pauseDuration: 3 + Math.random() * 4,
      });

      const stratInfo = podStrategyNames[podId];
      if (stratInfo) {
        const label = createAgentLabel([stratInfo[0], role], fd.hex);
        agent.add(label);
      }

      const screenProximity = Math.max(0, 1.0 - (staging.z + 2.0) / 4.0);
      agent.children.forEach(child => {
        if (child.isMesh && child.material && child.material.emissiveIntensity !== undefined) {
          child.material.emissiveIntensity = 0.10 + screenProximity * 0.12;
        }
      });

      g.add(agent);
      podSilhouettes[uniqueId] = agent;
    });
  });

  // Governance floor agents
  if (idx === 4) {
    GOVERNANCE_STAGING.forEach((gs, gi) => {
      const ga = govAgents[gi];
      if (!ga) return;
      const posture = gs.posture;

      const agent = createAgentMesh(new THREE.Color(ga.accent).getHex(), ga.id, posture);

      const seatDrop = agent.userData._seatDrop || 0;
      agent.position.set(gs.x, SLAB_T * 0.5 - seatDrop, gs.z);
      agent.rotation.y = gs.rotY;

      agent.userData = Object.assign(agent.userData || {}, {
        podId: ga.id, floorIndex: idx,
        baseY: SLAB_T * 0.5 - seatDrop, baseZ: gs.z,
        isGovAgent: true, posture,
        idlePhase: Math.random() * Math.PI * 2,
        headScanFreq: 0.025 + Math.random() * 0.015,
        headScanAmp: 0.06 + Math.random() * 0.04,
        weightShiftFreq: 0.04 + Math.random() * 0.03,
        weightShiftAmp: 0.006 + Math.random() * 0.004,
        gestureTimer: 35 + Math.random() * 20,
        gestureCountdown: 35 + Math.random() * 20,
        pauseTimer: 0,
        pauseDuration: 4 + Math.random() * 5,
      });

      const label = createAgentLabel(ga.label, ga.accent);
      agent.add(label);
      g.add(agent);
      podSilhouettes[ga.id] = agent;
    });
  }

  floorAnimState[idx] = {
    screens: screenMats,
    trimMat: trimMat,
    pointLight: pt,
    rimLight: rimLight,
    glassMat: frontGlass.material,
    baseEmissive: 0.65,
    baseTrimEmissive: 0.45,
    baseLightInt: 1.8,
    hoverGlowIntensity: 0.65,
    hovering: false,
    floorState: 'idle',
    podSilhouettes: podSilhouettes,
    group: g,
  };

  g.position.y = fd.y + SLAB_T * 0.5;
  return g;
}

// Build all 5 floors
FLOORS.forEach((fd, i) => scene.add(buildFloor(fd, i)));

const extGeo = new THREE.BoxGeometry(FLOOR_W + 0.55, 25, FLOOR_D + 0.55);
const extEdges = new THREE.EdgesGeometry(extGeo);
const extFrame = new THREE.LineSegments(
  extEdges,
  new THREE.LineBasicMaterial({ color: 0x1a3550, transparent: true, opacity: 0.32 })
);
extFrame.position.set(0, 5, 0);
scene.add(extFrame);

const strip = document.getElementById('floor-strip');
const floorToPod = {};
Object.entries(podFloorMap).forEach(([pod, fi]) => { floorToPod[fi] = pod; });

const floorLegendInfo = {
  0: { pod: 'EQUITIES', strat: 'Stocks / ETFs' },
  1: { pod: 'FX', strat: 'Currencies' },
  2: { pod: 'CRYPTO', strat: 'Digital Assets' },
  3: { pod: 'COMMODITIES', strat: 'Macro' },
  4: { pod: 'GOV', strat: 'CEO · CIO · CRO' },
};

FLOORS.forEach((fd, i) => {
  const info = floorLegendInfo[i];
  const el = document.createElement('div');
  el.className = 'fl-item';
  el.innerHTML = `<div class="fl-dot" style="background:${fd.hex};opacity:.7"></div><span class="fl-pod">${info.pod}</span><span class="fl-strat">${info.strat}</span>`;
  strip.appendChild(el);
});
