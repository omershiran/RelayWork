import React, {useEffect, useRef, useState} from "react";
import {Link} from "react-router-dom";
import {SandboxCheckout} from "./sandbox-checkout";
import {api, Field, useAction} from "./shared";

export const quoteLabels = {
  en:{quotes:"Quotes", quoteForm:"Send quote", counter:"Counter offer", reject:"Reject",
      withdraw:"Withdraw", accept:"Accept quote", confirm:"Confirm order at this price", paymentPending:"Order created. Waiting for a payment provider.", checkoutPreview:"Try checkout preview", ACCEPTED:"Accepted", quoteTerms:"Terms and revision policy", quoteDelivered:"Expected deliverables",
      quotePrice:"Price (USD cents)", quoteSaved:"Quote sent.", quoteUpdated:"Quote updated.",
      OPEN:"Open", EXPIRED:"Expired", COUNTERED:"Countered", WITHDRAWN:"Withdrawn", REJECTED:"Rejected"},
  he:{quotes:"הצעות מחיר", quoteForm:"שליחת הצעת מחיר", counter:"הצעה נגדית", reject:"דחייה",
      withdraw:"משיכה", accept:"קבלת הצעה", confirm:"אישור הזמנה במחיר זה", paymentPending:"ההזמנה נוצרה וממתינה לחיבור ספק סליקה.", checkoutPreview:"ניסיון בתצוגת התשלום", ACCEPTED:"התקבלה", quoteTerms:"תנאים ומדיניות תיקונים", quoteDelivered:"תוצרים צפויים",
      quotePrice:"מחיר בסנטים של דולר", quoteSaved:"ההצעה נשלחה.", quoteUpdated:"ההצעה עודכנה.",
      OPEN:"פתוחה", EXPIRED:"פג תוקף", COUNTERED:"נענתה בהצעה נגדית", WITHDRAWN:"נמשכה", REJECTED:"נדחתה"}
};

export function Quotes({t, lang, threadId}) {
  const action = useAction(t);
  const [rows, setRows] = useState([]);
  const [confirmation, setConfirmation] = useState(null);
  const [formTarget, setFormTarget] = useState(undefined);
  const previous = useRef(null);
  const endpoint = "/conversations/" + threadId + "/quotes";
  const refresh = async () => setRows(await api(endpoint));
  useEffect(() => {
    let active = true;
    let timer;
    async function tick() {
      try {
        const next = await api(endpoint);
        if (active) setRows(next);
      } finally {
        if (active) timer = setTimeout(() => tick().catch(() => {}), 3000);
      }
    }
    action.run(tick);
    return () => { active = false; clearTimeout(timer); };
  }, [endpoint]);
  const money = new Intl.NumberFormat(lang, {style:"currency", currency:"USD"});
  const dates = new Intl.DateTimeFormat(lang, {dateStyle:"medium", timeStyle:"short"});
  return <section className="publish"><h2>{t.quotes}</h2>{action.status}
    {rows.filter(row => row.disposition === "ACCEPTED").map(row =>
      import.meta.env.VITE_DEPLOYMENT === "sandbox"
        ? <SandboxCheckout key={row.id} t={t} lang={lang} threadId={threadId} buyer={!row.mine}/>
        : <p key={row.id} className="note">{t.paymentPending} <Link to="/checkout-preview">{t.checkoutPreview}</Link></p>
    )}
    {rows.map(row => <article className="card message" key={row.id}>
      <strong>{money.format(row.price_cents / 100)}</strong> · {t[row.disposition]} · {row.mine ? t.mine : t.other}{row.author_agent_id && " · " + t.agentSender}
      <p>{row.description}</p><p>{t.quoteDelivered} · {row.deliverables}</p><p>{t.quoteTerms} · {row.terms}</p>
      <p>{t.due} · {dates.format(new Date(row.due_at))}</p>
      <p>{t.expires} · {dates.format(new Date(row.expires_at))}</p>
      {row.disposition === "OPEN" && <div className="actions">
        {row.can_accept && <button onClick={() => setConfirmation(row.id)}>{t.accept}</button>}
        {!row.mine && <button className="secondary" onClick={() => setFormTarget(row.id)}>{t.counter}</button>}
        <button className="secondary" disabled={action.busy} onClick={() => action.run(async () => {
          await api(endpoint + "/" + row.id + (row.mine ? "/withdraw" : "/reject"), "POST");
          await refresh();
        }, t.quoteUpdated)}>{row.mine ? t.withdraw : t.reject}</button>
      </div>}
      {row.can_accept && confirmation === row.id && <div className="actions">
        <button disabled={action.busy} onClick={() => action.run(async () => {
          await api(endpoint + "/" + row.id + "/accept", "POST", {confirmed_price_cents:row.price_cents});
          setConfirmation(null);
          await refresh();
        })}>{t.confirm} · {money.format(row.price_cents / 100)}</button>
      </div>}
    </article>)}
    {!rows.some(row => ["OPEN", "ACCEPTED"].includes(row.disposition)) && formTarget === undefined &&
      <button className="secondary" onClick={() => setFormTarget(null)}>{t.quoteForm}</button>}
    {formTarget !== undefined && <form className="card" onSubmit={event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.currentTarget));
      data.price_cents = Number(data.price_cents);
      data.due_at = new Date(data.due_at).toISOString();
      data.expires_at = new Date(data.expires_at).toISOString();
      data.supersedes_id = formTarget;
      const signature = JSON.stringify(data);
      if (previous.current?.signature !== signature) previous.current = {signature, id:crypto.randomUUID()};
      action.run(async () => {
        await api(endpoint, "POST", {...data, client_id:previous.current.id});
        setFormTarget(undefined);
        previous.current = null;
        await refresh();
      }, t.quoteSaved);
    }}>
      <Field name="price_cents" type="number" min="1" max="100000000" required label={t.quotePrice}/>
      {Object.entries({description:t.description, deliverables:t.quoteDelivered, terms:t.quoteTerms}).map(([name, label]) =>
        <label key={name}>{label}<textarea name={name} minLength={2} maxLength={4000} required/></label>)}
      <Field label={t.due} name="due_at" type="datetime-local" required/>
      <Field label={t.expires} name="expires_at" type="datetime-local" required/>
      <button disabled={action.busy}>{formTarget ? t.counter : t.quoteForm}</button>
    </form>}
  </section>;
}
