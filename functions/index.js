const {onDocumentCreated} = require("firebase-functions/v2/firestore");
const {defineSecret} = require("firebase-functions/params");
const admin = require("firebase-admin");

admin.initializeApp();

// GitHub fine-grained PAT (Contents: read/write on My-Weekly-Briefing). Used to
// dispatch the admin-send worker the instant a job is queued. Set it with:
//   firebase functions:secrets:set GH_DISPATCH_TOKEN
const GH_DISPATCH_TOKEN = defineSecret("GH_DISPATCH_TOKEN");

const BUCKET = "pi-briefing-38ddc.firebasestorage.app";

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

// Triggered the instant the admin queues a send (adminSends/{jobId}). Kicks the
// GitHub Actions worker immediately via repository_dispatch, so the send runs in
// seconds instead of waiting for the 5-minute cron. The worker still performs the
// actual sending and writes status back to the job doc (which the admin UI watches).
exports.dispatchAdminSend = onDocumentCreated(
    {document: "adminSends/{jobId}", secrets: [GH_DISPATCH_TOKEN]},
    async (event) => {
      const jobId = event.params.jobId;
      const snap = event.data;
      const data = (snap && snap.data) ? snap.data() : {};
      // Only fire for freshly queued jobs (ignore later status writes).
      if (data.status && data.status !== "queued") return;

      const token = GH_DISPATCH_TOKEN.value();
      if (!token) {
        console.error("GH_DISPATCH_TOKEN is not set; cannot dispatch worker");
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
