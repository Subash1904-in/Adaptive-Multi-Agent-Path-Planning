import './style.css';
import { config } from './config.js';
import { Simulation } from './simulation.js';
import { World } from './world.js';

const simulation = new Simulation();
simulation.running = false;
const world = new World(document.querySelector('#viewport'));
let selectedVehicle = 'V1';
let previousFrame = performance.now();
let previousUiUpdate = 0;
let displayedSequenceStage = '';
let displayedSuddenBrakingPair = '';

const element = (selector) => document.querySelector(selector);
element('#start-footnote').textContent = `${config.vehicles.count} connected vehicles · Flyover, underpass, ring-road and U-turn routes · Live planning`;
world.setCamera('overview', {
  x: 0, y: 1.2, z: 0,
  radius: config.rendering.openingOverviewRadiusMeters,
  pitch: config.rendering.sequenceOverviewPitch,
}, 0);
const formatClock = (seconds) => {
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
};

function baselineTrafficFocus() {
  return {
    x: 0,
    y: 1.2,
    z: 0,
    heading: 0,
    radius: config.rendering.sequenceOverviewRadiusMeters,
    pitch: config.rendering.sequenceOverviewPitch,
  };
}

function populateVehicleSelector() {
  const select = element('#vehicle-select');
  select.innerHTML = simulation.agents.map((agent) => (
    `<option value="${agent.id}">${agent.id} · ${agent.type === 'Ambulance' ? 'Ambulance' : 'Passenger car'}</option>`
  )).join('');
  select.value = selectedVehicle;
}

