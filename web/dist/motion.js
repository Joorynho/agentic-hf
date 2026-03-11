'use strict';

// ================================================================
//  SCROLL TRAVERSAL & CAMERA
// ================================================================

function animateCameraToFloor(floorIdx) {
  const floor = FLOORS[floorIdx];
  const targetY = floor.y + 5;
  const targetZ = 13;

  gsap.killTweensOf(cameraTweenState);
  gsap.to(cameraTweenState, {
    baseY: targetY,
    baseZ: targetZ,
    lookY: floor.y,
    duration: TIMING.FLOOR_FOCUS,
    ease: EASE.CAMERA,
  });

  FLOORS.forEach((fd, i) => {
    const st = floorAnimState[i];
    if (!st) return;
    const isSelected = (i === floorIdx);
    const targetScreenEmissive = isSelected ? 0.85 : 0.65;
    const targetTrimEmissive = isSelected ? 0.65 : 0.45;
    const targetLightInt = isSelected ? 2.2 : 1.5;

    gsap.to(st, {
      baseLightInt: targetLightInt,
      duration: TIMING.FLOOR_FOCUS,
      ease: EASE.PANEL,
      onUpdate: () => {
        st.pointLight.intensity = st.baseLightInt;
        if (st.rimLight) st.rimLight.intensity = isSelected ? 0.8 : 0.5;
      },
    });

    st.screens.forEach(m => {
      gsap.to(m, { emissiveIntensity: targetScreenEmissive, duration: TIMING.FLOOR_FOCUS, ease: EASE.PANEL });
    });
    gsap.to(st.trimMat, { emissiveIntensity: targetTrimEmissive, duration: TIMING.FLOOR_FOCUS, ease: EASE.PANEL });

    if (st.group) {
      st.group.traverse(child => {
        if (child.isMesh && child.material && !child.material._isScreen) {
          if (child.material._baseToneFactor === undefined) {
            child.material._baseToneFactor = 1.0;
          }
        }
      });
    }

    st.floorState = isSelected ? 'selected' : 'idle';
  });

  document.getElementById('back-to-building').style.display = 'block';
}

function updateFloorContext(floorIdx) {
  const floor = FLOORS[floorIdx];

  const floorHeader = document.querySelector('.floor-header');
  floorHeader.innerHTML = `
    <div class="floor-title" style="color: ${floor.hex}">
      ${floor.name}
    </div>
    <div class="floor-label">${floor.label}</div>
  `;

  const breadcrumb = document.querySelector('.floor-breadcrumb');
  breadcrumb.innerHTML = Array.from({length: 6}, (_, i) =>
    `<span class="crumb ${i === floorIdx ? 'active' : ''}" onclick="scrollToFloor(${i})">●</span>`
  ).join('');
}

function scrollToFloor(floorIdx) {
  if (isScrolling || floorIdx === currentFloor) return;
  currentFloor = floorIdx;
  animateCameraToFloor(currentFloor);
  updateFloorContext(currentFloor);
  isScrolling = true;
  setTimeout(() => { isScrolling = false; }, 250);
}

function backToBuilding() {
  gsap.killTweensOf(cameraTweenState);
  gsap.to(cameraTweenState, {
    baseY: 7,
    baseZ: 30,
    lookY: 4,
    duration: TIMING.RETURN_OVERVIEW,
    ease: EASE.CAMERA,
  });

  FLOORS.forEach((fd, i) => {
    const st = floorAnimState[i];
    if (!st) return;
    gsap.to(st, {
      baseLightInt: 1.8,
      duration: TIMING.RETURN_OVERVIEW,
      ease: EASE.PANEL,
      onUpdate: () => {
        st.pointLight.intensity = st.baseLightInt;
        if (st.rimLight) st.rimLight.intensity = 0.6;
      },
    });
    st.screens.forEach(m => {
      gsap.to(m, { emissiveIntensity: 0.65, duration: TIMING.RETURN_OVERVIEW, ease: EASE.PANEL });
    });
    gsap.to(st.trimMat, { emissiveIntensity: 0.45, duration: TIMING.RETURN_OVERVIEW, ease: EASE.PANEL });
    st.floorState = 'idle';
  });

  currentFloor = -1;
  document.getElementById('back-to-building').style.display = 'none';

  const floorHeader = document.querySelector('.floor-header');
  floorHeader.innerHTML = `
    <div class="floor-title" style="color: var(--cyan)">OVERVIEW</div>
    <div class="floor-label">ALL FLOORS · SCROLL TO NAVIGATE</div>
  `;

  const breadcrumb = document.querySelector('.floor-breadcrumb');
  breadcrumb.innerHTML = Array.from({length: 6}, (_, i) =>
    `<span class="crumb" onclick="scrollToFloor(${i})">●</span>`
  ).join('');
}

