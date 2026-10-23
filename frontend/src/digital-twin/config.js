/**
 * Shared simulation and presentation settings.
 * Keep tunable values here so changes do not need to be repeated across modules.
 */
export const config = {
  world: {
    metersPerUnit: 1,
    roadSpacing: 110,
    roadSpeedKmh: { arterial: 60, urban: 40, ring: 50, flyover: 60 },
    ringRoadRadiusBlocks: 3,
    ringRoadSegments: 32,
    uTurnRadiusMeters: 6,
    uTurnSegments: 14,
    uTurnSpeedKmh: 15,
    uTurnRoadWidthMeters: 7,
    uTurnLocationBlocks: -1.5,
    flyoverHeightMeters: 5.2,
    flyoverGraphSegments: 20,
    underpassDepthMeters: 5,
    underpassGraphSegments: 24,
    underpassLocationBlocks: -2,
    // Detailed streets stay central; connected road surfaces continue outward.
    renderedRoadRadius: 5,
    roadNetworkRadius: 24,
    cityscapeRadius: 8,
    buildingHeightZones: {
      foregroundRadiusMeters: 165,
      foregroundMinMeters: 10,
      foregroundMaxMeters: 24,
      skylineMinMeters: 34,
      skylineMaxMeters: 95,
    },
    asphaltTextureRepeatMeters: 12,
    groundSurfaceRepeatMeters: 18,
    asphaltTextureUrl: '/assets/urban-asphalt-tile.png',
    officeFacadeTextureUrl: '/assets/office-facade-tile.png',
    alternateFacadeTextureUrl: '/assets/bengaluru-office-facade-variation.png',
    initialGraphRadius: 4,
    graphSearchRadius: 8,
    roadHalfWidth: 10,
    curbOffsetMeters: 10.2,
    sidewalkOffsetMeters: 12.1,
    sidewalkWidth: 3.3,
    arterialMedianWidthMeters: 1.15,
    arterialMedianHeightMeters: 0.28,
    arterialMedianJunctionClearanceMeters: 20,
  },
  vehicles: {
    // A denser connected-city fleet that remains manageable for browser rendering.
    count: 120,
    emergencyIndex: 9,
    passengerSpeedKmh: [40, 43],
    emergencySpeedKmh: 72,
    accelerationMps2: 2.4,
    brakingMps2: 6.5,
    turnSpeedKmh: 20,
    turnRadiusMeters: 12,
    turnDecelerationMps2: 3.2,
    laneChangeRateMps: 1.25,
    yieldLaneOffsetMeters: 7,
    // Longer headway helps preserve car-length clearance at city speeds.
    followingDistanceMeters: 18,
    minimumFollowingGapMeters: 6.5,
    laneOffsetMeters: 2.5,
    maxFrameSeconds: 0.05,
    initialProgressStep: 0.12,
  },
  communication: {
    // Short urban links make intermediate vehicles useful relays in the city.
    rangeMeters: 120,
    maxRelayHops: 3,
    latencyMs: [32, 86],
    linkDurationSeconds: 4.5,
    alertHighlightSeconds: 8,
    roleHighlightSeconds: 2.4,
    messageHistoryLimit: 120,
    packetRadiusMeters: 0.34,
    communicationArcHeightMeters: 5.5,
  },
  scenarios: {
    blockageDurationSeconds: 18,
    emergencyPrioritySeconds: 22,
    emergencyYieldSpeedKmh: 12,
    emergencyLookAheadNodes: 5,
    emergencyCorridorWidthMeters: 18,
    blockageAlertLookAheadNodes: 6,
    intersectionHoldSeconds: 3,
    intersectionConflictWindowSeconds: 8,
    intersectionStopLineOffsetMeters: 13,
    // Keep cross-traffic yielding local to the junction so a busy fleet can
    // continue flowing instead of braking far upstream.
    // Start conflict detection far enough upstream to brake at urban speed
    // before the turn-aware stop line, even with finite simulation timesteps.
    intersectionGuardDistanceMeters: 50,
    intersectionOccupancyRadiusMeters: 10,
    intersectionMaxHoldSeconds: 30,
    trafficDurationSeconds: 38,
    trafficSpeedKmh: 10,
    trafficLookAheadNodes: 5,
    automaticScenarioIntervalSeconds: 0,
    presentationBaselineSeconds: 12,
    quickPresentationBaselineSeconds: 3,
    presentationEncounterSeconds: 8,
    quickPresentationEncounterSeconds: 6,
    presentationNoConflictSeconds: 8,
    quickPresentationNoConflictSeconds: 6,
    vehicleEncounterResponseSeconds: 5,
    vehicleEncounterSpeedFactor: 0.85,
    quickTrafficDurationSeconds: 10,
    quickEmergencyPrioritySeconds: 12,
    quickConflictHoldSeconds: 6,
    quickBlockageDurationSeconds: 10,
    featureStageTimeoutSeconds: 120,
    quickFeatureStageTimeoutSeconds: 45,
    suddenBrakingLeadInSeconds: 2.5,
    suddenBrakingHoldSeconds: 1.2,
    suddenBrakingResponseSeconds: 3,
    suddenBrakingResponseSpeedFactor: 0.45,
  },
  rendering: {
    pixelRatioLimit: 1.75,
    shadowMapSize: 2048,
    streetCameraRadius: 34,
    streetCameraPitch: 0.34,
    streetCameraLookAheadMeters: 12,
    streetCameraFollowRate: 5,
    streetCameraYaw: 1.42,
    // Scene view: high enough to read the junction, low enough to see cars
    // at road scale and retain a realistic skyline perspective.
    overviewCameraRadius: 26,
    overviewCameraPitch: 0.06,
    // Frame a readable multi-block district while keeping traffic large enough
    // to see; incident shots include senders, affected cars, and relay links.
    // Keep the opening aerial view broad enough to read as a district, while
    // bringing the active roads and traffic up to a visible size behind the title.
    openingOverviewRadiusMeters: 190,
    // Start the moving presentation closer than the title-screen city view so
    // the traffic is legible without asking the presenter to zoom manually.
    // This radius keeps the camera clear of nearby buildings while framing the
    // central traffic district for the baseline shot.
    sequenceOverviewRadiusMeters: 96,
    // Use an elevated street perspective instead of looking almost straight
    // down; this keeps moving traffic and intersection geometry in view.
    sequenceOverviewPitch: 0.42,
    cameraTransitionSeconds: 1.6,
    blockageCameraRadius: 52,
    blockageCameraPitch: 0.62,
    conflictCameraRadius: 44,
    conflictCameraPitch: 0.26,
    conflictCameraYawOffset: 0,
    vehicleEncounterCameraRadius: 26,
    emergencyCameraRadius: 34,
    emergencyCameraPitch: 0.3,
    trafficCameraRadius: 42,
    trafficCameraPitch: 0.2,
    featureCameraRadius: 50,
    underpassCameraRadius: 32,
    ringCameraRadius: 78,
    uTurnCameraRadius: 42,
    featureCameraPitch: 0.34,
    adaptiveRouteDisplaySeconds: 10,
    maxAdaptiveRouteOverlays: 4,
    intersectionPriorityColor: '#4fe28b',
    intersectionYieldColor: '#ff8a38',
    vehicleTagWidthMeters: 2.2,
    vehicleTagHeightMeters: 0.72,
    vehicleStatusMarkerRadiusMeters: 1.35,
    adaptiveRouteWidthMeters: 0.3,
    adaptiveRouteColor: '#35e58d',
    adaptiveRouteEmissiveColor: '#0c7044',
    blockedRouteWidthMeters: 0.48,
    blockedRouteColor: '#ff3d45',
    maxMessageBubbles: 4,
    messageBubbleWidthMeters: 16,
    messageBubbleHeightMeters: 4.2,
    messageBubbleStackSpacingMeters: 5.2,
    messageBubbleClearanceMeters: 12,
    messageBubbleLateralOffsetMeters: 6,
    cameraMinRadius: 8,
    cameraMaxRadius: 500,
  },
};

