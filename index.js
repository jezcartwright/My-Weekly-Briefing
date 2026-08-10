const {onDocumentCreated} = require("firebase-functions/v2/firestore");
const {defineSecret} = require("firebase-functions/params");
const admin = require("firebase-admin");
const crypto = require("crypto");
const {onRequest} = require("firebase-functions/v2/https");

admin.initializeApp();

// --- GitHub App credentials (durable replacement for the expiring PAT) ---
// Instead of a fine-grained personal access token (which expires and must be
// manually renewed), we authenticate as a GitHub App installed on
// My-Weekly-Briefing. The App mints short-lived installation tokens on demand,
// so there is nothing to expire or renew. Set these three secrets with:
//   printf '%s' '<APP_ID>'          | firebase functions:secrets:set GH_APP_ID --data-file -
//   printf '%s' '<INSTALLATION_ID>' | firebase functions:secrets:set GH_APP_INSTALLATION_ID --data-file -
//   firebase functions:secrets:set GH_APP_PRIVATE_KEY --data-file /path/to/key.pem
const GH_APP_ID = defineSecret("GH_APP_ID");
const GH_APP_INSTALLATION_ID = defineSecret("GH_APP_INSTALLATION_ID");
const GH_APP_PRIVATE_KEY = defineSecret("GH_APP_PRIVATE_KEY");

const GITHUB_APP_SECRETS = [
  GH_APP_ID, GH_APP_INSTALLATION_ID, GH_APP_PRIVATE_KEY,
];

// HMAC secret for unsubscribe tokens. MUST hold the SAME value the send
// pipeline signs with (senders.py reads UNSUBSCRIBE_SECRET from the Actions
// secret). Set it into Secret Manager with:
//   printf '%s' '<the same secret value>' | firebase functions:secrets:set UNSUBSCRIBE_SECRET --data-file -
const UNSUBSCRIBE_SECRET = defineSecret("UNSUBSCRIBE_SECRET");

const BUCKET = "pi-briefing-38ddc.firebasestorage.app";

// --- Installation-token minting -------------------------------------------
// 1. Build a short (10-min) JWT signed with the App's private key (RS256).
// 2. Exchange it for an installation access token (lives ~1 hour).
// The installation token is cached in module memory and reused until it is
// close to expiry, so we are not signing a JWT on every single dispatch.
let cachedInstallationToken = null;
let cachedTokenExpiryMs = 0;

function base64url(input) {
  return Buffer.from(input)
      .toString("base64")
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
}

function buildAppJwt() {
  const appId = GH_APP_ID.value();
  const privateKey = GH_APP_PRIVATE_KEY.value();
  const now = Math.floor(Date.now() / 1000);
  const header = {alg: "RS256", typ: "JWT"};
  const payload = {
    // iat backdated 60s to tolerate minor clock drift between us and GitHub.
    iat: now - 60,
    exp: now + 540, // 9 minutes; GitHub's max is 10.
    iss: appId,
  };
  const unsigned =
      `${base64url(JSON.stringify(header))}.${base64url(JSON.stringify(payload))}`;
  const signer = crypto.createSign("RSA-SHA256");
  signer.update(unsigned);
  signer.end();
  const signature = signer.sign(privateKey)
      .toString("base64")
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
  return `${unsigned}.${signature}`;
}

