(() => {
  const video = document.getElementById('editing-case-video');
  const player = document.getElementById('editing-case-player');
  const play = document.querySelector('.editing-case-play');
  const cuts = Array.from(document.querySelectorAll('.editing-case-shots [data-cut-start]'));
  if (!video || !player || !play || !cuts.length) return;

  const startTimes = cuts.map(cut => Number(cut.dataset.cutStart));
  const treeShots = Array.from(document.querySelectorAll('[data-tree-shot]'));
  const evidenceLabels = document.querySelectorAll('[data-evidence-shot]');
  const evidencePanels = document.querySelectorAll('.editing-case-evidence');
  const nativeShot = document.querySelector('[data-native-shot]');
  const learnedShot = document.querySelector('[data-learned-shot]');
  const framesPerSecond = 24;
  let pendingCut;

  function inspectShot(cut) {
    if (!cut || !nativeShot || !learnedShot) return;
    const { shot, sourceFile, sourceStart, cutStart, duration } = cut.dataset;
    const startFrame = Math.round(Number(cutStart) * framesPerSecond);
    const frameCount = Math.round(Number(duration) * framesPerSecond);

    treeShots.forEach(node => node.setAttribute('aria-pressed', String(node.dataset.treeShot === shot)));
    evidenceLabels.forEach(label => { label.textContent = shot; });
    nativeShot.textContent = `{ src: '${sourceFile}',
  start: ${startFrame}, frames: ${frameCount}, label: '${shot}' }`;
    learnedShot.textContent = [
      `file: "${sourceFile}"`,
      `sourceStartSeconds: ${sourceStart}`,
      `outputStartSeconds: ${cutStart}`,
      `durationSeconds: ${duration}`,
      `label: "${shot}"`
    ].join(',\n');
  }

  treeShots.forEach(node => {
    node.addEventListener('click', () => {
      inspectShot(cuts.find(cut => cut.dataset.shot === node.dataset.treeShot));
      evidencePanels.forEach(panel => { panel.open = true; });
    });
  });

  function selectCut(index) {
    cuts.forEach((cut, position) => {
      if (index === position) {
        cut.setAttribute('aria-current', 'true');
      } else {
        cut.removeAttribute('aria-current');
      }
    });
  }

  function syncCut() {
    if (!player.hidden && pendingCut === undefined) {
      selectCut(startTimes.findLastIndex(start => start <= video.currentTime));
    }
  }

  function seekTo(index) {
    selectCut(index);
    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
      video.currentTime = startTimes[index];
      return;
    }
    pendingCut = index;
    if (video.networkState !== HTMLMediaElement.NETWORK_LOADING) {
      video.preload = 'metadata';
      video.load();
    }
  }

  function showPlayer(open) {
    player.hidden = !open;
    play.setAttribute('aria-expanded', String(open));
  }

  play.hidden = false;
  play.addEventListener('click', () => {
    if (!player.hidden) {
      video.pause();
      showPlayer(false);
      selectCut(-1);
      return;
    }
    showPlayer(true);
    seekTo(0);
    video.play().catch(() => {});
  });

  cuts.forEach((cut, index) => {
    cut.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      inspectShot(cut);
      showPlayer(true);
      seekTo(index);
    });
  });

  video.addEventListener('loadedmetadata', () => {
    if (pendingCut !== undefined) {
      video.currentTime = startTimes[pendingCut];
      pendingCut = undefined;
    }
  });
  video.addEventListener('timeupdate', syncCut);
  video.addEventListener('seeked', syncCut);
})();
