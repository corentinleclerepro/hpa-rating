(() => {
  "use strict";
  const key = "hpa-rating.brouillon.v1";
  function read() {
    try {
      const value = JSON.parse(localStorage.getItem(key));
      return value && typeof value.id === "string" && /^[a-f0-9]{32}$/.test(value.id) ? value : null;
    } catch { return null; }
  }
  function write(value) {
    try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; }
  }
  function erase(id) {
    try { if (read()?.id === id) localStorage.removeItem(key); return true; } catch { return false; }
  }
  function packet(value) {
    const {id,reference,type,mention,stars,pitches,answers} = value;
    return {id,reference,type,mention,stars,pitches,answers};
  }
  function count(event, token) {
    if (navigator.globalPrivacyControl === true || navigator.doNotTrack === "1" || !token) return;
    fetch("/parcours/compter/" + event, {method:"POST", credentials:"same-origin", keepalive:true,
      headers:{"X-CSRFToken":token}}).catch(() => {});
  }
  window.HpaDraft = {key,read,write,erase,packet,count};
})();
