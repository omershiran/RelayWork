import React, {useEffect, useState} from "react";
import {api, useAction} from "./shared";

const labels = {
  en: {open:"Open Sandbox checkout", confirm:"Simulate payment", done:"Sandbox payment recorded. No money was charged."},
  he: {open:"פתיחת טופס תשלום להדגמה", confirm:"הדמיית תשלום", done:"תשלום הדגמה נרשם. לא חויב כסף."}
};

export function SandboxCheckout({t, lang, threadId, buyer}) {
  const action = useAction(t);
  const [payment, setPayment] = useState(null);
  const [open, setOpen] = useState(false);
  const base = "/conversations/" + threadId;
  const words = labels[lang];
  useEffect(() => { action.run(async () => setPayment(await api(base + "/payment"))); }, [base]);
  if (payment?.status === "SANDBOX_CONFIRMED") return <p className="note">{words.done}</p>;
  if (!buyer) return action.status;
  return <div className="actions">
    {!open && <button disabled={action.busy} onClick={() => action.run(async () => {
      setPayment(await api(base + "/payment", "POST"));
      setOpen(true);
    })}>{words.open}</button>}
    {open && payment && <form onSubmit={event => {
      event.preventDefault();
      action.run(async () => setPayment(await api(base + "/sandbox-checkout", "POST")));
    }}>
      <p>{t.sandbox} · {new Intl.NumberFormat(lang, {style:"currency", currency:"USD"}).format(payment.amount_cents / 100)}</p>
      <button disabled={action.busy}>{words.confirm}</button>
    </form>}
    {action.status}
  </div>;
}
