(() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function run(){
    try {
      await sleep(1500);
      chrome.runtime.sendMessage({
        type:'FILM4K_READY',
        title:document.title,
        pageUrl:location.href
      });

      const tryPlay = async () => {
        const video = document.querySelector('video');
        if (!video) return false;
        try {
          video.muted = true;
          video.volume = 0;
          await video.play();
          return true;
        } catch (_) {
          try { video.click(); await video.play(); return true; } catch (_) {}
        }
        return false;
      };

      for (let i=0;i<12;i++) {
        await tryPlay();
        await sleep(1000);
      }

      chrome.runtime.sendMessage({
        type:'FILM4K_DONE',
        title:document.title,
        pageUrl:location.href
      });
    } catch (e) {
      chrome.runtime.sendMessage({type:'FILM4K_DONE', error:String(e?.message || e)});
    }
  }
  run();
})();