export const destinations = [
  { name: 'Airport Terminal', node: '2,0' },
  { name: 'East Business Park', node: '3,1' },
  { name: 'Riverside East', node: '4,-1' },
  { name: 'Stadium District', node: '3,-2' },
  { name: 'East University', node: '4,2' },
  { name: 'North East Hospital', node: '2,-3' },
  { name: 'West Airport', node: '-2,0' },
  { name: 'West University', node: '-3,-1' },
  { name: 'Old Town West', node: '-4,1' },
  { name: 'West Hospital', node: '-3,2' },
  { name: 'Industrial West', node: '-4,-2' },
  { name: 'West Station', node: '-2,3' },
  { name: 'South Station', node: '0,2' },
  { name: 'South University', node: '1,3' },
  { name: 'South Medical Centre', node: '-1,4' },
  { name: 'South Airport', node: '2,4' },
  { name: 'South Industrial Park', node: '-2,4' },
  { name: 'South Shopping Centre', node: '3,4' },
  { name: 'North Station', node: '0,-2' },
  { name: 'North University', node: '1,-3' },
  { name: 'North Medical Centre', node: '-1,-4' },
  { name: 'North Airport', node: '2,-4' },
  { name: 'North Business Park', node: '-2,-3' },
  { name: 'North Shopping Centre', node: '3,-4' },
];

