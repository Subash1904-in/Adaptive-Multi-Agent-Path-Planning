import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { config } from './config.js';
import { getRoutePolyline } from './vehicle.js';

const BLOCK = config.world.roadSpacing;

const materialCache = new Map();
const boxGeometryCache = new Map();
const staticMeshes = [];
let collectStaticMeshes = false;
function loadSurfaceTexture(url){
 const texture=new THREE.TextureLoader().load(url);
 texture.colorSpace=THREE.SRGBColorSpace;
 texture.wrapS=THREE.RepeatWrapping;texture.wrapT=THREE.RepeatWrapping;
 texture.anisotropy=8;return texture;
}
const mat=(color,roughness=.84,metalness=0)=>{
 const key=`${color}:${roughness}:${metalness}`;
 if(!materialCache.has(key))materialCache.set(key,new THREE.MeshStandardMaterial({color,roughness,metalness}));
 return materialCache.get(key);
};
function box(parent,material,x,y,z,sx,sy,sz,cast=false){
 const key=`${sx}:${sy}:${sz}`;
 if(!boxGeometryCache.has(key))boxGeometryCache.set(key,new THREE.BoxGeometry(sx,sy,sz));
 let o=new THREE.Mesh(boxGeometryCache.get(key),material);o.position.set(x,y,z);o.castShadow=cast;o.receiveShadow=true;parent.add(o);if(collectStaticMeshes)staticMeshes.push(o);return o;
}
function makeAsphaltTexture(){
 const size=256,canvas=document.createElement('canvas');
 canvas.width=size;canvas.height=size;
 const context=canvas.getContext('2d'),image=context.createImageData(size,size);
 let seed=927431;
 const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 for(let pixel=0;pixel<size*size;pixel++){
  const grain=231+Math.floor(random()*18),offset=pixel*4;
  image.data[offset]=grain+1;
  image.data[offset+1]=grain;
  image.data[offset+2]=grain;
  image.data[offset+3]=255;
 }
 context.putImageData(image,0,0);
 // Low contrast aggregate, repaired patches and fine hairline cracks.
 for(let patch=0;patch<10;patch++){
  const x=random()*size,y=random()*size,width=10+random()*56,height=4+random()*20;
  context.fillStyle=random()>.5?'rgba(22,27,28,.035)':'rgba(255,255,255,.025)';
  context.beginPath();context.ellipse(x,y,width,height,random()*.4,0,Math.PI*2);context.fill();
 }
 for(let crack=0;crack<2;crack++){
  let x=random()*size,y=random()*size;
  context.strokeStyle='rgba(20,24,25,.07)';context.lineWidth=.35+random()*.3;context.beginPath();context.moveTo(x,y);
  for(let segment=0;segment<5;segment++){x+=(random()-.5)*23;y+=(random()-.5)*18;context.lineTo(x,y);}
  context.stroke();
 }
 const texture=new THREE.CanvasTexture(canvas);
 texture.colorSpace=THREE.SRGBColorSpace;
 texture.wrapS=THREE.RepeatWrapping;
 texture.wrapT=THREE.RepeatWrapping;
 texture.anisotropy=8;
 return texture;
}
function makeSkyTexture(){
 const canvas=document.createElement('canvas');
 canvas.width=1024;canvas.height=512;
 const context=canvas.getContext('2d');
 const gradient=context.createLinearGradient(0,0,0,512);
 gradient.addColorStop(0,'#587f98');
 gradient.addColorStop(.42,'#adc8d6');
 gradient.addColorStop(.76,'#e9d2b5');
 gradient.addColorStop(1,'#f4e2ca');
 context.fillStyle=gradient;context.fillRect(0,0,1024,512);
 let seed=31847;
 const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
 for(let cloud=0;cloud<34;cloud++){
  const centerX=random()*1024,centerY=115+random()*205;
  context.fillStyle=`rgba(244,239,228,${.025+random()*.035})`;
  for(let puff=0;puff<9;puff++){
   const width=35+random()*90,height=9+random()*22;
   context.beginPath();
   context.ellipse(centerX+(random()-.5)*125,centerY+(random()-.5)*24,width,height,0,0,Math.PI*2);
   context.fill();
  }
 }
 const texture=new THREE.CanvasTexture(canvas);
 texture.colorSpace=THREE.SRGBColorSpace;
 texture.mapping=THREE.EquirectangularReflectionMapping;
 return texture;
}
function makeMessageBubble(message){
 const canvas=document.createElement('canvas');
 canvas.width=768;canvas.height=210;
 const context=canvas.getContext('2d');
 context.fillStyle='rgba(10,26,32,.96)';
 context.beginPath();context.roundRect(5,5,758,200,34);context.fill();
 context.strokeStyle='#64e5f2';context.lineWidth=7;context.stroke();
  context.fillStyle='#70e6ef';context.font='bold 42px Arial';
 const routeLabel=message.hop>1
  ?`${message.originSender} via ${message.sender} → ${message.receiver} · HOP ${message.hop}`
  :`${message.sender} → ${message.receiver} · HOP 1`;
 context.fillText(routeLabel,34,63);
  context.fillStyle='#f4fbfc';context.font='bold 54px Arial';
  const words=(message.decision??message.content).split(' ');
  let line='',lineY=132;
 for(const word of words){
  const candidate=line?`${line} ${word}`:word;
  if(context.measureText(candidate).width>690&&line){context.fillText(line,34,lineY);line=word;lineY+=52;}
  else line=candidate;
 }
 if(lineY<=185)context.fillText(line,34,lineY);
 const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
 const bubble=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthTest:false}));
 bubble.scale.set(
  config.rendering.messageBubbleWidthMeters,
  config.rendering.messageBubbleHeightMeters,
  1,
 );bubble.renderOrder=5;return bubble;
}
export class World{
 constructor(container){this.container=container;this.scene=new THREE.Scene();this.scene.background=makeSkyTexture();this.scene.fog=new THREE.Fog('#cbd7dc',560,1500);this.scene.add(new THREE.HemisphereLight('#e9eff1','#535b51',1.55));const sun=new THREE.DirectionalLight('#fff0d7',2.9);sun.position.set(-240,340,130);sun.castShadow=true;sun.shadow.mapSize.set(config.rendering.shadowMapSize,config.rendering.shadowMapSize);sun.shadow.camera.left=-520;sun.shadow.camera.right=520;sun.shadow.camera.top=520;sun.shadow.camera.bottom=-520;sun.shadow.bias=-.00015;this.scene.add(sun);this.facadeTextures=[config.world.officeFacadeTextureUrl,config.world.alternateFacadeTextureUrl].map(loadSurfaceTexture);this.facadeMaterials=this.facadeTextures.map((texture)=>new THREE.MeshStandardMaterial({map:texture,roughness:.48,metalness:.12}));this.camera=new THREE.PerspectiveCamera(46,1,.1,2400);this.renderer=new THREE.WebGLRenderer({antialias:true,powerPreference:'high-performance'});this.renderer.setPixelRatio(Math.min(devicePixelRatio,config.rendering.pixelRatioLimit));this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.04;this.renderer.outputColorSpace=THREE.SRGBColorSpace;container.appendChild(this.renderer.domElement);this.root=new THREE.Group();this.scene.add(this.root);this.vehicles=new Map();this.agentLookup=new Map();this.carTemplate=null;this.loadCarTemplate();this.routeLine=null;this.routeSignature='';this.adaptiveRouteLines=new Map();this.eventObjects=[];this.renderedBlockageKey=null;this.links=new Map();this.makeGround();collectStaticMeshes=true;this.makeRoads();this.makeIntersectionMarkings();this.makeFlyover();this.makeUnderpass();this.makeSignals();this.makeStreetLighting();this.makeTreeCanopies();collectStaticMeshes=false;this.mergeStaticGeometry();this.setupCamera();this.resize();addEventListener('resize',()=>this.resize());}
 mergeStaticGeometry(){const byMaterial=new Map(),emptyParents=new Set();for(const mesh of staticMeshes){mesh.updateWorldMatrix(true,false);if(mesh.parent!==this.root)emptyParents.add(mesh.parent);const material=mesh.material;if(!byMaterial.has(material))byMaterial.set(material,[]);const geometry=mesh.geometry.clone();geometry.applyMatrix4(mesh.matrixWorld);if(material.map&&!mesh.userData.preserveUv){const positions=geometry.getAttribute('position'),uv=geometry.getAttribute('uv'),repeat=config.world.asphaltTextureRepeatMeters;for(let i=0;i<positions.count;i++)uv.setXY(i,positions.getX(i)/repeat,positions.getZ(i)/repeat);uv.needsUpdate=true;}byMaterial.get(material).push(geometry);mesh.parent?.remove(mesh);}for(const parent of emptyParents)if(parent.children.length===0)this.root.remove(parent);for(const [material,geometries]of byMaterial){const merged=mergeGeometries(geometries,false);for(const geometry of geometries)geometry.dispose();if(!merged)continue;const mesh=new THREE.Mesh(merged,material);mesh.castShadow=true;mesh.receiveShadow=true;this.root.add(mesh);}staticMeshes.length=0;}
 makeGround(){
  const size=8000,texture=makeAsphaltTexture();
  const half=size/2,underpassX=config.world.underpassLocationBlocks*BLOCK;
  const shape=new THREE.Shape();
  shape.moveTo(-half,-half);shape.lineTo(half,-half);shape.lineTo(half,half);
  shape.lineTo(-half,half);shape.closePath();
  const opening=new THREE.Path();
  const left=underpassX-config.world.roadHalfWidth-2;
  const right=underpassX+config.world.roadHalfWidth+2;
  const start=-2*BLOCK,end=2*BLOCK;
  opening.moveTo(left,start);opening.lineTo(left,end);opening.lineTo(right,end);
  opening.lineTo(right,start);opening.closePath();shape.holes.push(opening);
  const geometry=new THREE.ShapeGeometry(shape);
  const positions=geometry.getAttribute('position'),uv=geometry.getAttribute('uv');
  for(let index=0;index<positions.count;index++){
   uv.setXY(index,positions.getX(index)/config.world.groundSurfaceRepeatMeters,
    positions.getY(index)/config.world.groundSurfaceRepeatMeters);
  }
  uv.needsUpdate=true;
  texture.repeat.set(1,1);
  const surface=new THREE.MeshStandardMaterial({color:'#777a76',map:texture,roughness:.97});
  const ground=new THREE.Mesh(geometry,surface);
  ground.rotation.x=-Math.PI/2;ground.position.y=-.14;ground.receiveShadow=true;this.root.add(ground);
 }
 makeRoads(){
  const asphalt=mat('#f0f0ed',.98),mark=mat('#d9d6c8',.8),yellow=mat('#d0b064',.8),curb=mat('#aeb1a8',.9),walk=mat('#96968d',.94),stripe=mat('#e6e3d9',.8);
  asphalt.map=loadSurfaceTexture(config.world.asphaltTextureUrl);
  asphalt.needsUpdate=true;
  const range=config.world.roadNetworkRadius;
  const detailRange=config.world.renderedRoadRadius;
  const cityRange=config.world.cityscapeRadius;
  const roadLength=(range*2+1)*BLOCK;
  const roadWidth=config.world.roadHalfWidth*2;
  const roadStart=-roadLength/2,roadEnd=roadLength/2;
  const underpassX=config.world.underpassLocationBlocks;
  const underpassSegments=index=>index===underpassX
   ?[[roadStart,-2*BLOCK],[2*BLOCK,roadEnd]]:[[roadStart,roadEnd]];

  // Long strips span the whole generated district so each crossing is connected.
  for(let index=-range;index<=range;index++){
   const offset=index*BLOCK;
   box(this.root,asphalt,0,.01,offset,roadLength,.10,roadWidth);
   for(const [segmentStart,segmentEnd] of underpassSegments(index)){
    const segmentLength=segmentEnd-segmentStart;
    if(segmentLength<=0)continue;
    box(this.root,asphalt,offset,.012,(segmentStart+segmentEnd)/2,roadWidth,.10,segmentLength);
   }
   for(const side of [-1,1]){
    const curbOffset=side*config.world.curbOffsetMeters;
    const walkOffset=side*config.world.sidewalkOffsetMeters;
    box(this.root,curb,0,.10,offset+curbOffset,roadLength,.2,.42);
    box(this.root,walk,0,.045,offset+walkOffset,roadLength,.12,config.world.sidewalkWidth);
    for(const [segmentStart,segmentEnd] of underpassSegments(index)){
     const segmentLength=segmentEnd-segmentStart;
     if(segmentLength<=0)continue;
     const segmentCenter=(segmentStart+segmentEnd)/2;
     box(this.root,curb,offset+curbOffset,.10,segmentCenter,.42,.2,segmentLength);
     box(this.root,walk,offset+walkOffset,.045,segmentCenter,config.world.sidewalkWidth,.12,segmentLength);
    }
   }

   // Broken lane lines and center lines run along each arterial.
   if(Math.abs(index)<=detailRange)for(let distance=-detailRange*BLOCK;distance<=detailRange*BLOCK;distance+=28){
    if(Math.abs(distance-offset)<17)continue;
    if(index!==0)box(this.root,yellow,distance,.075,offset,8,.018,.24);
    box(this.root,mark,distance,.075,offset-3.2,8,.018,.15);
    box(this.root,mark,distance,.075,offset+3.2,8,.018,.15);
    if(index!==underpassX||Math.abs(distance)>2*BLOCK){
     box(this.root,mark,offset-3.2,.075,distance,.15,.018,8);
     box(this.root,mark,offset+3.2,.075,distance,.15,.018,8);
    }
   }

   // Crosswalk bars repeat at every junction along both road directions.
   if(Math.abs(index)<=detailRange)for(let junction=-detailRange;junction<=detailRange;junction++){
    const intersection=junction*BLOCK;
    for(let bar=-3;bar<=3;bar++){
     const position=intersection+bar*1.35;
     box(this.root,stripe,position,.076,offset,.72,.02,3.1);
     if(index!==underpassX||Math.abs(intersection)>2*BLOCK){
      box(this.root,stripe,offset,.076,position,3.1,.02,.72);
     }
    }
   }
  }

  // Raised dividers identify the two main arterials and separate opposing flow.
  // They stop short of every junction so turning paths remain unobstructed.
  const median=mat('#777d78',.92),medianTop=mat('#59634f',.98);
  const medianClearance=config.world.arterialMedianJunctionClearanceMeters;
  const medianLength=BLOCK-medianClearance*2;
  const medianWidth=config.world.arterialMedianWidthMeters;
  const uTurnMedianSegment=Math.floor(config.world.uTurnLocationBlocks);
  const uTurnGapCenter=config.world.uTurnLocationBlocks*BLOCK;
  const uTurnGapHalfWidth=config.world.uTurnRadiusMeters+medianWidth*2;
  for(let segment=-range;segment<range;segment++){
   const center=(segment+.5)*BLOCK;
   if(segment===uTurnMedianSegment){
    const medianStart=center-medianLength/2,medianEnd=center+medianLength/2;
    const gapStart=uTurnGapCenter-uTurnGapHalfWidth,gapEnd=uTurnGapCenter+uTurnGapHalfWidth;
    for(const [start,end] of [[medianStart,gapStart],[gapEnd,medianEnd]]){
     if(end<=start)continue;
     const length=end-start,midpoint=(start+end)/2;
     box(this.root,median,0,.14,midpoint,medianWidth,config.world.arterialMedianHeightMeters,length);
     box(this.root,medianTop,0,.29,midpoint,medianWidth*.72,.04,length*.94);
    }
   }else{
    box(this.root,median,0,.14,center,medianWidth,config.world.arterialMedianHeightMeters,medianLength);
    box(this.root,medianTop,0,.29,center,medianWidth*.72,.04,medianLength*.94);
   }
   box(this.root,median,center,.14,0,medianLength,config.world.arterialMedianHeightMeters,medianWidth);
   box(this.root,medianTop,center,.29,0,medianLength*.94,.04,medianWidth*.72);
  }

  // Pavement for the routable median-opening U-turn pocket. Its centerline is
  // taken from the same sampled graph nodes used by the moving vehicle.
  const uTurnPath=[this.graphPoint('0,-1')];
  for(let index=0;index<=config.world.uTurnSegments;index++)uTurnPath.push(this.graphPoint(`uturn:${index}`));
  uTurnPath.push(this.graphPoint('0,-1'));
  const halfWidth=config.world.uTurnRoadWidthMeters/2;
  const vertices=[],uvs=[],indices=[];
  for(let index=0;index<uTurnPath.length;index++){
   const previous=uTurnPath[Math.max(0,index-1)],next=uTurnPath[Math.min(uTurnPath.length-1,index+1)];
   const dx=next.x-previous.x,dz=next.z-previous.z,length=Math.hypot(dx,dz)||1;
   const sideX=-dz/length,sideZ=dx/length,point=uTurnPath[index];
   vertices.push(point.x+sideX*halfWidth,.09,point.z+sideZ*halfWidth);
   vertices.push(point.x-sideX*halfWidth,.09,point.z-sideZ*halfWidth);
   uvs.push(index,0,index,1);
   if(index>0){const base=(index-1)*2;indices.push(base,base+2,base+1,base+1,base+2,base+3);}
  }
  const uTurnGeometry=new THREE.BufferGeometry();
  uTurnGeometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  uTurnGeometry.setAttribute('uv',new THREE.Float32BufferAttribute(uvs,2));
  uTurnGeometry.setIndex(indices);uTurnGeometry.computeVertexNormals();
  const uTurnSurface=new THREE.Mesh(uTurnGeometry,asphalt);
  uTurnSurface.receiveShadow=true;this.root.add(uTurnSurface);staticMeshes.push(uTurnSurface);
  const pocketEdgeMaterial=mat('#e5ddcc',.72);
  for(const side of [0,1]){
   const edgePoints=uTurnPath.slice(1,-1).map((_,arcIndex)=>{
    const index=arcIndex+1;
    return new THREE.Vector3(vertices[index*6+side*3],.17,vertices[index*6+side*3+2]);
   });
   const edgeCurve=new THREE.CatmullRomCurve3(edgePoints);
   const edgeMesh=new THREE.Mesh(new THREE.TubeGeometry(edgeCurve,48,.16,6,false),pocketEdgeMaterial);
   edgeMesh.castShadow=false;edgeMesh.receiveShadow=false;this.root.add(edgeMesh);
  }

  // The ring road is a broad asphalt carriageway with two marked lanes.
  const ringRadius = config.world.ringRoadRadiusBlocks * BLOCK;
  const ringHalfWidth = config.world.roadHalfWidth;
  const ringRoad = new THREE.Mesh(
   new THREE.RingGeometry(ringRadius - ringHalfWidth, ringRadius + ringHalfWidth, 160),
   asphalt,
  );
  ringRoad.rotation.x = -Math.PI / 2;
  ringRoad.position.y = .065;
  ringRoad.receiveShadow = true;
  this.root.add(ringRoad);
  for (const offset of [-3.2, 3.2]) {
   const radius = ringRadius + offset;
   const points = Array.from({ length: 193 }, (_, index) => {
    const angle = (index / 192) * Math.PI * 2;
    return new THREE.Vector3(Math.cos(angle) * radius, .085, Math.sin(angle) * radius);
   });
   const geometry = new THREE.BufferGeometry().setFromPoints(points);
   const line = new THREE.Line(geometry, new THREE.LineDashedMaterial({
    color: '#dedbd0', dashSize: 8, gapSize: 6, transparent: true, opacity: .9,
   }));
   line.computeLineDistances();
   this.root.add(line);
  }

  // Fill blocks between roads. Building setbacks keep façades out of junctions.
  for(let x=-cityRange;x<cityRange;x++)for(let z=-cityRange;z<cityRange;z++){
   const centerX=(x+.5)*BLOCK,centerZ=(z+.5)*BLOCK;
   const ringClearance = Math.abs(Math.hypot(centerX, centerZ) - ringRadius);
   if (ringClearance > ringHalfWidth + 24) {
    const seed=(x+range)*31+z+range;
    // Keep the large footprints inside the block instead of placing them
    // beside the junction corners, where they obscure cross traffic and
    // camera views of approaching vehicles.
    this.addBuildingsAt(centerX,centerZ,seed);
   }
   if((x+z)%2===0){
    const seed=(x+range)*17+z+range;
    this.addTreeAt(centerX-28,centerZ+22,seed);
    this.addTreeAt(centerX+28,centerZ-22,seed+37);
   }
  }
 }