function renderUi() {
  const activeLink = [...simulation.links].reverse().find((link) => {
    const message = simulation.messages.find((item) => item.id === link.messageId);
    return message && !message.decision.toLowerCase().includes('no route conflict');
  }) ?? simulation.links.at(-1);
  let activeMessage = activeLink
    ? simulation.messages.find((message) => message.id === activeLink.messageId)
    : null;
  if (simulation.blockage?.focusVehicleId) {
    const blockageMessage = simulation.messages.find((message) => (
      message.type === 'Road blockage alert'
      && message.receiver === simulation.blockage.focusVehicleId
    ));
    if (blockageMessage) activeMessage = blockageMessage;
  }
  const sequence = simulation.presentationSequence;
  const stageNames = {
    baseline: 'NORMAL TRAFFIC',
    'vehicle-encounter': 'VEHICLE ENCOUNTER',
    traffic: 'CONGESTION',
    emergency: 'AMBULANCE',
    conflict: 'INTERSECTION',
    'no-conflict': 'NO-CONFLICT CONTROL',
    'sudden-braking': 'SUDDEN BRAKING',
    blockage: 'ROAD BLOCKAGE',
    flyover: 'FLYOVER',
    ring: 'RING ROAD',
    uturn: 'U-TURN',
  };
  const stageIndex = sequence ? sequence.index + 1 : 0;
  const stageCount = sequence ? sequence.stages.length + 1 : 8;
  element('#caption-stage').textContent = sequence
    ? `${String(sequence.finished ? stageCount : stageIndex + 1).padStart(2, '0')} / ${String(stageCount).padStart(2, '0')} · ${sequence.finished ? 'COMPLETE' : stageNames[sequence.stage]}`
    : 'CITY NETWORK';
  element('#caption-sender').textContent = activeMessage
    ? `${activeMessage.sender}  →  ${activeMessage.receiver}`
    : 'CITY NETWORK';
  element('#caption-title').textContent = activeMessage?.type ?? simulation.event;
  element('#caption-detail').textContent = activeMessage?.content ?? simulation.eventDetail;
  const metrics = simulation.metrics;
  element('#sim-clock').textContent = formatClock(simulation.time);
  element('#active-count').textContent = metrics.active;
  element('#arrived-count').textContent = metrics.arrived;
  element('#mean-speed').textContent = Math.round(metrics.mean);
  element('#reroutes').textContent = metrics.reroutes;
  element('#distance-travelled').textContent = metrics.distanceTravelledKm.toFixed(1);
  element('#mean-trip-time').textContent = metrics.meanTripSeconds === null
    ? '—' : formatClock(metrics.meanTripSeconds);
  element('#messages-sent').textContent = metrics.sentHops;
  element('#messages-received').textContent = metrics.receivedHops;
  element('#mean-latency').textContent = metrics.meanLatencyMs === null
    ? '—' : Math.round(metrics.meanLatencyMs);
  element('#conflict-predictions').textContent = metrics.conflictPredictions;
  element('#skip-stage').hidden = !sequence || sequence.finished;
  element('#event-title').textContent = simulation.event;
  element('#event-detail').textContent = simulation.eventDetail;
  element('#play').innerHTML = simulation.running ? 'Ⅱ &nbsp; PAUSE' : '▶ &nbsp; RESUME';

  const agent = simulation.agents.find((vehicle) => vehicle.id === selectedVehicle);
  if (agent) {
    element('#destination').textContent = `Destination · ${agent.destination.name}`;
    element('#vehicle-speed').innerHTML = `${Math.round(agent.speed)} <small>km/h</small>`;
    const distance = simulation.graph.distance(agent.route, agent.index, agent.progress);
    element('#remaining').innerHTML = `${(distance / 1000).toFixed(2)} <small>km</small>`;
    const etaSeconds = distance / (Math.max(8, agent.speed) / 3.6);
    element('#eta').textContent = agent.arrived ? 'ARRIVED' : formatClock(etaSeconds);
    element('#route-status').textContent = agent.status
      + (agent.replans ? ` · ${agent.replans} replan${agent.replans > 1 ? 's' : ''}` : '')
      + (agent.lastAlertDecision ? ` · V2V: ${agent.lastAlertDecision}` : '');
  }

  element('#message-list').innerHTML = simulation.messages.length
    ? simulation.messages.slice(0, 6).map((message) => (
      `<div class="message-item"><b>${message.sender} → ${message.receiver}</b> · ${message.type} · hop ${message.hop}<br>`
      + `<small>${message.decision} · ${message.latency} ms simulated</small></div>`
    )).join('')
    : '<div class="empty">No messages transmitted</div>';
  element('#timeline').innerHTML = simulation.events.length
    ? simulation.events.slice(0, 7).map((event) => (
      `<div class="timeline-item"><small>${formatClock(event.time)} · </small>${event.text}</div>`
    )).join('')
    : '<div class="empty">Simulation events appear here</div>';
}