// Spread a larger fleet across the first two city blocks instead of packing
// every starting approach at the central eight junctions.
const startCandidates = [];
for (let radius = 1; radius <= 2; radius++) {
  for (let z = -radius; z <= radius; z++) {
    for (let x = -radius; x <= radius; x++) {
      if (Math.max(Math.abs(x), Math.abs(z)) === radius) startCandidates.push(`${x},${z}`);
    }
  }
}
// The flyover's grid endpoints connect to short ramp edges and are poor spawn
// points for staggered traffic packs.
for (const node of ['2,-2', '2,2']) {
  startCandidates.splice(startCandidates.indexOf(node), 1);
}
const reservedStartNodes = new Set(startCandidates);

// Keep every configured vehicle on its own reachable trip instead of reusing
// the first 24 destinations when the fleet grows. Destinations stay within the
// rendered city district so journeys remain visible in the city overview.
const usedDestinationNodes = new Set(destinations.map(({ node }) => node));
for (let radius = 2; radius <= 6 && destinations.length < config.vehicles.count; radius++) {
  for (let z = -radius; z <= radius && destinations.length < config.vehicles.count; z++) {
    for (let x = -radius; x <= radius && destinations.length < config.vehicles.count; x++) {
      if (Math.max(Math.abs(x), Math.abs(z)) !== radius) continue;
      const node = `${x},${z}`;
      if (usedDestinationNodes.has(node) || reservedStartNodes.has(node)) continue;
      destinations.push({ name: `City District ${destinations.length + 1}`, node });
      usedDestinationNodes.add(node);
    }
  }
}

// Rotate through the distributed starts and avoid assigning a vehicle its own
// starting junction as its destination.
export const vehicleStarts = Array.from({ length: config.vehicles.count }, (_, index) => {
  const destination = destinations[index % destinations.length].node;
  let candidateIndex = index % startCandidates.length;
  while (startCandidates[candidateIndex] === destination) {
    candidateIndex = (candidateIndex + 1) % startCandidates.length;
  }
  return startCandidates[candidateIndex];
});

export const vehicleColors = [
  '#c3c7c6', '#3d454c', '#e3e1db', '#2c4b69', '#2b2e31',
  '#91423c', '#a7aaa6', '#f1f0eb', '#56655f', '#4a5055',
];