 graphPoint(nodeId){
  const [x,z]=nodeId.startsWith('uturn:')
   ?[this.uTurnNode(nodeId).x,this.uTurnNode(nodeId).z]:nodeId.split(',').map(Number);
  return {x:x*BLOCK,z:z*BLOCK};
 }
 uTurnNode(nodeId){
  const index=Number(nodeId.slice('uturn:'.length));
  const radius=config.world.uTurnRadiusMeters/BLOCK,angle=Math.PI+(Math.PI*index)/config.world.uTurnSegments;
  return {x:radius*Math.cos(angle),z:config.world.uTurnLocationBlocks+radius*Math.sin(angle)};
 }

 makeIntersectionMarkings(){
  const stripe=mat('#e5e4dc',.84),range=config.world.renderedRoadRadius,width=config.world.roadHalfWidth*2;
  const straightArrowShape=new THREE.Shape();
  straightArrowShape.moveTo(-.34,-1.55);straightArrowShape.lineTo(.34,-1.55);
  straightArrowShape.lineTo(.34,.2);straightArrowShape.lineTo(.88,.2);
  straightArrowShape.lineTo(0,1.55);straightArrowShape.lineTo(-.88,.2);straightArrowShape.lineTo(-.34,.2);
  const arrowGeometry=new THREE.ShapeGeometry(straightArrowShape);
  arrowGeometry.rotateX(-Math.PI/2);
  const addArrow=(x,z,rotation)=>{
   const arrow=new THREE.Mesh(arrowGeometry,stripe);arrow.position.set(x,.088,z);arrow.rotation.y=rotation;
   arrow.receiveShadow=true;this.root.add(arrow);staticMeshes.push(arrow);
  };
  for(let x=-range;x<=range;x++)for(let z=-range;z<=range;z++){
   const junctionX=x*BLOCK,junctionZ=z*BLOCK;
   // Stop bars sit before the crosswalk on all four approaches.
   box(this.root,stripe,junctionX-13,.087,junctionZ,.52,.025,width-.8);
   box(this.root,stripe,junctionX+13,.087,junctionZ,.52,.025,width-.8);
   box(this.root,stripe,junctionX,.087,junctionZ-13,width-.8,.025,.52);
   box(this.root,stripe,junctionX,.087,junctionZ+13,width-.8,.025,.52);
   // Lane arrows guide through traffic into each connected street leg.
   addArrow(junctionX-25,-3.2+junctionZ,-Math.PI/2);
   addArrow(junctionX+25,3.2+junctionZ,Math.PI/2);
   addArrow(3.2+junctionX,junctionZ-25,Math.PI);
   addArrow(-3.2+junctionX,junctionZ+25,0);
  }
 }