function animate(timestamp) {
  const frameSeconds = Math.max(0, (timestamp - previousFrame) / 1000);
  previousFrame = timestamp;
  simulation.tick(frameSeconds);
  world.updateCameraTransition(frameSeconds);
  const stage = simulation.presentationSequence?.stage ?? '';
  if (simulation.suddenBraking) {
    const pairKey = `${simulation.suddenBraking.leaderId}:${simulation.suddenBraking.followerId}`;
    if (pairKey !== displayedSuddenBrakingPair) {
      displayedSuddenBrakingPair = pairKey;
      selectedVehicle = simulation.suddenBraking.followerId;
      populateVehicleSelector();
      const leader = simulation.agents.find((agent) => agent.id === simulation.suddenBraking.leaderId);
      const follower = simulation.agents.find((agent) => agent.id === simulation.suddenBraking.followerId);
      const followPosition = follower && simulation.position(follower);
      if (followPosition) {
        world.presentationFollowing = false;
        world.setCamera('street', followPosition);
      }
    }
  }
  if (stage && stage !== displayedSequenceStage) {
    displayedSequenceStage = stage;
    if (stage === 'baseline') {
      world.setCamera('overview', baselineTrafficFocus());
      world.presentationFollowing = false;
    } else {
      if (stage === 'vehicle-encounter' && simulation.vehicleEncounter) {
        selectedVehicle = simulation.vehicleEncounter.followerId;
        populateVehicleSelector();
      }
      if (stage === 'blockage' && simulation.blockage?.focusVehicleId) {
        selectedVehicle = simulation.blockage.focusVehicleId;
        populateVehicleSelector();
      }
      if (stage === 'emergency') {
        selectedVehicle = simulation.agents[config.vehicles.emergencyIndex]?.id ?? selectedVehicle;
        populateVehicleSelector();
      }
      if (stage === 'conflict' && simulation.intersectionConflict?.yieldingVehicleId) {
        selectedVehicle = simulation.intersectionConflict.yieldingVehicleId;
        populateVehicleSelector();
      }
      if (stage === 'no-conflict' && simulation.noConflictPair?.firstId) {
        selectedVehicle = simulation.noConflictPair.firstId;
        populateVehicleSelector();
      }
      const focusAgent = simulation.agents.find((agent) => agent.id === selectedVehicle);
      const focusPosition = focusAgent && simulation.position(focusAgent);
      if (focusPosition) {
        world.presentationFollowing = false;
        world.setCamera('street', focusPosition);
      } else {
        world.setCamera('overview', presentationFocus());
        world.presentationFollowing = true;
      }
    }
  }
  if (world.cameraAutoFollow && !world.cameraTransition) {
    const selectedAgent = simulation.agents.find((agent) => agent.id === selectedVehicle);
    const position = selectedAgent && simulation.position(selectedAgent);
    if (position) {
      const follow = Math.min(1, frameSeconds * config.rendering.streetCameraFollowRate);
      const heading = position.heading ?? 0;
      const lookAhead = config.rendering.streetCameraLookAheadMeters;
      const targetX = position.x + Math.sin(heading) * lookAhead;
      const targetZ = position.z + Math.cos(heading) * lookAhead;
      world.target.x += (targetX - world.target.x) * follow;
      world.target.y += ((position.y ?? 0) + 1.2 - world.target.y) * follow;
      world.target.z += (targetZ - world.target.z) * follow;
      const headingDelta = Math.atan2(
        Math.sin(heading + Math.PI - world.yaw),
        Math.cos(heading + Math.PI - world.yaw),
      );
      world.yaw += headingDelta * follow;
      world.updateCamera();
    }
  } else if (stage !== 'baseline' && world.presentationFollowing && !world.cameraTransition) {
    const focus = presentationFocus();
    if (focus) {
      const follow = Math.min(1, frameSeconds * 1.7);
      world.target.x += (focus.x - world.target.x) * follow;
      world.target.y += (focus.y - world.target.y) * follow;
      world.target.z += (focus.z - world.target.z) * follow;
      if (Number.isFinite(focus.heading)) {
        const headingDelta = Math.atan2(
          Math.sin(focus.heading - world.yaw),
          Math.cos(focus.heading - world.yaw),
        );
        world.yaw += headingDelta * follow;
      }
      world.updateCamera();
    }
  }
  world.update(simulation, selectedVehicle);
  world.render();
  if (timestamp - previousUiUpdate > 160) {
    renderUi();
    previousUiUpdate = timestamp;
  }
  requestAnimationFrame(animate);
}

populateVehicleSelector();
renderUi();
requestAnimationFrame(animate);

function startPresentation(quick = false) {
  simulation.reset();
  simulation.running = false;
  selectedVehicle = 'V1';
  populateVehicleSelector();
  displayedSequenceStage = '';
  displayedSuddenBrakingPair = '';
  simulation.startPresentationSequence({ quick });
  simulation.running = true;
  element('#controls-panel').hidden = false;
  element('#telemetry-panel').hidden = false;
  element('#panel-toggle').hidden = false;
  setDashboardOpen(false);
  document.body.classList.add('presentation-active');
  world.setCamera('overview', baselineTrafficFocus());
  world.presentationFollowing = false;
}

element('#start-button').onclick = () => startPresentation();
element('#quick-start-button').onclick = () => startPresentation(true);

function setDashboardOpen(open) {
  document.body.classList.toggle('dashboard-open', open);
  const toggle = element('#panel-toggle');
  toggle.setAttribute('aria-expanded', String(open));
  toggle.textContent = open ? '× Close panel' : '☰ Controls';
}