// Returns a valid installation token, minting a fresh one if the cache is
// empty or within 5 minutes of expiry. Returns null on failure (callers log
// and bail, exactly as the old token check did).
async function getInstallationToken() {
  const nowMs = Date.now();
  if (cachedInstallationToken && nowMs < cachedTokenExpiryMs - 5 * 60 * 1000) {
    return cachedInstallationToken;
  }

  let jwt;
  try {
    jwt = buildAppJwt();
  } catch (e) {
    console.error("Failed to build App JWT (check GH_APP_ID / GH_APP_PRIVATE_KEY):", e);
    return null;
  }

  const installationId = GH_APP_INSTALLATION_ID.value();
  try {
    const res = await fetch(
        `https://api.github.com/app/installations/${installationId}/access_tokens`,
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${jwt}`,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pi-briefing-dispatch",
          },
        });
    if (!res.ok) {
      const body = await res.text();
      console.error(`Installation token request failed: ${res.status} ${body}`);
      return null;
    }
    const json = await res.json();
    cachedInstallationToken = json.token;
    // json.expires_at is an ISO timestamp ~1 hour out.
    cachedTokenExpiryMs = new Date(json.expires_at).getTime();
    return cachedInstallationToken;
  } catch (e) {
    console.error("Installation token request error:", e);
    return null;
  }
}

async function deleteQueryInChunks(query) {
  const snap = await query.get();
  const docs = snap.docs;
  for (let i = 0; i < docs.length; i += 450) {
    const batch = admin.firestore().batch();
    docs.slice(i, i + 450).forEach((d) => batch.delete(d.ref));
    await batch.commit();
  }
}

// Triggered when a user requests deletion by creating deletionRequests/{uid}.
// Runs with admin privileges; erases all of that user's data and their login.
exports.processAccountDeletion = onDocumentCreated(
    "deletionRequests/{uid}", async (event) => {
      const uid = event.params.uid;
      const db = admin.firestore();

      // 1. Storage: every video stored under this user's folder
      try {
        await admin.storage().bucket(BUCKET)
            .deleteFiles({prefix: `videos/${uid}/`});
      } catch (e) {
        console.error("storage delete failed:", e);
      }

      // 2. Video-library index entries for this user
      await deleteQueryInChunks(
          db.collection("videos").where("threadUid", "==", uid));

      // 3. Thread messages, then the thread document
      await deleteQueryInChunks(
          db.collection("threads").doc(uid).collection("messages"));
      await db.collection("threads").doc(uid).delete().catch(() => {});

      // 4. User profile (includes saved notes + liked topics)
      await db.collection("users").doc(uid).delete().catch(() => {});

      // 5. The sign-in account itself
      try {
        await admin.auth().deleteUser(uid);
      } catch (e) {
        console.error("auth delete failed:", e);
      }

      // 6. Clean up the request document
      await db.collection("deletionRequests").doc(uid).delete().catch(() => {});
    });

// Triggered when the admin requests an email change by creating
// emailChangeRequests/{uid}. Updates the Firebase Auth login email (the source
// of truth that re-populates basicProfile.email on every sign-in) plus the
// Firestore copies, then writes a status back to the request doc for the UI.
exports.processEmailChange = onDocumentCreated(
    "emailChangeRequests/{uid}", async (event) => {
      const uid = event.params.uid;
      const db = admin.firestore();
      const reqRef = db.collection("emailChangeRequests").doc(uid);
      const data = (event.data && event.data.data) ? event.data.data() : {};
      const newEmail = (data.newEmail || "").trim();

      // Only act on freshly queued requests (ignore our own status writeback).
      if (data.status && data.status !== "queued") return;

      const fail = async (msg) => {
        console.error("email change failed:", msg);
        await reqRef.set(
            {status: "error", error: msg, completedAt: new Date().toISOString()},
            {merge: true}).catch(() => {});
      };

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail)) {
        return fail("That doesn't look like a valid email address.");
      }

      try {
        await admin.auth().updateUser(uid, {email: newEmail, emailVerified: true});
      } catch (e) {
        const code = (e && e.code) ? e.code : "";
        if (code === "auth/email-already-exists") {
          return fail("Another account already uses that email address.");
        }
        if (code === "auth/user-not-found") {
          return fail("No sign-in account found for this subscriber.");
        }
        return fail(e.message || String(e));
      }

      // Keep the Firestore copies in step so the change shows immediately and
      // the briefing send (which reads basicProfile.email first) uses it now.
      try {
        await db.collection("users").doc(uid).set({
          basicProfile: {email: newEmail},
          profile: {email: newEmail},
        }, {merge: true});
      } catch (e) {
        console.error("firestore email sync failed:", e);
      }

      await reqRef.set(
          {status: "done", email: newEmail, completedAt: new Date().toISOString()},
          {merge: true}).catch(() => {});
    });

// Triggered the instant the admin queues a send (adminSends/{jobId}). Kicks the
// GitHub Actions worker immediately via repository_dispatch, so the send runs in
// seconds instead of waiting for the 5-minute cron. The worker still performs the
// actual sending and writes status back to the job doc (which the admin UI watches).
exports.dispatchAdminSend = onDocumentCreated(
    {document: "adminSends/{jobId}", secrets: GITHUB_APP_SECRETS},
    async (event) => {
      const jobId = event.params.jobId;
      const snap = event.data;
      const data = (snap && snap.data) ? snap.data() : {};
      // Only fire for freshly queued jobs (ignore later status writes).
      if (data.status && data.status !== "queued") return;

      const token = await getInstallationToken();
      if (!token) {
        console.error("Could not obtain GitHub App installation token; cannot dispatch worker");
        return;
      }

      try {
        const res = await fetch(
            "https://api.github.com/repos/jezcartwright/My-Weekly-Briefing/dispatches",
            {
              method: "POST",
              headers: {
                "Authorization": `Bearer ${token}`,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "pi-briefing-dispatch",
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                event_type: "admin-send",
                client_payload: {jobId},
              }),
            });
        if (!res.ok) {
          const body = await res.text();
          console.error(`GitHub dispatch failed: ${res.status} ${body}`);
        } else {
          console.log(`Dispatched admin-send worker for job ${jobId}`);
        }
      } catch (e) {
        console.error("dispatch error:", e);
      }
    });

// Shared: kick the welcome-send workflow for one user via repository_dispatch.
// The workflow (welcome-send.yml) runs send_welcome.py with WELCOME_UID=uid.
async function dispatchWelcome(uid, source) {
  const token = await getInstallationToken();
  if (!token) {
    console.error("Could not obtain GitHub App installation token; cannot dispatch welcome");
    return false;
  }
  try {
    const res = await fetch(
        "https://api.github.com/repos/jezcartwright/My-Weekly-Briefing/dispatches",
        {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pi-briefing-dispatch",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            event_type: "welcome-new-user",
            client_payload: {uid, source},
          }),
        });
    if (!res.ok) {
      const body = await res.text();
      console.error(`welcome dispatch failed: ${res.status} ${body}`);
      return false;
    }
    console.log(`Dispatched welcome-new-user for ${uid} (${source})`);
    return true;
  } catch (e) {
    console.error("welcome dispatch error:", e);
    return false;
  }
}

// Auto-welcome: a new subscriber's user record (users/{uid}) being created
// kicks the welcome-send workflow. send_welcome.py filters out admin /
// unsubscribed / no-email / already-welcomed, sends once, stamps welcomedAt.
exports.onNewSubscriberWelcome = onDocumentCreated(
    {document: "users/{uid}", secrets: GITHUB_APP_SECRETS},
    async (event) => {
      await dispatchWelcome(event.params.uid, "auto");
    });

// Manual (re)send: the admin "Send welcome email" button creates
// welcomeSends/{uid}. We clear any prior welcomedAt first (the common case is a
// typo'd email that was auto-welcomed, then corrected), kick the same workflow,
// and write a status back for the admin UI to watch.
exports.onWelcomeSendRequest = onDocumentCreated(
    {document: "welcomeSends/{uid}", secrets: GITHUB_APP_SECRETS},
    async (event) => {
      const uid = event.params.uid;
      const db = admin.firestore();
      const reqRef = db.collection("welcomeSends").doc(uid);
      const data = (event.data && event.data.data) ? event.data.data() : {};
      if (data.status && data.status !== "queued") return;

      try {
        await db.collection("users").doc(uid).set(
            {welcomedAt: admin.firestore.FieldValue.delete()}, {merge: true});
      } catch (e) {
        console.error("clear welcomedAt failed:", e);
      }

      const ok = await dispatchWelcome(uid, "manual");
      await reqRef.set(
          ok
            ? {status: "dispatched", completedAt: new Date().toISOString()}
            : {status: "error", error: "Could not kick the welcome workflow.",
               completedAt: new Date().toISOString()},
          {merge: true}).catch(() => {});
    });


// ---------------------------------------------------------------------------
// Unsubscribe — server-side, so it works from any browser or network.
//
// Every email footer links to /unsubscribe.html?t=<token>. firebase.json now
// rewrites that path to THIS function (the old static page is deleted), so
// links already sitting in sent emails keep working with no reissue. Nothing
// runs in the subscriber's browser: no Firebase SDK, no auth, no Firestore
// rules, nothing a corporate firewall can block — it's a plain page served from
// our own domain, the same request that already loads the masthead fine.
//
// Token = base64url(uid|email|HMAC_SHA256(secret,"uid|email")). We verify the
// signature here with the same secret senders.py signs with (proven byte-for-
// byte against a real minted token), then flip `unsubscribed` via the Admin SDK,
// which bypasses Firestore rules.
//
// GET shows a confirm page; the unsubscribe only happens on the POST from the
// Confirm button, so an email-security scanner that pre-fetches the link can't
// unsubscribe anyone by accident. The write is idempotent.
// ---------------------------------------------------------------------------
function verifyUnsubToken(token) {
  try {
    if (!token) return null;
    const raw = Buffer.from(String(token), "base64url");
    if (!raw.length) return null;
    const PIPE = 0x7c;
    const last = raw.lastIndexOf(PIPE); // matches Python raw.rsplit(b"|", 1)
    if (last === -1) return null;
    const msg = raw.subarray(0, last);
    const sig = raw.subarray(last + 1);
    const expected = crypto.createHmac("sha256", UNSUBSCRIBE_SECRET.value())
        .update(msg).digest();
    if (sig.length !== expected.length) return null;
    if (!crypto.timingSafeEqual(sig, expected)) return null;
    const first = msg.indexOf(PIPE); // matches Python msg.split(b"|", 1)
    if (first === -1) return null;
    return {
      uid: msg.subarray(0, first).toString("utf8"),
      email: msg.subarray(first + 1).toString("utf8"),
    };
  } catch (e) {
    return null;
  }
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  }[c]));
}

function unsubPage(title, inner, cls) {
  return "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">" +
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\">" +
    "<title>" + esc(title) + " — Performance Intelligence Weekly Briefing</title>" +
    "<link href=\"https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=IBM+Plex+Serif:wght@500;600&family=Inter:wght@400;600;700&display=swap\" rel=\"stylesheet\">" +
    "<style>" +
    ":root{--orange:#ff6600;--bg:#FBF8F2;--t:#1a1a1a;--b:#E0D8CB}" +
    "*{box-sizing:border-box}html,body{margin:0;padding:0;background:var(--bg);font-family:'Inter',sans-serif;color:var(--t);min-height:100vh;display:flex;flex-direction:column}" +
    ".bar{background:var(--orange);color:#fff;padding:18px 24px;display:flex;align-items:center;gap:14px}" +
    ".bar img{width:36px;height:36px}" +
    ".bar .eyebrow{font-family:'Cormorant Garamond',Georgia,serif;font-size:12px;letter-spacing:.35em;text-transform:uppercase;font-weight:600;opacity:.95}" +
    ".bar .title{font-family:'IBM Plex Serif',Georgia,serif;font-size:22px;font-weight:600;letter-spacing:-.01em;line-height:1}" +
    "main{flex:1;max-width:560px;margin:0 auto;padding:48px 24px;text-align:center}" +
    ".card{background:#fff;border:1px solid var(--b);border-radius:8px;padding:32px;box-shadow:0 1px 0 var(--b),0 20px 40px -24px rgba(0,0,0,.08)}" +
    "h1{font-family:'IBM Plex Serif',Georgia,serif;font-size:26px;font-weight:600;letter-spacing:-.01em;margin:0 0 12px}" +
    "p{font-size:14px;line-height:1.6;margin:0 0 16px}.email{font-weight:700}" +
    ".btn{display:inline-block;background:var(--orange);color:#fff;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:700;font-size:13px;letter-spacing:.05em;text-transform:uppercase;border:none;cursor:pointer;margin-top:16px}" +
    ".btn-secondary{background:#fff;color:var(--t);border:1px solid var(--b);margin-left:10px}" +
    ".error{color:#c00}.success{color:#2E7A3E}" +
    "</style></head><body>" +
    "<header class=\"bar\"><img src=\"https://weeklybriefing.jezcartwright.com/favicon-512x512.png\" alt=\"PI\">" +
    "<div><div class=\"eyebrow\">Performance Intelligence</div><div class=\"title\">Weekly Briefing</div></div></header>" +
    "<main><div class=\"card\">" +
    "<h1" + (cls ? " class=\"" + cls + "\"" : "") + ">" + esc(title) + "</h1>" + inner +
    "</div></main></body></html>";
}

exports.unsubscribe = onRequest(
    {secrets: [UNSUBSCRIBE_SECRET]},
    async (req, res) => {
      const token = (req.method === "POST" && req.body && req.body.t) ?
        req.body.t : (req.query.t || "");
      const parsed = verifyUnsubToken(token);

      if (!parsed) {
        res.status(200).send(unsubPage("Invalid unsubscribe link",
            "<p>This link is malformed or expired. To unsubscribe, reply to any " +
            "briefing email with the word <b>UNSUBSCRIBE</b> and we'll remove you.</p>",
            "error"));
        return;
      }

      const db = admin.firestore();
      const ref = db.collection("users").doc(parsed.uid);
      let snap;
      try {
        snap = await ref.get();
      } catch (e) {
        console.error("unsubscribe read failed:", e);
        res.status(200).send(unsubPage("Something went wrong",
            "<p>We couldn't reach the subscriber list just now. Please try again in " +
            "a moment, or reply <b>UNSUBSCRIBE</b> to any briefing email.</p>", "error"));
        return;
      }

      if (!snap.exists) {
        res.status(200).send(unsubPage("Already removed",
            "<p>We couldn't find this subscription — you may already have been " +
            "removed. No further action needed.</p>", "success"));
        return;
      }

      const data = snap.data() || {};
      const storedEmail =
        (data.basicProfile && data.basicProfile.email) ||
        (data.profile && data.profile.email) || parsed.email;

      if (data.unsubscribed === true) {
        res.status(200).send(unsubPage("Already unsubscribed",
            "<p><span class=\"email\">" + esc(storedEmail) + "</span> is already " +
            "unsubscribed. No further action needed.</p>", "success"));
        return;
      }

      if (req.method === "POST") {
        try {
          await ref.set({
            unsubscribed: true,
            unsubscribedAt: new Date().toISOString(),
          }, {merge: true});
        } catch (e) {
          console.error("unsubscribe write failed:", e);
          res.status(200).send(unsubPage("Something went wrong",
              "<p>We hit an error saving your preference. Please try again, or reply " +
              "<b>UNSUBSCRIBE</b> to any briefing email.</p>", "error"));
          return;
        }
        res.status(200).send(unsubPage("You're unsubscribed",
            "<p><span class=\"email\">" + esc(storedEmail) + "</span> will no longer " +
            "receive the Weekly Briefing. Thank you for having been a subscriber.</p>",
            "success"));
        return;
      }

      // GET: confirmation page. The write happens only on the POST below, so a
      // link-prefetching scanner cannot unsubscribe anyone by merely opening it.
      res.status(200).send(unsubPage("Unsubscribe from the briefing?",
          "<p>We'll stop sending the Weekly Briefing to " +
          "<span class=\"email\">" + esc(storedEmail) + "</span> immediately. Your " +
          "liked topics and notes will be kept in case you change your mind.</p>" +
          "<form method=\"POST\" action=\"\">" +
          "<input type=\"hidden\" name=\"t\" value=\"" + esc(token) + "\">" +
          "<button class=\"btn\" type=\"submit\">Confirm unsubscribe</button>" +
          "<a class=\"btn btn-secondary\" href=\"https://weeklybriefing.jezcartwright.com/\">Cancel — keep me subscribed</a>" +
          "</form>", ""));
    });