 makeStreetLighting(){
  const steel=mat('#4b5353',.68,.5),fixture=mat('#d7d0bb',.45,.12),range=config.world.renderedRoadRadius;
  fixture.emissive=new THREE.Color('#dfaa56');fixture.emissiveIntensity=.06;
  for(let x=-range;x<=range;x+=2)for(let z=-range;z<=range;z+=2){
   const junctionX=x*BLOCK,junctionZ=z*BLOCK;
   if(Math.abs(junctionX)<70&&Math.abs(junctionZ)<70)continue;
   const poleX=junctionX+14,poleZ=junctionZ+14,height=8.2;
   box(this.root,steel,poleX,height/2,poleZ,.24,height,.24,true);
   const arm=box(this.root,steel,poleX,7.85,poleZ-3.2,.16,.16,6.4,true);
   arm.rotation.x=-.04;
   box(this.root,fixture,poleX,7.72,poleZ-6.1,1.15,.18,.58,true);
  }
 }

 addTreeAt(x,z,seed){
  const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  const height=4.2+random()*1.3;
  const trunk=new THREE.Mesh(new THREE.CylinderGeometry(.16,.31,height,12),mat('#51463a',.96));
  trunk.position.set(x,height/2,z);trunk.castShadow=true;trunk.receiveShadow=true;
  this.root.add(trunk);staticMeshes.push(trunk);

  // Layered avenue-tree crowns add varied silhouettes without a mesh per leaf.
  this.foliageClusters??=[];
  const palettes=['#40583e','#4c6548','#58704e','#637856'];
  const leafScale=1.65+random()*.5;
  const clusters=[
   [0,height+1.7,0,leafScale*1.32],[-.95,height+1.3,.18,leafScale*.91],
   [.92,height+1.5,-.22,leafScale*.98],[.18,height+1.25,.92,leafScale*.94],
   [-.24,height+1.36,-.91,leafScale*.91],[random()-.5,height+2.55,random()-.5,leafScale*.82],
  ];
  for(const [offsetX,offsetY,offsetZ,radius] of clusters){
   const paletteIndex=Math.min(palettes.length-1,Math.floor(random()*palettes.length));
   this.foliageClusters.push({
    color:palettes[paletteIndex],x:x+offsetX+(random()-.5)*.35,
    y:offsetY+(random()-.5)*.35,z:z+offsetZ+(random()-.5)*.35,
    sx:radius*(.92+random()*.22),sy:radius*(.72+random()*.22),sz:radius*(.9+random()*.24),
   });
  }
 }
 makeTreeCanopies(){
  if(!this.foliageClusters?.length)return;
  const geometry=new THREE.SphereGeometry(1,14,10),groups=new Map();
  for(const cluster of this.foliageClusters){
   if(!groups.has(cluster.color))groups.set(cluster.color,[]);
   groups.get(cluster.color).push(cluster);
  }
  const matrix=new THREE.Matrix4(),position=new THREE.Vector3(),scale=new THREE.Vector3(),rotation=new THREE.Quaternion();
  for(const [color,clusters] of groups){
   const instances=new THREE.InstancedMesh(geometry,mat(color,.93),clusters.length);
   clusters.forEach((cluster,index)=>{
    position.set(cluster.x,cluster.y,cluster.z);scale.set(cluster.sx,cluster.sy,cluster.sz);
    matrix.compose(position,rotation,scale);instances.setMatrixAt(index,matrix);
   });
   instances.instanceMatrix.needsUpdate=true;instances.castShadow=true;instances.receiveShadow=true;
   this.root.add(instances);
  }
  this.foliageClusters.length=0;
 }