element('#panel-toggle').onclick = () => {
  setDashboardOpen(!document.body.classList.contains('dashboard-open'));
};

function presentationFocus() {
  const spacing = config.world.roadSpacing;
  if (simulation.traffic) {
    const { x, y, z } = simulation.traffic.point;
    const [fromId, toId] = simulation.traffic.edge;
    const from = simulation.graph.node(fromId), to = simulation.graph.node(toId);
    return {
      x: x * spacing, y: y + 1.2, z: z * spacing,
      heading: Math.atan2(to.x - from.x, to.z - from.z),
      radius: config.rendering.trafficCameraRadius, pitch: config.rendering.trafficCameraPitch,
    };
  }
  if (simulation.vehicleEncounter) {
    const { leaderId, followerId } = simulation.vehicleEncounter;
    const leader = simulation.agents.find((agent) => agent.id === leaderId);
    const follower = simulation.agents.find((agent) => agent.id === followerId);
    const first = leader && simulation.position(leader);
    const second = follower && simulation.position(follower);
    if (first && second) return {
      x: (first.x + second.x) / 2,
      y: (first.y + second.y) / 2 + 1.2,
      z: (first.z + second.z) / 2,
      heading: second.heading,
      radius: config.rendering.vehicleEncounterCameraRadius,
      pitch: config.rendering.emergencyCameraPitch,
    };
  }
  if (simulation.noConflictPair) {
    const firstAgent = simulation.agents.find((agent) => agent.id === simulation.noConflictPair.firstId);
    const secondAgent = simulation.agents.find((agent) => agent.id === simulation.noConflictPair.secondId);
    const first = firstAgent && simulation.position(firstAgent);
    const second = secondAgent && simulation.position(secondAgent);
    if (first && second) return {
      x: (first.x + second.x) / 2,
      y: (first.y + second.y) / 2 + 1.2,
      z: (first.z + second.z) / 2,
      heading: first.heading,
      radius: config.rendering.conflictCameraRadius,
      pitch: config.rendering.conflictCameraPitch,
    };
  }
  if (simulation.featureJourney) {
    const feature = simulation.featureJourney;
    const agent = simulation.agents.find((item) => item.id === feature.agentId);
    const position = agent && simulation.position(agent);
    const node = feature.focusNodeId && simulation.graph.node(feature.focusNodeId);
    if (node) return {
      x: position?.x ?? node.x * spacing,
      y: (position?.y ?? node.y ?? 0) + 1.2,
      z: position?.z ?? node.z * spacing,
      heading: position?.heading ?? 0.72,
      radius: feature.scenario === 'uturn'
        ? config.rendering.uTurnCameraRadius
        : feature.scenario === 'underpass'
          ? config.rendering.underpassCameraRadius
        : feature.scenario === 'ring'
          ? config.rendering.ringCameraRadius : config.rendering.featureCameraRadius,
      pitch: config.rendering.featureCameraPitch,
    };
  }
  if (simulation.blockage) {
    const { x, y, z } = simulation.blockage.point;
    const hazard={x:x*spacing,y:y+1.2,z:z*spacing};
    const focusId=simulation.blockage.focusVehicleId;
    const affected=simulation.agents.find((agent)=>agent.id===focusId);
    const approaching=affected&&{agent:affected,position:simulation.position(affected)};
    if(!approaching?.position)return {...hazard,radius:config.rendering.blockageCameraRadius};
    const centerX=(hazard.x+approaching.position.x)/2;
    const centerZ=(hazard.z+approaching.position.z)/2;
    const centerY=(hazard.y+(approaching.position.y??0))/2;
    const from=simulation.graph.node(simulation.blockage.edge[0]);
    const to=simulation.graph.node(simulation.blockage.edge[1]);
    return {
      x:centerX,
      y:centerY,
      z:centerZ,
      heading:Math.atan2(to.x-from.x,to.z-from.z)+Math.PI,
      radius:Math.max(
        config.rendering.blockageCameraRadius,
        Math.min(130,Math.hypot(approaching.position.x-hazard.x,approaching.position.z-hazard.z)*2),
      ),
      pitch:config.rendering.blockageCameraPitch,
    };
  }
  if (simulation.intersectionConflict) {
    const conflict=simulation.intersectionConflict;
    const node=simulation.graph.node(conflict.nodeId);
    if(node){
      const priority=simulation.agents.find((agent)=>agent.id===conflict.priorityVehicleId);
      const yielding=simulation.agents.find((agent)=>agent.id===conflict.yieldingVehicleId);
      const first=priority&&simulation.position(priority),second=yielding&&simulation.position(yielding);
      if(first&&second){
        const junctionX=node.x*spacing;
        const junctionZ=node.z*spacing;
        // Frame the two decision-making vehicles and the junction together.
        // Focusing the junction alone placed one car close to the camera and
        // the other far down its approach, making the yield hard to see.
        const centerX=(first.x+second.x+junctionX)/3;
        const centerZ=(first.z+second.z+junctionZ)/3;
        return {
        x:centerX,
        y:((first.y??0)+(second.y??0)+(node.y??0))/3+1.2,
        z:centerZ,
        heading:Math.atan2(junctionX-centerX,junctionZ-centerZ)
          +config.rendering.conflictCameraYawOffset,
        radius:config.rendering.conflictCameraRadius,
        pitch:config.rendering.conflictCameraPitch,
        };
      }
    }
  }
  const emergency = simulation.agents.find((agent) => agent.type === 'Ambulance');
  const emergencyPosition = emergency && simulation.position(emergency);
  const yielding = simulation.agents
    .filter((agent) => agent.status.startsWith('Yielding'))
    .map((agent) => simulation.position(agent))
    .filter(Boolean)
    .sort((a, b) => Math.hypot(a.x - emergencyPosition.x, a.z - emergencyPosition.z)
      - Math.hypot(b.x - emergencyPosition.x, b.z - emergencyPosition.z))[0];
  if (emergencyPosition && yielding) {
    return {
      x: (emergencyPosition.x + yielding.x) / 2,
      y: (emergencyPosition.y + yielding.y) / 2 + 1.2,
      z: (emergencyPosition.z + yielding.z) / 2,
      heading: emergencyPosition.heading,
      radius: config.rendering.emergencyCameraRadius,
      pitch: config.rendering.emergencyCameraPitch,
    };
  }
  return emergencyPosition
    ? { x: emergencyPosition.x, y: emergencyPosition.y + 1.2, z: emergencyPosition.z }
    : undefined;
}