// ================================================================
//  POD SILHOUETTE FUNCTIONS
// ================================================================

function hashPodId(podId) {
  let hash = 0;
  for (let i = 0; i < podId.length; i++) {
    hash += podId.charCodeAt(i);
  }
  return (hash % 628) / 100;
}

function findPodById(podId) {
  for (const st of Object.values(floorAnimState)) {
    if (st && st.podSilhouettes && st.podSilhouettes[podId]) {
      return st.podSilhouettes[podId];
    }
  }
  return null;
}

function findAllPodsByBaseName(baseName) {
  const results = [];
  for (const st of Object.values(floorAnimState)) {
    if (st && st.podSilhouettes) {
      Object.entries(st.podSilhouettes).forEach(([key, agent]) => {
        if (agent.userData.basePodId === baseName || key === baseName) {
          results.push(agent);
        }
      });
    }
  }
  return results;
}

function getAgentMeshes(agentGroup) {
  return agentGroup.children.filter(c => c.isMesh);
}

function updatePodSilhouetteColor(podId, status) {
  const agents = findAllPodsByBaseName(podId);
  if (!agents.length) return;

  const template = podStatusMaterials[status];
  if (!template) return;

  agents.forEach(agent => {
    if (agent.userData.isGovAgent) return;
    const meshes = getAgentMeshes(agent);
    meshes.forEach(mesh => {
      const baseEI = mesh.material.emissiveIntensity;
      const targetEI = status === 'ACTIVE' ? baseEI : (status === 'HALTED' ? 0.15 : 0.03);
      gsap.to(mesh.material, { emissiveIntensity: targetEI, duration: 0.5, ease: EASE.PANEL });
    });
    agent.userData.status = status;
  });
}

function triggerPodHeartbeat(podId) {
  const agents = findAllPodsByBaseName(podId);
  agents.forEach(agent => {
    const meshes = getAgentMeshes(agent);
    meshes.forEach(m => {
      const origEI = m.material.emissiveIntensity;
      gsap.to(m.material, {
        emissiveIntensity: 0.45,
        duration: 0.25,
        ease: EASE.HOVER,
        onComplete: () => {
          gsap.to(m.material, {
            emissiveIntensity: origEI,
            duration: 0.4,
            ease: 'power2.in',
          });
        },
      });
    });
  });
}

function highlightAgent(agentGroup, on) {
  const meshes = getAgentMeshes(agentGroup);
  meshes.forEach(m => {
    const targetEI = on ? 0.4 : (m.material._restEI !== undefined ? m.material._restEI : 0.12);
    if (on && m.material._restEI === undefined) {
      m.material._restEI = m.material.emissiveIntensity;
    }
    gsap.to(m.material, { emissiveIntensity: targetEI, duration: TIMING.HOVER_IN, ease: EASE.HOVER });
  });

  agentGroup.children.forEach(child => {
    if (child.isSprite) child.visible = on;
  });
}

// ================================================================
//  POSTURE-SPECIFIC ANIMATION LOOP
//  Children: [0]=head, [1]=neck, [2]=torso, [3]=shoulders,
//            [4]=hips, [5]=legL, [6]=legR, [7]=armL, [8]=armR,
//            [9]=accentStripe
// ================================================================

const clock = new THREE.Clock();

const _ambientState = {
  screenTimers: {},
  lightTimers: {},
};