 addBuildingsAt(x,z,seed){
  const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};
  const facades=['#687174','#81796e','#5c696d','#91877a','#707a78','#9b958a'];
  const glass=['#425a60','#486166','#52696c','#4a5e62'];
  const radius=Math.max(Math.abs(x),Math.abs(z));
  const heightZones=config.world.buildingHeightZones;
  const foreground=radius<heightZones.foregroundRadiusMeters;
  const minimumHeight=foreground?heightZones.foregroundMinMeters:heightZones.skylineMinMeters;
  const maximumHeight=foreground?heightZones.foregroundMaxMeters:heightZones.skylineMaxMeters;
  const height=minimumHeight+random()*(maximumHeight-minimumHeight);
  const width=24+random()*14,depth=22+random()*14;
  const buildingFacade=this.facadeMaterials[Math.floor(random()*this.facadeMaterials.length)];
  const building=new THREE.Group();
  building.position.set(x,0,z);
  this.root.add(building);
  box(building,mat(facades[Math.floor(random()*facades.length)],.9),0,height/2,0,width,height,depth,true);

  // A modest roof plant room and parapet give the massing a more urban profile.
  box(building,mat('#646b69'),0,height+.3,0,width*.72,.6,depth*.72);
  box(building,mat('#777875'),width*.2,height+.8,depth*.12,width*.26,.4,depth*.24);

