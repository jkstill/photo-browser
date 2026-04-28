function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "0:00";
  }

  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function initializeVideoPlayer(root) {
  const video = root.querySelector("[data-video]");
  const controls = root.querySelector("[data-controls]");
  const playButton = root.querySelector("[data-play]");
  const muteButton = root.querySelector("[data-mute]");
  const seekInput = root.querySelector("[data-seek]");
  const timeLabel = root.querySelector("[data-time]");

  if (!video || !controls || !playButton || !muteButton || !seekInput || !timeLabel) {
    return;
  }

  video.controls = false;
  controls.hidden = false;

  const syncPlayState = () => {
    playButton.textContent = video.paused ? "Play" : "Pause";
  };

  const syncMuteState = () => {
    muteButton.textContent = video.muted ? "Unmute" : "Mute";
  };

  const syncTimeline = () => {
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    seekInput.max = duration.toString();
    seekInput.value = Math.min(video.currentTime, duration).toString();
    timeLabel.textContent = `${formatTime(video.currentTime)} / ${formatTime(duration)}`;
  };

  playButton.addEventListener("click", () => {
    if (video.paused) {
      void video.play();
      return;
    }
    video.pause();
  });

  muteButton.addEventListener("click", () => {
    video.muted = !video.muted;
  });

  seekInput.addEventListener("input", () => {
    const nextTime = Number.parseFloat(seekInput.value);
    if (Number.isFinite(nextTime)) {
      video.currentTime = nextTime;
    }
  });

  video.addEventListener("click", () => {
    if (video.paused) {
      void video.play();
      return;
    }
    video.pause();
  });

  video.addEventListener("loadedmetadata", syncTimeline);
  video.addEventListener("durationchange", syncTimeline);
  video.addEventListener("timeupdate", syncTimeline);
  video.addEventListener("play", syncPlayState);
  video.addEventListener("pause", syncPlayState);
  video.addEventListener("volumechange", syncMuteState);
  video.addEventListener("ended", syncPlayState);

  syncPlayState();
  syncMuteState();
  syncTimeline();
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-video-player]").forEach(initializeVideoPlayer);
});