function focusScenarioCamera() {
  const focusAgent = simulation.agents.find((agent) => agent.id === selectedVehicle);
  const position = focusAgent && simulation.position(focusAgent);
  if (position) {
    world.presentationFollowing = false;
    world.setCamera('street', position);
    return;
  }
  const focus = presentationFocus();
  if (!focus) return;
  world.presentationFollowing = true;
  world.setCamera('overview', focus);
}

document.addEventListener('keydown', (event) => {
  if (event.code === 'Escape' && document.body.classList.contains('presentation-active')) {
    if (document.body.classList.contains('dashboard-open')) {
      setDashboardOpen(false);
      return;
    }
    simulation.running = false;
    document.body.classList.remove('presentation-active');
    element('#panel-toggle').hidden = true;
    world.presentationFollowing = false;
    world.setCamera('overview');
    return;
  }
  if (event.code !== 'Space' || !document.body.classList.contains('presentation-active')) return;
  event.preventDefault();
  simulation.running = !simulation.running;
  element('#caption-title').textContent = simulation.running ? 'Simulation resumed' : 'Simulation paused';
  element('#caption-detail').textContent = 'Press Space to continue.';
});

element('#play').onclick = () => {
  simulation.running = !simulation.running;
  renderUi();
};
element('#skip-stage').onclick = () => {
  simulation.skipPresentationStage();
  renderUi();
};
element('#reset').onclick = () => {
  simulation.reset();
  populateVehicleSelector();
  renderUi();
};
element('#vehicle-select').onchange = (event) => {
  selectedVehicle = event.target.value;
  if (world.cameraAutoFollow) {
    world.setCamera('street', simulation.position(simulation.agents.find((agent) => agent.id === selectedVehicle)));
  }
  renderUi();
};
element('#rate').oninput = (event) => {
  simulation.rate = Number(event.target.value);
  element('#rate-value').textContent = `${simulation.rate.toFixed(1)}×`;
};
element('#blockage').onclick = () => {
  chooseScenario('blockage');
};
element('#emergency').onclick = () => {
  chooseScenario('emergency');
};
function chooseScenario(scenario) {
  element('#scenario').value = scenario;
  element('#scenario').dispatchEvent(new Event('change', { bubbles: true }));
}
element('#scenario').onchange = (event) => {
  const scenario = event.target.value;
  simulation.reset();
  element('#rate').value = String(simulation.rate);
  element('#rate-value').textContent = `${simulation.rate.toFixed(1)}×`;
  displayedSequenceStage = '';
  displayedSuddenBrakingPair = '';
  selectedVehicle = 'V1';
  world.presentationFollowing = false;
  populateVehicleSelector();

  if (['normal', 'flyover', 'underpass', 'ring', 'uturn', 'traffic'].includes(scenario)) {
    simulation.startJourney(scenario);
    if (simulation.featureJourney?.agentId) selectedVehicle = simulation.featureJourney.agentId;
    populateVehicleSelector();
    if (scenario === 'normal') {
      world.presentationFollowing = false;
      world.setCamera('overview', baselineTrafficFocus());
    } else focusScenarioCamera();
  } else if (scenario === 'blockage') simulation.triggerBlockage();
  else if (scenario === 'emergency') simulation.triggerEmergency();
  else if (scenario === 'conflict') simulation.triggerConflict();
  else if (scenario === 'vehicle-encounter') simulation.triggerVehicleEncounter();
  else if (scenario === 'no-conflict') simulation.triggerNoConflict();
  else if (scenario === 'sudden-braking') simulation.startSuddenBraking();
  else {
    simulation.mode = 'normal';
    simulation.event = 'Normal traffic flow';
    simulation.eventDetail = 'Vehicles are following assigned routes.';
  }
  if (scenario === 'vehicle-encounter' && simulation.vehicleEncounter) {
    selectedVehicle = simulation.vehicleEncounter.followerId;
    populateVehicleSelector();
    focusScenarioCamera();
  }
  if (scenario === 'blockage' && simulation.blockage?.focusVehicleId) {
    selectedVehicle = simulation.blockage.focusVehicleId;
    populateVehicleSelector();
    focusScenarioCamera();
  }
  if (scenario === 'emergency') {
    selectedVehicle = simulation.agents[config.vehicles.emergencyIndex]?.id ?? selectedVehicle;
    populateVehicleSelector();
    focusScenarioCamera();
  }
  if (scenario === 'conflict' && simulation.intersectionConflict?.yieldingVehicleId) {
    selectedVehicle = simulation.intersectionConflict.yieldingVehicleId;
    populateVehicleSelector();
    focusScenarioCamera();
  }
  if (scenario === 'no-conflict' && simulation.noConflictPair?.firstId) {
    selectedVehicle = simulation.noConflictPair.firstId;
    populateVehicleSelector();
    focusScenarioCamera();
  }
  renderUi();
};
document.querySelectorAll('.camera').forEach((button) => {
  button.onclick = () => {
    document.querySelectorAll('.camera').forEach((camera) => camera.classList.remove('active'));
    button.classList.add('active');
    const agent = simulation.agents.find((vehicle) => vehicle.id === selectedVehicle);
    world.setCamera(button.dataset.camera, simulation.position(agent));
  };
});
element('#cam-reset').onclick = () => {
  const agent = simulation.agents.find((vehicle) => vehicle.id === selectedVehicle);
  world.setCamera('street', simulation.position(agent));
};
