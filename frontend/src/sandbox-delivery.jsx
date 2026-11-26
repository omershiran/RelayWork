import React, {useEffect, useRef, useState} from "react";
import {api, useAction} from "./shared";

const labels = {
  en: {title:"Sandbox delivery", deliver:"Submit deliverable", body:"Deliverable text", revise:"Request revision",
    dispute:"Open dispute", approve:"Approve delivery", reason:"Reason", planned:"Automatic approval",
    DELIVERED:"Delivered", APPROVED:"Approved", AUTO_APPROVED:"Automatically approved",
    REVISION_REQUESTED:"Revision requested", DISPUTED:"Disputed"},
  he: {title:"אספקה בסביבת הדגמה", deliver:"מסירת תוצר", body:"טקסט התוצר", revise:"בקשת תיקון",
    dispute:"פתיחת סכסוך", approve:"אישור תוצר", reason:"סיבה", planned:"אישור אוטומטי",
    DELIVERED:"נמסר", APPROVED:"אושר", AUTO_APPROVED:"אושר אוטומטית",
    REVISION_REQUESTED:"נדרש תיקון", DISPUTED:"בסכסוך"}
};

export function SandboxDelivery({t, lang, threadId, buyer}) {
  const action = useAction(t);
  const [rows, setRows] = useState([]);
  const [decision, setDecision] = useState(null);
  const prior = useRef(null);
  const base = "/conversations/" + threadId + "/deliveries";
  const words = labels[lang];
  const current = rows.at(-1);
  const refresh = async () => setRows(await api(base));
  useEffect(() => {
    let active = true;
    let timer;
    async function update() {
      try {
        const next = await api(base);
        if (active) setRows(next);
      } finally {
        if (active) timer = setTimeout(() => update().catch(() => {}), 3500);
      }
    }
    action.run(update);
    return () => {active = false; clearTimeout(timer);};
  }, [base]);
  function decide(choice, reason) {
    action.run(async () => {
      await api(base + "/" + current.id + "/decision", "POST", {action:choice, reason});
      setDecision(null);
      await refresh();
    });
  }
  return <section className="publish"><h3>{words.title}</h3>{action.status}
    {rows.map(row => <article className="card message" key={row.id}>
      <strong>{words[row.state]}</strong><p>{row.body}</p>
      {row.reason && <p>{words.reason} · {row.reason}</p>}
      {row.state === "DELIVERED" && <p>{words.planned} · {new Date(row.auto_approve_at).toLocaleString(lang)}</p>}
    </article>)}
    {!buyer && (!current || current.state === "REVISION_REQUESTED") && <form onSubmit={event => {
      event.preventDefault();
      const form = event.currentTarget;
      const body = new FormData(form).get("body");
      if (prior.current?.body !== body) prior.current = {body, client_id:crypto.randomUUID()};
      action.run(async () => {
        await api(base, "POST", prior.current); prior.current = null; form.reset(); await refresh();
      });
    }}><label>{words.body}<textarea name="body" maxLength={10000} required/></label>
      <button disabled={action.busy}>{words.deliver}</button>
    </form>}
    {current && ["DELIVERED", "REVISION_REQUESTED"].includes(current.state) && <div className="actions">
      {buyer && current.state === "DELIVERED" && <>
        <button disabled={action.busy} onClick={() => decide("approve", null)}>{words.approve}</button>
        <button className="secondary" onClick={() => setDecision("revise")}>{words.revise}</button>
      </>}
      <button className="secondary" onClick={() => setDecision("dispute")}>{words.dispute}</button>
    </div>}
    {decision && <form onSubmit={event => {
      event.preventDefault();
      decide(decision, new FormData(event.currentTarget).get("reason"));
    }}><label>{words.reason}<textarea name="reason" minLength={3} maxLength={4000} required/></label>
      <button disabled={action.busy}>{words[decision]}</button>
    </form>}
  </section>;
}
