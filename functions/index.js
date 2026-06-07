const {onCall, HttpsError} = require("firebase-functions/v2/https");
const admin = require("firebase-admin");

admin.initializeApp();

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

// Callable: a signed-in user deletes their own account and all associated data.
exports.deleteMyAccount = onCall(async (request) => {
  const uid = request.auth && request.auth.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "You must be signed in.");
  }
  const db = admin.firestore();

  // 1. Storage: every video stored under this user's folder
  try {
    await admin.storage().bucket(BUCKET).deleteFiles({prefix: `videos/${uid}/`});
  } catch (e) {
    console.error("storage delete failed:", e);
  }

  // 2. Video-library index entries for this user
  await deleteQueryInChunks(db.collection("videos").where("threadUid", "==", uid));

  // 3. Thread messages, then the thread document
  await deleteQueryInChunks(
      db.collection("threads").doc(uid).collection("messages"));
  await db.collection("threads").doc(uid).delete().catch(() => {});

  // 4. User profile (includes saved notes + liked topics)
  await db.collection("users").doc(uid).delete().catch(() => {});

  // 5. The sign-in account itself
  await admin.auth().deleteUser(uid);

  return {ok: true};
});