function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  const dt = clock.getDelta() || 0.016;

  // Camera micro-drift
  const driftX = Math.sin(t * 0.07) * 0.15 + Math.sin(t * 0.13) * 0.08;
  const driftY = Math.sin(t * 0.05) * 0.08;

  camera.position.x += (driftX - camera.position.x) * 0.02;
  camera.position.y += ((cameraTweenState.baseY + driftY) - camera.position.y) * 0.04;
  camera.position.z += (cameraTweenState.baseZ - camera.position.z) * 0.04;
  camera.lookAt(camera.position.x * 0.15, cameraTweenState.lookY, 0);

  // Posture-specific agent animation
  Object.values(floorAnimState).forEach(st => {
    if (!st || !st.podSilhouettes) return;
    Object.entries(st.podSilhouettes).forEach(([podId, agent]) => {
      const ud = agent.userData;
      const phase = ud.idlePhase || hashPodId(podId);
      const posture = ud.posture || 'standing';

      if (ud.pauseTimer > 0) {
        ud.pauseTimer -= dt;
        return;
      }
      if (Math.random() < 0.0002) {
        ud.pauseTimer = ud.pauseDuration || 3;
        return;
      }

      const head = agent.children[0];
      const torso = agent.children[2];
      const armL = agent.children[7];
      const armR = agent.children[8];

      if (!head || !torso) return;

      switch (posture) {

        case 'seated': {
          const rockF = ud.weightShiftFreq || 0.06;
          const rockA = ud.weightShiftAmp || 0.008;
          if (torso.isMesh) {
            torso.rotation.z = Math.sin(t * rockF + phase) * rockA;
          }
          const typeF = ud.typingFreq || 2.5;
          const typeA = ud.typingAmp || 0.012;
          if (armL && armL.isMesh) {
            armL.rotation.x = -Math.PI / 4 + Math.sin(t * typeF + phase) * typeA;
          }
          if (armR && armR.isMesh) {
            armR.rotation.x = -Math.PI / 4 + Math.sin(t * typeF + phase + 1.2) * typeA;
          }
          const headF = ud.headScanFreq || 0.03;
          const headA = ud.headScanAmp || 0.06;
          if (head.isMesh) {
            head.rotation.y = Math.sin(t * headF + phase * 3) * headA;
          }
          break;
        }

        case 'leaning': {
          const adjF = ud.weightShiftFreq || 0.05;
          const adjA = ud.weightShiftAmp || 0.005;
          if (torso.isMesh) {
            torso.rotation.z = Math.sin(t * adjF + phase) * adjA;
          }
          if (head.isMesh) {
            head.rotation.y = Math.sin(t * 0.025 + phase) * 0.06;
          }
          break;
        }

        case 'observing': {
          const scanF = ud.headScanFreq || 0.025;
          const scanA = ud.headScanAmp || 0.1;
          if (head.isMesh) {
            head.rotation.y = Math.sin(t * scanF + phase) * scanA;
          }
          const shiftF = ud.weightShiftFreq || 0.04;
          const shiftA = 0.004;
          agent.position.x += Math.sin(t * shiftF + phase) * shiftA * dt;
          break;
        }

        case 'conversing': {
          if (head.isMesh) {
            head.rotation.y = Math.sin(t * 0.035 + phase) * 0.08 + 0.12;
          }
          if (torso.isMesh) {
            torso.rotation.z = Math.sin(t * 0.04 + phase * 2) * 0.006;
          }
          break;
        }

        case 'standing':
        default: {
          const shiftF = ud.weightShiftFreq || 0.06;
          const shiftA = ud.weightShiftAmp || 0.008;
          if (torso.isMesh) {
            torso.rotation.z = Math.sin(t * shiftF + phase) * shiftA;
          }
          const headF = ud.headScanFreq || 0.03;
          const headA = ud.headScanAmp || 0.08;
          if (head.isMesh) {
            head.rotation.y = Math.sin(t * headF + phase * 3) * headA;
          }
          break;
        }
      }

      if (ud.gestureCountdown !== undefined) {
        ud.gestureCountdown -= dt;
        if (ud.gestureCountdown <= 0) {
          ud.gestureCountdown = ud.gestureTimer || 35;
          if (armR && armR.isMesh && posture !== 'seated') {
            const origX = armR.rotation.x;
            const origZ = armR.rotation.z;
            gsap.to(armR.rotation, {
              x: origX - 0.08,
              z: origZ - 0.1,
              duration: 0.7,
              ease: EASE.HOVER,
              onComplete: () => {
                gsap.to(armR.rotation, {
                  x: origX,
                  z: origZ,
                  duration: 1.0,
                  ease: EASE.PANEL,
                });
              },
            });
          }
        }
      }
    });
  });

  // Ambient screen shimmer
  Object.entries(floorAnimState).forEach(([idx, st]) => {
    if (!st || !st.screens) return;
    st.screens.forEach((screenMat, si) => {
      const key = idx + '_' + si;
      if (!_ambientState.screenTimers[key]) {
        _ambientState.screenTimers[key] = 3 + Math.random() * 5;
      }
      _ambientState.screenTimers[key] -= dt;
      if (_ambientState.screenTimers[key] <= 0) {
        _ambientState.screenTimers[key] = 3 + Math.random() * 5;
        const baseEI = st.floorState === 'selected' ? 0.85 : 0.65;
        const flicker = baseEI * (0.92 + Math.random() * 0.16);
        gsap.to(screenMat, {
          emissiveIntensity: flicker,
          duration: 0.3 + Math.random() * 0.4,
          ease: EASE.HOVER,
          onComplete: () => {
            gsap.to(screenMat, {
              emissiveIntensity: baseEI,
              duration: 0.5 + Math.random() * 0.5,
              ease: 'power1.out',
            });
          },
        });
      }
    });

    // Light pulse
    const lightKey = 'light_' + idx;
    if (!_ambientState.lightTimers[lightKey]) {
      _ambientState.lightTimers[lightKey] = 2 + Math.random() * 3;
    }
    _ambientState.lightTimers[lightKey] -= dt;
    if (_ambientState.lightTimers[lightKey] <= 0) {
      _ambientState.lightTimers[lightKey] = 2 + Math.random() * 3;
      const baseLI = st.baseLightInt || 1.8;
      const pulse = baseLI * (0.92 + Math.random() * 0.16);
      gsap.to(st.pointLight, {
        intensity: pulse,
        duration: 0.8,
        ease: 'power1.inOut',
        onComplete: () => {
          gsap.to(st.pointLight, {
            intensity: baseLI,
            duration: 1.0,
            ease: 'power1.out',
          });
        },
      });
    }
  });

  // Fade and dispose governance light tubes
  govLightLines = govLightLines.filter(obj => {
    obj.material.opacity -= 0.005;
    if (obj.material.opacity <= 0) {
      scene.remove(obj);
      obj.geometry.dispose();
      obj.material.dispose();
      return false;
    }
    return true;
  });

  renderer.render(scene, camera);
}
animate();

