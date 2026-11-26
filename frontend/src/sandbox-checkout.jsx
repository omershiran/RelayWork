import React, {useEffect, useState} from "react";
import {SandboxDelivery} from "./sandbox-delivery";
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
  const confirmed = payment?.status === "SANDBOX_CONFIRMED";
  useEffect(() => {
    action.run(async () => setPayment(await api(base + "/payment")));
    if (buyer || confirmed) return;
    const timer = setInterval(() => api(base + "/payment").then(setPayment).catch(() => {}), 3500);
    return () => clearInterval(timer);
  }, [base, buyer, confirmed]);
  if (confirmed) return <><p className="note">{words.done}</p><SandboxDelivery t={t} lang={lang} threadId={threadId} buyer={buyer}/></>;
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
