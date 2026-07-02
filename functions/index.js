const {onDocumentCreated} = require("firebase-functions/v2/firestore");
const {defineSecret} = require("firebase-functions/params");
const admin = require("firebase-admin");
const crypto = require("crypto");

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