  const makeFacade=(panelWidth,panelHeight,position,rotationY)=>{
   const geometry=new THREE.PlaneGeometry(panelWidth,panelHeight);
   const uv=geometry.getAttribute('uv');
   for(let index=0;index<uv.count;index++)uv.setXY(index,uv.getX(index)*panelWidth/12,uv.getY(index)*panelHeight/20);
   uv.needsUpdate=true;
   const panel=new THREE.Mesh(geometry,buildingFacade);
   panel.position.copy(position);panel.rotation.y=rotationY;panel.receiveShadow=true;
   panel.userData.preserveUv=true;building.add(panel);staticMeshes.push(panel);
  };
  makeFacade(width-.3,height-.5,new THREE.Vector3(0,height/2,depth/2+.055),0);
  makeFacade(width-.3,height-.5,new THREE.Vector3(0,height/2,-depth/2-.055),Math.PI);
  makeFacade(depth-.3,height-.5,new THREE.Vector3(width/2+.055,height/2,0),Math.PI/2);
  makeFacade(depth-.3,height-.5,new THREE.Vector3(-width/2-.055,height/2,0),-Math.PI/2);
  box(building,mat('#304144',.3,.15),0,1.65,depth/2+.04,width*.58,2.5,.08);
  box(building,mat('#222d2f',.5),width*.31,1.35,depth/2+.09,width*.09,2.2,.08);
  box(building,mat('#383d3c'),0,.9,depth/2+.03,width*.16,1.8,.06);
 }
 makeFlyover(){
  const concrete=mat('#747a77',.93),deck=mat('#323739'),white=mat('#e1ded4');
  const flyoverX=2*BLOCK,start=-2*BLOCK,end=2*BLOCK,segments=44;
  const elevation=(z)=>Math.max(0,config.world.flyoverHeightMeters*(1-Math.max(0,Math.abs(z)-BLOCK)/BLOCK));
  for(let index=0;index<segments;index++){
   const z0=start+index*(end-start)/segments,z1=start+(index+1)*(end-start)/segments;
   const y0=elevation(z0),y1=elevation(z1),midZ=(z0+z1)/2,midY=(y0+y1)/2;
   const angle=Math.atan2(y1-y0,z1-z0),length=Math.hypot(z1-z0,y1-y0);
   const roadDeck=box(this.root,deck,flyoverX,midY,midZ,18,.65,length+.15,true);
   roadDeck.rotation.x=-angle;
   for(const side of [-1,1]){
    const rail=box(this.root,concrete,flyoverX+side*9.15,midY+.62,midZ,.48,.58,length,true);
    rail.rotation.x=-angle;
   }
   if(index%3===0){
    const laneMark=box(this.root,white,flyoverX,midY+.34,midZ,.14,.02,length*.5);
    laneMark.rotation.x=-angle;
   }
  }

  // The end points meet the ground-level road at the graph nodes (x=2, z=±2).
  for(let z=-BLOCK;z<=BLOCK;z+=44){
   const pierHeight=elevation(z)-.35;
   if(pierHeight<=0)continue;
   box(this.root,concrete,flyoverX,pierHeight/2,z,2.1,pierHeight,2.4,true);
   box(this.root,concrete,flyoverX,elevation(z)-.12,z,13,.35,2.8,true);
  }
 }
 makeUnderpass(){
  const x=config.world.underpassLocationBlocks*BLOCK;
  const depth=config.world.underpassDepthMeters;
  const segments=config.world.underpassGraphSegments;
  const roadWidth=config.world.roadHalfWidth*2-2;
  const yAt=(z)=>-depth*Math.min(1,Math.max(0,(2-Math.abs(z/BLOCK))/1.35));
  const asphalt=mat('#303638',.96);
  asphalt.map=loadSurfaceTexture(config.world.asphaltTextureUrl);asphalt.needsUpdate=true;
  const concrete=mat('#777d78',.94),mark=mat('#d9d6c8',.8);
  const sideLights=mat('#e9c978',.35,.12);
  sideLights.emissive=new THREE.Color('#e9a943');sideLights.emissiveIntensity=.55;
  for(let index=0;index<segments;index++){
   const z0=(-2+4*index/segments)*BLOCK;
   const z1=(-2+4*(index+1)/segments)*BLOCK;
   const y0=yAt(z0),y1=yAt(z1),midZ=(z0+z1)/2,midY=(y0+y1)/2;
   const angle=Math.atan2(y1-y0,z1-z0),length=Math.hypot(z1-z0,y1-y0);
   const road=box(this.root,asphalt,x,midY-.16,midZ,roadWidth,.34,length+.2,true);
   road.rotation.x=-angle;
   if(midY<-.25){
    const wallHeight=Math.max(.45,-midY+.18);
    for(const side of [-1,1]){
     const wall=box(this.root,concrete,x+side*(roadWidth/2+.7),(midY+.12)/2,midZ,.8,wallHeight,length+.5,true);
     wall.rotation.x=-angle;
     if(index%3===0){
      const light=box(this.root,sideLights,x+side*(roadWidth/2+.28),Math.min(-.45,midY+1.2),midZ,.14,.18,.65);
      light.rotation.x=-angle;
     }
    }
   }
   if(index%3===1){
    const laneMark=box(this.root,mark,x,midY+.025,midZ,.16,.025,length*.48);
    laneMark.rotation.x=-angle;
   }
  }

 }
 makeSignals(){const pole=mat('#515958'),head=mat('#292f30');for(let x=-2;x<=2;x+=2)for(let z=-2;z<=2;z+=2){if(x===0&&z===0)continue;let px=x*BLOCK,pz=z*BLOCK;let px2=px+(x>0?-11:11),pz2=pz+(z>0?-11:11);box(this.root,pole,px2,4.1,pz2,.22,8.2,.22,true);let obj=box(this.root,head,px2,7.3,pz2,1.05,1.8,.72);obj.castShadow=true;for(let k=0;k<3;k++){let light=new THREE.Mesh(new THREE.SphereGeometry(.19,12,8),mat(k===0?'#a5453a':k===1?'#c29847':'#517d57',.3));light.position.set(px2,7.85-k*.55,pz2+.37);this.root.add(light);}}}
 loadCarTemplate(){new GLTFLoader().load('/assets/graphite-four-door-sedan.glb',(gltf)=>{this.carTemplate=this.prepareCarTemplate(gltf.scene);for(const [id,car] of this.vehicles){const agent=this.agentLookup.get(id);if(agent)this.replaceWithDetailedCar(agent,car);}},undefined,(error)=>console.warn('Detailed sedan asset could not be loaded; using procedural vehicle fallback.',error));}
 prepareCarTemplate(source){
  source.updateMatrixWorld(true);
  const byMaterial=new Map();
  const addGeometry=(material,geometry)=>{if(!byMaterial.has(material))byMaterial.set(material,[]);byMaterial.get(material).push(geometry);};
  source.traverse((object)=>{
   if(!object.isMesh)return;
   const geometry=object.geometry.clone();
   geometry.applyMatrix4(object.matrixWorld);
   const materials=Array.isArray(object.material)?object.material:[object.material];
   if(materials.length>1&&geometry.groups.length&&geometry.index){
    for(const group of geometry.groups){
     const part=geometry.clone();
     const indices=geometry.index.array.slice(group.start,group.start+group.count);
     part.setIndex(new THREE.BufferAttribute(indices,1));
     part.clearGroups();
     addGeometry(materials[group.materialIndex],part);
    }
    geometry.dispose();
   }else addGeometry(materials[0],geometry);
  });
  const template=new THREE.Group();
  for(const [material,geometries]of byMaterial){
   const merged=mergeGeometries(geometries,false);
   for(const geometry of geometries)geometry.dispose();
   if(!merged)continue;
   template.add(new THREE.Mesh(merged,material));
  }
  template.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(template);
  const size=bounds.getSize(new THREE.Vector3());
  this.carTemplateDimensions={size,center:bounds.getCenter(new THREE.Vector3()),minimumY:bounds.min.y};
  return template;
 }
 makeDetailedCar(agent){
  const model=this.carTemplate.clone(true);
  const {size,center,minimumY}=this.carTemplateDimensions;
  const scale=4.45/Math.max(size.x,size.z);
  model.scale.setScalar(scale);
  model.position.set(-center.x*scale,-minimumY*scale,-center.z*scale);
  const orientedModel=new THREE.Group();
  orientedModel.rotation.y=-Math.PI/2;
  orientedModel.add(model);
  const sharedMaterials=new Map();
  model.traverse((object)=>{
   if(!object.isMesh)return;
   object.castShadow=true;object.receiveShadow=true;
   const materials=Array.isArray(object.material)?object.material:[object.material];
   const mapped=materials.map((material)=>{
    if(!sharedMaterials.has(material.uuid)){
     const colorMaterial=material.clone();
     if(material.name.toLowerCase().includes('paint')){
      colorMaterial.map=null;
      colorMaterial.color.set(agent.color);
      colorMaterial.metalness=.16;
      colorMaterial.roughness=.36;
      colorMaterial.emissive.set(agent.color);
      colorMaterial.emissiveIntensity=.035;
      colorMaterial.userData.vehiclePaintColor=agent.color;
     }
     sharedMaterials.set(material.uuid,colorMaterial);
    }
    return sharedMaterials.get(material.uuid);
   });
   object.material=Array.isArray(object.material)?mapped:mapped[0];
  });
  if(agent.type==='Ambulance'){
   for(const [x,color] of [[-.28,'#e33c37'],[.28,'#337de0']]){
    const beacon=box(orientedModel,mat(color,.24,.08).clone(),x,1.53,0,.42,.12,.27,true);
    beacon.material.emissive=new THREE.Color(color);
    beacon.material.emissiveIntensity=1.6;
    beacon.userData.emergencyBeacon=color;
   }
  }
  return orientedModel;
 }
 replaceWithDetailedCar(agent,car){
  if(agent.type==='Ambulance')return;
  const tag=car.children.find((child)=>child.userData.vehicleTag);
  const statusMarker=car.children.find((child)=>child.userData.vehicleStatusMarker);
  for(const child of [...car.children]){
   if(child===tag||child===statusMarker)continue;
   child.traverse((object)=>{
    if(object.isMesh&&!Array.from(boxGeometryCache.values()).includes(object.geometry))object.geometry.dispose();
    if(object.isSprite)object.material.map?.dispose();
   });
   car.remove(child);
  }
  car.add(this.makeDetailedCar(agent));
  if(tag)car.add(tag);
  if(statusMarker)car.add(statusMarker);
 }
 makeAmbulanceCar(agent){
  const group=new THREE.Group();group.userData.agent=agent.id;group.userData.ambulance=true;
  const white=new THREE.MeshStandardMaterial({color:'#f4f3ed',roughness:.38,metalness:.08});
  white.userData.vehiclePaintColor='#f4f3ed';
  const red=mat('#c52e32',.42,.04),glass=mat('#233b45',.2,.18),rubber=mat('#171a1b',.9),silver=mat('#aeb5b2',.3,.55);
  const rounded=(width,height,length,radius,x,y,z,material)=>{
   const mesh=new THREE.Mesh(new RoundedBoxGeometry(width,height,length,3,radius),material);
   mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;
  };
  rounded(2.02,.48,4.65,.15,0,.62,0,mat('#292d2e',.88));
  rounded(1.94,1.7,4.25,.23,0,1.45,.06,white);
  rounded(1.72,.44,1.42,.14,0,1.82,-1.36,white);
  box(group,glass,0,1.83,-2.085,1.48,.66,.055);
  box(group,glass,0,1.79,2.19,1.18,.72,.055);
  for(const side of [-1,1]){
   for(const z of [-1.52,1.46]){
    const tire=new THREE.Mesh(new THREE.CylinderGeometry(.37,.37,.25,24),rubber);
    tire.rotation.z=Math.PI/2;tire.position.set(side*1.01,.39,z);tire.castShadow=true;group.add(tire);
    const hub=new THREE.Mesh(new THREE.CylinderGeometry(.2,.2,.27,20),silver);
    hub.rotation.z=Math.PI/2;hub.position.copy(tire.position);group.add(hub);
   }
   for(const z of [-1.2,-.12,1.02])box(group,glass,side*1.005,1.78,z,.035,.55,.78);
   box(group,red,side*1.015,1.06,.13,.035,.25,4.0);
   box(group,mat('#f8f4e8'),side*1.04,1.06,.13,.035,.07,3.85);
   box(group,red,side*1.045,1.55,.76,.05,.75,.12);
   box(group,red,side*1.046,1.55,.76,.05,.12,.68);
   for(const z of [-1.94,1.95])box(group,z<0?mat('#fff1d5',.3):red,side*.69,.82,z,.35,.17,.045);
  }
  const labelCanvas=document.createElement('canvas');labelCanvas.width=512;labelCanvas.height=128;
  const ctx=labelCanvas.getContext('2d');ctx.fillStyle='#c52e32';ctx.font='bold 78px Arial';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('AMBULANCE',256,65);
  const labelTexture=new THREE.CanvasTexture(labelCanvas);labelTexture.colorSpace=THREE.SRGBColorSpace;
  for(const side of [-1,1]){
   const label=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture,transparent:true,depthWrite:false}));
   label.position.set(side*1.08,1.48,-.25);label.scale.set(1.95,.49,1);label.renderOrder=4;group.add(label);
  }
  const rearLabel=new THREE.Sprite(new THREE.SpriteMaterial({map:labelTexture,transparent:true,depthWrite:false}));
  rearLabel.position.set(0,1.48,2.25);rearLabel.scale.set(1.72,.43,1);rearLabel.renderOrder=4;group.add(rearLabel);
  box(group,red,0,1.08,2.24,.68,.11,.045);
  box(group,red,0,1.08,2.24,.11,.68,.045);
  const lightbar=box(group,mat('#252a2b',.45),0,2.39,-.28,.72,.13,.3,true);
  for(const [x,color] of [[-.24,'#f12b30'],[.24,'#297df5']]){
   const beacon=box(group,mat(color,.2,.05).clone(),x,2.43,-.28,.34,.16,.3,true);
   beacon.material.emissive=new THREE.Color(color);beacon.material.emissiveIntensity=2.1;beacon.userData.emergencyBeacon=color;
  }
  const grille=box(group,mat('#252a2b',.55),0,1.03,-2.12,.7,.28,.06);
  grille.userData.ambulanceDetail=true;
  return this.addVehicleTag(group,agent);
 }
 makeCar(agent) {
  if(agent.type==='Ambulance')return this.makeAmbulanceCar(agent);
  if(this.carTemplate){const car=new THREE.Group();car.userData.agent=agent.id;car.add(this.makeDetailedCar(agent));return this.addVehicleTag(car,agent);}
  const group = new THREE.Group();
  group.userData.agent = agent.id;
  const body = mat(agent.color, .34, .12).clone();
  body.userData.vehiclePaintColor=agent.color;
  const glass = mat('#24353b', .2, .15);
  const rubber = mat('#16191a', .92);
  const silver = mat('#aab3b2', .34, .55);
  const lamp = mat('#fff0ca', .22);
  const tail = mat('#b8322c', .3);
  const roundedMesh = (width, height, length, radius, x, y, z, material) => {
   const geometry = new RoundedBoxGeometry(width, height, length, 3, radius);
   const mesh = new THREE.Mesh(geometry, material);
   mesh.position.set(x, y, z);
   mesh.castShadow = true;
   mesh.receiveShadow = true;
   group.add(mesh);
   return mesh;
  };

  roundedMesh(2.02, .66, 4.45, .16, 0, .76, 0, body);
  roundedMesh(1.72, .72, 2.36, .25, 0, 1.25, -.16, body);
  box(group, glass, 0, 1.3, -.24, 1.62, .39, .06);
  box(group, glass, 0, 1.3, .66, 1.62, .39, .06);
  const windshield = new THREE.Mesh(new THREE.PlaneGeometry(1.52, .73), glass);
  windshield.position.set(0, 1.31, -.94);
  windshield.rotation.x = -.46;
  group.add(windshield);
  const rearWindow = windshield.clone();
  rearWindow.position.z = .74;
  rearWindow.rotation.x = .46;
  group.add(rearWindow);

  for (const side of [-1, 1]) {
   for (const axle of [-1.43, 1.43]) {
    const tire = new THREE.Mesh(new THREE.CylinderGeometry(.37, .37, .24, 24), rubber);
    tire.rotation.z = Math.PI / 2;
    tire.position.set(side * 1.03, .38, axle);
    tire.castShadow = true;
    group.add(tire);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(.2, .2, .255, 20), silver);
    hub.rotation.z = Math.PI / 2;
    hub.position.copy(tire.position);
    group.add(hub);
   }
   box(group, lamp, side * .7, .79, -2.23, .42, .16, .035);
   box(group, tail, side * .7, .79, 2.23, .38, .17, .04);
   box(group, body, side * .75, .94, -.3, .15, .11, .34);
  }
  box(group, mat('#454a49'), 0, .72, -2.27, 1.1, .11, .05);

  if (agent.type === 'Ambulance') {
   roundedMesh(1.62, .5, 1.75, .16, 0, 1.72, .02, mat('#f0efea', .34, .08));
   for (const [x, color] of [[-.28, '#e33c37'], [.28, '#337de0']]) {
    const beacon = box(group, mat(color, .24, .08).clone(), x, 2.03, -.06, .42, .13, .27, true);
    beacon.material.emissive = new THREE.Color(color);
    beacon.material.emissiveIntensity = 1.6;
    beacon.userData.emergencyBeacon=color;
   }
  }

  const tagCanvas = document.createElement('canvas');
  tagCanvas.width = 256;
  tagCanvas.height = 96;
  const context = tagCanvas.getContext('2d');
  context.fillStyle = '#10181de8';
  context.beginPath();
  context.roundRect(5, 5, 246, 86, 18);
  context.fill();
  context.strokeStyle = '#83d9ce';
  context.lineWidth = 5;
  context.stroke();
  context.fillStyle = '#f1f6f3';
  context.font = 'bold 48px Arial';
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(agent.id, 128, 49);
  const tagTexture = new THREE.CanvasTexture(tagCanvas);
  return this.addVehicleTag(group,agent,tagTexture);
 }
 addVehicleTag(group,agent,texture){
  if(!texture){
   const tagCanvas=document.createElement('canvas');tagCanvas.width=256;tagCanvas.height=96;
   const context=tagCanvas.getContext('2d');context.fillStyle='#10181de8';context.beginPath();context.roundRect(5,5,246,86,18);context.fill();context.strokeStyle='#83d9ce';context.lineWidth=5;context.stroke();context.fillStyle='#f1f6f3';context.font='bold 48px Arial';context.textAlign='center';context.textBaseline='middle';context.fillText(agent.id,128,49);texture=new THREE.CanvasTexture(tagCanvas);
  }
  const tag=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false}));tag.userData.vehicleTag=true;tag.scale.set(config.rendering.vehicleTagWidthMeters,config.rendering.vehicleTagHeightMeters,1);tag.position.set(0,group.userData.ambulance?3.05:2.45,0);tag.renderOrder=3;group.add(tag);
  const marker=new THREE.Mesh(
   new THREE.TorusGeometry(config.rendering.vehicleStatusMarkerRadiusMeters,.075,8,32),
   new THREE.MeshBasicMaterial({color:'#ffffff',transparent:true,opacity:.9,depthWrite:false}),
  );
  marker.rotation.x=-Math.PI/2;marker.position.y=.12;marker.renderOrder=2;marker.userData.vehicleStatusMarker=true;group.add(marker);
  return group;
 }
  update(sim, selected) {
    this.agentLookup=new Map(sim.agents.map((agent)=>[agent.id,agent]));
    for (const agent of sim.agents) {
      let car = this.vehicles.get(agent.id);
      if (!car) {
        car = this.makeCar(agent);
        this.vehicles.set(agent.id, car);
        this.root.add(car);
      }
      const position = sim.position(agent);
      if (position) {
        car.position.set(position.x, position.y + 0.05, position.z);
        car.rotation.y = position.heading;
        car.visible = true;
        const routeActive = agent.replans > 0
          && sim.time - agent.routeChangedAt < config.rendering.adaptiveRouteDisplaySeconds;
        const alertActive = sim.time < agent.alertExpiresAt
          && !agent.lastAlertDecision.toLowerCase().includes('no route conflict');
        const conflictRole = sim.intersectionConflict?.priorityVehicleId === agent.id
          ? 'priority'
          : sim.intersectionConflict?.yieldingVehicleId === agent.id ? 'yielding' : '';
        const suddenBraking = sim.time < agent.suddenBrakeUntil
          && agent.status.startsWith('Braking');
        const emergencyYielding = agent.yieldUntil > sim.time && agent.status.startsWith('Yielding');
        const visualRole = conflictRole || (suddenBraking ? 'braking' : emergencyYielding ? 'yielding' : agent.replanningVisualUntil > sim.time
          && agent.replanningVisualAt <= sim.time ? 'replanning'
          : agent.messageRoleExpiresAt > sim.time ? agent.messageRole : '');
        const roleColor = {
          sending: '#378dff',
          receiving: '#45e3ef',
          replanning: '#ffb833',
          priority: config.rendering.intersectionPriorityColor,
          yielding: config.rendering.intersectionYieldColor,
          braking: '#ff5148',
        }[visualRole];
        const highlightColor = roleColor ?? (routeActive || alertActive ? '#ffad22' : null);
        const highlighted = Boolean(highlightColor);
        const flash = Math.floor(sim.time * 5) % 2;
        car.traverse((object) => {
          if (object.userData.vehicleTag) {
            object.visible = agent.id === selected
              || highlighted
              || (agent.type === 'Ambulance' && sim.mode === 'emergency');
          }
          if (object.userData.vehicleStatusMarker) {
            object.visible = highlighted;
            object.material.color.set(highlightColor ?? '#ffffff');
          }
          if (object.isMesh && object.material) {
            const materials=Array.isArray(object.material)?object.material:[object.material];
            for(const material of materials){
              if(!material.userData?.vehiclePaintColor||!material.emissive)continue;
              material.emissive.set(highlighted?highlightColor:material.userData.vehiclePaintColor);
              material.emissiveIntensity=highlighted?(flash?0.72:0.28):0.035;
            }
          }
          if (!object.userData.emergencyBeacon) return;
          const red = object.userData.emergencyBeacon === '#f12b30';
          object.material.emissiveIntensity = red === (Math.floor(sim.time * 4) % 2 === 0) ? 3.2 : 0.05;
        });
      } else {
        car.visible = false;
      }
    }

    const agent = sim.agents.find((vehicle) => vehicle.id === selected);
    const signature = agent ? `${agent.id}:${agent.index}:${agent.replans}:${agent.route.join(';')}` : '';
    if (signature !== this.routeSignature) {
      this.clearRouteLine();
      this.routeSignature = signature;
      if (agent && agent.route.length > 1) {
        const current = sim.position(agent);
        const points = current ? [
          new THREE.Vector3(current.x, current.y + 0.32, current.z),
          ...getRoutePolyline(sim.graph, agent.route.slice(agent.index), 0.32).slice(1)
            .map((point) => new THREE.Vector3(point.x, point.y, point.z)),
        ] : [];
        if (points.length > 1) {
          const geometry = new THREE.BufferGeometry().setFromPoints(points);
          const material = new THREE.LineDashedMaterial({
            color: agent.replans ? '#edb65b' : '#32cfc2',
            dashSize: 5,
            gapSize: 3,
            transparent: true,
            opacity: 0.85,
          });
          this.routeLine = new THREE.Line(geometry, material);
          this.routeLine.computeLineDistances();
          this.scene.add(this.routeLine);
        }
      }
    }

    // Keep the route origin attached to the moving vehicle between junctions.
    if (this.routeLine && agent) {
      const current = sim.position(agent);
      if (current) {
        this.routeLine.geometry.attributes.position.setXYZ(0, current.x, current.y + 0.32, current.z);
        this.routeLine.geometry.attributes.position.needsUpdate = true;
        this.routeLine.computeLineDistances();
      }
    }

    this.updateAdaptiveRoutes(sim, selected);
    this.updateEvents(sim);
    this.updateLinks(sim, selected);
  }

  clearRouteLine() {
    if (!this.routeLine) return;
    this.scene.remove(this.routeLine);
    this.routeLine.geometry.dispose();
    this.routeLine.material.dispose();
    this.routeLine = null;
  }

  updateAdaptiveRoutes(sim, selected) {
    const visible = new Set();
    const candidates = sim.agents
      .filter((agent) => agent.replans && !agent.arrived
        && sim.time - agent.routeChangedAt < config.rendering.adaptiveRouteDisplaySeconds)
      .map((agent) => ({ agent, position: sim.position(agent) }))
      .filter((item) => item.position)
      .sort((a, b) => {
        if (a.agent.id === selected) return -1;
        if (b.agent.id === selected) return 1;
        const cameraDistance = (item) => Math.hypot(
          item.position.x - this.target.x,
          item.position.z - this.target.z,
        );
        return cameraDistance(a) - cameraDistance(b);
      })
      .slice(0, config.rendering.maxAdaptiveRouteOverlays);
    for (const { agent, position } of candidates) {
      if (!agent.replans || agent.arrived
        || sim.time - agent.routeChangedAt >= config.rendering.adaptiveRouteDisplaySeconds) continue;
      visible.add(agent.id);
      const signature = `${agent.index}:${agent.route.join(';')}`;
      let record = this.adaptiveRouteLines.get(agent.id);
      if (!record || record.signature !== signature) {
        if (record) this.removeAdaptiveRoute(agent.id, record);
        const points = [
          new THREE.Vector3(position.x, position.y + 0.42, position.z),
          ...getRoutePolyline(sim.graph, agent.route.slice(agent.index), 0.42).slice(1)
            .map((point) => new THREE.Vector3(point.x, point.y, point.z)),
        ];
        if (points.length < 2) continue;
        const curve=new THREE.CatmullRomCurve3(points);
        const geometry=new THREE.TubeGeometry(
          curve,Math.max(32,points.length*4),config.rendering.adaptiveRouteWidthMeters/2,8,false,
        );
        const material=new THREE.MeshStandardMaterial({
          color:config.rendering.adaptiveRouteColor,
          emissive:config.rendering.adaptiveRouteEmissiveColor,
          emissiveIntensity:1.25,
          roughness:.38,metalness:.05,transparent:true,opacity:.94,
        });
        const line=new THREE.Mesh(geometry,material);
        line.renderOrder=3;line.castShadow=false;line.receiveShadow=false;
        this.scene.add(line);
        record = { line, signature };
        this.adaptiveRouteLines.set(agent.id, record);
      }
    }
    for (const [id, record] of this.adaptiveRouteLines) {
      if (!visible.has(id)) this.removeAdaptiveRoute(id, record);
    }
  }

  removeAdaptiveRoute(id, record) {
    this.scene.remove(record.line);
    record.line.geometry.dispose();
    record.line.material.dispose();
    this.adaptiveRouteLines.delete(id);
  }

  updateEvents(sim) {
    const key = sim.blockage?.edge.join('|') ?? null;
    if (key === this.renderedBlockageKey) return;
    for (const object of this.eventObjects) {
      this.scene.remove(object);
      if (object.userData.disposeGeometryOnRemoval) {
        object.geometry.dispose();
        object.material.map?.dispose();
        object.material.dispose();
      }
    }
    this.eventObjects = [];
    this.renderedBlockageKey = key;
    if (!sim.blockage) return;

    const x = sim.blockage.point.x * BLOCK;
    const z = sim.blockage.point.z * BLOCK;
    const y = sim.blockage.point.y ?? 0;
    const [from, to] = sim.blockage.edge.map((id) => sim.graph.node(id));
    const dx = to.x - from.x,dz = to.z - from.z,length = Math.hypot(dx,dz) || 1;
    const normalX = -dz / length,normalZ = dx / length;
    const rotation = Math.atan2(-normalZ,normalX);
    const blockedPath = new THREE.LineCurve3(
      new THREE.Vector3(from.x * BLOCK, (from.y ?? y) + .34, from.z * BLOCK),
      new THREE.Vector3(to.x * BLOCK, (to.y ?? y) + .34, to.z * BLOCK),
    );
    const blockedRoute = new THREE.Mesh(
      new THREE.TubeGeometry(blockedPath, 24, config.rendering.blockedRouteWidthMeters / 2, 8, false),
      new THREE.MeshStandardMaterial({
        color: config.rendering.blockedRouteColor,
        emissive: config.rendering.blockedRouteColor,
        emissiveIntensity: 1.5,
        roughness: .35,
      }),
    );
    blockedRoute.renderOrder = 4;
    blockedRoute.userData.disposeGeometryOnRemoval = true;
    this.scene.add(blockedRoute);
    this.eventObjects.push(blockedRoute);
    const barricade = box(this.scene,mat('#e76b32'),x,y+.72,z,config.world.roadHalfWidth*1.65,1.25,.42,true);
    barricade.rotation.y = rotation;
    this.eventObjects.push(barricade);
    const signCanvas=document.createElement('canvas');
    signCanvas.width=1024;signCanvas.height=192;
    const signContext=signCanvas.getContext('2d');
    signContext.fillStyle='#8f2925';signContext.fillRect(0,0,signCanvas.width,signCanvas.height);
    signContext.strokeStyle='#f1e8d7';signContext.lineWidth=12;signContext.strokeRect(7,7,signCanvas.width-14,signCanvas.height-14);
    signContext.fillStyle='#fff8ea';signContext.font='bold 82px Arial';
    signContext.textAlign='center';signContext.textBaseline='middle';
    signContext.fillText('ROAD CLOSED',signCanvas.width/2,signCanvas.height/2-20);
    signContext.font='bold 32px Arial';
    signContext.fillText(`SEGMENT ${from.id} TO ${to.id}`,signCanvas.width/2,signCanvas.height/2+61);
    const signTexture=new THREE.CanvasTexture(signCanvas);
    signTexture.colorSpace=THREE.SRGBColorSpace;
    const sign=new THREE.Mesh(
      new THREE.PlaneGeometry(12,2.25),
      new THREE.MeshBasicMaterial({map:signTexture,side:THREE.DoubleSide,toneMapped:false}),
    );
    sign.position.set(x,y+2.55,z);
    sign.rotation.y=rotation;
    sign.renderOrder=4;
    sign.userData.disposeGeometryOnRemoval=true;
    this.scene.add(sign);this.eventObjects.push(sign);
    for(let band=-3;band<=3;band+=2){
      const stripe=box(this.scene,mat('#f0e6d2'),x+normalX*band*2.5,y+.74,z+normalZ*band*2.5,.82,1.05,.46,true);
      stripe.rotation.y=rotation;this.eventObjects.push(stripe);
    }
    const coneMaterial=mat('#f07831'),reflector=mat('#f4e8d4');
    for(let index=-3;index<=3;index++){
      const offset=index*2.55;
      const cone=new THREE.Mesh(new THREE.ConeGeometry(.38,1.25,12),coneMaterial);
      cone.position.set(x+normalX*offset,y+.66,z+normalZ*offset);cone.castShadow=true;cone.receiveShadow=true;
      this.scene.add(cone);this.eventObjects.push(cone);
      const bandMesh=new THREE.Mesh(new THREE.CylinderGeometry(.29,.34,.18,12),reflector);
      bandMesh.position.set(cone.position.x,y+.68,cone.position.z);this.scene.add(bandMesh);this.eventObjects.push(bandMesh);
    }
    const beacon = new THREE.PointLight('#ff793c', 65, 36);
    beacon.position.set(x, y+3.3, z);
    this.scene.add(beacon);
    this.eventObjects.push(beacon);
  }
  updateLinks(sim, selected){
   const bubbleAnchors=[];
   const messageById=new Map(sim.messages.map((message)=>[message.id,message]));
   const bubbleKeys=new Set(sim.links
    .map((link)=>{
     const message=messageById.get(link.messageId);
     const receiver=this.vehicles.get(link.to);
     const decision=message?.decision?.toLowerCase()??'';
     const priority=decision.includes('replan')||decision.includes('rerout')?0
      :decision.includes('yield')||decision.includes('moving aside')||decision.includes('waiting at crossing')?1
       :decision.includes('caution')||decision.includes('continuing')?2:3;
     return message&&receiver&&!decision.includes('no route conflict')
      ?{key:`${link.from}-${link.to}-${link.messageId}`,priority,
       focus:link.to===selected?0:1,hop:message.hop,
       distance:Math.hypot(receiver.position.x-this.target.x,receiver.position.z-this.target.z)}
      :null;
    })
    .filter(Boolean)
    .sort((a,b)=>a.focus-b.focus||a.priority-b.priority||a.hop-b.hop||a.distance-b.distance)
    .slice(0,config.rendering.maxMessageBubbles)
    .map((item)=>item.key));
   for(const linkState of sim.links){
    const key=`${linkState.from}-${linkState.to}-${linkState.messageId}`;
    let rendered=this.links.get(key);
    const sender=this.vehicles.get(linkState.from),receiver=this.vehicles.get(linkState.to);
    if(!sender||!receiver)continue;
    const message=sim.messages.find((item)=>item.id===linkState.messageId);
    // Keep the 3D overlay focused on receivers whose driving decision changed.
    // Clear-route receivers still get the V2V message in the trace panel.
    if(message?.decision?.toLowerCase().includes('no route conflict'))continue;
    if(!rendered){
     const geometry=new THREE.BufferGeometry();
     const line=new THREE.Line(geometry,new THREE.LineDashedMaterial({color:'#4298ff',dashSize:2.2,gapSize:1.1,transparent:true,opacity:.92,depthTest:true}));
     line.renderOrder=4;this.scene.add(line);
     const packet=new THREE.Mesh(new THREE.SphereGeometry(config.communication.packetRadiusMeters,12,10),new THREE.MeshBasicMaterial({color:'#62b8ff'}));
     packet.renderOrder=5;this.scene.add(packet);
     rendered={line,bubble:null,packet,until:linkState.until};this.links.set(key,rendered);
    }
    if(bubbleKeys.has(key)&&!rendered.bubble){
     rendered.bubble=makeMessageBubble(message);this.scene.add(rendered.bubble);
    }else if(!bubbleKeys.has(key)&&rendered.bubble){
     this.scene.remove(rendered.bubble);rendered.bubble.material.map?.dispose();rendered.bubble.material.dispose();
     rendered.bubble=null;
    }
    const from=sender.position.clone().add(new THREE.Vector3(0,3.2,0));
    const to=receiver.position.clone().add(new THREE.Vector3(0,3.2,0));
    const control=from.clone().lerp(to,.5).add(new THREE.Vector3(0,config.communication.communicationArcHeightMeters,0));
    const arc=new THREE.QuadraticBezierCurve3(from,control,to);
    rendered.line.geometry.setFromPoints(arc.getPoints(24));rendered.line.computeLineDistances();
    const progress=message?THREE.MathUtils.clamp((sim.time-message.timestamp)/config.communication.linkDurationSeconds,0,1):.5;
    rendered.packet.position.copy(arc.getPoint(progress));
    if(rendered.bubble){
     const anchor=bubbleAnchors.find((candidate)=>Math.hypot(
      receiver.position.x-candidate.x,receiver.position.z-candidate.z,
     )<config.rendering.messageBubbleClearanceMeters);
     let stack=0;
     if(anchor){stack=anchor.count;anchor.count+=1;}
     else bubbleAnchors.push({x:receiver.position.x,z:receiver.position.z,count:1});
     const scale=Math.max(.55,Math.min(1,this.radius/config.rendering.sequenceOverviewRadiusMeters));
     rendered.bubble.scale.set(
      config.rendering.messageBubbleWidthMeters*scale,
      config.rendering.messageBubbleHeightMeters*scale,
      1,
     );
     rendered.bubble.position.set(
      to.x,
      to.y+stack*config.rendering.messageBubbleStackSpacingMeters*scale,
      to.z,
     );
    }
   }
   for(const [key,rendered]of this.links)if(rendered.until<=sim.time){
    this.scene.remove(rendered.line);rendered.line.geometry.dispose();rendered.line.material.dispose();
    if(rendered.bubble){this.scene.remove(rendered.bubble);rendered.bubble.material.map?.dispose();rendered.bubble.material.dispose();}
    this.scene.remove(rendered.packet);rendered.packet.geometry.dispose();rendered.packet.material.dispose();
    this.links.delete(key);
   }
  }
 setupCamera(){this.target=new THREE.Vector3(0,1.2,0);this.yaw=config.rendering.streetCameraYaw;this.pitch=config.rendering.streetCameraPitch;this.radius=config.rendering.streetCameraRadius;this.cameraMode='street';this.cameraAutoFollow=true;this.presentationFollowing=false;this.cameraTransition=null;this.updateCamera();let dragging=false,px=0,py=0,c=this.renderer.domElement;c.addEventListener('pointerdown',e=>{dragging=true;this.cameraTransition=null;this.cameraAutoFollow=false;this.presentationFollowing=false;px=e.clientX;py=e.clientY;c.setPointerCapture(e.pointerId);});c.addEventListener('pointerup',()=>dragging=false);c.addEventListener('pointermove',e=>{if(!dragging)return;this.yaw-=(e.clientX-px)*.005;this.pitch=Math.max(.1,Math.min(1.25,this.pitch+(e.clientY-py)*.004));px=e.clientX;py=e.clientY;this.updateCamera();});c.addEventListener('wheel',e=>{e.preventDefault();this.cameraTransition=null;this.radius=THREE.MathUtils.clamp(this.radius*Math.exp(e.deltaY*.001),config.rendering.cameraMinRadius,config.rendering.cameraMaxRadius);this.cameraAutoFollow=false;this.presentationFollowing=false;this.updateCamera();},{passive:false});}
 updateCamera(){let r=this.radius,cp=Math.cos(this.pitch);this.camera.position.set(this.target.x+r*cp*Math.sin(this.yaw),this.target.y+r*Math.sin(this.pitch),this.target.z+r*cp*Math.cos(this.yaw));this.camera.lookAt(this.target);}
 setCamera(mode,selectedPosition,transitionSeconds=config.rendering.cameraTransitionSeconds){
  this.cameraMode=mode;this.cameraAutoFollow=mode==='street';
  const to={
   target:new THREE.Vector3(
    (selectedPosition?.x??0)+(mode==='street'&&Number.isFinite(selectedPosition?.heading)
      ?Math.sin(selectedPosition.heading)*config.rendering.streetCameraLookAheadMeters:0),
    mode==='street'?(selectedPosition?.y??0)+1.2:(selectedPosition?.y??0),
    (selectedPosition?.z??0)+(mode==='street'&&Number.isFinite(selectedPosition?.heading)
      ?Math.cos(selectedPosition.heading)*config.rendering.streetCameraLookAheadMeters:0),
   ),
   yaw:Number.isFinite(selectedPosition?.heading)
    ?selectedPosition.heading+(mode==='street'?Math.PI:0)
    :(mode==='overview'?.72:config.rendering.streetCameraYaw),
   pitch:mode==='overview'
    ?(selectedPosition?.pitch??config.rendering.overviewCameraPitch):config.rendering.streetCameraPitch,
   radius:mode==='overview'
    ?(selectedPosition?.radius??config.rendering.overviewCameraRadius):config.rendering.streetCameraRadius,
  };
  to.radius=THREE.MathUtils.clamp(to.radius,config.rendering.cameraMinRadius,config.rendering.cameraMaxRadius);
  if(transitionSeconds<=0){
   this.target.copy(to.target);this.yaw=to.yaw;this.pitch=to.pitch;this.radius=to.radius;this.cameraTransition=null;this.updateCamera();return;
  }
  this.cameraTransition={
   from:{target:this.target.clone(),yaw:this.yaw,pitch:this.pitch,radius:this.radius},
   to,elapsed:0,duration:transitionSeconds,
  };
 }
 updateCameraTransition(frameSeconds){
  const transition=this.cameraTransition;
  if(!transition)return;
  transition.elapsed=Math.min(transition.duration,transition.elapsed+Math.max(0,frameSeconds));
  const raw=transition.duration?transition.elapsed/transition.duration:1;
  const t=raw*raw*(3-2*raw);
  this.target.lerpVectors(transition.from.target,transition.to.target,t);
  const yawDelta=Math.atan2(
   Math.sin(transition.to.yaw-transition.from.yaw),
   Math.cos(transition.to.yaw-transition.from.yaw),
  );
  this.yaw=transition.from.yaw+yawDelta*t;
  this.pitch=THREE.MathUtils.lerp(transition.from.pitch,transition.to.pitch,t);
  this.radius=THREE.MathUtils.lerp(transition.from.radius,transition.to.radius,t);
  if(raw>=1)this.cameraTransition=null;
  this.updateCamera();
 }
 resetCamera(){this.setCamera('street',{x:0,z:0});}
 resize(){let w=this.container.clientWidth,h=this.container.clientHeight;this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.renderer.setSize(w,h);}
 render(){this.renderer.render(this.scene,this.camera);}
}