// ================================================================
//  HOVER GLOW & FLOOR STATE
// ================================================================

function addFloorHoverGlow(floorIdx) {
  const st = floorAnimState[floorIdx];
  if (!st || st.floorState === 'selected') return;
  st.hovering = true;
  st.floorState = 'hovered';

  gsap.killTweensOf(st);
  gsap.to(st, {
    hoverGlowIntensity: 1.0,
    duration: TIMING.HOVER_IN,
    ease: EASE.HOVER,
    onUpdate: () => {
      st.screens.forEach(m => { m.emissiveIntensity = st.hoverGlowIntensity; });
    },
  });

  gsap.to(st.trimMat, {
    emissiveIntensity: 0.7,
    duration: TIMING.HOVER_IN,
    delay: 0.04,
    ease: EASE.HOVER,
  });

  if (st.rimLight) {
    gsap.to(st.rimLight, { intensity: 0.8, duration: TIMING.HOVER_IN, ease: EASE.HOVER });
  }
}

function removeFloorHoverGlow(floorIdx) {
  const st = floorAnimState[floorIdx];
  if (!st || st.floorState === 'selected') return;
  st.hovering = false;
  st.floorState = 'idle';

  gsap.killTweensOf(st);
  gsap.to(st, {
    hoverGlowIntensity: 0.65,
    duration: TIMING.HOVER_OUT,
    ease: 'power2.in',
    onUpdate: () => {
      st.screens.forEach(m => { m.emissiveIntensity = st.hoverGlowIntensity; });
    },
  });

  gsap.to(st.trimMat, {
    emissiveIntensity: 0.45,
    duration: TIMING.HOVER_OUT,
    ease: 'power2.in',
  });

  if (st.rimLight) {
    gsap.to(st.rimLight, { intensity: 0.6, duration: TIMING.HOVER_OUT, ease: 'power2.in' });
  }
}

