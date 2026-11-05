(function () {
  "use strict";
  var CONSENT_VERSION = "v1-2026-11";
  var MAX_SEC = 30, MIN_SEC = 0.6;
  var DISTRICTS = {
    "Dhaka": "Dhaka,Faridpur,Gazipur,Gopalganj,Kishoreganj,Madaripur,Manikganj,Munshiganj,Narayanganj,Narsingdi,Rajbari,Shariatpur,Tangail",
    "Chattogram": "Bandarban,Brahmanbaria,Chandpur,Chattogram,Cox's Bazar,Cumilla,Feni,Khagrachhari,Lakshmipur,Noakhali,Rangamati",
    "Rajshahi": "Bogura,Chapai Nawabganj,Joypurhat,Naogaon,Natore,Pabna,Rajshahi,Sirajganj",
    "Khulna": "Bagerhat,Chuadanga,Jashore,Jhenaidah,Khulna,Kushtia,Magura,Meherpur,Narail,Satkhira",
    "Barishal": "Barguna,Barishal,Bhola,Jhalokati,Patuakhali,Pirojpur",
    "Sylhet": "Habiganj,Moulvibazar,Sunamganj,Sylhet",
    "Rangpur": "Dinajpur,Gaibandha,Kurigram,Lalmonirhat,Nilphamari,Panchagarh,Rangpur,Thakurgaon",
    "Mymensingh": "Jamalpur,Mymensingh,Netrokona,Sherpur"
  };

  var cfg = window.BV_CONFIG || {};
  var $ = function (id) { return document.getElementById(id); };
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem("bv_" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem("bv_" + k, JSON.stringify(v)); } catch (e) {} }
  };

  var prompts = [], byId = {}, order = [], pos = 0;
  var stream = null, rec = null, chunks = [], blob = null, blobUrl = "", mime = "";
  var startedAt = 0, duration = 0, tick = null, busy = false;

  function show(name) {
    var s = document.querySelectorAll("main > section");
    for (var i = 0; i < s.length; i++) s[i].hidden = s[i].id !== "screen-" + name;
    window.scrollTo(0, 0);
  }
  function fatal(msg) { $("error-text").textContent = msg; show("error"); }
  function status(msg, kind) { var el = $("status"); el.textContent = msg || ""; el.className = "status" + (kind ? " " + kind : ""); }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var b = new Uint8Array(16); crypto.getRandomValues(b);
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    var h = Array.prototype.map.call(b, function (x) { return (x + 256).toString(16).slice(1); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }
  function speakerId() {
    var id = store.get("speaker_id", "");
    if (!id) { id = "spk_" + uuid().replace(/-/g, "").slice(0, 16); store.set("speaker_id", id); }
    return id;
  }
  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }
  // Shuffle within each category, then deal round-robin so every short session covers all categories.
  function makeOrder() {
    var groups = {};
    prompts.forEach(function (p) { (groups[p.category] = groups[p.category] || []).push(p.id); });
    var lists = shuffle(Object.keys(groups)).map(function (c) { return shuffle(groups[c]); });
    var out = [];
    for (var k = 0; out.length < prompts.length; k++) lists.forEach(function (l) { if (k < l.length) out.push(l[k]); });
    return out;
  }

  // ---- Supabase (plain fetch; the public key can only INSERT, see supabase/setup.sql) ----
  function authHeaders(extra) {
    var h = { apikey: cfg.supabaseKey };
    if (/^eyJ/.test(cfg.supabaseKey)) h.Authorization = "Bearer " + cfg.supabaseKey;
    for (var k in extra) h[k] = extra[k];
    return h;
  }
  function post(path, body, headers) {
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 90000);
    return fetch(cfg.supabaseUrl + path, { method: "POST", headers: authHeaders(headers), body: body, signal: ctl && ctl.signal })
      .then(function (r) {
        clearTimeout(timer);
        if (!r.ok) return r.text().then(function (t) { throw new Error("HTTP " + r.status + " " + t.slice(0, 160)); });
      }, function (e) { clearTimeout(timer); throw e; });
  }

  // ---- Screens ----
  function initConsent() {
    if (cfg.contactText) { $("contact").textContent = "Contact: " + cfg.contactText; $("contact").hidden = false; }
    $("agree").onchange = function () { $("btn-consent").disabled = !this.checked; };
    $("btn-consent").onclick = function () {
      if (!$("agree").checked) return;
      store.set("consent", CONSENT_VERSION);
      speakerId();
      initProfile(); show("profile");
    };
  }
  function initProfile() {
    var sel = $("region");
    if (sel.options.length === 1) {
      Object.keys(DISTRICTS).forEach(function (div) {
        var g = document.createElement("optgroup"); g.label = div + " division";
        DISTRICTS[div].split(",").forEach(function (d) { var o = document.createElement("option"); o.textContent = d; g.appendChild(o); });
        sel.appendChild(g);
      });
      var g2 = document.createElement("optgroup"); g2.label = "Other";
      var o = document.createElement("option"); o.textContent = "Outside Bangladesh"; g2.appendChild(o); sel.appendChild(g2);
    }
    var p = store.get("profile", {});
    $("age_range").value = p.age_range || ""; sel.value = p.region || ""; $("phone_model").value = p.phone_model || "";
    $("speaker").textContent = speakerId(); $("footer").hidden = false;
    $("btn-newspeaker").onclick = function () {
      if (!confirm("Start as a new speaker? The next person will see the consent screen again.")) return;
      ["speaker_id", "profile", "consent", "batch_done", "total_done"].forEach(function (k) { try { localStorage.removeItem("bv_" + k); } catch (e) {} });
      $("agree").checked = false; $("btn-consent").disabled = true; $("footer").hidden = true;
      show("consent");
    };
    $("btn-profile").onclick = function () {
      store.set("profile", { age_range: $("age_range").value, region: sel.value, phone_model: $("phone_model").value.trim().slice(0, 100) });
      startRecording();
    };
  }
  function startRecording() {
    if (!window.isSecureContext) return fatal("This page must be opened over https:// for the microphone to work.");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder)
      return fatal("This browser can't record audio. Please open the link in Google Chrome (Android) or Safari (iPhone, iOS 14.3+).");
    show("record"); loadPrompt();
  }

  function progressText() { return store.get("batch_done", 0) + "/" + (cfg.sessionGoal || 50); }
  function current() { return byId[order[pos]]; }
  function loadPrompt() {
    if (pos >= order.length) { order = makeOrder(); pos = 0; store.set("order", order); }
    store.set("pos", pos);
    var p = current();
    $("prompt").textContent = p.text;
    $("actual").value = p.text;
    $("progress").textContent = progressText();
    resetTake(); status("");
  }
  function resetTake() {
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blob = null; blobUrl = ""; duration = 0;
    $("player").removeAttribute("src");
    $("btn-play").disabled = $("btn-rerecord").disabled = $("btn-submit").disabled = true;
    $("record-label").textContent = "Record"; $("timer").textContent = "";
  }
  function pickMime() {
    var c = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    for (var i = 0; i < c.length; i++) if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(c[i])) return c[i];
    return "";
  }
  function getStream() {
    if (stream && stream.active) return Promise.resolve(stream);
    return navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: true } })
      .then(function (s) { stream = s; return s; });
  }
  function startRec() {
    if (busy) return;
    resetTake(); status("");
    getStream().then(function (s) {
      chunks = []; mime = pickMime();
      rec = mime ? new MediaRecorder(s, { mimeType: mime, audioBitsPerSecond: 64000 }) : new MediaRecorder(s);
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      rec.onstop = onStopped;
      rec.start();
      startedAt = Date.now();
      $("btn-record").classList.add("on"); $("record-label").textContent = "Stop";
      $("btn-rerecord").disabled = true; $("btn-skip").disabled = true;
      tick = setInterval(function () {
        var t = (Date.now() - startedAt) / 1000;
        $("timer").textContent = t.toFixed(0) + "s";
        if (t >= MAX_SEC) stopRec();
      }, 250);
    }).catch(function (e) {
      var denied = e && (e.name === "NotAllowedError" || e.name === "SecurityError");
      status(denied ? "Microphone blocked. Tap the lock icon next to the address, allow Microphone, then try again."
                    : "Could not start the microphone: " + (e && (e.name || e.message)), "err");
    });
  }
  function stopRec() {
    if (!rec || rec.state === "inactive") return;
    duration = (Date.now() - startedAt) / 1000;
    clearInterval(tick);
    rec.stop();
  }
  function onStopped() {
    $("btn-record").classList.remove("on"); $("record-label").textContent = "Record"; $("btn-skip").disabled = false;
    var type = (rec && rec.mimeType) || mime || "audio/webm";
    blob = new Blob(chunks, { type: type }); chunks = [];
    $("btn-rerecord").disabled = false;
    if (duration < MIN_SEC || !blob.size) { status("That was too short. Tap Record and read the whole sentence.", "err"); blob = null; return; }
    blobUrl = URL.createObjectURL(blob);
    $("player").src = blobUrl;
    $("timer").textContent = duration.toFixed(1) + "s";
    $("btn-play").disabled = $("btn-submit").disabled = false;
    status("Listen back if you like, fix the text if needed, then Submit.");
  }
  function ext(type) { return /mp4|m4a|aac/.test(type) ? "m4a" : /ogg/.test(type) ? "ogg" : "webm"; }

  function submit() {
    if (!blob || busy) return;
    var text = $("actual").value.replace(/\s+/g, " ").trim();
    if (!text) { status("Please type what you said.", "err"); $("actual").focus(); return; }
    busy = true; setBusy(true); status("Uploading…");
    var p = current(), spk = speakerId(), prof = store.get("profile", {});
    var type = blob.type || "audio/webm";
    var path = spk + "/" + p.id + "_" + Date.now() + "_" + uuid().slice(0, 8) + "." + ext(type);
    var row = {
      speaker_id: spk, prompt_id: p.id, prompt_text: p.text, actual_text: text, category: p.category,
      audio_path: path, duration_sec: Math.round(duration * 100) / 100, mime_type: type,
      user_agent: navigator.userAgent.slice(0, 500), consent_version: store.get("consent", CONSENT_VERSION),
      age_range: prof.age_range || null, region: prof.region || null, phone_model: prof.phone_model || null
    };
    post("/storage/v1/object/" + encodeURIComponent(cfg.bucket) + "/" + path, blob, { "Content-Type": type.split(";")[0], "x-upsert": "false" })
      .then(function () { return post("/rest/v1/recordings", JSON.stringify(row), { "Content-Type": "application/json", Prefer: "return=minimal" }); })
      .then(function () {
        busy = false; setBusy(false);
        var done = store.get("batch_done", 0) + 1;
        store.set("batch_done", done); store.set("total_done", store.get("total_done", 0) + 1);
        pos++;
        if (done >= (cfg.sessionGoal || 50)) { $("done-count").textContent = store.get("total_done", done); show("done"); return; }
        loadPrompt(); status("Saved ✓ Next sentence.", "ok");
      })
      .catch(function (e) {
        busy = false; setBusy(false);
        status("Upload failed. Check your internet and tap Submit again. (" + (e && e.message || e) + ")", "err");
      });
  }
  function setBusy(b) {
    ["btn-record", "btn-play", "btn-rerecord", "btn-submit", "btn-skip"].forEach(function (id) { $(id).disabled = b; });
  }

  function initRecorderUI() {
    $("btn-record").onclick = function () { if (rec && rec.state === "recording") stopRec(); else startRec(); };
    $("btn-rerecord").onclick = startRec;
    $("btn-play").onclick = function () { var a = $("player"); a.currentTime = 0; a.play(); };
    $("btn-submit").onclick = submit;
    $("btn-skip").onclick = function () { if (busy || (rec && rec.state === "recording")) return; pos++; loadPrompt(); };
    $("btn-more").onclick = function () { store.set("batch_done", 0); show("record"); loadPrompt(); };
    window.addEventListener("pagehide", function () { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); stream = null; });
  }

  function boot() {
    if (!cfg.supabaseUrl || !cfg.supabaseKey) return fatal("The site is not configured yet (missing Supabase settings).");
    initConsent(); initRecorderUI();
    fetch("prompts.json").then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (list) {
      prompts = list; list.forEach(function (p) { byId[p.id] = p; });
      order = (store.get("order", []) || []).filter(function (id) { return byId[id]; });
      if (order.length !== prompts.length) { order = makeOrder(); store.set("order", order); store.set("pos", 0); }
      pos = Math.min(store.get("pos", 0), order.length);
      if (store.get("consent", "") === CONSENT_VERSION) { initProfile(); show("profile"); }
      else show("consent");
    }).catch(function () { fatal("Could not load the sentences. Check your internet and reload the page."); });
  }
  boot();
})();
