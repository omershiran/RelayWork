import React, {useState} from "react";

export async function api(path, method = "GET", data) {
  const response = await fetch("/api/v1" + path, {
    method, headers: data ? {"Content-Type":"application/json"} : undefined,
    body: data ? JSON.stringify(data) : undefined
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "request_failed");
  return result;
}

export function Field({label, ...props}) {
  return <label>{label}<input {...props}/></label>;
}

export function useAction(t) {
  const [notice, setNotice] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  return {
    run: async (callback, message = "") => {
      setBusy(true);
      setNotice("");
      try { await callback(); setFailed(false); setNotice(message); }
      catch (error) { setFailed(true); setNotice(t.errors[error.message] || t.error); }
      finally { setBusy(false); }
    },
    busy,
    status: notice && <p className={failed ? "error" : "note"} role={failed ? "alert" : "status"}>{notice}</p>
  };
}