function createDataRoute(srcFloorIdx, dstFloorIdx, color) {
  const srcFloor = FLOORS[srcFloorIdx];
  const dstFloor = FLOORS[dstFloorIdx];

  const srcY = srcFloor.y;
  const dstY = dstFloor.y;
  const midY = (srcY + dstY) / 2;

  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-1.2, srcY, 0.5),
    new THREE.Vector3(0, midY, 3.5),
    new THREE.Vector3(1.2, dstY, 0.5),
  ]);

  const tubeGeo = new THREE.TubeGeometry(curve, 24, 0.045, 5, false);
  const tubeMat = new THREE.MeshBasicMaterial({
    color: color,
    transparent: true,
    opacity: 0.55,
    depthWrite: false,
  });

  const tube = new THREE.Mesh(tubeGeo, tubeMat);
  scene.add(tube);
  govLightLines.push(tube);

  const delay = TIMING.CROSS_FLOOR * 0.6;
  setTimeout(() => {
    flashFloor(dstFloorIdx, 1.8, 0.8);
  }, delay * 1000);
}

// ================================================================
//  WHEEL, KEYBOARD & RAYCASTER
// ================================================================

const leftPanel = document.querySelector('.left-panel');
leftPanel.addEventListener('wheel', (e) => {
  e.preventDefault();

  if (isScrolling) return;
  isScrolling = true;

  const direction = e.deltaY > 0 ? -1 : 1;
  const base = currentFloor < 0 ? (direction > 0 ? -1 : -1) : currentFloor;
  const nextFloor = Math.max(0, Math.min(4, base + direction));

  if (nextFloor !== currentFloor && nextFloor >= 0) {
    currentFloor = nextFloor;
    animateCameraToFloor(currentFloor);
    updateFloorContext(currentFloor);
  }

  scrollTimeout = setTimeout(() => { isScrolling = false; }, 250);
});

leftPanel.style.overflowY = 'hidden';
updateFloorContext(0);

document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (currentFloor < 0) { currentFloor = 0; }
    else { currentFloor = Math.min(4, currentFloor + 1); }
    animateCameraToFloor(currentFloor);
    updateFloorContext(currentFloor);
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (currentFloor < 0) { currentFloor = 0; }
    else { currentFloor = Math.max(0, currentFloor - 1); }
    animateCameraToFloor(currentFloor);
    updateFloorContext(currentFloor);
  } else if (e.key === 'Escape') {
    e.preventDefault();
    backToBuilding();
  }
});

// ================================================================
//  RAYCASTER & INTERACTION
// ================================================================

const tooltip = document.getElementById('agent-tooltip');

canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect();
  mouse.x = (e.clientX - rect.left) / rect.width * 2 - 1;
  mouse.y = -(e.clientY - rect.top) / rect.height * 2 + 1;

  raycaster.setFromCamera(mouse, camera);
  const intersects = raycaster.intersectObjects(scene.children, true);

  let newHoveredFloor = null;
  let newHoveredPod = null;
  for (const hit of intersects) {
    let obj = hit.object;
    let hitPod = null;
    let hitFloor = null;
    while (obj) {
      if (obj.userData.podId !== undefined && hitPod === null) {
        hitPod = obj.userData.podId;
      }
      if (obj.userData.floorIndex !== undefined && hitFloor === null) {
        hitFloor = obj.userData.floorIndex;
      }
      obj = obj.parent;
    }
    if (hitFloor !== null && newHoveredFloor === null) {
      newHoveredFloor = hitFloor;
    }
    if (hitPod !== null && newHoveredPod === null) {
      newHoveredPod = hitPod;
    }
    if (newHoveredPod !== null) break;
  }

  if (newHoveredFloor !== hoveredFloor) {
    if (hoveredFloor !== null) removeFloorHoverGlow(hoveredFloor);
    hoveredFloor = newHoveredFloor;
    if (hoveredFloor !== null) addFloorHoverGlow(hoveredFloor);
  }

  if (newHoveredPod !== hoveredPod) {
    if (hoveredPod !== null) {
      const prev = findPodById(hoveredPod);
      if (prev) highlightAgent(prev, false);
    }
    hoveredPod = newHoveredPod;
    if (hoveredPod !== null) {
      const curr = findPodById(hoveredPod);
      if (curr) highlightAgent(curr, true);
    }
  }

  if (hoveredPod !== null) {
    const agent = findPodById(hoveredPod);
    const basePodId = agent?.userData?.basePodId || hoveredPod;
    const role = agent?.userData?.role || '';
    const isGov = agent?.userData?.isGovAgent;
    const podData = pods[basePodId];
    const stratInfo = isGov
      ? govAgents.find(g => g.id === hoveredPod)?.label
      : podStrategyNames[basePodId];
    tooltip.querySelector('.tt-name').textContent = (stratInfo?.[0] || basePodId).toUpperCase();
    tooltip.querySelector('.tt-strategy').textContent = role || stratInfo?.[1] || '';
    if (podData) {
      const nav = podData.nav != null ? '$' + Number(podData.nav).toFixed(2) : '—';
      const pnl = podData.daily_pnl != null ? Number(podData.daily_pnl).toFixed(2) : '—';
      const pnlClass = Number(podData.daily_pnl || 0) >= 0 ? 'pos' : 'neg';
      const status = podData.status || 'ACTIVE';
      tooltip.querySelector('.tt-stats').innerHTML = `
        <div class="stat-row"><span>Role</span><span class="stat-val">${role || '—'}</span></div>
        <div class="stat-row"><span>NAV</span><span class="stat-val">${nav}</span></div>
        <div class="stat-row"><span>P&L</span><span class="stat-val ${pnlClass}">${pnl}</span></div>
        <div class="stat-row"><span>Status</span><span class="stat-val">${status}</span></div>
      `;
    } else if (isGov) {
      tooltip.querySelector('.tt-stats').innerHTML = `<div class="stat-row"><span>Firm-level agent</span></div>`;
    } else {
      tooltip.querySelector('.tt-stats').innerHTML = '<div class="stat-row"><span>Awaiting data…</span></div>';
    }

    // Show last agent reasoning in tooltip
    var reasoningEl = tooltip.querySelector('.tt-reasoning');
    if (reasoningEl) {
      var actKey = isGov ? hoveredPod : basePodId + '_' + (role || 'pm').toLowerCase().replace(/\s+/g, '_');
      var activities = agentActivity[actKey] || agentActivity[basePodId + '_pm'] || [];
      if (activities.length > 0) {
        reasoningEl.textContent = activities[0].summary || '';
      } else {
        reasoningEl.textContent = '';
      }
    }

    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX - rect.left + 16) + 'px';
    tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
  } else {
    tooltip.style.display = 'none';
  }

  canvas.classList.toggle('hovering', hoveredFloor !== null || hoveredPod !== null);
});

canvas.addEventListener('click', () => {
  if (hoveredPod !== null) {
    const agent = findPodById(hoveredPod);
    if (agent && agent.userData.floorIndex !== currentFloor) {
      scrollToFloor(agent.userData.floorIndex);
    }
  } else if (hoveredFloor !== null && hoveredFloor !== currentFloor) {
    scrollToFloor(hoveredFloor);
  }
});

canvas.addEventListener('mouseleave', () => {
  tooltip.style.display = 'none';
  if (hoveredPod !== null) {
    const prev = findPodById(hoveredPod);
    if (prev) highlightAgent(prev, false);
    hoveredPod = null;
  }
});

// ================================================================
//  FLASH ANIMATION HELPERS
// ================================================================

function flashFloor(idx, peak, dur) {
  const st = floorAnimState[idx];
  if (!st) return;
  const proxy = { v: st.baseEmissive };
  gsap.killTweensOf(proxy);
  gsap.to(proxy, {
    v: peak, duration: 0.18, ease: 'power3.out',
    onUpdate: () => {
      st.screens.forEach(m => { m.emissiveIntensity = proxy.v; });
      st.pointLight.intensity = st.baseLightInt * (proxy.v / 0.65);
    },
    onComplete: () => {
      gsap.to(proxy, {
        v: 0.65, duration: dur, ease: 'expo.out',
        onUpdate: () => {
          st.screens.forEach(m => { m.emissiveIntensity = proxy.v; });
          st.pointLight.intensity = st.baseLightInt * (proxy.v / 0.65);
        },
      });
    },
  });
}

function triggerTradePulse(floorIdx) { flashFloor(floorIdx ?? 0, 2.2, 1.0); }
function triggerRiskAlert() { flashFloor(0, 3.0, 1.5); }

function triggerAgentActivity(podId, role) {
  if (!podId) return;
  var agents = findAllPodsByBaseName(podId);
  if (!agents.length && podId === 'firm') {
    // Governance agents
    for (var st of Object.values(floorAnimState)) {
      if (st && st.podSilhouettes) {
        Object.values(st.podSilhouettes).forEach(function(a) {
          if (a.userData.isGovAgent) agents.push(a);
        });
      }
    }
  }

  // Find the specific agent by role if possible
  var target = null;
  if (role) {
    var roleLower = role.toLowerCase();
    target = agents.find(function(a) {
      var r = (a.userData.role || '').toLowerCase();
      return r === roleLower || r.indexOf(roleLower) >= 0;
    });
  }
  var targets = target ? [target] : agents.slice(0, 1);

  targets.forEach(function(agent) {
    var meshes = getAgentMeshes(agent);
    meshes.forEach(function(m) {
      var origEI = m.material.emissiveIntensity;
      var origEmissive = m.material.emissive ? m.material.emissive.getHex() : 0xffffff;
      m.material.emissive.set(0xffffff);
      gsap.to(m.material, {
        emissiveIntensity: 0.6,
        duration: 0.15,
        ease: 'power3.out',
        onComplete: function() {
          gsap.to(m.material, {
            emissiveIntensity: origEI,
            duration: 0.35,
            ease: 'power2.in',
            onComplete: function() {
              m.material.emissive.set(origEmissive);
            },
          });
        },
      });
    });
  });

  // Fire a data route from agent floor to governance for trade/mandate decisions
  var floorIdx = podFloorMap[podId];
  if (floorIdx != null && floorIdx !== 4 && typeof createDataRoute === 'function') {
    var action = (role || '').toLowerCase();
    if (action === 'pm' || action === 'trader' || action === 'ceo' || action === 'cio') {
      createDataRoute(floorIdx, 4, 0x00cfe8);
    }
  }
}

function triggerGovernanceLightFlow(agentName) {
  const fi = 4;
  flashFloor(fi, 1.8, 1.2);

  const srcY = FLOORS[4].y + FLOOR_H;
  const dstY = FLOORS[3].y + FLOOR_H * 0.5;
  const mid = (srcY + dstY) * 0.5;

  const curve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-0.8, srcY, 0.5),
    new THREE.Vector3( 0,   mid,  2.5),
    new THREE.Vector3( 0.8, dstY, 0.5),
  ]);
  const tubeGeo = new THREE.TubeGeometry(curve, 24, 0.04, 5, false);
  const tubeMat = new THREE.MeshBasicMaterial({
    color: FLOORS[fi].accent, transparent: true, opacity: 0.55, depthWrite: false,
  });
  const tube = new THREE.Mesh(tubeGeo, tubeMat);
  scene.add(tube);
  govLightLines.push(tube);
}
